"""Bounded NHL editorial collection; strict exact-name matching, no inferred PP role."""
from datetime import timedelta
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import requests
from context_inputs import stamp


class ArticleParser(HTMLParser):
    active=False
    articles=None
    def __init__(self):
        super().__init__(); self.articles=[]; self.buffer=[]
    def handle_starttag(self,tag,attrs):
        if tag=='script':
            self.active=dict(attrs).get('type')=='application/ld+json'; self.buffer=[]
    def handle_data(self,data):
        if self.active:self.buffer.append(data)
    def handle_endtag(self,tag):
        if tag=='script' and self.active:
            self.active=False
            try:
                obj=json.loads(''.join(self.buffer))
                if obj.get('@type')=='NewsArticle': self.articles.append(obj)
            except (ValueError,AttributeError): pass


def load_article(root, season, now):
    from odds_recorder import atomic_json
    if root is None: return None
    path=Path(root)/'context'/'official_article.json.gz'
    import gzip
    if path.exists():
        with gzip.open(path,'rt') as f:cached=json.load(f)
        if now-stamp(cached['observed_at'])<timedelta(hours=1): return cached
    url=f'https://www.nhl.com/news/nhl-lineup-projections-{season[:4]}-{season[6:]}-season'
    response=requests.get(url,timeout=15); response.raise_for_status()
    parser=ArticleParser();parser.feed(response.content.decode('utf-8'))
    if len(parser.articles)!=1: raise ValueError('Official article schema unavailable')
    article=parser.articles[0]
    published=article.get('dateModified') or article.get('datePublished')
    if stamp(published)>now: raise ValueError('Future publication')
    cached={'source_url':url,'published_at':published,'observed_at':now.isoformat(),
        'evidence_sha256':hashlib.sha256(response.content).hexdigest(),'body':article['articleBody']}
    atomic_json(path,cached,compressed=True)
    return cached


def player_observations(article, event, player, now):
    from odds_recorder import name_key, parse_time, LOCAL_ZONE
    if not article: return []
    start=parse_time(event['commence_time'])
    # Mutable daily article must be captured before the game, on its game day.
    if stamp(article['observed_at'])>=start or stamp(article['published_at']).astimezone(LOCAL_ZONE).date()!=start.astimezone(LOCAL_ZONE).date(): return []
    chunks=re.split(r'\*\*([^*\n]+) projected lineup\*\*',article['body'])
    matched=[]
    for i in range(1,len(chunks),2):
        team=chunks[i].strip()
        if not any(t.casefold().endswith(team.casefold()) for t in (event['home_team'],event['away_team'])):continue
        section=chunks[i+1].split('**Status report**')[0].split('## ')[0]
        lines=[re.sub(r'[*]', '',x).strip() for x in section.splitlines() if x.strip()]
        for line in lines:
            if line.startswith(('Injured:','Scratched:','Suspended:')):
                label, names=line.split(':',1)
                for name in names.split(','):
                    if name_key(re.sub(r'\([^)]*\)','',name))==name_key(player['name']):
                        matched.append(('injury_status' if label=='Injured' else 'lineup_status',label.lower()))
            elif '--' in line:
                members=line.split('--')
                if any(name_key(n)==name_key(player['name']) for n in members):
                    matched.append(('lineup_status','projected_in_lineup'))
                    matched.append(('line_assignment',[n.strip() for n in members]))
    base={k:article[k] for k in ('source_url','published_at','observed_at','evidence_sha256')}
    return [{**base,'player_id':player['id'],'event_id':event['id'],'game_start':event['commence_time'],
             'certainty':'projected','field':field,'value':value} for field,value in matched]
