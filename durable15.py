"""Research-only deterministic 15-policy journal. Replays source snapshots on restart."""
import json,hashlib,os,fcntl
from pathlib import Path
from shadow15 import Shadow15
class CorruptJournal(RuntimeError):pass
class Durable15:
 def __init__(self,path,**cfg):
  self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.fd=os.open(str(path)+'.lock',os.O_CREAT|os.O_RDWR,0o600)
  try:fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:os.close(self.fd);raise RuntimeError('single writer only')
  self.engine=Shadow15(**cfg);self.count=0;self.digest='0'*64;self.keys=set();self.evaluations=0
  try:self._recover()
  except BaseException:self.close();raise
 def close(self):
  if getattr(self,'fd',None) is not None:fcntl.flock(self.fd,fcntl.LOCK_UN);os.close(self.fd);self.fd=None
 def _recover(self):
  if not self.path.exists():return
  for line in self.path.read_bytes().splitlines(keepends=True):
   if not line.endswith(b'\n'):raise CorruptJournal('truncated record')
   try:
    r=json.loads(line);body=json.dumps({'seq':r['seq'],'prev':r['prev'],'snapshot':r['snapshot'],'key':r['key']},sort_keys=True,separators=(',',':')).encode()
    if r['seq']!=self.count+1 or r['prev']!=self.digest or hashlib.sha256(body).hexdigest()!=r['digest'] or r['key'] in self.keys:raise CorruptJournal('journal chain or duplicate invalid')
    events=self.engine.evaluate(r['snapshot']);self.evaluations+=len(events);self.keys.add(r['key']);self.count+=1;self.digest=r['digest']
   except (KeyError,ValueError,TypeError) as e:raise CorruptJournal('malformed record') from e
 def observe(self,snapshot):
  key=hashlib.sha256(json.dumps([snapshot.get('ticker'),snapshot.get('state_sequence'),snapshot.get('logged_at_utc'),(snapshot.get('execution_market') or {}).get('book_sid'),(snapshot.get('execution_market') or {}).get('book_seq')],sort_keys=True).encode()).hexdigest()
  if key in self.keys:return []
  # Validate on a copied state before committing.
  import copy
  trial=copy.deepcopy(self.engine);events=trial.evaluate(snapshot)
  body={'seq':self.count+1,'prev':self.digest,'snapshot':snapshot,'key':key};encoded=json.dumps(body,sort_keys=True,separators=(',',':')).encode();digest=hashlib.sha256(encoded).hexdigest()
  line=json.dumps({**body,'digest':digest},sort_keys=True,separators=(',',':')).encode()+b'\n'
  with self.path.open('ab') as f:f.write(line);f.flush();os.fsync(f.fileno())
  self.engine=trial;self.keys.add(key);self.count+=1;self.digest=digest;self.evaluations+=len(events)
  return events
