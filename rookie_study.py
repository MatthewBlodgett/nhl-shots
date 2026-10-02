#!/usr/bin/env python3
"""Separate official rookie development cohort; never fetch validation/holdout."""
import argparse
import hashlib
import json
from pathlib import Path
from research_study import fetch, read_gz, write_gz, digest
from probability_model import count_over
from shots import prepare_game_log

ROOT=Path('research/rookies')


def run(root=ROOT, online=False):
    root.mkdir(parents=True,exist_ok=True)
    protocol=root/'protocol.json'
    if not protocol.exists():
        if not online:raise ValueError('No frozen rookie dataset; use --collect once')
        raw=fetch('https://api.nhle.com/stats/rest/en/skater/summary',{
            'isAggregate':'false','isGame':'false','limit':-1,
            'cayenneExp':'seasonId=20232024 and gameTypeId=2 and isRookie=1'})
        if len(raw['data'])!=raw['total']:raise ValueError('Incomplete rookie census')
        write_gz(root/'census.json.gz',raw)
        cohort=sorted(raw['data'],key=lambda r:digest(['rookie-development-v1',r['playerId']]))[:12]
        body={'season':'20232024','selection':'12 deterministic hash picks from official isRookie=1 census, no minimum GP or replacements',
            'cohort':[{'id':r['playerId'],'name':r['skaterFullName'],'expected_games':r['gamesPlayed']} for r in cohort],
            'warmup':5,'lines':[1.5,2.5,3.5],'models':['season_nb20','recent5_nb20'],
            'limits':['Retrospective completed-season census has participation selection bias.',
                      'Development descriptive only; no live promotion or unseen validation claim.'],
            'holdout':'20252026 never requested','census_sha256':digest(raw)}
        protocol.write_text(json.dumps(body,indent=2)+'\n')
    body=json.loads(protocol.read_text());rows=[];coverage=[]
    if body['season']!='20232024':raise ValueError('Only development season allowed')
    for player in body['cohort']:
        path=root/f"player-{player['id']}.json.gz"
        if not path.exists():
            if not online:raise ValueError('Missing frozen rookie input')
            raw=fetch(f"https://api-web.nhle.com/v1/player/{player['id']}/game-log/20232024/2")
            if raw.get('seasonId') not in (None,20232024) or raw.get('gameTypeId') not in (None,2):raise ValueError('Wrong season or game type')
            write_gz(path,raw)
        raw=read_gz(path);games=prepare_game_log(raw['gameLog'])
        if len(games)!=player['expected_games']:raise ValueError('Rookie log census mismatch')
        coverage.append({'player_id':player['id'],'games':len(games),'eligible':max(0,len(games)-5)})
        for game in sorted(games,key=lambda g:g['gameDate']):
            hist=prepare_game_log(games,game['gameDate'])
            if len(hist)<5:continue
            means={'season_nb20':sum(g['shots'] for g in hist)/len(hist),
                   'recent5_nb20':sum(g['shots'] for g in hist[:5])/5}
            rows.append({'player_id':player['id'],'game_id':game['gameId'],'date':game['gameDate'],
                'brier':{name:sum((count_over(line,mean,20)-int(game['shots']>line))**2 for line in body['lines'])/3 for name,mean in means.items()}})
    report={'status':'descriptive_development_only_no_eligibility_change','protocol_sha256':digest(body),
        'implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'player_games':len(rows),'players':len({r['player_id'] for r in rows}),'coverage':coverage,
        'mean_brier':{name:sum(r['brier'][name] for r in rows)/len(rows) if rows else None for name in body['models']},
        'limitations':body['limits'],'rows':rows}
    write_gz(root/'report.json.gz',report)
    return {k:v for k,v in report.items() if k!='rows'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--collect',action='store_true');a=p.parse_args()
    print(json.dumps(run(online=a.collect),indent=2))
