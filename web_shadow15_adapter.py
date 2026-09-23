"""Opt-in Web integration adapter, observation-only. No orders, fills or real trading."""
import os, threading
from datetime import datetime, timezone
from pathlib import Path
from durable15 import Durable15
_LOCK=threading.RLock()
_JOURNAL=None
_FIELDS=('decision','settlement','ghost_thread_recursive','structure','orderflow','multi_orderflow','l2','exhaustion_reversal','profit_reversal_risk')
def normalized_snapshot(d, now=None, sequence=None):
    if not isinstance(d,dict) or d.get('status')!='ok': return None
    m=d.get('market') or {}; em=d.get('execution_market') or {}
    if not m.get('ticker'): return None
    t=now or datetime.now(timezone.utc).isoformat()
    snap={'ticker':m.get('ticker'),'logged_at_utc':t,'server_time':d.get('server_time'),
          'state_sequence':sequence if sequence is not None else d.get('state_sequence'),
          'target':m.get('target'),'brti':m.get('brti'),'seconds_left':m.get('seconds_left'),
          'execution_market':{k:em.get(k) for k in ('yes_bid','yes_ask','no_bid','no_ask','book_healthy','book_sid','book_seq','timestamp_utc','transport')}}
    snap.update({k:d.get(k) for k in _FIELDS})
    return snap
def observe_web_state(d, journal_path=None, now=None, sequence=None):
    """Called only from an opt-in worker hook; fail closed and propagate errors to caller."""
    global _JOURNAL
    if os.getenv('BTC15M_SHADOW15_OBSERVER_ENABLED')!='1':return []
    snap=normalized_snapshot(d,now,sequence)
    if snap is None:return []
    with _LOCK:
        path=str(journal_path or os.getenv('BTC15M_SHADOW15_JOURNAL','/var/data/btc15m_shadow15.ndjson'))
        if _JOURNAL is None:_JOURNAL=Durable15(path)
        elif str(_JOURNAL.path)!=path:raise RuntimeError('journal path changed: refuse unsafe state switch')
        return _JOURNAL.observe(snap)
def shutdown():
    global _JOURNAL
    with _LOCK:
        if _JOURNAL is not None:_JOURNAL.close();_JOURNAL=None
