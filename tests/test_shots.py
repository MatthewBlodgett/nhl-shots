"""Unit tests for NHL Shots prediction engine.

These tests validate the core scoring & probability functions without
hitting the NHL API (that's what the backtest is for).
"""
import math
import sys
from pathlib import Path

# Ensure the project root is on sys.path so we can import shots
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

from shots import (
    poisson_probability,
    prob_over,
    prob_under,
    calculate_stats,
    parse_toi,
    get_days_rest,
    is_player_on_b2b,
    get_current_season,
)


# ── Poisson distribution ───────────────────────────────────────────

def test_poisson_zero_lambda():
    """An expected value of 0 should always yield 0 shots."""
    assert poisson_probability(0, 0) == 1.0
    assert poisson_probability(5, 0) == 0.0


def test_poisson_exact_lambda():
    """P(X=λ) for small λ should be about 1/(e)."""
    # For λ=1: P(X=1) = 1^1 * e^-1 / 1! = 1/e ≈ 0.3679
    assert math.isclose(poisson_probability(1, 1), 1 / math.e, rel_tol=1e-4)


def test_poisson_sums_to_one():
    """The Poisson PMF should sum to ~1 over many k."""
    total = sum(poisson_probability(k, 4.2) for k in range(20))
    assert math.isclose(total, 1.0, rel_tol=1e-3)


# ── Over / Under probabilities ─────────────────────────────────────

def test_prob_over_high_line():
    """A high line should have probability ~0 (few skaters hit 5.5)."""
    assert prob_over(5.5, 2.0) < 0.02


def test_prob_over_low_line():
    """A low line should have probability approaching 1."""
    assert prob_over(0.5, 4.0) > 0.98


def test_prob_under_is_complement():
    """P(under) should be roughly 1 - P(over) for the same line."""
    lam = 3.5
    line = 2.5
    over = prob_over(line, lam)
    under = prob_under(line, lam)
    assert math.isclose(over + under, 1.0, rel_tol=1e-6)


def test_prob_over_50pct():
    """When lambda equals the line, over should be ~50%."""
    # For λ=3.0 and line=2.5: the mean exactly matches the threshold
    # P(X ≥ 3) when X~Poisson(3.0) ≈ 0.576 — not exactly 50/50
    # because Poisson is discrete, but test isn't this precise.
    # Just verify it's between 40% and 70%.
    p = prob_over(2.5, 3.0)
    assert 0.40 < p < 0.70


# ── Calculate stats ────────────────────────────────────────────────

def test_calculate_stats_empty():
    assert calculate_stats([])["avg"] == 0


def test_calculate_stats_basic():
    games = [
        {"shots": 3, "homeRoadFlag": "H"},
        {"shots": 5, "homeRoadFlag": "H"},
        {"shots": 1, "homeRoadFlag": "R"},
    ]
    s = calculate_stats(games)
    assert s["games"] == 3
    assert s["total"] == 9
    assert math.isclose(s["avg"], 3.0)
    assert math.isclose(s["home_avg"], 4.0)
    assert math.isclose(s["away_avg"], 1.0)


def test_calculate_stats_last_n():
    games = [{"shots": i, "gameDate": f"2025-01-{i:02d}"} for i in range(1, 11)]
    s = calculate_stats(games, 3)
    assert s["games"] == 3
    assert s["total"] == 8 + 9 + 10  # 27
    assert s["avg"] == 9.0


# ── TOI parser ────────────────────────────────────────────────────

def test_parse_toi_standard():
    assert parse_toi("21:30") == 21.5


def test_parse_toi_zero():
    assert parse_toi("0:00") == 0.0


def test_parse_toi_empty():
    assert parse_toi("") == 0.0


def test_parse_toi_malformed():
    assert parse_toi("not-a-time") == 0.0


# ── Days rest ──────────────────────────────────────────────────────

def test_get_days_rest_b2b():
    """Back-to-back: 0 days rest."""
    games = [{"gameDate": "2025-01-10"}, {"gameDate": "2025-01-12"}]
    # Most recent game is 2025-01-12, next game is 2025-01-13
    assert get_days_rest(games, "2025-01-13") == 0


def test_get_days_rest_one_day():
    games = [{"gameDate": "2025-01-10"}, {"gameDate": "2025-01-12"}]
    assert get_days_rest(games, "2025-01-14") == 1


def test_get_days_rest_empty():
    assert get_days_rest([], "2025-01-13") == 2


# ── B2B detection ──────────────────────────────────────────────────

def test_is_b2b_true():
    games = [{"gameDate": "2025-01-12"}]
    assert is_player_on_b2b(games, "2025-01-13") is True


def test_is_b2b_false():
    games = [{"gameDate": "2025-01-10"}]
    assert is_player_on_b2b(games, "2025-01-13") is False


# ── Season detection ───────────────────────────────────────────────

def test_get_current_season_format(monkeypatch):
    """Season string should be 8 digits: '20252026' pattern."""
    import shots
    monkeypatch.setattr(shots, "api_request", lambda *a, **k: {"seasons": [
        {"id": 20262027, "standingsStart": "2026-09-29"}]})
    s = get_current_season("2026-10-02")
    assert len(s) == 8
    assert s.isdigit()
    # first 4 digits + 1 should equal last 4 digits
    first = int(s[:4])
    second = int(s[4:])
    assert second == first + 1


def test_one_day_rest_is_neutral_and_thin_tiers_drop_the_multiplier():
    import shots
    one_day = [{"gameDate": f"2024-10-{1 + 2 * i:02d}", "shots": 1, "homeRoadFlag": "H"} for i in range(8)]
    neutral = shots.analyze_player(1, games=one_day, game_date="2024-10-17")
    assert neutral["rest"]["days_rest"] == 1
    assert neutral["rest"]["neutral_one_day"] is True
    assert neutral["projection"]["rest_factor"] == 1.0

    sparse = [{"gameDate": d, "shots": 1, "homeRoadFlag": "H"}
              for d in ("2024-01-01", "2024-01-10", "2024-01-20", "2024-01-30")]
    long_gap = shots.analyze_player(1, games=sparse, game_date="2024-02-10")
    assert long_gap["rest"]["days_rest"] >= 3
    assert long_gap["rest"]["estimated"] is False
    assert long_gap["projection"]["rest_factor"] == 1.0


def test_back_to_back_factor_is_shrunk_toward_the_overall_mean():
    import shots
    games = [{"gameDate": f"2024-10-{i:02d}", "shots": 10 if i == 1 else 1, "homeRoadFlag": "H"}
             for i in range(1, 9)]
    result = shots.analyze_player(1, games=games, game_date="2024-10-09")
    assert result["rest"]["days_rest"] == 0
    assert result["rest"]["estimated"] is True
    overall = [10] + [1] * 7
    expected = shots.shrunk_rest_factor([1] * 7, overall)
    assert result["projection"]["rest_factor"] == round(expected, 3)
    assert result["projection"]["rest_factor"] < 1
    # The old ladder divided by the rested mean and floored small samples at 0.95.
    rested_only = 10 / 1
    assert result["b2b"]["factor"] != round(min(1.2, max(0.7, 1 / rested_only)), 3)


def test_real_boxscore_does_not_apply_a_power_play_multiplier(capsys):
    import json
    from pathlib import Path
    import shots
    fixture = Path(__file__).resolve().parent / "fixtures" / "boxscore-2024021308.json"
    raw = fixture.read_text()
    assert "powerPlayToi" not in raw
    box = json.loads(raw)
    assert box["id"] == 2024021308
    assert box["playerByGameStats"]["homeTeam"]["forwards"]
    games = [{"gameDate": "2025-04-17", "gameId": 2024021308, "shots": 1,
              "homeRoadFlag": "H", "toi": "15:36", "opponentAbbrev": "DET"}]
    plain = shots.analyze_player(8479318, games=games, game_date="2025-04-18", boxscores={})
    with_box = shots.analyze_player(
        8479318, games=games, game_date="2025-04-18",
        boxscores={2024021308: box, "2024021308": box})
    assert with_box["data_quality"]["pp_data_available"] is False
    assert with_box["projection"]["pp_factor"] == 1.0
    assert with_box["projection"]["expected_shots"] == plain["projection"]["expected_shots"]
    shots.print_analysis(with_box)
    printed = capsys.readouterr().out
    assert "Power play data available: no" in printed
    assert "Live power-play multiplier is not applied." in printed


def test_every_team_maps_under_stats_and_odds_spellings():
    import shots
    assert shots.get_team_abbrev("Not A Real Club") is None
    assert shots.get_team_abbrev("St Louis Blues") != "ST "
    for abbrev, (stats_name, odds_name) in shots.TEAM_SPELLINGS.items():
        assert shots.get_team_abbrev(stats_name) == abbrev
        assert shots.get_team_abbrev(odds_name) == abbrev
        # Punctuation and accents collapse to the same key.
        assert shots.get_team_abbrev(stats_name.replace(".", "")) == abbrev


def test_default_forecast_uses_blend_only_with_a_prior_log():
    import shots
    from probability_model import blend_mean
    current = [{"gameDate": f"2026-10-{i+1:02d}", "shots": 4, "homeRoadFlag": "H"} for i in range(3)]
    prior = [{"gameDate": f"2025-10-{i+1:02d}", "shots": 2, "homeRoadFlag": "H"} for i in range(25)]
    blended = shots.default_count_forecast(current, prior, "2026-10-10")
    assert blended["model"] == "blend20_nb20"
    assert blended["distribution"] == "negative_binomial"
    assert blended["dispersion"] == 20
    assert blended["expected_shots"] == blend_mean(
        shots.prepare_game_log(current, "2026-10-10"),
        shots.prepare_game_log(prior, "2026-10-10"), 20, 30)
    season = shots.default_count_forecast(current, prior[:5], "2026-10-10")
    assert season["model"] == "season_mean"
    assert season["distribution"] == "poisson"
    assert season["expected_shots"] == 4
    assert "error" in shots.default_count_forecast([], prior, "2026-10-10")


def test_heuristic_flag_prints_validation_comparison(capsys, monkeypatch):
    import shots
    log = {"seasonId": 20242025, "gameTypeId": 2, "gameLog": [
        {"gameDate": "2024-10-01", "shots": 3, "homeRoadFlag": "H", "toi": "18:00"}]}
    monkeypatch.setattr(shots, "api_request", lambda *a, **k: log)
    shots.run_prediction(1, None, True, None, None, "2024-10-03", "20242025", True)
    out = capsys.readouterr().out
    assert "Power play data available: no" in out
    assert "0.146610" in out and "0.148067" in out and "0.149249" in out
    assert "2025-26 holdout not used" in out
