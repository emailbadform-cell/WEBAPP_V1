"""15 named research-only strategies. Event-time causal; no fabricated fills/GT authority."""
from datetime import datetime
from math import isfinite
POLICIES=('decision_only','decision_settlement','decision_gt','decision_structure','decision_of_l2','hold_settlement','decision_flip','decision_flip_5s','target_recross','reversal','of_l2_opposition','take_profit','trailing_protection','time_exit','multi_risk')
DEFAULTS=dict(max_quote_age_s=10,entry_min_s=20,entry_max_s=180,decision_flip_persist_s=5,take_profit_cents=10,trailing_giveback_cents=5,time_exit_s=30,multi_risk_count=2,gt_horizon=5,cooldown_s=30)
def side(x):
 if not isinstance(x,str):return None
 x=x.upper().strip();return x if x in ('ABOVE','BELOW') else None
def num(x):
 try:
  y=float(x);return y if isfinite(y) else None
 except (TypeError,ValueError):return None
def stamp(s):
 if not isinstance(s,str):return None
 try:
  x=datetime.fromisoformat(s.replace('Z','+00:00'));return x if x.tzinfo else None
 except ValueError:return None
def opposite(s):return 'BELOW' if s=='ABOVE' else 'ABOVE'
def gt_side(d,horizon):
 # Legacy recursive GT is research-only; can be tested as a proxy, never labeled authoritative.
 g=d.get('ghost_thread_recursive') or {};directions=g.get('directions') or []
 if len(directions)<horizon:return None
 return {'UP':'ABOVE','DOWN':'BELOW'}.get(directions[horizon-1])
def structure_side(d):
 x=d.get('structure') or {};v=[num(x.get(k)) for k in ('m1_trend','m5_trend','m15_trend')];v=[z for z in v if z is not None]
 return 'ABOVE' if sum(v)>0 else 'BELOW' if sum(v)<0 else None
def of_side(d):
 x=d.get('multi_orderflow') or {};x=x.get('combined') or d.get('orderflow') or {}
 for key in ('pressure_score','pressure','imbalance'):
  v=num(x.get(key))
  if v is not None and abs(v)>0.05:return 'ABOVE' if v>0 else 'BELOW'
 return None
def l2_side(d):
 x=(d.get('l2') or {}).get('combined') or {};v=num(x.get('imbalance'))
 return ('ABOVE' if v>0.05 else 'BELOW' if v<-.05 else None) if v is not None else None
class Shadow15:
 def __init__(self,**kw):self.cfg=DEFAULTS|kw;self.prev={};self.open={};self.seen=set();self.last_entry={};self.flip_since={};self.exit_fired=set()
 def evaluate(self,d):
  ticker=d.get('ticker') or (d.get('market') or {}).get('ticker');at=stamp(d.get('logged_at_utc') or d.get('server_time'));b=d.get('execution_market') or {};q=stamp(b.get('timestamp_utc'))
  if not ticker or at is None:return []
  dec=side((d.get('decision') or {}).get('decision'));sett=side((d.get('settlement') or {}).get('prediction'));seconds=num(d.get('seconds_left'));price=num(d.get('brti'));target=num(d.get('target'));seq=d.get('state_sequence')
  prev=self.prev.get(ticker,{});age=(at-q).total_seconds() if q else None
  identity=b.get('book_sid') is not None or b.get('book_seq') is not None
  base=dec is not None and seconds is not None and self.cfg['entry_min_s']<=seconds<=self.cfg['entry_max_s'] and identity and b.get('book_healthy') is True and age is not None and 0<=age<=self.cfg['max_quote_age_s']
  gs=gt_side(d,self.cfg['gt_horizon']);ss=structure_side(d);ofs=of_side(d);ls=l2_side(d)
  if prev.get('decision')!=dec and dec is not None:self.flip_since[ticker]=at
  reversal=d.get('exhaustion_reversal') or {};risk=d.get('profit_reversal_risk') or {}
  opposed=ofs==opposite(dec) and ls==opposite(dec) if dec else False
  confirmed=bool(reversal.get('reversal') or risk.get('confirmed_reversal'))
  recross=prev.get('distance') is not None and price is not None and target is not None and (price-target)*prev['distance']<0
  adverse=[confirmed,opposed, bool(risk.get('mp_opposes_decision')),bool(risk.get('chart_disagrees')),bool(recross)]
  entry={'decision_only':dec is not None,'decision_settlement':sett==dec and dec is not None,'decision_gt':gs==dec and dec is not None,'decision_structure':ss==dec and dec is not None,'decision_of_l2':ofs==dec and ls==dec and dec is not None}
  out=[]
  for policy in POLICIES:
   pos=self.open.get((ticker,policy));ask=num(b.get('yes_ask' if dec=='ABOVE' else 'no_ask')) if dec else None
   if policy in entry:
    trigger=entry[policy];reason='ELIGIBLE' if trigger and base and ask is not None and 0<ask<1 else 'CONDITION_FALSE' if not trigger else 'INVALID_OR_STALE_QUOTE'
    if reason=='ELIGIBLE' and (ticker,policy) in self.last_entry and (at-self.last_entry[ticker,policy]).total_seconds()<self.cfg['cooldown_s']:reason='COOLDOWN'
    if reason=='ELIGIBLE' and (ticker,policy) not in self.open:
     self.last_entry[ticker,policy]=at;self.open[ticker,policy]=dict(side=dec,entry_at=at,entry_ask=ask,high_bid=None,entry_quote_id=b.get('book_sid'),entry_quote_seq=b.get('book_seq'),synthetic=True)
    elif reason=='ELIGIBLE' and pos:reason='POSITION_ALREADY_OPEN'
    out.append(dict(contract=ticker,at=at.isoformat(),sequence=seq,policy=policy,action='ENTRY_SIGNAL' if reason=='ELIGIBLE' else 'REJECTED',reason=reason,side=dec,quote_age_s=age,quote_id=b.get('book_sid'),price=ask,authority='RESEARCH_ONLY_NO_FILL'))
   else:
    # Position-management policies evaluate an independently attributed hypothetical Decision-only entry.
    anchor=self.open.get((ticker,'decision_only'))
    if not anchor:
     out.append(dict(contract=ticker,at=at.isoformat(),sequence=seq,policy=policy,action='NO_POSITION',reason='NO_DECISION_ANCHOR',authority='RESEARCH_ONLY_NO_FILL'));continue
    ps=anchor['side'];bid=num(b.get('yes_bid' if ps=='ABOVE' else 'no_bid'));entry_ask=anchor['entry_ask'];peak=anchor.get('high_bid');peak=max(peak,bid) if peak is not None and bid is not None else bid
    anchor['high_bid']=peak
    flip=dec is not None and dec!=ps
    persist=(at-self.flip_since.get(ticker,at)).total_seconds() if flip else 0
    trigger={'hold_settlement':sett is not None and sett!=ps,'decision_flip':flip,'decision_flip_5s':flip and persist>=self.cfg['decision_flip_persist_s'],'target_recross':bool(recross and ((price-target<0 and ps=='ABOVE') or (price-target>0 and ps=='BELOW'))),'reversal':confirmed,'of_l2_opposition':ofs==opposite(ps) and ls==opposite(ps),'take_profit':bid is not None and (bid-entry_ask)*100>=self.cfg['take_profit_cents'],'trailing_protection':peak is not None and bid is not None and peak>entry_ask and (peak-bid)*100>=self.cfg['trailing_giveback_cents'],'time_exit':seconds is not None and seconds<=self.cfg['time_exit_s'],'multi_risk':sum(adverse)>=self.cfg['multi_risk_count']}[policy]
    valid=identity and b.get('book_healthy') is True and age is not None and 0<=age<=self.cfg['max_quote_age_s'] and bid is not None and 0<bid<1
    reason='ALREADY_TRIGGERED' if (ticker,policy) in self.exit_fired else 'TRIGGERED' if trigger and valid else 'STALE_OR_MISSING_EXIT_QUOTE' if trigger else 'CONDITION_FALSE'
    if reason=='TRIGGERED':self.exit_fired.add((ticker,policy))
    out.append(dict(contract=ticker,at=at.isoformat(),sequence=seq,policy=policy,action='EXIT_SIGNAL' if reason=='TRIGGERED' else 'REJECTED',reason=reason,side=ps,quote_age_s=age,quote_id=b.get('book_sid'),price=bid,anchor_entry_ask=entry_ask,authority='RESEARCH_ONLY_NO_FILL'))
  self.prev[ticker]=dict(decision=dec,distance=(price-target) if price is not None and target is not None else None)
  return out
