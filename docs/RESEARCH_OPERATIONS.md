# Research operations extension — 2026-10-02

## Timestamped context

`official_context.py` fetches the official NHL daily lineup article at most once
per hour when a model-matched game needs it. It reads NewsArticle JSON-LD,
uses dateModified when available, retains the raw article with SHA256 and actual
observation time, and accepts same-game-day captures made before puck drop only.
Exact roster IDs/names and matching team headings are required. Injury lists,
scratch lists and line combinations remain projected editorial observations;
absence is never inferred as injury or scratch. Missing pages/schema produce
explicit collection_error. The source is free; it is not a contractual feed/SLA.

Source: https://www.nhl.com/news/nhl-lineup-projections-2026-27-season

Supplemental inputs are attached to each reproducible model record but **do not
change the frozen live probability or eligibility**. Historical recent-ten TOI
and recent3/previous7 role-change flags are exposed as proxies, not confirmed
projections. PP units and coach projected TOI remain missing unless an exact,
timestamped official-source observation is supplied through `context_inputs.py`.
No reliable complete free structured PP/projected-TOI feed was established.

`feature_study.py coverage --data-dir ../records/data` reports collection coverage.
`freeze-development` requires the completed future development period and will
not overwrite its frozen artifact. `validation` requires the fresh validation
period to have ended, matching protocol/code/model hashes, and a development
artifact created before validation began. No command opens either holdout.
Per-feature rate models and missingness/paired Brier/log-loss/calibration tests
are implemented; credible evidence of feature improvement requires new data.

## Separate coverage studies

`python coverage_studies.py` reproduces development-only zero-current-history,
team-change and TOI-role-change diagnostics from existing frozen inputs.
`python rookie_study.py` reproduces a separate official isRookie=1 cohort.
`--collect` requests only 2023–24 development logs, never historical validation
or the reserved holdout. Twelve fixed hash picks include low-participation
players without replacements; official game counts are checked. Retrospective
participation selection bias is disclosed. Rookies remain live-ineligible.

| Study | Sample | Interpretation |
| --- | --- | --- |
| Zero current history | 22 development player-games | Prior30 NB20 Brier .131730 vs prior-season mean NB20 .134198; too small, no promotion |
| Team changes | 6 transitions | No >=10 current-team-history paired sample; unresolved research |
| TOI role change | 128 games / 17 players | Scaled model .141952 vs frozen .137646 Brier; not a reason to deploy adjustment |
| Official rookies | 151 eligible games / 10 contributing players of 12 selected | Season NB20 .122635 vs recent5 NB20 .128328; development descriptive only |

These studies neither alter the original protocol nor claim unseen validation.
The new written prospective protocol is research/next_protocol.json. Development
starts October 3, 2026; fresh validation December 2–31; January 2027 final holdout
remains gated. The historical 2025–26 study holdout remains unopened.

## Settlement rules

`sportsbook_rules.json` records reviewed rules and remaining gaps for all four
currently sampled books. FanDuel Illinois sections 15.1/15.5 support any TOI,
regulation plus OT, shootout exclusion and specified abnormal-game void rules.
General resettlement permits official-result/error corrections within a reasonable
period; no precise numeric cutoff is specified. DraftKings' retrieved rule page omitted
its rule body; Bovada and BetOnline official general hockey rules were retrieved, but do not
establish complete individual SOG participation/correction semantics. No guessed
rules are inserted. API region=us does not identify jurisdiction.

`settlement_rules.assess` therefore leaves all current bookmaker settlements
unresolved. Official full-game SOG statistical grading and hypothetical returns
remain useful research outcomes, labeled separately. Stat revisions do not imply
that a bookmaker would regrade identically. No actual stakes exist.

## Sampling v2 and coverage

Existing daily selections are immutable. Newly selected days use hash_five_v2:
SHA256(day + policy + event ID) chooses up to five discovered upcoming games,
independent of price/model; all returned books/players/lines are archived. On a
five-game day the last hash pick's early window is explicitly omitted; all five
middle and late windows remain planned. This is at most14 calls/day, or434 over
31 days before outages, with the 450 cap and50 reserve unchanged. More than one
credit per call or quota use by another client can reduce collection further.
No billing reset date is inferred. Old/new policy periods must be reported
separately rather than treated as identical sampling regimes.

Discovery census now includes unselected games and selected games with zero
snapshots. Planned omissions are distinct from missed windows. Census cannot
measure games absent from the provider, games added after fixed selection, or
runs that never execute. Hash sampling reduces start-time preference but retains
provider/region/prop availability bias. No apparently attractive odds determine
selection. Schedules are checks twice an hour, not continuous collection.

## Reliability and recovery

Actions serializes runs. Before each paid call, the reservation ledger must be
committed and pushed to odds-records. A failed push prevents that call. A killed
runner after acknowledged reservation cannot cause the slot to be automatically
retried. Purchased snapshots are still saved before enrichment. A 14-day Actions
recovery artifact is uploaded before the final full-archive Git push.

If the final push fails, preserve/download that run's recovery artifact and compare
it against a fresh odds-records checkout. Do not overwrite newer ledger/quotes or
clear reserved slots. Missing snapshots are recoverable from the artifact; an
abruptly killed runner before artifact upload can still lose its response, but
its durable reservation remains. GitHub runs are external evidence when health
JSON cannot be updated. No notification channel is deployed.

Reports now include Wilson calibration intervals, matched market paired
Brier game-cluster intervals, unique observed event/player-game counts, price
movement coverage/mean, unresolved bookmaker decisions, and drawdown excluding
incompletely settled games. Cluster intervals need20 games. Wilson bin intervals
are descriptive and do not remove player/game dependence. No forecast-parameter
uncertainty interval has been validated; the dashboard states that explicitly.
