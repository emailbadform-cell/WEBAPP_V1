import os, math, json, threading, time, tempfile
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

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import numpy as np
import pandas as pd
import requests

import live_btc15m_predictor as core


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
    """Public Kalshi book snapshot for execution display only; never feeds Chart/Decision."""
    global _KALSHI_BOOK_CACHE
    if not ticker: return {}
    now=time.time()
    if _KALSHI_BOOK_CACHE.get('ticker')==ticker and now-_KALSHI_BOOK_CACHE.get('ts',0)<0.8:
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
              'source':'Kalshi orderbook','timestamp_utc':datetime.now(timezone.utc).isoformat()}
        _KALSHI_BOOK_CACHE={'ticker':ticker,'ts':now,'data':data}; return data
    except Exception as e:
        return {'error':str(e)}

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
    ds = core.decision_signal(r, sec)
    candles = engine.candles
    spark = []
    candle_data = []
    chart_gap_fill_count = 0
    if candles is not None and len(candles):
        # V2.12 DISPLAY-ONLY continuity repair.  Historical BRTI retrieval can
        # omit an isolated minute even while the live 5Hz feed is healthy.
        # Reindex only the browser chart to a complete 1-minute timeline and
        # render a missing minute as a flat carry-forward candle.  The engine's
        # original candles remain untouched, so model/Chart/MP features are not
        # fabricated or changed by this visual repair.
        c = candles.copy()
        required = {"time", "open", "high", "low", "close"}
        if required.issubset(c.columns):
            c["time"] = pd.to_datetime(c["time"], utc=True, errors="coerce")
            c = c.dropna(subset=["time"]).sort_values("time").drop_duplicates("time", keep="last")
            if len(c):
                end = c["time"].max().floor("min")
                start = end - pd.Timedelta(minutes=89)
                c = c[c["time"] >= start].set_index("time")
                full_index = pd.date_range(start=start, end=end, freq="1min", tz="UTC")
                before = len(c)
                c = c.reindex(full_index)
                chart_gap_fill_count = int(c["close"].isna().sum())
                prev = c["close"].ffill().bfill()
                for col in ["open","high","low","close"]:
                    c[col] = c[col].fillna(prev)
                c = c.reset_index().rename(columns={"index":"time"})
                spark = [{"t":clean(t), "v":clean(v)} for t, v in zip(c["time"], c["close"])]
                candle_data = [{"t":clean(row["time"]),"o":clean(row["open"]),"h":clean(row["high"]),"l":clean(row["low"]),"c":clean(row["close"])} for _,row in c.iterrows()]
        if not candle_data:
            c = candles.tail(90)
            spark = [{"t":clean(t), "v":clean(v)} for t, v in zip(c["time"], c["close"])]
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
    execution_market = kalshi_execution_market(r.get("ticker"))
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
        "status":"ok","version":"V2.15 / V10.31",
        "server_time":now,
        "market":{
            "ticker":r.get("ticker"), "target":r.get("target"), "brti":r.get("btc"),
            "distance":r.get("distance"), "close_time":r.get("close_time"), "seconds_left":sec,
            "source":r.get("source"), "quote_time":r.get("quote_time"),
            "brti_feed":r.get("brti_feed"), "brti_age_s":feed.get("age_s"), "feed_mode":feed.get("mode"),
            "next_ticker":feed.get("next_ticker"), "next_prefetched":feed.get("next_prefetched")
        },
        "chart":{
            "prediction":r.get("prediction"), "p_above":r.get("p_above"), "p_below":r.get("p_below"),
            "raw_p_above":r.get("model_p_above"), "mtf_adjustment":r.get("multitf_adjustment"),
            "checkpoint":r.get("checkpoint_model"), "model_kind":r.get("model_kind"), "model_family":r.get("model_family")
        },
        "decision":ds,
        "reachability":tr,
        "target_of_context":tr_of,
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
        "execution_market":execution_market,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine, threads
    engine = core.LiveEngine(
        allow_coinbase_fallback=os.getenv("ALLOW_COINBASE_FALLBACK","0") == "1",
        brti_interval=float(os.getenv("BRTI_INTERVAL","2")),
        orderflow_interval=float(os.getenv("ORDERFLOW_INTERVAL","2")),
    )
    threads = [
        threading.Thread(target=engine.worker, daemon=True),
        threading.Thread(target=engine.orderflow_worker, daemon=True),
        threading.Thread(target=multi_exchange_worker, daemon=True),
    ]
    for t in threads: t.start()
    yield
    global MX_RUNNING
    MX_RUNNING=False
    engine.stop()

app = FastAPI(title="BTC15M V2.15 / V10.31 Execution + Exhaustion Research", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).with_name("static")), name="static")

@app.get("/", response_class=HTMLResponse)
def home():
    html=Path(__file__).with_name("static").joinpath("index.html").read_text(encoding="utf-8")
    return HTMLResponse(html, headers={"Cache-Control":"no-store, no-cache, must-revalidate, max-age=0","Pragma":"no-cache"})

@app.get("/api/state")
def state():
    return JSONResponse(build_state())

@app.get("/api/health")
def health():
    r = build_state()
    return {"ok": r.get("status") == "ok", "status": r.get("status"), "error": r.get("error") or r.get("errors",{}).get("engine")}
