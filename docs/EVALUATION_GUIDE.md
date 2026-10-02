# Accuracy work: priorities 1–5

## Status

Implemented: strict pre-game histories, consistent N+ thresholds, target-date
rest handling, zero-mean probability correction, benchmark metrics, optional
development-only weight selection and chronological multi-season evaluation.

Verified on 2026-10-02 with offline regression tests. NHL player-log and team
statistics requests returned HTTP 403 in the implementation environment.
No genuine historical accuracy, calibration or profitability result is claimed.
Synthetic fixtures validate software behavior, not predictive skill.

## Temporal boundaries

Every prediction uses player games whose gameDate is strictly less than the
target date. Input order does not matter, and the caller's rows are not mutated.
Same-day games are excluded conservatively. Season averages, recent form,
home/away splits, rest comparisons and ice-time trends all use that history.

Historical prediction does not fetch current player metadata or current team
averages. Dated opponent context is rebuilt from supplied completed team games
in the requested season before the target date. Boxscores are looked up only
for the previous player games. No target or future boxscore contributes.
Missing opponent or power-play data means factor 1.0, with coverage exposed
in JSON. The evaluator never substitutes a season-end team average.

Player logs are regular-season logs from the existing NHL /game-log/SEASON/2
endpoint. Offline inputs must also contain only completed regular-season games.
Missing outcomes, invalid venues and duplicate games fail evaluation instead
of being silently counted as zero shots. Whole missing player/season datasets
also stop the run. Data collection completeness cannot be inferred from a
user-supplied JSON; verify it before interpreting results.

## Lines and rest

The backtest accepts positive integer N+ thresholds: 3 means actual shots >= 3,
with probability computed at over 2.5. Live prediction accepts ordinary lines:
over 3.5 means >= 4. Integer lines have a push probability; an equal outcome is
neither an over win nor an under win.

Today is the default target date, using the machine's local calendar. --date
removes ambiguity. --season overrides the October season-ID heuristic.
Explicit b2b forces zero rest days. Explicit rest forces at least one rest
day, preserving a longer inferred rest interval. Rest is based on player
appearances: missed appearances can make it differ from team schedule rest.

## Benchmarks and measurements

Three forecasts are compared on exactly the same eligible games:

| Model | Expected shots |
| --- | --- |
| full | Weighted averages multiplied by available adjustment factors |
| season_average | Pre-game season mean, with no adjustments |
| recent_average | Mean of the previous ten appearances, with no adjustments |

MAE measures typical absolute shot error; RMSE penalizes larger misses.
Brier score measures squared error between the over probability and the
binary over outcome. Lower values are better. Ten fixed probability bins
report mean predicted probability, actual over frequency and sample count.
Sparse bins should not be treated as reliable calibration evidence.

All eligible games contribute, even when the confidence policy skips a bet.
The confidence threshold applies only to illustrative bet statistics.
ROI assumes every selected bet was available at -110 with one unit risked.
No real sportsbook lines or prices are available, so ROI is not a market edge.

## Chronological protocol

Use at least three seasons for development, validation and final holdout.
The earliest season is development; intermediate seasons are validation;
the latest is holdout. Seasons are sorted chronologically. At least two are
required, but two seasons have no separate validation period.

By default the holdout's player data is neither loaded nor scored. With
--tune-weights, five prespecified weight candidates are compared by Brier
score only in development. The selected weights are frozen before loading
any validation or holdout player data. The existing multipliers are not tuned.
Development scores are in-sample for this selection and are optimistic.

Review validation, freeze players, line, confidence, weights, feature context
and minimum history, then explicitly use --include-holdout. A protocol hash
includes the implementation digest; player and context input digests are also
saved. Compare these across runs to detect changes. This is an explicit
workflow gate, not an irreversible lock: once viewed, a holdout must not be
reused to tune choices while still being called unseen.

Histories reset each season and the first ten appearances are excluded by
default. Prior-season blending and cold-start prediction are deferred to the
next accuracy phase. Model selection across repeated player subsets, lines
or validation runs still risks overfitting; one final holdout does not erase it.

## Offline dataset

Pass --dataset PATH to run without NHL requests. Required shape:

```json
{
  "players": {
    "8478402": {
      "20242025": [
        {
          "gameId": 2024020001,
          "gameDate": "2024-10-09",
          "shots": 3,
          "homeRoadFlag": "H",
          "opponentAbbrev": "WPG",
          "toi": "21:30"
        }
      ]
    }
  },
  "team_games": [
    {
      "season": "20242025",
      "gameId": 2024020001,
      "gameDate": "2024-10-09",
      "home": "EDM",
      "away": "WPG",
      "homeShots": 30,
      "awayShots": 25
    }
  ],
  "boxscores": {}
}
```

The example is schematic, not an actual game result or an adequate evaluation
sample. Add full logs for the requested players and seasons. For opponent
adjustment, team_games should cover the entire league's completed regular
season games, once per game, rather than only selected players' games.
boxscores optionally maps string game IDs to the raw NHL boxscore objects;
the existing engine reads playerByGameStats homeTeam/awayTeam forwards/defense
entries with playerId and powerPlayToi. If that field is absent, PP adjustment
remains neutral. Save raw data alongside reports to make runs reproducible.

```bash
python backtest.py mcdavid 3 55 --dataset history.json \
  --seasons 20232024 20242025 20252026 --tune-weights \
  --output development-validation.json
```

Default online runs fetch player logs only; they do not collect a complete
dated opponent or PP dataset automatically. Their feature coverage is partial.
Use a consistent context policy across development, validation and holdout.
The full label identifies the engine, not a guarantee that every input exists.

## Verification and remaining limitations

Regression coverage includes altered future outcomes and ice time, target and
future boxscores, dated opponent games, reversed logs, exact N+ scoring,
rest overrides, integer pushes, zero expected shots, metric arithmetic,
baseline sample parity, holdout exclusion, validation-independent tuning,
season-scoped team caches, missing data failures and offline CLI export.

Historical API results may include later statistical corrections. We have
not reconstructed timestamped live data snapshots. Default quick-name players
are a selected population, so a broader fixed roster is needed to assess
survivorship and selection bias. Confidence intervals, model distribution
selection, causal feature validation and real-market odds remain future work.

Earlier Phase 1/2 notes are exploratory. Their assertions of statistical
significance and betting edge are not established by this implementation.
