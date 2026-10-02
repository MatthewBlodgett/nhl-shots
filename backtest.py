#!/usr/bin/env python3
"""Chronological shots evaluation using only information before each game."""
import argparse
import hashlib
import json
from math import sqrt
from pathlib import Path
from shots import (PLAYER_IDS, analyze_player, calculate_stats, get_current_season,
                   get_player_game_log, prepare_game_log, prob_over)

DEFAULT_CONFIDENCE = 0.55
DEFAULT_WEIGHTS = (0.5, 0.3, 0.2)
WEIGHT_CANDIDATES = (DEFAULT_WEIGHTS, (1., 0., 0.), (0., 1., 0.),
                     (0.7, 0.2, 0.1), (0.3, 0.4, 0.3))
MODELS = ("full", "season_average", "recent_average")


def validate_seasons(seasons):
    seasons = sorted(set(seasons))
    if not seasons or any(len(s) != 8 or not s.isdigit() or
                          int(s[4:]) != int(s[:4]) + 1 for s in seasons):
        raise ValueError("Use season IDs such as 20242025")
    return seasons


def validate_games(games):
    """Reject missing outcomes, ambiguous venues and duplicate game IDs."""
    seen = set()
    for g in games:
        prepare_game_log([g])
        if not isinstance(g.get("shots"), int) or g["shots"] < 0:
            raise ValueError("Each player game needs a nonnegative integer shots outcome")
        if g.get("homeRoadFlag") not in ("H", "R"):
            raise ValueError("Each player game needs homeRoadFlag H or R")
        key = g.get("gameId", g["gameDate"])
        if key in seen:
            raise ValueError(f"Duplicate player game: {key}")
        seen.add(key)


def team_stats_before(team_games, season, target_date):
    """Aggregate complete regular-season team games strictly before target_date.

    Each input row is one finalized game: season, gameDate, gameId, home,
    away, homeShots, awayShots. The caller must supply regular-season games.
    """
    totals, seen = {}, set()
    for game in team_games:
        if game["season"] != season or game["gameDate"] >= target_date:
            continue
        prepare_game_log([game])
        if game["gameId"] in seen:
            raise ValueError(f"Duplicate team game: {game['gameId']}")
        seen.add(game["gameId"])
        if game["home"] == game["away"]:
            raise ValueError("A team cannot play itself")
        for field in ("homeShots", "awayShots"):
            if not isinstance(game[field], int) or game[field] < 0:
                raise ValueError("Team shots must be nonnegative integers")
        for team, sf, sa in ((game["home"], game["homeShots"], game["awayShots"]),
                             (game["away"], game["awayShots"], game["homeShots"])):
            t = totals.setdefault(team, {"name": team, "games": 0, "sf": 0, "sa": 0})
            t["games"] += 1
            t["sf"] += sf
            t["sa"] += sa
    return {team: {"name": t["name"], "games": t["games"],
                   "shots_for_pg": t["sf"] / t["games"],
                   "shots_against_pg": t["sa"] / t["games"]}
            for team, t in totals.items()}


def evaluate_games(player_id, player_name, games, season, line=3, min_history=10,
                   team_games=(), boxscores=None, weights=DEFAULT_WEIGHTS):
    """Walk forward within one season; N+ means over N-0.5."""
    if not isinstance(line, int) or line < 1 or min_history < 1:
        raise ValueError("Positive integer N+ threshold and minimum history required")
    validate_games(games)
    records = []
    for current in reversed(prepare_game_log(games)):
        date = current["gameDate"]
        history = prepare_game_log(games, date)
        if len(history) < min_history:
            continue
        prediction = analyze_player(
            player_id, line=line - 0.5, is_home=current["homeRoadFlag"] == "H",
            opponent=current.get("opponentAbbrev"), game_date=date, season=season,
            games=history, player_info={},
            team_stats=team_stats_before(team_games, season, date),
            boxscores=boxscores or {}, weights=weights,
        )
        means = {
            "full": prediction["projection"]["expected_shots"],
            "season_average": calculate_stats(history)["avg"],
            "recent_average": calculate_stats(history, 10)["avg"],
        }
        records.append({
            "player_id": player_id, "player": player_name, "season": season,
            "game_date": date, "game_id": current.get("gameId"),
            "history_through": history[0]["gameDate"], "history_games": len(history),
            "actual": current["shots"], "line_n_plus": line,
            "outcome_over": int(current["shots"] >= line),
            "data_quality": prediction["data_quality"],
            "models": {name: {"expected_shots": mean,
                              "prob_over": prob_over(line - 0.5, mean)}
                       for name, mean in means.items()},
        })
    return records


def summarize(records, model="full", confidence=DEFAULT_CONFIDENCE):
    """MAE, RMSE, Brier and calibration on ALL eligible games, including skips."""
    if not 0.5 < confidence <= 1:
        raise ValueError("Confidence must be above 0.5 and at most 1")
    if not records:
        return {"games": 0, "mae": None, "rmse": None, "brier": None,
                "calibration": [], "bets": 0, "wins": 0, "skipped": 0,
                "illustrative_roi": None}
    errors, briers, calibration = [], [], [[] for _ in range(10)]
    bets = wins = 0
    for r in records:
        mean, p = r["models"][model]["expected_shots"], r["models"][model]["prob_over"]
        y = r["outcome_over"]
        errors.append(mean - r["actual"])
        briers.append((p - y) ** 2)
        calibration[min(9, int(p * 10))].append((p, y))
        if p >= confidence:
            bets += 1
            wins += y
        elif 1 - p >= confidence:
            bets += 1
            wins += 1 - y
    n = len(records)
    return {
        "games": n, "mae": sum(abs(e) for e in errors) / n,
        "rmse": sqrt(sum(e * e for e in errors) / n),
        "brier": sum(briers) / n,
        "calibration": [{"lower": i / 10, "upper": (i + 1) / 10,
                         "count": len(bucket),
                         "predicted": sum(p for p, _ in bucket) / len(bucket),
                         "observed": sum(y for _, y in bucket) / len(bucket)}
                        for i, bucket in enumerate(calibration) if bucket],
        "bets": bets, "wins": wins, "skipped": n - bets,
        "illustrative_roi": (wins * (100 / 110) - (bets - wins)) / bets if bets else None,
    }


def backtest_player(player_id, player_name, line=3, confidence=DEFAULT_CONFIDENCE,
                    *, season=None, games=None, team_games=(), boxscores=None):
    """Compatibility entry point with consistent probabilities and outcomes."""
    season = season or get_current_season()
    games = get_player_game_log(player_id, season) if games is None else games
    if not games:
        raise ValueError(f"No game data for {player_name}, season {season}")
    records = evaluate_games(player_id, player_name, games, season, line,
                             team_games=team_games, boxscores=boxscores)
    results = {"total_games": len(records), "bets_placed": 0, "skipped": 0,
               "over_wins": 0, "over_losses": 0, "under_wins": 0,
               "under_losses": 0, "predicted_overs": [], "predicted_unders": [],
               "records": records,
               "metrics": {m: summarize(records, m, confidence) for m in MODELS}}
    for r in records:
        p = r["models"]["full"]["prob_over"]
        side = "over" if p >= confidence else "under" if 1 - p >= confidence else None
        if side is None:
            results["skipped"] += 1
            continue
        win = bool(r["outcome_over"]) if side == "over" else not r["outcome_over"]
        results["bets_placed"] += 1
        results[f"{side}_{'wins' if win else 'losses'}"] += 1
        results[f"predicted_{side}s"].append((
            r["game_date"], r["models"]["full"]["expected_shots"],
            (p if side == "over" else 1 - p) * 100, r["actual"], "W" if win else "L"))
    return results


def chronological_evaluation(players, seasons, load_games, *, include_holdout=False,
                              tune_weights=False, line=3, confidence=DEFAULT_CONFIDENCE,
                              min_history=10, team_games=(), boxscores=None):
    """Tune on earliest season only; freeze before validation and final holdout.

    Latest season player logs are not loaded unless include_holdout is explicit.
    No previous-season blending yet; minimum history resets each season.
    """
    seasons = validate_seasons(seasons)
    if len(seasons) < 2:
        raise ValueError("Chronological evaluation requires at least two seasons")
    summarize([], confidence=confidence)
    if line < 1 or not isinstance(line, int) or min_history < 1:
        raise ValueError("Positive integer line and minimum history required")
    loaded, coverage = {}, []
    active = seasons if include_holdout else seasons[:-1]
    def load_season(season):
        for name, pid in players.items():
            games = load_games(pid, season)
            if not games:
                raise ValueError(f"Missing data for {name}, {season}; evaluation stopped")
            validate_games(games)
            loaded[(pid, season)] = games
            coverage.append({"player": name, "season": season, "input_games": len(games)})

    load_season(seasons[0])

    def evaluate(season, weights):
        rows = []
        for name, pid in players.items():
            rows.extend(evaluate_games(pid, name, loaded[(pid, season)], season,
                        line, min_history, team_games, boxscores, weights))
        return sorted(rows, key=lambda r: (r["game_date"], r["player_id"]))

    weights, tuning = DEFAULT_WEIGHTS, []
    if tune_weights:
        for candidate in WEIGHT_CANDIDATES:
            metrics = summarize(evaluate(seasons[0], candidate), confidence=confidence)
            if metrics["games"] == 0:
                raise ValueError("No eligible development games for tuning")
            tuning.append({"weights": candidate, "development_brier": metrics["brier"]})
        weights = min(tuning, key=lambda t: t["development_brier"])["weights"]
    config = {"players": players, "seasons": seasons, "line_n_plus": line,
              "confidence": confidence, "min_history": min_history,
              "weights": weights, "tune_weights": tune_weights}
    config["implementation_sha256"] = hashlib.sha256(
        Path(__file__).read_bytes() + Path(__file__).with_name("shots.py").read_bytes()
    ).hexdigest()
    report = {
        "protocol": config,
        "protocol_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
        "holdout_season": seasons[-1], "holdout_opened": include_holdout,
        "tuning": tuning, "coverage": coverage, "folds": [],
        "limitations": [
            "Player selection may introduce survivorship bias.",
            "Historical corrections are not timestamped snapshots of what was known live.",
            "ROI uses fixed hypothetical -110 odds; no market prices or available lines.",
            "Rest uses player appearances, not the team's full schedule.",
            "Opponent inputs require complete finalized regular-season team-game data.",
        ],
    }
    for season in active:
        if season != seasons[0]:
            load_season(season)
        records = evaluate(season, weights)
        if not records:
            raise ValueError(f"No eligible games in {season}")
        report["folds"].append({
            "season": season,
            "role": "development" if season == seasons[0] else
                    "holdout" if season == seasons[-1] else "validation",
            "metrics": {m: summarize(records, m, confidence) for m in MODELS},
            "opponent_data_games": sum(r["data_quality"]["opponent_adjustment_available"] for r in records),
            "pp_data_games": sum(r["data_quality"]["pp_data_available"] for r in records),
            "records": records,
        })
    report["input_sha256"] = {
        f"{pid}/{season}": hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        for (pid, season), data in loaded.items()
    }
    report["context_sha256"] = hashlib.sha256(json.dumps(
        {"team_games": team_games, "boxscores": boxscores or {}}, sort_keys=True
    ).encode()).hexdigest()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("player", help="Quick name, NHL player ID, or all")
    parser.add_argument("line", nargs="?", type=int, default=3, help="N+ shots, e.g. 3 = over 2.5")
    parser.add_argument("confidence", nargs="?", type=float, default=55, help="Percent, default 55")
    parser.add_argument("--seasons", nargs="+", help="Latest season held out by default")
    parser.add_argument("--season", help="Single-season evaluation")
    parser.add_argument("--include-holdout", action="store_true")
    parser.add_argument("--tune-weights", action="store_true", help="Select on development Brier only")
    parser.add_argument("--min-history", type=int, default=10)
    parser.add_argument("--dataset", type=Path, help="Offline JSON: players, team_games, boxscores")
    parser.add_argument("--output", type=Path, help="Detailed JSON report")
    args = parser.parse_args()
    if args.season and args.seasons:
        parser.error("Choose --season or --seasons")
    if (args.include_holdout or args.tune_weights) and not args.seasons:
        parser.error("Holdout and tuning options require --seasons")
    try:
        players = dict(PLAYER_IDS) if args.player == "all" else {
            args.player: PLAYER_IDS[args.player] if args.player in PLAYER_IDS else int(args.player)}
        dataset = json.loads(args.dataset.read_text()) if args.dataset else None
        team_games = dataset.get("team_games", []) if dataset else []
        boxscores = dataset.get("boxscores", {}) if dataset else {}

        def load(pid, season):
            if dataset is not None:
                return dataset.get("players", {}).get(str(pid), {}).get(season, [])
            return get_player_game_log(pid, season)

        confidence = args.confidence / 100
        if args.seasons:
            report = chronological_evaluation(players, args.seasons, load,
                include_holdout=args.include_holdout, tune_weights=args.tune_weights,
                line=args.line, confidence=confidence, min_history=args.min_history,
                team_games=team_games, boxscores=boxscores)
        else:
            season = validate_seasons([args.season or get_current_season()])[0]
            summarize([], confidence=confidence)
            records = []
            for name, pid in players.items():
                games = load(pid, season)
                if not games:
                    raise ValueError(f"No game data for {name}, {season}")
                records.extend(evaluate_games(pid, name, games, season, args.line,
                    args.min_history, team_games, boxscores))
            if not records:
                raise ValueError("No eligible games")
            report = {"single_season": season, "holdout_opened": False,
                      "folds": [{"season": season, "role": "exploratory",
                          "metrics": {m: summarize(records, m, confidence) for m in MODELS},
                          "records": records}]}
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
        for fold in report["folds"]:
            print(f"{fold['season']} ({fold['role']})")
            print("  Model                Games    MAE    RMSE   Brier")
            for name, m in fold["metrics"].items():
                print(f"  {name:<20} {m['games']:>5} {m['mae']:>6.3f} {m['rmse']:>7.3f} {m['brier']:>7.4f}")
        if args.seasons and not args.include_holdout:
            print(f"Holdout {report['holdout_season']} excluded; open only after freezing choices.")
        print("Lower errors/Brier are better. Calibration and game details are in --output JSON.")
        print("Missing dated opponent/PP inputs are neutral, never replaced with current data.")
    except (ValueError, KeyError, OSError, TypeError) as e:
        parser.exit(1, f"Evaluation failed: {e}\n")


if __name__ == "__main__":
    main()
