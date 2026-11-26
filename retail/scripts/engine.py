"""Transparent research rules. Scores are not calibrated probabilities or trade signals."""
import re,html,math,statistics
VERSION='retail-v1.0'
POS=['看多','看好','牛市','上涨','大涨','起飞','涨停','反转','反弹','加仓','买入','抄底','低吸','黄金坑','必涨','新高']
NEG=['看空','熊市','下跌','暴跌','跌停','崩盘','割肉','清仓','减仓','卖出','爆仓','破位','阴跌','亏死','套牢','逃命']
CHASE=['梭哈','满仓干','追涨','追高','踏空','闭眼买','必涨','翻倍','抢筹','最后上车']
PANIC=['爆仓','崩盘','割肉','救命','绝望','亏死','血亏','清仓','不玩了','退出股市','销户','腰斩']
NOVICE=['新手','小白','刚开户','第一次买','能买吗','该买吗','该卖吗','求带','怎么开户','不懂股票','怎么操作']
SPAM=['加微信','加薇','进群','扫码','开户链接','老师带','私信领取','免费荐股']
def clean(s):return html.unescape(re.sub('<[^>]+>',' ',str(s))).strip()
def normalize(s):return re.sub(r'[\W_]+','',clean(s)).lower()
def hits(text,words):
 out=[]
 for word in words:
  for m in re.finditer(re.escape(word),text):
   prefix=text[max(0,m.start()-4):m.start()]
   # Negated or questioned cues are not direct directional assertions.
   if re.search(r'(不|没|别|勿|避免|不能|不要|并非|不是).{0,2}$',prefix):continue
   if re.match(r'(吗|么|？|\?)',text[m.end():]):continue
   out.append(word);break
 return out
def classify(text):
 text=clean(text);p=hits(text,POS);n=hits(text,NEG)
 # Explicit quoted/cautionary expressions are excluded from cue classification.
 chase=hits(text,CHASE);panic=hits(text,PANIC)
 return dict(direction=1 if len(p)>len(n) else -1 if len(n)>len(p) else 0,
             chase=bool(chase),panic=bool(panic),novice=bool(hits(text,NOVICE)),
             evidence='、'.join(p+n+chase+panic)[:90])
def summarize(posts):
 n=len(posts)
 if not n:return dict(n=0,score=None,chase=None,panic=None,novice=None,bull=0,bear=0,neutral=0)
 b=sum(p['direction']>0 for p in posts);a=sum(p['direction']<0 for p in posts)
 return dict(n=n,score=50+50*(b-a)/n,chase=100*sum(p['chase'] for p in posts)/n,
             panic=100*sum(p['panic'] for p in posts)/n,novice=100*sum(p['novice'] for p in posts)/n,bull=b,bear=a,neutral=n-b-a)
def community(posts):
 platforms=sorted(set(p['platform'] for p in posts));parts={p:summarize([x for x in posts if x['platform']==p]) for p in platforms}
 usable=[v for v in parts.values() if v['n']>=10]
 score=statistics.mean(x['score'] for x in usable) if usable else None
 return dict(score=score,qualified=len(usable),parts=parts,reliable=len(usable)>=2 and len(posts)>=50,**{k:v for k,v in summarize(posts).items() if k!='score'})
def percentile(value,history):
 return 100*(sum(v<value for v in history)+.5*sum(v==value for v in history))/len(history) if len(history)>=20 else None
def clamp(x):return max(0,min(100,x))
def composite(comm,trade,lag_ok):
 if not comm['reliable'] or trade is None or not lag_ok:return None
 return .6*comm['score']+.4*trade
