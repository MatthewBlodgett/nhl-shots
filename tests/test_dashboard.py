from datetime import timedelta
import json
from pathlib import Path
import subprocess
from build_dashboard import summary,build
from odds_recorder import atomic_json
from tests.test_paper_tools import archive,NOW


def test_public_summary_excludes_internal_state_and_reuses_latest_player_gate(tmp_path):
    archive(tmp_path)
    archive(tmp_path,stage='late',candidate=False,at=NOW+timedelta(hours=1))
    atomic_json(tmp_path/'state.json',{'sensitive_test_value':'never-export','attempts':{'internal':'private-test'}})
    result=summary(tmp_path,NOW)
    assert 'never-export' not in json.dumps(result)
    assert 'quota_state' not in result['status']
    assert result['candidates']['observations']==[]
    assert result['players']['1']['observations']
    assert 'paper_decisions' not in result['performance']


def test_static_build_supports_project_subpath_and_copies_only_site_assets(tmp_path):
    build(tmp_path)
    assert set(p.name for p in tmp_path.iterdir())=={'index.html','archive-client.js','.nojekyll'}
    html=(tmp_path/'index.html').read_text()
    assert 'data-source="archive"' in html
    assert 'src="archive-client.js"' in html
    assert 'ODDS_API_KEY' not in html
    assert 'data-view="health"' in html and 'data-view="performance"' in html


def test_browser_freshness_advances_without_refetching_or_modifying_input(tmp_path):
    script=Path(__file__).parents[1]/'dashboard'/'archive-client.js'
    js='''const assert=require('node:assert/strict');const api=require(process.argv[1]);
const now=Date.parse('2026-10-02T18:00:00Z');
const q={book_updated_at:'2026-10-02T18:00:00Z',game_start:'2026-10-02T20:00:00Z'};
const input={schema_version:1,status:{last_run:{recorded_at:'2026-10-02T18:00:00Z'}},candidates:{observations:[q]},players:{'1':{observations:[q]}},performance:{versions:{}},research:{}};
let x=api.ageSummary(input,now);assert.equal(x.candidates.observations[0].expired_now,false);
x=api.ageSummary(input,now+601000);assert.equal(x.players['1'].observations[0].expired_now,true);
x=api.ageSummary(input,now+7201000);assert.equal(x.status.stale,true);
assert.equal(input.candidates.observations[0].expired_now,undefined);
assert.equal(api.ageQuotes({observations:[{book_updated_at:'invalid',game_start:'invalid'}]},now).observations[0].expired_now,true);
assert.equal(api.ageQuotes({observations:[{book_updated_at:'2026-10-02T18:02:00Z',game_start:q.game_start}]},now).observations[0].expired_now,true);
assert.throws(()=>api.ageSummary({schema_version:99}));
'''
    subprocess.run(['node','-e',js,str(script)],check=True)
