"""Credential-free operational status and bounded run history."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import gzip
import json
from pathlib import Path


def record_health(data_dir, summary, *, success, now=None):
    root=Path(data_dir); root.mkdir(parents=True,exist_ok=True)
    now=now or datetime.now(timezone.utc)
    path=root/'health.json'
    old=json.loads(path.read_text()) if path.exists() else {}
    history=old.get('recent_runs',[])
    entry={'at':now.isoformat(),'success':success,'requests':summary.get('requests',0),
           'snapshots':summary.get('snapshots',0),'errors':summary.get('errors',[])}
    history=(history+[entry])[-200:]
    last_success=now.isoformat() if success else old.get('last_success_at')
    counts=Counter(); observed={}
    for file in (root/'snapshots').glob('*/*.json.gz'):
        with gzip.open(file,'rt') as f: snap=json.load(f)
        collected=datetime.fromisoformat(snap['collected_at'].replace('Z','+00:00'))
        if now-collected>timedelta(days=14): continue
        event=snap['event']['id']
        record=observed.setdefault(event,{'start':datetime.fromisoformat(snap['event']['commence_time'].replace('Z','+00:00')),'stages':set()})
        record['stages'].add(snap['stage'])
        for q in snap['quotes']: counts[q.get('blocked_reason','eligible' if q.get('model_probability') is not None else 'no_model')]+=1
    state_path=root/'state.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else {}
    census=state.get('event_census', {})
    discovered={eid:r for eid,r in census.items()
        if now-datetime.fromisoformat(r['event']['commence_time'].replace('Z','+00:00')) < timedelta(days=14)}
    selected_without_snapshots=sum(r.get('selected',False) and eid not in observed
        for eid,r in discovered.items())
    for eid,r in discovered.items():
        if r.get('selected'):
            observed.setdefault(eid, {'start':datetime.fromisoformat(r['event']['commence_time'].replace('Z','+00:00')), 'stages':set()})
    backlog=sum(now>r['start']+timedelta(hours=6) and not (root/'settlements'/f'{eid}.json.gz').exists()
                for eid,r in observed.items())
    missed=sum(stage not in r['stages'] and eid+':'+stage not in state.get('planned_omissions',{}) and now>=r['start']-timedelta(hours=end)
               for eid,r in observed.items() for stage,end in [('early',4),('middle',1),('late',0)])
    consecutive=0
    for r in reversed(history):
        if r['success']: break
        consecutive+=1
    quota=summary.get('quota',old.get('quota'))
    report={'schema_version':1,'last_attempt_at':now.isoformat(),'last_success_at':last_success,
        'consecutive_failures':consecutive,'quota':quota,'recent_runs':history,
        'recent_blocked_quote_counts':dict(counts),'observed_games_last_14_days':len(observed),
        'missing_elapsed_windows_on_observed_games':missed,'unsettled_games_more_than_6_hours_after_start':backlog,
        'quota_paused': bool(quota and (quota['used']>=450 or quota['remaining']<=50)),
        'discovered_games_last_14_days':len(discovered),
        'selected_games_without_snapshots':selected_without_snapshots,
        'sampling_policies':state.get('day_policies',{}),
        'planned_omitted_windows':len(state.get('planned_omissions',{})),
        'limitations':['No external notifications. A failed GitHub runner cannot update this file.',
                       'Discovery coverage starts with census deployment; games never discovered remain unknown.']}
    path.write_text(json.dumps(report,indent=2)+'\n')
    return report
