# NHL shots research build status

Updated 2026-10-02. The odds recorder remains a paper research experiment.

## Completed in this build

1. Frozen 24-player cohort from 2022–23 with forwards/defensemen and shot-rate
   strata; no later replacement of inactive players. Player logs match official
   season game counts. Complete dated opponent context covers both study seasons.
2. Reproducible development and validation study, compressed raw inputs and
   per-game predictions. Eight predeclared model families, four legacy feature
   ablations, line/position/volume breakdowns, calibration and paired player
   cluster intervals. The 2025–26 holdout is not fetched by the study loader.
3. Development-selected blend20_nb20 frozen for live paper forecasts. Prior
   weighting and dispersion were not changed to match validation. Early-season
   gates now require one current appearance, twenty prior appearances, and extra
   caution for changed teams. Rookies and zero-current-history games stay blocked.
   Candidate lines are restricted to the studied 1.5, 2.5 and 3.5 thresholds.
4. Versioned reproducible live model inputs, seven-day prior-log cache and
   distinct invalid-data versus history eligibility blocks.
5. Prospective fixed-window reporting: one paper decision per player/game,
   model-version separation, matched market benchmarks, calibration, hypothetical
   returns and drawdowns, game-cluster intervals and unresolved outcomes.
6. Once-daily stat-correction checks for seven days with previous-actual ledger;
   longer unresolved recovery through a bounded explicit lookback.
7. Operational health and bounded recent-run history, quote blockers, quota pause,
   observed-game missing windows and settlement backlog. Read-only agent JSON CLI
   returns timestamps, expiry, model coverage and research results without keys.

## Evidence and limits

Validation: 1,343 player games, including 180 with one through nine current
appearances. Selected Brier 0.146610; season baseline 0.148067; recent ten
0.153496; legacy engine 0.149249. Paired interval versus season baseline
[-0.002958, 0.000408] includes zero. These results support continued paper
testing, not a claim of predictive superiority or profitability. See research/README.md.

## Remaining priorities

1. Accumulate and review prospective results under the frozen model; verify
   each sampled bookmaker's SOG participation, overtime and void rules before
   interpreting hypothetical returns as executable results.
2. Investigate reliable timestamped injuries, line deployment, projected ice
   time and PP-role data. No external provider is selected or purchased. Future
   feature studies must use development-only choices and a fresh validation
   period rather than tune to the results already viewed.
3. Study rookies, zero-current-history players and changed roles; the current
   cohort does not support their eligibility. Consider probability calibration
   only through a properly separated experiment; none has been fitted here.
4. Add a convenient review dashboard or hosted agent API/MCP after agreeing
   the operating environment. The GitHub status/performance pages and JSON CLI
   work now; no autonomous reasoning agent or hosted dashboard is deployed.
5. Review free-tier sampling coverage and reserve use after several weeks.
   Selective/rotating sampling needs a recorded policy, not silent selection
   of only apparently attractive odds.
6. Improve runner/persistence failure recovery, archive growth management and
   complete coverage of games with no snapshots. A failed runner cannot write
   its own health file; GitHub Actions still needs occasional review.
7. Freeze the next research protocol before opening the reserved holdout.
   Prospective proof, operational reliability and a separate user decision
   are required before any live wagering or paid expansion.

The previous Word plan is a dated review document. This file and the archive
status are the current implementation record.
