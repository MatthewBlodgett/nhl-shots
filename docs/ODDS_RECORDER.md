# NHL odds recorder and paper research

## Operation

The NHL Odds Recorder workflow checks collection windows twice per hour at
13 and 43 minutes past the hour (UTC). GitHub schedules may run late or miss
a run. This is pregame sampling, not continuous market monitoring.

The first five upcoming games available on each America/Chicago calendar day
are fixed in the ledger. Additional games never rotate in after those begin.
The collector uses only player_shots_on_goal from US-region bookmakers:

| Window | Time remaining before puck drop |
| --- | --- |
| early | More than 4 hours, at most 12 hours |
| middle | More than 1 hour, at most 4 hours |
| late | More than 0 hours, at most 1 hour |

At most one paid request is attempted for each game/window. Each request
collects all returned players and books, including quotes with no apparent
edge. Three snapshots for five games is at most 15 paid calls per day.
Actual calls can be fewer when windows are missed or props are unavailable.
The late snapshot is not guaranteed to be a true closing price.

The provider's quota headers are authoritative for its billing cycle. Paid
calls stop at 450 used credits or 50 remaining credits. Missing quota headers
stop collection. Event discovery costs zero credits; no historical-odds calls
are made. The API key remains in the repository Actions secret ODDS_API_KEY.
Raw URLs and API exception text are never printed. HTTP failures are reported
by status only. No credential is written to the data branch.

## Persistence

The odds-records branch holds the personal research archive separately from
the application code. It is subject to the same public visibility as this
repository; it contains public market observations and model outputs, never
credentials, real bet activity, personal balances or account identifiers.

| Path on odds-records | Purpose |
| --- | --- |
| data/README.md | Readable collection status and latest observed paper candidates |
| data/state.json | Selected daily games, request reservations, quotas and alert deduplication |
| data/snapshots/YYYY-MM-DD/EVENT-WINDOW.json.gz | Quotes, source timestamps, model results and version hashes |
| data/settlements/EVENT.json.gz | Official SOG outcomes and hypothetical returns |
| data/latest_run.json | Latest run counts and safe diagnostics |

Snapshots are saved before NHL enrichment. Failures in roster or model data
do not discard purchased quotes. The workflow commits the request ledger and
data even if the collector step fails. Runs are serialized across branches.

A slot is reserved before the request, and unknown failures are not retried
automatically, because the server may already have charged a credit. A runner
or persistence failure can still lose a local reservation before Git push;
the next provider usage check prevents unlimited spending, but cannot make
the API call and Git commit atomic. Check failed Actions runs rather than
blindly rerunning them. No workflow is triggered by data-branch commits.

Records are stored for this user's research, not provided as a competing raw
data feed. The provider explicitly permits storing data indefinitely:
https://the-odds-api.com/terms-and-conditions.html

## Predictions and paper candidates

Sportsbook games must match one regular-season NHL game by teams and start
time within 15 minutes. Players must match exactly one normalized roster name.
Accents and punctuation are normalized; fuzzy guesses are not used. Unmatched
or ambiguous players are recorded with a blocked model status.

The current model requires at least ten completed appearances in the current
season before the target date. Early-season odds are still archived, but no
paper candidates are produced for shorter histories. Prior-season blending
is a future accuracy change; it is not silently substituted here.

Live opponent season-to-date summaries are captured as available at the
snapshot. PP context is not available from the inspected current boxscore
schema and remains neutral. Missing inputs are exposed in the prediction.
No injuries, expected deployment or verified starting line information is
currently integrated. Candidates remain unvalidated research observations.

Half-point lines only can qualify. For decimal odds d and model probability p,
the estimated return is p*d-1. Break-even probability is 1/d. A proportional
margin-removed market estimate is available when both sides at the identical
book/player/line are present; it is a benchmark, not the wager's break-even.

Paper candidates require estimated return >=5%, a bookmaker update no more
than ten minutes old (and no more than one minute in the future), a unique
player match, and enough history. These are operating thresholds, not tuned
profitability claims. Alert deduplication uses event/book/player/line/side,
price and model version. Changed prices can generate another observation.

The collector places no bets, sends no external messages, recommends no
stakes, and never treats the model probability as a demonstrated market edge.
The data report contains archived candidates; prices may no longer exist.

## Outcomes

After a game completes, subsequent runs check recent recorded games through
the NHL boxscore endpoint, without using odds credits. Full-game official SOG
includes overtime. Missing players/outcomes remain unresolved rather than
being counted as automatic losses or wins. Participation, void and regulation
rules must be checked for each sportsbook before interpreting real returns.

Settlements include hypothetical one-unit returns and Brier errors where a
pre-game probability exists. Repeated quotes across books and windows are
not independent games: group by player/game and a fixed observation window
for a performance study. Current settlement files are created once and are
not automatically revised for later NHL stat corrections. Games more than
14 days old require a manual recovery after a prolonged outage.

## Running and pausing

GitHub Actions > NHL Odds Recorder > Run workflow supports a bounded manual
run (default one paid request; maximum five). The first push on the feature
branch also performs a one-request live check. Recurring schedule runs require
the workflow on the repository's default branch, master.

To pause, disable NHL Odds Recorder in the Actions page. The archive remains.
The existing Verify Odds API check is separate and is not a recurring collector.

Locally, provide ODDS_API_KEY through the environment and run:

```bash
python odds_recorder.py --data-dir data --max-requests 1
python -m pytest tests/ -q
```

The GitHub workflow stores all outputs in odds-records. Local data is ignored
by Git to reduce accidental commits; use the dedicated data checkout.
