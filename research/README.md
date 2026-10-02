# Broad historical count-model study

Study frozen 2026-10-02. Development 2023–24; validation 2024–25; 2025–26 reserved holdout was not fetched or scored by the study.

Development-selected model: **blend20_nb20**. Twenty equivalent prior appearances shrink the current mean toward the last thirty prior-season appearances; NB2 dispersion is twenty.

## Results

| Period / sample | Games | Selected Brier | Season baseline | Recent ten baseline | Legacy engine |
| --- | ---: | ---: | ---: | ---: | ---: |
| development / all | 1449 | 0.153586 | 0.156536 | 0.161884 | 0.158339 |
| development / early | 198 | 0.155722 | 0.173535 | 0.173535 | 0.175406 |
| development / established | 1251 | 0.153248 | 0.153846 | 0.160040 | 0.155638 |
| validation / all | 1343 | 0.146610 | 0.148067 | 0.153496 | 0.149249 |
| validation / early | 180 | 0.155681 | 0.164155 | 0.164155 | 0.157624 |
| validation / established | 1163 | 0.145206 | 0.145577 | 0.151846 | 0.147952 |

Scores average 2+, 3+ and 4+ Brier errors on identical player games. Lower is better. Early means one through nine current-season appearances; zero-history games are excluded.

## Interpretation

The selected model improved validation point estimates, but its paired 95 percent player-cluster interval versus the season baseline includes zero. This is sufficient to run a versioned paper experiment, not to establish predictive superiority or a market edge. The development scores are optimistic because they selected the candidate.

Eight prespecified candidate families were compared. The validation winner was not substituted for the development winner. Legacy feature ablations are descriptive diagnostics and did not tune the selected model.

### Validation paired intervals

| Comparator | Brier difference | Lower | Upper |
| --- | ---: | ---: | ---: |
| season_poisson | -0.001457 | -0.002958 | 0.000408 |
| recent10_poisson | -0.006886 | -0.010127 | -0.003690 |
| legacy_full | -0.002639 | -0.005696 | 0.000308 |

Negative differences favor the selected model. These are descriptive intervals across a small fixed cohort, not a correction for all model-selection uncertainty.

## Cohort and completeness

Twenty-four players were selected using only 2022–23 season totals: forwards and defensemen, three position-specific shot-rate tertiles, four deterministic hash selections per stratum, minimum forty appearances. No later-season replacements were made.

| Player | Position | Volume tier |
| --- | --- | --- |
| Sean Kuraly | F | low |
| Radek Faksa | F | low |
| Nick Foligno | F | low |
| Sam Carrick | F | low |
| Marcus Johansson | F | medium |
| Cole Perfetti | F | medium |
| Yanni Gourde | F | medium |
| Emil Bemstrom | F | medium |
| Mark Stone | F | high |
| Nathan MacKinnon | F | high |
| Auston Matthews | F | high |
| Alex Iafallo | F | high |
| Colton White | D | low |
| Jordan Oesterle | D | low |
| Patrik Nemeth | D | low |
| Jarred Tinordi | D | low |
| Bowen Byram | D | medium |
| Mattias Samuelsson | D | medium |
| Pierre-Olivier Joseph | D | medium |
| Jacob MacDonald | D | medium |
| Cam Fowler | D | high |
| Devon Toews | D | high |
| Moritz Seider | D | high |
| Jake Sanderson | D | high |

Missing participation is retained in the coverage file. Twenty-two cohort players contribute development predictions and twenty contribute validation predictions. Full player-log game counts match the complete official season census. Each team season contains 1,312 regular-season games, checked through matching home/away rows. Opponent aggregates include only earlier dates.

## Limits and next work

- Established-player cohort excludes rookies and short-season players.
- No historical sportsbook prices; no market profitability conclusion.
- Official historical stats include subsequent corrections.
- Power-play, injuries and confirmed deployment are not supplied.
- Early-season validation has only 180 player games across twenty players; confidence is limited.
- The study supplies historical opponent context but the selected model uses count history alone. Injury, role and power-play feature integration remains open.
- Prior-season data used by a later live 2026–27 forecast does not constitute opening or scoring the study holdout. The study loader explicitly rejects 2025–26 data.

## Reproduce

`python research_study.py --offline` uses the committed compressed dataset and never requests odds. Raw NHL responses, the protocol, selected model, predictions and report are included in this folder.

Protocol SHA256: `531bc7265bdc6844a3c4d86607be6dbae0296c9dca7a53d599d0aa8b5993d764`
Dataset SHA256: `283ef604ffbe3d3361bfa025c31c8794addd890893e2b3ea8e51fbf1c8aa2b5e`

Inputs are corrected official historical records rather than reconstructed real-time publications. NHL sources: https://api-web.nhle.com/v1 and https://api.nhle.com/stats/rest/en.
