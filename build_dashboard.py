#!/usr/bin/env python3
"""Publish a credential-free summary and static dashboard. No network or odds calls."""
import argparse
from collections import defaultdict
from datetime import datetime,timezone
import json
from pathlib import Path
from agent_tool import query,load_observations,observation_result
from odds_recorder import atomic_json

QUOTE_FIELDS=('player','player_id','book','line','side','decimal_odds','model_probability',
    'market_no_vig_probability','expected_return','paper_candidate','blocked_reason','model_status',
    'model_version','book_updated_at','collected_at','stage','source_revision','event_id','game_start',
    'age_seconds_now','expired_now','model_details')
HEALTH_FIELDS=('last_attempt_at','last_success_at','consecutive_failures','quota',
    'recent_blocked_quote_counts','observed_games_last_14_days','discovered_games_last_14_days',
    'missing_elapsed_windows_on_observed_games','unsettled_games_more_than_6_hours_after_start',
    'quota_paused','selected_games_without_snapshots','sampling_policies','planned_omitted_windows','limitations')


def public_observations(result):
    result['observations']=[{k:q[k] for k in QUOTE_FIELDS if k in q} for q in result['observations']]
    return result


def summary(data_dir, now=None):
    now=now or datetime.now(timezone.utc)
    status=query(data_dir,'status',now=now)
    # No request ledger, arbitrary state or environment values reach the browser.
    status.pop('quota_state',None)
    status['health']={k:v for k,v in (status['health'] or {}).items() if k in HEALTH_FIELDS}
    status['last_run']={k:v for k,v in (status['last_run'] or {}).items()
                        if k in ('recorded_at','day','requests','snapshots','quotes','new_paper_candidates','quota','errors')}
    observations=load_observations(Path(data_dir));players=defaultdict(list)
    for q in observations:
        if q.get('player_id') is not None: players[q['player_id']].append(q)
    ids=sorted(players)
    performance=query(data_dir,'performance',now=now)
    performance.pop('paper_decisions',None)
    return {'schema_version':1,'generated_at':now.isoformat(),'mode':'public_paper_summary',
        'status':status,'candidates':public_observations(observation_result(observations,'candidates',now)),
        'players':{str(pid):public_observations(observation_result(players[pid],'player',now)) for pid in ids},
        'performance':performance,'research':query(data_dir,'research',now=now),
        'coverage':{'player_count':len(ids),'observations_per_player_limit':20,
                    'candidate_limit':20,'no_live_price_verification':True}}


def write_summary(data_dir,now=None):
    result=summary(data_dir,now)
    atomic_json(Path(data_dir)/'review.json',result)
    return result


def build(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    source=Path(__file__).parent/'dashboard'/'index.html'
    # One UI serves either the local API or the published public summary.
    html=source.read_text().replace('<html lang="en">','<html lang="en" data-source="archive">')
    (output/'index.html').write_text(html)
    (output/'archive-client.js').write_bytes((source.parent/'archive-client.js').read_bytes())
    (output/'.nojekyll').write_text('')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data-dir',type=Path)
    p.add_argument('--output',type=Path);a=p.parse_args()
    if a.data_dir:
        result=write_summary(a.data_dir);print(json.dumps({'player_count':result['coverage']['player_count'],'generated_at':result['generated_at']}))
    if a.output:build(a.output)
    if not a.data_dir and not a.output:p.error('Supply --data-dir and/or --output')

if __name__=='__main__':main()
