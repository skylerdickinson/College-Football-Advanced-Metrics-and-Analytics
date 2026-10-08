"""
Answers a specific question: for the games the STAT-VOTE MODEL
has picked WRONG so far, what was the SEPARATE forecast engine's
win-probability margin (today's stats, post-hoc), and is there a real
correlation between a narrow forecast margin and the stat-vote model
missing.

IMPORTANT DISTINCTION -- read this before trusting anything below:
build_matchup_forecast() (the "forecast engine", in cfb_working_schedule.py)
is a SEPARATE, hand-weighted model from the stat-vote model that actually
drives the report's tracked accuracy (87.5% as of this writing) and the
turquoise/orange highlighting. The forecast engine has never been
backtested or validated the way the stat-vote model has (see
cfb_stat_vote_validation_backtest.py). This script borrows the forecast
engine's win-probability number purely as a diagnostic LENS on the
stat-vote model's misses -- finding a correlation here is a lead worth
looking at, not proof the forecast engine itself is calibrated or reliable.

REAL, DISCLOSED LIMIT: same as the FEI/F+ margin check -- this uses TODAY's
current stats for every input the forecast engine needs (FPI, efficiency,
scoring, yardage, turnovers, home-field), not a frozen snapshot from each
game's actual date, since most of those sources don't publish a historical
week-by-week archive either. Fine for looking at margin-size PATTERNS
across many games, not a claim about the exact number on any one game day.

Run this locally (needs real network access to TeamRankings, bcftoys,
CFBD, and ESPN):

    python3 research_and_backtests/cfb_winprob_margin_check.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cfb_working_schedule import load_stat_history, tune_stat_weights, build_matchup_forecast  # noqa: E402
from cfb_weekly_diagnostics_check import build_live_stats_lookup  # noqa: E402 -- reuses the same real data-pull pipeline
import pandas as pd

SEASON_YEAR = 2026


def bucket_label(margin, edges):
    for lo, hi, label in edges:
        if lo <= margin < hi:
            return label
    return "other"


def main():
    history = load_stat_history()
    included_stats, acc, correct, decided, total = tune_stat_weights(history)
    weights_by_key = {key: weight for _, key, weight, _, _ in included_stats}
    included_keys = [key for _, key, _, _, _ in included_stats]
    print(f"Current stat-vote model: {included_keys} -> {correct}/{decided} = {acc*100:.1f}% on {total} games\n")

    print("Pulling today's real stats for the forecast engine (TeamRankings, ESPN FPI, bcftoys, CFBD)...")
    stats_lookup, _schedule_df, _week, _season = build_live_stats_lookup(SEASON_YEAR)
    print(f" -> {len(stats_lookup)} teams\n")

    rows = []
    for game in history["games"].values():
        votes = game.get("votes", {})
        score = sum(weights_by_key.get(k, 0) * votes[k] for k in included_keys if k in votes)
        if score == 0:
            continue  # stat-vote model had no decided pick on this one -- excluded the same way everywhere else
        is_miss = score < 0

        away, home = game.get("away"), game.get("home")
        winner, loser = game.get("winner"), game.get("loser")
        if away is None or home is None or away not in stats_lookup.index or home not in stats_lookup.index:
            continue
        away_ts, home_ts = stats_lookup.loc[away], stats_lookup.loc[home]
        if isinstance(away_ts, pd.DataFrame):
            away_ts = away_ts.iloc[0]
        if isinstance(home_ts, pd.DataFrame):
            home_ts = home_ts.iloc[0]

        try:
            forecast = build_matchup_forecast(away, home, away_ts, home_ts)
        except Exception:
            forecast = None
        if not forecast:
            continue  # forecast engine had no real data for this matchup -- can't check it

        favored_prob = max(forecast["home_win_prob"], forecast["away_win_prob"]) * 100
        win_prob_margin = favored_prob - 50.0
        stat_vote_pick = loser if is_miss else winner
        rows.append({
            "winner": winner, "loser": loser, "is_miss": is_miss,
            "win_prob_margin": win_prob_margin, "favored_team": forecast["favored_team"],
            "stat_vote_pick": stat_vote_pick,
            "forecast_agrees": forecast["favored_team"] == stat_vote_pick,
        })

    misses = [r for r in rows if r["is_miss"]]
    print(f"{len(rows)} real decided stat-vote games matched to today's forecast-engine data; "
          f"{len(misses)} of those are stat-vote misses.\n")

    if not misses:
        print("No real misses matched -- nothing to check.")
        return

    # ---- Every disagreement, not just the 6 misses. A disagreement on a
    # HIT means the forecast engine would have been WRONG on a game the
    # stat-vote model got right -- the mirror image of the 3/6 "would have
    # caught it" misses. This is the real answer to "did they disagree on
    # any others."
    disagreements = [r for r in rows if not r["forecast_agrees"]]
    disagree_on_hit = [r for r in disagreements if not r["is_miss"]]
    disagree_on_miss = [r for r in disagreements if r["is_miss"]]
    agreements = [r for r in rows if r["forecast_agrees"]]
    print(f"=== Every game where the forecast engine picked a DIFFERENT team than the stat-vote model "
          f"({len(disagreements)} of {len(rows)}) ===")
    print(f"  Disagreed on a stat-vote MISS (forecast would have been right): {len(disagree_on_miss)} of "
          f"{len(misses)} misses")
    print(f"  Disagreed on a stat-vote HIT (forecast would have been wrong):  {len(disagree_on_hit)} of "
          f"{len(rows) - len(misses)} hits")
    if disagree_on_hit:
        print("\n  The hits where the forecast engine disagreed (forecast favored the team that actually lost):")
        for r in sorted(disagree_on_hit, key=lambda r: r["win_prob_margin"]):
            print(f"    {r['winner']:20s} over {r['loser']:20s}  stat-vote picked {r['stat_vote_pick']:20s} "
                  f"(correctly) -- forecast favored {r['favored_team']} by {r['win_prob_margin']:+.1f} pts instead")
    print(f"\n  Overall: forecast agrees with the stat-vote pick on {len(agreements)}/{len(rows)} games "
          f"({len(agreements)/len(rows)*100:.1f}%); stat-vote hit rate when they agree = "
          f"{sum(1 for r in agreements if not r['is_miss'])}/{len(agreements)} "
          f"({(sum(1 for r in agreements if not r['is_miss'])/len(agreements)*100 if agreements else 0):.1f}%), "
          f"when they disagree = {sum(1 for r in disagreements if not r['is_miss'])}/{len(disagreements)} "
          f"({(sum(1 for r in disagreements if not r['is_miss'])/len(disagreements)*100 if disagreements else 0):.1f}%).")

    print("\n=== Forecast-engine win-prob margin for each of the stat-vote model's real misses (narrowest first) ===")
    for r in sorted(misses, key=lambda r: r["win_prob_margin"]):
        agrees = "forecast ALSO favored the loser (agrees with the miss)" if r["favored_team"] == r["loser"] \
            else "forecast favored the real winner (disagreed with the stat-vote pick)"
        print(f"  {r['winner']:20s} over {r['loser']:20s}  win-prob margin = {r['win_prob_margin']:+5.1f} pts   ({agrees})")

    print("\n=== Real miss rate by forecast win-prob margin bucket (ALL decided stat-vote games, not just misses) ===")
    edges = [(0.0, 5.0, "very narrow (<5 pts)"), (5.0, 15.0, "narrow (5-15 pts)"),
              (15.0, 25.0, "moderate (15-25 pts)"), (25.0, 999.0, "wide (25+ pts)")]
    buckets = {}
    for r in rows:
        b = bucket_label(r["win_prob_margin"], edges)
        buckets.setdefault(b, {"n": 0, "misses": 0})
        buckets[b]["n"] += 1
        buckets[b]["misses"] += 1 if r["is_miss"] else 0
    for lo, hi, label in edges:
        d = buckets.get(label, {"n": 0, "misses": 0})
        rate = d["misses"] / d["n"] * 100 if d["n"] else 0.0
        print(f"  {label:24s} n={d['n']:3d}  misses={d['misses']:2d}  miss rate={rate:5.1f}%")

    avg_miss = sum(r["win_prob_margin"] for r in misses) / len(misses)
    avg_all = sum(r["win_prob_margin"] for r in rows) / len(rows)
    avg_hits = sum(r["win_prob_margin"] for r in rows if not r["is_miss"]) / max(1, len(rows) - len(misses))
    print(f"\nAverage forecast win-prob margin: misses={avg_miss:+.1f} pts  hits={avg_hits:+.1f} pts  "
          f"all decided games={avg_all:+.1f} pts")
    print("\n(Small n, and this is the UNVALIDATED forecast engine's number, not the stat-vote model's own -- "
          "read this as a lead to look at further, not a finished result.)")


if __name__ == "__main__":
    main()
