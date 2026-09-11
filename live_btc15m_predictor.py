#!/usr/bin/env python3
"""
BTC15M AUTO LIVE V10.11 — CHART SIGNAL + TR + MOVE PROJECTION + ORDER FLOW
===========================================

Predicts whether the active Kalshi KXBTC15M contract will settle ABOVE or BELOW
using BRTI chart signals only. Target and distance are DISPLAY ONLY and are never
used as prediction features.

V10.10 upgrades:
- Adds a separate Coinbase BTC-USD Order Flow (OF) module for live depth/pressure diagnostics.
- OF estimates how much displayed liquidity must be consumed to sweep ~1/2/5 bps from the current book.
- Tracks nearby bid/ask depth, imbalance, depletion between snapshots, and 1/5/10/25/50% depth-consumption thresholds.
- OF is display-only in V10.10: it does NOT alter Chart Signal or MP yet.
- Coinbase order book is a venue-specific proxy for BTC microstructure; BRTI remains the settlement/reference feed.

Inherited V10.8/V10.6 upgrades:
- Adds Move Projection (MP), a chart-only heuristic for likely continuation distance, hold/protect/cash-out state, and projected price zones.
- MP NEVER uses the Kalshi target and NEVER changes the Chart Signal probability.
- Adds native Windows console colors without reintroducing CLS flashing or ANSI cursor redraw.
- Replaces ANSI cursor redraw with the native Windows Console API to stop garbled/duplicated frames.
- Writes each dashboard frame at fixed width, truncates safely before the wrap column, and pads old rows cleanly.
- Preserves 1-second countdown, ~2-second BRTI refresh, and automatic contract rollover.

V10.4 upgrades:
- Automatically rolls into the next KXBTC15M contract instead of exiting at expiry.
- Keeps the console open continuously; no "Press any key to continue" pause.
- If the next contract is briefly unavailable, displays WAITING FOR NEXT CONTRACT and retries.

V10.1 upgrades:
- Adds Target Reachability (TR) as a separate DISPLAY-ONLY diagnostic.
- TR uses absolute target distance, 1m ATR, and live time remaining to estimate whether the target can realistically be crossed before expiry.
- TR NEVER changes Chart Signal direction or probability.

V10 upgrades:
- Removes target distance, distance/ATR, distance %, and sqrt(time) from the primary model.
- Distance and target remain visible on screen as DISPLAY ONLY.
- Countdown refresh is decoupled from network calls and updates locally every second.
- BRTI refresh runs in a background worker every ~2 seconds by default.
- Historical BRTI is cached instead of re-downloaded on every screen refresh.

Inherited V9 capabilities:
- BRTI remains the primary live/reference feed.
- Explicit 1m, 5m, and 15m OHLC construction.
- 15m HH/HL/LH/LL context.
- Approximate protected high / protected low from recent confirmed swings.
- BOS / CHOCH-style state features.
- Developing 15m candle path-order features:
    * HH -> LL
    * LL -> HH
- Target location inside developing 15m range.
- 1m/5m/15m alignment and disagreement.
- Feature families are historically retested if historical BRTI-derived feature
  data is available; otherwise deployment falls back to inherited V6/V8 models.

Kalshi YES/NO probability is never used as a prediction input.
"""

from __future__ import annotations
import argparse
import base64, json, math, os, sys, time, threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier, HistGradientBoostingClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score

HERE = Path(__file__).resolve().parent
FEATURES_CSV = HERE / "chart_features.csv"
SELECTORS_CSV = HERE / "checkpoint_selected_models.csv"
MODEL_FILE = HERE / "live_model_bundle.joblib"

KALSHI_BASE = "https://external-api.kalshi.com"
API_ROOT = "/trade-api/v2"
COINBASE_CANDLES = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
COINBASE_BOOK = "https://api.exchange.coinbase.com/products/BTC-USD/book"

BASE_FEATURES = [
    "distance","distance_atr","distance_pct","sqrt_time",
    "ret1","ret3","ret5","ret10","ema_gap","rsi14",
    "rv5","rv15","range5","range15",
    "hh1","ll1","body","wick_up","wick_dn",
    "f5ret","f5gap","f5hh","f5ll"
]

CHART_ONLY_FEATURES = [
    "ret1","ret3","ret5","ret10","ema_gap","rsi14",
    "rv5","rv15","range5","range15",
    "hh1","ll1","body","wick_up","wick_dn",
    "f5ret","f5gap","f5hh","f5ll"
]

CHART_ONLY_FAMILIES = {
    "momentum_chart":["ret1","ret3","ret5","ret10","ema_gap","rsi14","f5ret","f5gap","rv5","rv15","range5","range15"],
    "structure_chart":["hh1","ll1","body","wick_up","wick_dn","f5hh","f5ll","range5","range15","rv5","rv15"],
    "full_chart":CHART_ONLY_FEATURES,
}

V9_FEATURES = BASE_FEATURES + [
    "m1_trend","m5_trend","m15_trend",
    "m1_bos_up","m1_bos_dn","m5_bos_up","m5_bos_dn","m15_bos_up","m15_bos_dn",
    "m1_choch_up","m1_choch_dn","m5_choch_up","m5_choch_dn","m15_choch_up","m15_choch_dn",
    "dist_protected_low_atr","dist_protected_high_atr",
    "target_pos_15m","target_inside_15m",
    "dev15_body","dev15_wick_up","dev15_wick_dn",
    "dev15_hh_then_ll","dev15_ll_then_hh",
    "dev15_break_prev_high","dev15_break_prev_low",
    "dev15_reclaim_prev_high","dev15_reclaim_prev_low",
    "align_1m_5m","align_5m_15m","align_all",
    "m15_ema_gap","m15_rsi14","m15_ret1","m15_ret2"
]

FAMILY_FEATURES = {
    "distance_time":["distance","distance_atr","distance_pct","sqrt_time","rv5","rv15","range5","range15"],
    "momentum":["distance","distance_atr","sqrt_time","ret1","ret3","ret5","ret10","ema_gap","rsi14","f5ret","f5gap","rv5","rv15"],
    "structure":["distance","distance_atr","distance_pct","sqrt_time","hh1","ll1","body","wick_up","wick_dn","f5hh","f5ll","range5","range15","rv5","rv15"],
    "multitf_structure":[
        "distance","distance_atr","distance_pct","sqrt_time","rv5","rv15",
        "m1_trend","m5_trend","m15_trend",
        "m1_bos_up","m1_bos_dn","m5_bos_up","m5_bos_dn","m15_bos_up","m15_bos_dn",
        "m1_choch_up","m1_choch_dn","m5_choch_up","m5_choch_dn","m15_choch_up","m15_choch_dn",
        "dist_protected_low_atr","dist_protected_high_atr",
        "target_pos_15m","target_inside_15m",
        "dev15_hh_then_ll","dev15_ll_then_hh",
        "dev15_break_prev_high","dev15_break_prev_low",
        "dev15_reclaim_prev_high","dev15_reclaim_prev_low",
        "align_1m_5m","align_5m_15m","align_all"
    ],
    "full_v9":V9_FEATURES,
}

def _model(kind):
    if kind in ("extra","extra_trees"):
        return ExtraTreesClassifier(n_estimators=220,min_samples_leaf=3,max_features="sqrt",
                                    class_weight="balanced",random_state=42,n_jobs=-1)
    if kind in ("rf","random_forest"):
        return RandomForestClassifier(n_estimators=220,min_samples_leaf=4,max_features="sqrt",
                                      class_weight="balanced_subsample",random_state=42,n_jobs=-1)
    if kind in ("gb","gradient_boosting"):
        return GradientBoostingClassifier(random_state=42)
    if kind in ("hist","hist_gradient_boosting"):
        return HistGradientBoostingClassifier(max_iter=300, random_state=42)
    return make_pipeline(StandardScaler(),
                         LogisticRegression(C=0.7,max_iter=5000,class_weight="balanced"))

def train_bundle(features_csv=FEATURES_CSV, selectors_csv=SELECTORS_CSV, output=MODEL_FILE):
    """Train V10 models using chart signals only. No target-distance/time features."""
    df=pd.read_csv(features_csv).replace([np.inf,-np.inf],np.nan)
    # Chronological contract split for model/family selection.
    order=(df[["ticker","close_time"]].drop_duplicates("ticker")
           .assign(close_time=lambda x:pd.to_datetime(x.close_time,utc=True,errors="coerce"))
           .sort_values("close_time"))
    tickers=order.ticker.tolist(); n=len(tickers)
    a=max(1,int(n*0.60)); b=max(a+1,int(n*0.80))
    train_set=set(tickers[:a]); val_set=set(tickers[a:b]); test_set=set(tickers[b:])
    kinds=["logistic","extra","rf"]
    bundle={"models":{},"meta":{}}; result_rows=[]; selector_rows=[]
    for cp in sorted(df.checkpoint.dropna().astype(int).unique(), reverse=True):
        d=df[df["checkpoint"]==cp].copy()
        tr=d[d.ticker.isin(train_set)]; va=d[d.ticker.isin(val_set)]; te=d[d.ticker.isin(test_set)]
        best=None
        for fam,cols0 in CHART_ONLY_FAMILIES.items():
            cols=[c for c in cols0 if c in d.columns]
            med=tr[cols].median(numeric_only=True).to_dict()
            def prep(x):
                X=x[cols].copy()
                for c in cols: X[c]=X[c].fillna(med.get(c,0.0))
                return X
            for kind in kinds:
                try:
                    m=_model(kind); m.fit(prep(tr),tr.label.astype(int))
                    pv=m.predict_proba(prep(va))[:,1]
                    acc=accuracy_score(va.label.astype(int),pv>=.5)
                    bri=brier_score_loss(va.label.astype(int),pv)
                    result_rows.append({"checkpoint":cp,"family":fam,"model":kind,"validation_accuracy":acc,"validation_brier":bri})
                    score=(bri,-acc)
                    if best is None or score<best[0]: best=(score,fam,kind,cols)
                except Exception:
                    pass
        if best is None: continue
        _,fam,kind,cols=best
        # Test selected configuration untouched, then refit for deployment on all rows.
        med_tr=tr[cols].median(numeric_only=True).to_dict()
        def fill(x,med):
            X=x[cols].copy()
            for c in cols: X[c]=X[c].fillna(med.get(c,0.0))
            return X
        mt=_model(kind); mt.fit(fill(tr,med_tr),tr.label.astype(int))
        pt=mt.predict_proba(fill(te,med_tr))[:,1] if len(te) else np.array([])
        tacc=accuracy_score(te.label.astype(int),pt>=.5) if len(te) else np.nan
        tbri=brier_score_loss(te.label.astype(int),pt) if len(te) else np.nan
        selector_rows.append({"checkpoint":cp,"family":fam,"selected_model":kind,"test_accuracy":tacc,"test_brier":tbri,"n_test":len(te)})
        med=d[cols].median(numeric_only=True).to_dict(); X=fill(d,med); y=d.label.astype(int)
        m=_model(kind); m.fit(X,y)
        bundle["models"][cp]={"model":m,"features":cols,"median":med,"kind":kind,"family":fam,"n":len(d)}
    bundle["meta"]={
        "trained_utc":datetime.now(timezone.utc).isoformat(),
        "source":"V6 real BRTI historical chart dataset",
        "prediction_inputs":"CHART SIGNALS ONLY — no target distance, target position, distance/ATR, distance %, or sqrt(time)",
        "display_only":"target, distance, time remaining",
    }
    joblib.dump(bundle,output)
    pd.DataFrame(result_rows).to_csv(HERE/"chart_only_no_distance_results.csv",index=False)
    pd.DataFrame(selector_rows).to_csv(HERE/"checkpoint_chart_only_selectors.csv",index=False)
    return bundle

def _public_get(path, params=None, timeout=12):
    r=requests.get(KALSHI_BASE+API_ROOT+path,params=params,
                   headers={"User-Agent":"btc15m-v10.3/1.0"},timeout=timeout)
    r.raise_for_status()
    return r.json()

def _load_private_key():
    path=os.getenv("KALSHI_PRIVATE_KEY_PATH","").strip()
    if not path: raise RuntimeError("KALSHI_PRIVATE_KEY_PATH is not set.")
    return serialization.load_pem_private_key(Path(path).read_bytes(),password=None)

def _auth_headers(method,path_without_query):
    key_id=os.getenv("KALSHI_API_KEY_ID","").strip()
    if not key_id: raise RuntimeError("KALSHI_API_KEY_ID is not set.")
    ts=str(int(time.time()*1000))
    msg=(ts+method.upper()+API_ROOT+path_without_query).encode()
    sig=_load_private_key().sign(
        msg,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()),salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY":key_id,
        "KALSHI-ACCESS-TIMESTAMP":ts,
        "KALSHI-ACCESS-SIGNATURE":base64.b64encode(sig).decode(),
        "User-Agent":"btc15m-v10.3/1.0",
    }

def _auth_get(path,params=None,timeout=20):
    r=requests.get(KALSHI_BASE+API_ROOT+path,params=params,
                   headers=_auth_headers("GET",path),timeout=timeout)
    r.raise_for_status()
    return r.json()

def parse_dt(x):
    if not x: return None
    t=pd.to_datetime(x,utc=True,errors="coerce")
    return None if pd.isna(t) else t.to_pydatetime()

def fetch_active_kalshi_market(now=None):
    now=now or datetime.now(timezone.utc)
    data=_public_get("/markets",{"series_ticker":"KXBTC15M","status":"open","limit":100})
    candidates=[]
    for m in data.get("markets",[]):
        if "KXBTC15M" not in str(m.get("ticker","")): continue
        close=parse_dt(m.get("close_time") or m.get("expiration_time"))
        op=parse_dt(m.get("open_time"))
        target=m.get("floor_strike",m.get("functional_strike"))
        try: target=float(target)
        except Exception: continue
        if close and close>now and (op is None or op<=now):
            candidates.append((close,m,target))
    if not candidates: raise RuntimeError("No currently-open KXBTC15M contract found.")
    close,m,target=sorted(candidates,key=lambda x:x[0])[0]
    return {"ticker":m.get("ticker"),"target":target,"close_time":close,"open_time":parse_dt(m.get("open_time"))}

def _walk(obj):
    if isinstance(obj,dict):
        yield obj
        for v in obj.values(): yield from _walk(v)
    elif isinstance(obj,list):
        for v in obj: yield from _walk(v)
    elif isinstance(obj,str):
        s=obj.strip()
        if s.startswith("{") or s.startswith("["):
            try: yield from _walk(json.loads(s))
            except Exception: pass

def _first_num(d,keys):
    for k in keys:
        if k in d:
            try: return float(d[k])
            except Exception: pass
    return None

def _first_time(d,keys):
    for k in keys:
        if k in d:
            v=d[k]
            try:
                if isinstance(v,(int,float)) or (isinstance(v,str) and v.isdigit()):
                    x=float(v); unit="ms" if x>1e11 else "s"
                    t=pd.to_datetime(x,unit=unit,utc=True,errors="coerce")
                else: t=pd.to_datetime(v,utc=True,errors="coerce")
                if not pd.isna(t): return t
            except Exception: pass
    return None

def parse_brti_points(payload):
    pts=[]
    for d in _walk(payload):
        val=_first_num(d,["value","price","index_value","indexValue"])
        ts=_first_time(d,["time","timestamp","ts","sourceTime","source_time","received_at"])
        if val is not None and ts is not None and 1000<val<1000000: pts.append((ts,val))
    if not pts: return pd.DataFrame(columns=["time","value"])
    return pd.DataFrame(pts,columns=["time","value"]).drop_duplicates("time").sort_values("time")

def fetch_brti_recent_values():
    """
    CF Benchmarks /values returns recent published RTI values.
    For RTIs this can contain roughly the most recent hour and is our first,
    lowest-friction source of recent BRTI ticks.
    """
    j=_auth_get("/cfbenchmarks/values",{"id":"BRTI"},timeout=20)
    p=parse_brti_points(j)
    if not len(p):
        raise RuntimeError("BRTI /values response received but no prices were parsed.")
    return p.reset_index(drop=True), j

def fetch_brti_current():
    p,j=fetch_brti_recent_values()
    return {"value":float(p.iloc[-1].value),"time":p.iloc[-1].time,"raw":j}

def _hour_boundary(dt):
    """CF historical timestamp must be truncated to HOUR granularity."""
    return dt.replace(minute=0, second=0, microsecond=0)

def fetch_brti_history(hours=6):
    """
    Build BRTI tick history robustly.

    Important CF Benchmarks requirement:
    timestamp MUST be truncated to the requested timespan granularity.
    V9.1 sent timestamps such as 17:30:03Z with timespan=HOUR, which caused
    HTTP 400. V9.2 uses exact hour boundaries such as 17:00:00.000Z.

    We also seed history from /values, because RTI /values contains recent
    published values and can keep the model running even when a historical
    hour is temporarily delayed/unavailable.
    """
    now=datetime.now(timezone.utc)
    frames=[]
    errs=[]

    # 1) Recent RTI data first.
    try:
        recent,_=fetch_brti_recent_values()
        if len(recent):
            frames.append(recent)
    except Exception as e:
        errs.append("recent /values: "+str(e))

    # 2) Previous exact hour buckets. Skip the in-progress current hour because
    # historical values may lag recent values and CF notes recent historical
    # data can be delayed.
    base=_hour_boundary(now)
    for h in range(1, hours+1):
        boundary=base-timedelta(hours=h)
        stamp=boundary.isoformat(timespec="milliseconds").replace("+00:00","Z")
        try:
            j=_auth_get(
                "/cfbenchmarks/history/values",
                {"id":"BRTI","timespan":"HOUR","timestamp":stamp},
                timeout=25
            )
            ph=parse_brti_points(j)
            if len(ph):
                frames.append(ph)
        except Exception as e:
            errs.append(f"{stamp}: {e}")

    if not frames:
        raise RuntimeError("Could not retrieve BRTI recent/history data. "+" | ".join(errs[-4:]))

    ticks=(pd.concat(frames,ignore_index=True)
             .drop_duplicates("time")
             .sort_values("time")
             .reset_index(drop=True))

    # Limit to requested lookback plus a small overlap allowance.
    cutoff=pd.Timestamp(now-timedelta(hours=hours+1))
    ticks=ticks[ticks["time"]>=cutoff].reset_index(drop=True)

    # V9 needs >=45 one-minute candles. Fail clearly if entitlement/data stream
    # only returned sparse current values.
    mins=brti_ticks_to_1m(ticks)
    if len(mins)<45:
        detail=("Only %d one-minute BRTI bars were available; V9 requires at least 45. "
                "Historical CF Benchmarks values can lag by up to ~15 minutes. "
                "Retry shortly, or use RUN_LIVE_WITH_FALLBACK.bat.") % len(mins)
        if errs:
            detail += " Last historical error: " + errs[-1]
        raise RuntimeError(detail)

    return ticks

def brti_ticks_to_1m(ticks):
    x=ticks.set_index("time")["value"].sort_index()
    c=x.resample("1min").ohlc().dropna()
    c.columns=["open","high","low","close"]; c["volume"]=0.0
    return c.reset_index()

def fetch_coinbase_order_book(level=2):
    """Fetch Coinbase BTC-USD displayed order book.

    V10.10 uses Coinbase only as a venue-specific microstructure proxy. BRTI
    remains the price/reference feed used by the Kalshi contract model.
    """
    r=requests.get(COINBASE_BOOK,params={"level":int(level)},
                   headers={"User-Agent":"btc15m-v10.9/1.0"},timeout=8)
    r.raise_for_status()
    j=r.json()
    bids=[]; asks=[]
    for row in j.get("bids",[]):
        try:
            bids.append((float(row[0]),float(row[1])))
        except Exception:
            pass
    for row in j.get("asks",[]):
        try:
            asks.append((float(row[0]),float(row[1])))
        except Exception:
            pass
    if not bids or not asks:
        raise RuntimeError("Coinbase order book returned no usable bid/ask levels.")
    bids=sorted(bids,key=lambda x:x[0],reverse=True)
    asks=sorted(asks,key=lambda x:x[0])
    return {"bids":bids,"asks":asks,"time":datetime.now(timezone.utc)}


def _depth_within_bps(levels, mid, bps, side):
    """Displayed BTC depth from best price out to bps away from mid."""
    if mid<=0: return 0.0
    frac=float(bps)/10000.0
    if side=="ask":
        cutoff=mid*(1.0+frac)
        return float(sum(sz for px,sz in levels if px<=cutoff))
    cutoff=mid*(1.0-frac)
    return float(sum(sz for px,sz in levels if px>=cutoff))


def summarize_order_book(book, previous=None):
    """Create a compact order-flow/depth snapshot.

    This does not claim that every reduction in displayed depth was traded;
    cancellations and replenishment can also change the book. Depletion is
    therefore labeled as a liquidity-consumption proxy.
    """
    bids=book["bids"]; asks=book["asks"]
    best_bid=float(bids[0][0]); best_ask=float(asks[0][0]); mid=(best_bid+best_ask)/2.0
    spread=max(0.0,best_ask-best_bid)
    d={}
    for bps in (1,2,5):
        d[f"bid_depth_{bps}bps"]=_depth_within_bps(bids,mid,bps,"bid")
        d[f"ask_depth_{bps}bps"]=_depth_within_bps(asks,mid,bps,"ask")
    total5=d["bid_depth_5bps"]+d["ask_depth_5bps"]
    imbalance=(d["bid_depth_5bps"]-d["ask_depth_5bps"])/(total5+1e-12)

    bid_dep=ask_dep=0.0
    if previous:
        pb=float(previous.get("bid_depth_5bps",0.0)); pa=float(previous.get("ask_depth_5bps",0.0))
        if pb>1e-9: bid_dep=max(0.0,(pb-d["bid_depth_5bps"])/pb)
        if pa>1e-9: ask_dep=max(0.0,(pa-d["ask_depth_5bps"])/pa)

    # Up pressure = ask side depleting and/or bid-heavy book. Down pressure is opposite.
    pressure_score=float(np.clip(0.60*imbalance + 0.40*(ask_dep-bid_dep),-1.0,1.0))
    if pressure_score>=0.20: pressure="BUY"
    elif pressure_score<=-0.20: pressure="SELL"
    else: pressure="NEUTRAL"

    def dep_label(x):
        pct=100.0*float(x)
        if pct>=50: return "50%+"
        if pct>=25: return "25%+"
        if pct>=10: return "10%+"
        if pct>=5: return "5%+"
        if pct>=1: return "1%+"
        return "<1%"

    out={
        "time":book.get("time"),"best_bid":best_bid,"best_ask":best_ask,"mid":mid,"spread":spread,
        **d,"imbalance":float(imbalance),"bid_depletion":float(bid_dep),"ask_depletion":float(ask_dep),
        "bid_depletion_band":dep_label(bid_dep),"ask_depletion_band":dep_label(ask_dep),
        "pressure":pressure,"pressure_score":pressure_score,
    }
    # Practical snapshot answer: displayed BTC required to sweep the nearby band.
    out["buy_to_sweep_1bps"]=d["ask_depth_1bps"]
    out["buy_to_sweep_5bps"]=d["ask_depth_5bps"]
    out["sell_to_sweep_1bps"]=d["bid_depth_1bps"]
    out["sell_to_sweep_5bps"]=d["bid_depth_5bps"]
    return out

def fetch_coinbase_1m(limit_minutes=360):
    r=requests.get(COINBASE_CANDLES,params={"granularity":60},
                   headers={"User-Agent":"btc15m-v10.3/1.0"},timeout=12)
    r.raise_for_status()
    df=pd.DataFrame(r.json(),columns=["time","low","high","open","close","volume"])
    for c in ["low","high","open","close","volume"]: df[c]=pd.to_numeric(df[c],errors="coerce")
    df["time"]=pd.to_datetime(df["time"],unit="s",utc=True)
    return df.sort_values("time").drop_duplicates("time").tail(limit_minutes).reset_index(drop=True)

def ema(s,n): return s.ewm(span=n,adjust=False).mean()
def rsi(series,n=14):
    d=series.diff(); up=d.clip(lower=0).rolling(n).mean(); dn=(-d.clip(upper=0)).rolling(n).mean()
    rs=up/(dn+1e-12); return 100-(100/(1+rs))
def atr(df,n=14):
    prev=df.close.shift(1)
    tr=pd.concat([(df.high-df.low).abs(),(df.high-prev).abs(),(df.low-prev).abs()],axis=1).max(axis=1)
    return tr.rolling(n).mean()
def pctret(s,n): return s.iloc[-1]/s.iloc[-1-n]-1 if len(s)>n and s.iloc[-1-n] else 0.0

def resample_ohlc(df, rule):
    x=df.set_index("time")
    r=x.resample(rule,label="right",closed="right").agg(
        {"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
    return r.reset_index()

def trend_state(df):
    if len(df)<3: return 0
    a,b=df.iloc[-2],df.iloc[-1]
    if b.high>a.high and b.low>a.low: return 1
    if b.high<a.high and b.low<a.low: return -1
    return 0

def swing_levels(df, lookback=12):
    d=df.tail(max(lookback,5)).reset_index(drop=True)
    highs=[]; lows=[]
    for i in range(1,len(d)-1):
        if d.loc[i,"high"]>d.loc[i-1,"high"] and d.loc[i,"high"]>=d.loc[i+1,"high"]:
            highs.append(float(d.loc[i,"high"]))
        if d.loc[i,"low"]<d.loc[i-1,"low"] and d.loc[i,"low"]<=d.loc[i+1,"low"]:
            lows.append(float(d.loc[i,"low"]))
    return (highs[-1] if highs else float(d.high.iloc[-2]),
            lows[-1] if lows else float(d.low.iloc[-2]))

def bos_choch(df):
    if len(df)<5: return (0,0,0,0)
    sh,sl=swing_levels(df.iloc[:-1], lookback=min(20,len(df)-1))
    last=float(df.close.iloc[-1])
    prior_trend=trend_state(df.iloc[:-1])
    bos_up=int(last>sh); bos_dn=int(last<sl)
    choch_up=int(prior_trend<0 and bos_up); choch_dn=int(prior_trend>0 and bos_dn)
    return bos_up,bos_dn,choch_up,choch_dn

def developing_15m_features(df1, target):
    # Use UTC quarter-hour boundaries, consistent with KXBTC15M cadence.
    x=df1.copy().sort_values("time")
    t=x.time.iloc[-1]
    start=t.floor("15min")
    dev=x[x.time>=start].copy()
    prev=x[(x.time<start) & (x.time>=start-pd.Timedelta(minutes=15))]
    if len(dev)==0:
        return {}
    o=float(dev.open.iloc[0]); h=float(dev.high.max()); l=float(dev.low.min()); c=float(dev.close.iloc[-1])
    rng=max(h-l,1e-9)
    hh_then_ll=0; ll_then_hh=0
    if len(prev):
        ph=float(prev.high.max()); pl=float(prev.low.min())
        first_hh=None; first_ll=None
        for i,row in dev.iterrows():
            if first_hh is None and float(row.high)>ph: first_hh=row.time
            if first_ll is None and float(row.low)<pl: first_ll=row.time
        if first_hh is not None and first_ll is not None:
            hh_then_ll=int(first_hh<first_ll); ll_then_hh=int(first_ll<first_hh)
        break_high=int(h>ph); break_low=int(l<pl)
        reclaim_high=int(break_high and c>ph)
        reclaim_low=int(break_low and c<pl)
    else:
        ph=pl=np.nan; break_high=break_low=reclaim_high=reclaim_low=0
    return {
        "target_pos_15m":(target-l)/rng,
        "target_inside_15m":int(l<=target<=h),
        "dev15_body":(c-o)/rng,
        "dev15_wick_up":(h-max(o,c))/rng,
        "dev15_wick_dn":(min(o,c)-l)/rng,
        "dev15_hh_then_ll":hh_then_ll,
        "dev15_ll_then_hh":ll_then_hh,
        "dev15_break_prev_high":break_high,
        "dev15_break_prev_low":break_low,
        "dev15_reclaim_prev_high":reclaim_high,
        "dev15_reclaim_prev_low":reclaim_low,
    }

def compute_features(df,target,minutes_left,current_price=None):
    d=df.copy().dropna(subset=["open","high","low","close"]).sort_values("time").reset_index(drop=True)
    if len(d)<45: raise RuntimeError("Need at least 45 one-minute candles for V9.")
    if current_price is not None:
        d.loc[d.index[-1],"close"]=current_price
        d.loc[d.index[-1],"high"]=max(float(d.iloc[-1].high),current_price)
        d.loc[d.index[-1],"low"]=min(float(d.iloc[-1].low),current_price)

    c=d.close; a=atr(d,14); e9,e21=ema(c,9),ema(c,21); rs=rsi(c,14); ret=c.pct_change()
    last=d.iloc[-1]; prev=d.iloc[-2]; rng=max(float(last.high-last.low),1e-9)
    btc=float(current_price if current_price is not None else last.close)
    at=float(a.iloc[-1]) if np.isfinite(a.iloc[-1]) and a.iloc[-1]>0 else float((d.high-d.low).tail(14).mean())

    f5=resample_ohlc(d,"5min")
    f15=resample_ohlc(d,"15min")
    fc=f5.close; f9,f21=ema(fc,9),ema(fc,21); fl=f5.iloc[-1]; fp=f5.iloc[-2]
    c15=f15.close; e15_9,e15_21=ema(c15,9),ema(c15,21); r15=rsi(c15,14)

    m1=trend_state(d); m5=trend_state(f5); m15=trend_state(f15)
    b1u,b1d,c1u,c1d=bos_choch(d)
    b5u,b5d,c5u,c5d=bos_choch(f5)
    b15u,b15d,c15u,c15d=bos_choch(f15)
    ph15,pl15=swing_levels(f15, lookback=min(12,len(f15)))
    dev=developing_15m_features(d,target)

    f={
      "distance":btc-target,"distance_atr":(btc-target)/(at+1e-9),"distance_pct":(btc-target)/(target+1e-9),
      "sqrt_time":math.sqrt(max(minutes_left,1/60)),
      "ret1":pctret(c,1),"ret3":pctret(c,3),"ret5":pctret(c,5),"ret10":pctret(c,10),
      "ema_gap":float((e9.iloc[-1]-e21.iloc[-1])/(btc+1e-9)),
      "rsi14":float(rs.iloc[-1]) if np.isfinite(rs.iloc[-1]) else 50.0,
      "rv5":float(ret.tail(5).std(ddof=0) or 0),"rv15":float(ret.tail(15).std(ddof=0) or 0),
      "range5":float((d.high.tail(5).max()-d.low.tail(5).min())/(btc+1e-9)),
      "range15":float((d.high.tail(15).max()-d.low.tail(15).min())/(btc+1e-9)),
      "hh1":float(last.high>prev.high),"ll1":float(last.low<prev.low),
      "body":float((last.close-last.open)/rng),
      "wick_up":float((last.high-max(last.open,last.close))/rng),
      "wick_dn":float((min(last.open,last.close)-last.low)/rng),
      "f5ret":pctret(fc,1),"f5gap":float((f9.iloc[-1]-f21.iloc[-1])/(fc.iloc[-1]+1e-9)),
      "f5hh":float(fl.high>fp.high),"f5ll":float(fl.low<fp.low),
      "m1_trend":m1,"m5_trend":m5,"m15_trend":m15,
      "m1_bos_up":b1u,"m1_bos_dn":b1d,"m5_bos_up":b5u,"m5_bos_dn":b5d,"m15_bos_up":b15u,"m15_bos_dn":b15d,
      "m1_choch_up":c1u,"m1_choch_dn":c1d,"m5_choch_up":c5u,"m5_choch_dn":c5d,"m15_choch_up":c15u,"m15_choch_dn":c15d,
      "dist_protected_low_atr":(btc-pl15)/(at+1e-9),
      "dist_protected_high_atr":(ph15-btc)/(at+1e-9),
      "align_1m_5m":int(m1!=0 and m1==m5),
      "align_5m_15m":int(m5!=0 and m5==m15),
      "align_all":int(m1!=0 and m1==m5==m15),
      "m15_ema_gap":float((e15_9.iloc[-1]-e15_21.iloc[-1])/(c15.iloc[-1]+1e-9)),
      "m15_rsi14":float(r15.iloc[-1]) if np.isfinite(r15.iloc[-1]) else 50.0,
      "m15_ret1":pctret(c15,1),"m15_ret2":pctret(c15,2),
    }
    f.update(dev)
    return f,btc,at,{"m1":m1,"m5":m5,"m15":m15,"protected_high":ph15,"protected_low":pl15}

def nearest_checkpoint(minutes_left,checkpoints):
    return min(checkpoints,key=lambda x:abs(float(x)-minutes_left))

def _mtf_bias(f,state):
    # Chart-only MTF adjustment: no target or distance inputs.
    bias=0.0
    bias += 0.035*state["m1"] + 0.045*state["m5"] + 0.055*state["m15"]
    bias += 0.025*(f["m1_bos_up"]-f["m1_bos_dn"])
    bias += 0.035*(f["m5_bos_up"]-f["m5_bos_dn"])
    bias += 0.045*(f["m15_bos_up"]-f["m15_bos_dn"])
    bias += 0.04*(f["m1_choch_up"]-f["m1_choch_dn"])
    bias += 0.05*(f["m5_choch_up"]-f["m5_choch_dn"])
    bias += 0.06*(f["m15_choch_up"]-f["m15_choch_dn"])
    bias += 0.05*(f.get("dev15_ll_then_hh",0)-f.get("dev15_hh_then_ll",0))
    if f.get("align_all",0): bias += 0.04*state["m1"]
    return bias

def predict_from_data(market,candles,current,source="BRTI", quote_time=None):
    now=datetime.now(timezone.utc)
    target=float(market["target"]); close_time=market["close_time"]
    seconds_left=(close_time-now).total_seconds(); minutes_left=max(seconds_left/60,1/60)
    f,btc,at,state=compute_features(candles,target,minutes_left,current)
    if not MODEL_FILE.exists(): train_bundle()
    bundle=joblib.load(MODEL_FILE)
    cp=nearest_checkpoint(minutes_left,sorted(bundle["models"]))
    spec=bundle["models"][cp]
    # V10 invariant: deployment model may only receive chart-only fields.
    forbidden={"distance","distance_atr","distance_pct","sqrt_time","target_pos_15m","target_inside_15m"}
    bad=forbidden.intersection(spec["features"])
    if bad: raise RuntimeError("V10 model contains forbidden target/distance features: "+str(sorted(bad)))
    X=pd.DataFrame([{c:f.get(c,np.nan) for c in spec["features"]}])
    for c in spec["features"]: X[c]=X[c].fillna(spec["median"].get(c,0.0))
    p_model=float(spec["model"].predict_proba(X)[0,1])
    bias=_mtf_bias(f,state)
    p=float(np.clip(p_model+bias,0.01,0.99))
    return {
      "ticker":market["ticker"],"target":target,"btc":btc,"distance":btc-target,
      "close_time":close_time,"seconds_left":seconds_left,"minutes_left":minutes_left,"source":source,
      "quote_time":quote_time,"checkpoint_model":cp,"model_kind":spec["kind"],"model_family":spec["family"],
      "model_p_above":p_model,"multitf_adjustment":bias,
      "p_above":p,"p_below":1-p,"prediction":"ABOVE" if p>=.5 else "BELOW",
      "atr1m_14":at,
      "m1_trend":state["m1"],"m5_trend":state["m5"],"m15_trend":state["m15"],
      "protected_high":state["protected_high"],"protected_low":state["protected_low"],
      "dev15_hh_then_ll":f.get("dev15_hh_then_ll",0),
      "dev15_ll_then_hh":f.get("dev15_ll_then_hh",0),
      "target_inside_15m":f.get("target_inside_15m",0),
      "m15_bos_up":f["m15_bos_up"],"m15_bos_dn":f["m15_bos_dn"],
      "m15_choch_up":f["m15_choch_up"],"m15_choch_dn":f["m15_choch_dn"],
      # Chart-only diagnostics used by Move Projection (MP); no Kalshi target inputs.
      "m1_bos_up":f["m1_bos_up"],"m1_bos_dn":f["m1_bos_dn"],
      "m5_bos_up":f["m5_bos_up"],"m5_bos_dn":f["m5_bos_dn"],
      "m1_choch_up":f["m1_choch_up"],"m1_choch_dn":f["m1_choch_dn"],
      "m5_choch_up":f["m5_choch_up"],"m5_choch_dn":f["m5_choch_dn"],
      "ret1":f["ret1"],"ret3":f["ret3"],"ret5":f["ret5"],"ret10":f["ret10"],
      "ema_gap":f["ema_gap"],"f5ret":f["f5ret"],"f5gap":f["f5gap"],
      "rsi14":f["rsi14"],"body":f["body"],"wick_up":f["wick_up"],"wick_dn":f["wick_dn"],
      "range5_abs":f["range5"]*btc,"range15_abs":f["range15"]*btc,
    }

class LiveEngine:
    """Background BRTI worker so network latency never freezes the countdown."""
    def __init__(self, allow_coinbase_fallback=False, brti_interval=2.0, orderflow_interval=2.0):
        self.allow_coinbase_fallback=allow_coinbase_fallback
        self.brti_interval=max(float(brti_interval),1.0)
        self.orderflow_interval=max(float(orderflow_interval),1.0)
        self.lock=threading.Lock(); self.result=None; self.error=None; self.running=True
        self.market=None; self.ticks=None; self.candles=None
        self.last_ticker=None; self.waiting_for_next=False
        self.orderflow=None; self.orderflow_error=None; self._of_previous=None

    def _set(self, result=None, error=None):
        with self.lock:
            if result is not None: self.result=result
            self.error=error

    def snapshot(self):
        with self.lock:
            return self.result, self.error

    def _ensure_market(self):
        """Keep the engine attached to the active 15m contract and auto-roll at expiry."""
        now=datetime.now(timezone.utc)
        if self.market is None or self.market["close_time"]<=now:
            previous = self.market.get("ticker") if self.market else self.last_ticker
            try:
                nxt=fetch_active_kalshi_market(now)
            except Exception:
                # Kalshi can have a brief handoff gap around the exact boundary.
                # Do not terminate; the worker will retry on the next cycle.
                self.waiting_for_next=True
                raise
            self.market=nxt
            self.waiting_for_next=False
            if previous != nxt.get("ticker"):
                self.last_ticker=nxt.get("ticker")
                # Keep BRTI history/cache; only the contract target/expiry changes.
                # Clear the old prediction so the UI never presents the expired
                # contract as though it were the new one.
                with self.lock:
                    self.result=None

    def _initialize_brti(self):
        self._ensure_market()
        self.ticks=fetch_brti_history(hours=6)
        self.candles=brti_ticks_to_1m(self.ticks)

    def _refresh_brti(self):
        recent,_=fetch_brti_recent_values()
        if self.ticks is None:
            self.ticks=recent
        else:
            self.ticks=(pd.concat([self.ticks,recent],ignore_index=True)
                        .drop_duplicates("time").sort_values("time"))
            cutoff=pd.Timestamp(datetime.now(timezone.utc)-timedelta(hours=7))
            self.ticks=self.ticks[self.ticks.time>=cutoff].reset_index(drop=True)
        self.candles=brti_ticks_to_1m(self.ticks)
        current=float(recent.iloc[-1].value); qt=recent.iloc[-1].time
        return predict_from_data(self.market,self.candles,current,"BRTI",qt)

    def worker(self):
        try:
            self._initialize_brti()
        except Exception as e:
            if not self.allow_coinbase_fallback:
                self._set(error="Initialization failed: "+str(e)); return
        while self.running:
            started=time.monotonic()
            try:
                self._ensure_market()
                if self.ticks is not None:
                    r=self._refresh_brti()
                else:
                    candles=fetch_coinbase_1m(); current=float(candles.iloc[-1].close)
                    r=predict_from_data(self.market,candles,current,"Coinbase fallback",candles.iloc[-1].time)
                self._set(result=r,error=None)
            except Exception as e:
                self._set(error=str(e))
            delay=max(0.05,self.brti_interval-(time.monotonic()-started))
            time.sleep(delay)

    def orderflow_snapshot(self):
        with self.lock:
            return self.orderflow, self.orderflow_error

    def orderflow_worker(self):
        while self.running:
            started=time.monotonic()
            try:
                book=fetch_coinbase_order_book(level=2)
                cur=summarize_order_book(book,self._of_previous)
                self._of_previous=cur
                with self.lock:
                    self.orderflow=cur; self.orderflow_error=None
            except Exception as e:
                with self.lock:
                    self.orderflow_error=str(e)
            delay=max(0.05,self.orderflow_interval-(time.monotonic()-started))
            time.sleep(delay)

    def stop(self): self.running=False

def tname(x): return "bullish" if x>0 else "bearish" if x<0 else "neutral"

def target_reachability(distance, atr1m, seconds_left, prediction=None):
    """
    DISPLAY-ONLY Target Reachability (TR).

    TR is deliberately isolated from the Chart Signal model. It estimates how
    difficult it is for BRTI to touch/cross the target before expiration using
    a volatility-scaled travel budget:

        travel_budget = ATR_1m * sqrt(minutes_remaining)
        tr_score      = abs(distance) / travel_budget

    The crossing estimate uses the zero-drift Brownian first-passage form
    erfc(TR/sqrt(2)), with ATR used as a practical volatility proxy. It is a
    heuristic reachability diagnostic, NOT a calibrated probability and NOT a
    model input.
    """
    mins=max(float(seconds_left)/60.0, 1.0/60.0)
    atr=max(float(atr1m), 1e-9)
    travel=float(atr*math.sqrt(mins))
    score=float(abs(float(distance))/(travel+1e-12))
    cross=float(np.clip(math.erfc(score/math.sqrt(2.0)),0.0,1.0))
    if cross >= 0.50:
        status="LIKELY REACHABLE"
    elif cross >= 0.20:
        status="MARGINAL"
    else:
        status="UNLIKELY"
    current_side="ABOVE" if float(distance)>=0 else "BELOW"
    role=None
    if prediction in ("ABOVE","BELOW"):
        role="REQUIRED FOR PREDICTION" if prediction != current_side else "REVERSAL RISK"
    return {
        "travel_budget":travel,
        "tr_score":score,
        "cross_estimate":cross,
        "status":status,
        "current_side":current_side,
        "role":role,
    }

_MP_TRACKER = {}

def _mp_progress_state(r, mp):
    """Track progress from the start of the current MP direction for this contract."""
    key=str(r.get("ticker","UNKNOWN"))
    direction=mp["direction"]
    px=float(r["btc"])
    st=_MP_TRACKER.get(key)
    if st is None or st.get("direction") != direction:
        st={
            "direction":direction,
            "anchor":px,
            "near":float(mp["near"]),
            "base":float(mp["base"]),
            "extended":float(mp["extended"]),
        }
        _MP_TRACKER.clear()
        _MP_TRACKER[key]=st
    sign=1.0 if direction=="UP" else -1.0
    anchor=float(st["anchor"]); base=float(st["base"]); near=float(st["near"]); ext=float(st["extended"])
    total=max(1e-9, sign*(base-anchor))
    traveled=max(0.0, sign*(px-anchor))
    progress=max(0.0,min(2.0,traveled/total))
    remaining=max(0.0, sign*(base-px))
    return {
        "anchor":anchor,"near":near,"base":base,"extended":ext,
        "progress":progress,"progress_pct":100.0*progress,
        "traveled":traveled,"remaining_to_base":remaining,
    }

def move_projection(r):
    """Chart-only Move Projection (MP).

    MP estimates remaining directional travel from current BRTI using chart
    structure, realized range, ATR, momentum, candle shape, BOS/CHOCH and
    timeframe alignment. It deliberately does NOT read the Kalshi target,
    distance-to-target, or time remaining, and it never changes p_above/p_below.

    The price zones and hold state are heuristics for trade management, not
    calibrated forecasts or guarantees.
    """
    px=float(r["btc"]); atr=max(float(r.get("atr1m_14",0.0)),1e-9)
    trends=[int(r.get("m1_trend",0)),int(r.get("m5_trend",0)),int(r.get("m15_trend",0))]

    # Prefer agreement of the execution timeframes; fall back to the chart model.
    if trends[0] != 0 and trends[0] == trends[1]:
        direction=trends[0]
    elif trends[1] != 0 and trends[1] == trends[2]:
        direction=trends[1]
    else:
        direction=1 if r.get("prediction") == "ABOVE" else -1

    # Strength is deliberately based only on chart state.
    score=0.0
    score += 1.15 * direction * trends[0]
    score += 1.35 * direction * trends[1]
    score += 0.75 * direction * trends[2]
    score += 0.80 * direction * (int(r.get("m1_bos_up",0))-int(r.get("m1_bos_dn",0)))
    score += 1.00 * direction * (int(r.get("m5_bos_up",0))-int(r.get("m5_bos_dn",0)))
    score += 0.55 * direction * (int(r.get("m15_bos_up",0))-int(r.get("m15_bos_dn",0)))
    score += 0.95 * direction * (int(r.get("m1_choch_up",0))-int(r.get("m1_choch_dn",0)))
    score += 1.10 * direction * (int(r.get("m5_choch_up",0))-int(r.get("m5_choch_dn",0)))
    score += 0.65 * direction * (int(r.get("m15_choch_up",0))-int(r.get("m15_choch_dn",0)))

    # Normalize return impulse by ATR so the score is comparable across regimes.
    impulse=(0.45*float(r.get("ret1",0.0))+0.30*float(r.get("ret3",0.0))+0.25*float(r.get("ret5",0.0))) * px
    score += 1.25 * direction * np.clip(impulse/atr,-2.0,2.0)
    score += 0.60 * direction * np.clip(float(r.get("body",0.0)),-1.0,1.0)
    # Opposite-side wick rejection raises exhaustion risk.
    opp_wick=float(r.get("wick_dn",0.0)) if direction < 0 else float(r.get("wick_up",0.0))
    with_wick=float(r.get("wick_up",0.0)) if direction < 0 else float(r.get("wick_dn",0.0))
    score += 0.35*np.clip(with_wick-opp_wick,-1.0,1.0)

    score=float(np.clip(score,-4.0,7.0))
    strength="STRONG" if score>=3.2 else "MODERATE" if score>=1.1 else "WEAK"

    range5=max(float(r.get("range5_abs",0.0)),atr)
    range15=max(float(r.get("range15_abs",0.0)),range5)
    # Remaining-travel estimate: ATR anchor plus a capped fraction of current
    # realized ranges and strength. This is intentionally conservative.
    strength_mult=float(np.clip(0.72 + 0.13*max(score,0.0),0.60,1.55))
    expected=max(0.55*atr, min(2.35*atr, (0.72*atr + 0.18*range5 + 0.07*range15)*strength_mult))
    near=max(0.45*atr,0.48*expected)
    extended=max(1.35*expected,1.10*atr)

    # If a chart swing level lies ahead, use it as a meaningful projected zone.
    ph=float(r.get("protected_high",np.nan)); pl=float(r.get("protected_low",np.nan))
    structural=None
    if direction < 0 and np.isfinite(pl) and pl < px:
        structural=pl
    elif direction > 0 and np.isfinite(ph) and ph > px:
        structural=ph

    near_px=px + direction*near
    base_px=px + direction*expected
    ext_px=px + direction*extended
    if structural is not None:
        # Pull the base projection toward an actual chart level when reasonably close.
        gap=abs(px-structural)
        if 0.35*atr <= gap <= 3.0*atr:
            base_px=structural
            expected=gap
            near_px=px + direction*max(0.40*atr,0.50*gap)
            ext_px=px + direction*max(1.35*gap,1.10*atr)

    # Exhaustion / management state from counter-structure and loss of impulse.
    counter_choch=(int(r.get("m1_choch_up",0)) or int(r.get("m5_choch_up",0))) if direction<0 else (int(r.get("m1_choch_dn",0)) or int(r.get("m5_choch_dn",0)))
    counter_bos=(int(r.get("m1_bos_up",0)) or int(r.get("m5_bos_up",0))) if direction<0 else (int(r.get("m1_bos_dn",0)) or int(r.get("m5_bos_dn",0)))
    adverse_trend=(trends[0] == -direction and trends[0] != 0)
    fading=(direction*impulse < -0.15*atr) or opp_wick > 0.45
    exhaustion_points=int(bool(counter_choch))*2 + int(bool(counter_bos)) + int(bool(adverse_trend)) + int(bool(fading))
    exhaustion="HIGH" if exhaustion_points>=3 else "MEDIUM" if exhaustion_points>=1 else "LOW"

    if counter_choch or (adverse_trend and counter_bos):
        action="CASH OUT"
    elif exhaustion == "MEDIUM" or strength == "WEAK":
        action="PROTECT PROFIT"
    else:
        action="HOLD"

    # Approximate invalidation/reclaim level from nearest opposing swing or ATR.
    if direction < 0:
        invalidation=ph if np.isfinite(ph) and ph>px and (ph-px)<=3.0*atr else px+0.65*atr
    else:
        invalidation=pl if np.isfinite(pl) and pl<px and (px-pl)<=3.0*atr else px-0.65*atr

    return {
        "direction":"UP" if direction>0 else "DOWN",
        "near":float(near_px),"base":float(base_px),"extended":float(ext_px),
        "expected_remaining":float(abs(base_px-px)),"strength":strength,
        "exhaustion":exhaustion,"action":action,"invalidation":float(invalidation),
        "score":score,
    }

def _c(text, color):
    return f"[[{color}]]{text}[[RESET]]"

def _status_color_word(word):
    w=str(word).upper()
    if any(x in w for x in ("ABOVE","BULLISH","LIKELY","HOLD","LOW")): return "GREEN"
    if any(x in w for x in ("BELOW","BEARISH","CASH OUT","HIGH")): return "RED"
    if any(x in w for x in ("MARGINAL","NEUTRAL","PROTECT","MEDIUM","WEAK")): return "YELLOW"
    return "WHITE"

def decision_signal(r, seconds_left):
    """Separate settlement decision layer. Does not alter Chart Signal."""
    sec=max(0,float(seconds_left)); mins=sec/60.0
    chart=r.get("prediction","ABOVE")
    side="ABOVE" if r.get("distance",0.0)>=0 else "BELOW"
    if mins <= 4.5:
        decision=side; role="CURRENT SIDE PRIMARY"
    elif mins <= 6.5:
        # Current side has stronger frozen late accuracy; agreement upgrades confidence only.
        decision=side; role="CURRENT SIDE + CHART CONFIRM"
    else:
        decision=chart; role="CHART PRIMARY"
    agree=(chart==side)
    return {"decision":decision,"role":role,"chart":chart,"current_side":side,"agree":agree}


def build_dashboard(r, now=None, orderflow=None, err=None, of_err=None):
    """Build the complete dashboard in memory.

    Render guard: this function never writes to stdout. Every live section must
    append to this one line list. The live loop is the only place allowed to
    commit a frame to the console.
    """
    now=now or datetime.now(timezone.utc)
    sec=max(0,int((r["close_time"]-now).total_seconds()))
    age=None
    if r.get("quote_time") is not None:
        try: age=max(0.0,(pd.Timestamp(now)-pd.Timestamp(r["quote_time"])).total_seconds())
        except Exception: pass
    pred=r['prediction']; predc="GREEN" if pred=="ABOVE" else "RED"
    L=[]
    add=L.append
    add("="*76)
    add("KALSHI KXBTC15M — V10.11 CHART + DECISION + TR + MP + OF")
    add("="*76)
    add(f"Market:           {r['ticker']}")
    target_txt=f"${r['target']:,.2f}"
    add(f"Target:           {_c(target_txt, 'CYAN')}")
    brti_txt=f"${r['btc']:,.2f}" + (f"   ({age:.1f}s old)" if age is not None else "")
    add(f"BRTI:             {_c(brti_txt,'CYAN')}")
    distance_txt=f"${r['distance']:+,.2f}"
    add(f"Distance:         {_c(distance_txt,'CYAN')}")
    add(f"Time remaining:   {_c(f'{sec//60:02d}:{sec%60:02d}','CYAN')}")
    add("")
    add("PREDICTION")
    add(f"Direction:        {_c(pred,predc)}")
    above_txt=f"{100*r['p_above']:.1f}%"; below_txt=f"{100*r['p_below']:.1f}%"
    add(f"ABOVE / BELOW:    {_c(above_txt,'GREEN')} / {_c(below_txt,'RED')}")
    add(f"Raw model:        {100*r['model_p_above']:.1f}% ABOVE   |   MTF: {100*r['multitf_adjustment']:+.1f} pts")
    add(f"Model:            {r['model_kind']} / {r['model_family']} / cp {r['checkpoint_model']}m")
    ds=decision_signal(r,sec)
    dsc="GREEN" if ds["decision"]=="ABOVE" else "RED"
    add(f"Decision:         {_c(ds['decision'],dsc)}   |   {ds['role']}")
    add(f"Chart/side agree: {'YES' if ds['agree'] else 'NO'}")
    add("")

    mp=move_projection(r)
    mpp=_mp_progress_state(r,mp)
    prog_color='GREEN' if mpp['progress_pct']>=70 else ('YELLOW' if mpp['progress_pct']>=35 else 'CYAN')
    add("MOVE PROJECTION (MP)")
    add(f"Direction:        {_c(mp['direction'], 'GREEN' if mp['direction']=='UP' else 'RED')}   |   Strength: {_c(mp['strength'],_status_color_word(mp['strength']))}")
    near_txt=f"${mpp['near']:,.2f}"; base_txt=f"${mpp['base']:,.2f}"
    add(f"Near / Base:      {_c(near_txt,'CYAN')} / {_c(base_txt,'CYAN')}")
    ext_txt=f"${mpp['extended']:,.2f}"
    add(f"Extended:         {_c(ext_txt,'CYAN')}")
    prog_txt=f"{mpp['progress_pct']:.0f}%"
    add(f"Progress:         {_c(prog_txt,prog_color)} from ${mpp['anchor']:,.2f}   |   Traveled ${mpp['traveled']:,.2f}")
    rem_txt=f"${mpp['remaining_to_base']:,.2f}"
    add(f"Remaining base:   {_c(rem_txt,'CYAN')}   |   Exhaustion: {_c(mp['exhaustion'],_status_color_word(mp['exhaustion']))}")
    add(f"Trade state:      {_c(mp['action'],_status_color_word(mp['action']))}")
    inv_label="Reclaim/cash-out" if mp['direction']=="DOWN" else "Loss/cash-out"
    inv_txt=f"${mp['invalidation']:,.2f}"
    add(f"{inv_label+':':18}{_c(inv_txt,'YELLOW')}")
    add("")

    add("ORDER FLOW (OF) — COINBASE BTC-USD")
    if orderflow:
        of_age=None
        try: of_age=max(0.0,(pd.Timestamp(now)-pd.Timestamp(orderflow.get("time"))).total_seconds())
        except Exception: pass
        pressure=orderflow.get('pressure','NEUTRAL')
        pc='GREEN' if pressure=='BUY' else ('RED' if pressure=='SELL' else 'YELLOW')
        add(f"Pressure:         {_c(pressure,pc)}   |   5bp imbalance {100*orderflow.get('imbalance',0.0):+.1f}%")
        add(f"Depth 5bp:        bid {orderflow.get('bid_depth_5bps',0.0):.2f} BTC / ask {orderflow.get('ask_depth_5bps',0.0):.2f} BTC")
        add(f"Depletion:        ask {orderflow.get('ask_depletion_band','<1%')} {100*orderflow.get('ask_depletion',0.0):.1f}% / bid {orderflow.get('bid_depletion_band','<1%')} {100*orderflow.get('bid_depletion',0.0):.1f}%")
        add(f"Buy sweep:        1bp {orderflow.get('buy_to_sweep_1bps',0.0):.2f} BTC / 5bp {orderflow.get('buy_to_sweep_5bps',0.0):.2f} BTC")
        add(f"Sell sweep:       1bp {orderflow.get('sell_to_sweep_1bps',0.0):.2f} BTC / 5bp {orderflow.get('sell_to_sweep_5bps',0.0):.2f} BTC")
        add(f"Book spread:      ${orderflow.get('spread',0.0):.2f}" + (f"   ({of_age:.1f}s old)" if of_age is not None else ""))
    else:
        add("Status:           waiting for Coinbase order book...")
    add("")

    tr=target_reachability(r['distance'],r['atr1m_14'],sec,r.get('prediction'))
    add("TARGET REACHABILITY (TR)")
    add(f"Status:           {_c(tr['status'],_status_color_word(tr['status']))}   |   Score {tr['tr_score']:.2f}")
    add(f"Volatility travel:${tr['travel_budget']:,.2f}   |   Cross {100*tr['cross_estimate']:.1f}%")
    if tr.get('role'):
        add(f"Role:             {_c(tr['role'],_status_color_word(tr['role']))}")
    add("")

    add("STRUCTURE")
    add(f"Trend 1m/5m/15m:  {_c(tname(r['m1_trend']),_status_color_word(tname(r['m1_trend'])))} / {_c(tname(r['m5_trend']),_status_color_word(tname(r['m5_trend'])))} / {_c(tname(r['m15_trend']),_status_color_word(tname(r['m15_trend'])))}")
    add(f"Protected H/L:    ${r['protected_high']:,.2f} / ${r['protected_low']:,.2f}")
    add(f"15m sequence:     HH->LL {bool(r['dev15_hh_then_ll'])} / LL->HH {bool(r['dev15_ll_then_hh'])}")
    add(f"15m BOS up/down:  {r['m15_bos_up']}/{r['m15_bos_dn']}   |   CHOCH {r['m15_choch_up']}/{r['m15_choch_dn']}")
    add(f"ATR14 (1m):       ${r['atr1m_14']:.2f}")
    if err: add(f"BRTI refresh:     {str(err)[:55]}")
    if of_err: add(f"Order-flow error: {str(of_err)[:55]}")
    add("="*76)
    return "\n".join(L)

# Compatibility wrapper for one-shot/non-live mode only.
def print_result(r, now=None, orderflow=None):
    print(build_dashboard(r,now,orderflow))

def _init_live_display():
    """Initialize the live dashboard state.

    V10.8 renders the entire dashboard as one fixed-width rectangular frame.
    On Windows it uses WriteConsoleOutputW so the whole frame is committed in
    one native console operation.  This avoids cursor drift, line wrapping,
    duplicated old frames, CLS flashing, and ANSI cursor-home problems.
    """
    global _DISPLAY_STATE
    _DISPLAY_STATE = {"lines": 0, "width": 76}


def _parse_color_markup(line):
    """Return [(text,color)] from lightweight [[COLOR]] markers."""
    import re
    colors={"RESET":"WHITE","WHITE":"WHITE","GRAY":"GRAY","RED":"RED","GREEN":"GREEN","YELLOW":"YELLOW","CYAN":"CYAN"}
    out=[]; pos=0; cur="WHITE"
    for m in re.finditer(r"\[\[(RESET|WHITE|GRAY|RED|GREEN|YELLOW|CYAN)\]\]", line):
        if m.start()>pos: out.append((line[pos:m.start()],cur))
        cur=colors[m.group(1)]; pos=m.end()
    if pos<len(line): out.append((line[pos:],cur))
    return out


def _visible_text(line):
    import re
    return re.sub(r"\[\[(?:RESET|WHITE|GRAY|RED|GREEN|YELLOW|CYAN)\]\]", "", line)


def _render_frame(text):
    """Render one complete, fixed-width dashboard frame.

    Windows: one WriteConsoleOutputW rectangular buffer write with native color
    attributes.  No per-field cursor moves and no CLS.
    Other platforms: a conservative ANSI home/clear fallback.
    """
    global _DISPLAY_STATE
    width=int(_DISPLAY_STATE.get("width",76))
    incoming=text.rstrip("\n").splitlines()
    # Keep enough rows to overwrite remnants of a previously taller frame.
    height=max(len(incoming), int(_DISPLAY_STATE.get("lines",0)), 1)
    lines=incoming + [""]*(height-len(incoming))

    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            k32=ctypes.windll.kernel32
            STD_OUTPUT_HANDLE=-11
            h=k32.GetStdHandle(STD_OUTPUT_HANDLE)

            class COORD(ctypes.Structure):
                _fields_=[("X",ctypes.c_short),("Y",ctypes.c_short)]
            class SMALL_RECT(ctypes.Structure):
                _fields_=[("Left",ctypes.c_short),("Top",ctypes.c_short),("Right",ctypes.c_short),("Bottom",ctypes.c_short)]
            class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
                _fields_=[("dwSize",COORD),("dwCursorPosition",COORD),("wAttributes",wintypes.WORD),
                          ("srWindow",SMALL_RECT),("dwMaximumWindowSize",COORD)]
            class CHAR_UNION(ctypes.Union):
                _fields_=[("UnicodeChar",wintypes.WCHAR),("AsciiChar",ctypes.c_char)]
            class CHAR_INFO(ctypes.Structure):
                _anonymous_=("Char",)
                _fields_=[("Char",CHAR_UNION),("Attributes",wintypes.WORD)]

            info=CONSOLE_SCREEN_BUFFER_INFO()
            if not k32.GetConsoleScreenBufferInfo(h,ctypes.byref(info)):
                raise OSError("GetConsoleScreenBufferInfo failed")

            # Use the current visible window's top row, not absolute buffer row 0.
            top=0
            available=max(1, int(info.srWindow.Right-info.srWindow.Left+1))
            frame_width=min(width, max(40,available-1))

            # Standard bright console attributes on black background.
            attrs={
                "WHITE":0x0007,
                "GRAY":0x0008,
                "RED":0x000C,
                "GREEN":0x000A,
                "YELLOW":0x000E,
                "CYAN":0x000B,
            }

            buf=(CHAR_INFO*(frame_width*height))()
            for row,line in enumerate(lines):
                col=0
                for seg,color in _parse_color_markup(line):
                    for ch in seg:
                        if col>=frame_width: break
                        idx=row*frame_width+col
                        buf[idx].UnicodeChar=ch
                        buf[idx].Attributes=attrs.get(color,attrs["WHITE"])
                        col+=1
                    if col>=frame_width: break
                while col<frame_width:
                    idx=row*frame_width+col
                    buf[idx].UnicodeChar=' '
                    buf[idx].Attributes=attrs["WHITE"]
                    col+=1

            region=SMALL_RECT(0, top, frame_width-1, top+height-1)
            ok=k32.WriteConsoleOutputW(h,buf,COORD(frame_width,height),COORD(0,0),ctypes.byref(region))
            if not ok:
                raise OSError("WriteConsoleOutputW failed")
            # Keep the cursor at the upper-left. Never move it below the frame,
            # which can scroll the console window and desynchronize future writes.
            try:
                k32.SetConsoleCursorPosition(h,COORD(0,0))
            except Exception:
                pass
            _DISPLAY_STATE["lines"]=len(incoming)
            return
        except Exception:
            pass

    # Portable fallback.  Still writes the frame as one string.
    ansi={"WHITE":"\x1b[37m","GRAY":"\x1b[90m","RED":"\x1b[91m","GREEN":"\x1b[92m","YELLOW":"\x1b[93m","CYAN":"\x1b[96m"}
    reset="\x1b[0m"
    rendered=[]
    for line in lines:
        out=""; visible_count=0
        for seg,color in _parse_color_markup(line):
            room=width-visible_count
            if room<=0: break
            piece=seg[:room]
            out += ansi.get(color,ansi["WHITE"])+piece+reset
            visible_count += len(piece)
        out += " "*max(0,width-visible_count)
        rendered.append(out)
    sys.stdout.write("\x1b[H"+"\n".join(rendered)+"\x1b[J")
    sys.stdout.flush()
    _DISPLAY_STATE["lines"]=len(incoming)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--train",action="store_true")
    ap.add_argument("--watch",action="store_true")
    ap.add_argument("--brti-interval",type=float,default=2.0,help="BRTI/network refresh seconds")
    ap.add_argument("--display-interval",type=float,default=1.0,help="Local countdown redraw seconds")
    ap.add_argument("--orderflow-interval",type=float,default=2.0,help="Coinbase order-book refresh seconds")
    ap.add_argument("--allow-coinbase-fallback",action="store_true")
    ap.add_argument("--json",action="store_true")
    args=ap.parse_args()
    if args.train or not MODEL_FILE.exists():
        train_bundle()
        if args.train and not args.watch:
            print(f"Saved {MODEL_FILE}"); return
    if not args.watch:
        market=fetch_active_kalshi_market(); ticks=fetch_brti_history(hours=6); recent,_=fetch_brti_recent_values()
        r=predict_from_data(market,brti_ticks_to_1m(ticks),float(recent.iloc[-1].value),"BRTI",recent.iloc[-1].time)
        print(json.dumps(r,indent=2,default=str) if args.json else "")
        if not args.json: print_result(r)
        return
    eng=LiveEngine(args.allow_coinbase_fallback,args.brti_interval,args.orderflow_interval)
    th=threading.Thread(target=eng.worker,daemon=True); th.start()
    th_of=threading.Thread(target=eng.orderflow_worker,daemon=True); th_of.start()
    _init_live_display()
    try:
        while True:
            r,err=eng.snapshot()
            of,of_err=eng.orderflow_snapshot()
            if r is None:
                if err and "No currently-open KXBTC15M contract found" in str(err):
                    frame="V10.11 — WAITING FOR NEXT KXBTC15M CONTRACT...\nAuto-roll is active; retrying automatically."
                else:
                    frame="V10.11 initializing BRTI history, chart model, and order flow...\nCountdown will refresh every second once the active contract is loaded."
                    if err: frame += "\nERROR: " + str(err)
            else:
                if args.json:
                    out=dict(r); out["seconds_left_live"]=(r["close_time"]-datetime.now(timezone.utc)).total_seconds()
                    out["target_reachability"]=target_reachability(r["distance"],r["atr1m_14"],out["seconds_left_live"],r.get("prediction"))
                    _mp=move_projection(r)
                    _mp["progress"]=_mp_progress_state(r,_mp)
                    out["move_projection"]=_mp
                    frame=json.dumps(out,indent=2,default=str)
                else:
                    _now=datetime.now(timezone.utc)
                    frame=build_dashboard(r,_now,of,err,of_err)
            _render_frame(frame)
            # Never exit at contract expiry. The background worker automatically
            # discovers the next KXBTC15M contract and replaces the snapshot.
            time.sleep(max(args.display_interval,0.25))
    except KeyboardInterrupt:
        pass
    finally:
        eng.stop()

if __name__=="__main__":
    main()
