#!/usr/bin/env python3
"""
BTC15M AUTO LIVE V10.25 — FAST BRTI + ROLLOVER + FLIP + OF RESPONSE RESEARCH
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
import os
import csv, base64, json, math, os, sys, time, threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests
try:
    import websocket
except Exception:
    websocket=None
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
KALSHI_WS_URL = "wss://external-api-ws.kalshi.com/trade-api/ws/v2"
KALSHI_WS_PATH = "/trade-api/ws/v2"
COINBASE_CANDLES = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
COINBASE_BOOK = "https://api.exchange.coinbase.com/products/BTC-USD/book"
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


def _auth_headers_full_path(method, full_path):
    """Kalshi auth for paths outside REST /trade-api/v2, notably /trade-api/ws/v2."""
    key_id=os.getenv("KALSHI_API_KEY_ID","").strip()
    if not key_id: raise RuntimeError("KALSHI_API_KEY_ID is not set.")
    ts=str(int(time.time()*1000))
    msg=(ts+method.upper()+full_path).encode()
    sig=_load_private_key().sign(msg,padding.PSS(mgf=padding.MGF1(hashes.SHA256()),salt_length=padding.PSS.DIGEST_LENGTH),hashes.SHA256())
    return {"KALSHI-ACCESS-KEY":key_id,"KALSHI-ACCESS-TIMESTAMP":ts,"KALSHI-ACCESS-SIGNATURE":base64.b64encode(sig).decode(),"User-Agent":"btc15m-v10.25/1.0"}

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


def fetch_next_kalshi_market(after_close, now=None):
    """Prefetch the next listed KXBTC15M contract before the current one expires."""
    now=now or datetime.now(timezone.utc)
    data=_public_get("/markets",{"series_ticker":"KXBTC15M","limit":100})
    candidates=[]
    for m in data.get("markets",[]):
        if "KXBTC15M" not in str(m.get("ticker","")): continue
        close=parse_dt(m.get("close_time") or m.get("expiration_time")); op=parse_dt(m.get("open_time"))
        target=m.get("floor_strike",m.get("functional_strike"))
        try: target=float(target)
        except Exception: continue
        if close and close>after_close and (op is None or op<=close): candidates.append((close,m,target,op))
    if not candidates: return None
    close,m,target,op=sorted(candidates,key=lambda x:x[0])[0]
    return {"ticker":m.get("ticker"),"target":target,"close_time":close,"open_time":op}

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

def _mx_float(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception: return None

def fetch_multi_exchange_prices(timeout=2.5):
    out={"time":datetime.now(timezone.utc)}
    try: out["coinbase"]=_mx_float(requests.get(MULTI_EXCHANGE_URLS["coinbase"],timeout=timeout).json().get("price"))
    except Exception: out["coinbase"]=None
    try:
        j=requests.get(MULTI_EXCHANGE_URLS["kraken"],timeout=timeout).json()
        v=next(iter((j.get("result") or {}).values()),{})
        out["kraken"]=_mx_float((v.get("c") or [None])[0])
    except Exception: out["kraken"]=None
    try: out["bitstamp"]=_mx_float(requests.get(MULTI_EXCHANGE_URLS["bitstamp"],timeout=timeout).json().get("last"))
    except Exception: out["bitstamp"]=None
    try: out["gemini"]=_mx_float(requests.get(MULTI_EXCHANGE_URLS["gemini"],timeout=timeout).json().get("last"))
    except Exception: out["gemini"]=None
    vals=[out[k] for k in ("coinbase","kraken","bitstamp","gemini","crypto_com") if out.get(k) is not None]
    if vals:
        a=sorted(vals); n=len(a)
        out["median"]=a[n//2] if n%2 else (a[n//2-1]+a[n//2])/2
        out["mean"]=sum(a)/n; out["spread"]=max(a)-min(a); out["n"]=n
    else: out.update({"median":None,"mean":None,"spread":None,"n":0})
    return out


def _normalize_book_rows(rows):
    out=[]
    for row in rows or []:
        try:
            if isinstance(row,dict):
                px=float(row.get("price"))
                sz=float(row.get("amount"))
            else:
                px=float(row[0]); sz=float(row[1])
            if px>0 and sz>=0:
                out.append((px,sz))
        except Exception:
            pass
    return out

def fetch_exchange_order_book(exchange):
    """Fetch a public BTC-USD spot order book and normalize it to (price, BTC size)."""
    headers={"User-Agent":"btc15m-multi-of/1.0"}
    if exchange=="coinbase":
        r=requests.get(MULTI_EXCHANGE_BOOK_URLS["coinbase"],params={"level":2},headers=headers,timeout=8)
        r.raise_for_status(); j=r.json()
        bids=_normalize_book_rows(j.get("bids")); asks=_normalize_book_rows(j.get("asks"))
    elif exchange=="kraken":
        r=requests.get(MULTI_EXCHANGE_BOOK_URLS["kraken"],params={"pair":"XBTUSD","count":500},headers=headers,timeout=8)
        r.raise_for_status(); j=r.json()
        result=j.get("result") or {}
        v=next(iter(result.values()),{})
        bids=_normalize_book_rows(v.get("bids")); asks=_normalize_book_rows(v.get("asks"))
    elif exchange=="bitstamp":
        r=requests.get(MULTI_EXCHANGE_BOOK_URLS["bitstamp"],headers=headers,timeout=8)
        r.raise_for_status(); j=r.json()
        bids=_normalize_book_rows(j.get("bids")); asks=_normalize_book_rows(j.get("asks"))
    elif exchange=="gemini":
        r=requests.get(MULTI_EXCHANGE_BOOK_URLS["gemini"],params={"limit_bids":500,"limit_asks":500},headers=headers,timeout=8)
        r.raise_for_status(); j=r.json()
        bids=_normalize_book_rows(j.get("bids")); asks=_normalize_book_rows(j.get("asks"))
    elif exchange=="crypto_com":
        r=requests.get(
            MULTI_EXCHANGE_BOOK_URLS["crypto_com"],
            params={"instrument_name":"BTC_USD","depth":50},
            headers=headers,timeout=8
        )
        r.raise_for_status(); j=r.json()
        result=j.get("result") or {}
        data=result.get("data") if isinstance(result,dict) else None
        if isinstance(data,list):
            data=data[0] if data else {}
        if not isinstance(data,dict):
            data=result if isinstance(result,dict) else {}
        bids=_normalize_book_rows(data.get("bids")); asks=_normalize_book_rows(data.get("asks"))
    else:
        raise ValueError(f"Unsupported exchange: {exchange}")

    if not bids or not asks:
        raise RuntimeError(f"{exchange} order book returned no usable bid/ask levels.")
    bids=sorted(bids,key=lambda x:x[0],reverse=True)
    asks=sorted(asks,key=lambda x:x[0])
    return {"exchange":exchange,"bids":bids,"asks":asks,"time":datetime.now(timezone.utc)}

def combine_exchange_orderflow(per_exchange):
    """Equal-weight normalized consensus so a deeper venue cannot dominate."""
    good=[v for v in (per_exchange or {}).values() if isinstance(v,dict) and v.get("imbalance") is not None]
    if not good:
        return {"pressure":"NEUTRAL","pressure_score":0.0,"imbalance":0.0,
                "ask_depletion":0.0,"bid_depletion":0.0,"buy_count":0,"sell_count":0,
                "neutral_count":0,"n":0,"consensus":"0/0 NEUTRAL"}
    avg=lambda k: float(sum(float(x.get(k,0.0)) for x in good)/len(good))
    score=avg("pressure_score")
    pressure="BUY" if score>=0.15 else "SELL" if score<=-0.15 else "NEUTRAL"
    buy=sum(1 for x in good if x.get("pressure")=="BUY")
    sell=sum(1 for x in good if x.get("pressure")=="SELL")
    neutral=sum(1 for x in good if x.get("pressure")=="NEUTRAL")
    side="BUY" if buy>sell else "SELL" if sell>buy else "NEUTRAL"
    votes=max(buy,sell) if side!="NEUTRAL" else neutral
    return {
        "pressure":pressure,
        "pressure_score":score,
        "imbalance":avg("imbalance"),
        "ask_depletion":avg("ask_depletion"),
        "bid_depletion":avg("bid_depletion"),
        "buy_count":buy,"sell_count":sell,"neutral_count":neutral,
        "n":len(good),
        "consensus":f"{votes}/{len(good)} {side}",
    }

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
        self.multi_exchange=None; self.multi_exchange_error=None
        self.multi_orderflow={}
        self.multi_orderflow_error={}
        self._multi_of_previous={}

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

    def multi_exchange_snapshot(self):
        with self.lock:
            return self.multi_exchange, self.multi_exchange_error

    def multi_exchange_worker(self):
        """Collect multi-exchange spot snapshots plus normalized L2 order-flow research."""
        while self.running:
            started=time.monotonic()
            price_cur=None
            try:
                price_cur=fetch_multi_exchange_prices()
            except Exception:
                pass

            per={}
            errs={}
            for ex in ("coinbase","kraken","bitstamp","gemini","crypto_com"):
                try:
                    book=fetch_exchange_order_book(ex)
                    prev=self._multi_of_previous.get(ex)
                    cur=summarize_order_book(book,prev)
                    cur["exchange"]=ex
                    self._multi_of_previous[ex]=cur
                    per[ex]=cur
                except Exception as e:
                    errs[ex]=str(e)

            combined=combine_exchange_orderflow(per)
            with self.lock:
                if price_cur is not None:
                    self.multi_exchange=price_cur
                    self.multi_exchange_error=None
                self.multi_orderflow={"venues":per,"combined":combined,"time":datetime.now(timezone.utc)}
                self.multi_orderflow_error=errs

            delay=max(0.05,self.orderflow_interval-(time.monotonic()-started))
            time.sleep(delay)

    def multi_orderflow_snapshot(self):
        with self.lock:
            return (
                dict(self.multi_orderflow) if self.multi_orderflow else {},
                dict(self.multi_orderflow_error) if self.multi_orderflow_error else {}
            )

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

TR_PLATT_INTERCEPT = -0.756150291644
TR_PLATT_SLOPE = 0.761084603780

def _tr_calibrate_probability(raw_cross):
    """Frozen V10.19 chronological Platt calibration."""
    p=float(np.clip(raw_cross,1e-6,1.0-1e-6))
    logit=math.log(p/(1.0-p))
    z=TR_PLATT_INTERCEPT + TR_PLATT_SLOPE*logit
    return float(1.0/(1.0+math.exp(-z)))

def target_reachability(distance, atr1m, seconds_left, prediction=None):
    """
    V10.19 Target Reachability.

    Core geometry remains the original distance / ATR / sqrt(time) first-passage
    heuristic. The raw erfc crossing estimate is retained for diagnostics, but
    the displayed crossing probability is now chronologically calibrated from
    historical live research data.

    OF is deliberately NOT inserted into this probability because the current
    data did not validate a robust broad improvement from doing so.
    """
    mins=max(float(seconds_left)/60.0, 1.0/60.0)
    atr=max(float(atr1m), 1e-9)
    travel=float(atr*math.sqrt(mins))
    score=float(abs(float(distance))/(travel+1e-12))
    raw_cross=float(np.clip(math.erfc(score/math.sqrt(2.0)),0.0,1.0))
    cross=_tr_calibrate_probability(raw_cross)
    if cross >= 0.65:
        status="LIKELY REACHABLE"
    elif cross >= 0.35:
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
        "raw_cross_estimate":raw_cross,
        "cross_estimate":cross,
        "calibrated_cross_estimate":cross,
        "status":status,
        "current_side":current_side,
        "role":role,
        "calibration":"V10.19 chronological Platt",
    }

def target_reachability_of_context(r, mof, early=None):
    """Research-only OF relationship to the Kalshi target. Does not alter TR probability."""
    distance=float(r.get("distance",0.0))
    side_sign=1.0 if distance>=0 else -1.0
    c=(mof or {}).get("combined") or {}
    pressure=float(c.get("pressure_score") or 0.0)
    n=max(1,int(c.get("n") or 0))
    net=(int(c.get("buy_count") or 0)-int(c.get("sell_count") or 0))/n
    toward_score=-side_sign*pressure
    consensus_toward=-side_sign*net
    es=str((early or {}).get("signal") or "NONE").upper()
    early_toward=(distance>=0 and es=="EARLY SELL") or (distance<0 and es=="EARLY BUY")
    early_away=(distance>=0 and es=="EARLY BUY") or (distance<0 and es=="EARLY SELL")
    if toward_score>=0.15 or early_toward:
        state="TOWARD TARGET"
    elif toward_score<=-0.15 or early_away:
        state="AWAY FROM TARGET"
    else:
        state="NEUTRAL"
    return {
        "state":state,
        "toward_score":float(toward_score),
        "consensus_toward":float(consensus_toward),
        "early_signal":es,
        "changes_probability":False,
    }


_MP_TRACKER = {}

def _mp_progress_state(r, mp):
    """V10.26 projection lifecycle.

    The MP zones are one fixed projection *leg*. When the Base objective is
    reached, the completed leg is retired immediately and a fresh projection is
    anchored at the current BRTI using the current structural MP calculation.
    This prevents Progress from remaining at 100-200% while stale targets stay
    associated with an already-completed move.

    A structural direction change also starts a new leg immediately. The
    lifecycle does not assume that a completed leg must continue; it simply
    re-anchors and lets current structure/developing-move logic determine the
    next projection.
    """
    key=str(r.get("ticker","UNKNOWN"))
    direction=str(mp.get("structural_direction") or mp.get("direction") or "UP")
    px=float(r["btc"])
    qt=r.get("quote_time")
    quote_key=str(qt) if qt is not None else f"{px:.8f}"

    def _fresh(previous=None, reason="NEW PROJECTION"):
        prev_leg=int((previous or {}).get("leg_id",0))
        completed=int((previous or {}).get("completed_legs",0))
        return {
            "direction":direction,
            "anchor":px,
            "near":float(mp["near"]),
            "base":float(mp["base"]),
            "extended":float(mp["extended"]),
            "leg_id":prev_leg+1,
            "completed_legs":completed,
            "last_event":reason,
            "last_event_quote":quote_key,
        }

    st=_MP_TRACKER.get(key)
    if st is None:
        _MP_TRACKER.clear()
        st=_fresh(None,"NEW PROJECTION")
        _MP_TRACKER[key]=st
    elif st.get("direction") != direction:
        prior=dict(st)
        st=_fresh(prior,"DIRECTION CHANGE — REPROJECTED")
        _MP_TRACKER.clear(); _MP_TRACKER[key]=st

    sign=1.0 if direction=="UP" else -1.0
    anchor=float(st["anchor"]); base=float(st["base"])
    total=sign*(base-anchor)

    # A malformed/stale zone should never be allowed to survive.
    if total <= 1e-9:
        prior=dict(st)
        st=_fresh(prior,"INVALID ZONE — REPROJECTED")
        _MP_TRACKER.clear(); _MP_TRACKER[key]=st
        anchor=float(st["anchor"]); base=float(st["base"])
        total=max(1e-9,sign*(base-anchor))

    traveled_signed=sign*(px-anchor)
    raw_progress=traveled_signed/total

    # Base = completion of the current projection leg. Re-arm immediately.
    # Historical V10.26 testing showed post-base continuation was ~coin-flip,
    # so completion does not imply another same-direction extension; instead
    # we ask current MP structure for an entirely fresh leg.
    if raw_progress >= 1.0:
        prior=dict(st)
        prior["completed_legs"]=int(prior.get("completed_legs",0))+1
        st=_fresh(prior,"BASE ACHIEVED — REPROJECTED")
        st["completed_legs"]=int(prior["completed_legs"])
        _MP_TRACKER.clear(); _MP_TRACKER[key]=st
        anchor=float(st["anchor"]); base=float(st["base"])
        total=max(1e-9,sign*(base-anchor))
        traveled_signed=0.0
        raw_progress=0.0

    progress=max(0.0,min(1.0,raw_progress))
    remaining=max(0.0,sign*(base-px))
    status=st.get("last_event","ACTIVE") if st.get("last_event_quote")==quote_key else "ACTIVE"
    return {
        "anchor":float(st["anchor"]),
        "near":float(st["near"]),
        "base":float(st["base"]),
        "extended":float(st["extended"]),
        "progress":float(progress),
        "progress_pct":100.0*float(progress),
        "traveled":max(0.0,float(traveled_signed)),
        "remaining_to_base":float(remaining),
        "projection_status":status,
        "leg_id":int(st.get("leg_id",1)),
        "completed_legs":int(st.get("completed_legs",0)),
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


def interpret_15m_structure(r):
    """Collapse raw 15m sequence/BOS/CHOCH into one execution-friendly label."""
    seq_bull=bool(r.get("dev15_ll_then_hh",0))
    seq_bear=bool(r.get("dev15_hh_then_ll",0))
    bos_up=bool(r.get("m15_bos_up",0)); bos_dn=bool(r.get("m15_bos_dn",0))
    ch_up=bool(r.get("m15_choch_up",0)); ch_dn=bool(r.get("m15_choch_dn",0))
    trend=int(r.get("m15_trend",0) or 0)

    if (ch_up and ch_dn) or (bos_up and bos_dn) or (seq_bull and seq_bear):
        return "MIXED / EXPANSION"
    if ch_up:
        return "STRONG BULLISH SHIFT" if (bos_up or seq_bull) else "BULLISH SHIFT"
    if ch_dn:
        return "STRONG BEARISH SHIFT" if (bos_dn or seq_bear) else "BEARISH SHIFT"
    if bos_up:
        return "BULLISH BREAK"
    if bos_dn:
        return "BEARISH BREAK"
    if seq_bull:
        return "BULLISH REVERSAL"
    if seq_bear:
        return "BEARISH REVERSAL"
    if trend > 0:
        return "BULLISH STRUCTURE"
    if trend < 0:
        return "BEARISH STRUCTURE"
    return "NEUTRAL / NO STRUCTURAL BREAK"

def interpret_mp_thesis(r, mp=None):
    """Directional wording for the MP invalidation / management state."""
    mp=mp or move_projection(r)
    side="BULLISH" if mp.get("direction")=="UP" else "BEARISH"
    action=str(mp.get("action") or "")
    if action=="CASH OUT":
        return f"{side} THESIS INVALIDATING"
    if action=="PROTECT PROFIT":
        return f"{side} THESIS AT RISK"
    return f"{side} THESIS SAFE"

def interpret_target_of(r, trof):
    """Translate toward/away target semantics into direction + strength."""
    state=str((trof or {}).get("state") or "NEUTRAL")
    score=float((trof or {}).get("toward_score") or 0.0)
    current_side="ABOVE" if float(r.get("distance",0.0))>=0 else "BELOW"

    if state=="NEUTRAL":
        return {"direction":"NEUTRAL PRESSURE","strength":"NEUTRAL","display":"NEUTRAL PRESSURE"}

    if state=="TOWARD TARGET":
        direction="BEARISH PRESSURE" if current_side=="ABOVE" else "BULLISH PRESSURE"
    else:
        direction="BULLISH PRESSURE" if current_side=="ABOVE" else "BEARISH PRESSURE"

    a=abs(score)
    strength="STRONG" if a>=0.25 else "MODERATE" if a>=0.15 else "WEAK"
    return {"direction":direction,"strength":strength,"display":f"{direction} — {strength}"}

def interpret_of_early(early):
    sig=str((early or {}).get("signal") or "NONE")
    if sig=="EARLY BUY":
        return "EARLY BULLISH"
    if sig=="EARLY SELL":
        return "EARLY BEARISH"
    return "NONE"

def of_early_confirmation(early):
    """Evidence-based confirmation state from the existing live OF history.

    Historical validation favored persistence over Micro/breadth as a mandatory
    gate.  We therefore use same-direction combined OF persistence as the
    confirmation criterion, while Micro/breadth remain context.
    """
    sig=str((early or {}).get("signal") or "NONE")
    if sig=="NONE":
        return {"state":"NONE","direction":"NEUTRAL","persistence":None}

    direction=1 if sig=="EARLY BUY" else -1
    now_ts=_EARLY_OF_HISTORY[-1]["ts"] if _EARLY_OF_HISTORY else None
    if now_ts is None:
        return {"state":"UNCONFIRMED","direction":"BULLISH" if direction>0 else "BEARISH","persistence":None}

    recent=[x for x in _EARLY_OF_HISTORY if now_ts-10.0 < x["ts"] <= now_ts]
    valid=[x for x in recent if x.get("combined_pressure") is not None]
    persistence=(sum(1 for x in valid if direction*float(x["combined_pressure"])>=0.15)/len(valid)) if valid else None
    age=None
    # Find the first same-direction signal onset approximately from current early state.
    # The live early detector resets on NONE/opposite direction; confirmation is deliberately short-lived.
    if persistence is not None and len(valid)>=2:
        span=max(0.0,valid[-1]["ts"]-valid[0]["ts"])
    else:
        span=0.0

    word="BULLISH" if direction>0 else "BEARISH"
    if persistence is not None and span>=8.0 and persistence>=0.50:
        state=f"{word} CONFIRMED"
    elif persistence is not None and span>=4.0 and persistence>=0.50:
        state=f"{word} CONFIRMING"
    else:
        state=f"EARLY {word} — UNCONFIRMED"
    return {"state":state,"direction":word,"persistence":persistence,"window_span_s":span}

def interpret_of_micro(micro):
    sig=str((micro or {}).get("signal") or "NEUTRAL")
    strength=str((micro or {}).get("strength") or "WEAK")
    if sig=="BUY":
        return f"BULLISH PRESSURE — {strength}"
    if sig=="SELL":
        return f"BEARISH PRESSURE — {strength}"
    return "NEUTRAL PRESSURE"

def _status_color_word(word):
    w=str(word).upper()
    if any(x in w for x in ("ABOVE","BULLISH","LIKELY","HOLD","LOW")): return "GREEN"
    if any(x in w for x in ("BELOW","BEARISH","CASH OUT","HIGH")): return "RED"
    if any(x in w for x in ("MARGINAL","NEUTRAL","PROTECT","MEDIUM","WEAK")): return "YELLOW"
    return "WHITE"

RESEARCH_LOG_FILE = HERE / "BTC15M_V10_27_FORWARD_VALIDATED_OF_FLIP_MP_RESEARCH_LOG.csv"
_RESEARCH_LAST_KEY = None

def decision_signal(r, seconds_left):
    """V10.18 settlement decision: current-side anchored, Chart supplies context."""
    sec=max(0,float(seconds_left)); mins=sec/60.0
    chart=r.get("prediction","ABOVE")
    side="ABOVE" if r.get("distance",0.0)>=0 else "BELOW"
    # Major-research result: current side outperformed Chart on settlement
    # checkpoints in the accumulated live sample and remains dominant late.
    decision=side
    if mins <= 4.5:
        role="CURRENT SIDE PRIMARY — LATE"
    elif mins <= 8.0:
        role="CURRENT SIDE PRIMARY + CHART CONTEXT"
    else:
        role="CURRENT SIDE ANCHOR + CHART CONTEXT"
    agree=(chart==side)
    return {"decision":decision,"role":role,"chart":chart,"current_side":side,"agree":agree}


# ---------------------------------------------------------------------------
# V10.16 ORDER-FLOW EARLY DETECTION RESEARCH
# ---------------------------------------------------------------------------
# IMPORTANT: this is a research-only warning layer. It does NOT modify Chart
# Signal, Decision Signal, Target Reachability, or Move Projection.
#
# The purpose is to capture whether multi-exchange order-flow deterioration /
# improvement begins BEFORE price/structure/Chart/MP confirmation.  Raw
# components are logged so thresholds can be re-tested later without changing
# the historical data.
_EARLY_OF_HISTORY = []
_EARLY_OF_LAST = {}
_EARLY_OF_PREV_SIGNAL = "NONE"

def _safe_float(x):
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except Exception:
        return None

def _nearest_prior(history, now_ts, seconds):
    target=now_ts-float(seconds)
    candidates=[x for x in history if x["ts"]<=target]
    return candidates[-1] if candidates else None

def _of_early_detection(mof, now):
    """Research-only early-warning candidate based on OF acceleration/convergence."""
    global _EARLY_OF_HISTORY, _EARLY_OF_LAST, _EARLY_OF_PREV_SIGNAL
    venues=(mof or {}).get("venues") or {}
    combined=(mof or {}).get("combined") or {}
    now_ts=now.timestamp()

    snap={"ts":now_ts,
          "combined_pressure":_safe_float(combined.get("pressure_score")),
          "combined_imbalance":_safe_float(combined.get("imbalance")),
          "venues":{}}
    for ex in ("coinbase","kraken","bitstamp","gemini","crypto_com"):
        v=venues.get(ex) or {}
        snap["venues"][ex]={
            "pressure":_safe_float(v.get("pressure_score")),
            "imbalance":_safe_float(v.get("imbalance")),
            "ask_dep":_safe_float(v.get("ask_depletion")),
            "bid_dep":_safe_float(v.get("bid_depletion")),
        }

    # Do not duplicate the same order-book snapshot in the history.
    mof_time=(mof or {}).get("time")
    key=str(mof_time) if mof_time is not None else f"{now_ts:.3f}"
    if not _EARLY_OF_HISTORY or _EARLY_OF_HISTORY[-1].get("key") != key:
        snap["key"]=key
        _EARLY_OF_HISTORY.append(snap)
        cutoff=now_ts-90.0
        _EARLY_OF_HISTORY=[x for x in _EARLY_OF_HISTORY if x["ts"]>=cutoff]

    p2=_nearest_prior(_EARLY_OF_HISTORY,now_ts,2)
    p6=_nearest_prior(_EARLY_OF_HISTORY,now_ts,6)
    p10=_nearest_prior(_EARLY_OF_HISTORY,now_ts,10)

    def delta(cur, old, key):
        a=cur.get(key); b=(old or {}).get(key)
        return None if a is None or b is None else a-b

    dp2=delta(snap,p2,"combined_pressure")
    dp6=delta(snap,p6,"combined_pressure")
    dp10=delta(snap,p10,"combined_pressure")
    di6=delta(snap,p6,"combined_imbalance")

    deteriorating=0; improving=0; venue_valid=0
    venue_delta={}
    for ex,v in snap["venues"].items():
        old=((p6 or {}).get("venues") or {}).get(ex) or {}
        dp=None if v["pressure"] is None or old.get("pressure") is None else v["pressure"]-old["pressure"]
        di=None if v["imbalance"] is None or old.get("imbalance") is None else v["imbalance"]-old["imbalance"]
        skew=None if v["ask_dep"] is None or v["bid_dep"] is None else v["ask_dep"]-v["bid_dep"]
        venue_delta[ex]={"pressure_delta_6s":dp,"imbalance_delta_6s":di,"depletion_skew":skew}
        if dp is not None:
            venue_valid+=1
            if dp <= -0.04: deteriorating+=1
            if dp >=  0.04: improving+=1

    # Candidate score deliberately fires before the existing +/-0.20 OF
    # confirmation threshold.  This score is NOT claimed to be calibrated.
    cp=snap["combined_pressure"] or 0.0
    ci=snap["combined_imbalance"] or 0.0
    d6=dp6 or 0.0
    d10=dp10 or 0.0
    id6=di6 or 0.0
    convergence=(improving-deteriorating)/max(1,venue_valid)
    early_score=float(np.clip(
        0.25*cp + 0.20*ci + 0.25*d6 + 0.10*d10 + 0.10*id6 + 0.10*convergence,
        -1.0,1.0))

    signal="NONE"
    # Require cross-venue participation to reduce single-venue noise.
    if venue_valid>=2 and deteriorating>=2 and early_score<=-0.055:
        signal="EARLY SELL"
    elif venue_valid>=2 and improving>=2 and early_score>=0.055:
        signal="EARLY BUY"

    onset = signal!="NONE" and signal!=_EARLY_OF_PREV_SIGNAL
    if signal!="NONE":
        _EARLY_OF_PREV_SIGNAL=signal
    elif _EARLY_OF_PREV_SIGNAL!="NONE":
        _EARLY_OF_PREV_SIGNAL="NONE"

    out={
        "signal":signal,"score":early_score,"onset":bool(onset),
        "combined_pressure_delta_2s":dp2,
        "combined_pressure_delta_6s":dp6,
        "combined_pressure_delta_10s":dp10,
        "combined_imbalance_delta_6s":di6,
        "venues_deteriorating_6s":deteriorating,
        "venues_improving_6s":improving,
        "venues_valid":venue_valid,
        "venue_delta":venue_delta,
    }
    _EARLY_OF_LAST=out
    return out



def of_assisted_decision_research(r, mof, early):
    """Secondary research layer; never overwrites the production Decision Signal."""
    base=str(r.get("decision") or "").upper()
    if base not in ("ABOVE","BELOW"):
        return {"base":base or "—","assisted":base or "—","state":"NO BASE","risk":"—","score":0.0,"of_direction":"NEUTRAL"}
    c=(mof or {}).get("combined") or {}
    pressure=_safe_float(c.get("pressure_score")) or 0.0
    buy=int(c.get("buy_count") or 0); sell=int(c.get("sell_count") or 0); n=int(c.get("n") or 0)
    es=str((early or {}).get("signal") or "NONE").upper()
    escore=_safe_float((early or {}).get("score")) or 0.0
    det=int((early or {}).get("venues_deteriorating_6s") or 0)
    imp=int((early or {}).get("venues_improving_6s") or 0)
    score=0.65*pressure+0.35*escore+(0.10*((buy-sell)/max(1,n)) if n else 0.0)
    score=float(np.clip(score,-1.0,1.0))
    sign=1 if base=="ABOVE" else -1
    agreement=sign*score
    ofdir="BUY" if score>=0.08 else ("SELL" if score<=-0.08 else "NEUTRAL")
    state="NEUTRAL"; risk="LOW"; assisted=base
    if agreement>=0.08: state="SUPPORT"
    elif agreement<=-0.08: state="CONFLICT"; risk="MEDIUM"
    strong_cross=(base=="ABOVE" and det>=2) or (base=="BELOW" and imp>=2)
    strong_early=(base=="ABOVE" and es=="EARLY SELL") or (base=="BELOW" and es=="EARLY BUY")
    if agreement<=-0.16 and (strong_cross or strong_early):
        state="STRONG CONFLICT"; risk="HIGH"
        assisted="BELOW" if base=="ABOVE" else "ABOVE"
    return {"base":base,"assisted":assisted,"state":state,"risk":risk,"score":score,"of_direction":ofdir}


def of_micro_bias_research(mof, early):
    """Data-grounded micro-horizon OF classifier; intended mainly for ~10s context."""
    c=(mof or {}).get("combined") or {}
    p=_safe_float(c.get("pressure_score")) or 0.0
    e=_safe_float((early or {}).get("score")) or 0.0
    d10=_safe_float((early or {}).get("combined_pressure_delta_10s")) or 0.0
    # Keep level dominant; acceleration only upgrades/downgrades the warning.
    score=float(np.clip(0.60*p+0.25*d10+0.15*e,-1.0,1.0))
    if score>=0.15: sig="BUY"
    elif score<=-0.15: sig="SELL"
    else: sig="NEUTRAL"
    strength="STRONG" if abs(score)>=0.25 else ("MODERATE" if abs(score)>=0.15 else "WEAK")
    return {"signal":sig,"score":score,"strength":strength,"horizon":"~10s research"}

def mp_of_context_research(r, mof, early):
    """Do not change MP direction; classify whether OF supports or challenges it."""
    mp=move_projection(r)
    micro=of_micro_bias_research(mof,early)
    msign=1 if mp.get("direction")=="UP" else -1
    osign=1 if micro["signal"]=="BUY" else (-1 if micro["signal"]=="SELL" else 0)
    if osign==0:
        relation="NEUTRAL"; risk="NORMAL"
    elif osign==msign:
        relation="SUPPORT"; risk="LOWER"
    else:
        relation="CONFLICT"; risk="HIGHER"
    action=mp.get("action")
    if relation=="CONFLICT":
        if micro["strength"]=="STRONG":
            action="PROTECT / EXIT WATCH"
        elif action=="HOLD":
            action="PROTECT PROFIT"
    return {"relation":relation,"risk":risk,"micro_signal":micro["signal"],
            "micro_score":micro["score"],"action_candidate":action}

def signal_fusion_research(r, mof, early):
    """
    Settlement-risk overlay. Current side stays the Decision anchor.
    Chart, MP and OF only change SUPPORT/RISK classification here.
    """
    ds=decision_signal(r,max(0.0,(r["close_time"]-datetime.now(timezone.utc)).total_seconds()))
    dec=ds["decision"]
    dsign=1 if dec=="ABOVE" else -1
    chart_sign=1 if r.get("prediction")=="ABOVE" else -1
    mp=move_projection(r)
    mp_sign=1 if mp.get("direction")=="UP" else -1
    micro=of_micro_bias_research(mof,early)
    of_sign=1 if micro["signal"]=="BUY" else (-1 if micro["signal"]=="SELL" else 0)

    support=0; conflict=0
    support += int(chart_sign==dsign)
    conflict += int(chart_sign==-dsign)
    support += int(mp_sign==dsign)
    conflict += int(mp_sign==-dsign)
    if of_sign:
        support += int(of_sign==dsign)
        conflict += int(of_sign==-dsign)

    if conflict>=3:
        state="SEVERE CONFLICT"; risk="HIGH"
    elif conflict>=2:
        state="CONFLICT"; risk="MEDIUM-HIGH"
    elif support>=3:
        state="SUPPORTED"; risk="LOW"
    else:
        state="MIXED"; risk="MEDIUM"

    alt=("BELOW" if dec=="ABOVE" else "ABOVE") if state=="SEVERE CONFLICT" else dec
    return {"decision":dec,"state":state,"risk":risk,"support_count":support,
            "conflict_count":conflict,"research_candidate":alt,
            "of_micro":micro["signal"],"of_micro_score":micro["score"]}


def _research_row(r, now, orderflow, multi_exchange=None, multi_orderflow=None):
    sec=max(0.0,(r["close_time"]-now).total_seconds())
    tr=target_reachability(r['distance'],r['atr1m_14'],sec,r.get('prediction'))
    mp=move_projection(r); ds=decision_signal(r,sec)
    of=orderflow or {}
    mx=multi_exchange or {}
    mof=multi_orderflow or {}
    venues=mof.get('venues') or {}
    combined=mof.get('combined') or {}
    early=_of_early_detection(mof,now)
    trof=target_reachability_of_context(r,mof,early)
    oda=of_assisted_decision_research(r,mof,early)
    micro=of_micro_bias_research(mof,early)
    mpof=mp_of_context_research(r,mof,early)
    fusion=signal_fusion_research(r,mof,early)
    return {
      "timestamp_utc":now.isoformat(),"ticker":r.get("ticker"),"seconds_remaining":round(sec,3),
      "brti":r.get("btc"),"target":r.get("target"),"current_side":ds["current_side"],
      "chart_prediction":r.get("prediction"),"chart_raw_p_above":r.get("model_p_above"),
      "mtf_adjustment_pts":r.get("multitf_adjustment"),"chart_final_p_above":r.get("p_above"),
      "decision":ds["decision"],"decision_role":ds["role"],"chart_side_agree":ds["agree"],
      "structure_15m_interpretation":interpret_15m_structure(r),
      "trend_1m":r.get("m1_trend"),"trend_5m":r.get("m5_trend"),"trend_15m":r.get("m15_trend"),
      "bos_1m_up":r.get("m1_bos_up"),"bos_1m_down":r.get("m1_bos_dn"),"bos_5m_up":r.get("m5_bos_up"),"bos_5m_down":r.get("m5_bos_dn"),
      "bos_15m_up":r.get("m15_bos_up"),"bos_15m_down":r.get("m15_bos_dn"),
      "choch_1m_up":r.get("m1_choch_up"),"choch_1m_down":r.get("m1_choch_dn"),"choch_5m_up":r.get("m5_choch_up"),"choch_5m_down":r.get("m5_choch_dn"),
      "choch_15m_up":r.get("m15_choch_up"),"choch_15m_down":r.get("m15_choch_dn"),
      "seq_15m":"HH_LL" if r.get("dev15_hh_then_ll") else ("LL_HH" if r.get("dev15_ll_then_hh") else "NONE"),
      "tr_score":tr.get("tr_score"),
      "tr_raw_cross_estimate":tr.get("raw_cross_estimate"),
      "tr_cross_estimate":tr.get("cross_estimate"),
      "tr_calibrated_cross_estimate":tr.get("calibrated_cross_estimate"),
      "tr_status":tr.get("status"),
      "tr_of_state":trof.get("state"),
      "tr_of_toward_score":trof.get("toward_score"),
      "tr_of_consensus_toward":trof.get("consensus_toward"),
      "mp_direction":mp.get("direction"),"mp_near":mp.get("near"),"mp_base":mp.get("base"),"mp_extended":mp.get("extended"),
      "mp_strength":mp.get("strength"),"mp_exhaustion":mp.get("exhaustion"),"mp_trade_state":mp.get("action"),
      "mp_invalidation":mp.get("invalidation"),
      "mp_thesis_interpretation":interpret_mp_thesis(r,mp),
      "tr_of_directional":interpret_target_of(r,trof).get("direction"),
      "tr_of_strength":interpret_target_of(r,trof).get("strength"),
      "of_early_directional":interpret_of_early(early),
      "of_early_confirmation":of_early_confirmation(early).get("state"),
      "of_early_persistence":of_early_confirmation(early).get("persistence"),
      "of_micro_directional":interpret_of_micro(micro),
      "of_pressure":of.get("pressure"),"of_imbalance_5bp":of.get("imbalance"),"of_ask_depletion":of.get("ask_depletion"),"of_bid_depletion":of.get("bid_depletion"),
      "of_buy_sweep_1bp":of.get("buy_to_sweep_1bps"),"of_buy_sweep_5bp":of.get("buy_to_sweep_5bps"),
      "of_sell_sweep_1bp":of.get("sell_to_sweep_1bps"),"of_sell_sweep_5bp":of.get("sell_to_sweep_5bps"),
      "mx_coinbase":mx.get("coinbase"),"mx_kraken":mx.get("kraken"),"mx_bitstamp":mx.get("bitstamp"),"mx_gemini":mx.get("gemini"),
      "mx_median":mx.get("median"),"mx_mean":mx.get("mean"),"mx_spread":mx.get("spread"),"mx_n":mx.get("n"),
      "mx_brti_minus_median":(float(r.get("btc"))-float(mx.get("median"))) if r.get("btc") is not None and mx.get("median") is not None else None,
      "mx_coinbase_minus_median":(float(mx.get("coinbase"))-float(mx.get("median"))) if mx.get("coinbase") is not None and mx.get("median") is not None else None,
      "mx_kraken_minus_median":(float(mx.get("kraken"))-float(mx.get("median"))) if mx.get("kraken") is not None and mx.get("median") is not None else None,
      "mx_bitstamp_minus_median":(float(mx.get("bitstamp"))-float(mx.get("median"))) if mx.get("bitstamp") is not None and mx.get("median") is not None else None,
      "mx_gemini_minus_median":(float(mx.get("gemini"))-float(mx.get("median"))) if mx.get("gemini") is not None and mx.get("median") is not None else None,
      "mof_coinbase_pressure":(venues.get("coinbase") or {}).get("pressure"),
      "mof_coinbase_pressure_score":(venues.get("coinbase") or {}).get("pressure_score"),
      "mof_coinbase_imbalance":(venues.get("coinbase") or {}).get("imbalance"),
      "mof_coinbase_ask_depletion":(venues.get("coinbase") or {}).get("ask_depletion"),
      "mof_coinbase_bid_depletion":(venues.get("coinbase") or {}).get("bid_depletion"),
      "mof_kraken_pressure":(venues.get("kraken") or {}).get("pressure"),
      "mof_kraken_pressure_score":(venues.get("kraken") or {}).get("pressure_score"),
      "mof_kraken_imbalance":(venues.get("kraken") or {}).get("imbalance"),
      "mof_kraken_ask_depletion":(venues.get("kraken") or {}).get("ask_depletion"),
      "mof_kraken_bid_depletion":(venues.get("kraken") or {}).get("bid_depletion"),
      "mof_bitstamp_pressure":(venues.get("bitstamp") or {}).get("pressure"),
      "mof_bitstamp_pressure_score":(venues.get("bitstamp") or {}).get("pressure_score"),
      "mof_bitstamp_imbalance":(venues.get("bitstamp") or {}).get("imbalance"),
      "mof_bitstamp_ask_depletion":(venues.get("bitstamp") or {}).get("ask_depletion"),
      "mof_bitstamp_bid_depletion":(venues.get("bitstamp") or {}).get("bid_depletion"),
      "mof_gemini_pressure":(venues.get("gemini") or {}).get("pressure"),
      "mof_gemini_pressure_score":(venues.get("gemini") or {}).get("pressure_score"),
      "mof_gemini_imbalance":(venues.get("gemini") or {}).get("imbalance"),
      "mof_gemini_ask_depletion":(venues.get("gemini") or {}).get("ask_depletion"),
      "mof_gemini_bid_depletion":(venues.get("gemini") or {}).get("bid_depletion"),
      "mof_crypto_com_pressure":(venues.get("crypto_com") or {}).get("pressure"),
      "mof_crypto_com_pressure_score":(venues.get("crypto_com") or {}).get("pressure_score"),
      "mof_crypto_com_imbalance":(venues.get("crypto_com") or {}).get("imbalance"),
      "mof_crypto_com_ask_depletion":(venues.get("crypto_com") or {}).get("ask_depletion"),
      "mof_crypto_com_bid_depletion":(venues.get("crypto_com") or {}).get("bid_depletion"),
      "mof_combined_pressure":combined.get("pressure"),
      "mof_combined_pressure_score":combined.get("pressure_score"),
      "mof_combined_imbalance":combined.get("imbalance"),
      "mof_combined_ask_depletion":combined.get("ask_depletion"),
      "mof_combined_bid_depletion":combined.get("bid_depletion"),
      "mof_consensus":combined.get("consensus"),
      "mof_buy_count":combined.get("buy_count"),
      "mof_sell_count":combined.get("sell_count"),
      "mof_neutral_count":combined.get("neutral_count"),
      "mof_n":combined.get("n"),
      "of_early_signal":early.get("signal"),
      "of_early_score":early.get("score"),
      "of_early_onset":early.get("onset"),
      "of_pressure_delta_2s":early.get("combined_pressure_delta_2s"),
      "of_pressure_delta_6s":early.get("combined_pressure_delta_6s"),
      "of_pressure_delta_10s":early.get("combined_pressure_delta_10s"),
      "of_imbalance_delta_6s":early.get("combined_imbalance_delta_6s"),
      "of_venues_deteriorating_6s":early.get("venues_deteriorating_6s"),
      "of_venues_improving_6s":early.get("venues_improving_6s"),
      "of_venues_valid":early.get("venues_valid"),
      "of_cb_pressure_delta_6s":(early.get("venue_delta",{}).get("coinbase") or {}).get("pressure_delta_6s"),
      "of_kr_pressure_delta_6s":(early.get("venue_delta",{}).get("kraken") or {}).get("pressure_delta_6s"),
      "of_bs_pressure_delta_6s":(early.get("venue_delta",{}).get("bitstamp") or {}).get("pressure_delta_6s"),
      "of_gm_pressure_delta_6s":(early.get("venue_delta",{}).get("gemini") or {}).get("pressure_delta_6s"),
      "of_cc_pressure_delta_6s":(early.get("venue_delta",{}).get("crypto_com") or {}).get("pressure_delta_6s"),
      "of_decision_base":oda.get("base"),
      "of_decision_assisted":oda.get("assisted"),
      "of_decision_state":oda.get("state"),
      "of_decision_risk":oda.get("risk"),
      "of_decision_score":oda.get("score"),
      "of_decision_direction":oda.get("of_direction"),
      "of_micro_signal":micro.get("signal"),
      "of_micro_score":micro.get("score"),
      "of_micro_strength":micro.get("strength"),
      "mp_of_relation":mpof.get("relation"),
      "mp_of_risk":mpof.get("risk"),
      "mp_of_action_candidate":mpof.get("action_candidate"),
      "fusion_state":fusion.get("state"),
      "fusion_risk":fusion.get("risk"),
      "fusion_support_count":fusion.get("support_count"),
      "fusion_conflict_count":fusion.get("conflict_count"),
      "fusion_research_candidate":fusion.get("research_candidate")
    }

def log_research_snapshot(r, now, orderflow, multi_exchange=None, multi_orderflow=None):
    """Append at most once per distinct BRTI quote/order-book timestamp."""
    global _RESEARCH_LAST_KEY
    q=str(r.get("quote_time","")); ot=str((orderflow or {}).get("time","")); mt=str((multi_exchange or {}).get("time","")); key=(r.get("ticker"),q,ot,mt)
    if key==_RESEARCH_LAST_KEY: return
    row=_research_row(r,now,orderflow,multi_exchange,multi_orderflow); new=not RESEARCH_LOG_FILE.exists()
    with RESEARCH_LOG_FILE.open("a",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(row.keys()))
        if new: w.writeheader()
        w.writerow(row)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    _RESEARCH_LAST_KEY=key

def build_dashboard(r, now=None, orderflow=None, err=None, of_err=None, mof=None, mof_err=None):
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
    add("KALSHI KXBTC15M — V10.20 DIRECTIONAL DECISION UI RESEARCH")
    add("="*76)
    add(f"DATA LOG: {RESEARCH_LOG_FILE.name}  |  {RESEARCH_LOG_FILE}")
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
    add(f"Raw model:        {100*r['model_p_above']:.1f}% ABOVE")
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
    thesis=interpret_mp_thesis(r,mp)
    add(f"MP thesis:        {_c(thesis,_status_color_word(thesis))}")
    add("")

    early=_EARLY_OF_LAST or {}
    es=early.get("signal","NONE")
    esc="GREEN" if es=="EARLY BUY" else ("RED" if es=="EARLY SELL" else "YELLOW")
    add("OF EARLY DETECTION — RESEARCH ONLY")
    early_confirm=of_early_confirmation(early)
    early_words=early_confirm.get("state","NONE")
    early_color="GREEN" if "BULLISH" in early_words else ("RED" if "BEARISH" in early_words else "YELLOW")
    add(f"Early warning:    {_c(early_words,early_color)}")
    add(f"6s convergence:   {early.get('venues_improving_6s',0)}/4 improving   |   {early.get('venues_deteriorating_6s',0)}/4 deteriorating")
    d6=early.get('combined_pressure_delta_6s')
    d10=early.get('combined_pressure_delta_10s')
    add(f"Pressure change:  6s {'—' if d6 is None else f'{d6:+.3f}'}   |   10s {'—' if d10 is None else f'{d10:+.3f}'}")
    add("Warning only; does not alter Chart Signal, Decision, TR, or MP.")
    add("")

    oda=of_assisted_decision_research(r,mof,early)
    add("OF-ASSISTED DECISION — SECONDARY RESEARCH")
    state=oda.get("state","NEUTRAL")
    stc="RED" if state=="STRONG CONFLICT" else ("YELLOW" if state=="CONFLICT" else ("GREEN" if state=="SUPPORT" else "WHITE"))
    add(f"Primary Decision: {oda.get('base','—')}   |   OF: {oda.get('of_direction','NEUTRAL')}")
    add(f"OF relationship:  {_c(state,stc)}   |   Risk {oda.get('risk','—')}")
    if state=="STRONG CONFLICT":
        add(f"Research candidate: {_c(oda.get('assisted','—'),'YELLOW')}  (not an automatic override)")
    add("Primary Decision remains unchanged; lower-priority research layer.")
    add("")

    micro=of_micro_bias_research(mof,early)
    mpof=mp_of_context_research(r,mof,early)
    fusion=signal_fusion_research(r,mof,early)
    add("MAJOR RESEARCH FUSION")
    mc="GREEN" if micro["signal"]=="BUY" else ("RED" if micro["signal"]=="SELL" else "YELLOW")
    micro_words=interpret_of_micro(micro)
    mc="GREEN" if "BULLISH" in micro_words else ("RED" if "BEARISH" in micro_words else "YELLOW")
    add(f"OF micro (~10s):  {_c(micro_words,mc)}")
    rc="GREEN" if mpof["relation"]=="SUPPORT" else ("RED" if mpof["relation"]=="CONFLICT" else "YELLOW")
    add(f"MP / OF:          {_c(mpof['relation'],rc)}   |   candidate action {mpof['action_candidate']}")
    fc="GREEN" if fusion["state"]=="SUPPORTED" else ("RED" if "CONFLICT" in fusion["state"] else "YELLOW")
    add(f"Decision fusion:  {_c(fusion['state'],fc)}   |   Risk {fusion['risk']}")
    if fusion["state"]=="SEVERE CONFLICT":
        add(f"Alt research side:{_c(fusion['research_candidate'],'YELLOW')}   (warning, not automatic override)")
    add("Chart remains pure; Decision is current-side anchored; OF is micro/risk context.")
    add("")

    add("MULTI-EXCHANGE ORDER FLOW")
    add("Exchange     Pressure   Imbalance   Ask dep   Bid dep")
    venues=(mof or {}).get("venues") or {}
    for ex,label in (("coinbase","Coinbase"),("kraken","Kraken"),("bitstamp","Bitstamp"),("gemini","Gemini"),("crypto_com","Crypto.com")):
        v=venues.get(ex) or {}
        pr=v.get("pressure","WAIT")
        pc="GREEN" if pr=="BUY" else ("RED" if pr=="SELL" else "YELLOW")
        imb=v.get("imbalance"); ad=v.get("ask_depletion"); bd=v.get("bid_depletion")
        imbtxt="—" if imb is None else f"{100*imb:+.1f}%"
        adtxt="—" if ad is None else f"{100*ad:.1f}%"
        bdtxt="—" if bd is None else f"{100*bd:.1f}%"
        add(f"{label:<12} {_c(pr,pc):<18} {imbtxt:>9}   {adtxt:>7}   {bdtxt:>7}")
    comb=(mof or {}).get("combined") or {}
    pr=comb.get("pressure","NEUTRAL"); pc="GREEN" if pr=="BUY" else ("RED" if pr=="SELL" else "YELLOW")
    add("-"*76)
    add(f"COMBINED:         {_c(pr,pc)}   |   Imbalance {100*comb.get('imbalance',0.0):+.1f}%   |   Ask/Bid depletion {100*comb.get('ask_depletion',0.0):.1f}% / {100*comb.get('bid_depletion',0.0):.1f}%")
    add(f"CONSENSUS:        {_c(comb.get('consensus','0/0 NEUTRAL'),pc)}")
    if mof_err:
        bad=", ".join(sorted(mof_err.keys()))
        add(f"Feed issues:      {bad}")
    add("Order-flow research only; does not alter Chart Signal, Decision, TR, or MP.")
    add("")

    tr=target_reachability(r['distance'],r['atr1m_14'],sec,r.get('prediction'))
    trof=target_reachability_of_context(r,mof,early)
    add("TARGET REACHABILITY (TR) — V10.20 DIRECTIONAL DISPLAY")
    add(f"Status:           {_c(tr['status'],_status_color_word(tr['status']))}")
    add(f"Volatility travel:${tr['travel_budget']:,.2f}   |   Calibrated cross {100*tr['cross_estimate']:.1f}%")
    add(f"Raw model cross:  {100*tr['raw_cross_estimate']:.1f}%")
    tr_of_words=interpret_target_of(r,trof)
    tr_of_color="GREEN" if "BULLISH" in tr_of_words["direction"] else ("RED" if "BEARISH" in tr_of_words["direction"] else "YELLOW")
    add(f"OF target pressure:{_c(tr_of_words['display'],tr_of_color)}")
    add("OF remains context only; it does not alter calibrated TR probability.")
    if tr.get('role'):
        add(f"Role:             {_c(tr['role'],_status_color_word(tr['role']))}")
    add("")

    add("STRUCTURE")
    add(f"Trend 1m/5m/15m:  {_c(tname(r['m1_trend']),_status_color_word(tname(r['m1_trend'])))} / {_c(tname(r['m5_trend']),_status_color_word(tname(r['m5_trend'])))} / {_c(tname(r['m15_trend']),_status_color_word(tname(r['m15_trend'])))}")
    add(f"Protected H/L:    ${r['protected_high']:,.2f} / ${r['protected_low']:,.2f}")
    structure_words=interpret_15m_structure(r)
    add(f"15m structure:    {_c(structure_words,_status_color_word(structure_words))}")
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


# ---------------------------------------------------------------------------
# V10.26 FAST-LIVE / DYNAMIC-MP-LIFECYCLE / OF-PRICE-RESPONSE / DEVELOPING-MOVE / FLIP RESEARCH
# ---------------------------------------------------------------------------
_move_projection_v1023 = move_projection
_research_row_v1023 = _research_row
_OF_RESPONSE_TRACKER={}
_FLIP_TRACKER={}


def _tick_value_near(ticks, when, tolerance=1.2):
    if ticks is None or not len(ticks): return None
    x=ticks.copy(); x['time']=pd.to_datetime(x['time'],utc=True)
    delta=(x['time']-pd.Timestamp(when)).abs()
    i=delta.idxmin()
    if delta.loc[i].total_seconds()>tolerance: return None
    return float(x.loc[i,'value'])


def _attach_micro_price_features(r, ticks):
    qt=pd.to_datetime(r.get('quote_time'),utc=True,errors='coerce')
    if pd.isna(qt): return r
    px=float(r['btc'])
    for s in (2,5,10):
        old=_tick_value_near(ticks,qt-pd.Timedelta(seconds=s),tolerance=1.5)
        d=None if old is None else px-old
        r[f'micro_delta_{s}s']=d
        r[f'micro_delta_{s}s_bps']=None if d is None else 10000.0*d/max(px,1e-9)
    return r


def move_projection(r):
    """V10.26 keeps structural MP, developing-move detection, and dynamic projection lifecycle."""
    mp=_move_projection_v1023(r)
    structural=mp.get('direction','UP')
    b5=_safe_float(r.get('micro_delta_5s_bps')); b10=_safe_float(r.get('micro_delta_10s_bps'))
    active=0; evidence='QUIET'
    if b5 is not None and abs(b5)>=0.50:
        active=1 if b5>0 else -1; evidence='5s BRTI MOVE'
    elif b10 is not None and abs(b10)>=0.75:
        active=1 if b10>0 else -1; evidence='10s BRTI MOVE'
    structural_sign=1 if structural=='UP' else -1
    if active==0:
        display=structural; state='STRUCTURAL'
    elif active==structural_sign:
        display=structural+' ACTIVE'; state='CONTINUATION ACTIVE'
    else:
        display=('UP' if active>0 else 'DOWN')+' DEVELOPING'; state='OPPOSING MOVE DEVELOPING'
        # Do not flip the structural projection on micro movement alone, but do make the trade state react.
        if mp.get('action')=='HOLD': mp['action']='PROTECT PROFIT'
    mp['structural_direction']=structural
    mp['display_direction']=display
    mp['developing_state']=state
    mp['micro_evidence']=evidence
    mp['micro_5s_bps']=b5; mp['micro_10s_bps']=b10
    return mp



def validated_orderflow_research(mof):
    """Forward-validated OF research composite.

    V10.23 chronological testing favored Crypto.com as the most stable standalone
    venue. A conservative 60% Crypto.com + 40% Coinbase composite was positive
    across all tested holdout horizons. This is context only; it never silently
    overrides Chart or Decision.
    """
    venues=(mof or {}).get('venues') or {}
    cc=_safe_float((venues.get('crypto_com') or {}).get('pressure_score'))
    cb=_safe_float((venues.get('coinbase') or {}).get('pressure_score'))
    raw_combined=_safe_float(((mof or {}).get('combined') or {}).get('pressure_score'))
    if cc is not None and cb is not None:
        score=0.60*cc+0.40*cb; basis='60% CRYPTO.COM + 40% COINBASE'
    elif cc is not None:
        score=cc; basis='CRYPTO.COM ONLY'
    elif raw_combined is not None:
        score=raw_combined; basis='5-VENUE FALLBACK'
    else:
        score=0.0; basis='NO VALID VENUE'
    signal='BUY' if score>=0.15 else ('SELL' if score<=-0.15 else 'NEUTRAL')
    direction='BULLISH' if signal=='BUY' else ('BEARISH' if signal=='SELL' else 'NEUTRAL')
    return {'score':float(score),'signal':signal,'direction':direction,'basis':basis,
            'threshold':0.15,'role':'FORWARD-VALIDATED OF CONTEXT — NO DECISION OVERRIDE'}

def of_price_response_research(r, mof, now=None, score_override=None):
    """Describe whether BRTI is actually responding to current OF pressure; no settlement override."""
    now=now or datetime.now(timezone.utc); ticker=str(r.get('ticker','UNKNOWN')); px=float(r.get('btc',0.0))
    c=(mof or {}).get('combined') or {}; score=_safe_float(score_override)
    if score is None:
        score=_safe_float(validated_orderflow_research(mof).get('score'))
    score=score or 0.0
    sign=1 if score>=0.15 else (-1 if score<=-0.15 else 0)
    st=_OF_RESPONSE_TRACKER.get(ticker)
    if sign==0:
        _OF_RESPONSE_TRACKER[ticker]={'sign':0,'ts':now.timestamp(),'px':px}
        return {'state':'NEUTRAL','direction':'NEUTRAL','elapsed_s':0.0,'response_bps':0.0,'pressure_score':score,'role':'PRICE RESPONSE TO OF'}
    if st is None or st.get('sign')!=sign:
        st={'sign':sign,'ts':now.timestamp(),'px':px}; _OF_RESPONSE_TRACKER[ticker]=st
    elapsed=max(0.0,now.timestamp()-st['ts']); response_bps=sign*(px-st['px'])/max(px,1e-9)*10000.0
    direction='BULLISH' if sign>0 else 'BEARISH'
    if elapsed<2.0: state=f'{direction} PRESSURE — DEVELOPING'
    elif response_bps>=0.50: state=f'{direction} PRESSURE — PRICE CONFIRMED'
    elif response_bps<=-0.50: state=f'{direction} PRESSURE — ABSORBED / FAILED'
    else: state=f'{direction} PRESSURE — PENDING'
    return {'state':state,'direction':direction,'elapsed_s':elapsed,'response_bps':response_bps,'pressure_score':score,'role':'PRICE RESPONSE TO OF'}



def mp_of_price_confirmation(mp, of_response):
    """Connect developing MP to actual price-confirmed OF without flipping structural MP."""
    mp=mp or {}; o=of_response or {}
    state=str(o.get('state') or 'NEUTRAL')
    odir=str(o.get('direction') or 'NEUTRAL')
    structural=str(mp.get('structural_direction') or mp.get('direction') or 'UP')
    structural_bull=structural=='UP'
    price_confirmed='PRICE CONFIRMED' in state
    failed='ABSORBED / FAILED' in state
    if price_confirmed:
        same=(odir=='BULLISH' and structural_bull) or (odir=='BEARISH' and not structural_bull)
        if same:
            relation='CONTINUATION CONFIRMED BY OF + PRICE'
            action=mp.get('action')
        else:
            relation='OPPOSING MOVE CONFIRMED BY OF + PRICE'
            action='PROTECT PROFIT' if mp.get('action')=='HOLD' else mp.get('action')
    elif failed:
        relation='OF PRESSURE FAILED — PRICE RESISTING'
        action=mp.get('action')
    elif odir!='NEUTRAL':
        relation='OF PRESSURE AWAITING PRICE'
        action=mp.get('action')
    else:
        relation='NEUTRAL'
        action=mp.get('action')
    return {'state':relation,'action_candidate':action,'price_confirmed':price_confirmed,
            'of_direction':odir,'role':'MP DEVELOPING-MOVE CONFIRMATION'}

def flip_reachthrough_research(r, now=None):
    """FLIP = after target approach/reach, does BRTI cross through at least once?

    Settlement hold is irrelevant. The $10 band is only an ARMING zone derived
    from historical sampling. At 5Hz, an actual sign change confirms the cross.
    """
    now=now or datetime.now(timezone.utc)
    ticker=str(r.get('ticker','UNKNOWN')); dist=float(r.get('distance',0.0))
    sign=1 if dist>=0 else -1
    st=_FLIP_TRACKER.get(ticker)
    if st is None:
        st={'initial_sign':sign,'armed':False,'reached':False,'crossed':False,
            'arm_ts':None,'reach_ts':None,'min_abs_distance':abs(dist)}
        _FLIP_TRACKER.clear(); _FLIP_TRACKER[ticker]=st
    st['min_abs_distance']=min(float(st.get('min_abs_distance',abs(dist))),abs(dist))
    if not st['armed'] and abs(dist)<=10.0:
        st['armed']=True; st['arm_ts']=now.timestamp()
    # <=$1 is a practical same-side "reached" proxy; a sign change is definitive.
    if not st['reached'] and abs(dist)<=1.0:
        st['reached']=True; st['reach_ts']=now.timestamp()
    if sign!=st['initial_sign']:
        st['armed']=True; st['reached']=True; st['crossed']=True
        if st.get('reach_ts') is None: st['reach_ts']=now.timestamp()
    if st['crossed']:
        state='FLIPPED — CROSS THROUGH CONFIRMED'
    elif st['reached']:
        state='TARGET REACHED — FLIP WATCH'
    elif st['armed']:
        state='NEAR TARGET — FLIP ARMED'
    else:
        state='WAITING FOR TARGET'
    return {'state':state,'armed':bool(st['armed']),'reached':bool(st['reached']),
            'crossed':bool(st['crossed']),
            'initial_side':'ABOVE' if st['initial_sign']>0 else 'BELOW',
            'min_abs_distance':float(st['min_abs_distance']),
            'seconds_since_arm':None if st.get('arm_ts') is None else max(0.0,now.timestamp()-st['arm_ts']),
            'historical_10usd_holdout_context':'12/12 crossed after entering $10 zone in V10.23 holdout',
            'definition':'reach/approach target then cross through at least once; settlement hold not required'}

class LiveEngine(LiveEngine):
    """V10.25: 5Hz BRTI WebSocket primary, REST recovery, proactive next-contract prefetch."""
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw)
        self.next_market=None; self.last_market_discovery=0.0
        self.ws_latest=None; self.ws_status='STARTING'; self.ws_error=None; self.ws_last_received_monotonic=0.0
        self.last_rollover_info={'mode':'INITIAL','lag_s':None,'switched_at':None,'ticker':None}
        self.last_processed_ws_ts=None; self.last_rest_fallback=0.0; self.ws_thread=None

    def _switch_market(self,nxt):
        previous=self.market.get('ticker') if self.market else self.last_ticker
        was_prefetched=bool(self.next_market and self.next_market.get('ticker')==nxt.get('ticker'))
        self.market=nxt; self.waiting_for_next=False; self.next_market=None
        if previous!=nxt.get('ticker'):
            now=datetime.now(timezone.utc)
            ref=nxt.get('open_time')
            lag=None if ref is None else max(0.0,(now-ref).total_seconds())
            self.last_rollover_info={'mode':'PREFETCH' if was_prefetched else 'DISCOVERY',
                                     'lag_s':lag,'switched_at':now.isoformat(),'ticker':nxt.get('ticker')}
            self.last_ticker=nxt.get('ticker')
            _MP_TRACKER.clear(); _FLIP_TRACKER.clear(); _OF_RESPONSE_TRACKER.clear()

    def _ensure_market(self):
        now=datetime.now(timezone.utc)
        if self.market is None:
            self._switch_market(fetch_active_kalshi_market(now)); return
        remaining=(self.market['close_time']-now).total_seconds()
        # Prefetch up to 3 minutes early; rate-limit discovery to once per 5s.
        if remaining<=180 and self.next_market is None and time.monotonic()-self.last_market_discovery>=5:
            self.last_market_discovery=time.monotonic()
            try: self.next_market=fetch_next_kalshi_market(self.market['close_time'],now)
            except Exception: pass
        if remaining<=0:
            if self.next_market and self.next_market['close_time']>now and (self.next_market.get('open_time') is None or self.next_market['open_time']<=now+timedelta(seconds=2)):
                self._switch_market(self.next_market); return
            if time.monotonic()-self.last_market_discovery>=0.8:
                self.last_market_discovery=time.monotonic()
                try:
                    self._switch_market(fetch_active_kalshi_market(now)); return
                except Exception:
                    pass
            self.waiting_for_next=True
            raise RuntimeError('WAITING FOR NEXT KXBTC15M CONTRACT — rapid rollover retry active')

    def _append_live_tick(self, value, ts):
        row=pd.DataFrame([{'time':pd.to_datetime(ts,utc=True),'value':float(value)}])
        if self.ticks is None: self.ticks=row
        else:
            self.ticks=(pd.concat([self.ticks,row],ignore_index=True).drop_duplicates('time',keep='last').sort_values('time'))
            cutoff=pd.Timestamp(datetime.now(timezone.utc)-timedelta(hours=7)); self.ticks=self.ticks[self.ticks.time>=cutoff].reset_index(drop=True)
        self.candles=brti_ticks_to_1m(self.ticks)
        r=predict_from_data(self.market,self.candles,float(value),'BRTI 5Hz WebSocket',pd.to_datetime(ts,utc=True))
        r=_attach_micro_price_features(r,self.ticks)
        r['brti_feed']='WS_5HZ'; r['brti_received_monotonic']=self.ws_last_received_monotonic
        r['rollover_mode']=self.last_rollover_info.get('mode'); r['rollover_lag_s']=self.last_rollover_info.get('lag_s')
        r['next_prefetched']=bool(self.next_market); r['next_ticker']=(self.next_market or {}).get('ticker')
        return r

    def brti_websocket_worker(self):
        if websocket is None:
            self.ws_status='UNAVAILABLE'; self.ws_error='websocket-client not installed'; return
        while self.running:
            ws=None
            try:
                headers=_auth_headers_full_path('GET',KALSHI_WS_PATH)
                ws=websocket.create_connection(KALSHI_WS_URL,header=[f'{k}: {v}' for k,v in headers.items()],timeout=8,origin=None)
                ws.send(json.dumps({'id':1,'cmd':'subscribe','params':{'channels':['cfbenchmarks_value_5hz'],'index_ids':['BRTI']}}))
                self.ws_status='LIVE'; self.ws_error=None
                while self.running:
                    raw=ws.recv(); msg=json.loads(raw)
                    if msg.get('type')!='cfbenchmarks_value_5hz': continue
                    m=msg.get('msg') or {}
                    if m.get('index_id')!='BRTI': continue
                    val=float(m.get('value_usd')); ts_ms=float(m.get('source_ts_ms'))
                    ts=pd.to_datetime(ts_ms,unit='ms',utc=True)
                    with self.lock:
                        self.ws_latest={'value':val,'time':ts,'received_at':m.get('received_at')}
                        self.ws_last_received_monotonic=time.monotonic(); self.ws_status='LIVE'; self.ws_error=None
            except Exception as e:
                self.ws_status='RECONNECTING'; self.ws_error=str(e)
                time.sleep(1.0)
            finally:
                try:
                    if ws: ws.close()
                except Exception: pass

    def worker(self):
        try:
            self._initialize_brti()
        except Exception as e:
            if not self.allow_coinbase_fallback:
                self._set(error='Initialization failed: '+str(e)); return
        self.ws_thread=threading.Thread(target=self.brti_websocket_worker,daemon=True); self.ws_thread.start()
        while self.running:
            try:
                self._ensure_market()
                latest=None
                with self.lock:
                    if self.ws_latest: latest=dict(self.ws_latest)
                if latest is not None:
                    key=str(latest['time'])
                    if key!=self.last_processed_ws_ts:
                        self.last_processed_ws_ts=key
                        r=self._append_live_tick(latest['value'],latest['time']); self._set(result=r,error=None)
                stale=(time.monotonic()-self.ws_last_received_monotonic) if self.ws_last_received_monotonic else 999
                if stale>2.5 and time.monotonic()-self.last_rest_fallback>=1.0:
                    self.last_rest_fallback=time.monotonic()
                    try:
                        r=self._refresh_brti(); r=_attach_micro_price_features(r,self.ticks); r['brti_feed']='REST FALLBACK'; r['rollover_mode']=self.last_rollover_info.get('mode'); r['rollover_lag_s']=self.last_rollover_info.get('lag_s'); r['next_prefetched']=bool(self.next_market); r['next_ticker']=(self.next_market or {}).get('ticker'); self._set(result=r,error=None)
                    except Exception as e:
                        self._set(error='BRTI WS stale; REST fallback error: '+str(e))
            except Exception as e:
                self._set(error=str(e))
            time.sleep(0.20)

    def feed_status(self):
        with self.lock:
            latest=dict(self.ws_latest) if self.ws_latest else None
        age=None
        if latest and latest.get('time') is not None:
            age=max(0.0,(datetime.now(timezone.utc)-pd.to_datetime(latest['time'],utc=True).to_pydatetime()).total_seconds())
        return {'mode':self.ws_status,'age_s':age,'error':self.ws_error,'next_ticker':(self.next_market or {}).get('ticker'),'next_prefetched':bool(self.next_market)}


def _research_row(r, now, orderflow, multi_exchange=None, multi_orderflow=None):
    row=_research_row_v1023(r,now,orderflow,multi_exchange,multi_orderflow)
    mof=multi_orderflow or {}
    vof=validated_orderflow_research(mof)
    opr=of_price_response_research(r,mof,now,vof.get('score')); fl=flip_reachthrough_research(r,now); mp=move_projection(r)
    mpl=_mp_progress_state(r,mp); mplink=mp_of_price_confirmation(mp,opr)
    qt=pd.to_datetime(r.get('quote_time'),utc=True,errors='coerce')
    quote_age=None if pd.isna(qt) else max(0.0,(pd.Timestamp(now)-qt).total_seconds())
    row.update({
      'research_version':'V10.27',
      'brti_quote_age_s':quote_age,'rollover_mode':r.get('rollover_mode'),'rollover_lag_s':r.get('rollover_lag_s'),
      'next_prefetched':r.get('next_prefetched'),'next_ticker':r.get('next_ticker'),
      'of_validated_signal':vof.get('signal'),'of_validated_direction':vof.get('direction'),
      'of_validated_score':vof.get('score'),'of_validated_basis':vof.get('basis'),
      'mp_of_price_state':mplink.get('state'),'mp_of_price_action_candidate':mplink.get('action_candidate'),
      'brti_feed':r.get('brti_feed'),'micro_delta_2s_bps':r.get('micro_delta_2s_bps'),'micro_delta_5s_bps':r.get('micro_delta_5s_bps'),'micro_delta_10s_bps':r.get('micro_delta_10s_bps'),
      'mp_structural_direction':mp.get('structural_direction'),'mp_display_direction':mp.get('display_direction'),'mp_developing_state':mp.get('developing_state'),
      'mp_projection_status':mpl.get('projection_status'),'mp_projection_leg':mpl.get('leg_id'),'mp_projection_completed_legs':mpl.get('completed_legs'),'mp_projection_progress_pct':mpl.get('progress_pct'),
      'mp_projection_anchor':mpl.get('anchor'),'mp_projection_near':mpl.get('near'),'mp_projection_base':mpl.get('base'),'mp_projection_extended':mpl.get('extended'),
      'of_price_response_state':opr.get('state'),'of_price_response_bps':opr.get('response_bps'),'of_price_response_elapsed_s':opr.get('elapsed_s'),
      'flip_state':fl.get('state'),'flip_armed':fl.get('armed'),'flip_reached':fl.get('reached'),'flip_crossed':fl.get('crossed'),'flip_initial_side':fl.get('initial_side'),'flip_min_abs_distance':fl.get('min_abs_distance'),'flip_seconds_since_arm':fl.get('seconds_since_arm')
    })
    return row

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
    th_mx=threading.Thread(target=eng.multi_exchange_worker,daemon=True); th_mx.start()
    _init_live_display()
    try:
        while True:
            r,err=eng.snapshot()
            of,of_err=eng.orderflow_snapshot()
            mx,mx_err=eng.multi_exchange_snapshot()
            mof,mof_err=eng.multi_orderflow_snapshot()
            if r is None:
                if err and "No currently-open KXBTC15M contract found" in str(err):
                    frame="V10.27 — WAITING FOR NEXT KXBTC15M CONTRACT...\nAuto-roll is active; retrying automatically."
                else:
                    frame="V10.27 initializing BRTI history, 5Hz feed, chart model, and order flow...\nCountdown will refresh every second once the active contract is loaded."
                    if err: frame += "\nERROR: " + str(err)
            else:
                _now=datetime.now(timezone.utc)
                # V10.12 dedicated collector: always log in watch mode,
                # including --json sessions.
                try:
                    log_research_snapshot(r,_now,of,mx,mof)
                except Exception as log_exc:
                    # Keep the live predictor running, but surface the logger failure.
                    if err:
                        err = f"{err} | LOGGER ERROR: {log_exc}"
                    else:
                        err = f"LOGGER ERROR: {log_exc}"
                if args.json:
                    out=dict(r); out["seconds_left_live"]=(r["close_time"]-_now).total_seconds()
                    out["target_reachability"]=target_reachability(r["distance"],r["atr1m_14"],out["seconds_left_live"],r.get("prediction"))
                    _mp=move_projection(r)
                    _mp["progress"]=_mp_progress_state(r,_mp)
                    out["move_projection"]=_mp
                    out["research_log_file"]=str(RESEARCH_LOG_FILE)
                    out["multi_exchange_research"]=mx
                    frame=json.dumps(out,indent=2,default=str)
                else:
                    frame=build_dashboard(r,_now,of,err,of_err,mof,mof_err)
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
