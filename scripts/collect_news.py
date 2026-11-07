#!/usr/bin/env python3
"""GATE RADAR: free RSS headline collector, no scraping of article bodies.

Search feeds from Google News RSS (community-documented, no SLA). Only source-
linked headlines, publisher attribution and cautious BD suggestions are produced.
No personal data harvesting or invented contact details.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'feed.json'
NOW = lambda: dt.datetime.now(dt.timezone.utc)

SEARCHES = [
    ('Agency account wins', '("creative agency" OR "advertising agency") (appointed OR wins OR account) when:7d'),
    ('Agency appointments', '("agency of record" OR "creative account" OR "media account") (brand OR appoints OR pitch) when:7d'),
    ('Sport & culture', '(sportswear OR football OR athlete OR sponsorship) (campaign OR agency OR activation) when:7d'),
    ('Film production', '("production company" OR "film production" OR "commercial director") (campaign OR advertising OR signs) when:7d'),
    ('Creative campaigns', '("creative campaign" OR "brand film" OR "TV commercial") (agency OR production) when:7d'),
    ('Social & content', '("social-first" OR "social content" OR "branded content") (brand OR agency) when:7d'),
    ('Agency people', '("creative agency" OR "production company") ("head of production" OR "executive producer" OR appointment) when:7d'),
    ('Entertainment & culture', '("entertainment brand" OR "music campaign" OR "culture campaign") (agency OR content OR production) when:7d'),
    ('Retail & consumer brands', '(retailer OR beauty OR fashion OR hospitality) ("creative agency" OR "campaign launch") when:7d'),
    ('New briefs & tenders', '("video production" OR "film production" OR "content production") (tender OR RFP OR procurement) when:7d'),
]

BRANDS = [
    'JD Sports','Sports Direct','Nike','Adidas','Arsenal','Tottenham','Manchester United',
    'Red Bull','Under Armour','Puma','New Balance','On Running','M&S','Marks & Spencer',
    'BBC','Channel 4','ITV','Sky','Lego','Netflix','Amazon','Uber','Spotify','Durex',
    'Coca-Cola','Pepsi','McDonald\'s','Samsung','Apple','Cadbury','Unilever','Diageo',
    'Hollywood Bowl', 'Crufts', 'TikTok', 'YouTube'
]
AGENCIES = [
    'Uncommon','Homeground','Axe + Saw','Tommy','JOAN','McCann','We Are Social',
    'Dark Horses','M&C Saatchi','Havas','BBH','VCCP','Mother','WPP','Publicis',
    'Ogilvy','MSQ','The Romans','AMV BBDO','Saatchi & Saatchi','Leo Burnett',
    'Chaos x Magic','Wieden+Kennedy','Spin','One Day','VML','St Luke\'s'
]

# Words used to reject generic sports scores/general news from broad queries.
SIGNAL_TERMS = re.compile(r'\b(agency|agencies|campaign|brand|creative|production|film\w*|commercial\w*|advertis\w*|market\w*|appoint\w*|account|brief|content|social|partnership|sponsor\w*|director\w*|roster|tender|pitch|client|shoot\w*|studio|launch\w*|wins|awards)\b', re.I)
JUNK_TERMS = re.compile(r'\b(match report|fixture list|premier league table|live score|transfer rumour|stock price)\b', re.I)


def clean(value: str) -> str:
    v = re.sub(r'<[^>]+>', ' ', str(value or ''))
    return re.sub(r'\s+', ' ', html.unescape(v)).strip()


def safe_url(value: str) -> str:
    try:
        x = urllib.parse.urlparse((value or '').strip())
        return x.geturl() if x.scheme in ('https','http') and x.netloc else ''
    except Exception:
        return ''


def iso_date(value: str) -> str | None:
    from email.utils import parsedate_to_datetime
    try:
        d = parsedate_to_datetime(value)
        if not d.tzinfo: d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc).date().isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


def matches(title: str, names: list[str]) -> list[str]:
    found = []
    for n in names:
        if re.search(r'(?<![a-zA-Z0-9])' + re.escape(n) + r'(?![a-zA-Z0-9])', title, re.I):
            found.append(n)
    return found


def classify(title: str, group: str):
    t = title.lower()
    if re.search(r'\b(tender|rfp|invitation to tender|procurement notice)\b',t): return 'Tender'
    if re.search(r'\b(appoints?|appointed|agency of record|account win|wins (the |a |its )?account|awards? (the |its )?account|pitch win|names? .* agency)\b', t): return 'Account win'
    if re.search(r'\b(hired|joins|promoted|named .* head|new .* director|new .* chief|signs .* director|launches? .* studio)\b',t): return 'Industry move'
    if re.search(r'\b(campaign|film|commercial|advert|spot|launch|activation)\b',t): return 'Campaign'
    return 'Industry news'


def intelligence(title: str, group: str) -> dict:
    typ = classify(title,group)
    low = title.lower()
    sector = 'Sport & culture' if re.search(r'\b(sport|football|athlete|sponsor|nike|adidas|arsenal|tottenham|manchester united|cricket|rugby)\b',low) else ('Entertainment & culture' if re.search(r'\b(music|entertainment|film festival|gaming|culture)\b',low) else 'Creative & production')
    reasons=[];score=20
    if typ=='Account win':score+=40;reasons.append('Possible new agency–brand relationship')
    if typ=='Tender':score+=40;reasons.append('Potential procurement lead — eligibility unknown')
    if sector=='Sport & culture':score+=18;reasons.append('Sports sector fit')
    if re.search(r'\b(production|shoot|filmmak|commercial|branded content|film)\b',low):score+=13;reasons.append('Production adjacency')
    if typ=='Campaign':score+=9;reasons.append('Campaign conversation starter')
    if typ=='Industry move':score+=6;reasons.append('Potential relationship-building moment')
    if re.search(r'\b(social|short.form|digital|video|content)\b',low):score+=8;reasons.append('Content / social relevance')
    if not reasons: reasons=['Relevant industry headline; qualify production fit']
    score=min(score,95)
    if typ=='Account win':
        angle='New account relationships can trigger future film and content needs. Find out who commissions production, whether partners are already appointed, and what is planned next.'
        ask='Congratulations on the account news. How are you thinking about production support as the relationship develops?'
    elif typ=='Campaign':
        angle='The announced campaign may already be delivered. Use the work as a tailored conversation starter about future shoots, social cutdowns and overflow production.'
        ask='I saw the recently announced campaign. How do you usually resource the wider content and future production around work like this?'
    elif typ=='Industry move':
        angle='A team or leadership change can be a reason to build a relationship. Understand their remit before assuming they influence supplier selection.'
        ask='Congratulations on the news. I would love to understand the team’s upcoming priorities and where external production support fits.'
    elif typ=='Tender':
        angle='A potential procurement signal. Verify the official notice, buyer, deadlines, scope, budget and eligibility before treating this as a bid.'
        ask='I noticed this possible production procurement. Is there a live opportunity and an official brief we can review?'
    else:
        angle='Research the companies and commissioning roles involved, then check whether GATE has a credible production fit.'
        ask='I came across this news and thought there could be an interesting crossover with our film and content production work. How do you approach that side of projects?'
    return dict(type=typ, priority='High' if score>=65 else 'Medium', sector=sector,
                signal_score=score, signal_reasons=reasons, angle=angle, ask=ask,
                caution='Source-linked headline only. The story has not been independently fact-checked by GATE; an open production brief or available budget is NOT confirmed.')


def rss_url(query):
    return 'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q':query,'hl':'en-GB','gl':'GB','ceid':'GB:en'})


def parse_feed(raw: bytes, label: str) -> list[dict]:
    root=ET.fromstring(raw)
    entries=[]
    for item in root.findall('.//item'):
        title=clean(item.findtext('title'))
        link=safe_url(clean(item.findtext('link')))
        if not title or not link or not SIGNAL_TERMS.search(title) or JUNK_TERMS.search(title): continue
        publisher_node=item.find('source')
        publisher=clean(publisher_node.text if publisher_node is not None else '') or 'Publisher not identified'
        p_url=safe_url(publisher_node.attrib.get('url','')) if publisher_node is not None else ''
        # The aggregator usually appends the publisher name after a hyphen.
        if title.endswith(' - '+publisher):title=title[:-(len(publisher)+3)].strip()
        date=iso_date(item.findtext('pubDate'))
        if not date:continue  # no fabricated dates
        obj=intelligence(title,label)
        brand_names=matches(title,BRANDS); agency_names=matches(title,AGENCIES)
        normalized=re.sub(r'\W+',' ', title.lower()).strip()
        obj.update({
            'id':'rss-'+hashlib.sha256(normalized.encode()).hexdigest()[:16],
            'date':date,'title':title[:280],
            'summary':'Source-linked headline from '+publisher+'. Open the original report to confirm details, production credits and timing.',
            'agency':', '.join(agency_names) if agency_names else 'Agency to confirm',
            'brand':', '.join(brand_names) if brand_names else 'Brand to confirm',
            'production':'Not established by headline',
            'source':{'label':publisher,'url':link,'publisher_url':p_url, 'feed':label},
            'contacts':[], 'origin':'automated', 'review_status':'Headline collected — requires review',
            'contact_note':'No named contacts automatically inferred. Research the commissioning team and verify profiles before outreach.'
        })
        entries.append(obj)
    return entries


def download(url: str) -> bytes:
    req=urllib.request.Request(url,headers={'User-Agent':'GATE-RADAR/1.0 (+RSS-headline aggregator; internal research)','Accept':'application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.5'})
    with urllib.request.urlopen(req,timeout=18) as res:
        body=res.read(3_000_001)
        if len(body)>3_000_000:raise ValueError('Feed is too large')
        return body


def run(fetcher=download, dest=OUT, now=None):
    now=now or NOW()
    old={}
    if dest.exists():
        try:old=json.loads(dest.read_text(encoding='utf-8'))
        except (ValueError,OSError):old={}
    accumulated={x['id']:x for x in old.get('items',[]) if x.get('id') and isinstance(x,dict)}
    reports=[];successful=0;count_new=0
    for label,query in SEARCHES:
        url=rss_url(query)
        try:
            fresh=parse_feed(fetcher(url),label)
            successful+=1
            for article in fresh:
                if article['id'] not in accumulated:count_new+=1
                accumulated[article['id']]=article
            reports.append({'name':label,'state':'ok','items':len(fresh)})
        except Exception as e:
            reports.append({'name':label,'state':'error','items':0,'reason':str(e)[:140]})
    cutoff=(now-dt.timedelta(days=14)).date().isoformat()
    items=[x for x in accumulated.values() if x.get('date','')>=cutoff]
    items.sort(key=lambda x:(x['date'],int(x.get('signal_score',0))),reverse=True)
    items=items[:200]
    status='healthy' if successful==len(SEARCHES) else ('partial' if successful else 'unavailable')
    payload={
        'schema_version':1,'generated_at':now.isoformat(timespec='seconds').replace('+00:00','Z'),
        'last_successful_fetch':(now.isoformat(timespec='seconds').replace('+00:00','Z') if successful else old.get('last_successful_fetch')),
        'status':status,'sources_ok':successful,'sources_total':len(SEARCHES),
        'new_items_this_run':count_new,'sources':reports,'items':items
    }
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('GATE RADAR',status,successful,'/',len(SEARCHES),'sources;',len(items),'headlines;',count_new,'new')
    return payload


if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--fixture',help='Optional local RSS fixture for offline testing (does not verify live endpoints).');args=ap.parse_args()
    if args.fixture:
        f=Path(args.fixture).read_bytes()
        run(fetcher=lambda url:f)
    else:
        run()