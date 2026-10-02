#!/usr/bin/env python3
"""Separate development-only descriptive studies. No validation or holdout reads."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from probability_model import blend_mean, count_over
from shots import prepare_game_log, parse_toi


def studies(dataset):
    output={name:[] for name in ('zero_current_history','team_changes','role_changes')}
    for player,seasons in dataset['players'].items():
        # Access only pre-existing development and its earlier prior season.
        games=sorted(seasons.get('20232024',[]),key=lambda g:(g['gameDate'],g.get('gameId',0)))
        prior=prepare_game_log(seasons.get('20222023',[]))
        if len(prior)<20:continue
        for game in games:
            hist=prepare_game_log(games,game['gameDate']);mean=blend_mean(hist,prior,20,30)
            categories=[]
            if not hist:categories.append(('zero_current_history',mean))
            earlier=hist[0] if hist else prior[0]
            if game.get('teamAbbrev') and earlier.get('teamAbbrev') and game['teamAbbrev']!=earlier['teamAbbrev']:
                own=[g for g in hist if g.get('teamAbbrev')==game['teamAbbrev']]
                categories.append(('team_changes',sum(g['shots'] for g in own)/len(own) if len(own)>=10 else None))
            times=[parse_toi(g.get('toi','')) for g in hist[:10]]
            if len(times)==10 and all(t>0 for t in times):
                ratio=(sum(times[:3])/3)/(sum(times[3:])/7)
                if ratio<.8 or ratio>1.2:categories.append(('role_changes',mean*max(.8,min(1.2,ratio))))
            for name,alternative in categories:
                baseline_mean=sum(g['shots'] for g in prior)/len(prior) if name=='zero_current_history' else mean
                baseline=sum((count_over(line,baseline_mean,20)-int(game['shots']>line))**2 for line in (1.5,2.5,3.5))/3
                alt=sum((count_over(line,alternative,20)-int(game['shots']>line))**2 for line in (1.5,2.5,3.5))/3 if alternative is not None else None
                output[name].append({'player_id':player,'game_id':game['gameId'],'date':game['gameDate'],'earlier_appearances':len(hist),
                    'baseline_brier':baseline,'shadow_brier':alt})
    summaries={}
    for name,rows in output.items():
        paired=[r for r in rows if r['shadow_brier'] is not None]
        summaries[name]={'player_games':len(rows),'players':len({r['player_id'] for r in rows}),'paired_games':len(paired),
            'baseline_brier':sum(r['baseline_brier'] for r in paired)/len(paired) if paired else None,
            'shadow_brier':sum(r['shadow_brier'] for r in paired)/len(paired) if paired else None,
            'status':'descriptive_development_only_no_promotion'}
    summaries['rookies']={'status':'awaiting_separate_rookie_cohort','player_games':0,
        'reason':'existing >=40-GP established-player cohort cannot support rookie evaluation'}
    return {'period':'20232024 development only','studies':summaries,'rows':output,
        'limits':['No parameter selection or live eligibility changes.','Historical stats contain later corrections.',
                  'Injury/lineup/PP features require timestamped prospective observations; no fabricated history.']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('research/coverage_studies.json'))
    a=p.parse_args();source=Path(__file__).parent/'research'/'dataset.json.gz'
    with gzip.open(source,'rt') as f:dataset=json.load(f)
    result=studies(dataset);result['dataset_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    result['implementation_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['studies'],indent=2))

if __name__=='__main__':main()
