"""
ONE weekly command that answers the three things from the sacks/FEI-margin
investigation, run fresh against whatever's on record right now:

  1. THIS WEEK'S LIVE GAMES: for every real game on the live schedule, the
     model's pick, whether it's flagged risky (Def Sacks/Game disagrees --
     the one signal that held up, 0% vs 37.5% miss rate), the raw FEI/F+
     margin between the two teams, and the separate (unvalidated) forecast
     engine's win-probability margin over a coin flip -- since "margin"
     could mean either one, both are printed so you can see which number
     you're looking at.
  2. THE SACKS + FEI/F+-MARGIN CHECKS, re-run fresh: does the "sacks
     disagrees with the pick" split still hold up as more games get played,
     and does narrow FEI/F+ margin add anything on top of it (as of
     2026-09-22: no -- narrow+disagree missed LESS than wide+disagree,
     30% vs 50%, small n). Reuses cfb_fei_margin_check.py's own
     already-tested logic directly, not a reimplementation.
  3. A SCAN ACROSS EVERY STAT (not just sacks) for a similarly clean
     agree/disagree-with-the-pick split -- so if some other stat starts
     showing the same pattern sacks did, it shows up here instead of
     needing to be hand-checked again.

REAL, DISCLOSED LIMIT: same as every other script in this folder -- FEI/F+
are TODAY's current bcftoys values (no historical week-by-week archive
exists there), and small buckets are small buckets. Read the n's.

Run this locally (needs real network access to TeamRankings, bcftoys,
CFBD, and ESPN):

    python3 research_and_backtests/cfb_weekly_diagnostics_check.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cfb_working_schedule import (              # noqa: E402
    load_stat_history, tune_stat_weights, fetch_live_cfb_schedule,
    fetch_all_teamrankings_stats, fetch_espn_team_directory, fetch_espn_power_index,
    fetch_bcftoys_ratings, fetch_cfbd_advanced_stats, record_completed_games,
    stat_vote_model_pick, _live_stat_lean, build_matchup_forecast,
    _STAT_SIGNAL_SPECS,
)
import pandas as pd

import cfb_fei_margin_check      # noqa: E402 -- reused as-is, see part 2 below

SEASON_YEAR = 2026


# ======================================================================
# PART 1: this week's live games -- pick, risk flag, both kinds of margin
# ======================================================================
def build_live_stats_lookup(season_year):
    """Mirrors main()'s own real data-pull/merge pipeline in
    cfb_working_schedule.py for the sources the model pick + forecast
    engine actually use (TeamRankings, ESPN FPI/efficiency, bcftoys
    FEI/F+, CFBD advanced stats). Intentionally skips QBR and the
    per-team TFL/time-of-possession/FG% pull -- build_matchup_forecast()
    doesn't use those fields at all (see its own factors{} block), and
    this script never renders the PDF, so pulling them would just be
    slower for no real benefit here."""
    stats_lookup = fetch_all_teamrankings_stats()

    team_directory = fetch_espn_team_directory()
    schedule_df, week_number, season_year_live = fetch_live_cfb_schedule()
    fpi_lookup = fetch_espn_power_index(season_year_live, week_number, team_directory)
    fpi_rows = [{'Clean_Name': name, 'FPI': v.get('FPI'), 'Off_Eff': v.get('Off_Eff'), 'Def_Eff': v.get('Def_Eff')}
                for name, v in fpi_lookup.items()]
    if fpi_rows:
        stats_lookup = pd.merge(stats_lookup, pd.DataFrame(fpi_rows), on='Clean_Name', how='outer')

    bcftoys_df, _ = fetch_bcftoys_ratings(season_year_live)
    if not bcftoys_df.empty:
        stats_lookup = pd.merge(stats_lookup, bcftoys_df, on='Clean_Name', how='outer')

    cfbd_df, _ = fetch_cfbd_advanced_stats(season_year_live)
    if not cfbd_df.empty:
        stats_lookup = pd.merge(stats_lookup, cfbd_df, on='Clean_Name', how='outer')

    # Same belt-and-suspenders dedup guard as main() -- a duplicate
    # Clean_Name from any source turns .loc[team] into a multi-row
    # DataFrame instead of a Series for every downstream .get() call.
    dup_names = stats_lookup['Clean_Name'][stats_lookup['Clean_Name'].duplicated(keep=False)].unique()
    if len(dup_names):
        stats_lookup = stats_lookup.groupby('Clean_Name', as_index=False).first()
    stats_lookup.set_index('Clean_Name', inplace=True)
    return stats_lookup, schedule_df, week_number, season_year_live


def _pick_is_risky(pick_side, away_ts, home_ts):
    """Identical logic to the live PDF's _pick_is_risky() closure in
    cfb_working_schedule.py -- kept in sync by hand since it's defined
    inline there as a closure and can't be imported directly."""
    if pick_side is None:
        return False
    away_sacks = away_ts.get('Def_Sacks_PG') if hasattr(away_ts, 'get') else None
    home_sacks = home_ts.get('Def_Sacks_PG') if hasattr(home_ts, 'get') else None
    lean = _live_stat_lean(away_sacks, home_sacks, True)
    if lean is None:
        return False
    sacks_side = 'away' if lean == 1 else 'home'
    return sacks_side != pick_side


def _raw_margin(away_ts, home_ts, key):
    try:
        av, hv = float(away_ts.get(key)), float(home_ts.get(key))
    except (TypeError, ValueError):
        return None
    return abs(av - hv)


# Same exact boundaries as cfb_fei_margin_check.py's own `edges` (kept in
# sync by hand, same convention as _pick_is_risky() above) -- short labels
# here since these get printed inline next to each game, not as a report
# section header.
MARGIN_EDGES = [(0.0, 0.15, "very narrow"), (0.15, 0.35, "narrow"),
                 (0.35, 0.70, "moderate"), (0.70, 999.0, "wide")]


def compute_margin_bucket_stats(history, included_keys, weights_by_key, stats_lookup, margin_key):
    """Real historical miss rate for each margin bucket (very narrow/
    narrow/moderate/wide) of the given stat (FEI or F+), computed the exact
    same way cfb_fei_margin_check.py's own bucket table is -- every decided
    stat-vote game, TODAY's current rating for both teams (same disclosed
    post-hoc caveat as that script), bucketed by the real gap between them.
    Returns {bucket_label: (n, misses)}."""
    buckets = {label: [0, 0] for _, _, label in MARGIN_EDGES}  # [n, misses]
    for game in history["games"].values():
        votes = game.get("votes", {})
        score = sum(weights_by_key.get(k, 0) * votes[k] for k in included_keys if k in votes)
        if score == 0:
            continue
        is_miss = score < 0
        winner, loser = game.get("winner"), game.get("loser")
        if winner not in stats_lookup.index or loser not in stats_lookup.index:
            continue
        w_ts, l_ts = stats_lookup.loc[winner], stats_lookup.loc[loser]
        if isinstance(w_ts, pd.DataFrame):
            w_ts = w_ts.iloc[0]
        if isinstance(l_ts, pd.DataFrame):
            l_ts = l_ts.iloc[0]
        margin = _raw_margin(w_ts, l_ts, margin_key)
        if margin is None:
            continue
        label = cfb_fei_margin_check.bucket_label(margin, MARGIN_EDGES)
        if label not in buckets:
            continue
        buckets[label][0] += 1
        buckets[label][1] += 1 if is_miss else 0
    return {label: tuple(v) for label, v in buckets.items()}


def _margin_with_bucket(margin, bucket_stats):
    """Formats a margin value with its historical bucket label + miss rate
    in parens, e.g. '0.160 (narrow, 14.3%)' -- per request, right on the
    line with this week's games so you don't have to cross-reference the
    separate margin-check report to see whether a game's gap is one that's
    historically missed more or less."""
    if margin is None:
        return "n/a"
    label = cfb_fei_margin_check.bucket_label(margin, MARGIN_EDGES)
    n, misses = bucket_stats.get(label, (0, 0))
    if n == 0:
        return f"{margin:.3f} ({label}, n/a)"
    rate = misses / n * 100
    return f"{margin:.3f} ({label}, {rate:.1f}% miss)"


def print_this_weeks_games(included_stats, included_keys, weights_by_key):
    print("Pulling this week's live schedule + real stats (TeamRankings, ESPN FPI, bcftoys, CFBD)...")
    stats_lookup, schedule_df, week_number, season_year_live = build_live_stats_lookup(SEASON_YEAR)
    if schedule_df.empty:
        print("Live schedule came back empty -- nothing to check.")
        return
    print(f" -> week {week_number}, {len(schedule_df)} scheduled game(s)\n")

    print("Computing real historical miss rate by margin bucket for FEI and F+ (per request, 2026-09-22)...")
    history = load_stat_history()
    fei_bucket_stats = compute_margin_bucket_stats(history, included_keys, weights_by_key, stats_lookup, "FEI")
    fplus_bucket_stats = compute_margin_bucket_stats(history, included_keys, weights_by_key, stats_lookup, "F+")

    print("\n=== THIS WEEK'S GAMES: pick, risk flag, and both kinds of 'margin' ===")
    print("(FEI/F+ margin = raw gap between the two teams' current rating, now shown WITH its historical bucket "
          "and that bucket's real miss rate across every decided game so far, e.g. '0.160 (narrow, 14.3% miss)' "
          "-- same buckets as cfb_fei_margin_check.py's own report. Win-prob margin = the separate, UNVALIDATED "
          "forecast engine's win probability minus 50, shown WITH the team it favors (e.g. '+7.2 pts for Coastal "
          "Carolina'). The 'pick' column is the tracked, backtested stat-vote model (FEI/F+/Off_Havoc right now) "
          "-- the forecast engine is a different model built on different inputs (FPI, efficiency, scoring, "
          "yardage, turnovers, home-field) and has never been backtested, so it can and sometimes will favor the "
          "OTHER team from the pick; when that happens this prints '[forecast engine disagrees with the pick]' "
          "explicitly. REMINDER (also tested, 2026-09-22): a narrow FEI/F+ margin is a real but WEAK, standalone "
          "lean -- it does NOT compound with the sacks flag (narrow+sacks-disagree missed LESS than wide+sacks-"
          "disagree, 30% vs 50%, small n), so it's shown for visibility, not as a second thing to stack onto the "
          "orange flag.)\n")

    any_flagged = False
    for _, row in schedule_df.iterrows():
        if row.get("Completed"):
            continue  # already decided -- nothing to flag
        away, home = row.get("Away_Team"), row.get("Home_Team")
        if away not in stats_lookup.index or home not in stats_lookup.index:
            continue
        away_ts, home_ts = stats_lookup.loc[away], stats_lookup.loc[home]
        if isinstance(away_ts, pd.DataFrame):
            away_ts = away_ts.iloc[0]
        if isinstance(home_ts, pd.DataFrame):
            home_ts = home_ts.iloc[0]

        pick_side = stat_vote_model_pick(away_ts, home_ts, included_stats)
        pick_team = {"away": away, "home": home, None: "(no decided pick)"}[pick_side]
        risky = _pick_is_risky(pick_side, away_ts, home_ts)

        fei_margin = _raw_margin(away_ts, home_ts, "FEI")
        fplus_margin = _raw_margin(away_ts, home_ts, "F+")

        try:
            forecast = build_matchup_forecast(away, home, away_ts, home_ts)
        except Exception:
            forecast = None
        win_prob_margin = None
        forecast_favors_pick = None
        if forecast:
            favored_prob = max(forecast["home_win_prob"], forecast["away_win_prob"]) * 100
            win_prob_margin = favored_prob - 50.0
            # Print which team the forecast favors, not just the margin. The stat-vote
            # model (backtested) and the forecast engine (hand-weighted, not backtested)
            # use different inputs and can disagree, e.g. Liberty @ Coastal Carolina.
            if pick_team in (away, home):
                forecast_favors_pick = (forecast["favored_team"] == pick_team)

        flag_str = "*** FLAGGED (sacks disagrees) ***" if risky else ""
        if risky:
            any_flagged = True
        fei_str = _margin_with_bucket(fei_margin, fei_bucket_stats)
        fplus_str = _margin_with_bucket(fplus_margin, fplus_bucket_stats)
        if win_prob_margin is not None:
            wp_str = f"{win_prob_margin:+.1f} pts for {forecast['favored_team']}"
        else:
            wp_str = "n/a"
        forecast_note = ""
        if forecast_favors_pick is False:
            forecast_note = "  [forecast engine disagrees with the pick]"
        print(f"  {away} @ {home:24s} pick={pick_team:22s}\n"
              f"      FEI margin={fei_str:28s} F+ margin={fplus_str:28s}\n"
              f"      win-prob margin={wp_str:26s} {flag_str}{forecast_note}")

    if not any_flagged:
        print("\n  No games flagged this week (Def Sacks/Game agrees with the pick, or has no data, everywhere).")
    print()


# ======================================================================
# PART 2: re-run the sacks / FEI-margin checks fresh (reuses the already-
# tested logic in cfb_fei_margin_check.py directly -- not copied/redone)
# ======================================================================
def rerun_margin_and_sacks_checks():
    print("=" * 78)
    print("RE-RUNNING THE FEI/F+ MARGIN + SACKS COMPOUND CHECK (fresh data)")
    print("=" * 78)
    cfb_fei_margin_check.main()
    print()


# ======================================================================
# PART 3: scan EVERY stat (not just sacks) for a similarly clean
# agree/disagree-with-the-pick split, using only the stored vote history
# (no live data needed for this part).
# ======================================================================
def compute_stat_agreement_breakdown(history, included_keys, weights, stat_key):
    """Generalizes compute_sacks_agreement_breakdown() in
    cfb_working_schedule.py (same exact logic -- model_pick and
    <stat>_favors compared as TEAM NAMES, not raw vote signs) to any
    stat key, so every stat can be scanned the same correct way sacks
    was, instead of only ever checking sacks by hand again."""
    agree_hits = agree_n = disagree_hits = disagree_n = 0
    for game in history["games"].values():
        votes = game.get("votes", {})
        score = sum(weights.get(k, 0) * votes[k] for k in included_keys if k in votes)
        if score == 0:
            continue
        winner, loser = game.get("winner"), game.get("loser")
        model_pick = loser if score < 0 else winner
        is_hit = (model_pick == winner)
        stat_vote = votes.get(stat_key)
        stat_favors = None if stat_vote is None else (winner if stat_vote == 1 else loser)
        if stat_favors is None or stat_favors == model_pick:
            agree_n += 1
            agree_hits += 1 if is_hit else 0
        else:
            disagree_n += 1
            disagree_hits += 1 if is_hit else 0
    return {"agree": (agree_hits, agree_n), "disagree": (disagree_hits, disagree_n)}


def scan_all_stats_for_clean_splits(included_keys, weights_by_key):
    print("=" * 78)
    print("SCAN: every stat's agree/disagree-with-the-pick split (not just sacks)")
    print("=" * 78)
    print("Same test that found the sacks signal, run against every stat this project tracks. Sorted by the "
          "gap between the 'agrees' hit rate and the 'disagrees' hit rate -- a big gap with real n on both "
          "sides is what a new signal like sacks would look like. Small-n rows are still shown, just don't "
          "trust them yet.\n")

    history = load_stat_history()
    results = []
    for _, key, _hib in _STAT_SIGNAL_SPECS:
        breakdown = compute_stat_agreement_breakdown(history, included_keys, weights_by_key, key)
        a_hits, a_n = breakdown["agree"]
        d_hits, d_n = breakdown["disagree"]
        if a_n < 3 or d_n < 3:
            continue  # not enough real data on one side to say anything
        a_rate = a_hits / a_n * 100
        d_rate = d_hits / d_n * 100
        results.append((key, a_rate, a_n, d_rate, d_n, a_rate - d_rate))

    results.sort(key=lambda r: r[5], reverse=True)
    print(f"{'Stat':32s} {'Agree hit%':>12s} {'(n)':>5s}   {'Disagree hit%':>14s} {'(n)':>5s}   {'gap':>7s}  in model?")
    for key, a_rate, a_n, d_rate, d_n, gap in results:
        in_model = "yes" if key in included_keys else ""
        marker = " <-- Def_Sacks_PG (known baseline)" if key == "Def_Sacks_PG" else ""
        print(f"  {key:30s} {a_rate:10.1f}%  ({a_n:3d})   {d_rate:12.1f}%  ({d_n:3d})   {gap:+6.1f}  {in_model:>3s}{marker}")
    if not results:
        print("  Not enough decided games with real data yet for any stat to clear the n>=3-per-bucket bar.")
    print("\n(A gap this large with these n's could still be small-sample noise -- this is a scan to flag "
          "candidates for a real look, not a finished result.)\n")


def main():
    history = load_stat_history()
    included_stats, acc, correct, decided, total = tune_stat_weights(history)
    weights_by_key = {key: weight for _, key, weight, _, _ in included_stats}
    included_keys = [key for _, key, _, _, _ in included_stats]
    print(f"Current tuned model: {included_keys} -> {correct}/{decided} = {acc*100:.1f}% on {total} games\n")

    print_this_weeks_games(included_stats, included_keys, weights_by_key)
    scan_all_stats_for_clean_splits(included_keys, weights_by_key)
    rerun_margin_and_sacks_checks()


if __name__ == "__main__":
    main()
