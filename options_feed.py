"""Read-only BTC options IV collector. No keys, orders, or fabricated observations.
Outputs the exact current_options_iv.json shape expected by the existing BTC15M experiment.
REST bootstrap/low-cadence research collector; replace with WebSocket for subsecond production study.
"""
import argparse, datetime as dt, json, math, os, pathlib, re, tempfile, time, urllib.parse, urllib.request
UTC=dt.timezone.utc

def iso(t): return dt.datetime.fromtimestamp(t,UTC).isoformat().replace('+00:00','Z')
def finite(v):
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except (TypeError,ValueError): return None

def get_json(url,timeout=9):
    req=urllib.request.Request(url,headers={'User-Agent':'BTC15M-options-research/1.0','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as response:return json.load(response)

def deribit_fetch(target=None,request=get_json):
    base='https://www.deribit.com/api/v2/'
    raw=request(base+'public/get_instruments?currency=BTC&kind=option&expired=false')
    instruments=raw.get('result') or []
    now=time.time(); active=[x for x in instruments if x.get('is_active') and finite(x.get('expiration_timestamp')) and x['expiration_timestamp']/1000>now+1200 and finite(x.get('strike'))]
    if not active:raise ValueError('Deribit has no active suitable BTC options')
    expiry_ms=min(x['expiration_timestamp'] for x in active)
    group=[x for x in active if x['expiration_timestamp']==expiry_ms and x.get('option_type')=='call']
    if not group:raise ValueError('Deribit expiry has no calls')
    # Select near target if supplied; otherwise use a single ticker to get an actual underlying index.
    reference=finite(target)
    if reference is None:
        mid=group[len(group)//2]; ticker=request(base+'public/ticker?'+urllib.parse.urlencode({'instrument_name':mid['instrument_name']})).get('result') or {}
        reference=finite(ticker.get('index_price')) or finite(ticker.get('underlying_price'))
    if reference is None:raise ValueError('No actual target or source index')
    group.sort(key=lambda x:abs(x['strike']-reference)); chosen=sorted(group[:min(8,len(group))],key=lambda x:x['strike'])
    points=[]; raw_rows=[]
    for inst in chosen:
        t=request(base+'public/ticker?'+urllib.parse.urlencode({'instrument_name':inst['instrument_name']})).get('result') or {}
        source_ms=finite(t.get('timestamp')); iv=finite(t.get('mark_iv')); bid=finite(t.get('bid_iv'));ask=finite(t.get('ask_iv'))
        index=finite(t.get('index_price'))
        if source_ms is None or iv is None or iv<=0 or index is None:continue
        received=time.time(); age=received-source_ms/1000
        if age < -1 or age>30:continue
        # Deribit IVs are quoted in percent; challenger accepts decimal annualized IV.
        points.append({'strike':float(inst['strike']),'iv':iv/100,'bid_iv':bid/100 if bid is not None else None,'ask_iv':ask/100 if ask is not None else None,
                       'instrument':inst['instrument_name'],'source_time':iso(source_ms/1000),'received_at':iso(received),'underlying_index':index})
        raw_rows.append({'instrument':inst,'ticker':t})
    if len(points)<2:raise ValueError('Insufficient fresh Deribit smile strikes')
    # Conservative common-time rule: all smile constituents <= 30s and 15s apart.
    times=[dt.datetime.fromisoformat(p['source_time'].replace('Z','+00:00')).timestamp() for p in points]
    if max(times)-min(times)>15:raise ValueError('Deribit smile constituent timestamps too far apart')
    center=min(points,key=lambda p:abs(p['strike']-reference))
    record={'venue':'DERIBIT','instrument':center['instrument'],'source_time':iso(min(times)),'received_at':iso(time.time()),
      'expiry':iso(expiry_ms/1000),'iv':center['iv'],'smile':[{'strike':p['strike'],'iv':p['iv']} for p in points],
      'underlying_index':center['underlying_index'],'reference_strike':reference,'raw_constituents':points,
      'provenance':'DERIBIT_PUBLIC_TICKER','expiry_transfer_assumption':'UNVALIDATED_15MIN_EXTRAPOLATION'}
    return record,raw_rows

def okx_fetch(target=None,request=get_json):
    base='https://www.okx.com/api/v5/public/opt-summary?instFamily=BTC-USD'
    response=request(base)
    if response.get('code')!='0':raise ValueError('OKX public opt-summary error: '+str(response.get('msg')))
    rows=response.get('data') or []; now=time.time(); valid=[]
    # Resolve actual exchange expiry, never assume a settlement hour from the symbol.
    instruments=request('https://www.okx.com/api/v5/public/instruments?instType=OPTION&instFamily=BTC-USD')
    if instruments.get('code')!='0':raise ValueError('OKX instrument expiry lookup failed')
    expiries={x.get('instId'):finite(x.get('expTime')) for x in (instruments.get('data') or [])}
    for x in rows:
        name=x.get('instId') or ''; m=re.match(r'^BTC-USD-(\d{6})-(\d+(?:\.\d+)?)-([CP])$',name)
        if not m or m[3]!='C':continue
        expiry_ms=expiries.get(name)
        if expiry_ms is None:continue
        expiry=expiry_ms/1000
        strike=float(m[2]);ts=finite(x.get('ts'));iv=finite(x.get('markVol'));index=finite(x.get('idxPx'))
        if ts is None or iv is None or iv<=0 or index is None or expiry<=now+1200 or now-ts/1000>30 or ts/1000>now+1:continue
        valid.append({'expiry':expiry,'strike':strike,'iv':iv,'source':ts/1000,'index':index,'raw':x})
    if not valid:raise ValueError('No fresh OKX options summary with valid source timestamps')
    expiry=min(x['expiry'] for x in valid);group=[x for x in valid if x['expiry']==expiry]
    reference=finite(target) or sorted(x['index'] for x in group)[len(group)//2]
    group.sort(key=lambda x:abs(x['strike']-reference));chosen=sorted(group[:8],key=lambda x:x['strike'])
    if len(chosen)<2 or max(x['source'] for x in chosen)-min(x['source'] for x in chosen)>15:raise ValueError('Insufficient synchronized OKX strikes')
    center=min(chosen,key=lambda x:abs(x['strike']-reference));record={'venue':'OKX','instrument':center['raw']['instId'],
       'source_time':iso(min(x['source'] for x in chosen)),'received_at':iso(time.time()),'expiry':iso(expiry),
       'iv':center['iv'],'smile':[{'strike':x['strike'],'iv':x['iv']} for x in chosen],
       'underlying_index':center['index'],'reference_strike':reference,
       'raw_constituents':[{'instrument':x['raw']['instId'],'source_time':iso(x['source']),'strike':x['strike'],'iv':x['iv']} for x in chosen],
       'provenance':'OKX_PUBLIC_OPT_SUMMARY','expiry_transfer_assumption':'UNVALIDATED_15MIN_EXTRAPOLATION'}
    return record,[x['raw'] for x in chosen]

def persist(record,raw,out):
    folder=pathlib.Path(out);folder.mkdir(parents=True,exist_ok=True)
    # One venue's current record is never silently substituted for the other.
    name=record['venue'].lower();dest=folder/(name+'_current_options_iv.json')
    with tempfile.NamedTemporaryFile('w',dir=folder,prefix='tmp-',delete=False) as f:
        json.dump(record,f,separators=(',',':'));f.flush();os.fsync(f.fileno());temp=f.name
    os.replace(temp,dest)
    with (folder/(name+'_options_raw.ndjson')).open('a') as f:f.write(json.dumps({'collected_at':iso(time.time()),'normalized':record,'raw':raw},separators=(',',':'))+'\n')
    # Primary Deribit path consumed by current Web/Research/Live adapters.
    if name=='deribit':
        primary=folder/'current_options_iv.json'
        with tempfile.NamedTemporaryFile('w',dir=folder,prefix='tmp-',delete=False) as f:
            json.dump(record,f,separators=(',',':'));f.flush();os.fsync(f.fileno());temp=f.name
        os.replace(temp,primary)
    return str(dest)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',default='./options-feed-data');ap.add_argument('--target',type=float);ap.add_argument('--interval',type=int,default=15);ap.add_argument('--once',action='store_true');ap.add_argument('--venue',choices=['deribit','okx','both'],default='both');args=ap.parse_args()
    if args.interval<5:ap.error('REST polling interval must be >= 5 seconds')
    while True:
        for name,fn in [('deribit',deribit_fetch),('okx',okx_fetch)]:
            if args.venue not in ('both',name):continue
            try:
                record,raw=fn(args.target);path=persist(record,raw,args.out)
                print(json.dumps({'status':'OK','venue':name,'strikes':len(record['smile']),'source_time':record['source_time'],'path':path}),flush=True)
            except Exception as exc:print(json.dumps({'status':'ERROR','venue':name,'error':str(exc)}),flush=True)
        if args.once:break
        time.sleep(args.interval)
if __name__=='__main__':main()
