from datetime import datetime,timedelta,timezone
import gzip
import json
from unittest.mock import patch
import pytest
import agent_tool
import health_report
import odds_recorder as recorder
import paper_model
import performance_report

NOW=datetime(2026,10,2,18,tzinfo=timezone.utc)


def games(n,year,team='AAA'):
    return [{'gameDate':f'{year}-10-{i+1:02d}','shots':2,'teamAbbrev':team,'homeRoadFlag':'H'} for i in range(n)]


def test_paper_model_supports_validated_early_sample_and_exposes_inputs():
    forecast=paper_model.forecast(games(2,2026),games(25,2025),'2026-10-03','AAA')
    assert forecast['status']=='ok' and forecast['expected_shots']==2
    assert forecast['distribution']=='negative_binomial'
    assert len(forecast['inputs']['current_history'])==2
    assert forecast['feature_coverage']['injury_status'] is False
    assert paper_model.forecast([],games(25,2025),'2026-10-03','AAA')['status']=='insufficient_current_season_history'
    assert paper_model.forecast(games(2,2026),games(5,2025),'2026-10-03','AAA')['status']=='insufficient_prior_season_history'


def test_team_change_blocks_early_alerts_and_future_games_cannot_change_mean():
    old=games(25,2025)
    assert paper_model.forecast(games(2,2026),old,'2026-10-03','BBB')['status']=='team_change_review_required'
    current=games(2,2026)+[{'gameDate':'2026-10-03','shots':99,'homeRoadFlag':'H'}]
    assert paper_model.forecast(current,old,'2026-10-03','AAA')['expected_shots']==2
    with pytest.raises(ValueError): paper_model.forecast(games(2,2026),games(25,2026),'2026-10-03','AAA')


def archive(tmp_path, *, candidate=True, actual=3, stage='middle', price=2, at=NOW):
    event='a'*32
    q={'event_id':event,'player_id':1,'player':'Test','book':'a','line':2.5,'side':'Over',
       'decimal_odds':price,'model_probability':.7,'model_version':'v1','paper_candidate':candidate,
       'expected_return':.7*price-1,'book_updated_at':at.isoformat(),'market_no_vig_probability':.5}
    snapshot={'event':{'id':event,'commence_time':(NOW+timedelta(hours=2)).isoformat()},
              'collected_at':at.isoformat(),'stage':stage,'quotes':[q],'models':{}}
    path=tmp_path/'snapshots'/'2026-10-02'/f'{event}-{stage}.json.gz'
    recorder.atomic_json(path,snapshot,compressed=True)
    if actual is not None:
        result={**q,'collected_at':at.isoformat(),'actual_shots':actual,'result':'win' if actual>2.5 else 'loss',
                'hypothetical_unit_return':price-1 if actual>2.5 else -1}
        recorder.atomic_json(tmp_path/'settlements'/f'{event}.json.gz',{'event_id':event,'quotes':[result]},compressed=True)
    return snapshot


def test_performance_uses_one_fixed_window_decision_per_player_game(tmp_path):
    snap=archive(tmp_path)
    snap['quotes'].append({**snap['quotes'][0],'book':'b','decimal_odds':2.2,'expected_return':.54})
    recorder.atomic_json(tmp_path/'snapshots'/'2026-10-02'/('a'*32+'-middle.json.gz'),snap,compressed=True)
    archive(tmp_path,stage='early')
    report=performance_report.make_report(tmp_path,NOW)
    assert len(report['paper_decisions'])==1
    assert report['paper_decisions'][0]['book']=='b'
    assert report['versions']['v1']['unresolved']==1  # never borrow another book's settlement
    assert report['versions']['v1']['forecast_player_games']==1
    assert report['versions']['v1']['roi_interval']['lower'] is None


def test_pending_and_missing_participation_are_not_losses(tmp_path):
    archive(tmp_path,actual=None)
    report=performance_report.make_report(tmp_path,NOW)
    metrics=report['versions']['v1']
    assert metrics['resolved']==0 and metrics['unresolved']==1
    assert metrics['hypothetical_roi'] is None


def test_agent_latest_non_candidate_replaces_older_candidate(tmp_path):
    archive(tmp_path)
    archive(tmp_path,stage='late',candidate=False,at=NOW+timedelta(hours=1))
    assert agent_tool.query(tmp_path,'candidates',now=NOW+timedelta(hours=1))['observations']==[]
    result=agent_tool.query(tmp_path,'player',1,now=NOW+timedelta(hours=3))
    assert all(q['expired_now'] for q in result['observations'])
    assert agent_tool.query(tmp_path,'status',now=NOW)['stale'] is True


def test_health_tracks_failure_and_backlog_without_credentials(tmp_path):
    archive(tmp_path,actual=None)
    summary={'requests':1,'snapshots':1,'errors':[],'quota':{'used':4,'remaining':496}}
    good=health_report.record_health(tmp_path,summary,success=True,now=NOW)
    bad=health_report.record_health(tmp_path,{'errors':['HTTP 401']},success=False,now=NOW+timedelta(hours=9))
    assert bad['last_success_at']==good['last_success_at']
    assert bad['consecutive_failures']==1
    assert bad['unsettled_games_more_than_6_hours_after_start']==1


def test_settlement_rechecks_later_corrections_once_daily(tmp_path):
    snap=archive(tmp_path,actual=None)
    snap['models']={'Test':{'nhl_game_id':99}}
    recorder.atomic_json(tmp_path/'snapshots'/'2026-10-02'/('a'*32+'-middle.json.gz'),snap,compressed=True)
    def box(n): return {'gameState':'OFF','playerByGameStats':{'homeTeam':{'forwards':[{'playerId':1,'sog':n}]}}}
    with patch.object(recorder.shots,'get_boxscore',return_value=box(3)):
        assert recorder.settle_recent(tmp_path,NOW+timedelta(days=1))==1
    with patch.object(recorder.shots,'get_boxscore',return_value=box(2)) as fetch:
        assert recorder.settle_recent(tmp_path,NOW+timedelta(days=2))==1
        assert recorder.settle_recent(tmp_path,NOW+timedelta(days=2))==0
        assert fetch.call_count==1
    with gzip.open(tmp_path/'settlements'/('a'*32+'.json.gz'),'rt') as f: settled=json.load(f)
    assert settled['quotes'][0]['result']=='loss' and len(settled['revisions'])==1


def test_prior_log_cache_reuses_success_and_expires(tmp_path):
    response={'seasonId':20252026,'gameTypeId':2,'gameLog':games(25,2025)}
    with patch.object(recorder.shots,'api_request',return_value=response) as fetch:
        assert len(recorder.player_history(1,'20252026',NOW,prior=True,data_dir=tmp_path))==25
        recorder.player_history(1,'20252026',NOW+timedelta(days=6),prior=True,data_dir=tmp_path)
        assert fetch.call_count==1
        recorder.player_history(1,'20252026',NOW+timedelta(days=8),prior=True,data_dir=tmp_path)
        assert fetch.call_count==2
    with patch.object(recorder.shots,'api_request',return_value=None):
        with pytest.raises(ValueError): recorder.player_history(2,'20262027',NOW)


def test_enrichment_uses_negative_binomial_not_legacy_poisson():
    forecast=paper_model.forecast(games(2,2026),games(25,2025),'2026-10-03','AAA')
    forecast['player_id']=1
    quote={'player':'Test','book':'a','line':2.5,'side':'Over','decimal_odds':2,
           'book_updated_at':NOW.isoformat()}
    enriched=recorder.enrich_quotes([quote],{'Test':forecast},NOW,'v')[0]
    from probability_model import count_over
    assert enriched['model_probability']==count_over(2.5,2,20)
    quote['line']=4.5
    assert recorder.enrich_quotes([quote],{'Test':forecast},NOW,'v')[0]['blocked_reason']=='outside_studied_lines'


def test_invalid_book_timestamp_is_expired_in_agent_read(tmp_path):
    snap=archive(tmp_path)
    snap['quotes'][0]['book_updated_at']='invalid'
    recorder.atomic_json(tmp_path/'snapshots'/'2026-10-02'/('a'*32+'-middle.json.gz'),snap,compressed=True)
    assert agent_tool.query(tmp_path,'player',1,now=NOW)['observations'][0]['expired_now'] is True


def test_zero_ice_time_participation_remains_unresolved(tmp_path):
    snap=archive(tmp_path,actual=None);snap['models']={'Test':{'nhl_game_id':99}}
    recorder.atomic_json(tmp_path/'snapshots'/'2026-10-02'/('a'*32+'-middle.json.gz'),snap,compressed=True)
    box={'gameState':'OFF','playerByGameStats':{'homeTeam':{'forwards':[{'playerId':1,'sog':0,'toi':'00:00'}]}}}
    with patch.object(recorder.shots,'get_boxscore',return_value=box):
        recorder.settle_recent(tmp_path,NOW+timedelta(days=1))
    with gzip.open(tmp_path/'settlements'/('a'*32+'.json.gz'),'rt') as f:s=json.load(f)
    assert s['quotes'][0]['actual_shots'] is None
