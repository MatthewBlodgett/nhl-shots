"""Predeclared prospective paper analysis; one decision per player and game.

Uses the middle collection window. This is a hypothetical policy, not an
execution log. Missing participation remains unresolved. Never reads secrets.
"""
from collections import Counter
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import random

POLICY = {'schema_version':1,'stage':'middle','min_estimated_return':.05,
          'decision':'highest modeled return per event/player; stable book/line/side tie break',
          'calibration':'one quote per event/player; line nearest 2.5 then Over then alphabetic book',
          'unit_stake':1,'confidence_interval':'1000 game-cluster resamples; minimum 20 settled games',
          'settlement':'official full-game SOG; unverified sportsbook participation and void rules'}


def read(path):
    with gzip.open(path,'rt') as f: return json.load(f)


def grouped_interval(rows):
    groups={}
    for r in rows: groups.setdefault(r['event_id'],[]).append(r['hypothetical_unit_return'])
    if len(groups)<20: return {'games':len(groups),'lower':None,'upper':None,'status':'insufficient_game_clusters'}
    rng=random.Random(1847); values=list(groups.values()); draws=[]
    for _ in range(1000):
        sample=[rng.choice(values) for _ in values]
        draws.append(sum(map(sum,sample))/sum(map(len,sample)))
    draws.sort()
    return {'games':len(groups),'lower':draws[25],'upper':draws[975],
            'status':'descriptive_interval_not_a_profitability_guarantee'}


def make_report(data_dir, now=None):
    root=Path(data_dir); now=now or datetime.now(timezone.utc)
    snapshots=[]
    for path in sorted((root/'snapshots').glob('*/*.json.gz')):
        snapshots.append(read(path))
    settlements={}
    for path in sorted((root/'settlements').glob('*.json.gz')):
        s=read(path)
        for q in s['quotes']:
            # Current settlement includes every archived row, identified without fuzzy names.
            key=(s['event_id'],q.get('player_id'),q['book'],q['line'],q['side'],q['collected_at'])
            settlements[key]=q
    eligible={}; blockers=Counter(); latest={}
    for snap in sorted(snapshots,key=lambda s:s['collected_at']):
        event=snap['event']['id']
        for q in snap['quotes']:
            blockers[q.get('blocked_reason','eligible' if q.get('model_probability') is not None else 'no_model')]+=1
            if snap['stage']=='late':
                latest[(event,q.get('player_id'),q['book'],q['line'],q['side'])]=q
            if snap['stage']!=POLICY['stage'] or q.get('model_probability') is None:
                continue
            if datetime.fromisoformat(snap['collected_at'].replace('Z','+00:00'))>=datetime.fromisoformat(snap['event']['commence_time'].replace('Z','+00:00')):
                continue
            row={**q,'event_id':event,'collected_at':snap['collected_at'],
                 'game_start':snap['event']['commence_time']}
            key=(event,q.get('player_id'),q['book'],q['line'],q['side'],snap['collected_at'])
            outcome=settlements.get(key)
            if outcome:
                row.update({k:outcome[k] for k in ('actual_shots','result','hypothetical_unit_return') if k in outcome})
            else:
                row.update({'actual_shots':None,'result':'pending_or_unresolved'})
            eligible.setdefault((event,q['player_id']),[]).append(row)
    forecast_rows=[]; decisions=[]
    for key, quotes in sorted(eligible.items()):
        # One forecast benchmark and one optional paper decision per player/game.
        forecast=min(quotes,key=lambda q:(abs(q['line']-2.5),q['line'],q['side']!='Over',q['book']))
        forecast_rows.append(forecast)
        candidates=[q for q in quotes if q.get('paper_candidate') and not q.get('blocked_reason') and
                    q['expected_return']>=POLICY['min_estimated_return']]
        if candidates:
            selected=min(candidates,key=lambda q:(-q['expected_return'],q['book'],q['line'],q['side']))
            last=latest.get((key[0],key[1],selected['book'],selected['line'],selected['side']))
            selected['late_decimal_odds']=last['decimal_odds'] if last else None
            selected['late_implied_probability_change']=(1/last['decimal_odds']-1/selected['decimal_odds']) if last else None
            decisions.append(selected)
    # Split performance by model version so changing models cannot quietly mix evidence.
    versions={}
    for version in sorted({q['model_version'] for q in forecast_rows+decisions}):
        forecasts=[q for q in forecast_rows if q['model_version']==version and q.get('actual_shots') is not None]
        picks=[q for q in decisions if q['model_version']==version]
        resolved=sorted((q for q in picks if q.get('result') in ('win','loss','push')),
                        key=lambda q:(q['game_start'],q['event_id'],q['player_id']))
        briers=[]; market=[]; calibration=[[] for _ in range(10)]
        for q in forecasts:
            if q['actual_shots']==q['line']: continue
            y=int((q['actual_shots']>q['line'])==(q['side']=='Over')); p=q['model_probability']
            briers.append((p-y)**2); calibration[min(9,int(p*10))].append((p,y))
            if q.get('market_no_vig_probability') is not None:
                market.append(((p-y)**2,(q['market_no_vig_probability']-y)**2))
        profit=sum(q['hypothetical_unit_return'] for q in resolved)
        balance=peak=drawdown=0
        # Drawdown is marked only after all paper decisions in each game settle.
        game_profits={}
        for q in resolved: game_profits[q['event_id']]=game_profits.get(q['event_id'],0)+q['hypothetical_unit_return']
        for value in game_profits.values():
            balance+=value; peak=max(peak,balance); drawdown=max(drawdown,peak-balance)
        versions[version]={'forecast_player_games':len(forecasts),'brier':sum(briers)/len(briers) if briers else None,
            'matched_market_games':len(market),'matched_model_brier':sum(a for a,b in market)/len(market) if market else None,
            'market_no_vig_brier':sum(b for a,b in market)/len(market) if market else None,
            'calibration':[{'lower':i/10,'count':len(b),'predicted':sum(p for p,y in b)/len(b),
                            'observed':sum(y for p,y in b)/len(b)} for i,b in enumerate(calibration) if b],
            'paper_decisions':len(picks),'resolved':len(resolved),'unresolved':len(picks)-len(resolved),
            'hypothetical_profit_units':profit,'hypothetical_roi':profit/len(resolved) if resolved else None,
            'maximum_game_settled_drawdown_units':drawdown,'roi_interval':grouped_interval(resolved)}
    return {'generated_at':now.isoformat(),'policy':POLICY,'snapshot_count':len(snapshots),
        'quote_count':sum(len(s['quotes']) for s in snapshots),'blocked_quote_counts':dict(blockers),
        'eligible_middle_player_games':len(eligible),'versions':versions,'paper_decisions':decisions,
        'limitations':['No actual stakes or bet execution; hypothetical prices may not have been available.',
            'Missing participation and bookmaker rules are unresolved, not automatic losses.',
            'Only sampled games and returned props are represented; this is not league-wide coverage.',
            'Late snapshots are not guaranteed closing prices; repeated observations are not independent.']}


def write_performance(data_dir, now=None):
    report=make_report(data_dir,now)
    root=Path(data_dir)
    (root/'performance.json').write_text(json.dumps(report,indent=2)+'\n')
    lines=['# Prospective paper performance','',f"Updated: {report['generated_at']}",'',
        'Fixed policy: middle window; at most one paper decision per player and game. Results are split by model version.',
        '',f"Archive: {report['snapshot_count']} snapshots / {report['quote_count']} quotes.",
        f"Eligible middle-window player games: {report['eligible_middle_player_games']}.",'']
    if not report['versions']: lines+=['No model-qualified observations to evaluate yet.','']
    for version, metrics in report['versions'].items():
        lines += [f'## Model {version[:12]}','',
            f"Settled forecasts: {metrics['forecast_player_games']}. Brier: {metrics['brier']}.",
            f"Paper decisions: {metrics['paper_decisions']}; resolved: {metrics['resolved']}; unresolved: {metrics['unresolved']}.",
            f"Hypothetical profit units: {metrics['hypothetical_profit_units']:.3f}; ROI: {metrics['hypothetical_roi']}.",'']
    lines+=['## Limitations','',*['- '+x for x in report['limitations']]]
    (root/'PERFORMANCE.md').write_text('\n'.join(lines)+'\n')
    return report
