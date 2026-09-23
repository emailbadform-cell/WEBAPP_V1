import os, math, json, threading, time, tempfile, uuid, shutil, zipfile
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager

# Cloud secret support. Credentials stay server-side and must never be committed to GitHub.
# Option 1: KALSHI_PRIVATE_KEY_PEM environment variable containing the PEM text.
if os.getenv("KALSHI_PRIVATE_KEY_PEM") and not os.getenv("KALSHI_PRIVATE_KEY_PATH"):
    secret_path = Path(tempfile.gettempdir()) / "kalshi_private_key.pem"
    secret_path.write_text(os.environ["KALSHI_PRIVATE_KEY_PEM"], encoding="utf-8")
    os.environ["KALSHI_PRIVATE_KEY_PATH"] = str(secret_path)

# Option 2: Render Secret File named kalshi_private_key.pem.
# Render mounts secret files under /etc/secrets/.
render_secret = Path("/etc/secrets/kalshi_private_key.pem")
if not os.getenv("KALSHI_PRIVATE_KEY_PATH") and render_secret.exists():
    os.environ["KALSHI_PRIVATE_KEY_PATH"] = str(render_secret)

from fastapi import FastAPI, Request

# V2.28.21: one canonical runtime research-data folder.
# On Render set only: RDFZ_DIR=/var/data/RDFZ
RDFZ_DIR = Path(os.getenv("RDFZ_DIR", str(Path(__file__).with_name("RDFZ"))))
RDFZ_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("RDFZ_DIR", str(RDFZ_DIR))
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
from starlette.background import BackgroundTask
from fastapi.staticfiles import StaticFiles
import numpy as np
import pandas as pd
import requests
import joblib

import live_btc15m_predictor as core
from kalshi_market_stream import KalshiMarketStream
from advanced_signals import SignalSuite, L2Worker
SIGNALS = SignalSuite(Path(__file__).parent)
L2 = L2Worker(interval=float(os.getenv("L2_INTERVAL","1.0")))

# V2.19.1 Forward Signal deployment: frozen feature families selected by V10.33 research.
# These models use BRTI path dynamics only. They do not consume Kalshi prices, target,
# current side, Decision, TR, MP, or order flow.
FORWARD_MODELS = joblib.load(Path(__file__).with_name("forward_signal_models.joblib"))
FORWARD_THRESHOLDS = {5:0.225, 10:0.175, 30:0.125, 60:0.125}

def _nearest_tick_value(ticks, now_t, seconds):
    if ticks is None or len(ticks)==0: return None
    tt=pd.to_datetime(ticks["time"],utc=True,errors="coerce")
    target=pd.Timestamp(now_t)-pd.Timedelta(seconds=seconds)
    ix=np.where(tt.values <= target.to_datetime64())[0]
    if len(ix)==0: return None
    try: return float(ticks.iloc[ix[-1]]["value"])
    except Exception: return None

def _forward_features(ticks, current, now_t):
    px=float(current); hist={}
    for sec in (1,2,3,5,10,15,20,30,60,120):
        old=_nearest_tick_value(ticks,now_t,sec)
        hist[sec]=0.0 if old is None or old<=0 else (px/old-1.0)*10000.0
    f={f"br_r{k}":hist[k] for k in hist}
    f.update({
      "vel2":hist[2]/2, "vel5":hist[5]/5, "vel10":hist[10]/10, "vel30":hist[30]/30,
      "accel2_5":hist[2]/2-hist[5]/5, "accel5_10":hist[5]/5-hist[10]/10,
      "accel10_30":hist[10]/10-hist[30]/30,
      "jerk":(hist[2]/2-hist[5]/5)-(hist[5]/5-hist[10]/10),
    })
    # Path diagnostics from the last 30s of BRTI ticks.
    if ticks is not None and len(ticks):
        q=ticks.copy(); q["time"]=pd.to_datetime(q["time"],utc=True,errors="coerce")
        q=q[(q.time>=pd.Timestamp(now_t)-pd.Timedelta(seconds=30)) & (q.time<=pd.Timestamp(now_t))].dropna(subset=["time","value"])
        vals=q.value.astype(float).to_numpy() if len(q) else np.array([px])
    else: vals=np.array([px])
    dif=np.diff(vals)
    f["path_consistency"]=float(abs(np.sign(dif).sum())/max(1,len(dif))) if len(dif) else 0.0
    f["path_direction"]=float(np.sign(hist[10] if hist[10] else hist[5]))
    if len(vals)>1:
        rr=np.diff(np.log(np.maximum(vals,1e-9)))*10000
        f["rv30"]=float(np.std(rr)); f["range30_bps"]=float((vals.max()-vals.min())/px*10000)
        f["pos30"]=float((px-vals.min())/max(1e-9,vals.max()-vals.min()))
        f["dist_ma30_bps"]=float((px-vals.mean())/px*10000)
    else:
        f.update({"rv30":0.0,"range30_bps":0.0,"pos30":0.5,"dist_ma30_bps":0.0})
    old60=_nearest_tick_value(ticks,now_t,60);
    if ticks is not None and len(ticks):
        q=ticks.copy(); q["time"]=pd.to_datetime(q["time"],utc=True,errors="coerce"); q=q[(q.time>=pd.Timestamp(now_t)-pd.Timedelta(seconds=60)) & (q.time<=pd.Timestamp(now_t))].dropna(subset=["time","value"]); vv=q.value.astype(float).to_numpy()
        rr=np.diff(np.log(np.maximum(vv,1e-9)))*10000 if len(vv)>1 else np.array([]); f["rv60"]=float(np.std(rr)) if len(rr) else 0.0
    else: f["rv60"]=0.0
    return f

def forward_signal_state(engine, r, now):
    try:
        ticks=engine.ticks.copy() if engine is not None and engine.ticks is not None else None
        if ticks is None or len(ticks)<2: return {"state":"SIDEWAYS","label":"SIDEWAYS","horizon_s":5,"confidence":0.0,"prob_up":0.5,"horizons":{}}
        f=_forward_features(ticks,float(r.get("btc")),pd.Timestamp(now))
        probs={}; states={}
        for h,b in FORWARD_MODELS.items():
            X=pd.DataFrame([{k:f.get(k,0.0) for k in b["features"]}])
            pu=float(b["model"].predict_proba(X)[0,1]); conf=abs(pu-0.5)
            probs[h]=pu; states[h]="UP" if pu>=0.5 else "DOWN"
        # Core horizon is the longest confident horizon that agrees with 5/10 direction;
        # otherwise contract quickly to the shortest confident horizon.
        confident=[h for h in (5,10,30,60) if abs(probs[h]-.5)>=FORWARD_THRESHOLDS[h]]
        if not confident:
            return {"state":"SIDEWAYS","label":"SIDEWAYS","horizon_s":5,"confidence":max(abs(v-.5) for v in probs.values())*2,"prob_up":probs[5],"horizons":probs}
        base=states[5] if 5 in confident else states[min(confident)]
        horizon=min(confident)
        for h in (10,30,60):
            if h in confident and states[h]==base: horizon=h
            elif h in confident and states[h]!=base: break
        pu=probs[horizon]; direction="UP" if pu>=.5 else "DOWN"
        recent=f.get("br_r10",0.0); continuation=(recent>0 and direction=="UP") or (recent<0 and direction=="DOWN")
        phase="CONTINUATION" if continuation else "REVERSAL"
        # V2.24.3 display clarity: retain REVERSAL internally/research, but do not show the word in Forward Signal.
        display_label=f"{direction} — CONTINUATION" if continuation else direction
        return {"state":direction,"label":display_label,"phase":phase,"horizon_s":horizon,"confidence":abs(pu-.5)*2,"prob_up":pu,"horizons":probs,"recent_10s_bps":recent,"rv30":f.get("rv30",0.0)}
    except Exception as e:
        return {"state":"SIDEWAYS","label":"SIDEWAYS","horizon_s":5,"confidence":0.0,"prob_up":0.5,"horizons":{},"error":str(e)}


# V2.5 multi-exchange OF + V10.19 calibrated TR/Decision research display.
# No logging. BRTI remains settlement reference. Web app performs no research logging.
MULTI_EXCHANGE_URLS={
    "coinbase":"https://api.exchange.coinbase.com/products/BTC-USD/ticker",
    "kraken":"https://api.kraken.com/0/public/Ticker?pair=XBTUSD",
    "bitstamp":"https://www.bitstamp.net/api/v2/ticker/btcusd/",
    "gemini":"https://api.gemini.com/v1/pubticker/btcusd",
}
MULTI_EXCHANGE_BOOK_URLS={
    "coinbase":"https://api.exchange.coinbase.com/products/BTC-USD/book",
    "kraken":"https://api.kraken.com/0/public/Depth",
    "bitstamp":"https://www.bitstamp.net/api/v2/order_book/btcusd/",
    "gemini":"https://api.gemini.com/v1/book/btcusd",
    "crypto_com":"https://api.crypto.com/exchange/v1/public/get-book",
}
MX_LOCK=threading.Lock()
MX_LATEST={}
MX_ERROR=None
MOF_LATEST={}
MOF_ERROR={}
MOF_PREVIOUS={}
MX_RUNNING=True

def _mx_float(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _book_rows(rows):
    out=[]
    for row in rows or []:
        try:
            if isinstance(row,dict):
                px=float(row.get("price")); sz=float(row.get("amount"))
            else:
                px=float(row[0]); sz=float(row[1])
            if px>0 and sz>=0: out.append((px,sz))
        except Exception: pass
    return out

def fetch_exchange_book(exchange):
    headers={"User-Agent":"btc15m-web-multi-of/1.0"}
    if exchange=="coinbase":
        j=requests.get(MULTI_EXCHANGE_BOOK_URLS["coinbase"],params={"level":2},headers=headers,timeout=8).json()
        bids=_book_rows(j.get("bids")); asks=_book_rows(j.get("asks"))
    elif exchange=="kraken":
        j=requests.get(MULTI_EXCHANGE_BOOK_URLS["kraken"],params={"pair":"XBTUSD","count":500},headers=headers,timeout=8).json()
        v=next(iter((j.get("result") or {}).values()),{})
        bids=_book_rows(v.get("bids")); asks=_book_rows(v.get("asks"))
    elif exchange=="bitstamp":
        j=requests.get(MULTI_EXCHANGE_BOOK_URLS["bitstamp"],headers=headers,timeout=8).json()
        bids=_book_rows(j.get("bids")); asks=_book_rows(j.get("asks"))
    elif exchange=="gemini":
        j=requests.get(MULTI_EXCHANGE_BOOK_URLS["gemini"],params={"limit_bids":500,"limit_asks":500},headers=headers,timeout=8).json()
        bids=_book_rows(j.get("bids")); asks=_book_rows(j.get("asks"))
    elif exchange=="crypto_com":
        j=requests.get(
            MULTI_EXCHANGE_BOOK_URLS["crypto_com"],
            params={"instrument_name":"BTC_USD","depth":50},
            headers=headers,timeout=8
        ).json()
        result=j.get("result") or {}
        data=result.get("data") if isinstance(result,dict) else None
        if isinstance(data,list):
            data=data[0] if data else {}
        if not isinstance(data,dict):
            data=result if isinstance(result,dict) else {}
        bids=_book_rows(data.get("bids")); asks=_book_rows(data.get("asks"))
    else: raise ValueError(exchange)
    if not bids or not asks: raise RuntimeError(f"{exchange} empty book")
    return {"bids":sorted(bids,reverse=True),"asks":sorted(asks),"time":time.time()}

def _depth(levels,mid,bps,side):
    frac=bps/10000.0
    if side=="ask":
        cut=mid*(1+frac); return sum(sz for px,sz in levels if px<=cut)
    cut=mid*(1-frac); return sum(sz for px,sz in levels if px>=cut)

def summarize_book(book,prev=None):
    bids=book["bids"]; asks=book["asks"]
    best_bid=bids[0][0]; best_ask=asks[0][0]; mid=(best_bid+best_ask)/2
    bd=_depth(bids,mid,5,"bid"); ad=_depth(asks,mid,5,"ask")
    imb=(bd-ad)/(bd+ad+1e-12)
    bid_dep=ask_dep=0.0
    if prev:
        pb=float(prev.get("bid_depth_5bps",0)); pa=float(prev.get("ask_depth_5bps",0))
        if pb>1e-9: bid_dep=max(0.0,(pb-bd)/pb)
        if pa>1e-9: ask_dep=max(0.0,(pa-ad)/pa)
    score=max(-1.0,min(1.0,0.60*imb+0.40*(ask_dep-bid_dep)))
    pressure="BUY" if score>=0.15 else "SELL" if score<=-0.15 else "NEUTRAL"
    return {"pressure":pressure,"pressure_score":score,"imbalance":imb,
            "ask_depletion":ask_dep,"bid_depletion":bid_dep,
            "bid_depth_5bps":bd,"ask_depth_5bps":ad}

def combine_books(venues):
    good=list(venues.values())
    if not good: return {"pressure":"NEUTRAL","imbalance":0.0,"ask_depletion":0.0,"bid_depletion":0.0,"n":0,"consensus":"0/0 NEUTRAL"}
    avg=lambda k: sum(float(v.get(k,0.0)) for v in good)/len(good)
    score=avg("pressure_score")
    pressure="BUY" if score>=0.15 else "SELL" if score<=-0.15 else "NEUTRAL"
    buy=sum(v.get("pressure")=="BUY" for v in good); sell=sum(v.get("pressure")=="SELL" for v in good)
    neutral=len(good)-buy-sell
    side="BUY" if buy>sell else "SELL" if sell>buy else "NEUTRAL"
    votes=max(buy,sell) if side!="NEUTRAL" else neutral
    return {"pressure":pressure,"pressure_score":score,"imbalance":avg("imbalance"),
            "ask_depletion":avg("ask_depletion"),"bid_depletion":avg("bid_depletion"),
            "n":len(good),"consensus":f"{votes}/{len(good)} {side}",
            "buy_count":buy,"sell_count":sell,"neutral_count":neutral}

def fetch_multi_exchange_prices(timeout=2.5):
    out={"ts":time.time()}
    try:
        out["coinbase"]=_mx_float(requests.get(MULTI_EXCHANGE_URLS["coinbase"],timeout=timeout).json().get("price"))
    except Exception:
        out["coinbase"]=None
    try:
        j=requests.get(MULTI_EXCHANGE_URLS["kraken"],timeout=timeout).json()
        v=next(iter((j.get("result") or {}).values()),{})
        out["kraken"]=_mx_float((v.get("c") or [None])[0])
    except Exception:
        out["kraken"]=None
    try:
        out["bitstamp"]=_mx_float(requests.get(MULTI_EXCHANGE_URLS["bitstamp"],timeout=timeout).json().get("last"))
    except Exception:
        out["bitstamp"]=None
    try:
        out["gemini"]=_mx_float(requests.get(MULTI_EXCHANGE_URLS["gemini"],timeout=timeout).json().get("last"))
    except Exception:
        out["gemini"]=None
    vals=[out[k] for k in ("coinbase","kraken","bitstamp","gemini") if out.get(k) is not None]
    if vals:
        vals=sorted(vals); n=len(vals)
        out["median"]=vals[n//2] if n%2 else (vals[n//2-1]+vals[n//2])/2
        out["mean"]=sum(vals)/n
        out["spread"]=max(vals)-min(vals)
        out["n"]=n
    else:
        out.update({"median":None,"mean":None,"spread":None,"n":0})
    return out

def multi_exchange_worker():
    global MX_LATEST,MX_ERROR,MX_RUNNING,MOF_LATEST,MOF_ERROR,MOF_PREVIOUS
    while MX_RUNNING:
        started=time.monotonic()
        try:
            cur=fetch_multi_exchange_prices()
            with MX_LOCK:
                MX_LATEST=cur; MX_ERROR=None
        except Exception as e:
            with MX_LOCK: MX_ERROR=str(e)

        venues={}; errs={}
        for ex in ("coinbase","kraken","bitstamp","gemini","crypto_com"):
            try:
                book=fetch_exchange_book(ex)
                cur=summarize_book(book,MOF_PREVIOUS.get(ex))
                MOF_PREVIOUS[ex]=cur
                venues[ex]=cur
            except Exception as e:
                errs[ex]=str(e)
        with MX_LOCK:
            _mof_ts=time.time()
            MOF_LATEST={"venues":venues,"combined":combine_books(venues),"ts":_mof_ts,"time":_mof_ts}
            MOF_ERROR=errs
        time.sleep(max(0.05,2.0-(time.monotonic()-started)))


engine = None
threads = []
KALSHI_MARKET_STREAM = None
STATE_WAKE = threading.Event()
STATE_GENERATION = 0

def _kalshi_ws_event(_kind, _rec):
    # Execution-domain event: wake state construction without feeding prediction architects.
    STATE_WAKE.set()

def _kalshi_ws_auth_headers():
    return core._auth_headers_full_path('GET', core.KALSHI_WS_PATH)


def clean(v):
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        v = float(v)
        return v if math.isfinite(v) else None
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (datetime, pd.Timestamp)):
        return pd.Timestamp(v).isoformat()
    if isinstance(v, dict):
        return {str(k): clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


_KALSHI_BOOK_CACHE={"ticker":None,"ts":0.0,"data":{}}
def kalshi_execution_market(ticker):
    """Execution-domain Kalshi book. WebSocket primary, REST recovery only; never feeds predictors."""
    global _KALSHI_BOOK_CACHE
    if not ticker: return {}
    if KALSHI_MARKET_STREAM is not None:
        live=KALSHI_MARKET_STREAM.book(ticker)
        if live and live.get('book_healthy') and float(live.get('quote_age_ms') or 1e9) <= 5000:
            return live
    now=time.time()
    if _KALSHI_BOOK_CACHE.get('ticker')==ticker and now-_KALSHI_BOOK_CACHE.get('ts',0)<2.0:
        return dict(_KALSHI_BOOK_CACHE.get('data') or {})
    try:
        u=f"https://external-api.kalshi.com/trade-api/v2/markets/{ticker}/orderbook"
        j=requests.get(u,params={'depth':10},headers={'User-Agent':'btc15m-execution-research/1.0'},timeout=4).json()
        ob=j.get('orderbook_fp') or j.get('orderbook') or {}
        def levels(name):
            out=[]
            for row in ob.get(name) or []:
                try: out.append((float(row[0]),float(row[1])))
                except Exception: pass
            return out
        y=levels('yes_dollars') or [(float(a)/100.0,float(b)) for a,b in (ob.get('yes') or [])]
        n=levels('no_dollars') or [(float(a)/100.0,float(b)) for a,b in (ob.get('no') or [])]
        yb=max((x[0] for x in y),default=None); nb=max((x[0] for x in n),default=None)
        ya=(1.0-nb) if nb is not None else None; na=(1.0-yb) if yb is not None else None
        data={'yes_bid':yb,'yes_ask':ya,'no_bid':nb,'no_ask':na,
              'yes_gross_multiplier':(1/ya if ya and ya>0 else None),'no_gross_multiplier':(1/na if na and na>0 else None),
              'source':'Kalshi REST orderbook fallback','timestamp_utc':datetime.now(timezone.utc).isoformat(),'book_healthy':True,'transport':'REST_FALLBACK'}
        _KALSHI_BOOK_CACHE={'ticker':ticker,'ts':now,'data':data}; return data
    except Exception as e:
        return {'error':str(e)}

STATE_LOCK=threading.Lock()
STATE_CACHE=None
STATE_CACHE_AT=0.0
STATE_CACHE_ERROR=None
STATE_CACHE_RUNNING=True
STATE_CACHE_WORKER_STARTED_AT=0.0
STATE_CACHE_WORKER_LAST_BEGIN=0.0
STATE_CACHE_WORKER_LAST_END=0.0

def state_cache_worker():
    global STATE_CACHE, STATE_CACHE_AT, STATE_CACHE_ERROR
    global STATE_CACHE_WORKER_STARTED_AT, STATE_CACHE_WORKER_LAST_BEGIN, STATE_CACHE_WORKER_LAST_END
    STATE_CACHE_WORKER_STARTED_AT=time.time()
    while STATE_CACHE_RUNNING:
        started=time.time()
        STATE_CACHE_WORKER_LAST_BEGIN=started
        try:
            fresh=build_state()
            if isinstance(fresh, dict):
                # Publish by atomic reference assignment. HTTP readers never wait
                # for a state-construction lock.
                STATE_CACHE=fresh
                STATE_CACHE_AT=time.time()
                STATE_CACHE_ERROR=None
                try: auto_paper_tick(fresh)
                except Exception as _ape: _append_trade_event({"event_type":"AUTO_ERROR","source":"SERVER_AUTO_V1","detail":str(_ape)})
                try: prospective_instrumentation_tick(fresh)
                except Exception as _pie: _append_trade_event({"event_type":"INSTRUMENTATION_ERROR","source":"SERVER_INSTRUMENTATION_V1","detail":str(_pie)})
                # Independent options/regime experiment: never touches orders or existing decisions.
                if os.getenv('BTC15M_OPTIONS_EXPERIMENT_ENABLED') == '1':
                    try:
                        from web_options_adapter import observe as _observe_options
                        _observe_options(fresh)
                    except Exception as _oe:
                        _append_trade_event({'event_type':'OPTIONS_EXPERIMENT_ERROR','detail':str(_oe)})
                # Independent research observer: no order authority; fail isolated.
                if os.getenv("BTC15M_SHADOW15_OBSERVER_ENABLED") == "1":
                    try:
                        from web_shadow15_adapter import observe_web_state
                        observe_web_state(fresh)
                    except Exception as _soe:
                        _append_trade_event({"event_type":"SHADOW15_OBSERVER_ERROR","source":"SHADOW15_RESEARCH_ONLY","detail":str(_soe)})
        except Exception as e:
            STATE_CACHE_ERROR=str(e)
        finally:
            STATE_CACHE_WORKER_LAST_END=time.time()
        elapsed=time.time()-started
        # Event-driven wake for Kalshi book/trade changes; 50ms coalescing floor, 750ms watchdog ceiling.
        wait_s=max(0.05, 0.75-elapsed)
        STATE_WAKE.wait(wait_s); STATE_WAKE.clear()

# V2.28.30 candidate: persistent per-contract source-second Final Target accumulator.
FINAL_TARGET_SECONDS={}
FINAL_TARGET_LOCK=threading.RLock()

def _capture_final_target_second(r, now):
    """Synchronize an immutable per-contract 60-second settlement bucket.

    V2.28.40 repairs the old snapshot-only collector.  Instead of capturing only
    the latest displayed quote, every call backfills all source-timestamped BRTI
    ticks already present in engine.ticks for the active settlement minute.  A
    completed source second is therefore retained and sample_count is monotonic.
    """
    ticker=str((r or {}).get("ticker") or (getattr(engine,"market",{}) or {}).get("ticker") or "")
    closep=pd.to_datetime((r or {}).get("close_time"),utc=True,errors="coerce")
    if not ticker or pd.isna(closep): return {}
    start=closep-pd.Timedelta(seconds=60)
    additions={}
    try:
        ticks=getattr(engine,"ticks",None)
        if ticks is not None and len(ticks):
            q=ticks[["time","value"]].copy()
            q["time"]=pd.to_datetime(q["time"],utc=True,errors="coerce")
            q["value"]=pd.to_numeric(q["value"],errors="coerce")
            q=q.dropna().sort_values("time")
            # Never include the close-boundary second itself.
            q=q[(q.time>=start)&(q.time<closep)]
            if len(q):
                q["second"]=q.time.dt.floor("s")
                for _,row in q.groupby("second",as_index=False).tail(1).iterrows():
                    additions[pd.Timestamp(row["second"]).isoformat()]=float(row["value"])
    except Exception:
        pass
    # Also capture the latest result quote if it carries a valid source time.
    qt=pd.to_datetime((r or {}).get("quote_time"),utc=True,errors="coerce")
    val=(r or {}).get("btc")
    if not pd.isna(qt) and val is not None and start <= qt < closep:
        additions[qt.floor("s").isoformat()]=float(val)
    with FINAL_TARGET_LOCK:
        bucket=FINAL_TARGET_SECONDS.setdefault(ticker,{})
        bucket.update(additions)
        # Keep the just-completed contract for diagnostics; prune only older ones.
        if len(FINAL_TARGET_SECONDS)>3:
            for k in list(FINAL_TARGET_SECONDS)[:-3]: FINAL_TARGET_SECONDS.pop(k,None)
        return dict(bucket)

def _kalshi_primary_final_target(local_state, r, now):
    """Use Kalshi CF Benchmarks final-minute average as primary when fresh.

    Local 60-second reconstruction is always retained under verifier_local.
    Outside the final minute (or if the Kalshi feed is stale/missing), the
    local diagnostic state remains the displayed fallback.
    """
    try:
        ks=engine.kalshi_final_target_snapshot() if hasattr(engine,"kalshi_final_target_snapshot") else None
        closep=pd.to_datetime((r or {}).get("close_time"),utc=True,errors="coerce")
        nowp=pd.to_datetime(now,utc=True)
        in_window=(not pd.isna(closep)) and ((closep-pd.Timedelta(seconds=60)) < nowp <= (closep+pd.Timedelta(seconds=2)))
        fresh=bool(ks and ks.get("age_ms") is not None and float(ks.get("age_ms")) <= 3000.0)
        if in_window and fresh and ks.get("value") is not None:
            target=(r or {}).get("target")
            v=float(ks["value"]); n=int(ks.get("window_size") or 0)
            return {
                "schema":"FINAL_TARGET_KALSHI_PRIMARY_V1", "source":"KALSHI_CF_BENCHMARKS_WS",
                "authority":"KALSHI_FINAL_MINUTE_AVERAGE", "final_target":v, "sample_count":n,
                "window_size":n, "remaining_samples_est":max(0,60-n),
                "window_start_ts_ms":ks.get("window_start_ts_ms"),
                "window_end_ts_exclusive":ks.get("window_end_ts_exclusive"),
                "feed_age_ms":ks.get("age_ms"),
                "distance_to_target":(v-float(target)) if target is not None else None,
                "verifier_local":local_state,
                "kalshi_minus_local":(v-float(local_state.get("final_target"))) if local_state and local_state.get("final_target") is not None else None,
                "official_result":False, "note":"Kalshi live final-minute BRTI average; official market result is separate."
            }
    except Exception as e:
        if isinstance(local_state,dict): local_state=dict(local_state); local_state["kalshi_primary_error"]=str(e)
    # V2.28.41: Web display authority is Kalshi only. Local reconstruction remains
    # nested diagnostic data and can never masquerade as the displayed Final Target.
    return {
        "schema":"FINAL_TARGET_KALSHI_PRIMARY_V2", "source":"KALSHI_CF_BENCHMARKS_WS",
        "authority":"KALSHI_FINAL_MINUTE_AVERAGE", "final_target":None, "sample_count":0,
        "window_size":0, "feed_age_ms":(ks or {}).get("age_ms") if 'ks' in locals() and ks else None,
        "status":"WAITING_KALSHI", "verifier_local":local_state, "official_result":False,
        "note":"Kalshi live Final Target unavailable/stale; local reconstruction is diagnostic only."
    }

def _data_quality_state(r, feed, execution_market, final_target):
    """V2.28.43 fail-closed data quality summary. No prediction authority."""
    flags=[]
    try:
        age=float((feed or {}).get("age_s"))
        if age>2.5: flags.append("BRTI_STALE")
    except Exception:
        flags.append("BRTI_AGE_UNKNOWN")
    em=execution_market or {}
    try:
        qage=float(em.get("quote_age_ms"))
        if qage>2000.0: flags.append("BOOK_STALE")
    except Exception:
        flags.append("BOOK_AGE_UNKNOWN")
    if em.get("book_healthy") is False: flags.append("BOOK_UNHEALTHY")
    if not em.get("yes_ask") or not em.get("no_ask"): flags.append("BOOK_SIDE_MISSING")
    ft=final_target or {}
    if ft.get("final_target") is None: flags.append("BENCHMARK_UNAVAILABLE")
    sec=(r or {}).get("seconds_left")
    if sec is not None and float(sec)<=0: flags.append("ROLLOVER_OR_EXPIRED")
    execution_ok=not any(x in flags for x in ("BRTI_STALE","BRTI_AGE_UNKNOWN","BOOK_STALE","BOOK_AGE_UNKNOWN","BOOK_UNHEALTHY","BOOK_SIDE_MISSING","ROLLOVER_OR_EXPIRED"))
    return {"schema":"BTC15M_DATA_QUALITY_V1","flags":flags,"valid_for_execution_eval":execution_ok,"valid_for_model_eval":not any(x in flags for x in ("BRTI_STALE","BRTI_AGE_UNKNOWN","ROLLOVER_OR_EXPIRED"))}

def build_state():
    global engine
    if engine is None:
        return {"status":"starting"}
    r, err = engine.snapshot()
    of, of_err = engine.orderflow_snapshot()
    if r is None:
        return {"status":"starting", "error":err, "orderflow_error":of_err}
    now = datetime.now(timezone.utc)
    sec = max(0.0, (r["close_time"] - now).total_seconds())
    preserved_ft_seconds=_capture_final_target_second(r,now)
    local_final_target = core.settlement_window_state(engine.ticks, r.get('btc'), r.get('target'), r.get('close_time'), now, preserved_ft_seconds)
    final_target = _kalshi_primary_final_target(local_final_target, r, now)
    tr = core.target_reachability(r["distance"], r["atr1m_14"], sec, r.get("prediction"))
    mp = core.move_projection(r)
    mp_progress = core._mp_progress_state(r, mp)
    # V2.10: zones and progress now refer to the same projection leg.
    # When Base is achieved the core immediately re-arms a fresh leg.
    mp["progress"] = mp_progress
    mp["near"] = mp_progress["near"]
    mp["base"] = mp_progress["base"]
    mp["extended"] = mp_progress["extended"]
    mp["projection_status"] = mp_progress.get("projection_status")
    mp["projection_leg"] = mp_progress.get("leg_id")
    mp["completed_legs"] = mp_progress.get("completed_legs")
    ds = SIGNALS.decision_state(engine.ticks, r.get("btc"), r.get("target"), sec, now)
    ds["current_side"] = "ABOVE" if float(r.get("distance",0.0)) >= 0 else "BELOW"
    ds["chart"] = r.get("prediction")
    ds["agree"] = (ds.get("decision") == r.get("prediction"))
    ds["role"] = "PREDICTIVE PRICE-GEOMETRY — CURRENT SIDE DISPLAY ONLY"
    candles = engine.candles
    spark = []
    candle_data = []
    chart_gap_fill_count = 0
    if candles is not None and len(candles):
        # V2.16 DISPLAY-ONLY continuous chart. Build a complete 1-minute grid
        # ending at the current UTC minute, carry the last real close across
        # missing minutes, and explicitly attach the live BRTI to the newest
        # displayed candle. Synthetic display candles never enter engine/model data.
        c = candles.copy()
        required = {"time", "open", "high", "low", "close"}
        if required.issubset(c.columns):
            c["time"] = pd.to_datetime(c["time"], utc=True, errors="coerce").dt.floor("min")
            c = c.dropna(subset=["time"]).sort_values("time").drop_duplicates("time", keep="last")
            if len(c):
                end_minute = pd.Timestamp(now).floor("min")
                start_minute = end_minute - pd.Timedelta(minutes=359)
                c = c[(c["time"] >= start_minute) & (c["time"] <= end_minute)].set_index("time")
                full_index = pd.date_range(start=start_minute, end=end_minute, freq="1min", tz="UTC")
                c = c.reindex(full_index)
                chart_gap_fill_count = int(c["close"].isna().sum())
                carry = c["close"].ffill()
                # If the requested 90m window begins before the first real candle,
                # seed the left edge from the first known close strictly for display.
                carry = carry.bfill()
                for col in ["open", "high", "low", "close"]:
                    c[col] = c[col].fillna(carry)
                # Guarantee the live minute reaches the current BRTI instead of
                # leaving a visual right-edge gap between history and live price.
                live_px = r.get("btc")
                if live_px is not None and math.isfinite(float(live_px)):
                    idx = end_minute
                    prior_close = c.loc[idx, "close"] if idx in c.index else float(live_px)
                    if pd.isna(prior_close): prior_close = float(live_px)
                    if idx in c.index:
                        if pd.isna(c.loc[idx, "open"]): c.loc[idx, "open"] = prior_close
                        c.loc[idx, "close"] = float(live_px)
                        c.loc[idx, "high"] = max(float(c.loc[idx, "high"]), float(live_px))
                        c.loc[idx, "low"] = min(float(c.loc[idx, "low"]), float(live_px))
                # Display-only EMA overlays are calculated from the exact continuous
                # chart close series so they never feed back into model features.
                # This keeps the overlays visually continuous across display-only
                # carry-forward minutes while preserving the engine candles unchanged.
                c["ema9_display"] = c["close"].ewm(span=9, adjust=False).mean()
                c["ema21_display"] = c["close"].ewm(span=21, adjust=False).mean()
                c = c.reset_index().rename(columns={"index":"time"})
                spark = [{"t":clean(t), "v":clean(v)} for t, v in zip(c["time"], c["close"])]
                candle_data = [{
                    "t":clean(row["time"]),"o":clean(row["open"]),"h":clean(row["high"]),
                    "l":clean(row["low"]),"c":clean(row["close"]),
                    "e9":clean(row.get("ema9_display")),"e21":clean(row.get("ema21_display"))
                } for _,row in c.iterrows()]
        if not candle_data:
            c = candles.tail(360)
            c = c.copy()
            c["ema9_display"] = c["close"].ewm(span=9, adjust=False).mean()
            c["ema21_display"] = c["close"].ewm(span=21, adjust=False).mean()
            spark = [{"t":clean(t), "v":clean(v)} for t, v in zip(c["time"], c["close"])]
            candle_data = [{
                "t":clean(row["time"]),"o":clean(row["open"]),"h":clean(row["high"]),
                "l":clean(row["low"]),"c":clean(row["close"]),
                "e9":clean(row.get("ema9_display")),"e21":clean(row.get("ema21_display"))
            } for _,row in c.iterrows() if all(k in row for k in ["time","open","high","low","close"])]
    with MX_LOCK:
        mx=dict(MX_LATEST) if MX_LATEST else {}
        mx_err=MX_ERROR
    if mx.get("median") is not None and r.get("btc") is not None:
        mx["brti_minus_median"]=float(r.get("btc"))-float(mx["median"])
    else:
        mx["brti_minus_median"]=None
    mx["error"]=mx_err

    with MX_LOCK:
        mof = dict(MOF_LATEST) if MOF_LATEST else {"venues":{},"combined":{}}
        mof_errors = dict(MOF_ERROR) if MOF_ERROR else {}

    # V10.19/V10.18 research layers — display only; web app does not log.
    early = core._of_early_detection(mof, now)
    tr_of = core.target_reachability_of_context(r, mof, early)
    of_micro = core.of_micro_bias_research(mof, early)
    mp_of = core.mp_of_context_research(r, mof, early)
    fusion = core.signal_fusion_research(r, mof, early)
    validated_of = core.validated_orderflow_research(mof)
    of_response = core.of_price_response_research(r, mof, now, validated_of.get('score'))
    mp_of_price = core.mp_of_price_confirmation(mp, of_response)
    flip = core.flip_reachthrough_research(r, now, tr.get("calibrated_cross_estimate"))
    exrev = core.exhaustion_reversal_research(r, mp, mof, of_response)
    # V2.17 / V10.32: research-backed settlement and execution-risk context.
    # These layers are strictly diagnostic/execution context and never override
    # Chart Signal, Market Decision, TR, FLIP/RE-FLIP, or structural MP.
    settlement = core.settlement_confirmation_research(r, sec)
    cross_hazard = core.target_cross_hazard_research(r, sec)
    profit_reversal = core.profit_reversal_risk_research(
        r, mp=mp, fusion=fusion, exrev=exrev, fl=flip, mpof=mp_of, seconds_left=sec
    )
    if KALSHI_MARKET_STREAM is not None:
        KALSHI_MARKET_STREAM.set_markets([r.get("ticker"), (engine.next_market or {}).get("ticker") if engine is not None else None, getattr(engine,"expected_next_ticker",None) if engine is not None else None])
        # V2.28.23: bridge execution-domain WS evidence into rollover metadata
        # prefetch only. No Kalshi market price enters any prediction architect.
        if engine is not None and getattr(engine,"expected_next_ticker",None):
            _nb=KALSHI_MARKET_STREAM.book(engine.expected_next_ticker)
            if _nb.get("book_healthy") and hasattr(engine,"note_ws_next_market_seen"):
                engine.note_ws_next_market_seen(engine.expected_next_ticker)
    execution_market = kalshi_execution_market(r.get("ticker"))
    forward_signal = SIGNALS.forward_state(engine.ticks, r.get("btc"), now)
    ghost_thread = SIGNALS.ghost_state(engine.ticks, r.get("btc"), now, forward_signal)
    l2, l2_errors = L2.snapshot()
    feed = engine.feed_status() if hasattr(engine, "feed_status") else {}
    display = {
        "structure_15m": core.interpret_15m_structure(r),
        "mp_thesis": core.interpret_mp_thesis(r, mp),
        "tr_of": core.interpret_target_of(r, tr_of),
        "of_early": core.interpret_of_early(early),
        "of_early_confirmation": core.of_early_confirmation(early),
        "of_micro": core.interpret_of_micro(of_micro),
        "of_price_response": of_response.get("state"),
        "validated_of": validated_of.get("direction") + " — " + validated_of.get("basis"),
        "mp_of_price": mp_of_price.get("state"),
        "flip": flip.get("state"),
    }

    return clean({
        "status":"ok","version":"V2.28.35 / V10.39.19",
        "server_time":now,
        "market":{
            "ticker":r.get("ticker"), "target":r.get("target"), "brti":r.get("btc"),
            "distance":r.get("distance"), "close_time":r.get("close_time"), "seconds_left":sec,
            "source":r.get("source"), "quote_time":r.get("quote_time"),
            "brti_feed":r.get("brti_feed"), "brti_age_s":feed.get("age_s"), "feed_mode":feed.get("mode"),
            "next_ticker":feed.get("next_ticker"), "next_prefetched":feed.get("next_prefetched"),
            "next_ticker_expected":feed.get("next_ticker_expected"),
            "next_prefetch_started":feed.get("next_prefetch_started"),
            "next_prefetch_attempts":feed.get("next_prefetch_attempts"),
            "next_market_found":feed.get("next_market_found"),
            "next_target_loaded":feed.get("next_target_loaded"),
            "rollover_mode":feed.get("rollover_mode"),
            "rollover_latency_ms":feed.get("rollover_latency_ms"),
            "fallback_discovery_used":feed.get("fallback_discovery_used")
        },
        "chart":{
            "prediction":r.get("prediction"), "p_above":r.get("p_above"), "p_below":r.get("p_below"),
            "raw_p_above":r.get("model_p_above"), "mtf_adjustment":r.get("multitf_adjustment"),
            "checkpoint":r.get("checkpoint_model"), "model_kind":r.get("model_kind"), "model_family":r.get("model_family")
        },
        "decision":ds,
        "settlement":r.get("settlement_forecast") or {},
        "final_target":final_target,
        "gt15_ft_challengers": core.gt_final_target_challengers({**r,"_final_target":final_target}) if hasattr(core,"gt_final_target_challengers") else {},
        "flip_challenger_v1":{"mode":"STRICT_PRECROSS_CAPTURE_GEOM_TRAJ_OF_60S_PERSIST2","authority":False,"research_only":True},
        "reachability":tr,
        "target_of_context":tr_of,
        "anticipation": core.technical_anticipation_state(r),
        "trend_transition": core.trend_transition_challenger_v2(r, getattr(engine,"ticks",None), now),
            "move_projection":mp,
        "mp_of_context":mp_of,
        "of_early":early,
        "of_micro":of_micro,
        "decision_fusion":fusion,
        "of_price_response":of_response,
        "validated_of":validated_of,
        "mp_of_price":mp_of_price,
        "flip":flip,
        "exhaustion_reversal":exrev,
        "settlement_protection":settlement,
        "target_cross_hazard":cross_hazard,
        "profit_reversal_risk":profit_reversal,
        "execution_market":execution_market,
        "data_quality":_data_quality_state(r, feed, execution_market, final_target),
        "auto_paper":auto_paper_status(),
        "kalshi_stream":KALSHI_MARKET_STREAM.health() if KALSHI_MARKET_STREAM is not None else {"status":"OFF"},
        "forward_signal":forward_signal,
        "ghost_thread":ghost_thread,
        "ghost_thread_recursive":r.get("_gt_common_anchor_path") or {},
        "l2":{**l2,"errors":l2_errors},
        "display":display,
        "orderflow":of,
        "structure":{
            "m1_trend":r.get("m1_trend"), "m5_trend":r.get("m5_trend"), "m15_trend":r.get("m15_trend"),
            "protected_high":r.get("protected_high"), "protected_low":r.get("protected_low"),
            "dev15_hh_then_ll":r.get("dev15_hh_then_ll"), "dev15_ll_then_hh":r.get("dev15_ll_then_hh"),
            "m15_bos_up":r.get("m15_bos_up"), "m15_bos_dn":r.get("m15_bos_dn"),
            "m15_choch_up":r.get("m15_choch_up"), "m15_choch_dn":r.get("m15_choch_dn"),
            "atr1m_14":r.get("atr1m_14"),
            "rsi14":r.get("rsi14"), "kdj_k":r.get("kdj_k"), "kdj_d":r.get("kdj_d"), "kdj_j":r.get("kdj_j"),
            "macd_line":r.get("macd_line"), "macd_signal":r.get("macd_signal"), "macd_hist":r.get("macd_hist"),
        },
        "errors":{"engine":err, "orderflow":of_err},
        "sparkline":spark,
        "candles":candle_data,
        "chart_gap_fill_count":chart_gap_fill_count,
        "multi_exchange":mx,
        "multi_orderflow":{
            **mof,
            "errors":mof_errors
        },
    })



def market_stream_sync_worker():
    """Continuously subscribe current + deterministic next Kalshi markets.

    Rollover plumbing only. Kalshi book prices never enter prediction architects.
    """
    global KALSHI_MARKET_STREAM
    while STATE_CACHE_RUNNING:
        try:
            if engine is not None and KALSHI_MARKET_STREAM is not None:
                r=engine.snapshot() if hasattr(engine,"snapshot") else None
                cur=((r or {}).get("ticker") if isinstance(r,dict) else None) or ((getattr(engine,"market",None) or {}).get("ticker"))
                expected=getattr(engine,"expected_next_ticker",None)
                pref=(getattr(engine,"next_market",None) or {}).get("ticker")
                KALSHI_MARKET_STREAM.set_markets([cur,pref,expected])
                if expected:
                    nb=KALSHI_MARKET_STREAM.book(expected)
                    # Existence of any received book/event state is enough to accelerate metadata lookup.
                    # Book prices are not prediction inputs.
                    if nb and (nb.get("timestamp_utc") or nb.get("book_sid") is not None or nb.get("book_seq") is not None):
                        if hasattr(engine,"note_ws_next_market_seen"):
                            engine.note_ws_next_market_seen(expected)
        except Exception:
            pass
        time.sleep(0.25)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine, threads, STATE_CACHE_RUNNING, MX_RUNNING
    STATE_CACHE_RUNNING=True
    _load_auto_state()
    L2.start()
    engine = core.LiveEngine(
        allow_coinbase_fallback=os.getenv("ALLOW_COINBASE_FALLBACK","0") == "1",
        brti_interval=float(os.getenv("BRTI_INTERVAL","2")),
        orderflow_interval=float(os.getenv("ORDERFLOW_INTERVAL","2")),
    )
    global KALSHI_MARKET_STREAM
    KALSHI_MARKET_STREAM = KalshiMarketStream(core.KALSHI_WS_URL, _kalshi_ws_auth_headers,
        event_log_path=str(RDFZ_DIR / "BTC15M_KALSHI_WS_EVENTS.ndjson"), on_event=_kalshi_ws_event)
    KALSHI_MARKET_STREAM.start()
    threads = [
        threading.Thread(target=engine.worker, daemon=True),
        threading.Thread(target=engine.orderflow_worker, daemon=True),
        threading.Thread(target=multi_exchange_worker, daemon=True),
        threading.Thread(target=state_cache_worker, daemon=True),
        threading.Thread(target=market_stream_sync_worker, daemon=True),
    ]
    for t in threads: t.start()
    yield
    MX_RUNNING=False
    STATE_CACHE_RUNNING=False
    L2.stop()
    if KALSHI_MARKET_STREAM is not None: KALSHI_MARKET_STREAM.stop()
    engine.stop()

app = FastAPI(title="BTC15M V2.28.40 / V10.39.24 Server Auto Paper V1 + Atomic RDFZ + Fast Rollover", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).with_name("static")), name="static")

# V2.26.1 runtime hardening + paper-trade lifecycle persistence.
TRADE_EVENT_LOG_PATH = Path(os.getenv("TRADE_EVENT_LOG_PATH", str(RDFZ_DIR / "BTC15M_AUTO_PAPER_EVENTS.ndjson")))
TRADE_EVENT_LOCK = threading.Lock()
CLIENT_TELEMETRY_LOG_PATH = Path(os.getenv("CLIENT_TELEMETRY_LOG_PATH", str(RDFZ_DIR / "BTC15M_CLIENT_LATENCY.ndjson")))
CLIENT_TELEMETRY_LOCK = threading.Lock()



# V2.28.24 / V10.39.14: instrumentation-only prospective recorder.
# No prediction or Auto Paper policy authority is changed by this layer.
PROSPECTIVE_LOG_PATH = Path(os.getenv("PROSPECTIVE_LOG_PATH", str(RDFZ_DIR / "BTC15M_V10_39_24_PROSPECTIVE_ARCHITECT_SNAPSHOTS.ndjson")))
WS_HEALTH_LOG_PATH = Path(os.getenv("WS_HEALTH_LOG_PATH", str(RDFZ_DIR / "BTC15M_WS_HEALTH_SUMMARY.ndjson")))
PROSPECTIVE_LOG_LOCK = threading.Lock()
WS_HEALTH_LOG_LOCK = threading.Lock()
PROSPECTIVE_MIN_INTERVAL_S = float(os.getenv("PROSPECTIVE_MIN_INTERVAL_S","0.50"))
WS_HEALTH_INTERVAL_S = float(os.getenv("WS_HEALTH_INTERVAL_S","5.0"))
_LAST_PROSPECTIVE_AT = 0.0
_LAST_WS_HEALTH_AT = 0.0
_STATE_SEQUENCE = 0

def _append_ndjson(path, lock, rec):
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        row={"logged_at_utc":datetime.now(timezone.utc).isoformat(),**clean(rec)}
        with lock:
            with path.open("a",encoding="utf-8") as f:
                f.write(json.dumps(row,separators=(",",":"),ensure_ascii=False)+"\n")
        return row
    except Exception:
        return None

def _settlement_provenance(d):
    # V1 rollover result is explicitly a proxy. Official Kalshi settlement is
    # recorded only if a future authoritative field is actually present.
    m=(d or {}).get("market") or {}
    st=(d or {}).get("settlement") or {}
    return {
        "proxy_basis":"last_observed_brti_vs_target",
        "proxy_brti":m.get("brti"),
        "proxy_target":m.get("target"),
        "official_result":st.get("official_result"),
        "official_source":st.get("official_source"),
        "official_available":bool(st.get("official_result") is not None),
    }

def prospective_instrumentation_tick(d):
    global _LAST_PROSPECTIVE_AT,_LAST_WS_HEALTH_AT,_STATE_SEQUENCE
    if not isinstance(d,dict) or d.get("status")!="ok": return
    now=time.time()
    if now-_LAST_PROSPECTIVE_AT >= PROSPECTIVE_MIN_INTERVAL_S:
        _LAST_PROSPECTIVE_AT=now; _STATE_SEQUENCE+=1
        m=d.get("market") or {}; em=d.get("execution_market") or {}
        rec={
            "schema":"BTC15M_PROSPECTIVE_STATE_V1",
            "app_version":"V2.28.43","research_version":"V10.39.25",
            "state_sequence":_STATE_SEQUENCE,
            "server_time":d.get("server_time"),
            "ticker":m.get("ticker"),"target":m.get("target"),"brti":m.get("brti"),
            "distance":m.get("distance"),"seconds_left":m.get("seconds_left"),
            "brti_age_s":m.get("brti_age_s"),"feed_mode":m.get("feed_mode"),"rollover_telemetry":{"next_ticker":m.get("next_ticker"),"next_prefetched":m.get("next_prefetched"),"next_ticker_expected":m.get("next_ticker_expected"),"next_prefetch_started":m.get("next_prefetch_started"),"next_prefetch_attempts":m.get("next_prefetch_attempts"),"next_market_found":m.get("next_market_found"),"next_target_loaded":m.get("next_target_loaded"),"rollover_mode":m.get("rollover_mode"),"rollover_latency_ms":m.get("rollover_latency_ms"),"fallback_discovery_used":m.get("fallback_discovery_used")},
            "decision":d.get("decision"),"settlement":d.get("settlement"),"final_target":d.get("final_target"),
            "gt15_ft_challengers":d.get("gt15_ft_challengers"),"flip_challenger_v1":d.get("flip_challenger_v1"),
            "trend_transition":d.get("trend_transition"),
            "chart":d.get("chart"),"reachability":d.get("reachability"),
            "target_of_context":d.get("target_of_context"),"anticipation":d.get("anticipation"),
            "move_projection":d.get("move_projection"),"mp_of_context":d.get("mp_of_context"),
            "of_early":d.get("of_early"),"of_micro":d.get("of_micro"),
            "decision_fusion":d.get("decision_fusion"),"of_price_response":d.get("of_price_response"),
            "validated_of":d.get("validated_of"),"mp_of_price":d.get("mp_of_price"),
            "flip":d.get("flip"),"exhaustion_reversal":d.get("exhaustion_reversal"),
            "settlement_protection":d.get("settlement_protection"),
            "target_cross_hazard":d.get("target_cross_hazard"),
            "profit_reversal_risk":d.get("profit_reversal_risk"),
            "forward_signal":d.get("forward_signal"),
            "ghost_thread":d.get("ghost_thread"),
            "ghost_thread_recursive":d.get("ghost_thread_recursive"),
            "structure":d.get("structure"),"display":d.get("display"),
            "orderflow":d.get("orderflow"),"multi_orderflow":d.get("multi_orderflow"),
            "l2":d.get("l2"),"multi_exchange":d.get("multi_exchange"),
            "execution_market":{
                "yes_bid":em.get("yes_bid"),"yes_ask":em.get("yes_ask"),
                "no_bid":em.get("no_bid"),"no_ask":em.get("no_ask"),
                "quote_age_ms":em.get("quote_age_ms"),"book_healthy":em.get("book_healthy"),
                "book_sid":em.get("book_sid"),"book_seq":em.get("book_seq"),
                "transport":em.get("transport"),"timestamp_utc":em.get("timestamp_utc")
            },
            "auto_gate":auto_paper_status(d).get("gate"),
            "settlement_provenance":_settlement_provenance(d)
        }
        _append_ndjson(PROSPECTIVE_LOG_PATH,PROSPECTIVE_LOG_LOCK,rec)
    if now-_LAST_WS_HEALTH_AT >= WS_HEALTH_INTERVAL_S:
        _LAST_WS_HEALTH_AT=now
        _append_ndjson(WS_HEALTH_LOG_PATH,WS_HEALTH_LOG_LOCK,{
            "schema":"BTC15M_WS_HEALTH_V1","app_version":"V2.28.43",
            "ticker":((d.get("market") or {}).get("ticker")),
            "seconds_left":((d.get("market") or {}).get("seconds_left")),
            "kalshi_stream":d.get("kalshi_stream"),
            "execution_market":d.get("execution_market"),
            "brti_age_s":((d.get("market") or {}).get("brti_age_s")),
            "api_state_cache_at":STATE_CACHE_AT
        })

# V2.28.21: server-owned frozen Auto Paper V1. Manual browser paper trading is intentionally separate.
AUTO_PAPER_POLICY={"version":"AUTO_PAPER_V1_FROZEN_2026_09_16","min_seconds":20.0,"max_seconds":180.0,"max_ask":0.75,"min_decision_persistence_s":2.0,"require_settlement_agreement":True}
AUTO_PAPER_STATE_PATH=Path(os.getenv("AUTO_PAPER_STATE_PATH",str(RDFZ_DIR / "BTC15M_AUTO_PAPER_STATE.json")))
AUTO_PAPER_LOCK=threading.RLock()
AUTO_PAPER={"enabled":True,"position":None,"decision_side":None,"decision_since":0.0,"last_shadow_key":None,"last_exit":None,"shadow_positions":[],"contract_stats":{},"coverage_candidate":None}

def _save_auto_state():
    try:
        AUTO_PAPER_STATE_PATH.parent.mkdir(parents=True,exist_ok=True)
        AUTO_PAPER_STATE_PATH.write_text(json.dumps({"enabled":bool(AUTO_PAPER["enabled"]),"position":AUTO_PAPER["position"],"last_exit":AUTO_PAPER["last_exit"]},separators=(",",":")),encoding="utf-8")
    except Exception: pass

def _load_auto_state():
    try:
        if AUTO_PAPER_STATE_PATH.exists():
            j=json.loads(AUTO_PAPER_STATE_PATH.read_text(encoding="utf-8"))
            AUTO_PAPER["enabled"]=True; AUTO_PAPER["position"]=j.get("position"); AUTO_PAPER["last_exit"]=j.get("last_exit")
    except Exception: pass

def _side_book(side,em):
    return {"bid":em.get("yes_bid"),"ask":em.get("yes_ask")} if side=="ABOVE" else {"bid":em.get("no_bid"),"ask":em.get("no_ask")}

def _settlement_side(st):
    x=str((st or {}).get("prediction") or "").upper()
    return "ABOVE" if "ABOVE" in x else ("BELOW" if "BELOW" in x else None)

def _trade_context(d):
    m=d.get("market") or {}; em=d.get("execution_market") or {}; ds=d.get("decision") or {}; st=d.get("settlement") or {}; fl=d.get("flip") or {}; xr=d.get("exhaustion_reversal") or {}; pr=d.get("profit_reversal_risk") or {}
    return {"ticker":m.get("ticker"),"brti":m.get("brti"),"target":m.get("target"),"seconds_left":m.get("seconds_left"),"yes_bid":em.get("yes_bid"),"yes_ask":em.get("yes_ask"),"no_bid":em.get("no_bid"),"no_ask":em.get("no_ask"),"quote_age_ms":em.get("quote_age_ms"),"quote_timestamp_utc":em.get("timestamp_utc"),"book_healthy":em.get("book_healthy"),"book_sid":em.get("book_sid"),"book_seq":em.get("book_seq"),"transport":em.get("transport"),"decision":ds.get("decision"),"decision_confidence":ds.get("confidence"),"settlement_prediction":st.get("prediction"),"settlement_confidence":st.get("confidence"),"flip_count":fl.get("flip_count"),"reversal":xr.get("reversal"),"profit_risk_level":pr.get("level"),"profit_risk_score":pr.get("score")}

def _auto_event(kind,d,extra=None,pos=None):
    pos=pos or AUTO_PAPER.get("position") or {}
    payload={"event_type":kind,"source":"SERVER_AUTO_V1","policy":AUTO_PAPER_POLICY["version"],"app_version":"V2.28.43","research_version":"V10.39.25","state_sequence":_STATE_SEQUENCE,"settlement_provenance":_settlement_provenance(d),"trade_id":pos.get("trade_id"),"side":pos.get("side"),"entry":pos.get("entry"),"stake":pos.get("stake",100.0),"context":_trade_context(d)}
    if extra: payload.update(extra)
    return _append_trade_event(payload)

def _auto_gate(d,now):
    m=d.get("market") or {}; ds=d.get("decision") or {}; em=d.get("execution_market") or {}; side=ds.get("decision"); sec=float(m.get("seconds_left") or -1); settle=_settlement_side(d.get("settlement")); b=_side_book(side,em) if side in ("ABOVE","BELOW") else {"ask":None,"bid":None}
    if side!=AUTO_PAPER.get("decision_side"):
        AUTO_PAPER["decision_side"]=side; AUTO_PAPER["decision_since"]=now
    persist=max(0.0,now-float(AUTO_PAPER.get("decision_since") or now)); reasons=[]
    ask=b.get("ask")
    if side not in ("ABOVE","BELOW"): reasons.append("no Decision")
    if sec<AUTO_PAPER_POLICY["min_seconds"] or sec>AUTO_PAPER_POLICY["max_seconds"]: reasons.append("outside 20-180s")
    try: ask=float(ask)
    except Exception: ask=float('nan')
    if not math.isfinite(ask) or ask<=0 or ask>=1: reasons.append("no ask")
    elif ask>AUTO_PAPER_POLICY["max_ask"]: reasons.append("ask >75c")
    if persist<AUTO_PAPER_POLICY["min_decision_persistence_s"]: reasons.append("Decision <2s")
    if AUTO_PAPER_POLICY["require_settlement_agreement"] and settle!=side: reasons.append("Settlement disagreement/unavailable")
    if em.get("book_healthy") is False: reasons.append("book unhealthy")
    try:
        if float(m.get("brti_age_s")) > 2.5: reasons.append("BRTI stale >2.5s")
    except Exception: reasons.append("BRTI age unavailable")
    try:
        if float(em.get("quote_age_ms")) > 2000.0: reasons.append("book stale >2.0s")
    except Exception: reasons.append("book age unavailable")
    return {"pass":not reasons,"side":side,"seconds_left":sec,"ask":ask if math.isfinite(ask) else None,"bid":b.get("bid"),"settlement":settle,"persistence_s":persist,"reasons":reasons}

def _paper_position(ticker,side,entry,bid,now,kind,gate):
    return {"trade_id":str(uuid.uuid4()),"ticker":ticker,"side":side,"stake":100.0,"entry":float(entry),"quantity":100.0/float(entry),"peak_bid":float(bid) if bid is not None else float(entry),"trough_bid":float(bid) if bid is not None else float(entry),"entered_at":now,"opp_since":0.0,"kind":kind,"blocked_by":list((gate or {}).get("reasons") or [])}

def _shadow_tick(d, g, now):
    m=d.get("market") or {}; em=d.get("execution_market") or {}; ticker=m.get("ticker"); side=g.get("side")
    if not ticker or side not in ("ABOVE","BELOW"): return
    # One live rejected shadow per side/contract; repeated snapshots do not create trades.
    live=[x for x in AUTO_PAPER["shadow_positions"] if x.get("ticker")==ticker and x.get("side")==side and not x.get("closed")]
    if (not g.get("pass")) and not live and g.get("ask") is not None:
        p=_paper_position(ticker,side,g["ask"],g.get("bid"),now,"SHADOW_REJECTED",g); AUTO_PAPER["shadow_positions"].append(p); _auto_event("SHADOW_ENTRY",d,{"gate":g,"blocked_by":p["blocked_by"]},p)
    for p in list(AUTO_PAPER["shadow_positions"]):
        if p.get("closed"): continue
        if p.get("ticker")!=ticker or float(m.get("seconds_left") or 0)<=0:
            brti=p.get("last_brti",m.get("brti")); target=p.get("target",m.get("target"))
            if brti is not None and target is not None:
                wins=(float(brti)>=float(target)) if p["side"]=="ABOVE" else (float(brti)<float(target)); xp=1.0 if wins else 0.0; pnl=p["quantity"]*(xp-p["entry"]); p["closed"]=True; _auto_event("SHADOW_EXIT",d,{"exit":xp,"pnl":pnl,"reason":"EXPIRY / ROLLOVER","blocked_by":p["blocked_by"]},p)
            continue
        p["last_brti"]=m.get("brti"); p["target"]=m.get("target"); b=_side_book(p["side"],em); bid=b.get("bid")
        try: bid=float(bid)
        except Exception: continue
        p["peak_bid"]=max(p["peak_bid"],bid); p["trough_bid"]=min(p["trough_bid"],bid)
        opp=(d.get("decision") or {}).get("decision") not in (None,p["side"]); p["opp_since"]=(p.get("opp_since") or now) if opp else 0.0
        reason=None; cur=bid-p["entry"]; give=p["peak_bid"]-bid
        if p.get("opp_since") and now-p["opp_since"]>=5: reason="AUTO - DECISION OPPOSITION 5S"
        elif cur>=.08 and give>=.05: reason="AUTO - PROFIT GIVEBACK"
        elif float(m.get("seconds_left") or 999)<=45 and cur>=.08: reason="AUTO - LATE PROFIT CAPTURE"
        elif (p["peak_bid"]-p["entry"])>=.08 and 0<cur<=.01: reason="AUTO - PROFIT RISK"
        if reason:
            pnl=p["quantity"]*(bid-p["entry"]); p["closed"]=True; _auto_event("SHADOW_EXIT",d,{"exit":bid,"pnl":pnl,"reason":reason,"mfe":p["peak_bid"]-p["entry"],"mae":p["entry"]-p["trough_bid"],"blocked_by":p["blocked_by"]},p)

def _coverage_candidate(g,d,now):
    m=d.get("market") or {}; ticker=m.get("ticker"); side=g.get("side")
    if not ticker or side not in ("ABOVE","BELOW") or g.get("ask") is None:return
    score=100-20*len(g.get("reasons") or [])+float((d.get("decision") or {}).get("confidence") or 0)
    c=AUTO_PAPER.get("coverage_candidate")
    if c is None or c.get("ticker")!=ticker or score>c.get("score",-1): AUTO_PAPER["coverage_candidate"]={"ticker":ticker,"side":side,"ask":g["ask"],"bid":g.get("bid"),"score":score,"gate":g,"at":now}

def auto_paper_tick(d):
    if not isinstance(d,dict) or d.get("status")!="ok": return
    now=time.time()
    with AUTO_PAPER_LOCK:
        g=_auto_gate(d,now); m=d.get("market") or {}; ticker=m.get("ticker"); side=g.get("side")
        _shadow_tick(d,g,now); _coverage_candidate(g,d,now)
        if ticker and side:
            key=f"{ticker}|{side}|{int(g.get('seconds_left',0)//5)*5}"
            if key!=AUTO_PAPER.get("last_shadow_key"):
                AUTO_PAPER["last_shadow_key"]=key
                _auto_event("SHADOW_OPPORTUNITY",d,{"gate":g,"shadow_policies":["decision_only","decision_settlement","decision_gt","decision_structure","decision_of_l2","hold_settlement","decision_flip","decision_flip_5s","target_recross","reversal","of_l2_opposition","take_profit","trailing_protection","time_exit","multi_risk"]},pos={"side":side,"stake":100.0})
        pos=AUTO_PAPER.get("position")
        if not AUTO_PAPER.get("enabled"):
            return
        stats=AUTO_PAPER["contract_stats"].setdefault(ticker,{"primary":0,"coverage":0}) if ticker else {"primary":0,"coverage":0}
        if pos is None and g["pass"]:
            bid=g.get("bid"); entry=float(g["ask"]); pos=_paper_position(ticker,side,entry,bid,now,"PRIMARY",g); pos.update({"last_brti":m.get("brti"),"target":m.get("target"),"last_update_event_at":now}); stats["primary"]+=1
            AUTO_PAPER["position"]=pos; _save_auto_state(); _auto_event("ENTRY",d,{"entry_source":"SERVER_AUTO_V1","trade_class":"PRIMARY","gate":g},pos); return
        # Coverage path is separate from Primary. If no Primary has entered this contract, force the best executable candidate by 90s.
        if pos is None and ticker and stats["primary"]==0 and stats["coverage"]==0 and float(m.get("seconds_left") or 999)>0 and float(m.get("seconds_left") or 999)<=90:
            c=AUTO_PAPER.get("coverage_candidate") or {}
            if c.get("ticker")==ticker:
                livebook=_side_book(c["side"],d.get("execution_market") or {}); liveask=livebook.get("ask"); livebid=livebook.get("bid")
                try: liveask=float(liveask)
                except Exception: liveask=float("nan")
                if math.isfinite(liveask) and 0<liveask<1:
                    pos=_paper_position(ticker,c["side"],liveask,livebid,now,"FORCED_COVERAGE",c.get("gate")); pos.update({"last_brti":m.get("brti"),"target":m.get("target"),"last_update_event_at":now}); stats["coverage"]+=1; AUTO_PAPER["position"]=pos; _save_auto_state(); _auto_event("ENTRY",d,{"entry_source":"FORCED_COVERAGE","trade_class":"FORCED_COVERAGE","gate":c.get("gate"),"candidate_score":c.get("score")},pos); return
        if pos is None:return
        # Settle stale positions from the completed 60-second BRTI accumulator when
        # all 60 source seconds are present. Never award an expiry win from the
        # last observed BRTI when a complete settlement reconstruction exists.
        if ticker!=pos.get("ticker") or float(m.get("seconds_left") or 0)<=0:
            target=m.get("target") if ticker==pos.get("ticker") else pos.get("target")
            old_ticker=pos.get("ticker"); bucket=dict(FINAL_TARGET_SECONDS.get(old_ticker,{}) or {})
            vals=[float(v) for _,v in sorted(bucket.items()) if v is not None]
            if target is not None and len(vals)>=60:
                settle_brti=float(sum(vals[:60])/60.0); above=settle_brti>=float(target)
                wins=above if pos["side"]=="ABOVE" else not above; xp=1.0 if wins else 0.0; pnl=pos["quantity"]*(xp-pos["entry"])
                _auto_event("EXIT",d,{"exit":xp,"pnl":pnl,"reason":"EXPIRY / ROLLOVER","result_type":"RECONSTRUCTED_60S_BRTI_NOT_OFFICIAL","settlement_brti_60s":settle_brti,"settlement_sample_count":len(vals),"peak_bid":pos["peak_bid"],"trough_bid":pos["trough_bid"]},pos); AUTO_PAPER["last_exit"]={"trade_id":pos["trade_id"],"pnl":pnl,"reason":"EXPIRY / ROLLOVER","at":now}; AUTO_PAPER["position"]=None; _save_auto_state()
            else:
                brti=m.get("brti") if ticker==pos.get("ticker") else pos.get("last_brti")
                if brti is not None and target is not None:
                    above=float(brti)>=float(target); wins=above if pos["side"]=="ABOVE" else not above; xp=1.0 if wins else 0.0; pnl=pos["quantity"]*(xp-pos["entry"])
                    _auto_event("EXIT",d,{"exit":xp,"pnl":pnl,"reason":"EXPIRY / ROLLOVER","result_type":"PROXY_LAST_BRTI_INCOMPLETE_SETTLEMENT","settlement_sample_count":len(vals),"peak_bid":pos["peak_bid"],"trough_bid":pos["trough_bid"]},pos); AUTO_PAPER["last_exit"]={"trade_id":pos["trade_id"],"pnl":pnl,"reason":"EXPIRY / ROLLOVER","at":now}; AUTO_PAPER["position"]=None; _save_auto_state()
            return
        pos["last_brti"]=m.get("brti"); pos["target"]=m.get("target")
        b=_side_book(pos["side"],d.get("execution_market") or {}); bid=b.get("bid")
        try: bid=float(bid)
        except Exception:return
        pos["peak_bid"]=max(float(pos.get("peak_bid",bid)),bid); pos["trough_bid"]=min(float(pos.get("trough_bid",bid)),bid)
        opp=(d.get("decision") or {}).get("decision") not in (None,pos["side"])
        if opp:
            if not pos.get("opp_since"):pos["opp_since"]=now
        else: pos["opp_since"]=0.0
        confirmed=bool(pos.get("opp_since") and now-pos["opp_since"]>=5.0); cur=bid-pos["entry"]; give=pos["peak_bid"]-bid; reason=None
        if confirmed:reason="AUTO - DECISION OPPOSITION 5S"
        elif cur>=.08 and give>=.05:reason="AUTO - PROFIT GIVEBACK"
        elif float(m.get("seconds_left") or 999)<=45 and cur>=.08:reason="AUTO - LATE PROFIT CAPTURE"
        elif (pos["peak_bid"]-pos["entry"])>=.08 and 0<cur<=.01:reason="AUTO - PROFIT RISK"
        if now-float(pos.get("last_update_event_at") or 0)>=0.9:
            _auto_event("UPDATE",d,{"current_bid":bid,"peak_bid":pos["peak_bid"],"trough_bid":pos["trough_bid"],"mfe":pos["peak_bid"]-pos["entry"],"mae":pos["entry"]-pos["trough_bid"]},pos)
            pos["last_update_event_at"]=now
        if reason:
            pnl=pos["quantity"]*(bid-pos["entry"]); _auto_event("EXIT",d,{"exit":bid,"pnl":pnl,"reason":reason,"peak_bid":pos["peak_bid"],"trough_bid":pos["trough_bid"],"mfe":pos["peak_bid"]-pos["entry"],"mae":pos["entry"]-pos["trough_bid"]},pos); AUTO_PAPER["last_exit"]={"trade_id":pos["trade_id"],"pnl":pnl,"reason":reason,"at":now}; AUTO_PAPER["position"]=None
        _save_auto_state()

def auto_paper_status(d=None):
    with AUTO_PAPER_LOCK:
        g=_auto_gate(d,time.time()) if isinstance(d,dict) and d.get("status")=="ok" else None
        return {"enabled":bool(AUTO_PAPER["enabled"]),"policy":AUTO_PAPER_POLICY,"position":AUTO_PAPER["position"],"last_exit":AUTO_PAPER["last_exit"],"gate":g,"owner":"SERVER","manual_isolated":True}

def _engine_history_rows():
    """Return history length without evaluating a pandas DataFrame as boolean."""
    try:
        ticks = getattr(engine, "ticks", None) if engine is not None else None
        return int(len(ticks)) if ticks is not None else 0
    except Exception:
        return 0

def _append_trade_event(payload: dict):
    if not isinstance(payload, dict):
        raise ValueError("trade event must be a JSON object")
    rec = dict(payload)
    rec.setdefault("server_received_utc", datetime.now(timezone.utc).isoformat())
    raw = json.dumps(rec, separators=(",", ":"), ensure_ascii=False)
    if len(raw.encode("utf-8")) > 131072:
        raise ValueError("trade event too large")
    TRADE_EVENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TRADE_EVENT_LOCK:
        with TRADE_EVENT_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(raw + "\n")
    return rec

@app.get("/", response_class=HTMLResponse)
def home():
    html=Path(__file__).with_name("static").joinpath("index.html").read_text(encoding="utf-8")
    return HTMLResponse(html, headers={"Cache-Control":"no-store, no-cache, must-revalidate, max-age=0","Pragma":"no-cache"})


@app.head("/")
def home_head():
    return HTMLResponse("", status_code=200, headers={"Cache-Control":"no-store"})

@app.get("/api/ping")
def api_ping():
    """Never waits on engine/cache/feed locks; browser startup liveness probe."""
    return JSONResponse({
        "ok": True,
        "status": "web_alive",
        "version": "V2.28.43",
        "cache_ready": STATE_CACHE is not None,
        "cache_age_s": (time.time()-STATE_CACHE_AT) if STATE_CACHE_AT else None,
        "cache_error": STATE_CACHE_ERROR,
        "engine_created": engine is not None,
        "history_rows": _engine_history_rows(),
        "engine_error": (engine.snapshot()[1] if engine is not None else None),
    }, headers={"Cache-Control":"no-store"})

@app.get("/api/runtime/health")
def runtime_health():
    """Cheap, lock-light self diagnostics for Render instances without shell access."""
    import resource
    rss_kb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    try: disk=shutil.disk_usage(RDFZ_DIR)
    except Exception: disk=None
    ws=KALSHI_MARKET_STREAM.health() if KALSHI_MARKET_STREAM is not None else {}
    return JSONResponse({"ok":True,"version":"V2.28.43","uptime_cache_age_s":(time.time()-STATE_CACHE_AT) if STATE_CACHE_AT else None,
        "state_build_last_s":max(0.0,STATE_CACHE_WORKER_LAST_END-STATE_CACHE_WORKER_LAST_BEGIN) if STATE_CACHE_WORKER_LAST_END else None,
        "rss_peak_bytes":int(rss_kb*1024),"brti":engine.feed_status() if engine is not None and hasattr(engine,"feed_status") else {},
        "kalshi_ws":ws,"disk":({"total":disk.total,"used":disk.used,"free":disk.free} if disk else None)},headers={"Cache-Control":"no-store"})

@app.get("/api/brti/stream")
def brti_stream():
    """Push each newly observed BRTI quote to the browser without waiting for /api/state.

    This is display/instrumentation only. Architect authority remains in the engine.
    """
    def events():
        last_key=None
        while STATE_CACHE_RUNNING:
            try:
                r,err = engine.snapshot() if engine is not None else (None,"engine_unavailable")
                if r and r.get("btc") is not None:
                    key=(str(r.get("quote_time")), float(r.get("btc")))
                    if key != last_key:
                        now_utc=datetime.now(timezone.utc)
                        qt=pd.to_datetime(r.get("quote_time"),utc=True,errors="coerce")
                        age_ms=None if pd.isna(qt) else max(0.0,(pd.Timestamp(now_utc)-qt).total_seconds()*1000.0)
                        payload={"brti":float(r.get("btc")),"source_timestamp_utc":str(r.get("quote_time") or ""),
                                 "server_emit_utc":now_utc.isoformat(),"source_age_ms_at_emit":age_ms,
                                 "feed":r.get("brti_feed")}
                        yield "data: "+json.dumps(payload,separators=(",",":"))+"\n\n"
                        last_key=key
                time.sleep(0.04)
            except GeneratorExit:
                break
            except Exception as e:
                yield "event: error\ndata: "+json.dumps({"error":str(e)})+"\n\n"
                time.sleep(0.25)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control":"no-cache, no-transform","X-Accel-Buffering":"no"})

@app.post("/api/client-telemetry")
async def client_telemetry(request: Request):
    """Record browser receipt/render timing for prospective latency validation."""
    try:
        payload=await request.json()
        if not isinstance(payload,dict): raise ValueError("object required")
        rec=dict(payload); rec["server_received_utc"]=datetime.now(timezone.utc).isoformat()
        raw=json.dumps(rec,separators=(",",":"),ensure_ascii=False)
        if len(raw.encode("utf-8"))>32768: raise ValueError("telemetry too large")
        CLIENT_TELEMETRY_LOG_PATH.parent.mkdir(parents=True,exist_ok=True)
        with CLIENT_TELEMETRY_LOCK:
            with CLIENT_TELEMETRY_LOG_PATH.open("a",encoding="utf-8") as f: f.write(raw+"\n")
        return JSONResponse({"ok":True})
    except Exception as e:
        return JSONResponse({"ok":False,"error":str(e)},status_code=400)

@app.get("/api/state/stream")
def state_stream():
    """Push completed state snapshots; browser polling remains watchdog fallback only."""
    def events():
        last_at=0.0
        while STATE_CACHE_RUNNING:
            try:
                if STATE_CACHE is not None and STATE_CACHE_AT!=last_at:
                    payload=dict(STATE_CACHE); payload["api_cache_age_s"]=max(0.0,time.time()-STATE_CACHE_AT); payload["api_cache_status"]="LIVE"
                    payload["server_emit_utc"]=datetime.now(timezone.utc).isoformat()
                    yield "data: "+json.dumps(clean(payload),separators=(",",":"))+"\n\n"
                    last_at=STATE_CACHE_AT
                time.sleep(0.04)
            except GeneratorExit: break
            except Exception as e:
                yield "event: error\ndata: "+json.dumps({"error":str(e)})+"\n\n"; time.sleep(.25)
    return StreamingResponse(events(),media_type="text/event-stream",headers={"Cache-Control":"no-cache, no-transform","X-Accel-Buffering":"no"})

@app.get("/api/state")
def state():
    # Serve the latest completed snapshot. Heavy state construction happens in a
    # background worker so a slow venue/model cycle cannot block the HTTP request
    # and trigger an intermittent Render proxy 502.
    cached=STATE_CACHE
    cache_at=STATE_CACHE_AT
    cache_error=STATE_CACHE_ERROR
    age=(time.time()-cache_at) if cache_at else None
    if cached is not None:
        payload=dict(cached)
        payload["api_cache_age_s"]=age
        if age is not None and age>5:
            payload["api_cache_status"]="STALE"
        else:
            payload["api_cache_status"]="LIVE"
        return JSONResponse(payload, headers={"Cache-Control":"no-store"})
    
    warm={"status":"starting","ok":False,"error":cache_error or "state_cache_warming",
          "cache_worker_started":bool(STATE_CACHE_WORKER_STARTED_AT),
          "cache_worker_cycle_s":(time.time()-STATE_CACHE_WORKER_LAST_BEGIN) if STATE_CACHE_WORKER_LAST_BEGIN and STATE_CACHE_WORKER_LAST_END<STATE_CACHE_WORKER_LAST_BEGIN else 0.0}
    try:
        warm["history_ready"]=bool(getattr(engine,"history_ready",False)) if engine is not None else False
        warm["history_rows"]=_engine_history_rows()
        warm["model_ready"]=bool(warm["history_ready"] and warm["history_rows"]>=45)
    except Exception:
        pass
    return JSONResponse(warm, headers={"Cache-Control":"no-store"})

@app.get("/api/health")
def health():
    # V2.24.2: retain V2.24.1 liveness-only health check. Render should consider the service
    # alive whenever FastAPI can answer, even while market-data state is
    # warming or temporarily stale. Data readiness remains visible in JSON.
    with STATE_LOCK:
        age=(time.time()-STATE_CACHE_AT) if STATE_CACHE_AT else None
        err=STATE_CACHE_ERROR
        has_state=STATE_CACHE is not None
    if not has_state:
        data_status="WARMING"
    elif age is not None and age >= 15.0:
        data_status="STALE"
    else:
        data_status="LIVE"
    return JSONResponse({
        "ok":True,
        "service":"alive",
        "version":"V2.28.35 / V10.39.19",
        "data_status":data_status,
        "cache_age_s":age,
        "cache_error":err,
        "history_ready":bool(getattr(engine,"history_ready",False)) if engine is not None else False,
        "history_rows":_engine_history_rows()
    }, status_code=200, headers={"Cache-Control":"no-store"})

@app.get("/api/auto-paper/status")
def api_auto_paper_status():
    return JSONResponse({"ok":True,**auto_paper_status(STATE_CACHE)},headers={"Cache-Control":"no-store"})

@app.post("/api/auto-paper/mode")
async def api_auto_paper_mode(request: Request):
    body=await request.json(); enabled=bool(body.get("enabled"))
    with AUTO_PAPER_LOCK:
        AUTO_PAPER["enabled"]=enabled; _save_auto_state()
        d=STATE_CACHE if isinstance(STATE_CACHE,dict) else {}
        _auto_event("AUTO_MODE",d,{"enabled":enabled})
    STATE_WAKE.set()
    return JSONResponse({"ok":True,**auto_paper_status(STATE_CACHE)},headers={"Cache-Control":"no-store"})

@app.post("/api/trade-event")
async def trade_event(request: Request):
    try:
        payload = await request.json()
        rec = _append_trade_event(payload)
        return JSONResponse({"ok":True,"status":"recorded","event_type":rec.get("event_type"),"trade_id":rec.get("trade_id")}, headers={"Cache-Control":"no-store"})
    except Exception as exc:
        return JSONResponse({"ok":False,"status":"error","error":"trade_event_write_failed","detail":str(exc)}, status_code=400, headers={"Cache-Control":"no-store"})

@app.get("/api/trade-events/status")
def trade_events_status():
    try:
        exists=TRADE_EVENT_LOG_PATH.exists()
        size=TRADE_EVENT_LOG_PATH.stat().st_size if exists else 0
        lines=0
        if exists and size <= 20_000_000:
            with TRADE_EVENT_LOG_PATH.open("r",encoding="utf-8") as f:
                for _ in f: lines += 1
        return JSONResponse({
            "ok":True,"enabled":True,"exists":exists,"bytes":size,"events":lines if exists and size<=20_000_000 else None,
            "path":str(TRADE_EVENT_LOG_PATH),
            "durability":"runtime filesystem; set TRADE_EVENT_LOG_PATH to a mounted persistent volume for deploy-surviving storage"
        }, headers={"Cache-Control":"no-store"})
    except Exception as exc:
        return JSONResponse({"ok":False,"enabled":True,"error":str(exc)}, status_code=500, headers={"Cache-Control":"no-store"})



def _rdfz_active_files():
    RDFZ_DIR.mkdir(parents=True,exist_ok=True)
    export_root=RDFZ_DIR/"_exports"
    for p in sorted(RDFZ_DIR.rglob("*")):
        if not p.is_file(): continue
        try:
            p.relative_to(export_root)
            continue
        except ValueError: pass
        if p.name in ("RDFZ_MANIFEST.json","RDFZ_EXPORT_TIMING.json","RDFZ_LAST_EXPORT.json"): continue
        yield p

def _rdfz_record_timestamp(obj):
    """Best-effort event timestamp extraction for RDFZ accounting.

    Prefer collector/log timestamps so every current RDFZ stream has a causal,
    comparable export timestamp. Source timestamps remain fallbacks.
    """
    if not isinstance(obj,dict): return None
    keys=(
        "logged_at_utc","server_received_utc","timestamp_utc","timestamp","ts_utc","ts",
        "event_time_utc","event_time","created_utc","received_utc","server_time","server_ts",
        "source_timestamp_utc","source_timestamp","source_ts","time_utc"
    )
    for k in keys:
        v=obj.get(k)
        if v is None: continue
        try:
            if isinstance(v,(int,float)):
                x=float(v)
                if x>1e12: x/=1000.0
                return datetime.fromtimestamp(x,timezone.utc)
            t=str(v).strip().replace("Z","+00:00")
            d=datetime.fromisoformat(t)
            if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
            return d.astimezone(timezone.utc)
        except Exception: pass
    return None

def _rdfz_snapshot_specs(files):
    """Capture immutable byte boundaries for a point-in-time cumulative export."""
    specs=[]
    for p in files:
        try:
            st=p.stat()
            specs.append({"path":p,"size":int(st.st_size),"mtime":float(st.st_mtime)})
        except (FileNotFoundError,OSError):
            continue
    return specs

def _rdfz_iter_snapshot_lines(p, limit, chunk_size=1024*1024):
    """Yield complete NDJSON lines from exactly the first *limit* bytes."""
    remaining=int(limit); buf=b""
    with p.open("rb") as f:
        while remaining>0:
            chunk=f.read(min(chunk_size,remaining))
            if not chunk: break
            remaining-=len(chunk); buf+=chunk
            while True:
                i=buf.find(b"\n")
                if i<0: break
                line=buf[:i]; buf=buf[i+1:]
                if line.strip(): yield line
        # Include a final complete JSON record without newline if it parses.
        if buf.strip():
            try:
                json.loads(buf.decode("utf-8"))
                yield buf
            except Exception:
                pass

def _rdfz_snapshot_file_stats(spec):
    p=spec["path"]; limit=spec["size"]
    row={"name":p.relative_to(RDFZ_DIR).as_posix(),"bytes":limit,
         "modified_utc":datetime.fromtimestamp(spec["mtime"],timezone.utc).isoformat(),
         "rows":None,"first_record_utc":None,"last_record_utc":None}
    if p.suffix.lower() not in (".ndjson",".jsonl"):
        return row
    n=0; first=None; last=None
    try:
        for raw in _rdfz_iter_snapshot_lines(p,limit):
            n+=1
            try: d=_rdfz_record_timestamp(json.loads(raw.decode("utf-8")))
            except Exception: d=None
            if d is not None:
                if first is None or d<first: first=d
                if last is None or d>last: last=d
    except Exception as exc:
        row["scan_error"]=str(exc)
    row["rows"]=n
    row["first_record_utc"]=first.isoformat() if first else None
    row["last_record_utc"]=last.isoformat() if last else None
    return row

def _rdfz_file_stats(p):
    try:
        st=p.stat(); spec={"path":p,"size":int(st.st_size),"mtime":float(st.st_mtime)}
        return _rdfz_snapshot_file_stats(spec)
    except Exception as exc:
        return {"name":p.relative_to(RDFZ_DIR).as_posix(),"bytes":0,"modified_utc":None,
                "rows":None,"first_record_utc":None,"last_record_utc":None,"scan_error":str(exc)}

def _rdfz_stats(files=None, specs=None):
    if specs is None:
        specs=_rdfz_snapshot_specs(list(files or []))
    rows=[]; times=[]
    for spec in specs:
        try:
            r=_rdfz_snapshot_file_stats(spec); rows.append(r)
            for k in ("first_record_utc","last_record_utc"):
                if r.get(k): times.append(datetime.fromisoformat(r[k]))
        except Exception: pass
    return rows,(min(times) if times else None),(max(times) if times else None)

def _rdfz_range(files):
    _,first,last=_rdfz_stats(files=files)
    if first or last: return first,last
    mts=[]
    for p in files:
        try: mts.append(p.stat().st_mtime)
        except Exception: pass
    if not mts: return None,None
    return datetime.fromtimestamp(min(mts),timezone.utc),datetime.fromtimestamp(max(mts),timezone.utc)

def _rdfz_manifest(files=None):
    files=list(_rdfz_active_files()) if files is None else list(files)
    specs=_rdfz_snapshot_specs(files)
    rows,first,last=_rdfz_stats(specs=specs)
    return {"schema":"RDFZ_V2","app_version":"V2.28.43","research_version":"V10.39.25",
            "folder":str(RDFZ_DIR),"generated_at_utc":datetime.now(timezone.utc).isoformat(),
            "data_start_utc":first.isoformat() if first else None,"data_end_utc":last.isoformat() if last else None,
            "file_count":len(rows),"total_rows":sum((r.get("rows") or 0) for r in rows),"files":rows}

def _rdfz_existing_exports():
    root=RDFZ_DIR/"_exports"; out=[]
    if not root.exists(): return out
    for z in root.rglob("*.zip"):
        try:
            rel=z.relative_to(root).as_posix(); st=z.stat(); batch=z.parent.name
            out.append({"id":rel,"batch_id":batch,"filename":z.name,"bytes":st.st_size,
                        "modified_utc":datetime.fromtimestamp(st.st_mtime,timezone.utc).isoformat()})
        except Exception: pass
    out.sort(key=lambda x:x["modified_utc"],reverse=True)
    return out

def _storage_status():
    u=shutil.disk_usage(RDFZ_DIR)
    pct=(100.0*u.used/u.total) if u.total else 0.0
    active=sum((p.stat().st_size for p in _rdfz_active_files()),0)
    pending=0
    er=RDFZ_DIR/"_exports"
    if er.exists():
        for p in er.rglob("*"):
            if p.is_file():
                try: pending+=p.stat().st_size
                except Exception: pass
    level="OK" if pct<70 else ("NOTICE" if pct<85 else ("WARNING" if pct<95 else "CRITICAL"))
    return {"disk_total_bytes":u.total,"disk_used_bytes":u.used,"disk_free_bytes":u.free,"disk_used_pct":round(pct,2),
            "rdfz_active_bytes":active,"rdfz_exported_pending_clear_bytes":pending,"warning_level":level,
            "warning_thresholds_pct":[70,85,95]}

def _safe_tree_size(root: Path):
    total=0; files=0; dirs=0; errors=[]; largest=[]
    try:
        for base, dirnames, filenames in os.walk(root, followlinks=False):
            dirs += len(dirnames)
            bp=Path(base)
            for name in filenames:
                fp=bp/name
                try:
                    if fp.is_symlink():
                        continue
                    sz=fp.stat().st_size
                    total += sz; files += 1
                    largest.append((sz,str(fp)))
                    if len(largest)>250:
                        largest=sorted(largest,reverse=True)[:100]
                except Exception as exc:
                    if len(errors)<20: errors.append(f"{fp}: {exc}")
    except Exception as exc:
        errors.append(f"{root}: {exc}")
    largest=sorted(largest,reverse=True)[:30]
    return total,files,dirs,largest,errors

def _storage_inspector():
    # Read-only metadata scan. It never opens file contents and never deletes/moves data.
    data_root=RDFZ_DIR.parent if RDFZ_DIR.parent.exists() else RDFZ_DIR
    top=[]; largest=[]; errors=[]; accounted=0
    try:
        entries=sorted(list(data_root.iterdir()), key=lambda p:p.name.lower())
    except Exception as exc:
        entries=[]; errors.append(str(exc))
    for entry in entries:
        try:
            if entry.is_symlink():
                top.append({"name":entry.name,"path":str(entry),"type":"symlink","bytes":0,"files":0,"dirs":0})
                continue
            if entry.is_file():
                sz=entry.stat().st_size; accounted+=sz
                top.append({"name":entry.name,"path":str(entry),"type":"file","bytes":sz,"files":1,"dirs":0})
                largest.append((sz,str(entry)))
            elif entry.is_dir():
                sz,nf,nd,lg,er=_safe_tree_size(entry); accounted+=sz
                top.append({"name":entry.name,"path":str(entry),"type":"directory","bytes":sz,"files":nf,"dirs":nd})
                largest.extend(lg); errors.extend(er[:5])
        except Exception as exc:
            if len(errors)<20: errors.append(f"{entry}: {exc}")
    top.sort(key=lambda x:x.get("bytes",0),reverse=True)
    largest=sorted(largest,reverse=True)[:30]
    u=shutil.disk_usage(data_root)
    return {"root":str(data_root),"scanned_bytes":accounted,"disk_used_bytes":u.used,"disk_total_bytes":u.total,
            "disk_free_bytes":u.free,"unaccounted_used_bytes":max(0,u.used-accounted),
            "top_level":top[:50],"largest_files":[{"bytes":sz,"path":path} for sz,path in largest],
            "errors":errors[:20],"read_only":True,"generated_at_utc":datetime.now(timezone.utc).isoformat()}


def _deleted_open_file_inspector():
    # Linux /proc read-only scan for deleted files that are still held open.
    rows=[]; errors=[]; seen=set(); total=0
    proc=Path('/proc')
    if not proc.exists():
        return {"supported":False,"total_bytes":0,"count":0,"files":[],"errors":["/proc is unavailable"]}
    for pd in proc.iterdir():
        if not pd.name.isdigit():
            continue
        pid=pd.name
        comm='?'
        try:
            comm=(pd/'comm').read_text(errors='replace').strip()[:120]
        except Exception:
            pass
        fdroot=pd/'fd'
        try:
            fds=list(fdroot.iterdir())
        except Exception:
            continue
        for fd in fds:
            try:
                target=os.readlink(fd)
                if ' (deleted)' not in target:
                    continue
                st=os.stat(fd)
                key=(st.st_dev,st.st_ino)
                if key in seen:
                    continue
                seen.add(key)
                size=max(0,int(st.st_size)); total+=size
                rows.append({"pid":int(pid),"process":comm,"fd":fd.name,"bytes":size,"target":target,"device":int(st.st_dev),"inode":int(st.st_ino)})
            except (FileNotFoundError,PermissionError,ProcessLookupError):
                continue
            except Exception as exc:
                if len(errors)<20: errors.append(f"pid {pid} fd {fd.name}: {exc}")
    rows.sort(key=lambda x:x['bytes'],reverse=True)
    return {"supported":True,"total_bytes":total,"count":len(rows),"files":rows[:50],"errors":errors}

@app.get("/api/storage/deleted-open")
def storage_deleted_open():
    return JSONResponse({"ok":True,"read_only":True,**_deleted_open_file_inspector()},headers={"Cache-Control":"no-store"})

@app.get("/api/storage/inspect")
def storage_inspect():
    return JSONResponse({"ok":True,**_storage_inspector()},headers={"Cache-Control":"no-store"})

@app.get("/api/rdfz/status")
def rdfz_status():
    manifest=_rdfz_manifest()
    last={}
    lp=RDFZ_DIR/"RDFZ_LAST_EXPORT.json"
    if lp.exists():
        try:last=json.loads(lp.read_text(encoding="utf-8"))
        except Exception:pass
    return JSONResponse({"ok":True,**manifest,"storage":_storage_status(),"last_export":last},headers={"Cache-Control":"no-store"})

_RDFZ_DOWNLOAD_LOCK = threading.Lock()


def _rdfz_downloadable_files():
    """Active RDFZ files available for direct, uncompressed download."""
    return sorted([p for p in _rdfz_active_files() if p.is_file()], key=lambda p:p.name)


def _safe_rdfz_name(name: str):
    name=Path(str(name or "")).name
    if not name or name in {".",".."}:
        return None
    p=(RDFZ_DIR/name).resolve()
    try:p.relative_to(RDFZ_DIR.resolve())
    except ValueError:return None
    return p

@app.get("/api/rdfz/download-plan")
def rdfz_download_plan():
    """Freeze byte boundaries only; performs no copy, compression, checksum or ZIP build."""
    files=[]
    for p in _rdfz_downloadable_files():
        try:
            st=p.stat()
            files.append({"name":p.name,"bytes":int(st.st_size),"mtime":float(st.st_mtime),
                          "url":f"/api/rdfz/raw-file?name={p.name}&bytes={int(st.st_size)}"})
        except (FileNotFoundError,OSError):
            continue
    return JSONResponse({"ok":True,"mode":"direct_raw_stream","app_version":"V2.28.43",
                         "frozen_at_utc":datetime.now(timezone.utc).isoformat(),
                         "file_count":len(files),"total_bytes":sum(x["bytes"] for x in files),"files":files,
                         "note":"Each file is streamed directly from disk only to its frozen byte boundary. No server ZIP is created."},
                        headers={"Cache-Control":"no-store"})

@app.get("/api/rdfz/raw-file")
def rdfz_raw_file(name: str, bytes: int = -1):
    """Low-overhead direct file stream. Never compresses or creates a temporary archive."""
    p=_safe_rdfz_name(name)
    if p is None or not p.exists() or not p.is_file() or p.parent.resolve()!=RDFZ_DIR.resolve():
        return JSONResponse({"ok":False,"error":"rdfz_file_not_found"},status_code=404,headers={"Cache-Control":"no-store"})
    try: current=int(p.stat().st_size)
    except OSError:
        return JSONResponse({"ok":False,"error":"rdfz_file_unavailable"},status_code=409,headers={"Cache-Control":"no-store"})
    limit=current if bytes < 0 else max(0,min(int(bytes),current))
    def stream():
        remaining=limit
        with p.open("rb") as src:
            while remaining>0:
                chunk=src.read(min(256*1024,remaining))
                if not chunk: break
                remaining-=len(chunk)
                yield chunk
                # Cooperative yield so live market/WS/API work stays responsive.
                time.sleep(0)
    headers={"Cache-Control":"no-store","Content-Disposition":f'attachment; filename="{p.name}"',
             "Content-Length":str(limit),"X-RDFZ-Mode":"direct-raw-frozen-boundary"}
    return StreamingResponse(stream(),media_type="application/octet-stream",headers=headers)

# Compatibility endpoint: no ZIP is built. It returns the direct-download plan as JSON.
@app.get("/api/rdfz/download")
def rdfz_download_compat():
    return rdfz_download_plan()

@app.get("/api/rdfz/download-full")
def rdfz_download_full_compat():
    return rdfz_download_plan()

@app.get("/api/rdfz/exports")
def rdfz_exports():
    root=RDFZ_DIR/"_exports"
    xs=[]
    if root.exists():
        for p in root.rglob("*"):
            if p.is_file():
                try: xs.append({"id":str(p.relative_to(root)),"filename":p.name,"bytes":p.stat().st_size})
                except OSError: pass
    return JSONResponse({"ok":True,"exports":xs,"mode":"direct_raw_stream",
                         "note":"V2.28.42 creates no server-side ZIP exports. Listed items are legacy export artifacts only."},
                        headers={"Cache-Control":"no-store"})

@app.get("/api/rdfz/export-file")
def rdfz_export_file(id: str):
    root=(RDFZ_DIR/"_exports").resolve(); target=(root/id).resolve()
    try: target.relative_to(root)
    except ValueError: return JSONResponse({"ok":False,"error":"invalid_export_path"},status_code=400)
    if not target.exists() or not target.is_file():
        return JSONResponse({"ok":False,"error":"export_not_found"},status_code=404)
    return FileResponse(str(target),filename=target.name,headers={"Cache-Control":"no-store"})

@app.post("/api/rdfz/delete-export")
async def rdfz_delete_export(request: Request):
    try: body=await request.json()
    except Exception: body={}
    id=str(body.get("id") or "")
    if body.get("confirm") != "DELETE_EXISTING_EXPORT":
        return JSONResponse({"ok":False,"error":"confirmation_required"},status_code=400)
    root=(RDFZ_DIR/"_exports").resolve(); target=(root/id).resolve()
    try: target.relative_to(root)
    except ValueError: return JSONResponse({"ok":False,"error":"invalid_export_path"},status_code=400)
    if not target.exists() or not target.is_file():
        return JSONResponse({"ok":False,"error":"export_not_found"},status_code=404)
    size=target.stat().st_size; target.unlink()
    return JSONResponse({"ok":True,"deleted_bytes":size,"id":id,"storage":_storage_status()},headers={"Cache-Control":"no-store"})

@app.get("/api/rdfz/download-last")
def rdfz_download_last():
    return JSONResponse({"ok":False,"error":"zip_exports_removed","use":"/api/rdfz/download-plan","mode":"direct_raw_stream"},status_code=410,headers={"Cache-Control":"no-store"})

@app.post("/api/rdfz/clear-exported")
def rdfz_clear_exported():
    """Remove legacy server-created export artifacts only. Active RDFZ is untouched."""
    root=RDFZ_DIR/"_exports"; cleared=0; count=0; errors=[]
    if root.exists():
        for p in sorted(root.rglob("*"),reverse=True):
            try:
                if p.is_file(): cleared+=p.stat().st_size; p.unlink(); count+=1
                elif p.is_dir(): p.rmdir()
            except Exception as exc: errors.append({"path":str(p),"error":str(exc)})
    return JSONResponse({"ok":not errors,"cleared_bytes":cleared,"cleared_files":count,"errors":errors,
                         "active_preserved":True,"mode":"direct_raw_stream","storage":_storage_status()},
                        status_code=200 if not errors else 207,headers={"Cache-Control":"no-store"})

@app.post("/api/rdfz/delete-active")
async def rdfz_delete_active(request: Request):
    # Explicit destructive action. No download/export prerequisite. Exported batches,
    # export metadata, and Auto Paper persistent state are intentionally preserved.
    try: body=await request.json()
    except Exception: body={}
    if body.get("confirm") != "DELETE_ACTIVE_RDFZ":
        return JSONResponse({"ok":False,"error":"confirmation_required"},status_code=400)
    protected={
        Path(AUTO_PAPER_STATE_PATH).resolve(),
        (RDFZ_DIR/"RDFZ_LAST_EXPORT.json").resolve(),
        (RDFZ_DIR/"RDFZ_MANIFEST.json").resolve(),
        (RDFZ_DIR/"RDFZ_EXPORT_TIMING.json").resolve(),
    }
    deleted=[]; errors=[]; freed=0
    for fp in list(_rdfz_active_files()):
        try:
            if fp.resolve() in protected: continue
            sz=fp.stat().st_size
            fp.unlink()
            freed+=sz; deleted.append({"path":str(fp),"bytes":sz})
        except FileNotFoundError: pass
        except Exception as exc: errors.append({"path":str(fp),"error":str(exc)})
    return JSONResponse({"ok":not errors,"deleted_files":len(deleted),"deleted_bytes":freed,
                         "deleted":deleted,"errors":errors,"preserved_auto_paper_state":True,
                         "preserved_exported_batches":True,"storage":_storage_status()},
                        status_code=200 if not errors else 207,headers={"Cache-Control":"no-store"})

@app.get("/api/instrumentation/status")
def instrumentation_status():
    def stat(p):
        try:
            return {"path":str(p),"exists":p.exists(),"bytes":p.stat().st_size if p.exists() else 0}
        except Exception as e:return {"path":str(p),"error":str(e)}
    return JSONResponse({"ok":True,"version":"V2.28.35 / V10.39.19","rdfz_dir":str(RDFZ_DIR),
        "prospective":stat(PROSPECTIVE_LOG_PATH),"auto_events":stat(TRADE_EVENT_LOG_PATH),
        "auto_state":stat(AUTO_PAPER_STATE_PATH),"ws_health":stat(WS_HEALTH_LOG_PATH),
        "prospective_interval_s":PROSPECTIVE_MIN_INTERVAL_S,"ws_health_interval_s":WS_HEALTH_INTERVAL_S,
        "state_sequence":_STATE_SEQUENCE},headers={"Cache-Control":"no-store"})

@app.exception_handler(Exception)
async def api_json_exception_handler(request: Request, exc: Exception):
    # Never let an /api/* request fall through to an HTML error document.
    # The frontend validates content-type too, so intermittent proxy/server
    # failures cannot surface as "<!doctype ... is not valid JSON".
    if request.url.path.startswith("/api/"):
        return JSONResponse({"status":"error","ok":False,"error":"api_exception","detail":str(exc)}, status_code=500, headers={"Cache-Control":"no-store"})
    return HTMLResponse("Service temporarily unavailable", status_code=500)
