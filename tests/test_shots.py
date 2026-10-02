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
