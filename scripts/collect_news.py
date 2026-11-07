#!/usr/bin/env python3
"""GATE RADAR v4: target-aware RSS monitoring for UK, EMEA and US.

Only source-linked headlines and non-assertive outreach hypotheses are created.
GATE_TARGET_AGENCIES is an optional GitHub Actions secret containing newline-
separated agency names. The entire hitlist is never written into public code,
logs or output JSON. Google News does receive the agency names in search queries.
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
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'feed.json'
NOW = lambda: dt.datetime.now(dt.timezone.utc)

# Discovery-market searches. A Google News locale/search phrase is not evidence
# that the actual campaign or account win happened in that market.
MARKET_SEARCHES = [
    ('UK agency account wins', '("creative agency" OR "advertising agency") (appointed OR wins OR account OR pitch) (UK OR London OR Britain) when:7d', 'UK', 'agency'),
    ('EMEA agency account wins', '("creative agency" OR "advertising agency") (appointed OR wins OR account OR pitch) (Europe OR EMEA OR Germany OR France OR Netherlands OR UAE) when:7d', 'EMEA', 'agency'),
    ('US agency account wins', '("creative agency" OR "advertising agency") (appointed OR wins OR account OR pitch) (US OR America OR New York OR Los Angeles) when:7d', 'US', 'agency'),
    ('UK creative campaigns', '("new campaign" OR "brand film" OR "TV commercial") (agency OR production) (UK OR London OR Britain) when:7d', 'UK', 'campaign'),
    ('EMEA creative campaigns', '("new campaign" OR "brand film" OR "TV commercial") (agency OR production) (Europe OR EMEA OR France OR Germany OR Dubai) when:7d', 'EMEA', 'campaign'),
    ('US creative campaigns', '("new campaign" OR "brand film" OR "TV commercial") (agency OR production) (US OR America OR New York) when:7d', 'US', 'campaign'),
    ('UK talent agencies', '("talent agency" OR "talent management" OR "athlete representation" OR "creator management") (signs OR appointed OR campaign OR partnership) (UK OR London) when:10d', 'UK', 'talent'),
    ('EMEA talent agencies', '("talent agency" OR "talent management" OR "athlete representation" OR "creator management") (signs OR appointed OR campaign OR partnership) (Europe OR EMEA OR France OR Germany OR Dubai) when:10d', 'EMEA', 'talent'),
    ('US talent agencies', '("talent agency" OR "talent management" OR "athlete representation" OR "creator management") (signs OR appointed OR campaign OR partnership) (US OR America OR New York) when:10d', 'US', 'talent'),
    ('UK production procurement', '("film production" OR "video production" OR "branded content") (tender OR RFP OR procurement) (UK OR Britain OR London) when:14d', 'UK', 'tender'),
    ('EMEA production procurement', '("film production" OR "video production" OR "branded content") (tender OR RFP OR procurement) (Europe OR EMEA OR France OR Germany) when:14d', 'EMEA', 'tender'),
    ('US production procurement', '("film production" OR "video production" OR "branded content") (RFP OR tender OR procurement) (US OR USA OR America) when:14d', 'US', 'tender'),
]
# Kept for compatibility with v3 tests and integrations.
SEARCHES = [(label,query) for label,query,_,_ in MARKET_SEARCHES]

BRANDS = ['JD Sports','Sports Direct','Nike','Adidas','Arsenal','Tottenham','Manchester United',
          'Red Bull','Under Armour','Puma','New Balance','On Running','M&S','Marks & Spencer',
          'BBC','Channel 4','ITV','Sky','Lego','Netflix','Amazon','Uber','Spotify',
          'Coca-Cola','Pepsi','KFC','McDonald\'s','Samsung','Apple','Cadbury','Unilever','Diageo','TikTok']
# Public, illustrative entity recognition only; NOT GATE's internal agency hitlist.
PUBLIC_AGENCIES = ['Uncommon','Homeground','Tommy','We Are Social','Dark Horses','M&C Saatchi',
                   'VCCP','Mother','The Romans','Saatchi & Saatchi','Droga5','DEPT','MSQ Sport + Entertainment']
SIGNAL_TERMS = re.compile(r'\b(agency|agencies|campaign|brand|creative|production|film\w*|commercial\w*|advertis\w*|market\w*|appoint\w*|account|brief|content|social|partnership|sponsor\w*|director\w*|roster|tender|pitch|client|shoot\w*|studio|launch\w*|wins|awards|representation|talent|management|creator|signs|athlete|casting)\b',re.I)
JUNK_TERMS = re.compile(r'\b(match report|fixture list|premier league table|live score|transfer rumou?r|stock price|football transfer window|crypto price|betting odds)\b',re.I)
TALENT_TERMS = re.compile(r'\b(talent agency|talent management|athlete representation|creator management|model agency|modelling agency|artist management|sports management agency|influencer agency|talent roster|talent representation)\b',re.I)
ACTIVITY_TERMS = re.compile(r'\b(appoint\w*|won|wins|award\w*|sign\w*|launch\w*|campaign|pitch|new client|partnership|represent\w*|production|roster|commercial|film|content|acqui\w*|hired|joins)\b',re.I)
REGION_PATTERNS = {
 'UK': re.compile(r'\b(United Kingdom|UK|Britain|British|London|Manchester|Birmingham|Liverpool|Scotland|Wales|England|Leeds|Edinburgh|Bristol)\b',re.I),
 'US': re.compile(r'\b(United States|USA|U\.S\.|American|New York|Los Angeles|California|Chicago|Atlanta|San Francisco|Texas|Boston|Miami)\b',re.I),
 'EMEA': re.compile(r'\b(EMEA|Europe|European|France|French|Paris|Germany|German|Berlin|Netherlands|Dutch|Amsterdam|Spain|Spanish|Madrid|Italy|Italian|Milan|UAE|Dubai|Abu Dhabi|Saudi Arabia|Middle East|South Africa|Africa)\b',re.I),
}


def clean(value: str) -> str:
    return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',str(value or '')))).strip()


def safe_url(value: str) -> str:
    try:
        x=urllib.parse.urlparse((value or '').strip())
        return x.geturl() if x.scheme in ('http','https') and x.netloc else ''
    except Exception:return ''


def iso_date(value: str) -> str | None:
    from email.utils import parsedate_to_datetime
    try:
        d=parsedate_to_datetime(value)
        if not d.tzinfo:d=d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc).date().isoformat()
    except (ValueError,TypeError,OverflowError):return None


def target_names(value=None):
    """Do not log this list; secret supplied by owner through GitHub Settings."""
    value=os.environ.get('GATE_TARGET_AGENCIES','') if value is None else value
    names=[];seen=set()
    for n in re.split(r'[\n\r;]+',value):
        n=n.strip().strip('"\'')
        if not (2<=len(n)<=100) or n.lower() in seen:continue
        seen.add(n.lower());names.append(n)
    return names[:400]


def matches(title: str,names: list[str]) -> list[str]:
    found=[]
    for n in names:
        # Very short or highly generic agency names need human disambiguation.
        if len(n)<3:continue
        if re.search(r'(?<![a-zA-Z0-9])'+re.escape(n)+r'(?![a-zA-Z0-9])',title,re.I):found.append(n)
    return found



# Quality gate: Google News search matches do not establish that an item concerns
# an advertising business. An agency-like string alone (e.g. Mother / Union /
# Squad / Ultra) MUST NOT qualify a story as relevant.
TRADE_PUBLISHERS = re.compile(
    r'(?i)\b(campaign\s*(uk|us|asia)?|the drum|little black book|lbb|shots|'
    r'adweek|ad age|adage|marketing week|prweek|the media leader|'
    r'prolific north|muse by clio|creative review|creative boom|'
    r'creativepool|designrush|brand innovators|mediapost|'
    r'creative salon|marketing interactive|marketing beat|'
    r'the stable|adland|advertising week|ad forum|adforum|'
    r'advertising association|the inspiration room)\b')
MARKETING_CONTEXT = re.compile(
    r'(?i)\b(creative agency|advertising agency|ad agency|marketing agency|'
    r'pr agency|media agency|social media agency|digital agency|brand agency|'
    r'agency of record|agency appointment|creative partner|agency account|'
    r'client services|brand activation|brand partnership|brand campaign|'
    r'campaign launch|advertising campaign|marketing campaign|'
    r'creative campaign|social campaign|social-first campaign|'
    r'branded content|brand film|advertising film|campaign film|'
    r'tv commercial|television commercial|film production|video production|'
    r'content production|commercial production|production compan(?:y|ies)|'
    r'production house|production studio|content studio|creative studio|'
    r'production partner|production brief|commercial director|'
    r'video advert|advertising work|brand storytelling|agency pitch|'
    r'agency win|pitch win|creative account|influencer marketing|'
    r'creator marketing|athlete endorsement|talent representation|'
    r'athlete representation|talent management|creator management|'
    r'artist management|modelling agency|model agency)\b')
TRADE_ACTIVITY = re.compile(
    r'(?i)\b(brand|brands|advertising|advertis(?:er|ement|ing)|ad campaign|'
    r'campaign|commercial|production|film|video|content|social|creative|'
    r'account|client|pitch|agency|agencies|marketing|activation|'
    r'partner|partnership|sponsor|sponsorship|rebrand|launch|appointed|'
    r'appoints|joins|promoted|director|studio|campaigns|creator|talent)\b')
BUSINESS_ACTIVITY = re.compile(
    r'(?i)\b(appoints?|appointed|wins?|won|awarded|launches?|unveils?|'
    r'creates?|produces?|new|partnership|signs?|rebrand|campaign|'
    r'commercial|hires?|joins|promoted|pitch|client|roster|film|'
    r'production|activation|adverts?|directors?|account)\b')
IRRELEVANT_SPORTS = re.compile(
    r'(?i)\b(cricket|IPL|SMAT|syed mushtaq|t20|odi|test match|'
    r'wickets?|innings|hat.trick|squad (?:for|announced|named)|'
    r'(?:national|football|cricket) team squad|team (?:line.?up|news)|'
    r'head coach|match result|match report|match highlights|'
    r'live score|scores? (?:of|at|from)|goal scorer|goals? scored|'
    r'captain (?:for|of)|appointed .* captain|qualifying offers|'
    r'football transfers?|premier league standings)\b')
IRRELEVANT_POLITICS = re.compile(
    r'(?i)\b(governor.elect|election campaign|voter|voting|'
    r'presidential candidate|senator|prime minister|BJP|APC|'
    r'political campaign|ballot|polling station|union.endorsed candidates|'
    r'campaign ad featuring .* mother|administration election|'
    r'health ministry|union ministry|cabinet minister)\b')
IRRELEVANT_INDUSTRY = re.compile(
    r'(?i)\b(steel production|aircraft production|oil production|'
    r'crude oil|refinery|natural gas|wcs discount|manufacturing expansion|'
    r'manufacturing output|oil sands|energy production|gas production|'
    r'commodity trading|stock prices?|cryptocurrency|'
    r'digital life certificate|child welfare agency|forestry agency)\b')
IRRELEVANT_HR = re.compile(r'(?i)\b(organizational development|human resources|HR director|talent acquisition|talent management and organizational|workforce planning|employee relations)\b')
IRRELEVANT_GOSSIP = re.compile(
    r'(?i)\b(estranged mother|mother of teen|his wife|her husband|'
    r'children killed|murder case|lawsuit against|police smear|'
    r'celebrity divorce)\b')
# Common words that double as agency names must have marketing context.
AMBIGUOUS_NAMES = {
    'mother','union','squad','studio','ultra','stand','spin','ark','if',
    'wcs','frame','love creative','tommy','pitch','one agency',
    'scoop','accord','genesis','hope&glory','tangent agency',
    'the works','brand champions','creative race','social chain',
    'new commercial arts','homeground','squad','the lane agency',
    'waste creative','big partnership','the romans',
}


def qualified_target_hits(title: str, publisher: str, names: list[str]) -> list[str]:
    raw = matches(title,names)
    trade = bool(TRADE_PUBLISHERS.search(publisher))
    context = bool(MARKETING_CONTEXT.search(title))
    named_brand = bool(matches(title,BRANDS))
    # Generic words by themselves are not an agency identification.
    # A reputable advertising trade story explicitly mentioning a brand and
    # a known agency is a plausible match, but still a lead to verify.
    return [n for n in raw if n.lower() not in AMBIGUOUS_NAMES or
            (trade and (context or TRADE_ACTIVITY.search(title) or named_brand) or context)]


def qualify_story(title: str, publisher: str, category: str, targets: list[str]):
    """High-precision acceptance gate; prefer missing a lead to publishing junk."""
    if not title or JUNK_TERMS.search(title):return None
    trade = bool(TRADE_PUBLISHERS.search(publisher))
    explicit = bool(MARKETING_CONTEXT.search(title))
    talent = bool(TALENT_TERMS.search(title))
    target_hits = qualified_target_hits(title,publisher,targets)
    # Exclude sports results, elections, generic manufacturing and tabloid
    # stories; sports *commercial campaigns* are still welcome from industry
    # publishers where genuine advertising/production context is explicit.
    if any(p.search(title) for p in (IRRELEVANT_POLITICS,IRRELEVANT_INDUSTRY,IRRELEVANT_GOSSIP,IRRELEVANT_HR)):
        return None
    if IRRELEVANT_SPORTS.search(title) and not (trade and explicit):
        return None
    # The requested territories are UK, EMEA and US: India-only stories
    # aren't within scope even if they come through a broad news search.
    if re.search(r'(?i)\b(India|Indian|Mumbai|Delhi|Bengaluru|Bangalore|Chennai|Hyderabad)\b',title) and not any(REGION_PATTERNS[m].search(title) for m in REGION_PATTERNS):
        return None
    if category == 'talent':
        if not talent or not BUSINESS_ACTIVITY.search(title):return None
        return target_hits,talent
    if category == 'tender':
        if not (re.search(r'(?i)\b(rfp|tender|procurement|invitation to tender)\b',title)
                and re.search(r'(?i)\b(film|video|content|advertis|creative|marketing|production studio)\b',title)):
            return None
        return target_hits,talent
    if category == 'hitlist' and not target_hits:return None
    # Generic uses of 'campaign', 'production', 'agency', 'pitch', etc. are
    # not sufficient. Require an unambiguous creative-industry expression,
    # or BOTH a reputable ad-industry source and identifiable commercial work.
    if explicit:
        if category!='hitlist' and not BUSINESS_ACTIVITY.search(title):return None
        return target_hits,talent
    # An explicit named-agency account win is credible even outside trade media.
    if target_hits and re.search(r'(?i)\b(wins? .{1,70} account|won .{1,70} account|\bawarded .{1,70} account|\bappointed (?:as )?(?:creative|media|ad|marketing) agency)\b',title):
        return target_hits,talent
    if trade and target_hits and (TRADE_ACTIVITY.search(title) or matches(title,BRANDS)):
        return target_hits,talent
    return None


def item_category(item):
    feed=(item.get('source') or {}).get('feed','')
    if feed.startswith('Hitlist watch'):return 'hitlist'
    for label,_,_,category in MARKET_SEARCHES:
        if label==feed:return category
    return 'unknown'


def revalidate_saved_item(item,targets):
    """Retroactively purge previously accepted junk, not just new news."""
    title=item.get('title','')
    src=item.get('source') or {}
    category=item_category(item)
    if category=='unknown':return None
    verdict=qualify_story(title,src.get('label',''),category,targets)
    if verdict is None:return None
    target_hits,talent=verdict
    item['target_match']=bool(target_hits)
    item['talent_signal']=bool(talent)
    item['agency']=', '.join(target_hits or matches(title,PUBLIC_AGENCIES)) if (target_hits or matches(title,PUBLIC_AGENCIES)) else 'Agency to confirm'
    market=item.get('search_market','')
    info=intelligence(title,src.get('feed',''),bool(target_hits),bool(talent),market)
    item.update(info)
    return item


def get_searches(now=None,targets=None):
    now=now or NOW()
    targets=target_names() if targets is None else targets
    searches=list(MARKET_SEARCHES)
    if not targets:return searches
    # Eight rotating batches each hour, ~64 agencies/hour, full list ~3 hours.
    # Query strings stay short; do not print agency names to workflow logs.
    per_batch=8
    groups=[targets[i:i+per_batch] for i in range(0,len(targets),per_batch)]
    groups_per_hour=min(8,len(groups))
    cycle=int(now.timestamp()//3600)
    start=(cycle*groups_per_hour)%len(groups)
    for k in range(groups_per_hour):
        group=groups[(start+k)%len(groups)]
        selection=' OR '.join('"'+n.replace('"','')+'"' for n in group)
        query=f'({selection}) ("creative agency" OR "advertising agency" OR "brand campaign" OR "brand film" OR "agency appointed" OR "account win" OR "commercial production" OR "social content") when:14d'
        searches.append((f'Hitlist watch {k+1}/{groups_per_hour}',query,'UK/EMEA/US','hitlist'))
    return searches


# A staff appointment is not an account win. Match *client/agency selection* patterns.
ACCOUNT_WIN_RE = re.compile(
    r'(?i)(?:\b(?:wins?|won|secures?|lands?|bags?)\s+(?:[\w&’\'-]+\s+){0,7}(?:account|creative brief|advertising brief|media brief|business|creative duties|ad duties)\b|'
    r'\b(?:appointed|named|selected)\s+(?:(?:as|the|its|new|lead|global|integrated|creative|media|digital|social|advertising|brand|marketing)\s+){0,8}(?:agency of record|creative agency|media agency|advertising agency|marketing agency|social agency)\b|'
    r'\bagency of record\b|'
    r'\b(?:appoints?|names?|selects?|chooses?)\s+.{1,90}\b(?:creative|media|advertising|marketing|integrated|social|digital)\s+agency\b|'
    r'\b(?:creative|media|advertising|integrated|social)\s+(?:account|agency)\s+(?:win|appointment)\b)'
)
PRODUCTION_NEED_RE = re.compile(r'(?i)\b(film|filming|video|branded content|advertising production|creative production|commercial production|content production|production company|production partner|production services)\b')
LIVE_PROCUREMENT_RE = re.compile(r'(?i)\b(tender|rfp|request for proposals|invitation to tender|procurement notice|seeks? (?:an? )?(?:film|video|content|production) (?:agency|partner|supplier)|seeking (?:an? )?(?:film|video|content|production) (?:agency|partner|supplier))\b')
TALENT_NEW_BUSINESS_RE = re.compile(r'(?i)\b(signs?|signed|partners?|partnership|commercial deal|brand deal|brand partnership|appointed to represent|representation deal|new roster|launches?)\b')
PERSONNEL_RE = re.compile(r'(?i)\b(joins?|hired|hires?|promoted|promotion|appoints?|appointed|names? (?:an? )?(?:new )?(?:director|head|chief)|mov(?:es|ers)|new (?:director|head|chief|ceo|cmo)|people moves)\b')
CAMPAIGN_RE = re.compile(r'(?i)\b(brand film|commercial|creative campaign|advertising campaign|brand campaign|campaign|film|advert|ad spot|activation|creative work)\b')


def classify(title: str,group: str):
    # Category ordering is deliberate. 'appoints a director' is a people move,
    # never a won account. A published campaign is NOT automatically a live brief.
    if LIVE_PROCUREMENT_RE.search(title) and PRODUCTION_NEED_RE.search(title):return 'Tender'
    if ACCOUNT_WIN_RE.search(title):return 'Account win'
    if PERSONNEL_RE.search(title):return 'Industry move'
    if CAMPAIGN_RE.search(title) or (matches(title,BRANDS) and matches(title,PUBLIC_AGENCIES)):return 'Campaign'
    return 'Industry news'


def headline_region(title):
    found=[label for label,p in REGION_PATTERNS.items() if p.search(title)]
    return (found[0] if len(found)==1 else 'To verify'),('Headline evidence' if len(found)==1 else 'Search-market context only')


def intelligence(title,group,matched_target=False,talent=False,market=''):
    """Rank evidence of a *possible commissioning moment*, not headline popularity.

    High is reserved for explicit production procurement or a named target agency
    winning a client account. Every RSS item still requires source verification;
    even High does not mean that an active production brief exists.
    """
    typ=classify(title,group)
    low=title.lower()
    sector='Talent & representation' if talent else ('Sport & culture' if re.search(r'\b(sport|football|athlete|sponsor|nike|adidas|arsenal|tottenham|manchester united|rugby)\b',low) else ('Entertainment & culture' if re.search(r'\b(music|entertainment|gaming|culture)\b',low) else 'Creative & production'))
    is_live_tender=typ=='Tender' and bool(LIVE_PROCUREMENT_RE.search(title) and PRODUCTION_NEED_RE.search(title))
    has_account_win=typ=='Account win' and bool(ACCOUNT_WIN_RE.search(title))
    has_talent_deal=talent and bool(TALENT_NEW_BUSINESS_RE.search(title))
    has_production=bool(PRODUCTION_NEED_RE.search(title))
    region,confidence=headline_region(title)

    if is_live_tender:
        priority,score='High',92
        rationale='An explicit film/content production procurement signal is present in the headline.'
        next_action='Find the official notice; check whether the tender is still open, deadline, budget, scope and supplier requirements before bidding.'
        angle='This looks like a production procurement lead, but the official buyer notice must confirm a live requirement and eligibility.'
        ask='Could you point us to the official film/content production tender notice and clarify the supplier requirements?'
    elif matched_target and has_account_win:
        priority,score='High',85
        rationale='A named hitlist agency appears alongside a client-account appointment or win. This is an early relationship-opening signal, not an awarded production brief.'
        next_action='Verify the agency and client appointment, identify the account lead or head of production, then ask about upcoming campaign planning and external suppliers.'
        angle='A new client relationship can lead to future production. Confirm whether work is in planning and whether production suppliers are already selected.'
        ask='I saw the recent client appointment and was curious how you approach external film and social production as that relationship develops?'
    elif has_account_win:
        priority,score='Medium',65
        rationale='Agency/client appointment reported, but this is not a verified hitlist win or production requirement.'
        next_action='Check whether the account fits GATE’s sectors, confirm decision-makers and whether external production is relevant.'
        angle='An agency/client appointment may lead to creative production, but no production brief is established.'
        ask='I saw the account appointment and wondered how the team usually brings production partners into new client work?'
    elif has_talent_deal and (has_production or re.search(r'(?i)\b(brand|commercial|content|campaign|athlete|creator|influencer)\b',title)):
        priority,score='Medium',59
        rationale='Talent representation/partnership activity may prompt branded-content planning, but no production buying decision is evidenced.'
        next_action='Identify the partnerships/content lead; ask whether talent produces campaign or original social content with outside partners.'
        angle='New talent or partnerships sometimes create production needs; first confirm who produces the content.'
        ask='How do you approach video and social production when new talent or brand partnerships come on board?'
    elif typ=='Campaign':
        priority,score=('Medium',53) if matched_target else ('Low',32)
        rationale=('A hitlist agency is associated with a published campaign; follow-on work is only hypothetical.' if matched_target else 'A published campaign is a conversation starter, not evidence of an upcoming production brief.')
        next_action='Confirm creative and production credits, then ask about follow-on assets, adaptations, or upcoming work rather than the already-delivered campaign.'
        angle='The campaign may already be finished. Explore next phases or related film/social work without implying an open brief.'
        ask='I noticed the campaign. Do you usually handle follow-on film and social assets internally or work with additional production partners?'
    elif typ=='Industry move':
        priority,score='Low',22
        rationale='Personnel change or industry appointment; useful for relationship-building, not evidence of available production work.'
        next_action='Consider a friendly congratulations; learn their remit and production decision process before asking about opportunities.'
        angle='A new contact or remit can justify a light-touch introduction but does not imply a production need.'
        ask='Congratulations on the news. How does your team typically work with outside production partners?'
    else:
        priority,score='Low',16
        rationale='General creative-industry context. There is no concrete commissioning or account-win signal in the headline.'
        next_action='Monitor the account or research further; no immediate cold outreach recommended from this story alone.'
        angle='Useful context to research, not enough to justify a production-specific approach by itself.'
        ask='How does your team typically plan film and content production?'
    reasons=[rationale]
    if matched_target:reasons.append('Agency name matches the private target list; identity still needs verification.')
    if talent:reasons.append('Talent/representation angle; identify a partnerships or content owner.')
    if region!='To verify':reasons.append('Headline contains a market reference: '+region+'.')
    return dict(type=typ,priority=priority,sector=sector,
                signal_score=score,signal_reasons=reasons,priority_reason=rationale,
                next_action=next_action,angle=angle,ask=ask,
                region=region,region_evidence=confidence,search_market=market,
                caution='Headline-level lead. Confirm agency/client identity and original source before reaching out. Neither an open production brief nor budget is confirmed by a news headline alone.')


def rss_url(query,market='UK'):
    is_us=(market=='US')
    return 'https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':query,'hl':'en-US' if is_us else 'en-GB','gl':'US' if is_us else 'GB','ceid':'US:en' if is_us else 'GB:en'})


def parse_feed(raw: bytes,label: str,market='UK',category='agency',targets=None) -> list[dict]:
    root=ET.fromstring(raw)
    targets=target_names() if targets is None else targets
    entries=[]
    for item in root.findall('.//item'):
        title=clean(item.findtext('title'))
        link=safe_url(clean(item.findtext('link')))
        if not title or not link:continue
        publisher_node=item.find('source')
        publisher=clean(publisher_node.text if publisher_node is not None else '') or 'Publisher not identified'
        p_url=safe_url(publisher_node.attrib.get('url','')) if publisher_node is not None else ''
        if title.endswith(' - '+publisher):title=title[:-(len(publisher)+3)].strip()
        date=iso_date(item.findtext('pubDate'))
        if not date:continue
        verdict=qualify_story(title,publisher,category,targets)
        if verdict is None:continue
        target_hits,talent=verdict
        info=intelligence(title,label,bool(target_hits),talent,market)
        brands=matches(title,BRANDS)
        agencies=target_hits or matches(title,PUBLIC_AGENCIES)
        normalized=re.sub(r'\W+',' ',title.lower()).strip()
        info.update({
            'id':'rss-'+hashlib.sha256(normalized.encode()).hexdigest()[:16],
            'date':date,'title':title[:280],
            'summary':'Source-linked headline from '+publisher+'. Check the report to confirm full details, campaign credits and territory.',
            'agency':', '.join(agencies) if agencies else 'Agency to confirm',
            'brand':', '.join(brands) if brands else 'Brand to confirm',
            'production':'Not established by headline',
            'source':{'label':publisher,'url':link,'publisher_url':p_url,'feed':label},
            'contacts':[],'origin':'automated','review_status':'Headline collected — requires review',
            'target_match':bool(target_hits),'talent_signal':talent,
            'target_note':'Hitlist name match; verify this is the intended agency before outreach.' if target_hits else ('Talent agency signal; qualify roster, sector and relevance.' if talent else 'No agency hitlist match confirmed'),
            'contact_note':'Contacts are not inferred from news headlines. Verify names, titles and public profiles separately before outreach.'
        })
        entries.append(info)
    return entries


def download(url):
    req=urllib.request.Request(url,headers={'User-Agent':'GATE-RADAR/1.1 (+source-linked RSS headline monitor)','Accept':'application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.5'})
    with urllib.request.urlopen(req,timeout=17) as res:
        body=res.read(3_000_001)
        if len(body)>3_000_000:raise ValueError('Feed size limit exceeded')
        return body


def run(fetcher=download,dest=OUT,now=None):
    now=now or NOW()
    targets=target_names()
    searches=get_searches(now,targets)
    old={}
    if dest.exists():
        try:old=json.loads(dest.read_text(encoding='utf-8'))
        except (ValueError,OSError):old={}
    # Version 3's broad legacy feed should not remain in this targeted feed.
    accumulated={}
    for old_item in old.get('items',[]):
        if isinstance(old_item,dict) and old_item.get('id'):
            good=revalidate_saved_item(old_item,targets)
            if good is not None:accumulated[good['id']]=good
    reports=[];successful=0;count_new=0
    for label,query,market,category in searches:
        try:
            fresh=parse_feed(fetcher(rss_url(query,market)),label,market,category,targets)
            successful+=1
            for a in fresh:
                if a['id'] not in accumulated:count_new+=1
                accumulated[a['id']]=a
            reports.append({'name':label,'state':'ok','items':len(fresh)})
        except Exception as e:
            reports.append({'name':label,'state':'error','items':0,'reason':str(e)[:120]})
    cutoff=(now-dt.timedelta(days=21)).date().isoformat()
    items=[x for x in accumulated.values() if x.get('date','')>=cutoff]
    # Rank commercial evidence above generic name-matches and personnel news.
    items.sort(key=lambda x:({'High':3,'Medium':2,'Low':1}.get(x.get('priority'),0),int(x.get('signal_score',0)),x.get('date','')),reverse=True)
    items=items[:160]
    status='healthy' if successful==len(searches) else ('partial' if successful else 'unavailable')
    payload={
        'schema_version':2,'generated_at':now.isoformat(timespec='seconds').replace('+00:00','Z'),
        'last_successful_fetch':now.isoformat(timespec='seconds').replace('+00:00','Z') if successful else old.get('last_successful_fetch'),
        'status':status,'sources_ok':successful,'sources_total':len(searches),
        'new_items_this_run':count_new,'sources':reports,'items':items,
        'coverage':['UK','EMEA','US'], 'monitoring_mode':'target-first' if targets else 'markets-and-talent-only',
        'target_agency_count_configured':len(targets),
        'target_batches_this_run':max(0,len(searches)-len(MARKET_SEARCHES)),
        'target_sweep_note':'Target groups rotate across hourly runs; a full named-agency sweep can take several hours.' if targets else 'Add the GATE_TARGET_AGENCIES repository secret to activate named agency monitoring.',
        'methodology':'News search results are leads, not verified agency involvement or available production briefs. Regions may be inferred from headlines or remain unconfirmed.'
    }
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('GATE RADAR',status,successful,'/',len(searches),'feeds;',len(items),'headlines;',count_new,'new; target configuration count:',len(targets))
    return payload

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--fixture',help='Use local RSS fixture for offline tests; does not validate live endpoints.')
    args=ap.parse_args()
    if args.fixture:
        sample=Path(args.fixture).read_bytes()
        run(fetcher=lambda _:sample)
    else:run()