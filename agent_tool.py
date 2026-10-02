#!/usr/bin/env python3
"""Read-only JSON interface for an agent reviewing the NHL paper archive.

No key, network call, odds refresh, write operation or bet execution. The
caller supplies a current checkout of the odds-records data directory.
"""
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
from performance_report import make_report


def query(data_dir, command, player_id=None, now=None):
    now=now or datetime.now(timezone.utc); root=Path(data_dir)
    if command=='research':
        base=Path(__file__).parent
        with gzip.open(base/'research'/'rookies'/'report.json.gz','rt') as f:
            rookie=json.load(f)
        return {'mode':'paper_only','rookie_study':{k:v for k,v in rookie.items() if k!='rows'},'historical':(base/'research'/'README.md').read_text(),
            'next_protocol':json.loads((base/'research'/'next_protocol.json').read_text()),
            'sportsbook_rules':json.loads((base/'sportsbook_rules.json').read_text()),
            'coverage_studies':{k:v for k,v in json.loads((base/'research'/'coverage_studies.json').read_text()).items() if k!='rows'}}
    if command=='performance':
        return make_report(root,now)
    if command=='status':
        def read(name):
            path=root/name
            return json.loads(path.read_text()) if path.exists() else None
        latest=read('latest_run.json')
        last=datetime.fromisoformat(latest['recorded_at']) if latest else None
        age=(now-last).total_seconds() if last else None
        return {'schema_version':1,'as_of':now.isoformat(),'last_run':latest,
            'last_attempt_age_seconds':age,'stale':age is None or age>7200,
            'quota_state':read('state.json'),'health':read('health.json'),
            'mode':'paper_only','fresh_live_quotes':False}
    if command not in ('candidates','player'): raise ValueError('Unknown read command')
    records=load_observations(root)
    if command=='player': records=[r for r in records if r.get('player_id')==player_id]
    return observation_result(records,command,now)


def load_observations(root):
    records=[]
    for path in sorted((root/'snapshots').glob('*/*.json.gz')):
        with gzip.open(path,'rt') as f: snap=json.load(f)
        for q in snap['quotes']:
            model=snap.get('models',{}).get(q['player'],{})
            details={k:model[k] for k in ('status','model_name','expected_shots','history_games','prior_games',
                'input_sha256','feature_coverage','warning','team_changed_since_prior','supplemental_context') if k in model}
            records.append({**q,'collected_at':snap['collected_at'],'stage':snap['stage'],
                'model_details':details,
                'source_revision':snap.get('source_revision'),
                'event_id':snap['event']['id'],'game_start':snap['event']['commence_time']})
    return records


def observation_result(records,command,now):
    latest={}
    for r in sorted(records,key=lambda x:x['collected_at']):
        latest[(r['event_id'],r.get('player_id'),r['book'],r['line'],r['side'])]=r
    observations=sorted((r for r in latest.values() if command!='candidates' or r.get('paper_candidate')),
                        key=lambda x:x['collected_at'],reverse=True)[:20]
    for r in observations:
        timestamp=r.get('book_updated_at')
        try:
            age=(now-datetime.fromisoformat(timestamp.replace('Z','+00:00'))).total_seconds() if timestamp else None
        except (ValueError, TypeError, AttributeError):
            age=None
        r['age_seconds_now']=age
        r['expired_now']=age is None or age>600 or age< -60 or datetime.fromisoformat(r['game_start'].replace('Z','+00:00'))<=now
    return {'schema_version':1,'as_of':now.isoformat(),'command':command,'observations':observations,
            'mode':'archived_paper_research','warning':'No live price verification or demonstrated market edge.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['status','candidates','player','performance','research'])
    parser.add_argument('--data-dir',type=Path,default=Path('data'))
    parser.add_argument('--player-id',type=int)
    args=parser.parse_args()
    if args.command=='player' and args.player_id is None: parser.error('player requires --player-id')
    print(json.dumps(query(args.data_dir,args.command,args.player_id),indent=2))


if __name__=='__main__': main()
