#!/usr/bin/env python3
"""Save pregame NHL shot prices and unvalidated paper candidates. Never bet."""
import argparse
import gzip
import hashlib
import json
import math
import os
import re
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import shots

SPORT = "icehockey_nhl"
MARKET = "player_shots_on_goal"
DAILY_GAMES = 5
MONTHLY_CREDIT_CAP = 450
MIN_PAPER_EV = 0.05
MAX_QUOTE_AGE = 600
LOCAL_ZONE = ZoneInfo("America/Chicago")


class SafeAPIError(Exception):
    """Contains a safe diagnostic only; never a URL, key or response body."""


def parse_time(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    return result.astimezone(timezone.utc)


def name_key(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", value.lower())


def atomic_json(path, value, compressed=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    if compressed:
        payload = gzip.compress(payload, mtime=0)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        f.write(payload)
    os.replace(temp, path)


def quota(headers):
    value = headers.get("x-requests-used")
    remaining = headers.get("x-requests-remaining")
    if value is None or remaining is None or not str(value).isdigit() or not str(remaining).isdigit():
        raise SafeAPIError("Quota headers are missing; paid requests stopped")
    return {"used": int(value), "remaining": int(remaining)}


class OddsClient:
    def __init__(self, key):
        if not key:
            raise SafeAPIError("ODDS_API_KEY is missing")
        self.key = key.strip()

    def get(self, path, **params):
        url = "https://api.the-odds-api.com/v4/" + path + "?" + urllib.parse.urlencode(
            {"apiKey": self.key, **params})
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                return json.load(response), quota(response.headers)
        except urllib.error.HTTPError as e:
            raise SafeAPIError(f"Odds API returned HTTP {e.code}") from None
        except SafeAPIError:
            raise
        except Exception:
            raise SafeAPIError("Odds API connection or JSON parsing failed") from None

    def events(self):
        data, usage = self.get(f"sports/{SPORT}/events")  # zero-credit discovery
        if not isinstance(data, list):
            raise SafeAPIError("Unexpected event-list schema")
        return data, usage

    def odds(self, event_id):
        if not re.fullmatch(r"[a-fA-F0-9]{32}", event_id):
            raise SafeAPIError("Invalid event ID")
        data, usage = self.get(f"sports/{SPORT}/events/{event_id}/odds",
                               markets=MARKET, regions="us", oddsFormat="decimal")
        if not isinstance(data, dict) or data.get("id") != event_id:
            raise SafeAPIError("Unexpected event-odds schema")
        return data, usage


def stage_for(start, now):
    hours = (start - now).total_seconds() / 3600
    if 4 < hours <= 12:
        return "early"
    if 1 < hours <= 4:
        return "middle"
    if 0 < hours <= 1:
        return "late"
    return None


def select_events(events, state, now, policy="first_five_v1"):
    """Fix the day's first five available upcoming games; never rotate in extras."""
    day = now.astimezone(LOCAL_ZONE).date().isoformat()
    valid = {}
    for event in events:
        try:
            start = parse_time(event["commence_time"])
            if (start > now and start.astimezone(LOCAL_ZONE).date().isoformat() == day
                    and re.fullmatch(r"[a-fA-F0-9]{32}", event["id"])):
                valid[event["id"]] = event
        except (KeyError, TypeError, ValueError):
            continue
    selected = state.setdefault("days", {}).get(day)
    if selected is None and valid:
        order=(lambda eid: hashlib.sha256((day+':hash_five_v2:'+eid).encode()).hexdigest()) if policy=='hash_five_v2' else (lambda eid:(valid[eid]['commence_time'],eid))
        selected = sorted(valid,key=order)[:DAILY_GAMES]
        state.setdefault('day_policies',{})[day]=policy
        if policy=='hash_five_v2' and len(selected)==5:
            state.setdefault('planned_omissions',{})[selected[-1]+':early']={'day':day,'reason':'14_call_daily_plan_preserves_middle_and_late'}
        state["days"][day] = selected
    return day, [valid[eid] for eid in selected or [] if eid in valid]


def normalize_quotes(data):
    """Keep every valid quote, even without a model or apparent edge."""
    result = []
    for book in data.get("bookmakers", []):
        for market in book.get("markets", []):
            if market.get("key") != MARKET:
                continue
            updated = market.get("last_update", book.get("last_update"))
            for outcome in market.get("outcomes", []):
                side, player = outcome.get("name"), outcome.get("description")
                price, line = outcome.get("price"), outcome.get("point")
                if (side not in ("Over", "Under") or not isinstance(player, str)
                        or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 1
                        or not isinstance(line, (int, float)) or not math.isfinite(line) or line < 0):
                    continue
                result.append({"book": book["key"], "player": player, "side": side,
                               "line": float(line), "decimal_odds": float(price),
                               "book_updated_at": updated})
    # Exact duplicates in a provider response are not separate observations.
    return list({json.dumps(q, sort_keys=True): q for q in result}.values())


def map_nhl_game(event):
    day = parse_time(event["commence_time"]).astimezone(LOCAL_ZONE).date().isoformat()
    schedule = shots.api_request(f"{shots.BASE_URL}/schedule/{day}") or {}
    home, away = shots.get_team_abbrev(event["home_team"]), shots.get_team_abbrev(event["away_team"])
    matches = []
    for week in schedule.get("gameWeek", []):
        for game in week.get("games", []):
            if (game.get("gameType") == 2 and game.get("homeTeam", {}).get("abbrev") == home
                    and game.get("awayTeam", {}).get("abbrev") == away):
                try:
                    if abs((parse_time(game["startTimeUTC"]) - parse_time(event["commence_time"])).total_seconds()) <= 900:
                        matches.append(game)
                except (KeyError, ValueError, TypeError):
                    continue
    return (matches[0], home, away) if len(matches) == 1 else (None, home, away)


def roster_names(team, season):
    data = shots.api_request(f"{shots.BASE_URL}/roster/{team}/{season}") or {}
    result = {}
    for group in ("forwards", "defensemen"):
        for p in data.get(group, []):
            first = p.get("firstName", {}).get("default", "")
            last = p.get("lastName", {}).get("default", "")
            name = f"{first} {last}".strip()
            result.setdefault(name_key(name), []).append({"id": p["id"], "team": team,
                "name": name, "info": {"firstName": {"default": first},
                "lastName": {"default": last}, "currentTeamAbbrev": team}})
    return result


def player_history(player_id, season, now, *, prior=False, data_dir=None):
    """Retain prior logs for seven days; distinguish outages from zero games."""
    cache = Path(data_dir) / 'model_inputs' / 'prior' / f'{player_id}-{season}.json.gz' if prior and data_dir else None
    data = None
    if cache and cache.exists():
        with gzip.open(cache, 'rt') as f:
            record = json.load(f)
        age = (now - parse_time(record['fetched_at'])).total_seconds()
        if 0 <= age < 7 * 86400:
            data = record['response']
    if data is None:
        data = shots.api_request(f'{shots.BASE_URL}/player/{player_id}/game-log/{season}/2')
        if data is None:
            raise ValueError('Player history unavailable')
        if data.get('seasonId') is not None and str(data['seasonId']) != season:
            raise ValueError('Wrong player season')
        if data.get('gameTypeId') is not None and data['gameTypeId'] != 2:
            raise ValueError('Wrong player game type')
        if cache:
            atomic_json(cache, {'fetched_at': now.isoformat(), 'response': data}, compressed=True)
    return shots.prepare_game_log(data.get('gameLog', []))


def predict_players(event, quotes, now, data_dir=None):
    """Use exact normalized roster matches only. No fuzzy player guessing."""
    game, home, away = map_nhl_game(event)
    if game is None:
        return {q["player"]: {"status": "nhl_game_unmatched"} for q in quotes}
    season = str(game["season"])
    article = None
    context_error = None
    from official_context import load_article, player_observations
    try:
        article = load_article(data_dir, season, now)
    except Exception:
        context_error = 'official_editorial_unavailable'
    names = {}
    for team in (home, away):
        for key, players in roster_names(team, season).items():
            names.setdefault(key, []).extend(players)
    day = parse_time(event["commence_time"]).astimezone(LOCAL_ZONE).date().isoformat()
    models = {}
    for name in sorted({q["player"] for q in quotes}):
        players = names.get(name_key(name), [])
        if len(players) != 1:
            models[name] = {"status": "player_unmatched_or_ambiguous"}
            continue
        player = players[0]
        try:
            history = shots.prepare_game_log(player_history(player['id'], season, now), day)
            base = {"player_id": player["id"], "nhl_game_id": game["id"], "season": season,
                    "history_games": len(history), "input_as_of": now.isoformat()}
            from paper_model import forecast
            prior_season = f'{int(season[:4])-1}{season[:4]}'
            prior = player_history(player['id'], prior_season, now, prior=True, data_dir=data_dir)
            models[name] = {**base, **forecast(history, prior, day, player['team'])}
            from context_inputs import context_for
            observations=player_observations(article,event,player,now)
            if observations and data_dir:
                context_path=Path(data_dir)/'context'/'observations.json'
                previous=json.loads(context_path.read_text()) if context_path.exists() else []
                unique={hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest():r for r in previous+observations}
                atomic_json(context_path,list(unique.values()))
            models[name]['supplemental_context'] = context_for(data_dir, player['id'], event['id'], now, history)
            models[name]['supplemental_context']['collection_error'] = context_error
        except (ValueError, KeyError, TypeError):
            models[name] = {"status": "invalid_nhl_data", "player_id": player["id"]}
    return models


def enrich_quotes(quotes, models, now, model_version):
    paper_lines = json.loads(Path(__file__).with_name('paper_model_config.json').read_text())['paper_lines']
    prices = {(q["book"], q["player"], q["line"], q["side"]): q["decimal_odds"] for q in quotes}
    for q in quotes:
        model = models.get(q["player"], {"status": "no_model"})
        if "player_id" in model:
            q["player_id"] = model["player_id"]
        q.update({"model_status": model["status"], "model_version": model_version,
                  "break_even_probability": 1 / q["decimal_odds"], "paper_candidate": False})
        other = prices.get((q["book"], q["player"], q["line"], "Under" if q["side"] == "Over" else "Over"))
        if other:
            q["market_no_vig_probability"] = (1 / q["decimal_odds"]) / (1 / q["decimal_odds"] + 1 / other)
        if model["status"] != "ok":
            q["blocked_reason"] = model["status"]
            continue
        q["player_id"] = model["player_id"]
        if q["line"] % 1 != .5:
            q["blocked_reason"] = "only_half_point_lines_supported"
            continue
        if q['line'] not in paper_lines:
            q['blocked_reason'] = 'outside_studied_lines'
            continue
        from paper_model import probability
        p = probability(model['prediction'], q['line'])
        p = p if q["side"] == "Over" else 1 - p
        q.update({"model_probability": p, "model_fair_decimal_odds": 1 / p if p else None,
                  "expected_return": p * q["decimal_odds"] - 1,
                  "probability_edge": p - q["break_even_probability"]})
        try:
            age = (now - parse_time(q["book_updated_at"])).total_seconds()
            q["quote_age_seconds"] = age
            if age < -60 or age > MAX_QUOTE_AGE:
                q["blocked_reason"] = "stale_or_future_quote"
                continue
        except (ValueError, TypeError, AttributeError):
            q["blocked_reason"] = "missing_quote_timestamp"
            continue
        q["paper_candidate"] = q["expected_return"] >= MIN_PAPER_EV
        q["model_warning"] = "Unvalidated probability model; paper research only"
    return quotes


def collect(data_dir, client, *, now=None, max_requests=5, predictor=predict_players, reserve_callback=None, sampling_policy="first_five_v1"):
    realtime = now is None
    now = now or datetime.now(timezone.utc)
    if not 1 <= max_requests <= DAILY_GAMES:
        raise ValueError("max_requests must be between 1 and 5")
    root = Path(data_dir)
    state_path = root / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"schema_version": 1, "days": {}, "attempts": {}}
    if state.get("schema_version") != 1:
        raise ValueError("Unsupported state schema; collection stopped")
    events, usage = client.events()
    state["last_quota"] = usage
    day, selected = select_events(events, state, now, sampling_policy)
    # Discovery census includes unsampled games and selected games with no props.
    census = state.setdefault("event_census", {})
    for event in events:
        try:
            start = parse_time(event["commence_time"])
            if start.astimezone(LOCAL_ZONE).date().isoformat() != day:
                continue
            census[event["id"]] = {"event": event, "last_seen_at": now.isoformat(),
                "first_seen_at": census.get(event["id"], {}).get("first_seen_at", now.isoformat()),
                "selected": event["id"] in state.get("days", {}).get(day, []),
                "sampling_policy": state.get("day_policies",{}).get(day,"first_five_v1")}
        except (KeyError, TypeError, ValueError):
            continue
    atomic_json(state_path, state)
    from paper_model import version as model_version
    version = model_version()
    summary = {"recorded_at": now.isoformat(), "day": day, "requests": 0,
               "snapshots": 0, "quotes": 0, "new_paper_candidates": 0, "errors": [], "quota": usage}
    for event in selected:
        if realtime:
            now = datetime.now(timezone.utc)
        stage = stage_for(parse_time(event["commence_time"]), now)
        slot = event["id"] + ":" + str(stage)
        if (stage is None or slot in state.get("planned_omissions",{}) or slot in state["attempts"] or summary["requests"] >= max_requests
                or usage["used"] >= MONTHLY_CREDIT_CAP or usage["remaining"] <= 50):
            continue
        # Reserve the slot before the request: never blindly repeat a possibly billed call.
        state["attempts"][slot] = {"status": "reserved", "at": now.isoformat()}
        atomic_json(state_path, state)
        if reserve_callback is not None:
            # Paid call is forbidden unless the reservation is durably acknowledged.
            reserve_callback(root)
        summary["requests"] += 1
        try:
            response, usage = client.odds(event["id"])
            collected_at = datetime.now(timezone.utc) if realtime else now
            state["last_quota"] = usage
            quotes = normalize_quotes(response)
            for q in quotes:
                q["event_id"] = event["id"]
                q["game_start"] = event["commence_time"]
            # First persist quotes: NHL enrichment failures must not lose purchased data.
            snapshot = {"schema_version": 1, "event": event, "stage": stage,
                        "collected_at": collected_at.isoformat(), "quota": usage,
                        "model_version": version, "quotes": quotes, "models": {}}
            snapshot["collector_version"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            snapshot["source_revision"] = os.environ.get("GITHUB_SHA")
            snapshot["paper_protocol"] = {"model_config": json.loads(Path(__file__).with_name('paper_model_config.json').read_text()), "min_ev": MIN_PAPER_EV,
                                          "max_quote_age_seconds": MAX_QUOTE_AGE}
            path = root / "snapshots" / day / f"{event['id']}-{stage}.json.gz"
            atomic_json(path, snapshot, compressed=True)
            summary["snapshots"] += 1
            summary["quotes"] += len(quotes)
            try:
                if parse_time(event["commence_time"]) <= collected_at:
                    snapshot["models"] = {q["player"]: {"status": "game_already_started"} for q in quotes}
                else:
                    snapshot["models"] = (predictor(event, quotes, collected_at, data_dir=root)
                        if predictor is predict_players else predictor(event, quotes, collected_at))
                snapshot["quotes"] = enrich_quotes(quotes, snapshot["models"], collected_at, version)
                atomic_json(path, snapshot, compressed=True)
            except Exception:
                summary["errors"].append("NHL enrichment failed; purchased quotes retained")
            alerts = state.setdefault("paper_alert_keys", [])
            seen = set(alerts)
            for q in snapshot["quotes"]:
                if not q.get("paper_candidate"):
                    continue
                key = json.dumps([event["id"], q["book"], q["player_id"], q["line"],
                                  q["side"], q["decimal_odds"], version], separators=(",", ":"))
                if key not in seen:
                    seen.add(key)
                    alerts.append(key)
                    summary["new_paper_candidates"] += 1
            state["attempts"][slot]["status"] = "saved"
        except SafeAPIError as error:
            summary["errors"].append(str(error))
            state["attempts"][slot]["status"] = "request_failed_no_automatic_retry"
            # An unknown charge or auth failure must stop paid requests for this run.
            atomic_json(state_path, state)
            break
        except Exception:
            summary["errors"].append("Snapshot parsing or save failed; request not repeated")
            state["attempts"][slot]["status"] = "failed_no_automatic_retry"
            atomic_json(state_path, state)
            break
        atomic_json(state_path, state)
    summary["quota"] = usage
    atomic_json(root / "latest_run.json", summary)
    return summary


def settle_recent(data_dir, now=None, lookback_days=14):
    """Attach official outcomes to saved quotes; never fetch sportsbook results."""
    root = Path(data_dir)
    now = now or datetime.now(timezone.utc)
    if not 1 <= lookback_days <= 365:
        raise ValueError('Settlement lookback must be 1 to 365 days')
    groups = {}
    for path in sorted((root / "snapshots").glob("*/*.json.gz")):
        day = datetime.fromisoformat(path.parent.name).replace(tzinfo=LOCAL_ZONE)
        if (now - day.astimezone(timezone.utc)).days > lookback_days:
            continue
        with gzip.open(path, "rt") as f:
            snapshot = json.load(f)
        if parse_time(snapshot["event"]["commence_time"]) < now:
            groups.setdefault(snapshot["event"]["id"], []).append(snapshot)
    completed = 0
    for event_id, snapshots in groups.items():
        target = root / "settlements" / f"{event_id}.json.gz"
        previous = None
        if target.exists():
            with gzip.open(target, 'rt') as f:
                previous = json.load(f)
            checked = previous.get('checked_at', previous['settled_at'])
            if parse_time(checked).date() == now.date():
                continue
            age = (now - parse_time(snapshots[0]['event']['commence_time'])).days
            unresolved = any(q.get('actual_shots') is None for q in previous['quotes'])
            if age > 7 and not unresolved:
                continue
        ids = {m["nhl_game_id"] for s in snapshots for m in s["models"].values() if "nhl_game_id" in m}
        if len(ids) != 1:
            continue
        game_id = ids.pop()
        boxscore = shots.get_boxscore(game_id)
        if boxscore.get("gameState") not in ("OFF", "FINAL"):
            continue
        actuals = {}
        for team in ("homeTeam", "awayTeam"):
            for position in ("forwards", "defense"):
                for p in boxscore.get("playerByGameStats", {}).get(team, {}).get(position, []):
                    if p.get('toi') and shots.parse_toi(p['toi']) == 0:
                        continue
                    if isinstance(p.get("sog"), int):
                        actuals[p["playerId"]] = p["sog"]
        rows = []
        for snapshot in snapshots:
            for q in snapshot["quotes"]:
                actual = actuals.get(q.get("player_id"))
                row = {**q, "stage": snapshot["stage"], "collected_at": snapshot["collected_at"],
                       "actual_shots": actual, "result": "unresolved_player_or_participation"}
                if actual is not None:
                    row["result"] = "push" if actual == q["line"] else "win" if (
                        (actual > q["line"]) == (q["side"] == "Over")) else "loss"
                    row["hypothetical_unit_return"] = (0 if row["result"] == "push" else
                        q["decimal_odds"] - 1 if row["result"] == "win" else -1)
                    if "model_probability" in q and row["result"] != "push":
                        row["brier"] = (q["model_probability"] - int(row["result"] == "win")) ** 2
                # Official statistical outcomes and bookmaker settlements are distinct.
                from settlement_rules import assess
                row["sportsbook_settlement"] = assess(q, actual, now)
                rows.append(row)
        revisions = previous.get('revisions', []) if previous else []
        old_actuals = {str(q.get('player_id')): q.get('actual_shots') for q in previous['quotes']} if previous else {}
        new_actuals = {str(q.get('player_id')): q.get('actual_shots') for q in rows}
        changed = bool(previous and old_actuals != new_actuals)
        if changed:
            revisions.append({'replaced_at': now.isoformat(), 'previous_actuals': old_actuals})
        atomic_json(target, {"event_id": event_id, 'nhl_game_id': game_id,
            "settled_at": previous['settled_at'] if previous else now.isoformat(),
            'checked_at': now.isoformat(), 'revisions': revisions, "quotes": rows,
            "warning": "Official full-game SOG including overtime. Hypothetical returns; sportsbook participation and settlement rules require verification."}, compressed=True)
        completed += int(previous is None or changed)
    return completed


def write_report(data_dir, summary):
    """A readable status page beside the compressed research records."""
    root = Path(data_dir)
    quotes, snapshots, observations = [], 0, []
    for path in sorted((root / "snapshots" / summary["day"]).glob("*.json.gz")):
        with gzip.open(path, "rt") as f:
            data = json.load(f)
        snapshots += 1
        observations.append(data)
    for data in sorted(observations, key=lambda item: parse_time(item["collected_at"])):
        quotes.extend(data["quotes"])
    usable = sum(q.get("model_status") == "ok" for q in quotes)
    small = sum(q.get("model_status") in ('insufficient_current_season_history', 'insufficient_prior_season_history', 'team_change_review_required') for q in quotes)
    lines = ["# NHL odds research recorder", "", f"Updated: {summary['recorded_at']}", "",
        f"Today's archive: **{snapshots} snapshots / {len(quotes)} quotes**.", "",
        f"Quotes with usable model history: {usable}. Blocked by history or team-change rules: {small}.", "",
        f"API billing-cycle usage: {summary['quota']['used']} credits; {summary['quota']['remaining']} remaining.", "",
        "Five selected games per Chicago calendar day; three collection windows; 450-credit cap.", "",
        "**Paper research only. The model has not demonstrated a betting edge. No bets are placed.**", "",
        "Snapshots are in snapshots/YYYY-MM-DD/*.json.gz; official outcomes are in settlements/.", "",
        "[Prospective paper performance](PERFORMANCE.md) · [Operational health](health.json)", "",
        "## Latest paper candidates", ""]
    # Keep the most recently observed quote for each book/player/line/side.
    latest = {(q.get("event_id"), q["book"], q["player"], q["line"], q["side"]): q for q in quotes}
    candidates = sorted((q for q in latest.values() if q.get("paper_candidate")),
                        key=lambda q: q["expected_return"], reverse=True)[:20]
    if not candidates:
        lines.append("No qualifying paper candidates in today's recorded snapshots.")
    else:
        lines += ["| Player | Book | Side / line | Decimal price | Model probability | Estimated return |",
                  "| --- | --- | --- | ---: | ---: | ---: |"]
        for q in candidates:
            player, book = q["player"].replace("|", " ").replace("\n", " "), q["book"].replace("|", " ")
            lines.append(f"| {player} | {book} | {q['side']} {q['line']} | {q['decimal_odds']:.3f} | "
                         f"{q['model_probability']:.1%} | {q['expected_return']:.1%} |")
        lines += ["", "These are archived observations, not a statement that the price remains available."]
    if summary["errors"]:
        lines += ["", "## Run errors", "", *summary["errors"]]
    (root / "README.md").write_text("\n".join(lines) + "\n")


def persist_reservation(root):
    """Push only the ledger to odds-records before any possibly billed call."""
    import subprocess
    repo=Path(root).resolve().parent
    def run(*args):
        result=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
        if result.returncode: raise SafeAPIError('Reservation persistence failed; no paid call attempted')
        return result.stdout.strip()
    # Do not allow this option to write into the application branch.
    branch=run('rev-parse','--abbrev-ref','HEAD')
    if branch!='odds-records': raise SafeAPIError('Durable reservations require odds-records checkout')
    run('config','user.name','NHL Odds Recorder')
    run('config','user.email','nhl-odds-recorder@users.noreply.github.com')
    run('add','-f','data/state.json')
    run('commit','-m','Reserve odds request before collection')
    run('push','origin','HEAD:odds-records')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--max-requests", type=int, default=5)
    parser.add_argument("--durable-reservations", action="store_true")
    parser.add_argument("--sampling-policy",choices=["first_five_v1","hash_five_v2"],default="first_five_v1")
    args = parser.parse_args()
    try:
        summary = collect(args.data_dir, OddsClient(os.environ.get("ODDS_API_KEY")), max_requests=args.max_requests,
            reserve_callback=persist_reservation if args.durable_reservations else None, sampling_policy=args.sampling_policy)
        try:
            settled = settle_recent(args.data_dir)
        except Exception:
            settled = 0
            summary["errors"].append("Outcome update failed; saved odds retained")
        write_report(args.data_dir, summary)
        from performance_report import write_performance
        from health_report import record_health
        write_performance(args.data_dir)
        atomic_json(args.data_dir / 'latest_run.json', summary)
        record_health(args.data_dir, summary, success=not summary['errors'])
        text = (f"Saved {summary['snapshots']} snapshots / {summary['quotes']} quotes; "
                f"{summary['new_paper_candidates']} new paper candidates. "
                f"Credits used this billing cycle: {summary['quota']['used']}; "
                f"remaining: {summary['quota']['remaining']}.\n"
                f"New completed-game outcome files: {settled}.\n"
                "Paper research only; no orders or bets placed.\n")
        if summary["errors"]:
            text += "\n".join(summary["errors"]) + "\n"
        print(text)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
                f.write(text)
        return 1 if summary["errors"] else 0
    except SafeAPIError as error:
        print(str(error))
        from health_report import record_health
        record_health(args.data_dir, {'errors': [str(error)]}, success=False)
        return 1
    except Exception:
        print("Collector failed; diagnostic details withheld to protect credentials")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
