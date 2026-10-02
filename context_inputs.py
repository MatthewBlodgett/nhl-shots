"""Timestamped supplemental context. Never changes the frozen live model.

Official editorial observations require exact player IDs and human review;
absence from a projected lineup is not evidence of an injury or scratch.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
import shots

FIELDS = ('injury_status','lineup_status','line_assignment','power_play_role','projected_toi_minutes')


def stamp(value):
    t=datetime.fromisoformat(value.replace('Z','+00:00'))
    if t.tzinfo is None: raise ValueError('Timezone required')
    return t


def validate(record):
    if type(record.get('player_id')) is not int or record['player_id']<=0: raise ValueError('Exact player ID required')
    if record.get('field') not in FIELDS: raise ValueError('Unknown context field')
    host=urlparse(record.get('source_url','')).hostname or ''
    if host!='nhl.com' and not host.endswith('.nhl.com'): raise ValueError('Official NHL source required')
    if not record.get('evidence_sha256') or len(record['evidence_sha256'])!=64: raise ValueError('Source hash required')
    if record.get('certainty') not in ('confirmed','projected','uncertain'): raise ValueError('Certainty required')
    if stamp(record['published_at'])>stamp(record['observed_at']): raise ValueError('Publication after observation')
    if stamp(record['observed_at'])>=stamp(record['game_start']): raise ValueError('Postgame context rejected')
    if record.get('field')=='projected_toi_minutes' and not (isinstance(record.get('value'),(int,float)) and 0<=record['value']<=60):
        raise ValueError('Invalid projected ice time')
    return record


def context_for(root, player_id, event_id, as_of, history):
    fields={k:{'status':'missing','value':None} for k in FIELDS}
    path=Path(root)/'context'/'observations.json' if root else None
    records=json.loads(path.read_text()) if path and path.exists() else []
    accepted=[]
    for r in records:
        validate(r)
        if r['player_id']==player_id and r['event_id']==event_id and stamp(r['observed_at'])<=as_of and stamp(r['published_at'])<=as_of:
            if as_of<stamp(r['game_start']): accepted.append(r)
    for r in sorted(accepted,key=lambda r:r['observed_at']):
        fields[r['field']]={'status':r['certainty'],'value':r['value'],'source_url':r['source_url'],
            'published_at':r['published_at'],'observed_at':r['observed_at'],'evidence_sha256':r['evidence_sha256']}
    # A historical proxy is not a confirmed coach projection.
    times=[shots.parse_toi(g['toi']) for g in history[:10] if g.get('toi')]
    proxy=sum(times)/len(times) if times else None
    recent=times[:3]; earlier=times[3:]
    ratio=(sum(recent)/len(recent))/(sum(earlier)/len(earlier)) if recent and earlier and sum(earlier)>0 else None
    body={'as_of':as_of.isoformat(),'fields':fields,'recent_toi_proxy_minutes':proxy,
          'toi_history_appearances':len(times),'recent3_to_previous7_toi_ratio':ratio,
          'role_change_flag':bool(ratio is not None and (ratio<.8 or ratio>1.2)),
          'used_in_live_probability':False,'warning':'Historical TOI proxy is not projected deployment; editorial context may be uncertain.'}
    body['sha256']=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
    return body


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path); parser.add_argument('--data-dir',type=Path,required=True)
    args=parser.parse_args(); records=json.loads(args.input.read_text())
    for r in records: validate(r)
    from odds_recorder import atomic_json
    target=args.data_dir/'context'/'observations.json'
    old=json.loads(target.read_text()) if target.exists() else []
    merged={hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest():r for r in old+records}
    atomic_json(target,list(merged.values()))
    print(json.dumps({'imported':len(merged)-len(old),'mode':'supplemental_research_only'}))

if __name__=='__main__': main()
