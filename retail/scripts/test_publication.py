import unittest,json
from pathlib import Path
from update import prepare
from engine import classify,community,composite
class Publication(unittest.TestCase):
 def fixture(self):
  return dict(summary=dict(date='2026-11-25',collected_at='2026-11-26T12:00:00+08:00',score=None),history=[dict(date='2026-11-25',model='retail-v1.0',score=None)],intraday=dict(date='2026-11-26',community=None),intraday_posts=[],groups=[dict(topic='大盘')],posts=[],channels=[],factors=[],trade_history=[],margin=[],statuses=[])
 def test_same_day_valid_history_survives_low_coverage(self):
  old=dict(history=[dict(date='2026-11-25',model='retail-v1.0',score=52.0)])
  result=prepare(self.fixture(),old)
  self.assertEqual(result['last_valid_daily']['score'],52.0)
  self.assertIsNone(result['summary']['score'])
 def test_no_private_identifiers(self):
  raw=self.fixture();raw['posts']=[dict(date='2026-11-25',platform='eastmoney',topic='大盘',text='示例表达'*50,direction=0,chase=False,panic=False,novice=False,evidence='',url='https://guba.eastmoney.com/',author='private-id')]
  post=prepare(raw,{})['posts'][0];self.assertNotIn('author',post);self.assertLessEqual(len(post['text']),100)
 def test_missing_is_not_neutral(self):
  d=prepare(self.fixture(),{});self.assertIsNone(d['last_valid_daily']);self.assertIsNone(d['intraday']['community']);self.assertEqual(d['intraday_groups'][0]['n'],0)
 def test_zero_and_threshold(self):
  a=[dict(platform='A',direction=-1,chase=False,panic=True,novice=False) for i in range(50)]
  c=community(a);self.assertEqual(c['score'],0);self.assertFalse(c['reliable']);self.assertIsNone(composite(c,50,True))
if __name__=='__main__':unittest.main()
