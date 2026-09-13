\
import math, time, threading, json
from pathlib import Path
from datetime import datetime, timezone
import numpy as np, pandas as pd, requests, joblib

FORWARD_THRESHOLDS={5:.225,10:.175,30:.125,60:.125}
SNAPBACK_5M_SPEED_BPS_5S=0.253118
STRONG_2M_BODY_BPS=1.901514

class SignalSuite:
    def __init__(self, base_dir):
        base=Path(base_dir)
        self.forward=joblib.load(base/'forward_signal_models.joblib')
        self.decision=joblib.load(base/'decision_signal_model.joblib')
        self.candle2=joblib.load(base/'candle2_preview_model.joblib')
        self._direction='SIDEWAYS'; self._horizon=5; self._extend_candidate=None; self._extend_count=0
        self._last_5m_side=None; self._last_5m_bucket=None
    @staticmethod
    def _ticks(ticks,now):
        if ticks is None or len(ticks)==0:return pd.DataFrame(columns=['time','value'])
        q=ticks[['time','value']].copy(); q['time']=pd.to_datetime(q.time,utc=True,errors='coerce'); q['value']=pd.to_numeric(q.value,errors='coerce')
        now=pd.Timestamp(now); q=q.dropna().sort_values('time'); q=q[q.time<=now] # future-timestamp protection
        return q
    @staticmethod
    def _old(q,now,sec):
        if len(q)==0:return None
        target=pd.Timestamp(now)-pd.Timedelta(seconds=sec); z=q[q.time<=target]
        return None if len(z)==0 else float(z.iloc[-1].value)
    def features(self,ticks,current,now):
        q=self._ticks(ticks,now); px=float(current); h={}
        for s in (1,2,3,5,10,15,20,30,60,120):
            old=self._old(q,now,s); h[s]=0.0 if old is None or old<=0 else (px/old-1)*10000
        f={f'br_r{s}':h[s] for s in h}; f.update({'vel2':h[2]/2,'vel5':h[5]/5,'vel10':h[10]/10,'vel30':h[30]/30,'accel2_5':h[2]/2-h[5]/5,'accel5_10':h[5]/5-h[10]/10,'accel10_30':h[10]/10-h[30]/30,'jerk':(h[2]/2-h[5]/5)-(h[5]/5-h[10]/10)})
        q30=q[q.time>=pd.Timestamp(now)-pd.Timedelta(seconds=30)]; vals=q30.value.to_numpy(float) if len(q30) else np.array([px]); d=np.diff(vals)
        f['path_consistency']=float(abs(np.sign(d).sum())/max(1,len(d))) if len(d) else 0.; f['path_direction']=float(np.sign(h[10] if h[10] else h[5]))
        if len(vals)>1:
            rr=np.diff(np.log(np.maximum(vals,1e-9)))*10000; f['rv30']=float(np.std(rr)); f['range30_bps']=float((vals.max()-vals.min())/px*10000); f['pos30']=float((px-vals.min())/max(1e-9,vals.max()-vals.min())); f['dist_ma30_bps']=float((px-vals.mean())/px*10000)
        else:f.update({'rv30':0.,'range30_bps':0.,'pos30':.5,'dist_ma30_bps':0.})
        q60=q[q.time>=pd.Timestamp(now)-pd.Timedelta(seconds=60)]; vv=q60.value.to_numpy(float); rr=np.diff(np.log(np.maximum(vv,1e-9)))*10000 if len(vv)>1 else np.array([]); f['rv60']=float(np.std(rr)) if len(rr) else 0.
        return f,q
    def forward_state(self,ticks,current,now):
        f,q=self.features(ticks,current,now); probs={}; dirs={}
        for h,b in self.forward.items():
            X=pd.DataFrame([{k:f.get(k,0.) for k in b['features']}]); p=float(b['model'].predict_proba(X)[0,1]); probs[int(h)]=p; dirs[int(h)]='UP' if p>=.5 else 'DOWN'
        confident=[h for h in (5,10,30,60) if abs(probs[h]-.5)>=FORWARD_THRESHOLDS[h]]
        if not confident: raw_dir='SIDEWAYS'; raw_h=5
        else:
            raw_dir=dirs[min(confident)]; raw_h=min(confident)
            for h in (10,30,60):
                if h in confident and dirs[h]==raw_dir:raw_h=h
                elif h in confident and dirs[h]!=raw_dir:break
        # anti-flicker: direction change requires 2 consecutive non-sideways confirmations; SIDEWAYS contracts immediately
        if raw_dir=='SIDEWAYS': self._direction='SIDEWAYS'; self._horizon=5; self._extend_candidate=None; self._extend_count=0
        elif self._direction in ('SIDEWAYS',raw_dir):
            self._direction=raw_dir
            if raw_h>self._horizon:
                key=(raw_dir,raw_h); self._extend_count=self._extend_count+1 if self._extend_candidate==key else 1; self._extend_candidate=key
                if self._extend_count>=2:self._horizon=raw_h; self._extend_count=0
            elif raw_h<self._horizon:self._horizon=raw_h; self._extend_count=0; self._extend_candidate=None
        else:
            key=('DIR',raw_dir); self._extend_count=self._extend_count+1 if self._extend_candidate==key else 1; self._extend_candidate=key
            if self._extend_count>=2:self._direction=raw_dir; self._horizon=raw_h; self._extend_count=0; self._extend_candidate=None
        h=self._horizon; pu=probs.get(h,probs[5]); recent=f.get('br_r10',0.); phase='CONTINUATION' if ((recent>0 and self._direction=='UP') or (recent<0 and self._direction=='DOWN')) else 'REVERSAL'
        label='SIDEWAYS' if self._direction=='SIDEWAYS' else f'{self._direction} — {phase}'
        return {'state':self._direction,'label':label,'phase':phase,'horizon_s':h,'confidence':max(abs(probs[x]-.5)*2 for x in probs),'prob_up':pu,'horizons':probs,'features':f,'rv30':f.get('rv30',0.0)}
    def decision_state(self,ticks,current,target,seconds,now):
        f,q=self.features(ticks,current,now); dist=float(current)-float(target); vals={'signed_distance_usd':dist,'abs_distance_usd':abs(dist),'seconds_remaining':max(0.,float(seconds)),'distance_per_sqrt_time':dist/math.sqrt(max(1.,float(seconds))),'abs_distance_per_sqrt_time':abs(dist)/math.sqrt(max(1.,float(seconds))),'r5_bps':f['br_r5'],'r10_bps':f['br_r10'],'r30_bps':f['br_r30'],'r60_bps':f['br_r60'],'r120_bps':f['br_r120'],'accel_5_10':f['br_r5']/5-f['br_r10']/10}
        X=pd.DataFrame([{k:vals.get(k,0.) for k in self.decision['features']}]); p=float(self.decision['model'].predict_proba(X)[0,1]); side='ABOVE' if p>=.5 else 'BELOW'
        return {'decision':side,'state':side,'p_above':p,'p_below':1-p,'confidence':abs(p-.5)*2,'architecture':'PRICE_GEOMETRY — NO CURRENT SIDE'}
    @staticmethod
    def _bucket_open(q,now,mins):
        now=pd.Timestamp(now); epoch=int(now.timestamp()); width=mins*60; start=pd.Timestamp((epoch//width)*width,unit='s',tz='UTC'); z=q[(q.time>=start)&(q.time<=now)]; return (None,start) if len(z)==0 else (float(z.iloc[0].value),start)
    def ghost_state(self,ticks,current,now,fw):
        f,q=self.features(ticks,current,now); now=pd.Timestamp(now); out={}; px=float(current)
        for m in (1,2,3,4,5):
            op,start=self._bucket_open(q,now,m); elapsed=max(0.,(now-start).total_seconds()); side='FLAT' if op is None or abs(px-op)<1e-9 else ('UP' if px>op else 'DOWN'); out[str(m)]={'open':op,'elapsed_s':elapsed,'side':side,'distance_bps':None if not op else (px/op-1)*10000}
        e=out['1']['elapsed_s']; pside=out['1']['side']
        if e<5: gt_dir=fw['state']
        elif e<10: gt_dir=pside if pside!='FLAT' and abs(out['1']['distance_bps'] or 0)>=.10 else fw['state']
        else: gt_dir=pside if pside!='FLAT' else fw['state']
        stage='FORWARD' if e<5 else 'BLEND' if e<10 else 'PATH' if e<30 else 'PERSISTENCE'
        # 5m cross snapback research warning
        b5=pd.Timestamp(now).floor('5min'); s5=out['5']['side']; cross=False
        if self._last_5m_bucket==b5 and self._last_5m_side in ('UP','DOWN') and s5 in ('UP','DOWN') and s5!=self._last_5m_side: cross=True
        self._last_5m_bucket=b5; self._last_5m_side=s5
        fwd_support=sum(1 for h,p in fw['horizons'].items() if ('UP' if p>=.5 else 'DOWN') != s5)
        snap5=bool(cross and abs(f.get('br_r5',0.))>=SNAPBACK_5M_SPEED_BPS_5S and fwd_support>=3)
        # last completed 2m candle strong event
        start2=out['2']['elapsed_s']; last2_start=out['2']['open']; strong2=False; strong2_side=None
        prev_end=(pd.Timestamp(now).floor('2min')); prev_start=prev_end-pd.Timedelta(minutes=2); z=q[(q.time>=prev_start)&(q.time<prev_end)]
        if len(z)>=2:
            o=float(z.iloc[0].value); c=float(z.iloc[-1].value); body=(c/o-1)*10000; strong2=abs(body)>=STRONG_2M_BODY_BPS; strong2_side='UP' if body>0 else 'DOWN'
        snap2=bool(strong2 and fw['state'] in ('UP','DOWN') and fw['state']!=strong2_side)
        # Candle2 at T+50 only, triple agreement: dedicated model + native 30 + native 60
        c2={'active':False,'state':'OFF','direction':None,'confidence':0.}
        if e>=50:
            X=pd.DataFrame([{k:f.get(k,0.) for k in self.candle2['features']}]); cp=float(self.candle2['model'].predict_proba(X)[0,1]); cd='UP' if cp>=.5 else 'DOWN'; d30='UP' if fw['horizons'][30]>=.5 else 'DOWN'; d60='UP' if fw['horizons'][60]>=.5 else 'DOWN'
            if cd==d30==d60: c2={'active':True,'state':'PRELIMINARY','direction':cd,'confidence':abs(cp-.5)*2,'prob_up':cp,'provisional_open':px}
        rv=max(.05,float(f.get('rv30',0.))); return {'fixed_open_1m':out['1']['open'],'elapsed_1m_s':e,'stage':stage,'direction':gt_dir,'active_horizon_s':fw['horizon_s'],'uncertainty_bps':rv*math.sqrt(max(1,fw['horizon_s'])),'timeframes':out,'snapback_5m_warning':snap5,'strong_2m_snapback_warning':snap2,'candle2':c2,'candle3_active':False}

L2_URLS={'coinbase':'https://api.exchange.coinbase.com/products/BTC-USD/book','kraken':'https://api.kraken.com/0/public/Depth','bitstamp':'https://www.bitstamp.net/api/v2/order_book/btcusd/','gemini':'https://api.gemini.com/v1/book/btcusd'}
def _rows(rows):
    out=[]
    for x in rows or []:
        try:
            if isinstance(x,dict): p=float(x.get('price')); s=float(x.get('amount'))
            else:p=float(x[0]);s=float(x[1])
            if p>0 and s>=0:out.append((p,s))
        except:pass
    return out

def fetch_l2(exchange,timeout=4):
    h={'User-Agent':'btc15m-l2-v1034/1.0'}
    if exchange=='coinbase':j=requests.get(L2_URLS[exchange],params={'level':2},headers=h,timeout=timeout).json(); bids=_rows(j.get('bids'));asks=_rows(j.get('asks'))
    elif exchange=='kraken':j=requests.get(L2_URLS[exchange],params={'pair':'XBTUSD','count':100},headers=h,timeout=timeout).json();v=next(iter((j.get('result') or {}).values()),{});bids=_rows(v.get('bids'));asks=_rows(v.get('asks'))
    elif exchange=='bitstamp':j=requests.get(L2_URLS[exchange],params={'group':1},headers=h,timeout=timeout).json();bids=_rows(j.get('bids'));asks=_rows(j.get('asks'))
    else:j=requests.get(L2_URLS[exchange],params={'limit_bids':100,'limit_asks':100},headers=h,timeout=timeout).json();bids=_rows(j.get('bids'));asks=_rows(j.get('asks'))
    bids=sorted(bids,key=lambda z:z[0],reverse=True);asks=sorted(asks,key=lambda z:z[0]);
    if not bids or not asks:raise RuntimeError('empty book')
    return {'bids':bids[:100],'asks':asks[:100],'ts':time.time()}
def summarize_l2(book):
    bids,asks=book['bids'],book['asks']; bb,ba=bids[0][0],asks[0][0]; mid=(bb+ba)/2
    def depth(levels,bps,bid):
        lim=mid*(1-bps/10000) if bid else mid*(1+bps/10000); return sum(s for p,s in levels if (p>=lim if bid else p<=lim))
    d={}
    for b in (1,5,10,25):d[f'bid_depth_{b}bps']=depth(bids,b,True);d[f'ask_depth_{b}bps']=depth(asks,b,False)
    bd,ad=d['bid_depth_10bps'],d['ask_depth_10bps']; imb=(bd-ad)/(bd+ad+1e-12); score=max(-1.,min(1.,imb)); state='BULLISH' if score>=.15 else 'BEARISH' if score<=-.15 else 'NEUTRAL'
    d.update({'best_bid':bb,'best_ask':ba,'mid':mid,'spread_bps':(ba-bb)/mid*10000,'imbalance':imb,'score':score,'state':state,'ts':book['ts']});return d
class L2Worker:
    def __init__(self,interval=1.0,raw_dir=None):self.interval=max(.5,float(interval));self.raw_dir=Path(raw_dir) if raw_dir else None;self.lock=threading.Lock();self.latest={'venues':{},'combined':{'state':'NEUTRAL','score':0.,'n':0}};self.errors={};self.running=False
    def start(self):self.running=True;threading.Thread(target=self._run,daemon=True).start();return self
    def stop(self):self.running=False
    def snapshot(self):
        with self.lock:return json.loads(json.dumps(self.latest)),dict(self.errors)
    def _log(self,ex,b):
        if not self.raw_dir:return
        self.raw_dir.mkdir(parents=True,exist_ok=True); day=datetime.now(timezone.utc).strftime('%Y%m%d'); p=self.raw_dir/f'L2_{ex}_{day}.ndjson'; rec={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'exchange':ex,'bids':b['bids'][:50],'asks':b['asks'][:50]}
        with p.open('a',encoding='utf-8') as f:f.write(json.dumps(rec,separators=(',',':'))+'\n')
    def _run(self):
        while self.running:
            st=time.monotonic(); venues={};errs={}
            for ex in ('coinbase','kraken','bitstamp','gemini'):
                try:b=fetch_l2(ex);venues[ex]=summarize_l2(b);self._log(ex,b)
                except Exception as e:errs[ex]=str(e)
            vals=list(venues.values()); score=sum(v['score'] for v in vals)/len(vals) if vals else 0.; state='BULLISH' if score>=.15 else 'BEARISH' if score<=-.15 else 'NEUTRAL'; comb={'state':state,'score':score,'n':len(vals),'imbalance':sum(v['imbalance'] for v in vals)/len(vals) if vals else 0.,'bid_depth_10bps':sum(v['bid_depth_10bps'] for v in vals),'ask_depth_10bps':sum(v['ask_depth_10bps'] for v in vals),'ts':time.time()}
            with self.lock:self.latest={'venues':venues,'combined':comb,'ts':time.time()};self.errors=errs
            time.sleep(max(.05,self.interval-(time.monotonic()-st)))
