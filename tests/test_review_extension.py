from datetime import timedelta
import json
from threading import Thread
from urllib.request import urlopen, Request
from urllib.error import HTTPError
import pytest
from tests.test_paper_tools import NOW, archive
from context_inputs import context_for, validate
from official_context import ArticleParser, player_observations
from review_server import server
from settlement_rules import assess
import odds_recorder as recorder
from tests.test_odds_recorder import FakeClient, model
from health_report import record_health


def observation(**extra):
    return {'player_id':1,'event_id':'a'*32,'field':'injury_status','value':'injured','certainty':'projected',
        'published_at':NOW.isoformat(),'observed_at':NOW.isoformat(),'game_start':(NOW+timedelta(hours=2)).isoformat(),
        'source_url':'https://www.nhl.com/news/test','evidence_sha256':'a'*64,**extra}


def test_context_rejects_future_and_requires_official_source(tmp_path):
    with pytest.raises(ValueError):validate(observation(observed_at=(NOW+timedelta(hours=3)).isoformat()))
    with pytest.raises(ValueError):validate(observation(source_url='https://nhl.com.evil.test/article'))
    (tmp_path/'context').mkdir();(tmp_path/'context'/'observations.json').write_text(json.dumps([observation()]))
    assert context_for(tmp_path,1,'a'*32,NOW-timedelta(minutes=1),[])['fields']['injury_status']['status']=='missing'
    assert context_for(tmp_path,1,'a'*32,NOW,[])['fields']['injury_status']['status']=='projected'


def test_official_parser_does_not_infer_absence_or_pp():
    a={'body':'**Blues projected lineup**\n\nTest Player -- Other Player -- Third Player\n\n***Injured:** Someone Else (hand)*',
        'source_url':'https://www.nhl.com/news/test','published_at':NOW.isoformat(),
        'observed_at':NOW.isoformat(),'evidence_sha256':'a'*64}
    e={'id':'a'*32,'home_team':'St Louis Blues','away_team':'Dallas Stars','commence_time':(NOW+timedelta(hours=2)).isoformat()}
    r=player_observations(a,e,{'id':1,'name':'Test Player'},NOW)
    assert {x['field'] for x in r}=={'lineup_status','line_assignment'}
    assert player_observations(a,e,{'id':2,'name':'Missing Person'},NOW)==[]
    assert player_observations({**a,'observed_at':(NOW+timedelta(hours=3)).isoformat()},e,{'id':1,'name':'Test Player'},NOW)==[]


def test_no_paid_request_without_persisted_reservation(tmp_path):
    client=FakeClient()
    def fail(root):raise recorder.SafeAPIError('Persistence failed')
    with pytest.raises(recorder.SafeAPIError):recorder.collect(tmp_path,client,now=NOW,predictor=model,reserve_callback=fail)
    assert json.loads((tmp_path/'state.json').read_text())['attempts']
    # Persisted unknown reservation blocks a subsequent run.
    assert recorder.collect(tmp_path,client,now=NOW,predictor=model)['requests']==0


def test_health_counts_selected_game_with_no_snapshot(tmp_path):
    event={'commence_time':(NOW-timedelta(hours=8)).isoformat()}
    recorder.atomic_json(tmp_path/'state.json',{'event_census':{'a':{'event':event,'selected':True}}})
    h=record_health(tmp_path,{},success=True,now=NOW)
    assert h['selected_games_without_snapshots']==1
    assert h['missing_elapsed_windows_on_observed_games']==3


def test_unknown_and_partial_rules_never_claim_supported():
    assert assess({'book':'bovada'},3)['status']=='unresolved'
    assert assess({'book':'fanduel','jurisdiction':'US-IL'},3)['status']=='unresolved'


def test_http_interface_end_to_end_read_only(tmp_path):
    archive(tmp_path);http=server(tmp_path,0);thread=Thread(target=http.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{http.server_port}'
    try:
        for name in ('status','candidates','player?player_id=1','performance','research'):
            with urlopen(base+'/api/'+name) as response:
                assert response.status==200
                assert 'ODDS_API_KEY' not in response.read().decode()
        with urlopen(base+'/') as response:assert b'viewport' in response.read()
        for path in ('/api/player','/api/player?player_id=-1','/api/unknown','/../sportsbook_rules.json'):
            with pytest.raises(HTTPError):urlopen(base+path)
        with pytest.raises(HTTPError) as error:urlopen(Request(base+'/api/status',data=b'{}',method='POST'))
        assert error.value.code==501
    finally:http.shutdown();http.server_close();thread.join()


def test_hash_sampling_is_stable_price_independent_and_keeps_existing_selection(tmp_path):
    from tests.test_odds_recorder import event
    events=[event(i) for i in range(1,9)];state={'days':{}}
    _,first=recorder.select_events(events,state,NOW,'hash_five_v2')
    _,again=recorder.select_events(list(reversed(events)),state,NOW,'first_five_v1')
    assert [e['id'] for e in first]==[e['id'] for e in again]
    assert len(state['planned_omissions'])==1
    assert state['day_policies']['2026-10-02']=='hash_five_v2'


def test_partial_game_does_not_contribute_drawdown(tmp_path):
    import performance_report
    snap=archive(tmp_path,actual=0)
    snap['quotes'].append({**snap['quotes'][0],'player':'Other','player_id':2})
    recorder.atomic_json(tmp_path/'snapshots'/'2026-10-02'/('a'*32+'-middle.json.gz'),snap,compressed=True)
    metrics=performance_report.make_report(tmp_path,NOW)['versions']['v1']
    assert metrics['incomplete_games_excluded_from_drawdown']==1
    assert metrics['maximum_game_settled_drawdown_units']==0


def test_feature_loader_never_opens_reserved_periods(tmp_path):
    from feature_study import rows, fit, evaluate
    forbidden=tmp_path/'snapshots'/'2027-01-01';forbidden.mkdir(parents=True)
    (forbidden/'reserved.json.gz').write_bytes(b'not valid gzip: must never open')
    assert rows(tmp_path,{'start':'2026-10-03','end':'2026-11-30'})==[]
    data=[{'event_id':'e','player_id':1,'mean':2,'actual':3,'context':{'fields':{'injury_status':{'status':'projected','value':'injured'}}},'model_version':'v'}]
    artifact=fit(data,'p');report=evaluate(data,artifact)
    assert report['injury_status']['paired_player_games']==1
    assert report['power_play_role']['missing_or_unseen_category']==1
    assert report['injury_status']['brier_difference_interval'] is None
