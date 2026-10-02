# NHL shots research build status

Updated 2026-10-02. Paper research only. Repository implementation is authoritative.

## Dashboard publishing extension

- Static public dashboard now reads a credential-free `data/review.json` summary
  exported by the existing recorder. Refreshing/viewing players uses no odds credits.
- Opportunities, Performance and Health views share the local API UI; browser
  timestamps recalculate staleness/expiry without pretending to refresh odds.
- GitHub Pages build, regression tests and deploy workflow are implemented.
  Publishing is limited to master; local Python API remains separate.
- Local regression:112 passed. Static build and export passed (60 archived players
  in the inspected archive). Browser binary unavailable; rendered mobile QA is
  still pending. [PR5](https://github.com/MatthewBlodgett/nhl-shots/pull/5) merged. Remote
  build/artifact upload passed in [run37076819392](https://github.com/MatthewBlodgett/nhl-shots/actions/runs/37076819392).
  Master build and deployment passed in [run37076909863, attempt2](https://github.com/MatthewBlodgett/nhl-shots/actions/runs/37076909863/attempts/2)
  after the owner enabled GitHub Actions as the Pages source.
  [Public dashboard](https://matthewblodgett.github.io/nhl-shots/) is deployed:
  bounded checks on 2026-10-02 returned HTTP200 for the page, archive-client.js
  and public archive summary (schema1,60 players, generated23:18:34 UTC; CORS enabled).
  No recorder was rerun and no odds credits were consumed by deployment verification.
- Master [recorder run37076909867](https://github.com/MatthewBlodgett/nhl-shots/actions/runs/37076909867)
  passed and persisted `data/review.json`:60 player summaries; quota9 used/491
  remaining at that recorded run. Browser reads consume no odds credits.
- [Dashboard instructions and setup](DASHBOARD.md). No secret or paid service is needed.


## Implemented operations extension

- Durable Git request reservation before each paid call; failed acknowledgment
  stops collection. Recovery artifact before final archive push; serialized runs.
- Discovery census includes selected games without snapshots and unselected
  games. Hash sampling for new daily selections records policy and a planned
  early omission, preserving five middle/late windows and at most14 daily calls.
  Existing selections are unchanged; 450-credit cap/50-credit reserve remain.
- Official timestamped NHL projected injuries, scratch lists and line combinations
  with exact IDs, same-day pregame gates, source hashes and explicit missingness.
  Supplementary only: frozen live probabilities and eligibility are unchanged.
- Separate reproducible development-only studies for zero-current-history,
  team changes, TOI role changes and an official12-player rookie cohort.
- Written future evaluation protocol plus per-feature shadow study code,
  development artifact freeze, hash/version validation gates and no holdout reader.
- Version-separated reporting adds Wilson bin intervals, paired market Brier
  game-cluster uncertainty, unique sampling counts, price-movement coverage,
  incomplete-game drawdown exclusion and unresolved bookmaker settlement counts.
- Mobile dashboard and read-only HTTP API: status, candidates, player forecasts,
  performance and research. Actual local HTTP integration tests exercise routes,
  invalid inputs, no arbitrary files and no POST. Loopback only, no hosted service.
- Rule registry covers all four sampled books; FanDuel Illinois and partial Bovada/BetOnline source reviews.
  All current bookmaker settlements remain unresolved rather than invented.

Details and study results: [RESEARCH_OPERATIONS.md](RESEARCH_OPERATIONS.md).
API/dashboard: [AGENT_INTERFACE.md](AGENT_INTERFACE.md).
Next frozen protocol: [next_protocol.json](../research/next_protocol.json).

## Verification

Local regression:109 passed. Offline replay of coverage and rookie studies passed.
Local HTTP integration passed. Official NHL daily article returned HTTP200 with
publication/modification time and SHA256 capture. Official rookie census and12
player logs collected only for2023–24 development; all logs matched census GP.
No historical validation or reserved2025–26 holdout was fetched by new studies.
Remote verification: [recorder run37073265058](https://github.com/MatthewBlodgett/nhl-shots/actions/runs/37073265058)
passed every step, including durable reservations, collection, recovery artifact
and final persistence. One paid request saved82 quotes; usage7/493. Archive at
19723d4 had six snapshots /574 quotes /four events. Twelve forecast records
included supplemental context. No model/eligibility changes were made.
Both [push regression](https://github.com/MatthewBlodgett/nhl-shots/actions/runs/37073265141)
and [PR regression](https://github.com/MatthewBlodgett/nhl-shots/actions/runs/37073274367)
passed. Recovery artifact11255926856 is available for14 days.
Implementation: [PR4](https://github.com/MatthewBlodgett/nhl-shots/pull/4).

Initial inspected master:94c223dff32073084968efe0e7ca4a1a40227cee; no open PRs.
Inspected odds-records:1d27f87ad095ef58db27ac7676951cac9cfc8ed3; five snapshots,
four events,492 quotes across DraftKings/FanDuel/Bovada/BetOnline. Provider usage
at that saved check:6 used/494 remaining. These are dated observations, not live
counts. Last prior recorder run37068563838 succeeded.

## Functionality awaiting evidence or deployment

1. Timestamped feature studies need future observations and settled games before
   fitting/evaluating improvements. PP roles and projected TOI have no complete
   reliable free structured source; missing fields must remain missing.
2. Rookie/zero-history and role-change studies are development diagnostics,
   not credible prospective evidence or authorization to relax eligibility.
3. Bookmaker jurisdiction, full correction policies and abnormal-game evidence
   remain unresolved. Official statistical ROI is not executable-book ROI.
4. Static dashboard is deployed and HTTP-verified on GitHub Pages. Rendered mobile
   inspection remains pending. Python API remains local; no remote API, autonomous
   agent or notifications have been activated. No purchase or credentials were requested.
5. Sampling v2 needs prospective coverage review. It cannot recover never-discovered
   games or guarantee scheduled runner delivery. Abrupt death before artifact
   upload can lose a response, though acknowledged reservations survive.
6. Probability-parameter uncertainty remains unvalidated; cluster intervals and
   calibration intervals are descriptive, and sparse bins are explicitly limited.
7. Both final holdouts remain closed. Live model promotion requires fresh validation;
   historical validation already viewed cannot be used to choose new parameters.

## Existing frozen model evidence

Validation: 1,343 player games, including 180 with one through nine current
appearances. Selected Brier 0.146610; season baseline 0.148067; recent ten
0.153496; legacy engine 0.149249. Paired interval versus season baseline
[-0.002958, 0.000408] includes zero. These results support continued paper
testing, not a claim of predictive superiority or profitability. See research/README.md.
