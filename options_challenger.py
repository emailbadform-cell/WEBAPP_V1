"""BTC15M experimental binary fair value / risk observations. NO ORDER AUTHORITY.
The lognormal binary formula is a testable baseline, not a reproduction of the author's model.
External options IV must be supplied with verifiable source and timestamps; never substitute spot realized volatility silently.
"""
import math, json, os, time
from datetime import datetime,timezone
from pathlib import Path

def num(x):
    try:
        f=float(x)
        return f if math.isfinite(f) else None
    except (TypeError,ValueError):return None

def epoch(x):
    if isinstance(x,(int,float)):return float(x)
    if not x:return None
    try:return datetime.fromisoformat(str(x).replace('Z','+00:00')).timestamp()
    except ValueError:return None

def binary_yes(spot,strike,seconds,iv,rate=0.0):
    """Lognormal digital P(S_T > strike), NOT guaranteed Kalshi settlement probability."""
    s,k,t,v=map(num,(spot,strike,seconds,iv))
    if None in (s,k,t,v) or s<=0 or k<=0 or t<=0 or v<=0 or v>5:return None
    tau=t/(365.25*24*3600); z=(math.log(s/k)+(rate-0.5*v*v)*tau)/(v*math.sqrt(tau))
    return max(0.,min(1.,0.5*math.erfc(-z/math.sqrt(2))))

def interpolated_iv(points,strike):
    """Linear interpolation on a same-expiry strike slice; reject extrapolation."""
    try:p=sorted((float(x['strike']),float(x['iv'])) for x in points)
    except (KeyError,ValueError,TypeError):return None
    if len(p)<2 or strike<p[0][0] or strike>p[-1][0]:return None
    for (a,va),(b,vb) in zip(p,p[1:]):
        if a<=strike<=b and b>a:return va+(vb-va)*(strike-a)/(b-a)
    return None

def evaluate(snap,iv_record=None,now=None,fee_cents=2.0,maximum_quote_age=3.0):
    """All comparisons are hypothetical; require a contemporaneous source IV record."""
    now=time.time() if now is None else now
    spot=num(snap.get('brti'));strike=num(snap.get('target'));left=num(snap.get('seconds_left'))
    q=snap.get('execution_market') or {}; out={'schema':'BTC15M_OPTIONS_CHALLENGER_V1','ticker':snap.get('ticker'),
      'at':datetime.fromtimestamp(now,timezone.utc).isoformat(),'authority':'RESEARCH_ONLY_NO_ORDERS',
      'iv_status':'MISSING','fair_yes':None,'fair_no':None,'eligible':False,'reason':'NO_VALID_OPTIONS_IV',
      'gamma_zone':False,'target_distance_usd':None,'regime':'UNKNOWN','entries':{},'quote_status':'UNKNOWN'}
    if spot is None or strike is None or left is None or spot<=0 or strike<=0 or left<=0:return out
    dist=abs(spot-strike);out['target_distance_usd']=round(dist,3)
    # Dimensionless closeness, avoids a fixed-dollar threshold across volatility regimes.
    iv=num((iv_record or {}).get('iv'))
    out['gamma_zone']=bool(left<=180 and dist<=max(10,spot*(iv or 0.5)*math.sqrt(left/(365.25*86400))*0.5))
    if iv_record is None:return out
    ts=epoch(iv_record.get('source_time'));recv=epoch(iv_record.get('received_at'))
    if not iv_record.get('venue') or not iv_record.get('instrument') or ts is None or recv is None or iv is None:
        out['iv_status']='INVALID_PROVENANCE';return out
    if ts>now+1 or recv>now+1 or now-ts>30 or now-recv>30 or recv<ts-3:
        out['iv_status']='STALE_OR_FUTURE';return out
    # Do not use an option expiry earlier than contract settlement.
    expiry=epoch(iv_record.get('expiry'))
    if expiry is None or expiry<now+left:
        out['iv_status']='EXPIRY_MISMATCH';return out
    if iv_record.get('smile'):
        iv=interpolated_iv(iv_record['smile'],strike)
        if iv is None:out['iv_status']='SMILE_STRIKE_NOT_COVERED';return out
    p=binary_yes(spot,strike,left,iv)
    if p is None:out['iv_status']='INVALID_IV';return out
    out.update(iv_status='VALID_EXTERNAL',fair_yes=round(p,6),fair_no=round(1-p,6),
               options_source={'venue':iv_record['venue'],'instrument':iv_record['instrument'],
                               'source_time':iv_record['source_time'],'expiry':iv_record['expiry'],
                               'iv':iv,'model':'LOGNORMAL_DIGITAL_BASELINE'})
    qts=epoch(q.get('timestamp_utc'));healthy=q.get('book_healthy') is True
    qid=q.get('book_sid') or q.get('quote_id')
    if qts is None or qid is None or not healthy or qts>now+1 or now-qts>maximum_quote_age:
        out['quote_status']='STALE_UNIDENTIFIED_OR_UNHEALTHY';return out
    out['quote_status']='SOURCE_IDENTIFIED_HEALTHY'
    for side,pred in [('ABOVE',p),('BELOW',1-p)]:
        ask=num(q.get('yes_ask' if side=='ABOVE' else 'no_ask'))
        if ask is None:continue
        if ask>1:ask/=100
        if not 0<ask<1:continue
        edge=pred-ask-fee_cents/100
        out['entries'][side]={'ask':ask,'theoretical_edge_after_assumed_fee':round(edge,5),
           'qualifies_80_90':bool(0.8<=ask<=0.9 and edge>=0.03),
           'qualifies_40_60':bool(0.4<=ask<=0.6 and edge>=0.03),
           'quote_id':str(qid),'fee_cents_assumed':fee_cents}
    out['eligible']=True;out['reason']='RESEARCH_ONLY_VALID_INPUTS'
    return out

def model_stop(entry_price,model_fair,market_bid,regime_changed=False,gamma_zone=False):
    """Independent challenger signals; never an execution instruction."""
    e,m,b=map(num,(entry_price,model_fair,market_bid))
    if None in (e,m,b):return {'action':'NO_EVIDENCE'}
    if e>1:e/=100
    if m>1:m/=100
    if b>1:b/=100
    return {'model_below_entry':m<e,'market_below_entry':b<e,
            'regime_override':bool(regime_changed),'gamma_caution':bool(gamma_zone),
            'model_stop_candidate':bool(m<e or regime_changed),'authority':'RESEARCH_ONLY'}

class RegimeWatch:
    """Per-contract causal online detection; warm-up required; no future samples."""
    def __init__(self):self.prev={}
    def observe(self,ticker,spot,at,flow_direction=None,decision=None):
        t=epoch(at);s=num(spot)
        if not ticker or t is None or s is None:return {'regime':'UNKNOWN'}
        old=self.prev.get(ticker);self.prev[ticker]=(t,s)
        if not old or t<=old[0] or t-old[0]>30:return {'regime':'WARMUP'}
        speed=(s-old[1])/(t-old[0]);direction='ABOVE' if speed>0 else 'BELOW' if speed<0 else 'FLAT'
        conflict=direction!='FLAT' and decision in ('ABOVE','BELOW') and decision!=direction
        flow_conflict=flow_direction in ('ABOVE','BELOW') and flow_direction==direction
        return {'regime':'POSSIBLE_REVERSAL' if conflict and flow_conflict and abs(speed)>=2 else 'WATCH' if conflict else 'NORMAL',
                'btc_speed_usd_s':round(speed,4),'decision_price_conflict':conflict,
                'flow_supports_price':flow_conflict,'threshold_experimental':True}
