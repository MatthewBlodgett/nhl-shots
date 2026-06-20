# NHL Shots on Goal Predictor 🏒

**Predict shot totals for NHL player prop bets.**

---

## Quick Start

```bash
pip install -r requirements.txt
python shots.py mcdavid
python shots.py matthews away
python shots.py ovechkin 3.5 home
```

## Usage

```
python shots.py <player_name_or_id> [opponent] [line] [home|away] [b2b|rest]
```

### Quick names

| Tier | Players |
|---|---|
| ⭐ Elite | mcdavid, draisaitl, matthews, mackinnon, kucherov, ovechkin |
| A-tier | makar, pastrnak, kaprizov, stamkos, rantanen, marchand |
| B-tier | kconnor, werenski, chychrun, guenther, meier, boldy, forsberg, caufield, larkin, bouchard, panarin, debrusk |
| C-tier | kempe, jarvis, kadri, keller, svechnikov, hischier, hagel, reinhart, johnston, fiala, stutzle, dahlin, qhughes, eichel, celebrini, and more |

Or use any NHL player ID directly.

### Example output

```
============================================================
  Connor McDavid (EDM)
============================================================

📊 Season Stats (58 games):
   Total Shots: 220
   Average: 3.79 shots/game
   Home Avg: 4.62 | Away Avg: 2.97

🔥 Recent Form:
   Last 5 games: [8, 4, 3, 2, 3] (avg: 4.0)
   Last 10 avg: 3.9

💤 Days Rest Analysis:
   Current: 3+ days (factor: 1.03x)
   Historical: B2B=3.7, 1-day=3.74, 2-day=4.0, 3+day=4.0

⚡ Power Play Time (L3):
   Avg PP TOI: 4.32 min/game
   Status: PP1 player (factor: 1.08x)

📈 Time on Ice Trend:
   Recent (L5): 24.11 min | Season: 23.11 min
   Trend: Stable (factor: 1.0x)

🏠🛣️  Home/Away Splits:
   Home: 4.62 avg (29 games)
   Away: 2.97 avg (29 games)
   H/A Ratio: 1.558x
   🏡 Player-specific factors: Home=1.218x, Away=0.782x

🎯 Projection (HOME):
   Base: 3.87 × Loc: 1.218 × Rest: 1.03 × PP: 1.08
   Expected shots: 5.42

📈 Line Probabilities:
   Line     Over       Under
   ----------------------------
   1.5      94.9%      5.1%
   2.5      84.9%      15.1%
   3.5      69.2%      30.8%
   4.5      50.7%      49.3%
   5.5      33.3%      66.7%
```

## How It Works

1. **Data Source**: NHL API (free, no auth required)
2. **Stats Calculated**:
   - Season average (weight: 50%)
   - Last 10 game form (weight: 30%)
   - Last 5 game form (weight: 20%)
   - Home/away splits (player-specific when ≥15 games per location)
   - Opponent strength adjustment (shots allowed vs. league average)
   - Days rest tiers (B2B / 1-day / 2-day / 3+day)
   - Power play time correlation (from boxscore data)
   - Time on ice trends (rising/stable/declining)
3. **Projection**: Weighted average × all adjustment factors
4. **Probabilities**: Poisson distribution for over/under lines

## Backtesting

```bash
python backtest.py mcdavid 3       # 3+ shots, 55% confidence
python backtest.py matthews 4 65   # 4+ shots, 60% confidence
python backtest.py all 3 55        # all players, 3+, 55%
```

## Testing

```bash
python -m pytest tests/ -v
```

## Project Structure

```
nhl-shots/
├── shots.py                # Prediction engine
├── backtest.py             # Historical backtesting (uses shots.py)
├── requirements.txt
├── .gitignore
├── README.md
├── docs/                   # Phase research & validation docs
│   ├── PHASE1_IMPLEMENTATION_SUMMARY.md
│   ├── PHASE1_TEST_RESULTS.md
│   ├── PHASE2_SUMMARY_FOR_MAIN.md
│   ├── PHASE2_IMPLEMENTATION_SUMMARY.md
│   ├── PHASE2_BEFORE_AFTER_COMPARISON.md
│   ├── PHASE2_HOME_AWAY_RESEARCH.md
│   ├── VALIDATION_TESTS.md
│   └── USAGE_EXAMPLES.md
├── home_away_research.py   # Phase 2 research script
├── home_away_research_results.json
└── tests/                  # Pytest suite
    └── test_shots.py
```

## Dependencies

- Python 3.10+
- `requests`
- `pytest` (for running tests)

## Data Source

NHL API: `https://api-web.nhle.com/v1/`

## Future Enhancements

- [ ] Team shots allowed (opponent strength adjustment)
- [ ] Line combos / projected TOI
- [ ] Injury news integration
- [ ] Batch analysis for all players in today's games
- [ ] Web UI

## License

MIT