"""Season rollover and current NHL response contracts; no live HTTP required."""
import pytest
import shots


@pytest.fixture
def season_metadata(monkeypatch):
    data = {"seasons": [
        {"id": 20242025, "standingsStart": "2024-10-04"},
        {"id": 20252026, "standingsStart": "2025-10-07"},
        {"id": 20262027, "standingsStart": "2026-09-29"},
    ]}
    monkeypatch.setattr(shots, "api_request", lambda *a, **k: data)


@pytest.mark.parametrize("target,expected", [
    ("2026-09-28", "20252026"), ("2026-09-29", "20262027"),
    ("2026-10-02", "20262027"), ("2027-01-01", "20262027"),
    ("2025-10-06", "20242025"), ("2025-10-07", "20252026"),
    ("2025-01-15", "20242025"),
])
def test_actual_season_start_boundaries(season_metadata, target, expected):
    assert shots.get_current_season(target) == expected


@pytest.mark.parametrize("target,expected", [
    ("2026-09-28", "20252026"), ("2026-09-29", "20262027"),
    ("2025-10-06", "20242025"), ("2025-10-07", "20252026"),
])
def test_verified_fallback_during_outage(monkeypatch, target, expected):
    monkeypatch.setattr(shots, "api_request", lambda *a, **k: None)
    with pytest.warns(UserWarning, match="fallback"):
        assert shots.get_current_season(target) == expected


def test_malformed_metadata_is_ignored(monkeypatch):
    monkeypatch.setattr(shots, "api_request", lambda *a, **k: {"seasons": [
        {"id": 20262027, "standingsStart": None},
        {"id": "bad", "standingsStart": "2026-09-29"},
        {"id": 20262028, "standingsStart": "2026-09-29"},
    ]})
    with pytest.warns(UserWarning, match="fallback"):
        assert shots.get_current_season("2026-10-02") == "20262027"


def test_current_log_uses_new_season_and_sorts(monkeypatch):
    urls = []
    def api(url, **kwargs):
        urls.append(url)
        if url.endswith("standings-season"):
            return {"seasons": [{"id": 20262027, "standingsStart": "2026-09-29"}]}
        return {"seasonId": 20262027, "gameTypeId": 2, "gameLog": [
            {"gameDate": "2026-09-29", "shots": 4},
            {"gameDate": "2026-10-01", "shots": 3}]}
    monkeypatch.setattr(shots, "api_request", api)
    data = shots.get_player_game_log(8478402)
    assert "/game-log/20262027/2" in urls[-1]
    assert data[0]["gameDate"] == "2026-10-01"


@pytest.mark.parametrize("payload", [
    {"seasonId": 20252026, "gameTypeId": 2},
    {"seasonId": 20262027, "gameTypeId": 3},
])
def test_mismatched_log_metadata_rejected(monkeypatch, payload):
    monkeypatch.setattr(shots, "api_request", lambda *a, **k: payload)
    with pytest.raises(ValueError):
        shots.get_player_game_log(1, "20262027")


def test_new_team_name():
    assert shots.get_team_abbrev("Utah Mammoth") == "UTA"


def test_new_season_no_previous_season_fallback(monkeypatch):
    seen = []
    def api(url, **kwargs):
        seen.append(url)
        return {"seasonId": 20262027, "gameTypeId": 2, "gameLog": []}
    monkeypatch.setattr(shots, "api_request", api)
    result = shots.analyze_player(1, season="20262027", game_date="2026-10-02")
    assert "error" in result
    assert len(seen) == 1 and "20262027/2" in seen[0]
