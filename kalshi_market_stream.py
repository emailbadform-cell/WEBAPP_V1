"""Kalshi market WebSocket state cache for execution research.

Execution-domain only: never feed these prices into Decision/GT/Settlement.
Maintains current+next market order books from snapshot + sequence-checked deltas,
plus ticker/trade telemetry. REST remains the recovery/fallback path.
"""
from __future__ import annotations
import json, os, threading, time
from datetime import datetime, timezone

try:
    import websocket
except Exception:
    websocket=None

class KalshiMarketStream:
    def __init__(self, ws_url, auth_headers_fn, event_log_path=None, on_event=None):
        self.ws_url=ws_url; self.auth_headers_fn=auth_headers_fn
        self.event_log_path=event_log_path; self.on_event=on_event
        self.lock=threading.RLock(); self.running=False; self.thread=None
        self.desired=[]; self.books={}; self.tickers={}; self.trades={}
        self.status='STOPPED'; self.error=None; self.last_event_mono=0.0
        self.reconnects=0; self.sequence_gaps=0; self.generation=0

    def start(self):
        if self.running:return
        self.running=True; self.thread=threading.Thread(target=self._worker,daemon=True); self.thread.start()
    def stop(self): self.running=False
    def set_markets(self, tickers):
        clean=[]
        for x in tickers or []:
            x=str(x or '').strip()
            if x and x not in clean: clean.append(x)
        clean=clean[:3]
        with self.lock:
            if clean!=self.desired:
                self.desired=clean; self.generation+=1
    def _emit(self, kind, msg, seq=None):
        now=datetime.now(timezone.utc).isoformat()
        rec={'kind':kind,'server_received_utc':now,'seq':seq,'msg':msg}
        if self.event_log_path:
            try:
                with open(self.event_log_path,'a',encoding='utf-8') as f:f.write(json.dumps(rec,separators=(',',':'))+'\n')
            except Exception: pass
        if self.on_event:
            try:self.on_event(kind,rec)
            except Exception:pass
    @staticmethod
    def _levels(rows):
        out={}
        for row in rows or []:
            try:
                p=float(row[0]); q=float(row[1])
                if q>0: out[p]=q
            except Exception: pass
        return out
    def process_message(self, data):
        typ=data.get('type'); msg=data.get('msg') or {}; seq=data.get('seq'); ticker=msg.get('market_ticker')
        if typ=='orderbook_snapshot' and ticker:
            y=self._levels(msg.get('yes_dollars_fp') or msg.get('yes_dollars') or msg.get('yes'))
            n=self._levels(msg.get('no_dollars_fp') or msg.get('no_dollars') or msg.get('no'))
            # Legacy integer-cent rows, if present.
            if y and max(y)>1.0:y={p/100.0:q for p,q in y.items()}
            if n and max(n)>1.0:n={p/100.0:q for p,q in n.items()}
            with self.lock:self.books[ticker]={'yes':y,'no':n,'seq':seq,'updated_mono':time.monotonic(),'updated_utc':datetime.now(timezone.utc).isoformat(),'healthy':True}
            self._emit(typ,msg,seq); return
        if typ=='orderbook_delta' and ticker:
            with self.lock:
                b=self.books.get(ticker)
                if not b or b.get('seq') is None:
                    self.sequence_gaps+=1; raise RuntimeError('orderbook delta before snapshot')
                if seq is not None and int(seq)!=int(b['seq'])+1:
                    b['healthy']=False; self.sequence_gaps+=1; raise RuntimeError(f'orderbook sequence gap {b["seq"]}->{seq}')
                side=str(msg.get('side') or '').lower(); p=float(msg.get('price_dollars')); dq=float(msg.get('delta_fp',msg.get('delta',0)))
                levels=b.get(side)
                if levels is None: raise RuntimeError('invalid orderbook side')
                q=float(levels.get(p,0.0))+dq
                if q<=1e-12: levels.pop(p,None)
                else: levels[p]=q
                b['seq']=seq; b['updated_mono']=time.monotonic(); b['updated_utc']=datetime.now(timezone.utc).isoformat(); b['healthy']=True
            self._emit(typ,msg,seq); return
        if typ=='ticker' and ticker:
            with self.lock:self.tickers[ticker]={**msg,'updated_mono':time.monotonic(),'updated_utc':datetime.now(timezone.utc).isoformat()}
            self._emit(typ,msg,seq); return
        if typ=='trade' and ticker:
            with self.lock:self.trades[ticker]={**msg,'updated_mono':time.monotonic(),'updated_utc':datetime.now(timezone.utc).isoformat()}
            self._emit(typ,msg,seq); return
        if typ=='error': raise RuntimeError('Kalshi WS error: '+str(msg))
    def book(self,ticker):
        with self.lock:b=self.books.get(ticker)
        if not b:return {}
        y=b.get('yes') or {}; n=b.get('no') or {}
        yb=max(y,default=None); nb=max(n,default=None); ya=(1-nb) if nb is not None else None; na=(1-yb) if yb is not None else None
        age=max(0.0,time.monotonic()-b.get('updated_mono',0.0))
        return {'yes_bid':yb,'yes_ask':ya,'no_bid':nb,'no_ask':na,
                'yes_bid_depth':y.get(yb) if yb is not None else None,'no_bid_depth':n.get(nb) if nb is not None else None,
                'yes_ask_depth':n.get(nb) if nb is not None else None,'no_ask_depth':y.get(yb) if yb is not None else None,
                'yes_gross_multiplier':1/ya if ya else None,'no_gross_multiplier':1/na if na else None,
                'source':'Kalshi WebSocket orderbook','timestamp_utc':b.get('updated_utc'),'quote_age_ms':age*1000.0,
                'book_seq':b.get('seq'),'book_healthy':bool(b.get('healthy')),'book_levels_yes':len(y),'book_levels_no':len(n)}
    def health(self):
        with self.lock:
            return {'status':self.status,'error':self.error,'markets':list(self.desired),'reconnects':self.reconnects,
                    'sequence_gaps':self.sequence_gaps,'last_event_age_s':(time.monotonic()-self.last_event_mono) if self.last_event_mono else None,
                    'books':{k:{'healthy':v.get('healthy'),'seq':v.get('seq'),'age_s':time.monotonic()-v.get('updated_mono',0)} for k,v in self.books.items()}}
    def _worker(self):
        backoff=.5
        if websocket is None:self.status='UNAVAILABLE';self.error='websocket-client not installed';return
        while self.running:
            with self.lock: markets=list(self.desired); gen=self.generation
            if not markets:self.status='WAITING_MARKET';time.sleep(.1);continue
            ws=None
            try:
                self.status='CONNECTING'; headers=self.auth_headers_fn()
                ws=websocket.create_connection(self.ws_url,header=[f'{k}: {v}' for k,v in headers.items()],timeout=8,origin=None)
                ws.settimeout(1.0)
                ws.send(json.dumps({'id':201,'cmd':'subscribe','params':{'channels':['orderbook_delta','trade','ticker'],'market_tickers':markets}}))
                self.status='LIVE';self.error=None;backoff=.5
                while self.running:
                    with self.lock:
                        if self.generation!=gen: raise RuntimeError('market subscription changed')
                    try: raw=ws.recv()
                    except Exception as e:
                        if 'timed out' in str(e).lower(): continue
                        raise
                    data=json.loads(raw); self.last_event_mono=time.monotonic(); self.process_message(data)
            except Exception as e:
                self.error=str(e); self.status='RECONNECTING'; self.reconnects+=1
                with self.lock:
                    for t in markets:
                        if t in self.books:self.books[t]['healthy']=False
                time.sleep(backoff);backoff=min(8.0,backoff*1.7)
            finally:
                try:
                    if ws:ws.close()
                except Exception:pass
