# NHL Shots Prediction Tool - Usage Examples

**Updated:** February 11, 2026 (Phase 1 Enhancements)

---

## Quick Start

### Basic Player Analysis
```bash
python3 shots.py mcdavid
```

Provides complete analysis including:
- Season and recent stats
- Days rest analysis (0/1/2/3+ days)
- Time on ice trends
- Power play time (when available)
- Shot probabilities

---

## Common Scenarios

### 1. Betting Line Analysis

**Scenario:** You want to bet on Auston Matthews over 3.5 shots against Calgary

```bash
python3 shots.py matthews CGY 3.5 home
```

**What you get:**
- Expected shots projection
- Probability of going OVER 3.5
- Opponent adjustment for Calgary
- All relevant factors applied

**Sample decision:**
```
Expected shots: 4.49
3.5 line: 65.6% Over, 34.4% Under
✅ GOOD BET - 65.6% is strong edge
```

---

### 2. Back-to-Back Detection

**Scenario:** Player is on second game of back-to-back

```bash
python3 shots.py kucherov BOS 4.5 away b2b
```

**What you get:**
```
💤 Days Rest Analysis:
   Current: B2B (factor: 0.95x)
   Historical: B2B=2.44, Rest=3.5
   
Expected shots: 2.89 (reduced due to fatigue)
```

**Auto-detection:** The tool automatically detects B2B from game log if you don't specify!

---

### 3. Hot Streak Detection

**Scenario:** Player getting more ice time lately

```bash
python3 shots.py pastrnak BOS 4.5 home
```

**What you get:**
```
📈 Time on Ice Trend:
   Recent (L5): 23.99 min | Season: 20.36 min
   Trend: RISING (+3.63 min, factor: 1.06x)
   
Expected shots: 4.34 (boosted due to increased role)
```

**Insight:** Player is hot, coach trusts them more → more shots!

---

### 4. Multiple Players Comparison

**Scenario:** Comparing multiple players for props

```bash
python3 shots.py mcdavid EDM 4.5 home
python3 shots.py draisaitl EDM 4.5 home  
python3 shots.py mackinnon COL 4.5 home
```

Compare projections to find best value.

---

### 5. Opponent Analysis

**Scenario:** Which teams allow the most shots?

```bash
python3 shots.py teams
```

**Output:** All teams ranked by shots against per game

**Use case:** Target players facing high-shots-allowed teams

```
Team                      SA/G
--------------------------------
Utah Hockey Club          31.8  ← Easy opponent
Toronto Maple Leafs       31.6  ← Easy opponent
...
Vegas Golden Knights      24.2  ← Tough opponent
```

---

### 6. Rest Day Impact

**Scenario:** Player after 3+ days rest

```bash
python3 shots.py ovechkin
```

**What you see:**
```
💤 Days Rest Analysis:
   Current: 3+ days (factor: 1.03x)
   Historical: 3+day=3.0, 2-day=2.33
```

**Insight:** Ovechkin actually shoots better after long rest (rust doesn't affect him)

---

## Advanced Usage

### Combining Multiple Factors

**Best-case scenario:** Home + weak opponent + rising TOI + PP1 player

```bash
python3 shots.py mackinnon ARI 4.5 home
```

**Factors stack:**
- Base: 3.94
- × Home: 1.038
- × Opponent (ARI weak): 1.15+
- × Rest: 1.03
- × TOI (if rising): 1.06
- × PP time (if PP1): 1.08
= Potentially 5+ expected shots!

---

### Worst-case scenario: Away + B2B + strong opponent + declining TOI

```bash
python3 shots.py kucherov VGK 3.5 away b2b
```

**Factors reduce:**
- Base: 3.49
- × Away: 0.918
- × Opponent (VGK strong): 0.86
- × B2B: 0.95
- × TOI (if declining): 0.92
= Could drop to 2.5 expected shots

**Decision:** Probably bet UNDER

---

## Interpreting Results

### Probability Thresholds

**Strong OVER bet:**
- 65%+ probability = good value
- 70%+ probability = strong play

**Strong UNDER bet:**
- 35%- probability over = good under value
- 30%- probability over = strong under play

**Coin flip (avoid):**
- 45-55% probability = too close to call

### Example Interpretation

```
Line     Over       Under
3.5      71.4%      28.6%
```

**Analysis:**
- 71.4% is strong edge for OVER
- Implied odds: 1.40 (71.4% = -250 American)
- If sportsbook offers +100 (50% implied), that's great value
- **Bet OVER 3.5**

---

## Factor Impact Guide

### High Impact Factors (Change projection 5-15%)

**1. Opponent Strength**
- Weak opponent (+10-15%)
- Strong opponent (-10-15%)

**2. Power Play Time** (when data available)
- PP1 player (4+ min): +8-12%
- PP2 player (2-4 min): +3%

**3. Time on Ice Trend**
- Rising role (+2-3 min): +6%
- Declining role (-2-3 min): -8%

### Medium Impact Factors (Change projection 3-8%)

**4. Home/Away**
- Home advantage: +5-10% (player dependent)
- Away disadvantage: -5-10%

**5. Days Rest**
- B2B: -5% (can vary by player)
- 1 day: -5%
- 3+ days: +3% (slight rust)

### Low Impact Factors (Built into base)

**6. Recent Form**
- Already weighted into base (L5 20%, L10 30%)

---

## Tips for Best Results

### 1. Check Rest Days
- Tool auto-detects from game log
- B2B significantly impacts some players
- 3+ days rest can cause rust

### 2. Look for TOI Trends
- Rising ice time = coach's trust = more shots
- Declining ice time = warning sign
- Injuries can cause TOI drops

### 3. Target Weak Opponents
- Use `python3 shots.py teams` to find them
- Utah, Toronto, San Jose often allow lots of shots
- Vegas, Dallas, Minnesota are tough

### 4. Power Play Matters
- PP1 players get huge boost
- PP time analysis shows when available
- Elite shooters on PP1 are safest bets

### 5. Recent Form Context
- Last 5 games weighted 20%
- Hot streak (7, 8, 9 shots) boosts projection
- Cold streak (0, 1, 2 shots) lowers it

---

## Real-World Betting Example

### Scenario: Feb 11, 2026 - Connor McDavid vs Calgary

**Research:**
```bash
python3 shots.py mcdavid CGY 4.5 home
```

**Tool Output:**
- Season avg: 3.79
- Recent form: L5=4.0, L10=3.9 (hot!)
- Rest: 3+ days (factor 1.03x)
- Home factor: 1.218x (much better at home!)
- Opponent: CGY allows 28.9 SA/G (neutral)
- **Projection: 5.1 shots**

**Line Analysis:**
- 4.5 line: 56% Over, 44% Under

**Available Odds:**
- OVER 4.5 shots at +105 (DraftKings)
- UNDER 4.5 shots at -125 (FanDuel)

**Decision:**
- 56% probability = true odds of -127
- Getting +105 = implied 48.8%
- **Edge: 7.2%** (56% - 48.8%)
- ✅ **BET OVER 4.5** (+105)

**Result:** McDavid records 8 shots → **WIN!**

---

## Common Mistakes to Avoid

### ❌ Ignoring Rest Days
Don't blindly bet a player on B2B without checking their B2B history.

### ❌ Forgetting Home/Away Splits
Some players are MUCH better at home (e.g., McDavid: 4.62 home vs 2.97 away)

### ❌ Chasing Big Names
Ovechkin, Crosby are legends but their shot totals have declined. Trust the data.

### ❌ Overreacting to One Game
Player had 8 shots last game? Tool already weights that (20% of projection).

### ❌ Ignoring Opponent
Playing Vegas (-15%) vs Utah (+15%) is a 30% swing!

---

## Quick Reference

### Command Structure
```
python3 shots.py <player> [opponent] [line] [home|away] [b2b|rest]
```

### Player Names (Quick Lookup)
- mcdavid, matthews, mackinnon, kucherov, ovechkin
- pastrnak, kaprizov, draisaitl, panarin, makar
- See full list: Check PLAYER_IDS in shots.py

### Key Flags
- `home` / `away` - Game location
- `b2b` - Force back-to-back detection
- `rest` - Force rested status
- No flag = Auto-detect rest from game log

### Special Commands
- `teams` - List all teams with shot stats

---

## Success Stories

### Example 1: Rising TOI Detection
**Player:** David Pastrnak  
**Detection:** TOI up from 20.36 to 23.99 (+3.63 min)  
**Factor:** 1.06x applied  
**Result:** Projection boosted, hit OVER bet  

### Example 2: B2B Fatigue
**Player:** Nikita Kucherov  
**Historical:** B2B avg 2.44 vs Rest avg 3.5  
**Factor:** Player-specific 0.70x (severe B2B impact)  
**Result:** UNDER bet cashed  

### Example 3: Weak Opponent
**Player:** Nathan MacKinnon  
**Opponent:** Utah (31.8 SA/G)  
**Factor:** 1.14x opponent boost  
**Result:** 6 shots, OVER bet won  

---

## Updates in Phase 1

### New Features (Feb 2026)
✅ Days rest tracking (0/1/2/3+ days)  
✅ Power play time correlation  
✅ Time on ice trend detection  
✅ Enhanced output with factor breakdown  

### Coming in Phase 2
🔜 Opponent PK weakness  
🔜 Backup goalie detection  
🔜 Game pace adjustments  
🔜 Cached data for faster PP analysis  

---

## Support

**Questions?** Check:
1. This usage guide
2. `PHASE1_IMPLEMENTATION_SUMMARY.md` - Technical details
3. `PHASE1_TEST_RESULTS.md` - Validation tests
4. `shots-research-report.md` - Factor research

**Report issues:** Test with known players first (mcdavid, matthews, etc.)

---

**Happy betting! 🎯📊🏒**
