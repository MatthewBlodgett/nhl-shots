#!/usr/bin/env python3
"""Freeze a historical cohort, collect official inputs, run chronological study.

No sportsbook key or paid odds endpoint is used. Inputs and reports are
compressed JSON. The final holdout is never fetched by this command.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import random
import time
import requests
import shots
from backtest import team_stats_before, validate_games
from probability_model import blend_mean, count_over

ROOT = Path('research')
SEASONS = ['20222023', '20232024', '20242025']
HOLDOUT = '20252026'
CANDIDATES = {
    'season_poisson': {'kind': 'season'},
    'recent10_poisson': {'kind': 'recent'},
    'blend10_poisson': {'kind': 'blend', 'strength': 10},
    'blend20_poisson': {'kind': 'blend', 'strength': 20},
    'blend20_nb10': {'kind': 'blend', 'strength': 20, 'dispersion': 10},
    'blend20_nb20': {'kind': 'blend', 'strength': 20, 'dispersion': 20},
    'blend20_nb40': {'kind': 'blend', 'strength': 20, 'dispersion': 40},
    'legacy_full': {'kind': 'legacy'},
}


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def write_gz(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(value, sort_keys=True, separators=(',', ':')).encode(), mtime=0))


def read_gz(path):
    with gzip.open(path, 'rt') as f:
        return json.load(f)


def fetch(url, params=None):
    for attempt in range(3):
        try:
            response = requests.get(url, params=params, timeout=45)
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def stats(report, season, game=False):
    return fetch(f'{shots.STATS_URL}/{report}/summary', {
        'isAggregate': 'false', 'isGame': str(game).lower(), 'limit': -1, 'start': 0,
        'cayenneExp': f'seasonId={season} and gameTypeId=2'})


def choose_cohort(rows):
    """Four hash-selected players per position and volume tertile, >=40 GP."""
    cohort = []
    for position in ('F', 'D'):
        eligible = [r for r in rows if r['gamesPlayed'] >= 40 and
                    (r['positionCode'] == 'D') == (position == 'D')]
        eligible.sort(key=lambda r: (r['shots'] / r['gamesPlayed'], r['playerId']))
        for tier, name in enumerate(('low', 'medium', 'high')):
            group = eligible[len(eligible)*tier//3:len(eligible)*(tier+1)//3]
            selected = sorted(group, key=lambda r: digest(['nhl-shots-v1', r['playerId']]))[:4]
            for r in selected:
                cohort.append({'id': r['playerId'], 'name': r['skaterFullName'],
                    'position': position, 'volume_tier': name,
                    'cohort_games': r['gamesPlayed'],
                    'cohort_shots_pg': r['shots'] / r['gamesPlayed']})
    if len(cohort) != 24 or len({p['id'] for p in cohort}) != 24:
        raise ValueError('Expected 24 unique cohort players')
    return cohort


def freeze(root):
    path = root / 'protocol.json'
    if path.exists():
        return json.loads(path.read_text())
    census = stats('skater', SEASONS[0])
    if len(census['data']) != census['total']:
        raise ValueError('Incomplete cohort census')
    write_gz(root / 'cohort_source.json.gz', census)
    protocol = {'schema_version': 1, 'frozen_at': datetime.now(timezone.utc).isoformat(),
        'cohort_season': SEASONS[0], 'development_season': SEASONS[1],
        'validation_season': SEASONS[2], 'reserved_holdout': HOLDOUT,
        'cohort': choose_cohort(census['data']), 'cohort_source_sha256': digest(census),
        'cohort_rule': '>=40 cohort GP; F/D by shot-rate tertiles; four fixed hash picks per stratum; no replacements',
        'lines_n_plus': [2, 3, 4], 'prior_window': 30, 'min_current_for_common_sample': 10,
        'min_prior_games': 20, 'candidates': CANDIDATES,
        'selection': 'Lowest equal-line pooled development Brier among candidate families; no validation tuning',
        'bootstrap': '1000 paired player-cluster resamples; seed 1847',
        'limitations': ['Established-player cohort excludes rookies and short-season players.',
            'No historical sportsbook prices; no market profitability conclusion.',
            'Official historical stats include subsequent corrections.',
            'Power-play, injuries and confirmed deployment are not supplied.']}
    root.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(protocol, indent=2) + '\n')
    return protocol


def canonical_team_games(raw, season):
    if len(raw['data']) != raw['total']:
        raise ValueError('Incomplete team census')
    grouped = {}
    for r in raw['data']:
        grouped.setdefault(r['gameId'], []).append(r)
    result = []
    for gid, pair in grouped.items():
        if len(pair) != 2 or {r['homeRoad'] for r in pair} != {'H', 'R'}:
            raise ValueError(f'Incomplete home/away pair {gid}')
        home = next(r for r in pair if r['homeRoad'] == 'H')
        away = next(r for r in pair if r['homeRoad'] == 'R')
        if (home['shotsForPerGame'] != away['shotsAgainstPerGame'] or
            away['shotsForPerGame'] != home['shotsAgainstPerGame'] or home['gameDate'] != away['gameDate']):
            raise ValueError(f'Conflicting team outcome {gid}')
        result.append({'season': season, 'gameDate': home['gameDate'], 'gameId': gid,
            'home': away['opponentTeamAbbrev'], 'away': home['opponentTeamAbbrev'],
            'homeShots': int(home['shotsForPerGame']), 'awayShots': int(away['shotsForPerGame'])})
    return sorted(result, key=lambda r: r['gameId'])


def collect_inputs(root, protocol):
    expected = {}
    for season in SEASONS:
        path = root / 'raw' / f'skater-census-{season}.json.gz'
        census = read_gz(path) if path.exists() else stats('skater', season)
        if len(census['data']) != census['total']:
            raise ValueError('Incomplete skater season census')
        write_gz(path, census)
        expected[season] = {}
        for row in census['data']:
            pid = row['playerId']
            if pid in expected[season]:
                raise ValueError('Duplicate player in season census')
            expected[season][pid] = row['gamesPlayed']
    tasks = []
    for season in SEASONS:
        for player in protocol['cohort']:
            tasks.append(('player', player['id'], season))
        if season != SEASONS[0]:
            tasks.append(('team', None, season))
    def one(task):
        kind, pid, season = task
        path = root / 'raw' / f'{kind}-{pid or "league"}-{season}.json.gz'
        if path.exists():
            data = read_gz(path)
        else:
            if kind == 'player':
                data = fetch(f'{shots.BASE_URL}/player/{pid}/game-log/{season}/2')
            else:
                data = stats('team', season, True)
            write_gz(path, data)
        if kind == 'player':
            games = data.get('gameLog', [] if pid not in expected[season] else None)
            if not isinstance(games, list):
                raise ValueError(f'Missing gameLog {pid}/{season}')
            if games and (str(data.get('seasonId')) != season or data.get('gameTypeId') != 2):
                raise ValueError('Wrong player season or game type')
            validate_games(games)
            if len(games) != expected[season].get(pid, 0):
                raise ValueError(f'Player log completeness mismatch {pid}/{season}')
            return task, games
        return task, canonical_team_games(data, season)
    players, teams, coverage = {}, [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(one, t) for t in tasks]
        for future in as_completed(futures):
            (kind, pid, season), rows = future.result()
            if kind == 'player':
                players.setdefault(str(pid), {})[season] = rows
                coverage.append({'player_id': pid, 'season': season, 'games': len(rows)})
            else:
                teams.extend(rows)
            print(f'Collected {kind} {pid or "league"} {season}: {len(rows)} rows', flush=True)
    dataset = {'players': players, 'team_games': teams, 'coverage': sorted(coverage, key=lambda r:(r['season'],r['player_id'])),
               'collected_at': datetime.now(timezone.utc).isoformat(), 'protocol_sha256': digest(protocol)}
    write_gz(root / 'dataset.json.gz', dataset)
    return dataset


def make_records(protocol, dataset, season):
    context = {}
    records = []
    for player in protocol['cohort']:
        games = dataset['players'][str(player['id'])][season]
        prior_season = SEASONS[SEASONS.index(season)-1]
        prior = shots.prepare_game_log(dataset['players'][str(player['id'])][prior_season])
        for current in reversed(shots.prepare_game_log(games)):
            day = current['gameDate']
            history = shots.prepare_game_log(games, day)
            # Common warm and cold samples; pure current models cannot score zero-history games.
            if not history or len(prior) < protocol['min_prior_games']:
                continue
            if day not in context:
                context[day] = team_stats_before(dataset['team_games'], season, day)
            result = shots.analyze_player(player['id'], is_home=current['homeRoadFlag']=='H',
                opponent=current.get('opponentAbbrev'), game_date=day, season=season,
                games=history, player_info={}, team_stats=context[day], boxscores={})
            means, probs = {}, {}
            for name, spec in protocol['candidates'].items():
                kind = spec['kind']
                if kind == 'season': mean = shots.calculate_stats(history)['avg']
                elif kind == 'recent': mean = shots.calculate_stats(history,10)['avg']
                elif kind == 'blend': mean = blend_mean(history, prior, spec['strength'], protocol['prior_window'])
                else: mean = result['projection']['expected_shots']
                means[name] = mean
                probs[name] = [count_over(n-.5, mean, spec.get('dispersion')) for n in protocol['lines_n_plus']]
            # Frozen legacy ablations; diagnostic only, not added to selectable candidates.
            for factor in ('location','opponent','rest','toi'):
                name = 'legacy_without_' + factor
                mean = means['legacy_full'] / result['projection'][factor+'_factor']
                means[name] = mean
                probs[name] = [count_over(n-.5,mean) for n in protocol['lines_n_plus']]
            records.append({'player_id':player['id'],'player':player['name'],'position':player['position'],
                'volume_tier':player['volume_tier'],'season':season,'game_id':current['gameId'],
                'game_date':day,'history_games':len(history),'prior_games':len(prior),
                'actual':current['shots'],'means':means,'probabilities':probs,
                'opponent_context_available':result['data_quality']['opponent_adjustment_available']})
    return sorted(records,key=lambda r:(r['game_date'],r['player_id']))


def score(records, name, lines):
    if not records: return {'games':0, 'brier':None}
    per_line = []
    bins = [[] for _ in range(10)]
    for i,line in enumerate(lines):
        values=[]
        for r in records:
            p=r['probabilities'][name][i]; y=int(r['actual']>=line)
            values.append((p-y)**2); bins[min(9,int(p*10))].append((p,y))
        per_line.append({'n_plus':line,'brier':sum(values)/len(values)})
    errors=[r['means'][name]-r['actual'] for r in records]
    return {'games':len(records),'players':len({r['player_id'] for r in records}),
        'brier':sum(r['brier'] for r in per_line)/len(lines), 'per_line':per_line,
        'mae':sum(abs(e) for e in errors)/len(errors),
        'rmse':(sum(e*e for e in errors)/len(errors))**.5,
        'calibration':[{'lower':i/10,'count':len(b),
            'predicted':sum(p for p,y in b)/len(b),'observed':sum(y for p,y in b)/len(b)}
            for i,b in enumerate(bins) if b]}


def paired_interval(records, challenger, baseline, lines, repetitions=1000):
    grouped={}
    for r in records:
        delta=sum((r['probabilities'][challenger][i]-int(r['actual']>=n))**2-
                  (r['probabilities'][baseline][i]-int(r['actual']>=n))**2 for i,n in enumerate(lines))/len(lines)
        grouped.setdefault(r['player_id'],[]).append(delta)
    if len(grouped)<2: return {'players':len(grouped),'lower':None,'upper':None}
    pairs=[(sum(v),len(v)) for v in grouped.values()]
    rng=random.Random(1847); draws=[]
    for _ in range(repetitions):
        sampled=[rng.choice(pairs) for _ in pairs]
        draws.append(sum(x[0] for x in sampled)/sum(x[1] for x in sampled))
    draws.sort()
    return {'players':len(pairs),'difference':sum(x[0] for x in pairs)/sum(x[1] for x in pairs),
            'lower':draws[int(.025*repetitions)],'upper':draws[int(.975*repetitions)],
            'method':'paired player-cluster percentile bootstrap; descriptive 95 percent interval'}


def run_study(root, protocol, dataset):
    if dataset['protocol_sha256'] != digest(protocol):
        raise ValueError('Dataset does not match frozen protocol')
    if any(HOLDOUT in seasons for seasons in dataset['players'].values()):
        raise ValueError('Reserved holdout data must not enter this study')
    development=make_records(protocol,dataset,protocol['development_season'])
    lines=protocol['lines_n_plus']
    dev_scores={n:score(development,n,lines) for n in protocol['candidates']}
    if not development: raise ValueError('No development sample')
    selected=min(dev_scores,key=lambda n:dev_scores[n]['brier'])
    frozen={'name':selected,'spec':protocol['candidates'][selected], 'protocol_sha256':digest(protocol),
        'development_scores':{n:v['brier'] for n,v in dev_scores.items()}}
    # Write selection BEFORE any validation prediction is calculated.
    (root/'selected_model.json').write_text(json.dumps(frozen,indent=2)+'\n')
    validation=make_records(protocol,dataset,protocol['validation_season'])
    report={'protocol_sha256':digest(protocol),'dataset_sha256':digest(dataset),
        'implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()+Path('probability_model.py').read_bytes()+Path('shots.py').read_bytes()).hexdigest(),
        'selected_model':frozen,'holdout_opened':False,'holdout_loaded':False,
        'coverage':dataset['coverage'],'limitations':protocol['limitations'],'folds':{}}
    for label,rows in [('development',development),('validation',validation)]:
        groups={'all':rows,'early': [r for r in rows if r['history_games']<10],
                'established':[r for r in rows if r['history_games']>=10]}
        for pos in ('F','D'): groups['position_'+pos]=[r for r in rows if r['position']==pos]
        for tier in ('low','medium','high'): groups['volume_'+tier]=[r for r in rows if r['volume_tier']==tier]
        report['folds'][label]={'groups':{g:{n:score(rs,n,lines) for n in development[0]['means']} for g,rs in groups.items()},
            'paired_comparisons':{g:{b:paired_interval(rs,selected,b,lines) for b in ('season_poisson','recent10_poisson','legacy_full')} for g,rs in groups.items()},
            'opponent_context_games':sum(r['opponent_context_available'] for r in rows)}
    write_gz(root/'predictions.json.gz',{'development':development,'validation':validation})
    write_gz(root/'report.json.gz',report)
    print(json.dumps({'selected':selected,'validation':{n:score(validation,n,lines)['brier'] for n in protocol['candidates']},
        'games':len(validation),'early_games':sum(r['history_games']<10 for r in validation),
        'intervals':report['folds']['validation']['paired_comparisons']['all']},indent=2),flush=True)
    write_summary(root, protocol, report)
    return report


def write_summary(root, protocol, report):
    name=report['selected_model']['name']
    lines=['# Broad historical count-model study','',
        'Study frozen 2026-10-02. Development 2023–24; validation 2024–25; 2025–26 reserved holdout was not fetched or scored by the study.',
        '',f'Development-selected model: **{name}**. Twenty equivalent prior appearances shrink the current mean toward the last thirty prior-season appearances; NB2 dispersion is twenty.',
        '', '## Results','', '| Period / sample | Games | Selected Brier | Season baseline | Recent ten baseline | Legacy engine |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for fold in ('development','validation'):
        for group in ('all','early','established'):
            s=report['folds'][fold]['groups'][group]
            lines.append(f"| {fold} / {group} | {s[name]['games']} | {s[name]['brier']:.6f} | {s['season_poisson']['brier']:.6f} | {s['recent10_poisson']['brier']:.6f} | {s['legacy_full']['brier']:.6f} |")
    lines+=['', 'Scores average 2+, 3+ and 4+ Brier errors on identical player games. Lower is better. Early means one through nine current-season appearances; zero-history games are excluded.',
        '', '## Interpretation','',
        'The selected model improved validation point estimates, but its paired 95 percent player-cluster interval versus the season baseline includes zero. This is sufficient to run a versioned paper experiment, not to establish predictive superiority or a market edge. The development scores are optimistic because they selected the candidate.',
        '', 'Eight prespecified candidate families were compared. The validation winner was not substituted for the development winner. Legacy feature ablations are descriptive diagnostics and did not tune the selected model.',
        '', '### Validation paired intervals','', '| Comparator | Brier difference | Lower | Upper |', '| --- | ---: | ---: | ---: |']
    for b,v in report['folds']['validation']['paired_comparisons']['all'].items():
        lines.append(f"| {b} | {v['difference']:.6f} | {v['lower']:.6f} | {v['upper']:.6f} |")
    lines+=['', 'Negative differences favor the selected model. These are descriptive intervals across a small fixed cohort, not a correction for all model-selection uncertainty.',
        '', '## Cohort and completeness','',
        'Twenty-four players were selected using only 2022–23 season totals: forwards and defensemen, three position-specific shot-rate tertiles, four deterministic hash selections per stratum, minimum forty appearances. No later-season replacements were made.',
        '', '| Player | Position | Volume tier |', '| --- | --- | --- |']
    lines += [f"| {p['name']} | {p['position']} | {p['volume_tier']} |" for p in protocol['cohort']]
    lines+=['', 'Missing participation is retained in the coverage file. Twenty-two cohort players contribute development predictions and twenty contribute validation predictions. Full player-log game counts match the complete official season census. Each team season contains 1,312 regular-season games, checked through matching home/away rows. Opponent aggregates include only earlier dates.',
        '', '## Limits and next work','',*['- '+x for x in protocol['limitations']],
        '- Early-season validation has only 180 player games across twenty players; confidence is limited.',
        '- The study supplies historical opponent context but the selected model uses count history alone. Injury, role and power-play feature integration remains open.',
        '- Prior-season data used by a later live 2026–27 forecast does not constitute opening or scoring the study holdout. The study loader explicitly rejects 2025–26 data.',
        '', '## Reproduce','', '`python research_study.py --offline` uses the committed compressed dataset and never requests odds. Raw NHL responses, the protocol, selected model, predictions and report are included in this folder.',
        '', f"Protocol SHA256: `{report['protocol_sha256']}`", f"Dataset SHA256: `{report['dataset_sha256']}`",
        '', 'Inputs are corrected official historical records rather than reconstructed real-time publications. NHL sources: https://api-web.nhle.com/v1 and https://api.nhle.com/stats/rest/en.']
    (root/'README.md').write_text('\n'.join(lines)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--offline',action='store_true')
    args=parser.parse_args()
    protocol=freeze(args.root)
    print('Frozen cohort: '+', '.join(p['name'] for p in protocol['cohort']),flush=True)
    dataset=read_gz(args.root/'dataset.json.gz') if args.offline else collect_inputs(args.root,protocol)
    run_study(args.root,protocol,dataset)


if __name__=='__main__': main()
