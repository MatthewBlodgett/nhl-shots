"""Regression tests for time boundaries, event scoring and evaluation metrics."""
import copy
import json
import math
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
import shots
from backtest import (backtest_player, chronological_evaluation, evaluate_games,
                      summarize, team_stats_before)


def games(year=2024, n=18):
    start = date(year, 10, 1)
    return [{"gameDate": (start + timedelta(days=i * 2)).isoformat(),
             "gameId": year * 1000 + i, "shots": 1 + i % 5,
             "homeRoadFlag": "H" if i % 2 else "R", "opponentAbbrev": "BBB",
             "toi": "20:00"} for i in range(n)]


@pytest.fixture(autouse=True)
def forbid_live_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline historical evaluation attempted a live request")
    monkeypatch.setattr(shots, "api_request", forbidden)


def test_future_player_results_cannot_change_past_predictions():
    original = games()
    changed = copy.deepcopy(original)
    for g in changed[12:]:
        g["shots"] = 90
        g["toi"] = "50:00"
    before = evaluate_games(1, "test", original, "20242025")
    after = evaluate_games(1, "test", changed, "20242025")
    cutoff = original[12]["gameDate"]
    for a, b in zip(before, after):
        if a["game_date"] <= cutoff:
            assert a["models"] == b["models"]
            assert a["history_through"] < a["game_date"]


def test_ordering_does_not_change_predictions():
    data = games()
    assert evaluate_games(1, "t", data, "20242025") == evaluate_games(1, "t", data[::-1], "20242025")


def test_target_and_future_boxscores_are_excluded():
    data = games()
    cutoff = data[12]["gameDate"]
    boxes = {str(g["gameId"]): {"playerByGameStats": {"homeTeam": {
        "forwards": [{"playerId": 1, "powerPlayToi": "20:00"}]}}}
        for g in data[12:]}
    baseline = evaluate_games(1, "t", data, "20242025")
    changed = evaluate_games(1, "t", data, "20242025", boxscores=boxes)
    assert [(r["game_date"], r["models"]) for r in baseline if r["game_date"] <= cutoff] == [
        (r["game_date"], r["models"]) for r in changed if r["game_date"] <= cutoff]


def test_dated_opponent_stats_exclude_target_future_and_other_seasons():
    rows = [dict(season="20242025", gameDate="2024-10-01", gameId=1,
                 home="AAA", away="BBB", homeShots=40, awayShots=20),
            dict(season="20242025", gameDate="2024-10-03", gameId=2,
                 home="AAA", away="BBB", homeShots=90, awayShots=1),
            dict(season="20232024", gameDate="2023-10-01", gameId=3,
                 home="AAA", away="BBB", homeShots=1, awayShots=90)]
    stats = team_stats_before(rows, "20242025", "2024-10-03")
    assert stats["BBB"]["games"] == 1
    assert stats["BBB"]["shots_against_pg"] == 40
    assert shots.get_opponent_adjustment("BBB", stats) == pytest.approx(40 / 30)
    assert shots.get_opponent_adjustment("BBB", {}) == 1.0


def test_opponent_future_results_cannot_change_past_predictions():
    data = games()
    rows = [dict(season="20242025", gameDate=g["gameDate"], gameId=g["gameId"],
                 home="AAA", away="BBB", homeShots=30, awayShots=20) for g in data]
    changed = copy.deepcopy(rows)
    for r in changed[12:]:
        r["homeShots"] = 90
    a = evaluate_games(1, "t", data, "20242025", team_games=rows)
    b = evaluate_games(1, "t", data, "20242025", team_games=changed)
    assert [r["models"] for r in a if r["game_date"] <= data[12]["gameDate"]] == [
        r["models"] for r in b if r["game_date"] <= data[12]["gameDate"]]


def test_explicit_history_is_filtered_and_does_not_fetch_live_metadata():
    data = games()
    result = shots.analyze_player(1, games=data, game_date=data[12]["gameDate"], opponent="BBB")
    assert result["season"]["games"] == 12
    assert result["projection"]["opponent_factor"] == 1.0
    assert not result["data_quality"]["pp_data_available"]


def test_n_plus_probability_and_scoring_agree():
    data = games(n=11)
    for g in data:
        g["shots"] = 3
    # Home fallback and one rest day approximately cancel; still predicts over.
    data[-1]["homeRoadFlag"] = "H"
    result = backtest_player(1, "t", 3, games=data, season="20242025")
    r = result["records"][0]
    mean = r["models"]["full"]["expected_shots"]
    assert r["models"]["full"]["prob_over"] == shots.prob_over(2.5, mean)
    assert r["outcome_over"] == 1
    assert result["over_wins"] == 1
    assert result["under_losses"] == 0


@pytest.mark.parametrize("flag,expected", [(True, 0), (False, 1)])
def test_rest_override_affects_applied_factor(flag, expected):
    data = [{"gameDate": "2024-10-01", "shots": 3, "homeRoadFlag": "H"}]
    result = shots.analyze_player(1, games=data, game_date="2024-10-02", is_b2b=flag)
    assert result["rest"]["days_rest"] == expected
    assert result["b2b"]["is_b2b"] == flag
    assert result["rest"]["factor"] == 0.95


def test_forced_b2b_overrides_long_rest():
    result = shots.analyze_player(1, games=games(n=1), game_date="2024-10-10", is_b2b=True)
    assert result["rest"]["days_rest"] == 0
    assert result["projection"]["rest_factor"] == 0.95


def test_rest_ignores_same_day_and_future_games():
    data = [{"gameDate": "2024-10-05"}, {"gameDate": "2024-10-03"},
            {"gameDate": "2024-10-01"}]
    assert shots.get_days_rest(data, "2024-10-03") == 1


def test_zero_mean_and_integer_push():
    assert shots.prob_over(2.5, 0) == 0
    assert shots.prob_under(2.5, 0) == 1
    assert shots.prob_under(0, 0) == 0
    assert shots.prob_over(3, 3) + shots.prob_under(3, 3) + shots.poisson_probability(3, 3) == pytest.approx(1)
    with pytest.raises(ValueError):
        shots.prob_over(2.5, -1)
    with pytest.raises(ValueError):
        shots.prob_under(2.5, float("nan"))


def test_metrics_and_calibration_cover_skipped_games():
    rows = [{"actual": actual, "outcome_over": y,
             "models": {"full": {"expected_shots": mean, "prob_over": p}}}
            for actual, y, mean, p in [(3, 1, 2, .6), (1, 0, 3, .4)]]
    m = summarize(rows, confidence=.9)
    assert m["games"] == 2 and m["bets"] == 0 and m["skipped"] == 2
    assert m["mae"] == 1.5
    assert m["rmse"] == pytest.approx(math.sqrt(2.5))
    assert m["brier"] == pytest.approx(.16)
    assert sum(b["count"] for b in m["calibration"]) == 2
    assert m["illustrative_roi"] is None


def test_holdout_not_loaded_or_scored_by_default():
    seen = []
    def load(pid, season):
        seen.append(season)
        assert season != "20242025"
        return games(int(season[:4]))
    report = chronological_evaluation({"t": 1}, ["20242025", "20222023", "20232024"], load,
                                     tune_weights=True)
    assert seen == ["20222023", "20232024"]
    assert [f["role"] for f in report["folds"]] == ["development", "validation"]
    assert not report["holdout_opened"]
    assert len(report["tuning"]) == 5


def test_validation_outcomes_cannot_change_tuned_weights():
    def load(pid, season):
        return games(int(season[:4]))
    def altered(pid, season):
        data = load(pid, season)
        if season == "20232024":
            for g in data:
                g["shots"] = 80
        return data
    a = chronological_evaluation({"t": 1}, ["20222023", "20232024", "20242025"], load, tune_weights=True)
    b = chronological_evaluation({"t": 1}, ["20222023", "20232024", "20242025"], altered, tune_weights=True)
    assert a["protocol"]["weights"] == b["protocol"]["weights"]
    assert a["tuning"] == b["tuning"]


def test_explicit_holdout_and_benchmarks_share_samples():
    report = chronological_evaluation({"t": 1}, ["20222023", "20232024", "20242025"],
              lambda pid, season: games(int(season[:4])), include_holdout=True)
    assert report["folds"][-1]["role"] == "holdout"
    assert report["holdout_opened"]
    for fold in report["folds"]:
        assert len({m["games"] for m in fold["metrics"].values()}) == 1


def test_missing_data_and_invalid_outcomes_fail():
    with pytest.raises(ValueError, match="Missing data"):
        chronological_evaluation({"t": 1}, ["20232024", "20242025"], lambda *a: [])
    data = games()
    del data[0]["shots"]
    with pytest.raises(ValueError, match="shots outcome"):
        evaluate_games(1, "t", data, "20242025")


def test_team_cache_is_season_scoped(monkeypatch):
    shots.clear_cache()
    def api(url):
        rate = 20 if "20232024" in url else 40
        return {"data": [{"teamFullName": "St. Louis Blues", "teamId": 19,
                 "shotsAgainstPerGame": rate, "shotsForPerGame": 30, "gamesPlayed": 10}]}
    monkeypatch.setattr(shots, "api_request", api)
    assert shots.get_team_stats("20232024")["STL"]["shots_against_pg"] == 20
    assert shots.get_team_stats("20242025")["STL"]["shots_against_pg"] == 40
    assert shots.get_team_stats("20232024")["STL"]["shots_against_pg"] == 20
    assert shots.LEAGUE_AVG_SHOTS_AGAINST == 20
    shots.clear_cache()


def test_offline_cli_report(tmp_path):
    dataset = tmp_path / "dataset.json"
    output = tmp_path / "report.json"
    dataset.write_text(json.dumps({"players": {"1": {s: games(int(s[:4]))
        for s in ["20222023", "20232024", "20242025"]}}}))
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "backtest.py"), "1", "3", "55",
        "--seasons", "20222023", "20232024", "20242025", "--tune-weights",
        "--dataset", str(dataset), "--output", str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text())
    assert not report["holdout_opened"]
    assert "Holdout 20242025 excluded" in result.stdout


def test_weight_validation():
    with pytest.raises(ValueError, match="weights"):
        shots.analyze_player(1, games=games(), game_date="2024-12-01", weights=(1, 1, 1))
