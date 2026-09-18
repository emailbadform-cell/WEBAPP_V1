"""V10.39.6 / V2.28.16 research-only target-structure and pressure-response instrumentation.
No Decision, Settlement, GT, MP, Chart, or execution authority.
"""
from collections import defaultdict, deque
import math

AUTHORITY = False
VERSION = "TARGET_PRESSURE_CONTEXT_V1"
_HORIZONS = (1,2,3,5,10,20,30)
_THRESHOLDS = (5.0,10.0)
_state = defaultdict(lambda: {
    "last_of": None, "of_event": None,
    "last_l2": None, "l2_event": None,
    "cross_times": deque(maxlen=512), "last_price_side": None,
})

def _side(v):
    s=str(v or "").upper()
    if "ABOVE" in s or "BULL" in s or s in ("UP","BUY"): return 1
    if "BELOW" in s or "BEAR" in s or s in ("DOWN","SELL"): return 0
    return None

def _response(event, now_s, price):
    out={"state":"UNRESOLVED","age_s":None,"signed_response_usd":None,"threshold_usd":None}
    if not event: return out
    age=max(0.0, now_s-event["t"])
    signed=(price-event["price"])*(1.0 if event["side"]==1 else -1.0)
    # Mature threshold: $5 first; $10 is also logged as a stronger state.
    th=10.0 if abs(signed)>=10.0 else 5.0
    if age < 5.0: st="UNRESOLVED"
    elif signed >= th: st="EFFECTIVE"
    elif signed <= -th: st="COUNTERMOVE"
    else: st="ABSORBED"
    out.update(state=st,age_s=round(age,3),signed_response_usd=round(signed,4),threshold_usd=th)
    for h in _HORIZONS:
        out[f"mature_{h}s"]=bool(age>=h)
    return out

def update(ticker, epoch_s, brti, target, of_direction=None, l2_venue_imbalances=None):
    s=_state[str(ticker)]
    p=float(brti); tar=float(target)
    ps=1 if p>tar else 0
    if s["last_price_side"] is not None and ps != s["last_price_side"]:
        s["cross_times"].append(float(epoch_s))
    s["last_price_side"]=ps
    of=_side(of_direction)
    if of is not None and of != s["last_of"]:
        s["of_event"]={"t":float(epoch_s),"price":p,"side":of}
        s["last_of"]=of
    vals=[float(x) for x in (l2_venue_imbalances or []) if x is not None and math.isfinite(float(x))]
    l2=None
    if vals:
        pos=sum(x>0 for x in vals); neg=sum(x<0 for x in vals)
        l2=1 if pos>=neg else 0
        if l2 != s["last_l2"]:
            s["l2_event"]={"t":float(epoch_s),"price":p,"side":l2}
            s["last_l2"]=l2
    now=float(epoch_s)
    crosses={w:sum(t>=now-w for t in s["cross_times"]) for w in (30,60,120)}
    return {
        "of_response":_response(s["of_event"],now,p),
        "l2_response":_response(s["l2_event"],now,p),
        "l2_consensus_side":("ABOVE" if l2==1 else "BELOW") if l2 is not None else None,
        "l2_venue_n":len(vals),
        "l2_positive_fraction":(sum(x>0 for x in vals)/len(vals)) if vals else None,
        "l2_dispersion":(sum((x-sum(vals)/len(vals))**2 for x in vals)/len(vals))**0.5 if vals else None,
        "target_crosses_30s":crosses[30],"target_crosses_60s":crosses[60],"target_crosses_120s":crosses[120],
        "target_abs_distance":abs(p-tar),
        "research_only":True,"authority":False,"version":VERSION,
    }
