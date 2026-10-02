#!/usr/bin/env python3
"""Frozen per-feature shadow models fitted only on future development observations.

Never opens historical validation/holdout. Validation needs a previously frozen
artifact and reports paired errors on identical rows, including missingness.
"""
import argparse
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
from context_inputs import FIELDS
from probability_model import count_over
from performance_report import wilson
import math

PROTOCOL=Path(__file__).parent/'research'/'next_protocol.json'


def key_for(context,field):
    info=context.get('fields',{}).get(field,{})
    if info.get('status')=='missing' or info.get('value') is None:return '__missing__'
    value=info['value']
    if field=='projected_toi_minutes':return str(int(float(value)//5)*5)
    if field=='line_assignment':return info.get('status','uncertain')+':listed_with_linemates'
    return info.get('status','uncertain')+':'+str(value)


def rows(root,period):
    result=[]
    for path in sorted(Path(root).glob('snapshots/*/*.json.gz')):
        # Date filters are applied BEFORE opening files, guarding reserved periods.
        if not period['start']<=path.parent.name<=period['end']:continue
        with gzip.open(path,'rt') as f:snap=json.load(f)
        if snap['stage']!='middle':continue
        from context_inputs import stamp
        if stamp(snap['collected_at'])>=stamp(snap['event']['commence_time']):continue
        settlement=Path(root)/'settlements'/f"{snap['event']['id']}.json.gz"
        if not settlement.exists():continue
        with gzip.open(settlement,'rt') as f:actuals=json.load(f)
        actual={q['player_id']:q.get('actual_shots') for q in actuals['quotes'] if q.get('player_id') is not None}
        for name,m in snap.get('models',{}).items():
            if m.get('status')!='ok' or actual.get(m.get('player_id')) is None:continue
            result.append({'event_id':snap['event']['id'],'player_id':m['player_id'],
                'mean':m['expected_shots'],'actual':actual[m['player_id']],
                'context':m.get('supplemental_context',{}),'model_version':snap.get('model_version'),
                'date':path.parent.name})
    # Repeated books/lines/snapshots cannot increase feature evidence.
    return list({(r['event_id'],r['player_id']):r for r in result}.values())


def fit(data,protocol_hash):
    models={}
    for field in FIELDS:
        groups={}
        for r in data:
            key=key_for(r['context'],field)
            if key=='__missing__':continue
            g=groups.setdefault(key,{'actual':0.,'expected':0.,'count':0})
            g['actual']+=r['actual'];g['expected']+=r['mean'];g['count']+=1
        # A predeclared fixed shrinkage; no searching validation parameters.
        models[field]={k:{**g,'ratio':(g['actual']+20)/(g['expected']+20)} for k,g in groups.items()}
    return {'schema_version':1,'protocol_sha256':protocol_hash,'models':models,
        'development_player_games':len(data),'fitted_at':datetime.now(timezone.utc).isoformat(),
        'model_versions':sorted({r['model_version'] for r in data}),
        'implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'feature_definition':'line_assignment measures listed linemates coverage; does not infer first/second line or PP unit'}


def evaluate(data,artifact):
    report={}
    for field,groups in artifact['models'].items():
        paired=[];missing=0
        for r in data:
            key=key_for(r['context'],field)
            if key not in groups:missing+=1;continue
            mean=r['mean']*groups[key]['ratio']
            baseline=(count_over(2.5,r['mean'],20)-int(r['actual']>2.5))**2
            shadow=(count_over(2.5,mean,20)-int(r['actual']>2.5))**2
            probability=count_over(2.5,mean,20);y=int(r['actual']>2.5)
            logloss=-math.log(max(1e-12,min(1-1e-12,probability if y else 1-probability)))
            paired.append({**r,'baseline_brier':baseline,'shadow_brier':shadow,'difference':shadow-baseline,
                'probability':probability,'outcome':y,'log_loss':logloss})
        n=len(paired);players=len({r['player_id'] for r in paired})
        report[field]={'paired_player_games':n,'players':players,'missing_or_unseen_category':missing,
            'baseline_brier':sum(r['baseline_brier'] for r in paired)/n if n else None,
            'shadow_brier':sum(r['shadow_brier'] for r in paired)/n if n else None,
            'shadow_log_loss':sum(r['log_loss'] for r in paired)/n if n else None,
            'calibration':calibration(paired),
            'brier_difference_interval':interval(paired) if n>=100 and players>=20 else None,
            'status':'descriptive_shadow_no_promotion' if n>=100 and players>=20 else 'insufficient_data'}
    return report


def calibration(rows):
    bins=[]
    for i in range(10):
        group=[r for r in rows if min(9,int(r['probability']*10))==i]
        if group:
            n=len(group);successes=sum(r['outcome'] for r in group)
            bins.append({'lower':i/10,'count':n,'predicted':sum(r['probability'] for r in group)/n,
                'observed':successes/n,'observed_wilson_95':wilson(successes,n)})
    return bins


def interval(rows):
    import random
    groups={}
    for r in rows:groups.setdefault(r['player_id'],[]).append(r['difference'])
    values=list(groups.values());rng=random.Random(1847);draws=[]
    for _ in range(1000):
        sample=[rng.choice(values) for _ in values];draws.append(sum(map(sum,sample))/sum(map(len,sample)))
    draws.sort();return [draws[25],draws[975]]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['coverage','freeze-development','validation'])
    p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--artifact',type=Path,default=Path('research/feature_models.json'))
    a=p.parse_args();body=json.loads(PROTOCOL.read_text());digest=hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
    today=datetime.now(timezone.utc).date().isoformat()
    if a.command=='coverage':
        data=rows(a.data_dir,body['development']);print(json.dumps(evaluate(data,fit(data,digest)),indent=2));return
    if a.command=='freeze-development':
        if today<=body['development']['end']:p.error('Development period not complete; cannot freeze partial data')
        if a.artifact.exists():p.error('Existing frozen artifact cannot be overwritten')
        data=rows(a.data_dir,body['development'])
        if len(data)<100:p.error('Insufficient development data')
        artifact=fit(data,digest);a.artifact.write_text(json.dumps(artifact,indent=2)+'\n');return
    if today<=body['fresh_validation']['end']:p.error('Fresh validation period not complete')
    artifact=json.loads(a.artifact.read_text())
    if artifact['protocol_sha256']!=digest or artifact['implementation_sha256']!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest():p.error('Frozen protocol/implementation mismatch')
    if artifact['fitted_at'][:10]>body['fresh_validation']['start']:p.error('Artifact was frozen after validation began')
    data=rows(a.data_dir,body['fresh_validation'])
    if sorted({r['model_version'] for r in data})!=artifact['model_versions']:p.error('Model version mismatch')
    print(json.dumps(evaluate(data,artifact),indent=2))

if __name__=='__main__':main()
