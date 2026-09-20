import math
from datetime import datetime, timezone, timedelta
import pandas as pd
import app
import live_btc15m_predictor as core

EVENTS=[]
app._auto_event=lambda kind,d,extra=None,pos=None: EVENTS.append((kind,extra or {},dict(pos or {})))
app._save_auto_state=lambda: None

def state(sec, decision='ABOVE', settlement='BELOW', ask=.60, bid=.58, brti=101, target=100, ticker='T1'):
    return {'status':'ok','market':{'ticker':ticker,'seconds_left':sec,'brti':brti,'target':target},
            'decision':{'decision':decision,'confidence':70},'settlement':{'prediction':settlement,'confidence':60},
            'execution_market':{'yes_ask':ask,'yes_bid':bid,'no_ask':1-bid,'no_bid':1-ask,'book_healthy':True},
            'flip':{},'exhaustion_reversal':{},'profit_reversal_risk':{}}

def reset():
    EVENTS.clear(); app.AUTO_PAPER.update({'enabled':True,'position':None,'decision_side':'ABOVE','decision_since':0.0,'last_shadow_key':None,'last_exit':None,'shadow_positions':[],'contract_stats':{},'coverage_candidate':None})

# Final Target: complete preserved minute gives 60/60 and correct average.
close=pd.Timestamp('2026-09-19T13:30:00Z'); start=close-pd.Timedelta(seconds=60)
preserved={(start+pd.Timedelta(seconds=i)).isoformat(): 100+i for i in range(60)}
r=core.settlement_window_state(pd.DataFrame(columns=['time','value']),159,150,close,close,preserved)
assert r['sample_count']==60 and r['missing_second_count']==0, r
assert abs(r['final_target']-129.5)<1e-9

# Monotonic accumulator: capture 60 source seconds and ensure none disappear.
class E: market={'ticker':'TFT'}
app.engine=E(); app.FINAL_TARGET_SECONDS.clear(); counts=[]
for i in range(60):
    qt=start+pd.Timedelta(seconds=i)
    rr={'ticker':'TFT','close_time':close,'quote_time':qt,'btc':100+i}
    counts.append(len(app._capture_final_target_second(rr,qt.to_pydatetime())))
assert counts==list(range(1,61)), counts[-5:]

# Repeated rejected evaluations create one live shadow trade, not duplicates.
reset(); app.AUTO_PAPER['decision_since']=0
s=state(150,settlement='BELOW')
app.auto_paper_tick(s); app.auto_paper_tick(s); app.auto_paper_tick(s)
se=[e for e in EVENTS if e[0]=='SHADOW_ENTRY']
assert len(se)==1, len(se)

# No Primary -> coverage trade by 90s, separately labeled.
reset();
app.auto_paper_tick(state(150,settlement='BELOW'))
app.auto_paper_tick(state(89,settlement='BELOW'))
assert app.AUTO_PAPER['position'] is not None
assert app.AUTO_PAPER['position']['kind']=='FORCED_COVERAGE'
assert app.AUTO_PAPER['contract_stats']['T1']['coverage']==1

# Primary remains Primary when all frozen gates pass.
reset(); app.AUTO_PAPER['decision_side']='ABOVE'; app.AUTO_PAPER['decision_since']=0.0
# monkeypatch gate persistence by setting side same and a very old timestamp
app.AUTO_PAPER['decision_since']=1.0
# _auto_gate uses epoch now, so persistence passes
app.auto_paper_tick(state(150,settlement='ABOVE'))
assert app.AUTO_PAPER['position'] is not None and app.AUTO_PAPER['position']['kind']=='PRIMARY'
assert app.AUTO_PAPER['contract_stats']['T1']['primary']==1

# Shadow never becomes authoritative primary position.
reset(); app.auto_paper_tick(state(150,settlement='BELOW'))
assert app.AUTO_PAPER['position'] is None
assert len(app.AUTO_PAPER['shadow_positions'])==1

print('ALL_CANDIDATE_TESTS_PASS')

# Multi-contract coverage replay: every contract with executable quotes gets Primary or Coverage.
for k in range(4):
    reset(); ticker=f'R{k}'
    # Keep settlement opposed so Primary cannot pass; coverage must enter.
    for sec in (180,150,120,100,89):
        app.auto_paper_tick(state(sec,settlement='BELOW',ticker=ticker,brti=101+k,target=100))
        if app.AUTO_PAPER['position'] is not None: break
    st=app.AUTO_PAPER['contract_stats'][ticker]
    assert st['primary']+st['coverage']>=1,(ticker,st)
print('MULTICONTRACT_COVERAGE_PASS')
