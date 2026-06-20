#!/usr/bin/env python3
"""
Research script to analyze player-specific home/away shot differentials.
Tests whether top-line players show bigger home advantage than depth players.
"""

import sys
sys.path.insert(0, '/data/home/.openclaw/workspace/Nix-HQ/projects/nhl-shots')

from shots import get_player_game_log, get_player_info, PLAYER_IDS
import json
from typing import Dict, List

# Sample groups - classified by typical line deployment
SAMPLE_PLAYERS = {
    "elite_1st_line": {
        "mcdavid": 8478402,
        "matthews": 8479318,
        "mackinnon": 8477492,
        "kucherov": 8476453,
        "pastrnak": 8477956,
        "kaprizov": 8478864,
    },
    "mid_tier_2nd_line": {
        "meier": 8478414,
        "boldy": 8481557,
        "larkin": 8477946,
        "kempe": 8477960,
        "zibanejad": 8476459,
        "hischier": 8480002,
    },
    "depth_3rd_4th_line": {
        "hagel": 8479542,
        "bennett": 8477935,
        "tippett": 8480015,
        "dorofeyev": 8481604,
        "johnston": 8482740,
        "gauthier": 8483445,
    }
}


def analyze_home_away_split(player_id: int, player_name: str) -> Dict:
    """Analyze home vs away shot splits for a player."""
    games = get_player_game_log(player_id)
    info = get_player_info(player_id)
    
    if not games:
        return {"error": "No game data"}
    
    home_shots = []
    away_shots = []
    
    for game in games:
        shots = game.get("shots", 0)
        location = game.get("homeRoadFlag", "")
        
        if location == "H":
            home_shots.append(shots)
        elif location == "R":
            away_shots.append(shots)
    
    home_avg = sum(home_shots) / len(home_shots) if home_shots else 0
    away_avg = sum(away_shots) / len(away_shots) if away_shots else 0
    
    # Calculate home/away ratio (how much better at home)
    home_away_ratio = home_avg / away_avg if away_avg > 0 else 1.0
    diff = home_avg - away_avg
    
    # Get player team and position
    team = info.get("currentTeamAbbrev", "")
    position = info.get("position", "")
    
    return {
        "player": player_name,
        "player_id": player_id,
        "team": team,
        "position": position,
        "home_games": len(home_shots),
        "away_games": len(away_shots),
        "home_avg": round(home_avg, 2),
        "away_avg": round(away_avg, 2),
        "home_away_ratio": round(home_away_ratio, 3),
        "diff": round(diff, 2),
        "home_shots": home_shots,
        "away_shots": away_shots,
    }


def run_research():
    """Run full research analysis."""
    results = {}
    
    print("\n" + "="*80)
    print("HOME/AWAY SHOT DIFFERENTIAL RESEARCH")
    print("="*80)
    
    for tier, players in SAMPLE_PLAYERS.items():
        print(f"\n{'='*80}")
        print(f"TIER: {tier.upper().replace('_', ' ')}")
        print(f"{'='*80}")
        
        tier_results = []
        
        for name, player_id in players.items():
            print(f"\n🔍 Analyzing {name}...")
            result = analyze_home_away_split(player_id, name)
            
            if "error" in result:
                print(f"   ❌ {result['error']}")
                continue
            
            tier_results.append(result)
            
            # Print individual results
            print(f"   Player: {result['player']} ({result['team']} - {result['position']})")
            print(f"   Home: {result['home_avg']} avg ({result['home_games']} games)")
            print(f"   Away: {result['away_avg']} avg ({result['away_games']} games)")
            print(f"   Home/Away Ratio: {result['home_away_ratio']}x")
            print(f"   Differential: {'+' if result['diff'] > 0 else ''}{result['diff']} shots/game")
        
        results[tier] = tier_results
        
        # Tier summary
        if tier_results:
            avg_ratio = sum(r['home_away_ratio'] for r in tier_results) / len(tier_results)
            avg_diff = sum(r['diff'] for r in tier_results) / len(tier_results)
            
            print(f"\n📊 {tier.upper()} SUMMARY:")
            print(f"   Average Home/Away Ratio: {avg_ratio:.3f}x")
            print(f"   Average Differential: {'+' if avg_diff > 0 else ''}{avg_diff:.2f} shots/game")
    
    # Cross-tier comparison
    print("\n" + "="*80)
    print("CROSS-TIER COMPARISON")
    print("="*80)
    
    tier_summaries = {}
    for tier, tier_results in results.items():
        if tier_results:
            ratios = [r['home_away_ratio'] for r in tier_results]
            diffs = [r['diff'] for r in tier_results]
            
            tier_summaries[tier] = {
                "avg_ratio": sum(ratios) / len(ratios),
                "avg_diff": sum(diffs) / len(diffs),
                "sample_size": len(tier_results),
                "min_ratio": min(ratios),
                "max_ratio": max(ratios),
            }
    
    print(f"\n{'Tier':<25} {'Avg Ratio':<12} {'Avg Diff':<12} {'Range':<20} {'n':<5}")
    print("-"*80)
    for tier, summary in tier_summaries.items():
        tier_label = tier.replace('_', ' ').title()
        print(f"{tier_label:<25} {summary['avg_ratio']:<12.3f} {summary['avg_diff']:<+12.2f} "
              f"{summary['min_ratio']:.3f}-{summary['max_ratio']:.3f}    {summary['sample_size']}")
    
    # Statistical insights
    print("\n" + "="*80)
    print("KEY INSIGHTS")
    print("="*80)
    
    # Find players with biggest home advantage
    all_results = []
    for tier_results in results.values():
        all_results.extend(tier_results)
    
    sorted_by_ratio = sorted(all_results, key=lambda x: x['home_away_ratio'], reverse=True)
    sorted_by_diff = sorted(all_results, key=lambda x: x['diff'], reverse=True)
    
    print("\n🏆 TOP 5 HOME ADVANTAGE (by ratio):")
    for i, r in enumerate(sorted_by_ratio[:5], 1):
        print(f"   {i}. {r['player']}: {r['home_away_ratio']}x ({r['home_avg']} home vs {r['away_avg']} away)")
    
    print("\n📉 TOP 5 ROAD WARRIORS (better away):")
    road_warriors = [r for r in sorted_by_ratio if r['home_away_ratio'] < 1.0]
    if road_warriors:
        for i, r in enumerate(road_warriors[:5], 1):
            print(f"   {i}. {r['player']}: {r['home_away_ratio']}x ({r['home_avg']} home vs {r['away_avg']} away)")
    else:
        print("   None found - all players shoot more at home")
    
    print("\n📊 SAMPLE SIZE ANALYSIS:")
    avg_home_games = sum(r['home_games'] for r in all_results) / len(all_results)
    avg_away_games = sum(r['away_games'] for r in all_results) / len(all_results)
    print(f"   Average home games: {avg_home_games:.1f}")
    print(f"   Average away games: {avg_away_games:.1f}")
    
    # Variance analysis
    all_ratios = [r['home_away_ratio'] for r in all_results]
    mean_ratio = sum(all_ratios) / len(all_ratios)
    variance = sum((r - mean_ratio) ** 2 for r in all_ratios) / len(all_ratios)
    std_dev = variance ** 0.5
    
    print(f"\n📈 STATISTICAL VARIANCE:")
    print(f"   Mean ratio: {mean_ratio:.3f}")
    print(f"   Std deviation: {std_dev:.3f}")
    print(f"   Range: {min(all_ratios):.3f} - {max(all_ratios):.3f}")
    
    # Correlation between tier and home advantage
    print(f"\n🔬 HYPOTHESIS TEST:")
    elite_avg = tier_summaries.get("elite_1st_line", {}).get("avg_ratio", 0)
    depth_avg = tier_summaries.get("depth_3rd_4th_line", {}).get("avg_ratio", 0)
    
    if elite_avg and depth_avg:
        diff_pct = ((elite_avg - depth_avg) / depth_avg) * 100
        print(f"   Elite 1st line avg ratio: {elite_avg:.3f}")
        print(f"   Depth 3rd/4th line avg ratio: {depth_avg:.3f}")
        print(f"   Difference: {diff_pct:+.1f}%")
        
        if abs(diff_pct) > 5:
            print(f"   ✅ SIGNIFICANT: Elite players show {abs(diff_pct):.1f}% {'more' if diff_pct > 0 else 'less'} home advantage")
        else:
            print(f"   ⚠️  MARGINAL: Only {abs(diff_pct):.1f}% difference - may not be significant")
    
    # Recommendation
    print("\n" + "="*80)
    print("RECOMMENDATION")
    print("="*80)
    
    # Calculate what threshold makes sense
    min_games_threshold = int(min(avg_home_games, avg_away_games))
    
    if std_dev > 0.15:  # High variance suggests individual differences matter
        print("✅ IMPLEMENT PLAYER-SPECIFIC HOME/AWAY FACTORS")
        print(f"   Reason: High variance (σ={std_dev:.3f}) indicates individual differences are significant")
        print(f"   Suggested minimum sample: {min_games_threshold} games in each location")
        print(f"   Fallback: Use flat 1.05x home / 0.95x away for insufficient samples")
    else:
        print("❌ STICK WITH FLAT MULTIPLIER")
        print(f"   Reason: Low variance (σ={std_dev:.3f}) suggests individual differences are noise")
        print(f"   The league-wide trend is sufficient")
    
    # Save results to JSON for further analysis
    output_file = "/data/home/.openclaw/workspace/Nix-HQ/projects/nhl-shots/home_away_research_results.json"
    with open(output_file, 'w') as f:
        json.dump({
            "results": results,
            "tier_summaries": tier_summaries,
            "statistics": {
                "mean_ratio": mean_ratio,
                "std_dev": std_dev,
                "min_ratio": min(all_ratios),
                "max_ratio": max(all_ratios),
                "avg_home_games": avg_home_games,
                "avg_away_games": avg_away_games,
            },
            "recommendation": {
                "implement_player_specific": std_dev > 0.15,
                "min_games_threshold": min_games_threshold,
            }
        }, f, indent=2)
    
    print(f"\n💾 Full results saved to: {output_file}")
    print()


if __name__ == "__main__":
    run_research()
