"""Frozen development-selected count forecast; no sportsbook integration."""
import hashlib
import json
from pathlib import Path
import shots
from probability_model import blend_mean, count_over

CONFIG_PATH=Path(__file__).with_name('paper_model_config.json')


def version():
    return hashlib.sha256(CONFIG_PATH.read_bytes()+Path(__file__).read_bytes()+
        Path(__file__).with_name('probability_model.py').read_bytes()+Path(shots.__file__).read_bytes()).hexdigest()


def forecast(history, prior, game_date, team=None, config=None):
    config=config or json.loads(CONFIG_PATH.read_text())
    history=shots.prepare_game_log(history,game_date)
    prior=shots.prepare_game_log(prior,game_date)
    inputs={'current_history':history,'prior_history':prior[:config['prior_window']]}
    base={'model_name':config['name'],'distribution':'negative_binomial',
          'dispersion':config['dispersion'],'history_games':len(history),'prior_games':len(prior),
          'input_sha256':hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest(),
          'inputs':inputs,'feature_coverage':{'prior_season':True,'injury_status':False,
          'confirmed_deployment':False,'power_play':False,'opponent_adjustment':False}}
    if len(history)<config['min_current_games']:
        return {**base,'status':'insufficient_current_season_history'}
    if prior and prior[0]['gameDate']>=history[-1]['gameDate']:
        raise ValueError('Prior season overlaps current-season history')
    if len(prior)<config['min_prior_games']:
        return {**base,'status':'insufficient_prior_season_history'}
    mean=blend_mean(history,prior,config['prior_strength'],config['prior_window'])
    previous_team=prior[0].get('teamAbbrev')
    changed=bool(team and previous_team and previous_team!=team)
    if changed and len(history)<config['team_change_min_current_games']:
        return {**base,'status':'team_change_review_required','expected_shots':mean}
    return {**base,'status':'ok','expected_shots':mean,'team_changed_since_prior':changed,
        'prediction':{'projection':{'expected_shots':mean},'count_distribution':{
            'name':'negative_binomial','dispersion':config['dispersion']},
            'data_quality':{'small_sample':len(history)<10,'prior_games':len(prior),
                'opponent_adjustment_available':False,'pp_data_available':False}},
        'warning':'Unproven paper forecast; established-player study excludes zero-current-history games and rookies.'}


def probability(prediction,line):
    distribution=prediction.get('count_distribution',{})
    return count_over(line,prediction['projection']['expected_shots'],
        distribution.get('dispersion') if distribution.get('name')=='negative_binomial' else None)
