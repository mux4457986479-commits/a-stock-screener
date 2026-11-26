import json,re,csv,hashlib,statistics,urllib.request,urllib.parse,os,sys
from pathlib import Path
from datetime import datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor,as_completed
from collections import Counter
from engine import *
R=Path(__file__).parent; TZ=timezone(timedelta(hours=8)); NOW=datetime.now(TZ)
RAW=R/'raw'/NOW.strftime('%Y%m%d_%H%M%S');RAW.mkdir(parents=True,exist_ok=True)
BASKETS={'大盘':['zssh000001','zssz399001','zssz399006'],'国产算力':['688256','688041'],'PCB与电子材料':['002463','600183'],'光通信':['300308','300394'],'半导体材料':['688019','300054'],'存储':['603986','688525']}
LABELS={'eastmoney':'东方财富股吧','sina':'新浪股吧','taoguba':'淘股吧','NGA':'NGA手工导入','小红书':'小红书手工导入'}
headers={'User-Agent':'Mozilla/5.0','Accept':'application/json,text/html,*/*'}
statuses=[];posts=[]
def fetch(url,key):
 req=urllib.request.Request(url,headers={**headers,'Referer':'https://guba.eastmoney.com/' if 'eastmoney' in url else url})
 with urllib.request.urlopen(req,timeout=16) as f:b=f.read(); enc=f.headers.get_content_charset() or 'utf-8'
 t=b.decode(enc,errors='replace');(RAW/(key+'.txt')).write_text(t,encoding='utf-8');return t
def dt(v):
 try:
  if isinstance(v,(int,float)) or str(v).isdigit():return datetime.fromtimestamp(float(v)/(1000 if float(v)>1e11 else 1),TZ)
  a=datetime.fromisoformat(str(v).replace('Z','+00:00'));return a.replace(tzinfo=TZ) if a.tzinfo is None else a.astimezone(TZ)
 except:return None
def prefix(code):return code.replace('zssh','sh').replace('zssz','sz') if code.startswith('zs') else ('sh' if code.startswith('6') else 'sz')+code
def make(row,platform,topic,code):
 if platform=='eastmoney':
  if int(row.get('post_type',-1)) not in (0,42) or row.get('post_source_id') or str(row.get('v_user_code','0')) not in ('','0'):return None
  text=row.get('post_title','');user=row.get('user_nickname','');aid=row.get('user_id',user);date=dt(row.get('post_publish_time'));url=f"https://guba.eastmoney.com/news,{code},{row.get('post_id')}.html"
 elif platform=='taoguba':
  if row.get('auth') not in (None,0,'0') or (row.get('userTitle') or {}).get('title'):return None
  text=row.get('body') or row.get('subject','');user=row.get('userName','');aid=row.get('userID',user);date=dt(row.get('actionDate'));url='https://www.tgb.cn/quotes/'+prefix(code)
 else:
  u=row.get('user') or {}
  if u.get('verified') not in (False,None,0,'0',''):return None
  text=row.get('title') or row.get('content','');user=u.get('nick') or u.get('name','');aid=u.get('uid') or row.get('tid');date=dt(row.get('timestamp') or row.get('ctime'));url=f"https://guba.sina.cn/?s=thread&bid={row.get('bid','')}&tid={row.get('tid','')}"
 text=clean(text)
 if not date or len(normalize(text))<6 or len(text)>500 or any(w in text for w in SPAM):return None
 if any(w in str(user) for w in ['官方','证券','投顾','资讯','财富号','数据宝','基金经理']):return None
 return dict(platform=platform,topic=topic,code=code,text=text,date=date.strftime('%Y-%m-%d'),published=date.isoformat(),author=hashlib.sha256((platform+str(aid)).encode()).hexdigest()[:16],url=url,**classify(text))
def source_job(topic,code,platform):
 out=[];url='';rawcount=0
 try:
  if platform=='eastmoney':
   for page in (1,2):
    url='https://gbapi.eastmoney.com/webarticlelist/api/Article/Articlelist?'+urllib.parse.urlencode({'code':code,'sorttype':1,'ps':100,'p':page,'from':'CommonBaPost','version':200,'product':'Guba','plat':'Web'})
    j=json.loads(fetch(url,f'em_{code}_{page}'));rs=j.get('re')
    if not isinstance(rs,list):raise ValueError('返回非帖子列表')
    rawcount+=len(rs)
    out.extend(x for x in (make(r,platform,topic,code) for r in rs) if x)
  elif platform=='taoguba':
   url='https://www.tgb.cn/quotes/'+prefix(code);text=fetch(url,f'tgb_{code}')
   m=re.search(r'var\s+coolAttr\s*=\s*(\[.*?\])\s*;',text,re.S)
   if not m:raise ValueError('未找到匿名讨论列表，未绕过访问限制')
   rs=json.loads(m[1]);rawcount=len(rs);out=[x for x in (make(r,platform,topic,code) for r in rs) if x]
  else:
   url='https://guba.sina.cn/?s=bar&name='+prefix(code);text=fetch(url,'sina_'+code)
   m=re.search(r'data-bid="(\d+)"',text)
   if not m:raise ValueError('未找到公开板块编号')
   url='https://guba.sina.cn/api/?'+urllib.parse.urlencode({'s':'h5bar','bid':m[1],'num':50})
   rs=json.loads(fetch(url,'sina_api_'+code)).get('data',{}).get('threads',[]);rawcount=len(rs)
   out=[x for x in (make(r,platform,topic,code) for r in rs) if x]
  return out,dict(topic=topic,code=code,platform=platform,url=url,status='成功' if rawcount else '空列表',raw_count=rawcount,filtered_count=len(out),note='有页数上限；非全量社区，非随机抽样')
 except Exception as e:return [],dict(topic=topic,code=code,platform=platform,url=url,status='失败',raw_count=None,filtered_count=0,note=str(e)[:130])
def main():
 market=[];series={};market_status=[]
 for symbol,label in [('sh000001','上证指数'),('sz399006','创业板指'),('sh000300','沪深300')]:
  try:
   u='https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param='+symbol+',day,,,100,qfq'
   j=json.loads(fetch(u,'kline_'+symbol))['data'][symbol];rs=j.get('day') or j.get('qfqday')
   if not rs or len(rs)<25:raise ValueError('日线不足')
   series[label]=[dict(date=r[0],close=float(r[2]),volume=float(r[5])) for r in rs]
   market_status.append(dict(platform='腾讯日线',status='成功',url=u,note=f'{len(rs)}条，截止{rs[-1][0]}'))
  except Exception as e:market_status.append(dict(platform='腾讯日线',status='失败',url=u,note=str(e)))
 dates=[rs[-1]['date'] for rs in series.values()];anchor=min(dates) if dates else (NOW-timedelta(days=1)).date().isoformat()
 # Date is anchored to the latest completed market session, never the machine UTC day.
 if anchor==NOW.date().isoformat() and (NOW.hour,NOW.minute)<(15,10):
  anchor=max(r['date'] for rs in series.values() for r in rs if r['date']<anchor)
 margin=[]
 try:
  u='https://data.10jqka.com.cn/market/rzrq/client/on/';t=fetch(u,'margin')
  for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',t,re.S):
   vals=[clean(v) for v in re.findall(r'<td\b[^>]*>(.*?)</td>',row,re.S)]
   if len(vals)!=17 or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',vals[0]):continue
   def num(v):
    try:return float(v.replace(',',''))
    except:return None
   nums=list(map(num,vals[1:]));complete=all(nums[i] is not None for i in [0,1,2,3,4,5,6,7])
   if not complete:continue
   if abs(sum(nums[:3])-nums[3])>.06:continue
   if vals[0]<=anchor:margin.append(dict(date=vals[0],balance=nums[3],buy=nums[7]))
  margin.sort(key=lambda r:r['date'])
  for i in range(1,len(margin)):
   r=margin[i];r['net']=r['balance']-margin[i-1]['balance'];r['repay']=r['buy']-r['net'];r['score']=100*r['buy']/(r['buy']+r['repay']) if r['repay']>=0 else None
  market_status.append(dict(platform='同花顺两融',status='成功' if margin else '无完整行',url=u,note='沪深北完整汇总；缺失市场不当成0；余额/买入/偿还单位亿元'))
 except Exception as e:market_status.append(dict(platform='同花顺两融',status='失败',url=u,note=str(e)))
 tasks=[(topic,c,p) for topic,cs in BASKETS.items() for c in cs for p in ('eastmoney','taoguba')]
 tasks += [('大盘',c,'sina') for c in BASKETS['大盘']]
 with ThreadPoolExecutor(max_workers=4) as ex:
  for fut in as_completed([ex.submit(source_job,*args) for args in tasks]):
   ps,st=fut.result();posts.extend(ps);statuses.append(st);print(st['platform'],st.get('code'),st['status'],len(ps),flush=True)
 # Manual public-text imports are additive; they never masquerade as automatic collection.
 imp=R/'imports';imp.mkdir(exist_ok=True)
 for file in imp.glob('*.csv'):
  for r in csv.DictReader(file.open(encoding='utf-8-sig')):
   text=clean(r.get('text',''));p=r.get('platform','手工导入');date=r.get('date','')
   if len(normalize(text))<6 or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date):continue
   posts.append(dict(platform=p,topic=r.get('topic') or '大盘',code='',text=text,date=date,published=date+'T12:00:00+08:00',author=hashlib.sha256((p+r.get('author',normalize(text))).encode()).hexdigest()[:16],url=r.get('url',''),**classify(text)))
 # Today's community is a separate intraday observation; never mix it with yesterday's trading score.
 today=NOW.date().isoformat();today_posts=[];seen_today=set();author_today=Counter()
 for post in sorted(posts,key=lambda x:x['published'],reverse=True):
  if post['date']!=today or post['published']>NOW.isoformat():continue
  key=normalize(post['text']);author=(post['platform'],post['author'])
  if key in seen_today or author_today[author]>=3:continue
  seen_today.add(key);author_today[author]+=1;today_posts.append(post)
 intraday=community([post for post in today_posts if post['topic']=='大盘'])
 intraday_summary=dict(date=today,collected_at=NOW.isoformat(),community=intraday['score'] if intraday['reliable'] else None,n=intraday['n'],platforms=intraday['qualified'],reliable=intraday['reliable'],chase=intraday['chase'],panic=intraday['panic'],note='当日社区样本，未与上一交易日交易分合成')
 # Global text dedup prevents reposts and cross-board copying from receiving extra votes.
 seen=set();counts=Counter();valid=[]
 for p in sorted(posts,key=lambda x:x['published'],reverse=True):
  if p['date']!=anchor:continue
  key=normalize(p['text']);a=(p['platform'],p['author'],p['date'])
  if key in seen or counts[a]>=3:continue
  seen.add(key);counts[a]+=1;valid.append(p)
 groups=[]
 for topic in BASKETS:
  ps=[p for p in valid if p['topic']==topic];c=community(ps)
  groups.append(dict(topic=topic,**{k:v for k,v in c.items() if k!='parts'},coverage='跨平台样本达标' if c['reliable'] else '覆盖不足，仅供观察'))
 channel_rows=[]
 for topic in BASKETS:
  for platform in sorted(set(('eastmoney','sina','taoguba','NGA','小红书'))|{p['platform'] for p in valid}):
   x=summarize([p for p in valid if p['topic']==topic and p['platform']==platform]);channel_rows.append(dict(topic=topic,platform=LABELS.get(platform,platform),**x,status='已采集' if x['n'] else '未取得有效样本'))
 trade_history=[];factors=[]
 common=sorted(set(r['date'] for rs in series.values() for r in rs if r['date']<=anchor))
 for day in common:
  f=[];mom=[];vp=[]
  for label,rs in series.items():
   a=[r for r in rs if r['date']<=day]
   if len(a)<25:continue
   ret=(a[-1]['close']/a[-6]['close']-1)*100;v=percentile(a[-1]['volume'],[r['volume'] for r in a[-61:-1]])
   mom.append(clamp(50+5*ret))
   if v is not None:vp.append(v)
  eligible=[r for r in margin if r['date']<=day and r.get('score') is not None];mar=eligible[-1] if eligible else None
  lag=(datetime.fromisoformat(day)-datetime.fromisoformat(mar['date'])).days if mar else None
  if mom:f.append(('五日动量',statistics.mean(mom),day,'三指数5日收益经50+5×收益百分点映射，限制在0—100'))
  if vp:f.append(('成交活跃度',statistics.mean(vp),day,'三指数成交量相对各自此前最多60日的中位秩百分位；不代表散户专属成交'))
  if mar and lag<=4:f.append(('融资买偿强度',mar['score'],mar['date'],'100×融资买入/(买入+偿还)，中性50；偿还由余额差推算'))
  score=statistics.mean(x[1] for x in f) if len(f)==3 and len(series)==3 else None
  trade_history.append(dict(date=day,trade=score,momentum=statistics.mean(mom) if mom else None,activity=statistics.mean(vp) if vp else None,financing=mar['score'] if mar and lag<=4 else None))
  if day==anchor:factors=[dict(name=a,score=b,date=c,definition=e) for a,b,c,e in f]
 current=next((r for r in trade_history if r['date']==anchor),{})
 comm=community([p for p in valid if p['topic']=='大盘']);mix=composite(comm,current.get('trade'),True)
 summary=dict(date=anchor,collected_at=NOW.isoformat(),score=mix,community=comm['score'],trade=current.get('trade'),posts=len(valid),market_posts=comm['n'],platforms=comm['qualified'],coverage='可计算研究指数' if mix is not None else '数据覆盖不足，综合分暂不发布',model=VERSION)
 # Preserve the last good snapshot before every refresh; never silently erase it.
 old=R/'latest.json'
 if old.exists():
  backup=R/'backups';backup.mkdir(exist_ok=True)
  (backup/(NOW.strftime('%Y%m%d_%H%M%S')+'_latest.json')).write_bytes(old.read_bytes())
 if not valid or not series:
  (R/'last_failure.json').write_text(json.dumps(dict(collected_at=NOW.isoformat(),statuses=statuses+market_status),ensure_ascii=False,indent=2),encoding='utf-8')
  raise RuntimeError('公开数据采集失败：保留上次有效数据，未重写 latest.json。详见 last_failure.json')
 history_path=R/'history.json';history=json.loads(history_path.read_text(encoding='utf-8')) if history_path.exists() else []
 history=[r for r in history if r['date']!=anchor or r.get('model')!=VERSION];history.append(summary);history.sort(key=lambda r:r['date'])
 history_path.write_text(json.dumps(history,ensure_ascii=False,indent=2),encoding='utf-8')
 reviewed=dict(intraday=intraday_summary,intraday_posts=today_posts,summary=summary,groups=groups,channels=channel_rows,factors=factors,trade_history=trade_history,history=history,margin=margin,statuses=statuses+market_status,posts=valid)
 (R/'latest.json').write_text(json.dumps(reviewed,ensure_ascii=False,indent=2),encoding='utf-8')
 with (R/'帖子审阅.csv').open('w',encoding='utf-8-sig',newline='') as f:
  fields=['date','platform','topic','text','direction','chase','panic','novice','evidence','url'];w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader()
  for p in valid:w.writerow({k:("'"+v if isinstance(v,str) and v[:1] in '=+-@' else v) for k,v in p.items()})
 print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
