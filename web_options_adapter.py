"""Web experimental observer. External IV JSON file updated by an independently configured collector."""
import os,json,threading,time
from pathlib import Path
from options_challenger import evaluate,RegimeWatch
_lock=threading.RLock();_watch=RegimeWatch()
def observe(d):
    if os.getenv('BTC15M_OPTIONS_EXPERIMENT_ENABLED')!='1' or d.get('status')!='ok':return None
    m=d.get('market') or {}; em=d.get('execution_market') or {}
    if not m.get('ticker'):return None
    ivfile=os.getenv('BTC15M_OPTIONS_IV_FILE'); iv=None
    if ivfile:
        try:iv=json.loads(Path(ivfile).read_text())
        except (OSError,ValueError):pass
    now=time.time(); snap={'ticker':m.get('ticker'),'brti':m.get('brti'),'target':m.get('target'),
       'seconds_left':m.get('seconds_left'),'execution_market':em}
    row=evaluate(snap,iv,now=now)
    dec=d.get('decision') or {};state=dec.get('state') or dec.get('direction')
    row['regime_watch']=_watch.observe(m.get('ticker'),m.get('brti'),now,decision=state)
    row['gamma_zone']=bool(row['gamma_zone']);row['model_based_stop']='NOT_EVALUATED_NO_POSITION_LIFECYCLE'
    dest=os.getenv('BTC15M_OPTIONS_WEB_JOURNAL')
    if dest:
        with _lock:
            p=Path(dest);p.parent.mkdir(parents=True,exist_ok=True)
            with p.open('a',encoding='utf-8') as f:f.write(json.dumps(row,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())

    print(
        "WEB_OPTIONS_STATUS",
        json.dumps({
            "event": "observation_processed",
            "ticker": m.get("ticker"),
            "iv_available": iv is not None,
            "iv_venue": iv.get("venue") if isinstance(iv, dict) else None,
            "iv_source_time": iv.get("source_time") if isinstance(iv, dict) else None,
            "result": row.get("status"),
            "gamma_zone": row["gamma_zone"],
            "journal_configured": bool(dest)
        }),
        flush=True
    )
    return row