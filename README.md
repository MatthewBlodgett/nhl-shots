# NHL Shots on Goal Predictor 🏒

Python CLI for estimating player shots on goal and over/under probabilities.
The model is a research prototype; predictive improvement and betting value have
not yet been established by a clean historical study.

## Setup and predictions

```bash
pip install -r requirements.txt
python shots.py mcdavid CGY 3.5 away
python shots.py matthews MIN 4.5 home b2b
python shots.py mcdavid CGY 3.5 away --date 2025-01-15 --season 20242025
```

Use a quick name from the CLI's name list, or any NHL player ID.
Home is the default venue. The target date defaults to today, not tomorrow.
Dates follow the machine's local calendar; supply --date when necessary.
The season is resolved from NHL start-date metadata unless --season is supplied.
This handles the September 29 start of 2026–27 (season ID 20262027), rather
than assuming every season starts in October. Verified 2025/2026 boundaries
are used with a warning if season metadata is unavailable. Supplied offline
histories avoid network lookups and should include an explicit season.

Predictions blend season, last-ten and last-five averages (default 50/30/20),
then apply location, opponent, rest, power-play and ice-time factors.
Fewer than ten completed games triggers an early-season sample warning;
the engine does not silently replace the current season with last year's log.
A Poisson distribution converts the expected shots into probabilities.
These factors are heuristics, not proven effects.

Explicit dates and supplied histories use isolated prediction context:
current player metadata, season-end opponent statistics and live boxscores
are not silently imported. Missing dated opponent/PP data yields a neutral
factor. The Python API accepts supplied dated context; see the evaluation guide.

## Honest historical evaluation

```bash
# Single season; 3 means THREE OR MORE shots, equivalent to over 2.5.
python backtest.py mcdavid 3 55 --season 20242025 --output results.json

# Development on earliest season; validation on middle season.
# Latest season remains sealed and its player log is not requested.
python backtest.py mcdavid 3 55 \
  --seasons 20232024 20242025 20252026 \
  --tune-weights --output development-validation.json

# Open the final holdout only after choices are frozen.
python backtest.py mcdavid 3 55 \
  --seasons 20232024 20242025 20252026 \
  --tune-weights --include-holdout --output final-evaluation.json
```

The full model and season-average/recent-ten-average baselines are evaluated
on identical games. Reports include MAE, RMSE, Brier score, calibration bins,
data coverage and per-game predictions. Lower error and Brier are better.
Optional weight tuning selects only on the earliest season's Brier score.
The first ten player appearances of every season are warm-up by default.

Historical player data can be fetched from the NHL API or supplied through
--dataset. Opponent and power-play context must be supplied in that dataset;
otherwise those adjustments remain neutral and report coverage is zero.
Any reported ROI assumes hypothetical fixed -110 odds and is not evidence
of profitability at real market prices.

Read [docs/EVALUATION_GUIDE.md](docs/EVALUATION_GUIDE.md) for dataset format,
the evaluation protocol, and limitations. Earlier Phase 1/2 documents are
archived research notes; their accuracy and betting-edge claims are unverified.

## Tests

```bash
python -m pytest tests/ -q
```

Tests run offline and check future-data isolation, threshold scoring, rest
overrides, holdout exclusion, development-only tuning, calibration and CLI export.

## Structure

| Path | Role |
| --- | --- |
| shots.py | NHL API access and prediction engine |
| backtest.py | Walk-forward evaluation, benchmarks and development-only tuning |
| tests/ | Offline regression tests |
| docs/EVALUATION_GUIDE.md | Protocol, dataset schema and verification |
| home_away_research.py | Original exploratory home/away research |
| docs/PHASE*.md | Archived development notes |

## Odds recording and paper research

The [NHL odds recorder](docs/ODDS_RECORDER.md) saves current sportsbook SOG
prices using the repository secret ODDS_API_KEY. It collects up to five games
per Chicago day, once in each of three pregame windows, and stops at 450 used
credits or 50 remaining. Snapshots and hypothetical results live on the
separate odds-records branch; its data/README.md is the readable status page.

The scheduled GitHub Action checks windows twice per hour. It creates only
unvalidated paper candidates, blocks stale quotes and short player histories,
and never places bets. Missing odds history is accumulated prospectively.

Python 3.10+; requests and pytest. No website, injury feed, or automatic bet
placement is included.

## Current research build

The [broad fixed-cohort study](research/README.md) contains 1,449 development
and 1,343 validation player games with complete dated team context. The
development-selected prior-season blend and negative-binomial distribution
now drive the paper recorder. Its validation Brier is 0.146610 versus 0.148067
for the season baseline; the paired interval includes zero, so superiority
and a market edge are not established. The final holdout remains unopened.

Eligible paper forecasts require one current appearance and twenty prior-season
appearances. Early team changes remain blocked until ten current appearances.
The legacy shots.py CLI remains unchanged for comparison. Model inputs and
version hashes are captured; prospective results are separated by version.

See [agent reads](docs/AGENT_INTERFACE.md) for the credential-free JSON CLI and
[build status](docs/BUILD_STATUS.md) for implemented work and remaining tasks.
