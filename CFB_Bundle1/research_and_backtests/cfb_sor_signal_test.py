"""
Formal test: does adding SOR (Strength of Record) as a real weighted stat
to the tracked stat-vote model actually improve real backtested accuracy --
the exact same question already asked and answered (no) for Def Sacks/Game
(see cfb_miss_stat_gap_check.py / PROJECT_NOTES.md's "Def Sacks/Game flag"
section). This is that same test, run against SOR instead.

WHY THIS EXISTS: PROJECT_NOTES.md flagged SOR (pulled from ESPN's FPI feed,
field 'accomplishmentrank'/'accomplishment' -- see fetch_espn_power_index's
own real HONESTY NOTE for why the exact field isn't 100% ESPN-confirmed) as
a real, untested candidate: of 5 checkable misses this season, the team
with the better (lower) SOR number was the actual winner in 4/5. That's a
"here's what happened on the misses" finding, not "does it actually help
the model" -- this script answers that second question properly, the same
rigor every other candidate stat in this project gets.

METHOD:
  1. Load the real, persistent cfb_stat_history.json (95+ games, votes
     already recorded for every CURRENTLY tracked stat).
  2. Pull fresh CURRENT team stats (TeamRankings + bcftoys + CFBD, same as
     cfb_miss_stat_gap_check.py's build_current_stats_lookup) PLUS ESPN's
     power index specifically for SOR (fetch_espn_power_index) -- note SOR
     is NOT currently merged into main()'s own stats_lookup at all (only
     FPI/Off_Eff/Def_Eff make that merge -- confirmed by reading main()
     directly, 2026-09-29), so this script builds that merge itself just
     for this test rather than assuming it already exists anywhere.
  3. For every REAL historical game on record, computes a fresh SOR vote
     (winner's real SOR vs loser's real SOR, lower=better per the
     'accomplishmentrank' convention -- see the HONESTY NOTE below) using
     the exact same _stat_vote() function the real model itself uses for
     every other stat.
  4. Reports SOR's own standalone real win rate across every game where
     it's computable (not just the misses -- the first real, full-season
     version of the "4/5" finding).
  5. Runs tune_stat_weights() TWICE on the real history: once exactly as
     today (baseline, the real live model), and once on an augmented copy
     with SOR's freshly-computed vote injected into every game's votes
     dict as an additional real candidate -- then reports whether the
     greedy selector actually chooses to include SOR, and what happens to
     real backtested accuracy if it does.

REAL, DISCLOSED LIMITATION (same one cfb_miss_stat_gap_check.py already
has, and the same one PROJECT_NOTES.md's "current stats, not a frozen
snapshot" section discloses for every other post-hoc check in this
project): SOR was never recorded for these games when they were actually
played (it's not in _STAT_SIGNAL_SPECS yet, so record_completed_games()
never saved a vote for it) -- so every SOR vote here uses TODAY's current
SOR value for both teams, not a frozen day-of-game snapshot. Good enough
to see whether SOR carries real signal at all, not a perfectly clean
backtest. This is a real tradeoff already accepted everywhere else in this
project, not something new introduced here.

ANOTHER REAL LIMITATION: SOR's exact field identity isn't confirmed by
ESPN's own docs (fetch_espn_power_index tries 'accomplishmentrank' first,
falls back to 'accomplishment' if that team's entry doesn't have a rank --
these are two different real fields on two different scales, silently
mixed together team-by-team depending on which one ESPN actually returned
for them). This script assumes lower='accomplishmentrank' is better
(matches the rank convention every other '*rank' field in this project
already uses) -- if that assumption is wrong for teams that fell back to
the raw 'accomplishment' value instead, their vote could be backwards.
Flagged, not silently trusted.

IF THIS FINDS REAL SIGNAL: promoting SOR from "displayed" to "in the
model" needs one more real step this script deliberately does NOT do --
main()'s own stats_lookup merge only pulls FPI/Off_Eff/Def_Eff out of
fpi_lookup right now, SOR would need to be added to that merge (a few real
lines near "fpi_rows.append(...)" in main()) AND SOR added to
_STAT_SIGNAL_SPECS so record_completed_games() starts saving real votes
for it going forward. Left undone on purpose until this test's real result
says it's worth doing.

Run this locally (needs real network access to TeamRankings, bcftoys,
CFBD, and ESPN):

    python3 research_and_backtests/cfb_sor_signal_test.py
"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cfb_working_schedule import (              # noqa: E402
    load_stat_history, tune_stat_weights, _stat_vote,
    fetch_all_teamrankings_stats, fetch_bcftoys_ratings, fetch_cfbd_advanced_stats,
    fetch_espn_team_directory, fetch_espn_power_index, fetch_live_cfb_schedule,
)
import pandas as pd

SEASON_YEAR = 2026

# See the HONESTY NOTE above -- assumed True direction (lower SOR = better
# resume) per the 'accomplishmentrank' convention. Flip this to re-test the
# opposite assumption if the real result looks backwards/suspicious.
SOR_LOWER_IS_BETTER = True


def build_current_stats_lookup_with_sor():
    """Same real merge cfb_miss_stat_gap_check.py's build_current_stats_lookup()
    does (TeamRankings + bcftoys + CFBD), PLUS a real SOR column pulled
    fresh from ESPN's power index -- main()'s own stats_lookup does NOT
    currently include SOR at all (confirmed by reading main() directly),
    so this builds that merge itself, just for this test."""
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

    print("Pulling real live schedule (for the real current week number)...")
    _schedule_df, week_number, season_year = fetch_live_cfb_schedule()

    print("Pulling ESPN team directory + power index (real FPI/SOR)...")
    team_directory = fetch_espn_team_directory()
    fpi_lookup = fetch_espn_power_index(season_year or SEASON_YEAR, week_number, team_directory)
    sor_rows = [{"Clean_Name": name, "SOR": vals.get("SOR")} for name, vals in fpi_lookup.items()]
    n_with_sor = sum(1 for r in sor_rows if r["SOR"] is not None)
    print(f" -> {len(sor_rows)} teams from ESPN power index, {n_with_sor} with a real usable SOR value.")
    if sor_rows:
        stats_lookup = pd.merge(stats_lookup.reset_index() if stats_lookup.index.name == "Clean_Name" else stats_lookup,
                                 pd.DataFrame(sor_rows), on="Clean_Name", how="outer")

    if "Clean_Name" in stats_lookup.columns:
        stats_lookup = stats_lookup.set_index("Clean_Name")
    return stats_lookup[~stats_lookup.index.duplicated(keep="first")]


def compute_sor_votes(history, stats_lookup):
    """For every real game on record, computes a fresh SOR vote (winner vs
    loser, TODAY's real SOR values -- see the frozen-snapshot limitation in
    the module docstring). Returns (votes_by_event_id, n_scored, n_skipped)
    -- skipped covers a team missing from today's stats_lookup entirely, a
    missing/unusable SOR value on either side, or a real tie."""
    votes_by_event_id = {}
    n_skipped_no_team, n_skipped_no_sor, n_tie = 0, 0, 0
    for event_id, game in history["games"].items():
        winner, loser = game.get("winner"), game.get("loser")
        if winner not in stats_lookup.index or loser not in stats_lookup.index:
            n_skipped_no_team += 1
            continue
        w_ts, l_ts = stats_lookup.loc[winner], stats_lookup.loc[loser]
        if isinstance(w_ts, pd.DataFrame):
            w_ts = w_ts.iloc[0]
        if isinstance(l_ts, pd.DataFrame):
            l_ts = l_ts.iloc[0]
        w_sor, l_sor = w_ts.get("SOR"), l_ts.get("SOR")
        vote = _stat_vote(w_sor, l_sor, higher_is_better=not SOR_LOWER_IS_BETTER)
        if vote is None:
            if w_sor is None or l_sor is None or pd.isna(w_sor) or pd.isna(l_sor):
                n_skipped_no_sor += 1
            else:
                n_tie += 1
            continue
        votes_by_event_id[event_id] = vote
    n_scored = len(votes_by_event_id)
    print(f"Real SOR votes computed for {n_scored} of {len(history['games'])} real games "
          f"({n_skipped_no_team} skipped -- team not in today's stats, {n_skipped_no_sor} skipped -- "
          f"no real SOR value on one/both sides today, {n_tie} real ties).")
    return votes_by_event_id, n_scored


def main():
    history = load_stat_history()
    total_games = len(history["games"])
    print(f"Loaded real stat history: {total_games} games on record.\n")

    print("=== STEP 1: baseline -- today's real tracked model, unchanged ===")
    baseline_included, baseline_acc, baseline_correct, baseline_decided, _ = tune_stat_weights(history)
    baseline_keys = [key for _, key, _, _, _ in baseline_included]
    print(f"Real baseline model: {baseline_keys}")
    print(f"Real baseline accuracy: {baseline_correct}/{baseline_decided} = {baseline_acc*100:.1f}% "
          f"(of {total_games} total games on record)\n")

    print("=== STEP 2: pulling fresh real stats (TeamRankings/bcftoys/CFBD/ESPN) for SOR ===")
    stats_lookup = build_current_stats_lookup_with_sor()
    print()

    print("=== STEP 3: real standalone SOR win rate (every scoreable game, not just misses) ===")
    sor_votes, n_scored = compute_sor_votes(history, stats_lookup)
    if n_scored == 0:
        print("No real games had a usable SOR value on both sides today -- can't test this further.")
        return
    sor_hits = sum(1 for v in sor_votes.values() if v == 1)
    print(f"Real SOR standalone: {sor_hits}/{n_scored} = {sor_hits/n_scored*100:.1f}% "
          f"(assumption: lower SOR = better resume -- flip SOR_LOWER_IS_BETTER at the top of this file "
          f"and re-run if this comes back suspiciously low, e.g. well under 50%, which would suggest "
          f"the direction assumption is backwards)\n")

    print("=== STEP 4: does adding SOR as a real weighted candidate change the tuned model? ===")
    augmented_history = copy.deepcopy(history)
    for event_id, vote in sor_votes.items():
        augmented_history["games"][event_id]["votes"]["SOR"] = vote

    aug_included, aug_acc, aug_correct, aug_decided, _ = tune_stat_weights(augmented_history)
    aug_keys = [key for _, key, _, _, _ in aug_included]
    sor_was_picked = "SOR" in aug_keys
    print(f"With SOR available as a real candidate, the greedy selector's final stat set: {aug_keys}")
    print(f"SOR {'WAS' if sor_was_picked else 'was NOT'} selected into the real tuned model.")
    print(f"Accuracy with SOR available: {aug_correct}/{aug_decided} = {aug_acc*100:.1f}% "
          f"(baseline was {baseline_correct}/{baseline_decided} = {baseline_acc*100:.1f}%)\n")

    print("=== REAL VERDICT ===")
    if sor_was_picked and aug_acc > baseline_acc:
        print(f"SOR earned a real spot in the model and real accuracy improved "
              f"({baseline_acc*100:.1f}% -> {aug_acc*100:.1f}%). Worth promoting for real -- "
              f"see the module docstring's 'IF THIS FINDS REAL SIGNAL' section for the two remaining "
              f"real steps (stats_lookup merge in main(), add to _STAT_SIGNAL_SPECS).")
    elif sor_was_picked:
        print(f"SOR got selected but didn't actually move real accuracy "
              f"({baseline_acc*100:.1f}% -> {aug_acc*100:.1f}%) -- same shape as Def Sacks/Game's original "
              f"finding. Probably not worth promoting on this evidence alone.")
    else:
        print(f"SOR was NOT selected by the real greedy search at all -- the model found other stats "
              f"more useful. Same real conclusion as Def Sacks/Game: real signal on its own "
              f"({sor_hits}/{n_scored} = {sor_hits/n_scored*100:.1f}%), but not enough to earn a place "
              f"in the combined model over what's already there.")


if __name__ == "__main__":
    main()
