import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import collect_news as c

FAKE_RSS=b'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Research</title>
<item><title>Uncommon wins JD Sports account in London - Sample Trade</title>
<link>https://news.google.com/rss/articles/abc</link><pubDate>Sat, 07 Nov 2026 09:00:00 GMT</pubDate><source>Sample Trade</source></item>
<item><title>Talent management agency signs new sports roster in the UK - Sample Trade</title>
<link>https://news.google.com/rss/articles/tal</link><pubDate>Sat, 07 Nov 2026 09:00:00 GMT</pubDate><source>Sample Trade</source></item>
<item><title>Arsenal 2 - Liverpool 1 live score</title><link>https://news.google.com/rss/articles/def</link><pubDate>Sat, 07 Nov 2026 09:30:00 GMT</pubDate><source>Scores</source></item>
</channel></rss>'''
WHEN=dt.datetime(2026,11,7,21,tzinfo=dt.timezone.utc)

class CollectorTests(unittest.TestCase):
    def test_target_match_has_priority_and_region_is_evidenced(self):
        with patch.dict(os.environ,{'GATE_TARGET_AGENCIES':'Uncommon\nHomeground'},clear=False):
            a=c.parse_feed(FAKE_RSS,'Hitlist watch','UK/EMEA/US','hitlist')
            self.assertEqual(len(a),1)
            x=a[0]
            self.assertEqual(x['agency'],'Uncommon')
            self.assertTrue(x['target_match'])
            self.assertEqual(x['region'],'UK')
            self.assertEqual(x['type'],'Account win')
            self.assertEqual(x['priority'],'High')
            self.assertFalse(x['contacts'])
            self.assertNotIn('Homeground',json.dumps(x))

    def test_talent_feed_excludes_unrelated_scores(self):
        a=c.parse_feed(FAKE_RSS,'UK talent agencies','UK','talent',targets=[])
        self.assertEqual(len(a),1)
        self.assertTrue(a[0]['talent_signal'])
        self.assertEqual(a[0]['sector'],'Talent & representation')

    def test_news_locale_market_is_not_confirmed_region(self):
        self.assertIn('ceid=US%3Aen',c.rss_url('campaign','US'))
        self.assertIn('ceid=GB%3Aen',c.rss_url('campaign','UK'))
        self.assertEqual(c.headline_region('Creative agency wins airline work')[0],'To verify')

    def test_hitlist_rotates_without_leaking_names_to_feed_health(self):
        names=[f'Brand Agency {i}' for i in range(80)]
        s=c.get_searches(WHEN,names)
        self.assertEqual(len(s),len(c.MARKET_SEARCHES)+8)
        self.assertTrue(all('Brand Agency' not in label for label,*_ in s))
        self.assertNotEqual([q for _,q,*_ in s if 'Brand Agency' in q],[q for _,q,*_ in c.get_searches(WHEN+dt.timedelta(hours=1),names) if 'Brand Agency' in q])

    def test_respects_failure_and_deduplication(self):
        with tempfile.TemporaryDirectory() as t,patch.dict(os.environ,{'GATE_TARGET_AGENCIES':'Uncommon\nHomeground'},clear=False):
            p=Path(t)/'feed.json'
            result=c.run(fetcher=lambda _:FAKE_RSS,dest=p,now=WHEN)
            self.assertEqual(result['status'],'healthy')
            self.assertGreaterEqual(result['target_agency_count_configured'],2)
            self.assertEqual(len({x['id'] for x in result['items']}),len(result['items']))
            self.assertEqual(len(result['items']),2)
            with patch.dict(os.environ,{'GATE_TARGET_AGENCIES':''},clear=False):
                failed=c.run(fetcher=lambda _:(_ for _ in ()).throw(ValueError('unavailable')),dest=p,now=WHEN)
            self.assertEqual(failed['status'],'unavailable')
            self.assertEqual(failed['last_successful_fetch'],result['last_successful_fetch'])
            self.assertEqual(len(failed['items']),2)

if __name__=='__main__':unittest.main()