from pathlib import Path
import joblib, numpy as np, pandas as pd
_HERE=Path(__file__).resolve().parent
_BUNDLE=None
def _bundle():
    global _BUNDLE
    if _BUNDLE is None: _BUNDLE=joblib.load(_HERE/"settlement_research_bundle.joblib")
    return _BUNDLE
def _tick_near(ticks, now, sec):
    if ticks is None or len(ticks)==0: return None
    q=ticks.copy(); q["time"]=pd.to_datetime(q["time"],utc=True,errors="coerce"); q["value"]=pd.to_numeric(q["value"],errors="coerce")
    q=q.dropna().sort_values("time"); z=q[q.time<=pd.Timestamp(now)-pd.Timedelta(seconds=sec)]
    return None if z.empty else float(z.iloc[-1].value)
def _range_features(ticks, now, px, target):
    out={}
    if ticks is None or len(ticks)==0:
        for m in (1,5,15):
            for k in ("range","pos","target_pos","target_inside","dist_hi","dist_lo","slope","width"): out[f"{k}_{m}m"]=np.nan
        out["channel_alignment"]=0.0; return out
    q=ticks.copy(); q["time"]=pd.to_datetime(q["time"],utc=True,errors="coerce"); q["value"]=pd.to_numeric(q["value"],errors="coerce")
    q=q.dropna().sort_values("time"); q=q[q.time<=pd.Timestamp(now)]
    c=q.set_index("time")["value"].resample("1min").ohlc().dropna(); align=0.0
    for m in (1,5,15):
        w=c.tail(m)
        if w.empty: hi=lo=px; slope=width=0.0
        else:
            hi=float(w.high.max()); lo=float(w.low.min()); y=w.close.to_numpy(float)
            if len(y)>=2:
                x=np.arange(len(y)); co=np.polyfit(x,y,1); fit=co[0]*x+co[1]; slope=float(co[0]); width=float(np.max(np.abs(y-fit)))
            else: slope=width=0.0
        rng=hi-lo; out[f"range_{m}m"]=rng; out[f"pos_{m}m"]=np.nan if rng<=0 else (px-lo)/rng
        out[f"target_pos_{m}m"]=np.nan if rng<=0 else (target-lo)/rng; out[f"target_inside_{m}m"]=float(lo<=target<=hi)
        out[f"dist_hi_{m}m"]=hi-px; out[f"dist_lo_{m}m"]=px-lo; out[f"slope_{m}m"]=slope; out[f"width_{m}m"]=width; align+=float(np.sign(slope))
    out["channel_alignment"]=align; return out
def settlement_state(r, seconds_left, ticks, now=None):
    """Research-only final-winner forecast, separate from dynamic Decision."""
    b=_bundle(); now=pd.Timestamp(now or pd.Timestamp.now(tz="UTC")); px=float(r.get("btc") or r.get("brti") or 0.0); target=float(r.get("target") or 0.0); sec=max(0.0,float(seconds_left or 0.0))
    vals={"seconds_remaining":sec,"distance":px-target,"abs_distance":abs(px-target)}
    for h in (2,5,10):
        old=_tick_near(ticks,now,h); vals[f"micro_delta_{h}s_bps"]=0.0 if old in (None,0) else 10000.0*(px/old-1.0)
    vals.update(_range_features(ticks,now,px,target)); cp=min(b["checkpoints"],key=lambda x:abs(float(x)-sec))
    X=pd.DataFrame([{k:vals.get(k,np.nan) for k in b["features"]}]); p=float(b["models"][cp].predict_proba(X)[0,1]); side="ABOVE" if p>=.5 else "BELOW"; conf=abs(p-.5)*2.0
    return {"prediction":side,"p_above":p,"p_below":1-p,"confidence":conf,"checkpoint_s":int(cp),"seconds_remaining":sec,
            "qualified_70_research":bool(conf>=0.20),"role":"RESEARCH ONLY — settlement forecast; no Decision authority",
            "model_version":b["version"],"range_context":{str(m):{k:vals.get(f"{k}_{m}m") for k in ("range","pos","target_pos","target_inside","slope","width")} for m in (1,5,15)}}
