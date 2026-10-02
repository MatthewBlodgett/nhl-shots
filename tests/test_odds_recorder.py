import copy
import gzip
import io
import json
import urllib.error
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import odds_recorder as r

NOW = datetime(2026, 10, 2, 18, 0, tzinfo=timezone.utc)


def event(number=1, hours=6):
    return {"id": f"{number:032x}", "commence_time": (NOW + timedelta(hours=hours)).isoformat(),
            "home_team": "St. Louis Blues", "away_team": "Dallas Stars"}


def odds(e):
    return {"id": e["id"], "bookmakers": [{"key": "testbook", "markets": [
        {"key": r.MARKET, "last_update": NOW.isoformat(), "outcomes": [
            {"name": "Over", "description": "Test Player", "point": 2.5, "price": 2.0},
            {"name": "Under", "description": "Test Player", "point": 2.5, "price": 1.8}]}]}]}


class FakeClient:
    def __init__(self, events=None, used=1, remaining=499):
        self.items = events if events is not None else [event()]
        self.usage = {"used": used, "remaining": remaining}
        self.calls = []

    def events(self):
        return self.items, dict(self.usage)

    def odds(self, eid):
        self.calls.append(eid)
        self.usage["used"] += 1
        self.usage["remaining"] -= 1
        return odds(next(e for e in self.items if e["id"] == eid)), dict(self.usage)


def model(event, quotes, now):
    return {"Test Player": {"status": "ok", "player_id": 1, "nhl_game_id": 42,
            "prediction": {"projection": {"expected_shots": 4.0}}}}


@pytest.mark.parametrize("hours,stage", [(13, None), (12, "early"), (4.1, "early"),
    (4, "middle"), (1.1, "middle"), (1, "late"), (.1, "late"), (0, None), (-1, None)])
def test_snapshot_windows(hours, stage):
    assert r.stage_for(NOW + timedelta(hours=hours), NOW) == stage


def test_recording_and_repeat_slot_is_free(tmp_path):
    client = FakeClient()
    first = r.collect(tmp_path, client, now=NOW, predictor=model)
    second = r.collect(tmp_path, client, now=NOW, predictor=model)
    assert first["snapshots"] == 1 and first["quotes"] == 2
    assert first["new_paper_candidates"] == 1
    assert second["requests"] == 0 and len(client.calls) == 1
    path = next((tmp_path / "snapshots").glob("*/*.gz"))
    with gzip.open(path, "rt") as f:
        data = json.load(f)
    assert len(data["quotes"]) == 2
    over = data["quotes"][0]
    assert over["expected_return"] == pytest.approx(over["model_probability"] * 2 - 1)
    assert over["market_no_vig_probability"] == pytest.approx(.5 / (.5 + 1 / 1.8))


def test_each_of_three_stages_only_once(tmp_path):
    client = FakeClient()
    for hours_passed in [0, 3, 5.5, 5.7]:
        r.collect(tmp_path, client, now=NOW + timedelta(hours=hours_passed), predictor=model)
    assert len(client.calls) == 3


def test_five_game_selection_does_not_rotate(tmp_path):
    client = FakeClient([event(i) for i in range(1, 9)])
    first = r.collect(tmp_path, client, now=NOW, predictor=model)
    assert len(client.calls) == 5
    client.items = client.items[5:]
    second = r.collect(tmp_path, client, now=NOW, predictor=model)
    assert second["requests"] == 0


def test_monthly_cap_and_reserve(tmp_path):
    client = FakeClient([event(i) for i in range(1, 6)], used=449, remaining=51)
    r.collect(tmp_path, client, now=NOW, predictor=model)
    assert len(client.calls) == 1 and client.usage["used"] == 450
    assert r.collect(tmp_path, client, now=NOW, predictor=model)["requests"] == 0


def test_manual_request_limit(tmp_path):
    client = FakeClient([event(i) for i in range(1, 6)])
    assert r.collect(tmp_path, client, now=NOW, max_requests=1, predictor=model)["requests"] == 1
    assert len(client.calls) == 1


def test_quotes_survive_enrichment_failure(tmp_path):
    def bad(*args):
        raise RuntimeError("model failed")
    result = r.collect(tmp_path, FakeClient(), now=NOW, predictor=bad)
    assert result["quotes"] == 2 and result["errors"]
    with gzip.open(next((tmp_path / "snapshots").glob("*/*.gz")), "rt") as f:
        assert len(json.load(f)["quotes"]) == 2


def test_failed_billed_request_is_not_retried(tmp_path):
    client = FakeClient()
    with patch.object(client, "odds", side_effect=r.SafeAPIError("HTTP 429")) as get:
        first = r.collect(tmp_path, client, now=NOW, predictor=model)
        second = r.collect(tmp_path, client, now=NOW, predictor=model)
        assert get.call_count == 1
        assert first["errors"] and second["requests"] == 0


def test_bad_quotes_rejected_and_all_valid_quotes_saved():
    data = odds(event())
    rows = data["bookmakers"][0]["markets"][0]["outcomes"]
    rows += [{"name": "Over", "description": "bad", "point": 2.5, "price": float("nan")},
             {"name": "Over", "description": "bad", "point": 2.5, "price": 1.0}, copy.deepcopy(rows[0])]
    assert len(r.normalize_quotes(data)) == 2


def test_stale_price_cannot_alert():
    quotes = r.normalize_quotes(odds(event()))
    for q in quotes:
        q["book_updated_at"] = (NOW - timedelta(minutes=11)).isoformat()
    out = r.enrich_quotes(quotes, model(None, None, None), NOW, "v1")
    assert not any(q["paper_candidate"] for q in out)
    assert out[0]["blocked_reason"] == "stale_or_future_quote"


def test_small_history_and_integer_lines_blocked():
    quotes = r.normalize_quotes(odds(event()))
    out = r.enrich_quotes(quotes, {"Test Player": {"status": "insufficient_current_season_history", "player_id": 1}}, NOW, "v1")
    assert out[0]["player_id"] == 1
    assert not any(q["paper_candidate"] for q in out)
    for q in quotes:
        q["line"] = 3.0
    out = r.enrich_quotes(quotes, model(None, None, None), NOW, "v1")
    assert out[0]["blocked_reason"] == "only_half_point_lines_supported"


def test_name_matching_normalizes_but_does_not_guess():
    assert r.name_key("Tim Stützle") == r.name_key("Tim Stutzle")
    assert r.name_key("J.T. Miller") == r.name_key("JT Miller")
    assert r.name_key("Jack Hughes") != r.name_key("Quinn Hughes")


def test_quota_headers_fail_closed():
    with pytest.raises(r.SafeAPIError, match="Quota"):
        r.quota({})


def test_secret_safe_http_error():
    key = "DO-NOT-PRINT-THIS-SECRET"
    client = r.OddsClient(key)
    error = urllib.error.HTTPError("https://host/?apiKey=" + key, 401, key, {}, io.BytesIO(key.encode()))
    with patch.object(r.urllib.request, "urlopen", side_effect=error):
        with pytest.raises(r.SafeAPIError) as caught:
            client.events()
    assert key not in str(caught.value)
    assert "401" in str(caught.value)


def test_official_outcome_and_missing_participation(tmp_path, monkeypatch):
    client = FakeClient()
    r.collect(tmp_path, client, now=NOW, predictor=model)
    monkeypatch.setattr(r.shots, "get_boxscore", lambda *a: {"gameState": "OFF",
        "playerByGameStats": {"homeTeam": {"forwards": [{"playerId": 1, "sog": 3}]}}})
    assert r.settle_recent(tmp_path, NOW + timedelta(days=1)) == 1
    assert r.settle_recent(tmp_path, NOW + timedelta(days=1)) == 0
    with gzip.open(next((tmp_path / "settlements").glob("*.gz")), "rt") as f:
        data = json.load(f)
    assert data["quotes"][0]["result"] == "win"
    assert data["quotes"][0]["hypothetical_unit_return"] == 1
    assert data["quotes"][1]["result"] == "loss"


def test_chicago_calendar_day_boundary():
    early = datetime(2026, 10, 3, 0, 30, tzinfo=timezone.utc)
    state = {"days": {}}
    e = event()
    e["commence_time"] = "2026-10-03T02:00:00+00:00"
    day, selected = r.select_events([e], state, early)
    assert day == "2026-10-02" and selected


def test_status_report(tmp_path):
    summary = r.collect(tmp_path, FakeClient(), now=NOW, predictor=model)
    r.write_report(tmp_path, summary)
    text = (tmp_path / "README.md").read_text()
    assert "Paper research only" in text and "Test Player" in text
