from pathlib import Path
import math, numpy as np, pandas as pd

# Settlement 2.0: terminal-distribution core selected on V10.31 historical data.
# GT5 overlay is a current-era discovery adjustment and remains explicitly logged.
_VERSION="SETTLEMENT_2_1_CORE_CHALLENGER_V1"
_SIGMA_WINDOW_S=300.0
_SIGMA_FLOOR=1.0          # USD / sqrt(second)
_GT5_LOGIT_WEIGHT=0.0
_LEGACY_GT5_LOGIT_WEIGHT=0.75

def _clean_ticks(ticks, now):
    if ticks is None or len(ticks)==0: return pd.DataFrame(columns=["time","value"])
    q=ticks.copy()
    q["time"]=pd.to_datetime(q["time"],utc=True,errors="coerce")
    q["value"]=pd.to_numeric(q["value"],errors="coerce")
    q=q.dropna(subset=["time","value"]).sort_values("time")
    return q[q.time<=pd.Timestamp(now)]

def _sigma_per_sqrt_second(ticks, now):
    q=_clean_ticks(ticks,now)
    if q.empty: return _SIGMA_FLOOR
    q=q[q.time>=pd.Timestamp(now)-pd.Timedelta(seconds=_SIGMA_WINDOW_S)]
    if len(q)<4: return _SIGMA_FLOOR
    dt=q.time.diff().dt.total_seconds().to_numpy(float)
    dp=q.value.diff().to_numpy(float)
    ok=np.isfinite(dt)&np.isfinite(dp)&(dt>0)
    if ok.sum()<3: return _SIGMA_FLOOR
    inst=np.abs(dp[ok])/np.sqrt(dt[ok])
    sigma=float(np.sqrt(np.mean(inst*inst)))
    return max(_SIGMA_FLOOR,sigma) if np.isfinite(sigma) else _SIGMA_FLOOR

def _normal_cdf(z):
    return 0.5*(1.0+math.erf(float(z)/math.sqrt(2.0)))

def _gt5_evidence(r):
    fam=r.get("_gt_family") or {}
    g=(fam.get("5") or fam.get(5) or {}).get("direction")
    s=str(g or "").upper()
    if "UP" in s or "ABOVE" in s: return 1.0,g
    if "DOWN" in s or "BELOW" in s: return -1.0,g
    return 0.0,g

def settlement_state(r, seconds_left, ticks, now=None):
    """Settlement 2.0 final-winner forecast. Separate from dynamic Decision."""
    now=pd.Timestamp(now or pd.Timestamp.now(tz="UTC"))
    px=float(r.get("btc") or r.get("brti") or 0.0)
    target=float(r.get("target") or 0.0)
    sec=max(0.0,float(seconds_left or 0.0))
    distance=px-target
    sigma=_sigma_per_sqrt_second(ticks,now)
    terminal_sd=max(_SIGMA_FLOOR, sigma*math.sqrt(max(sec,1.0)))
    z=distance/terminal_sd
    p_core=float(np.clip(_normal_cdf(z),0.001,0.999))

    # Conservative GT5 evidence pooling. It changes log-odds, not the settlement
    # definition or target. When GT5 is unavailable, Settlement 2.0 is core-only.
    gt_ev,gt_dir=_gt5_evidence(r)
    core_logit=math.log(p_core/(1.0-p_core))
    # V10.39.14 Challenger: prospective Benchmark A showed the legacy +0.75 GT5
    # overlay reduced Settlement checkpoint accuracy. Core-only is now the
    # research Challenger output; the old overlay remains logged as a
    # counterfactual and has no Decision/Auto-Paper authority.
    p=float(np.clip(p_core,0.001,0.999))
    legacy_p=float(1.0/(1.0+math.exp(-(core_logit+_LEGACY_GT5_LOGIT_WEIGHT*gt_ev))))
    legacy_p=float(np.clip(legacy_p,0.001,0.999))
    side="ABOVE" if p>=0.5 else "BELOW"
    conf=abs(p-0.5)*2.0
    return {
      "prediction":side,"p_above":p,"p_below":1.0-p,"confidence":conf,
      "checkpoint_s":None,"seconds_remaining":sec,
      "qualified_70_research":bool(conf>=0.20),
      "role":"SETTLEMENT 2.0 — final-winner forecast; separate from dynamic Decision",
      "model_version":_VERSION,
      "core_p_above":p_core,"core_z":z,"distance":distance,
      "sigma_usd_sqrt_s":sigma,"terminal_sd_usd":terminal_sd,
      "gt5_direction":gt_dir,"gt5_evidence":gt_ev,"gt5_logit_weight":_GT5_LOGIT_WEIGHT,
      "legacy_gt5_p_above":legacy_p,"legacy_gt5_logit_weight":_LEGACY_GT5_LOGIT_WEIGHT,
      "time_model":"CONTINUOUS_TERMINAL_DISTRIBUTION",
      "legacy_checkpoint_model_used":False
    }
