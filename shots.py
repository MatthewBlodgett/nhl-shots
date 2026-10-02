#!/usr/bin/env python3
"""
NHL Shots on Goal Predictor
Predicts shot totals for NHL player prop bets using Poisson distribution.
"""
import requests
import json
import time
import warnings
from math import factorial, exp, floor, isfinite
from typing import Optional
from datetime import datetime

# ── API layer: caching, rate limiting, retry ────────────────────────

_API_CACHE: dict = {}
_API_LAST_CALL: float = 0.0
_API_MIN_INTERVAL: float = 0.3       # seconds between API calls
_API_CACHE_TTL: int = 300             # default cache TTL (5 min)
_MAX_RETRIES: int = 3


def api_request(url: str, cache_ttl: int | None = None) -> dict | None:
    """Make an API request with caching, rate limiting, and retry logic.

    Returns the parsed JSON dict on success, or None on failure.
    Cache keyed by URL; TTL defaults to _API_CACHE_TTL.
    """
    global _API_LAST_CALL
    ttl = _API_CACHE_TTL if cache_ttl is None else cache_ttl
    now = time.time()

    # Cache hit
    if url in _API_CACHE:
        cached_at, cached_data = _API_CACHE[url]
        if now - cached_at < ttl:
            return cached_data

    # Rate limit
    elapsed = now - _API_LAST_CALL
    if elapsed < _API_MIN_INTERVAL:
        time.sleep(_API_MIN_INTERVAL - elapsed)

    # Retry with exponential backoff
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=10)
            _API_LAST_CALL = time.time()
            if resp.status_code == 200:
                data = resp.json()
                _API_CACHE[url] = (time.time(), data)
                return data
            if resp.status_code == 429:
                warnings.warn(f"Rate limited on {url}, retry {attempt + 1}")
                time.sleep(2 ** attempt)
            else:
                warnings.warn(
                    f"API returned {resp.status_code} for {url}"
                )
                return None
        except requests.RequestException as e:
            warnings.warn(f"API request failed (attempt {attempt + 1}): {e}")
            if attempt < _MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    return None


# ── Season auto-detection ──────────────────────────────────────────

def get_current_season(game_date: str | None = None) -> str:
    """Auto-detect the current NHL season ID.

    The NHL season ID format is ``YYYYYYYY`` (e.g. ``20252026``).
    A season starts in October; games before Oct belong to the previous year's season.
    """
    now = datetime.strptime(game_date, "%Y-%m-%d") if game_date else datetime.now()
    year, month = now.year, now.month
    if month >= 10:
        return f"{year}{year + 1}"
    return f"{year - 1}{year}"


# ── Constants ──────────────────────────────────────────────────────

BASE_URL = "https://api-web.nhle.com/v1"
STATS_URL = "https://api.nhle.com/stats/rest/en"

# Default B2B fatigue factor (used when player sample size too small)
DEFAULT_B2B_FACTOR = 0.95  # 5% reduction on back-to-backs
MIN_B2B_SAMPLE = 5  # Minimum B2B games needed for player-specific factor

# Common player IDs for quick lookup
PLAYER_IDS = {
    "mcdavid": 8478402,
    "draisaitl": 8477934,
    "matthews": 8479318,
    "mackinnon": 8477492,
    "kucherov": 8476453,
    "ovechkin": 8471214,
    "makar": 8480069,
    "pastrnak": 8477956,
    "kaprizov": 8478864,
    "stamkos": 8474564,
    "rantanen": 8478420,
    "marchand": 8473419,
    "huberdeau": 8476456,
    "fox": 8479323,
    "hedman": 8475167,
}

# Team abbreviation to ID mapping
TEAM_IDS = {}
TEAM_STATS_CACHE = {}
LEAGUE_AVG_SHOTS_AGAINST = None
BOXSCORE_CACHE: dict = {}  # game_id → boxscore data


def get_team_stats(season: str | None = None) -> dict:
    """Fetch all team stats including shots against per game."""
    global TEAM_STATS_CACHE, LEAGUE_AVG_SHOTS_AGAINST, TEAM_IDS

    if season is None:
        season = get_current_season()

    if season in TEAM_STATS_CACHE:
        stats = TEAM_STATS_CACHE[season]
        total_games = sum(t["games"] for t in stats.values())
        LEAGUE_AVG_SHOTS_AGAINST = (
            sum(t["shots_against_pg"] * t["games"] for t in stats.values()) / total_games
            if total_games else 30.0
        )
        return stats

    stats = {}

    url = f"{STATS_URL}/team/summary?cayenneExp=seasonId={season}%20and%20gameTypeId=2"
    data = api_request(url)
    if not data:
        warnings.warn("Failed to fetch team stats; opponent adjustment disabled")
        return {}

    rows = data.get("data", [])
    total_shots_against = 0
    total_games = 0

    for team in rows:
        team_name = team.get("teamFullName", "")
        team_id = team.get("teamId")
        shots_against = team.get("shotsAgainstPerGame", 30)
        shots_for = team.get("shotsForPerGame", 30)
        games = team.get("gamesPlayed", 1)

        abbrev = get_team_abbrev(team_name)

        stats[abbrev] = {
            "name": team_name,
            "id": team_id,
            "shots_against_pg": shots_against,
            "shots_for_pg": shots_for,
            "games": games,
        }
        TEAM_IDS[abbrev] = team_id

        total_shots_against += shots_against * games
        total_games += games

    LEAGUE_AVG_SHOTS_AGAINST = total_shots_against / total_games if total_games > 0 else 30.0
    if stats:
        TEAM_STATS_CACHE[season] = stats
    return stats


def get_team_abbrev(full_name: str) -> str:
    """Convert full team name to abbreviation."""
    mapping = {
        "Anaheim Ducks": "ANA",
        "Arizona Coyotes": "ARI",
        "Boston Bruins": "BOS",
        "Buffalo Sabres": "BUF",
        "Calgary Flames": "CGY",
        "Carolina Hurricanes": "CAR",
        "Chicago Blackhawks": "CHI",
        "Colorado Avalanche": "COL",
        "Columbus Blue Jackets": "CBJ",
        "Dallas Stars": "DAL",
        "Detroit Red Wings": "DET",
        "Edmonton Oilers": "EDM",
        "Florida Panthers": "FLA",
        "Los Angeles Kings": "LAK",
        "Minnesota Wild": "MIN",
        "Montreal Canadiens": "MTL",
        "Montréal Canadiens": "MTL",
        "Nashville Predators": "NSH",
        "New Jersey Devils": "NJD",
        "New York Islanders": "NYI",
        "New York Rangers": "NYR",
        "Ottawa Senators": "OTT",
        "Philadelphia Flyers": "PHI",
        "Pittsburgh Penguins": "PIT",
        "San Jose Sharks": "SJS",
        "Seattle Kraken": "SEA",
        "St. Louis Blues": "STL",
        "Tampa Bay Lightning": "TBL",
        "Toronto Maple Leafs": "TOR",
        "Utah Hockey Club": "UTA",
        "Vancouver Canucks": "VAN",
        "Vegas Golden Knights": "VGK",
        "Washington Capitals": "WSH",
        "Winnipeg Jets": "WPG",
    }
    return mapping.get(full_name, full_name[:3].upper())


def get_opponent_adjustment(opponent_abbrev: str, team_stats: dict | None = None) -> float:
    """Calculate opponent strength adjustment factor.

    Returns a multiplier based on how many shots the opponent allows
    vs. league average. >1.0 means opponent allows more shots (good),
    <1.0 means opponent allows fewer shots (bad).
    """
    team_stats = get_team_stats() if team_stats is None else team_stats
    if not team_stats or opponent_abbrev not in team_stats:
        return 1.0

    opp_sa = team_stats[opponent_abbrev]["shots_against_pg"]
    total_games = sum(t["games"] for t in team_stats.values())
    league_avg = (
        sum(t["shots_against_pg"] * t["games"] for t in team_stats.values()) / total_games
        if total_games else 0
    )
    return opp_sa / league_avg if league_avg > 0 else 1.0


def get_player_game_log(player_id: int, season: str | None = None) -> list:
    """Fetch player's game log for the season."""
    if season is None:
        season = get_current_season()
    url = f"{BASE_URL}/player/{player_id}/game-log/{season}/2"
    data = api_request(url)
    if not data:
        warnings.warn(f"No game log data for player {player_id}")
        return []
    return data.get("gameLog", [])


def get_player_info(player_id: int) -> dict:
    """Fetch player info."""
    url = f"{BASE_URL}/player/{player_id}/landing"
    data = api_request(url)
    if not data:
        warnings.warn(f"No player info for {player_id}")
        return {}
    return data


def get_boxscore(game_id: int) -> dict:
    """Fetch boxscore data for a specific game.

    Results are cached in BOXSCORE_CACHE to minimise API calls
    (especially important for PP-time analysis).
    """
    if game_id in BOXSCORE_CACHE:
        return BOXSCORE_CACHE[game_id]

    url = f"{BASE_URL}/gamecenter/{game_id}/boxscore"
    data = api_request(url, cache_ttl=3600)  # boxscores never change
    if data:
        BOXSCORE_CACHE[game_id] = data
    return data or {}


def parse_toi(toi_str: str) -> float:
    """Convert TOI string like '21:30' to minutes as float."""
    if not toi_str:
        return 0.0
    try:
        parts = toi_str.split(":")
        return float(parts[0]) + float(parts[1]) / 60.0
    except (ValueError, IndexError):
        return 0.0


def prepare_game_log(games: list, before_date: str | None = None) -> list:
    """Return dated games newest first, strictly before the prediction date.

    Never mutate the caller's data. Undated rows are only allowed for
    standalone summary calculations, never for prediction history.
    """
    if before_date is not None:
        datetime.strptime(before_date, "%Y-%m-%d")
    for game in games:
        datetime.strptime(game["gameDate"], "%Y-%m-%d")
    return sorted(
        (g for g in games if before_date is None or g["gameDate"] < before_date),
        key=lambda g: (g["gameDate"], g.get("gameId", 0)), reverse=True,
    )


# ── Rest analysis ──────────────────────────────────────────────────

def analyze_rest_days(games: list) -> dict:
    """Analyze player's performance based on days of rest.

    Tracks 0 (B2B), 1, 2, 3+ days rest and returns per-tier averages
    plus a player-specific B2B factor.
    """
    if not games:
        return {
            "b2b_games": 0,
            "one_day_games": 0,
            "two_day_games": 0,
            "three_plus_games": 0,
            "b2b_avg": 0,
            "one_day_avg": 0,
            "two_day_avg": 0,
            "three_plus_avg": 0,
            "rest_avg": 0,
            "factor": DEFAULT_B2B_FACTOR,
            "is_default": True,
        }

    games = prepare_game_log(games)
    b2b_shots = []
    one_day_shots = []
    two_day_shots = []
    three_plus_shots = []

    for i, game in enumerate(games):
        try:
            date = datetime.strptime(game["gameDate"], "%Y-%m-%d")
            shots = game.get("shots", 0)

            if i + 1 < len(games):
                prev_date = datetime.strptime(games[i + 1]["gameDate"], "%Y-%m-%d")
                days_rest = (date - prev_date).days - 1

                if days_rest == 0:
                    b2b_shots.append(shots)
                elif days_rest == 1:
                    one_day_shots.append(shots)
                elif days_rest == 2:
                    two_day_shots.append(shots)
                else:
                    three_plus_shots.append(shots)
            else:
                # First game of season, treat as 2+ days rest
                two_day_shots.append(shots)
        except (KeyError, ValueError):
            continue

    b2b_avg = sum(b2b_shots) / len(b2b_shots) if b2b_shots else 0
    one_day_avg = sum(one_day_shots) / len(one_day_shots) if one_day_shots else 0
    two_day_avg = sum(two_day_shots) / len(two_day_shots) if two_day_shots else 0
    three_plus_avg = sum(three_plus_shots) / len(three_plus_shots) if three_plus_shots else 0

    rest_shots = one_day_shots + two_day_shots + three_plus_shots
    rest_avg = sum(rest_shots) / len(rest_shots) if rest_shots else 0

    if len(b2b_shots) >= MIN_B2B_SAMPLE and rest_avg > 0:
        factor = b2b_avg / rest_avg
        factor = max(0.7, min(1.2, factor))
        is_default = False
    else:
        factor = DEFAULT_B2B_FACTOR
        is_default = True

    return {
        "b2b_games": len(b2b_shots),
        "one_day_games": len(one_day_shots),
        "two_day_games": len(two_day_shots),
        "three_plus_games": len(three_plus_shots),
        "b2b_avg": round(b2b_avg, 2),
        "one_day_avg": round(one_day_avg, 2),
        "two_day_avg": round(two_day_avg, 2),
        "three_plus_avg": round(three_plus_avg, 2),
        "rest_avg": round(rest_avg, 2),
        "factor": round(factor, 3),
        "is_default": is_default,
    }


def analyze_back_to_back(games: list) -> dict:
    """Legacy wrapper for backward compatibility."""
    rest_data = analyze_rest_days(games)
    return {
        "b2b_games": rest_data["b2b_games"],
        "rest_games": rest_data["one_day_games"] + rest_data["two_day_games"] + rest_data["three_plus_games"],
        "b2b_avg": rest_data["b2b_avg"],
        "rest_avg": rest_data["rest_avg"],
        "factor": rest_data["factor"],
        "is_default": rest_data["is_default"],
    }


# ── Home / away splits ─────────────────────────────────────────────

def analyze_home_away_splits(games: list) -> dict:
    """Analyze player's home vs away shot splits.

    Returns player-specific home/away factors based on actual performance.
    Minimum sample: 15 games per location; falls back to league-average
    factors for small samples.
    """
    if not games:
        return {
            "home_games": 0,
            "away_games": 0,
            "home_avg": 0.0,
            "away_avg": 0.0,
            "home_factor": 1.05,
            "away_factor": 0.95,
            "ratio": 1.0,
            "is_player_specific": False,
            "sample_sufficient": False,
        }

    home_shots = []
    away_shots = []

    for game in games:
        shots = game.get("shots", 0)
        location = game.get("homeRoadFlag", "")
        if location == "H":
            home_shots.append(shots)
        elif location == "R":
            away_shots.append(shots)

    home_avg = sum(home_shots) / len(home_shots) if home_shots else 0
    away_avg = sum(away_shots) / len(away_shots) if away_shots else 0

    MIN_GAMES = 15
    sample_sufficient = len(home_shots) >= MIN_GAMES and len(away_shots) >= MIN_GAMES

    all_shots = home_shots + away_shots
    season_avg = sum(all_shots) / len(all_shots) if all_shots else 0

    if sample_sufficient and season_avg > 0:
        home_factor = home_avg / season_avg
        away_factor = away_avg / season_avg
        ratio = home_avg / away_avg if away_avg > 0 else 1.0
        home_factor = max(0.75, min(1.35, home_factor))
        away_factor = max(0.75, min(1.35, away_factor))
        is_player_specific = True
    else:
        home_factor = 1.05
        away_factor = 0.95
        ratio = home_avg / away_avg if (away_avg > 0 and home_avg > 0) else 1.0
        is_player_specific = False

    return {
        "home_games": len(home_shots),
        "away_games": len(away_shots),
        "home_avg": round(home_avg, 2),
        "away_avg": round(away_avg, 2),
        "home_factor": round(home_factor, 3),
        "away_factor": round(away_factor, 3),
        "ratio": round(ratio, 3),
        "is_player_specific": is_player_specific,
        "sample_sufficient": sample_sufficient,
    }


# ── Rest helpers ───────────────────────────────────────────────────

def get_days_rest(games: list, game_date: Optional[str] = None) -> int:
    """Calculate days of rest before the given date.

    Returns 0 (B2B), 1, 2, 3, 4+ days.
    """
    if not games:
        return 2

    game_date = game_date or datetime.now().strftime("%Y-%m-%d")
    target_date = datetime.strptime(game_date, "%Y-%m-%d")
    games = prepare_game_log(games, game_date)

    for game in games:
        try:
            last_date = datetime.strptime(game["gameDate"], "%Y-%m-%d")
            days_since = (target_date - last_date).days
            return max(0, days_since - 1)
        except (KeyError, ValueError):
            continue
    return 2


def is_player_on_b2b(games: list, game_date: Optional[str] = None) -> bool:
    """Check if player is on a back-to-back for the given date."""
    return get_days_rest(games, game_date) == 0


# ── PP time & TOI analysis ─────────────────────────────────────────

def analyze_pp_time(games: list, player_id: int, num_games: int = 5,
                    boxscores: dict | None = None) -> dict:
    """Analyze player's power play time from recent games.

    Fetches boxscore data to get PP TOI. Limited to 3 API calls;
    uses the BOXSCORE_CACHE to avoid redundant fetches.
    """
    if not games:
        return {"games_analyzed": 0, "avg_pp_toi": 0.0,
                "has_significant_pp": False, "factor": 1.0, "error": None}

    recent_games = games[:num_games]
    pp_times = []
    attempts = 0
    max_attempts = min(num_games, 3)

    for game in recent_games:
        if attempts >= max_attempts:
            break
        game_id = game.get("gameId")
        if not game_id:
            continue
        attempts += 1

        boxscore = (get_boxscore(game_id) if boxscores is None
                    else boxscores.get(str(game_id), boxscores.get(game_id, {})))
        if not boxscore:
            continue

        player_stats = None
        for team_key in ("homeTeam", "awayTeam"):
            team_data = boxscore.get("playerByGameStats", {}).get(team_key, {})
            for position in ("forwards", "defense"):
                for player in team_data.get(position, []):
                    if player.get("playerId") == player_id:
                        player_stats = player
                        break
                if player_stats:
                    break
            if player_stats:
                break

        if player_stats and "powerPlayToi" in player_stats:
            pp_times.append(parse_toi(player_stats["powerPlayToi"]))

    avg_pp_toi = sum(pp_times) / len(pp_times) if pp_times else 0.0

    if avg_pp_toi >= 5.0:
        factor, significant = 1.12, True
    elif avg_pp_toi >= 4.0:
        factor, significant = 1.08, True
    elif avg_pp_toi >= 2.0:
        factor, significant = 1.03, False
    else:
        factor, significant = 1.0, False

    return {
        "games_analyzed": len(pp_times),
        "avg_pp_toi": round(avg_pp_toi, 2),
        "has_significant_pp": significant,
        "factor": round(factor, 3),
        "error": None if pp_times else "No PP data available",
    }


def analyze_toi_trends(games: list, player_id: int, num_recent: int = 5) -> dict:
    """Analyze time on ice trends comparing recent games to season average.

    Detects if a player's role is rising, declining, or stable.
    """
    if not games or len(games) < num_recent:
        return {"recent_games": 0, "recent_avg_toi": 0.0,
                "season_avg_toi": 0.0, "trend": "neutral", "factor": 1.0}

    recent_games = games[:num_recent]
    recent_toi_values = []
    all_toi_values = []

    for game in games:
        toi_minutes = parse_toi(game.get("toi", ""))
        if toi_minutes > 0:
            all_toi_values.append(toi_minutes)
            if game in recent_games:
                recent_toi_values.append(toi_minutes)

    recent_avg = sum(recent_toi_values) / len(recent_toi_values) if recent_toi_values else 0
    season_avg = sum(all_toi_values) / len(all_toi_values) if all_toi_values else 0

    if season_avg == 0:
        return {"recent_games": len(recent_toi_values), "recent_avg_toi": round(recent_avg, 2),
                "season_avg_toi": 0.0, "trend": "neutral", "factor": 1.0}

    diff = recent_avg - season_avg
    if diff >= 2.0:
        trend, factor = "rising", 1.06
    elif diff <= -2.0:
        trend, factor = "declining", 0.92
    else:
        trend, factor = "neutral", 1.0

    return {"recent_games": len(recent_toi_values), "recent_avg_toi": round(recent_avg, 2),
            "season_avg_toi": round(season_avg, 2), "diff": round(diff, 2),
            "trend": trend, "factor": round(factor, 3)}


# ── Stats & probability ────────────────────────────────────────────

def calculate_stats(games: list, num_games: Optional[int] = None) -> dict:
    """Calculate shooting statistics from game log."""
    if games and all("gameDate" in g for g in games):
        games = prepare_game_log(games)
    if num_games:
        games = games[:num_games]
    if not games:
        return {"avg": 0, "total": 0, "games": 0, "shots_list": [],
                "home_avg": 0, "away_avg": 0, "max": 0, "min": 0}

    shots = [g.get("shots", 0) for g in games]
    home_shots = [g.get("shots", 0) for g in games if g.get("homeRoadFlag") == "H"]
    away_shots = [g.get("shots", 0) for g in games if g.get("homeRoadFlag") == "R"]

    return {
        "avg": sum(shots) / len(shots) if shots else 0,
        "total": sum(shots),
        "games": len(shots),
        "shots_list": shots,
        "home_avg": sum(home_shots) / len(home_shots) if home_shots else 0,
        "away_avg": sum(away_shots) / len(away_shots) if away_shots else 0,
        "max": max(shots) if shots else 0,
        "min": min(shots) if shots else 0,
    }


def poisson_probability(k: int, lambda_: float) -> float:
    """Calculate P(X = k) for Poisson distribution."""
    if not isfinite(lambda_) or lambda_ < 0:
        raise ValueError("Expected shots must be finite and nonnegative")
    if not isinstance(k, int) or k < 0:
        raise ValueError("Shot count must be a nonnegative integer")
    if lambda_ == 0:
        return 1.0 if k == 0 else 0.0
    return (lambda_ ** k * exp(-lambda_)) / factorial(k)


def prob_over(line: float, lambda_: float) -> float:
    """Calculate probability of going OVER a line (e.g., 3.5 shots)."""
    if not isfinite(line) or line < 0:
        raise ValueError("Line must be finite and nonnegative")
    threshold = floor(line)
    prob_under_or_equal = sum(poisson_probability(k, lambda_) for k in range(threshold + 1))
    return max(0.0, min(1.0, 1 - prob_under_or_equal))


def prob_under(line: float, lambda_: float) -> float:
    """Calculate probability of going UNDER a line."""
    if not isfinite(line) or line < 0:
        raise ValueError("Line must be finite and nonnegative")
    # At integer lines, P(equal) is a push, not an under win.
    poisson_probability(0, lambda_)  # validate even when no counts are below the line
    threshold = int(line) - 1 if float(line).is_integer() else floor(line)
    return sum(poisson_probability(k, lambda_) for k in range(threshold + 1))


# ── Main analysis ──────────────────────────────────────────────────

def analyze_player(
    player_id: int,
    line: Optional[float] = None,
    is_home: bool = True,
    opponent: Optional[str] = None,
    is_b2b: Optional[bool] = None,
    game_date: Optional[str] = None,
    *,
    season: str | None = None,
    games: list | None = None,
    player_info: dict | None = None,
    team_stats: dict | None = None,
    boxscores: dict | None = None,
    weights: tuple[float, float, float] = (0.5, 0.3, 0.2),
) -> dict:
    """Analyze only history before the target date (today by default).

    Supplied history runs without live metadata, opponent stats or boxscore
    calls. Historical callers must supply dated team stats explicitly;
    otherwise opponent adjustment is neutral rather than leaking future data.
    Explicit `rest` means at least one rest day, retaining the inferred tier.
    """
    if len(weights) != 3 or any(not isfinite(w) or w < 0 for w in weights) or abs(sum(weights) - 1) > 1e-9:
        raise ValueError("Three nonnegative weights must sum to one")
    isolated = games is not None or game_date is not None
    game_date = game_date or datetime.now().strftime("%Y-%m-%d")
    season = season or get_current_season(game_date)
    if games is None:
        games = get_player_game_log(player_id, season)
    games = prepare_game_log(games, game_date)
    info = player_info if player_info is not None else ({} if isolated else get_player_info(player_id))
    if boxscores is None and isolated:
        boxscores = {}
    if team_stats is None:
        team_stats = {} if isolated else (get_team_stats(season) if opponent else {})

    if not games:
        return {"error": "No game data found"}

    season_stats = calculate_stats(games)
    last_5 = calculate_stats(games, 5)
    last_10 = calculate_stats(games, 10)

    # Days rest
    rest_analysis = analyze_rest_days(games)
    days_rest = get_days_rest(games, game_date)
    b2b_analysis = analyze_back_to_back(games)
    if is_b2b is True:
        days_rest = 0
    elif is_b2b is False:
        days_rest = max(1, days_rest)
    is_b2b = days_rest == 0

    # PP time & TOI trends
    pp_analysis = analyze_pp_time(games, player_id, boxscores=boxscores)
    toi_analysis = analyze_toi_trends(games, player_id)

    # Home/away splits
    home_away_splits = analyze_home_away_splits(games)

    # Weighted average: 50% season, 30% last 10, 20% last 5
    base_lambda = (
        season_stats["avg"] * weights[0]
        + last_10["avg"] * weights[1]
        + last_5["avg"] * weights[2]
    )

    # Location factor (player-specific)
    location_factor = (
        home_away_splits["home_factor"] if is_home
        else home_away_splits["away_factor"]
    )

    adjusted_lambda = base_lambda * location_factor

    # Opponent strength
    opponent_factor = 1.0
    opponent_info = None
    if opponent:
        opp = opponent.upper()
        opponent_factor = get_opponent_adjustment(opp, team_stats)
        if opp in team_stats:
            total_games = sum(t["games"] for t in team_stats.values())
            league_avg = sum(t["shots_against_pg"] * t["games"] for t in team_stats.values()) / total_games if total_games else 0
            opponent_info = {
                "abbrev": opp,
                "name": team_stats[opp]["name"],
                "shots_against_pg": round(team_stats[opp]["shots_against_pg"], 1),
                "league_avg": round(league_avg, 1),
                "factor": round(opponent_factor, 3),
            }
        adjusted_lambda *= opponent_factor

    # Rest factor
    if days_rest == 0:
        rest_factor = b2b_analysis["factor"]
    elif days_rest == 1:
        rest_factor = 0.95
    elif days_rest == 2:
        rest_factor = 1.0
    else:
        rest_factor = 1.03
    adjusted_lambda *= rest_factor

    # PP factor
    pp_factor = pp_analysis["factor"]
    adjusted_lambda *= pp_factor

    # TOI trend factor
    toi_factor = toi_analysis["factor"]
    adjusted_lambda *= toi_factor

    # Player name
    first_name = info.get("firstName", {}).get("default", "")
    last_name = info.get("lastName", {}).get("default", "")
    player_name = f"{first_name} {last_name}".strip() or f"Player {player_id}"
    team = info.get("currentTeamAbbrev", "")

    result = {
        "game_date": game_date,
        "season_id": season,
        "history_through": games[0]["gameDate"],
        "data_quality": {
            "opponent_adjustment_available": opponent_info is not None,
            "pp_data_available": pp_analysis["games_analyzed"] > 0,
        },
        "player": player_name,
        "team": team,
        "player_id": player_id,
        "season": {
            "games": season_stats["games"],
            "total_shots": season_stats["total"],
            "avg": round(season_stats["avg"], 2),
            "home_avg": round(season_stats["home_avg"], 2),
            "away_avg": round(season_stats["away_avg"], 2),
        },
        "last_5": {"shots": last_5["shots_list"], "avg": round(last_5["avg"], 2)},
        "last_10": {"avg": round(last_10["avg"], 2)},
        "b2b": {
            "is_b2b": is_b2b,
            "b2b_games": b2b_analysis["b2b_games"],
            "b2b_avg": b2b_analysis["b2b_avg"],
            "rest_avg": b2b_analysis["rest_avg"],
            "factor": b2b_analysis["factor"],
            "is_default": b2b_analysis["is_default"],
        },
        "rest": {
            "days_rest": days_rest,
            "rest_label": ["B2B", "1 day", "2 days", "3+ days"][min(days_rest, 3)],
            "b2b_avg": rest_analysis["b2b_avg"],
            "one_day_avg": rest_analysis["one_day_avg"],
            "two_day_avg": rest_analysis["two_day_avg"],
            "three_plus_avg": rest_analysis["three_plus_avg"],
            "factor": round(rest_factor, 3),
        },
        "pp_time": {
            "games_analyzed": pp_analysis["games_analyzed"],
            "avg_pp_toi": pp_analysis["avg_pp_toi"],
            "has_significant_pp": pp_analysis["has_significant_pp"],
            "factor": pp_analysis["factor"],
        },
        "toi_trend": {
            "recent_avg": toi_analysis["recent_avg_toi"],
            "season_avg": toi_analysis["season_avg_toi"],
            "diff": toi_analysis.get("diff", 0),
            "trend": toi_analysis["trend"],
            "factor": toi_analysis["factor"],
        },
        "home_away": {
            "home_games": home_away_splits["home_games"],
            "away_games": home_away_splits["away_games"],
            "home_avg": home_away_splits["home_avg"],
            "away_avg": home_away_splits["away_avg"],
            "ratio": home_away_splits["ratio"],
            "home_factor": home_away_splits["home_factor"],
            "away_factor": home_away_splits["away_factor"],
            "is_player_specific": home_away_splits["is_player_specific"],
            "sample_sufficient": home_away_splits["sample_sufficient"],
        },
        "projection": {
            "base_lambda": round(base_lambda, 2),
            "location_factor": round(location_factor, 3),
            "opponent_factor": round(opponent_factor, 3),
            "rest_factor": round(rest_factor, 3),
            "pp_factor": round(pp_factor, 3),
            "toi_factor": round(toi_factor, 3),
            "final_lambda": round(adjusted_lambda, 2),
            "expected_shots": adjusted_lambda,
            "location": "home" if is_home else "away",
        },
        "opponent": opponent_info,
        "probabilities": {},
    }

    # Calculate probabilities for common lines
    lines = [1.5, 2.5, 3.5, 4.5, 5.5]
    if line and line not in lines:
        lines.append(line)
        lines.sort()

    for l in lines:
        over = prob_over(l, adjusted_lambda)
        result["probabilities"][f"{l}"] = {
            "over": f"{over*100:.1f}%",
            "under": f"{prob_under(l, adjusted_lambda)*100:.1f}%",
        }

    return result


# ── Output ─────────────────────────────────────────────────────────

def print_analysis(result: dict):
    """Pretty print analysis results."""
    if "error" in result:
        print(f"Error: {result['error']}")
        return

    print(f"\n{'='*60}")
    print(f"  {result['player']} ({result['team']})")
    print(f"{'='*60}")

    print(f"\n📊 Season Stats ({result['season']['games']} games):")
    print(f"   Total Shots: {result['season']['total_shots']}")
    print(f"   Average: {result['season']['avg']} shots/game")
    print(f"   Home Avg: {result['season']['home_avg']} | Away Avg: {result['season']['away_avg']}")

    print(f"\n🔥 Recent Form:")
    print(f"   Last 5 games: {result['last_5']['shots']} (avg: {result['last_5']['avg']})")
    print(f"   Last 10 avg: {result['last_10']['avg']}")

    rest = result.get("rest", {})
    if rest:
        print(f"\n💤 Days Rest Analysis:")
        print(f"   Current: {rest['rest_label']} (factor: {rest['factor']}x)")
        if rest.get("b2b_avg", 0) > 0:
            print(f"   Historical: B2B={rest['b2b_avg']}, 1-day={rest['one_day_avg']}, "
                  f"2-day={rest['two_day_avg']}, 3+day={rest['three_plus_avg']}")

    b2b = result["b2b"]
    if b2b["b2b_games"] > 0 and not rest:
        print(f"\n😴 Back-to-Back History:")
        print(f"   B2B games: {b2b['b2b_games']} (avg: {b2b['b2b_avg']}) | Rest: {b2b['rest_avg']}")
        ftype = "default" if b2b["is_default"] else "player-specific"
        print(f"   B2B factor: {b2b['factor']}x ({ftype})")

    pp = result.get("pp_time", {})
    if pp and pp["games_analyzed"] > 0:
        emoji = "⚡" if pp["has_significant_pp"] else "🔌"
        print(f"\n{emoji} Power Play Time (L{pp['games_analyzed']}):")
        print(f"   Avg PP TOI: {pp['avg_pp_toi']:.2f} min/game")
        if pp["has_significant_pp"]:
            print(f"   Status: PP1 player (factor: {pp['factor']}x)")
        else:
            print(f"   Factor: {pp['factor']}x")

    toi = result.get("toi_trend", {})
    if toi and toi.get("season_avg", 0) > 0:
        emoji = {"rising": "📈", "declining": "📉", "neutral": "➡️"}.get(toi["trend"], "➡️")
        print(f"\n{emoji} Time on Ice Trend:")
        print(f"   Recent (L5): {toi['recent_avg']:.2f} min | Season: {toi['season_avg']:.2f} min")
        if toi["trend"] != "neutral":
            sign = "+" if toi.get("diff", 0) > 0 else ""
            print(f"   Trend: {toi['trend'].upper()} ({sign}{toi.get('diff', 0):.2f} min, factor: {toi['factor']}x)")
        else:
            print(f"   Trend: Stable (factor: {toi['factor']}x)")

    ha = result.get("home_away", {})
    if ha and ha.get("home_games", 0) > 0:
        print(f"\n🏠🛣️  Home/Away Splits:")
        print(f"   Home: {ha['home_avg']} avg ({ha['home_games']} games)")
        print(f"   Away: {ha['away_avg']} avg ({ha['away_games']} games)")
        print(f"   H/A Ratio: {ha['ratio']}x")
        if ha["is_player_specific"]:
            direction = "🏡" if ha["ratio"] > 1.1 else "🛫" if ha["ratio"] < 0.95 else "⚖️"
            print(f"   {direction} Player-specific factors: Home={ha['home_factor']}x, Away={ha['away_factor']}x")
        else:
            print(f"   ⚠️  Default factors used (sample: {ha['home_games']}/{ha['away_games']} games)")

    if result.get("opponent"):
        opp = result["opponent"]
        direction = "↑" if opp["factor"] > 1 else "↓" if opp["factor"] < 1 else "→"
        print(f"\n🆚 Opponent: {opp['name']} ({opp['abbrev']})")
        print(f"   Shots Against/Game: {opp['shots_against_pg']} (League Avg: {opp['league_avg']})")
        print(f"   Adjustment: {opp['factor']}x {direction}")

    print(f"\n🎯 Projection ({result['projection']['location'].upper()}):")
    proj = result["projection"]
    factors_applied = [f"Base: {proj['base_lambda']}", f"Loc: {proj['location_factor']}"]
    if result.get("opponent"):
        factors_applied.append(f"Opp: {proj['opponent_factor']}")
    if rest:
        factors_applied.append(f"Rest: {proj['rest_factor']}")
    if pp and pp.get("factor", 1.0) != 1.0:
        factors_applied.append(f"PP: {proj['pp_factor']}")
    if toi and toi.get("factor", 1.0) != 1.0:
        factors_applied.append(f"TOI: {proj['toi_factor']}")
    print(f"   {' × '.join(factors_applied)}")
    print(f"   Expected shots: {proj['final_lambda']}")

    print(f"\n📈 Line Probabilities:")
    print(f"   {'Line':<8} {'Over':<10} {'Under':<10}")
    print(f"   {'-'*28}")
    for line, probs in result["probabilities"].items():
        print(f"   {line:<8} {probs['over']:<10} {probs['under']:<10}")
    print()


# ── Schedule & teams ───────────────────────────────────────────────

def get_todays_games() -> list:
    """Fetch today's games."""
    today = datetime.now().strftime("%Y-%m-%d")
    url = f"{BASE_URL}/schedule/{today}"
    data = api_request(url)
    if not data:
        return []

    games = []
    for week in data.get("gameWeek", []):
        if week.get("date") == today:
            for game in week.get("games", []):
                if game.get("gameType") == 2:
                    games.append({
                        "id": game.get("id"),
                        "home": game.get("homeTeam", {}).get("abbrev"),
                        "away": game.get("awayTeam", {}).get("abbrev"),
                        "time": game.get("startTimeUTC"),
                    })
    return games


def list_teams():
    """List all teams with their shot stats."""
    team_stats = get_team_stats()
    if not team_stats:
        print("\nCould not fetch team stats. Check your network connection.\n")
        return

    print(f"\n{'='*70}")
    print(f"  NHL Team Shot Statistics ({get_current_season()[:4]}-{get_current_season()[4:]})")
    print(f"{'='*70}")
    print(f"\n  {'Team':<25} {'SA/G':<8} {'SF/G':<8} {'vs Avg':<10}")
    print(f"  {'-'*55}")

    sorted_teams = sorted(team_stats.items(), key=lambda x: x[1]["shots_against_pg"], reverse=True)
    for abbrev, stats in sorted_teams:
        factor = stats["shots_against_pg"] / LEAGUE_AVG_SHOTS_AGAINST
        direction = "↑" if factor > 1.02 else "↓" if factor < 0.98 else "→"
        print(f"  {stats['name']:<25} {stats['shots_against_pg']:<8.1f} {stats['shots_for_pg']:<8.1f} {factor:.3f}x {direction}")

    print(f"\n  League Avg Shots Against: {LEAGUE_AVG_SHOTS_AGAINST:.1f}\n")


def clear_cache():
    """Clear all cached API data and team stats."""
    global _API_CACHE, TEAM_STATS_CACHE, BOXSCORE_CACHE, LEAGUE_AVG_SHOTS_AGAINST, TEAM_IDS
    _API_CACHE.clear()
    TEAM_STATS_CACHE.clear()
    BOXSCORE_CACHE.clear()
    LEAGUE_AVG_SHOTS_AGAINST = None
    TEAM_IDS.clear()


# ── CLI ────────────────────────────────────────────────────────────

def main():
    import sys

    if len(sys.argv) < 2:
        season = get_current_season()
        print(f"NHL Shots on Goal Predictor — {season[:4]}-{season[4:]} season")
        print("=" * 48)
        print("\nUsage:")
        print("  python shots.py <player> [opponent] [line] [home|away] [b2b|rest]")
        print("  python shots.py teams            (list team shot stats)")
        print("  python shots.py clear-cache      (flush API cache)")
        print("\nExamples:")
        print("  python shots.py mcdavid")
        print("  python shots.py mcdavid CGY")
        print("  python shots.py mcdavid CGY 3.5 away")
        print("  python shots.py matthews MIN 4.5 home b2b")
        print("\nFlags:")
        print("  home/away   - game location (default: home)")
        print("  b2b         - player is on a back-to-back")
        print("  rest        - player is rested (not B2B)")
        print("\nQuick names:")
        for name in sorted(PLAYER_IDS.keys()):
            print(f"  - {name}")
        return

    # Special commands
    cmd = sys.argv[1].lower()
    if cmd == "teams":
        list_teams()
        return
    if cmd == "clear-cache":
        clear_cache()
        print("API cache cleared.")
        return

    # Parse player
    if cmd in PLAYER_IDS:
        player_id = PLAYER_IDS[cmd]
    else:
        try:
            player_id = int(cmd)
        except ValueError:
            print(f"Unknown player: {cmd}")
            return

    # Parse remaining args
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--date", help="Target game date, YYYY-MM-DD (default: today)")
    parser.add_argument("--season", help="Season ID, e.g. 20242025")
    options, remaining = parser.parse_known_args(sys.argv[2:])
    opponent = None
    line = None
    is_home = True
    is_b2b = None

    for arg in remaining:
        al = arg.lower()
        if al == "home":
            is_home = True
        elif al == "away":
            is_home = False
        elif al == "b2b":
            is_b2b = True
        elif al == "rest":
            is_b2b = False
        elif len(arg) == 3 and arg.upper().isalpha():
            opponent = arg.upper()
        else:
            try:
                line = float(arg)
            except ValueError:
                pass

    result = analyze_player(player_id, line, is_home, opponent, is_b2b,
                            game_date=options.date, season=options.season)
    print_analysis(result)


if __name__ == "__main__":
    main()
