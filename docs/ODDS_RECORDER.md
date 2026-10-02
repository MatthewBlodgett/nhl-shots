# NHL odds recorder and paper research

## Operation

The NHL Odds Recorder workflow checks collection windows twice per hour at
13 and 43 minutes past the hour (UTC). GitHub schedules may run late or miss
a run. This is pregame sampling, not continuous market monitoring.

Existing first-five selections remain fixed. Newly selected days use hash_five_v2:
five deterministic day/event hash picks, independent of prices/model. Additional
games never rotate in after selection. One selected early window is explicitly
omitted on a five-game day; middle and late windows remain planned.
The collector uses only player_shots_on_goal from US-region bookmakers:

| Window | Time remaining before puck drop |
| --- | --- |
| early | More than 4 hours, at most 12 hours |
| middle | More than 1 hour, at most 4 hours |
| late | More than 0 hours, at most 1 hour |

At most one paid request is attempted for each game/window. Each request
collects all returned players and books, including quotes with no apparent
edge. Sampling v2 plans at most 14 paid calls per day (434 over 31 days).
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
automatically, because the server may already have charged a credit. The Actions collector now requires an acknowledged Git push of each reservation
before making the paid call. A failed push stops the call; a killed runner can
lose its response but its acknowledged slot cannot be retried automatically.
A 14-day recovery artifact precedes the final archive push. Check failed Actions runs rather than
blindly rerunning them. No workflow is triggered by data-branch commits.

Records are stored for this user's research, not provided as a competing raw
data feed. The provider explicitly permits storing data indefinitely:
https://the-odds-api.com/terms-and-conditions.html

## Predictions and paper candidates

Sportsbook games must match one regular-season NHL game by teams and start
time within 15 minutes. Players must match exactly one normalized roster name.
Accents and punctuation are normalized; fuzzy guesses are not used. Unmatched
or ambiguous players are recorded with a blocked model status.

The paper collector uses the development-selected blend20_nb20 model,
documented in research/README.md. The current-season shot sum is shrunk toward
the last thirty prior-season appearances with weight equivalent to twenty
games. Probabilities use negative binomial NB2 dispersion twenty, rather than
the legacy CLI's Poisson engine. The CLI remains available for comparison.

At least one completed current-season appearance and twenty prior-season
appearances are required. Zero-current-history players and rookies without
enough prior history remain blocked. A change from the last prior-season team
blocks candidates until ten current-season appearances; this is a conservative
operating guard, not a fitted effect. Inputs are strictly before the game date,
recorded with hashes and feature coverage. Prior logs have a seven-day durable
cache; current logs refresh on subsequent collections. HTTP outages are treated
as invalid NHL data rather than invented zero-shot games.

The study reconstructs dated opponent context for the legacy comparison and
feature diagnostics. The selected paper model uses count history alone.
Injury, opponent and PP adjustments are not applied to it. PP context was
unavailable from the inspected boxscore schema. Missing inputs are exposed.
Supplemental projected NHL editorial injuries, scratch lists and line combinations
are archived with source hashes and publication/observation times. They do not
change the frozen probabilities. PP roles and projected TOI remain missing unless
an explicit timestamped official observation is supplied; recent TOI is a proxy. Candidates remain unvalidated research observations.

Only the studied half-point lines 1.5, 2.5 and 3.5 can qualify. Other lines are
archived with outside_studied_lines status. For decimal odds d and model probability p,
the estimated return is p*d-1. Break-even probability is 1/d. A proportional
margin-removed market estimate is available when both sides at the identical
book/player/line are present; it is a benchmark, not the wager's break-even.

Paper candidates require estimated return >=5%, a bookmaker update no more
than ten minutes old (and no more than one minute in the future), a unique
player match, and the history and team-change gates. These are operating thresholds, not tuned
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
for a performance study. Settlements are rechecked once daily for seven days,
with prior actuals retained in a revision ledger when counts change. Unresolved
participation is rechecked through the lookback window. Games more than fourteen
days old require manual recovery after a prolonged outage; settle_recent supports
an explicit lookback up to 365 days. Sportsbook void rules remain unverified.

## Prospective reports and agent reads

data/PERFORMANCE.md and data/performance.json apply a fixed middle-window policy:
at most one paper decision per player/game, selecting highest modeled return
with stable tie breaks. Calibration uses one fixed quote per player/game.
Results are split by model version. Missing results remain unresolved. Hypothetical
ROI intervals use game clusters and are withheld below twenty settled games;
price movement uses the last saved late quote, not a guaranteed closing price.

data/health.json tracks recent runs, failures, credit pause, blockers, missing
elapsed windows on observed games and settlement backlog. A failed runner cannot
update it; agent status marks archives older than two hours as stale. A discovery census now includes selected games with no snapshots and unsampled
games; provider-undiscovered games remain unknown. No external notifications
are sent.

agent_tool.py provides read-only status, candidates, player and performance JSON.
It makes no network requests or bets and accepts no credentials. Candidates are
archived observations and marked expired against the query time. See
docs/AGENT_INTERFACE.md. A tested loopback read-only HTTP API and mobile dashboard are implemented in
review_server.py. No internet service is deployed. See docs/RESEARCH_OPERATIONS.md.

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
