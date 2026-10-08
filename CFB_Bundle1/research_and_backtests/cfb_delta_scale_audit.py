"""
Real audit: for every delta cfb_matchup_deltas.py computes (compute_all --
the exact same production function cfb_matchup_card_v4.py calls to build
the real deep-dive PDF, not a reimplementation), pulls TODAY's real stats
and computes every delta for EVERY real game on this week's actual
schedule, then prints each value next to its own real "Analytical Scale"
text (METRIC_META) -- so instead of arguing about the formula in the
abstract, this shows the real numbers a real week of real games actually
produces, all at once, so it's obvious which delta(s) (if any) are
routinely blowing way past what their own documented scale describes.

WHY THIS EXISTS: several delta numbers looked
"completely off the scale" and negative (VT's Yards Per Game line, Red
Zone % delta of -34.9 against a scale documented only up to "10.1%+
Liquidation"). The formula's ALGEBRA was already hand-verified separately
(plain a-b subtraction, no custom sign logic, checked against real Ohio
State/Kent State FEI data) -- universal_single computes
bracket_a - bracket_b, which algebraically simplifies to
(away_off + away_def) - (home_off + home_def), i.e. it SUMS two
independent off/def gaps rather than showing just one side. That means its
real range is naturally about double what a single "away offense vs home
defense" comparison alone would produce, especially for a team that is
simultaneously strong on one side of the ball and weak on the other
(exactly the extreme-mismatch case where big red-zone/yardage gaps show
up). This audit exists to confirm that empirically against real games
rather than guessing, so METRIC_META's scale text can be recalibrated to
match the real distribution this correctly-implemented formula produces.

For every metric, a rough "sanity ceiling" (roughly 3-5x the highest
NUMBER actually printed in that metric's own real Analytical Scale text --
generous on purpose, since real blowout games legitimately can and do
exceed a scale's top labeled bucket; this is not a hard rule, just a
loud flag) is used to mark any real game whose value blows past even
that generous ceiling with a "*** FAR OUTSIDE SCALE ***" tag, so those
are impossible to miss in the real output.

Run this locally (needs real network access to TeamRankings,
bcftoys, and CFBD):

    python3 research_and_backtests/cfb_delta_scale_audit.py
"""
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cfb_working_schedule import (              # noqa: E402
    fetch_all_teamrankings_stats, fetch_bcftoys_ratings, fetch_cfbd_advanced_stats,
    fetch_live_cfb_schedule,
)
from cfb_matchup_deltas import compute_all, METRIC_META   # noqa: E402
import pandas as pd

SEASON_YEAR = 2026

# Rough, generous sanity ceilings -- roughly 3-5x the highest real NUMBER
# printed in that metric's own METRIC_META scale text (see module
# docstring). A metric not listed here has no clean single "biggest
# number" in its scale text (e.g. the paired 2nd Level/Open Field deltas,
# which are deliberately described as +/- directional, not bucketed) and
# is shown but never flagged.
SANITY_CEILING = {
    "Points Per Game (PPG) Delta": 60,
    "Yards Per Game (YPG) Delta": 400,
    "Yards Per Play (YPP) Delta": 4.0,
    "Plays Per Game (Pace) Delta": 30,
    "Red Zone % (Blood Zone) Delta": 60,
    "3rd Down % (Money Down) Delta": 50,
    "Heavy Artillery Line Push (Line Yards Delta)": 3.0,
    "Drive-Killer Penetration (Stuff Rate Delta)": 30,
    "Net Efficiency Delta (The Vegas Filter)": 5.0,
    "Net Success Rate Delta": 30,
    "FEI Delta": 6.0,
    "Vertical Lightning Strike Delta (Passing Explosiveness)": 2.0,
    "Passing Down Panic Index (PPA)": 2.0,
    "'Stay-on-Schedule' Rushing Delta (Success Rate)": 60,
    "4th & Inches Manhood Test (Power Success Rate)": 60,
    "The Chaos Coefficient Mismatch (Havoc Delta)": 60,
    "The Fraud Index & Fraud Gap (Points vs. Yards)": 50,
    "Air Depth Delta (Passing Volume vs. Efficiency)": 5.0,
}


def build_current_stats_lookup():
    """Same real 3-way merge (TeamRankings + bcftoys + CFBD) every other
    research script in this folder already uses -- see
    cfb_miss_stat_gap_check.py's build_current_stats_lookup() for the
    original. No ESPN pull needed here -- nothing in SINGLE_DELTA_SPECS/
    PAIRED_DELTA_SPECS uses an ESPN-sourced key."""
    print("Pulling fresh TeamRankings stats...")
    tr_df = fetch_all_teamrankings_stats()
    print(f" -> {len(tr_df)} teams")
    print("Pulling fresh bcftoys F+/FEI/DSR...")
    bcftoys_df, _ = fetch_bcftoys_ratings(SEASON_YEAR)
    print(f" -> {len(bcftoys_df)} teams")
    print("Pulling fresh CFBD advanced stats...")
    cfbd_df, _ = fetch_cfbd_advanced_stats(SEASON_YEAR)
    print(f" -> {len(cfbd_df)} teams")

    stats_lookup = tr_df.copy()
    for extra in (bcftoys_df, cfbd_df):
        if extra is None or extra.empty:
            continue
        extra = extra.reset_index() if extra.index.name == "Clean_Name" else extra
        stats_lookup = pd.merge(stats_lookup.reset_index() if stats_lookup.index.name == "Clean_Name" else stats_lookup,
                                 extra, on="Clean_Name", how="outer")
    if "Clean_Name" in stats_lookup.columns:
        stats_lookup = stats_lookup.set_index("Clean_Name")
    return stats_lookup[~stats_lookup.index.duplicated(keep="first")]


def main():
    stats_lookup = build_current_stats_lookup()

    print("\nPulling this week's real live schedule...")
    schedule_df, week_number, season_year = fetch_live_cfb_schedule()
    if schedule_df is None or schedule_df.empty:
        print("No real schedule returned -- nothing to audit.")
        return
    games = [(row["Away_Team"], row["Home_Team"]) for _, row in schedule_df.iterrows()
             if row.get("Away_Team") in stats_lookup.index and row.get("Home_Team") in stats_lookup.index]
    print(f" -> {len(games)} of {len(schedule_df)} real scheduled game(s) have both teams in today's stats_lookup.\n")

    per_metric_values = {}   # label -> [(away, home, value), ...]
    for away, home in games:
        away_ts, home_ts = stats_lookup.loc[away], stats_lookup.loc[home]
        if isinstance(away_ts, pd.DataFrame):
            away_ts = away_ts.iloc[0]
        if isinstance(home_ts, pd.DataFrame):
            home_ts = home_ts.iloc[0]
        results = compute_all(away_ts, home_ts)
        for label, result in results.items():
            kind = result[0]
            if kind in ("single",):
                value = result[1]
            elif kind == "paired":
                a, h = result[1], result[2]
                value = None
                if a is not None and h is not None:
                    value = a if abs(a) >= abs(h) else h  # report whichever side is more extreme
            else:  # volEff -- 4 values, skip from the flat numeric audit (no single scale number)
                continue
            if value is None:
                continue
            per_metric_values.setdefault(label, []).append((away, home, value))

    print("=" * 100)
    print("REAL PER-GAME VALUES vs. EACH METRIC'S OWN ANALYTICAL SCALE TEXT")
    print("=" * 100)
    for label, rows in per_metric_values.items():
        ceiling = SANITY_CEILING.get(label)
        scale_text = METRIC_META.get(label, "")
        print(f"\n--- {label} ---")
        print(f"  Scale: {scale_text}")
        vals = [v for _, _, v in rows]
        print(f"  Real distribution across {len(vals)} game(s): "
              f"min={min(vals):+.3f}  max={max(vals):+.3f}  mean={statistics.mean(vals):+.3f}  "
              f"median={statistics.median(vals):+.3f}")
        flagged = [(a, h, v) for a, h, v in rows if ceiling is not None and abs(v) > ceiling]
        if flagged:
            print(f"  *** {len(flagged)} game(s) FAR OUTSIDE this metric's generous sanity ceiling "
                  f"(|value| > {ceiling}) ***")
            for a, h, v in sorted(flagged, key=lambda r: -abs(r[2]))[:8]:
                print(f"      {a} @ {h}: {v:+.3f}")

    print("\n" + "=" * 100)
    print("SUMMARY: metrics with at least one real game far outside their own sanity ceiling")
    print("=" * 100)
    any_flagged = False
    for label, rows in per_metric_values.items():
        ceiling = SANITY_CEILING.get(label)
        if ceiling is None:
            continue
        flagged = [(a, h, v) for a, h, v in rows if abs(v) > ceiling]
        if flagged:
            any_flagged = True
            worst = max(flagged, key=lambda r: abs(r[2]))
            print(f"  {label}: {len(flagged)}/{len(rows)} game(s) flagged -- worst: "
                  f"{worst[0]} @ {worst[1]} = {worst[2]:+.3f} (ceiling {ceiling})")
    if not any_flagged:
        print("  None -- every real delta this week stayed inside its generous sanity ceiling.")


if __name__ == "__main__":
    main()
