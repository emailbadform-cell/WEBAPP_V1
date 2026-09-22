"""BTC15M pre-release, opt-in immutable research telemetry. No trading authority."""
from datetime import datetime, timezone, timedelta
import json, math

SCHEMA='BTC15M_ARCHITECT_TELEMETRY_V1'
KINDS={'terminal_outcome','price_direction','target_reach','execution'}
LABELS={'official_kalshi','reconstructed_brti','last_observed_proxy','unknown'}

def utc(value):
    if isinstance(value,datetime): d=value
    elif isinstance(value,str): d=datetime.fromisoformat(value.replace('Z','+00:00'))
    else: raise ValueError('timestamp required')
    if d.tzinfo is None: raise ValueError('timezone required')
    return d.astimezone(timezone.utc)

def architect_record(*, ticker, architect, kind, issue_time, source_time, version, payload, fallback=None, freshness_s=None):
    issued,source=utc(issue_time),utc(source_time)
    if not ticker or not architect or not version or kind not in KINDS: raise ValueError('missing identity/type')
    if source>issued: raise ValueError('future source time')
    if freshness_s is not None and (not math.isfinite(float(freshness_s)) or float(freshness_s)<0): raise ValueError('invalid freshness')
    return {'schema':SCHEMA,'contract_ticker':ticker,'architect':architect,'signal_type':kind,'issue_time_utc':issued.isoformat(), 'asof_source_time_utc':source.isoformat(), 'model_version':version,'payload':payload,'fallback_reason':fallback,'input_freshness_s':freshness_s}

def gt_forecasts(*,ticker,issue_time,anchor_time,anchor_price,predictions,version):
    """GT1 = candle following the anchor's completed minute; independent of chart offset."""
    issue,anchor=utc(issue_time),utc(anchor_time)
    if anchor>issue: raise ValueError('future anchor')
    if len(predictions)!=15: raise ValueError('GT1..GT15 required')
    start=anchor.replace(second=0,microsecond=0)+timedelta(minutes=1)
    out=[]
    for i,p in enumerate(predictions,1):
        candle_start=start+timedelta(minutes=i-1)
        if candle_start<issue.replace(second=0,microsecond=0): raise ValueError('forecast target already passed')
        if not all(k in p for k in ('open','high','low','close')): raise ValueError('missing OHLC')
        if p['high']<max(p['open'],p['close'],p['low']) or p['low']>min(p['open'],p['close'],p['high']): raise ValueError('invalid OHLC')
        out.append({'horizon':i,'candle_start_utc':candle_start.isoformat(),'candle_end_utc':(candle_start+timedelta(minutes=1)).isoformat(),'ohlc':dict(p)})
    return {'schema':SCHEMA,'contract_ticker':ticker,'model_version':version,'issue_time_utc':issue.isoformat(),'anchor_time_utc':anchor.isoformat(),'anchor_price':anchor_price,'gt':out}

def outcome_record(ticker,side,source,observed_time):
    if source not in LABELS or side not in ('ABOVE','BELOW'): raise ValueError('invalid outcome')
    return {'contract_ticker':ticker,'outcome':side,'outcome_source':source,'observed_time_utc':utc(observed_time).isoformat(),'official':source=='official_kalshi'}

def append_jsonl(path,record):
    """Append-only. Caller must supply an owned file path; never overwrite past predictions."""
    with open(path,'a',encoding='utf-8') as f: f.write(json.dumps(record,allow_nan=False,sort_keys=True)+'\n')


def safe_snapshot(source, *, platform, issue_time=None):
    """Allowlisted passive snapshot; no API keys, config, raw account state or orders."""
    from datetime import datetime, timezone
    if not isinstance(source,dict): raise ValueError('snapshot must be dict')
    market=source.get('market') if isinstance(source.get('market'),dict) else source
    now=utc(issue_time) if issue_time else datetime.now(timezone.utc)
    ticker=market.get('ticker')
    if not ticker: raise ValueError('ticker required')
    quote=market.get('quote_time') or source.get('quote_time')
    quote_time=None
    if quote:
        try: quote_time=utc(quote)
        except (TypeError,ValueError): pass
    def scalar(obj,fields):
        if not isinstance(obj,dict): return {}
        return {k:obj[k] for k in fields if k in obj and isinstance(obj.get(k),(str,int,float,bool,type(None)))}
    return {
      'schema':'BTC15M_PASSIVE_SAFE_V1','platform':platform,'issue_time_utc':now.isoformat(),
      'contract_ticker':ticker,'market':scalar(market,('target','brti','btc','seconds_left','brti_age_s','distance','feed_mode')),
      'source_time_utc':quote_time.isoformat() if quote_time else None,
      'source_time_valid':bool(quote_time and quote_time<=now),
      'decision':scalar(source.get('decision') or source.get('_predictive_decision'),('state','side','confidence','probability','fallback_reason')),
      'settlement':scalar(source.get('settlement') or source.get('settlement_forecast'),('state','side','confidence','probability')),
      'rollover':scalar(source.get('rollover_telemetry') or market,('next_ticker','next_prefetched','next_ticker_expected','next_prefetch_attempts','next_market_found','next_target_loaded','rollover_mode','rollover_latency_ms','fallback_discovery_used')),
      'of':scalar(source.get('validated_of') or source.get('orderflow'),('state','side','pressure','imbalance','age_s','reason')),
      'gt_timestamp_semantics':'unverified',
      'outcome_source':'unknown',
    }
