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


# V2.2 multi-exchange public BTC-USD display feeds.
# No logging. No effect on Chart Signal, Decision, TR, MP, or Coinbase Level-2 OF.
MULTI_EXCHANGE_URLS={
    "coinbase":"https://api.exchange.coinbase.com/products/BTC-USD/ticker",
    "kraken":"https://api.kraken.com/0/public/Ticker?pair=XBTUSD",
    "bitstamp":"https://www.bitstamp.net/api/v2/ticker/btcusd/",
    "gemini":"https://api.gemini.com/v1/pubticker/btcusd",
}
MX_LOCK=threading.Lock()
MX_LATEST={}
MX_ERROR=None
MX_RUNNING=True

def _mx_float(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None

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
    global MX_LATEST,MX_ERROR,MX_RUNNING
    while MX_RUNNING:
        try:
            cur=fetch_multi_exchange_prices()
            with MX_LOCK:
                MX_LATEST=cur
                MX_ERROR=None
        except Exception as e:
            with MX_LOCK:
                MX_ERROR=str(e)
        time.sleep(2.0)

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
    mp["progress"] = core._mp_progress_state(r, mp)
    ds = core.decision_signal(r, sec)
    candles = engine.candles
    spark = []
    candle_data = []
    if candles is not None and len(candles):
        c = candles.tail(90)
        spark = [{"t":clean(t), "v":clean(v)} for t, v in zip(c["time"], c["close"])]
        required = {"time", "open", "high", "low", "close"}
        if required.issubset(c.columns):
            candle_data = [
                {
                    "t": clean(row["time"]),
                    "o": clean(row["open"]),
                    "h": clean(row["high"]),
                    "l": clean(row["low"]),
                    "c": clean(row["close"]),
                }
                for _, row in c.iterrows()
            ]
    with MX_LOCK:
        mx=dict(MX_LATEST) if MX_LATEST else {}
        mx_err=MX_ERROR
    if mx.get("median") is not None and r.get("btc") is not None:
        mx["brti_minus_median"]=float(r.get("btc"))-float(mx["median"])
    else:
        mx["brti_minus_median"]=None
    mx["error"]=mx_err
    return clean({
        "status":"ok",
        "server_time":now,
        "market":{
            "ticker":r.get("ticker"), "target":r.get("target"), "brti":r.get("btc"),
            "distance":r.get("distance"), "close_time":r.get("close_time"), "seconds_left":sec,
            "source":r.get("source"), "quote_time":r.get("quote_time")
        },
        "chart":{
            "prediction":r.get("prediction"), "p_above":r.get("p_above"), "p_below":r.get("p_below"),
            "raw_p_above":r.get("model_p_above"), "mtf_adjustment":r.get("multitf_adjustment"),
            "checkpoint":r.get("checkpoint_model"), "model_kind":r.get("model_kind"), "model_family":r.get("model_family")
        },
        "decision":ds,
        "reachability":tr,
        "move_projection":mp,
        "orderflow":of,
        "structure":{
            "m1_trend":r.get("m1_trend"), "m5_trend":r.get("m5_trend"), "m15_trend":r.get("m15_trend"),
            "protected_high":r.get("protected_high"), "protected_low":r.get("protected_low"),
            "dev15_hh_then_ll":r.get("dev15_hh_then_ll"), "dev15_ll_then_hh":r.get("dev15_ll_then_hh"),
            "m15_bos_up":r.get("m15_bos_up"), "m15_bos_dn":r.get("m15_bos_dn"),
            "m15_choch_up":r.get("m15_choch_up"), "m15_choch_dn":r.get("m15_choch_dn"),
            "atr1m_14":r.get("atr1m_14"),
        },
        "errors":{"engine":err, "orderflow":of_err},
        "sparkline":spark,
        "candles":candle_data,
        "multi_exchange":mx,
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

app = FastAPI(title="BTC15M V10.13 Multi-Exchange Web", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).with_name("static")), name="static")

@app.get("/", response_class=HTMLResponse)
def home():
    return Path(__file__).with_name("static").joinpath("index.html").read_text(encoding="utf-8")

@app.get("/api/state")
def state():
    return JSONResponse(build_state())

@app.get("/api/health")
def health():
    r = build_state()
    return {"ok": r.get("status") == "ok", "status": r.get("status"), "error": r.get("error") or r.get("errors",{}).get("engine")}
