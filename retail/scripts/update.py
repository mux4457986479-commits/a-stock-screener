"""Publish anonymous aggregates; raw responses and author identifiers never enter Pages data."""
from pathlib import Path
import json,sys,tempfile,subprocess,shutil,argparse,os
from datetime import datetime,timezone,timedelta
from engine import community,summarize,VERSION
R=Path(__file__).resolve().parents[1];TZ=timezone(timedelta(hours=8))
def load(p,default):
 try:return json.loads(p.read_text(encoding='utf-8-sig'))
 except (FileNotFoundError,json.JSONDecodeError):return default

def atomic(p,d):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8');os.replace(tmp,p)

def prepare(raw,prior):
 history={r['date']:r for r in prior.get('history',[]) if r.get('model')==VERSION}
 for row in raw.get('history',[]):
  old=history.get(row['date'])
  if row.get('score') is not None or not old or old.get('score') is None:history[row['date']]=row
 today=raw.get('intraday',{});ps=raw.get('intraday_posts',[]);topics=[r['topic'] for r in raw['groups']]
 groups=[];channels=[]
 for topic in topics:
  scoped=[p for p in ps if p['topic']==topic];c=community(scoped)
  groups.append(dict(topic=topic,score=c['score'],n=c['n'],qualified=c['qualified'],reliable=c['reliable'],chase=c['chase'],panic=c['panic'],novice=c['novice']))
  for platform in sorted(set(p['platform'] for p in scoped)):
   channels.append(dict(topic=topic,platform=platform,**summarize([p for p in scoped if p['platform']==platform])))
 intrahistory=prior.get('community_history',[])
 if today.get('date'):
  intrahistory=[r for r in intrahistory if r['date']!=today['date']];intrahistory.append(today)
 intrahistory=sorted(intrahistory,key=lambda r:r['date'])[-180:]
 # Short public excerpts, no handles, author hashes, IDs or private credentials.
 def excerpts(posts):
  return [dict(date=p['date'],platform=p['platform'],topic=p['topic'],text=p['text'][:100],direction=p['direction'],chase=p['chase'],panic=p['panic'],novice=p['novice'],evidence=p['evidence'],url=p['url']) for p in posts[:300]]
 h=sorted(history.values(),key=lambda r:r['date'])[-180:]
 return dict(schema_version=1,model=VERSION,generated_at=raw['summary']['collected_at'],summary=raw['summary'],intraday=today,last_valid_daily=next((r for r in reversed(h) if r.get('score') is not None),None),history=h,community_history=intrahistory,groups=raw['groups'],intraday_groups=groups,channels=raw['channels'],intraday_channels=channels,factors=raw['factors'],trade_history=raw['trade_history'][-80:],margin=raw['margin'],statuses=raw['statuses'],posts=excerpts(raw['posts']),intraday_posts=excerpts(ps),update=dict(ok=True,attempted_at=raw['summary']['collected_at'],message='采集完成；是否发布综合分取决于覆盖门槛'),schedule='沿用低价股看板任务：北京时间工作日09:00—15:30每30分钟云端采集；GitHub排队可能延迟。页面刷新仅重读已发布快照。')

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--input');args=ap.parse_args();dest=R/'data.json';prior=load(dest,{})
 try:
  if args.input:raw=load(Path(args.input),{})
  else:
   with tempfile.TemporaryDirectory(prefix='retail-pulse-') as td:
    t=Path(td)
    for name in ['collect.py','engine.py']:shutil.copyfile(R/'scripts'/name,t/name)
    if prior.get('history'):atomic(t/'history.json',prior['history'])
    subprocess.run([sys.executable,str(t/'collect.py')],check=True,timeout=300)
    raw=load(t/'latest.json',{})
  data=prepare(raw,prior);atomic(dest,data)
  print(json.dumps(dict(date=data['summary']['date'],score=data['summary']['score'],intraday=data['intraday'],history=len(data['history'])),ensure_ascii=False))
 except Exception as e:
  if prior:
   prior['update']=dict(ok=False,attempted_at=datetime.now(TZ).isoformat(),message='本次更新失败，保留上次数据：'+type(e).__name__);atomic(dest,prior)
  print('Update failed; prior snapshot retained:',type(e).__name__,file=sys.stderr);return 1
 return 0
if __name__=='__main__':sys.exit(main())
