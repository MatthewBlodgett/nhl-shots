from datetime import date, timedelta
import math
import pytest
import research_study as study
from probability_model import blend_mean, count_over
import shots


def logs(n, start='2023-10-01', amount=2):
    day=date.fromisoformat(start)
    return [{'gameId':i+1,'gameDate':(day+timedelta(days=2*i)).isoformat(),
             'shots':amount,'homeRoadFlag':'H','opponentAbbrev':'AAA','toi':'15:00'} for i in range(n)]


def test_count_models_known_probabilities():
    assert count_over(.5, 2) == pytest.approx(1-math.exp(-2))
    assert count_over(.5, 2, 1) == pytest.approx(2/3)
    assert count_over(1.5,2,1) == pytest.approx(4/9)
    assert count_over(2.5,2,1e6) == pytest.approx(shots.prob_over(2.5,2),abs=1e-6)
    assert count_over(2.5,0,10)==0
    with pytest.raises(ValueError): count_over(2.5,2,0)
    with pytest.raises(ValueError): count_over(2.5,float('nan'))


def test_prior_blending_is_explicit_and_handles_empty_current():
    assert blend_mean(logs(2,amount=4),logs(30,amount=2),10)==pytest.approx(28/12)
    assert blend_mean([],logs(30,amount=2),20)==2
    assert blend_mean(logs(2,amount=4),[],20)==4
    with pytest.raises(ValueError): blend_mean([],[])


def test_cohort_does_not_depend_on_api_order():
    rows=[{'playerId':i,'gamesPlayed':60,'shots':i%60+30,'positionCode':'D' if i<60 else 'C',
           'skaterFullName':str(i)} for i in range(120)]
    a=study.choose_cohort(rows)
    assert a==study.choose_cohort(list(reversed(rows)))
    assert len(a)==24
    assert all(sum(p['position']==pos and p['volume_tier']==tier for p in a)==4
               for pos in ('F','D') for tier in ('low','medium','high'))


def test_complete_team_pairs_required():
    row={'gameId':1,'gameDate':'2023-10-01','homeRoad':'H','opponentTeamAbbrev':'BBB',
         'shotsForPerGame':20,'shotsAgainstPerGame':30}
    away={**row,'homeRoad':'R','opponentTeamAbbrev':'AAA','shotsForPerGame':30,'shotsAgainstPerGame':20}
    assert study.canonical_team_games({'data':[row,away],'total':2},'20232024')[0]['home']=='AAA'
    with pytest.raises(ValueError): study.canonical_team_games({'data':[row],'total':1},'20232024')
    with pytest.raises(ValueError): study.canonical_team_games({'data':[row,away],'total':3},'20232024')


def test_research_predictions_do_not_use_future_player_or_team_results():
    protocol={'cohort':[{'id':1,'name':'Test','position':'F','volume_tier':'low'}],
              'min_prior_games':20,'prior_window':30,'candidates':study.CANDIDATES,'lines_n_plus':[2,3,4]}
    current=logs(12)
    dataset={'players':{'1':{'20222023':logs(30,'2022-10-01'),'20232024':current}},'team_games':[]}
    first=study.make_records(protocol,dataset,'20232024')
    current[-1]['shots']=100; current[-1]['toi']='59:00'
    dataset['team_games']=[{'season':'20232024','gameDate':'2024-06-01','gameId':999,
                            'home':'AAA','away':'BBB','homeShots':100,'awayShots':0}]
    second=study.make_records(protocol,dataset,'20232024')
    assert first[0]['probabilities']==second[0]['probabilities']
    assert first[-1]['probabilities']==second[-1]['probabilities']
    assert len(first)==11


def test_paired_cluster_interval_preserves_line_and_player_dependence():
    rows=[{'player_id':p,'actual':3,'probabilities':{'a':[.8,.8,.2],'b':[.5,.5,.5]}}
          for p in (1,2,3) for _ in range(p)]
    interval=study.paired_interval(rows,'a','b',[2,3,4],100)
    assert interval['difference']==pytest.approx(-.21)
    assert interval['lower']==pytest.approx(-.21)
    assert interval['upper']==pytest.approx(-.21)
