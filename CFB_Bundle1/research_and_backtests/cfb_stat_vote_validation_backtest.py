"""
Validates the CFB report's stat-weighted win prediction model (currently:
FEI, F+, and Off Havoc Rate -- see "STATS THE MODEL WEIGHTS" on the PDF)
against several REAL, COMPLETE past seasons, instead of just the single
in-progress season (48 games so far in 2026) the live report backtests
against every time it runs.

WHY THE LIVE 87.5% NUMBER NEEDS A SECOND LOOK
  1. Small sample: 48 games, one season.
  2. In-sample: tune_stat_weights() in cfb_working_schedule.py picks WHICH
     stats to include (greedy forward-selection, whatever combination
     scores highest) using the SAME games it then reports accuracy on.
     The 48 games that picked "FEI, F+, Off Havoc Rate" as the 3 best
     stats are the exact same 48 games "42/48 = 87.5%" is measured against.
     That's not a fair test of whether the pick holds up on games it
     didn't already see -- it's closer to grading your own open-book exam.

WHAT THIS SCRIPT DOES INSTEAD: leave-one-season-out cross-validation.
Pulls SEASONS (below) of real completed games and real per-season FEI/F+
(bcftoys.com) and CFBD advanced stats. For every test season, the stat
weights are tuned using ONLY the OTHER seasons' real games (tune_stat_weights
and _backtest_accuracy are imported directly from cfb_working_schedule.py --
this is the exact same model, not a reimplementation), then scored on the
held-out season's real games -- a season the weights never got to see. A
model that's mostly overfitting a small recent sample will fall apart here;
a model finding something real should hold up close to the live number.

A REAL, DISCLOSED LIMIT ON HOW FAR THIS GOES: this is NOT the same kind of
week-by-week walk-forward the NFL project's nfl_winprob_calibration_backtest.py
runs. That was possible there because nflverse publishes real play-by-play
for any cutoff date, so "stats as of the Tuesday before week N" is a real,
exact snapshot. FEI/F+ (bcftoys.com) only publish CURRENT ratings -- for a
past season, "current" means that season's FINAL, full-season rating, not
a week-by-week snapshot; there is no historical week-by-week FEI/F+ archive
to pull. So this script necessarily evaluates each season using that
season's own END-OF-SEASON FEI/F+/Off-Havoc-Rate values against that
season's own games -- the same within-season limitation the LIVE report
already has today (it also scores every game using today's current-
season-to-date stats, not "as of that specific game" stats -- that's a
separate, smaller-scope issue from the one this script fixes). What this
script DOES genuinely fix is the cross-season leakage: the weights for a
held-out season are tuned using ZERO games from that season.

ANOTHER REAL, DISCLOSED LIMIT: only stats bcftoys/CFBD publish per-season
are available historically through this path -- TeamRankings/ESPN-only
stats the live model could also draw on this season (QBR, FPI, raw yards/
game, 3rd-down%, red-zone%, sacks, turnover margin) aren't pulled here,
because those sources don't expose a clean "give me season Y's numbers"
historical endpoint the way bcftoys/CFBD do. The real, available subset
(FEI, F+, OF+/DF+/OFEI/DFEI, NSR/OSR/DSR, and the full CFBD advanced-stats
set: PPA, stuff rate, havoc rate, line/2nd-level/open-field yards, power
success, success rate, explosiveness -- ~25 real candidate stats) is
large enough to be a genuine test of whether FEI/F+/Off-Havoc-Rate keep
getting selected on their own merits, or whether some other combination
in that same pool would have scored just as well.

Run this locally (needs a real CFBD_API_KEY -- already set in
cfb_working_schedule.py -- and real network access to bcftoys.com and
api.collegefootballdata.com):

    python3 research_and_backtests/cfb_stat_vote_validation_backtest.py
"""
import os
import sys
import time
import requests
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cfb_working_schedule import (         # noqa: E402  (import after sys.path fix, real reuse of the live model's own code, not a copy)
    clean_team_name,
    fetch_bcftoys_ratings,
    fetch_cfbd_advanced_stats,
    _stat_vote,
    _STAT_SIGNAL_SPECS,
    tune_stat_weights,
    _backtest_accuracy,
    CFBD_API_KEY,
    _CFBD_BASE,
)

# Real, complete past seasons -- 2026 is excluded (still in progress, not a
# fair held-out season yet). Five full FBS seasons is roughly 4,000+ real
# games once both-teams-have-stats filtering is applied below -- a much
# bigger, more honest sample than the live report's current 48.
SEASONS = [2021, 2022, 2023, 2024, 2025]


def fetch_cfbd_games(season_year):
    """Pulls every real REGULAR-season game CFBD has on record for a given
    year, with real final scores. Returns a list of dicts: away, home,
    away_score, home_score, event_id (CFBD's own numeric game id, used the
    same way ESPN's Event_Id is used in cfb_stat_history.json -- to key
    each game uniquely). Only games CFBD marks 'completed' with real
    non-null scores on both sides are returned; postponed/cancelled/future
    games are skipped, not guessed."""
    if not CFBD_API_KEY:
        print(" -> ⚠ No CFBD_API_KEY set -- can't pull real historical games without it.")
        return []
    url = f"{_CFBD_BASE}/games"
    headers = {"Authorization": f"Bearer {CFBD_API_KEY}", "Accept": "application/json"}
    try:
        resp = requests.get(url, headers=headers, params={"year": season_year, "seasonType": "regular"}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f" -> ⚠ CFBD games pull failed for {season_year} ({e}).")
        return []

    games = []
    for g in data:
        if not g.get("completed"):
            continue
        away_pts, home_pts = g.get("awayPoints"), g.get("homePoints")
        if away_pts is None or home_pts is None or away_pts == home_pts:
            continue  # no real final score on one side, or an unresolved tie -- skip rather than guess
        games.append({
            "event_id": f"cfbd_{g.get('id')}",
            "away": clean_team_name(g.get("awayTeam")),
            "home": clean_team_name(g.get("homeTeam")),
            "away_score": away_pts,
            "home_score": home_pts,
        })
    return games


def build_season_history(season_year):
    """Pulls one real season's bcftoys FEI/F+ + CFBD advanced stats and
    real completed games, and assembles a {"games": {...}} dict in the
    EXACT same shape cfb_stat_history.json uses (event_id -> {away, home,
    winner, loser, votes}) by running the real _stat_vote() function
    (imported, not reimplemented) over every stat in _STAT_SIGNAL_SPECS
    that bcftoys/CFBD actually publish. Games where either team has no
    real matched stats row this season are skipped (mirrors the live
    report's own known_teams filter in main())."""
    print(f"  Pulling {season_year}: bcftoys F+/FEI/DSR...")
    bcftoys_df, _ = fetch_bcftoys_ratings(season_year)
    time.sleep(1)  # polite pause between real bcftoys page fetches, same courtesy the live script already uses
    print(f"  Pulling {season_year}: CFBD advanced stats...")
    cfbd_df, _ = fetch_cfbd_advanced_stats(season_year)

    if bcftoys_df.empty and cfbd_df.empty:
        print(f"  -> ⚠ No real stats came back for {season_year} at all -- skipping this season entirely "
              f"rather than scoring games against nothing.")
        return {"games": {}}, 0

    stats_lookup = bcftoys_df if cfbd_df.empty else (
        cfbd_df if bcftoys_df.empty else pd.merge(bcftoys_df.reset_index(), cfbd_df, on="Clean_Name", how="outer").set_index("Clean_Name")
    )
    if "Clean_Name" in stats_lookup.columns:
        stats_lookup = stats_lookup.set_index("Clean_Name")
    stats_lookup = stats_lookup[~stats_lookup.index.duplicated(keep="first")]

    print(f"  Pulling {season_year}: real completed games...")
    games = fetch_cfbd_games(season_year)

    history = {"games": {}}
    skipped_no_stats = 0
    for g in games:
        away, home = g["away"], g["home"]
        if away not in stats_lookup.index or home not in stats_lookup.index:
            skipped_no_stats += 1
            continue
        winner = away if g["away_score"] > g["home_score"] else home
        loser = home if winner == away else away
        winner_ts, loser_ts = stats_lookup.loc[winner], stats_lookup.loc[home if winner == away else away]
        if isinstance(winner_ts, pd.DataFrame):
            winner_ts = winner_ts.iloc[0]
        if isinstance(loser_ts, pd.DataFrame):
            loser_ts = loser_ts.iloc[0]

        votes = {}
        for _label, key, higher_is_better in _STAT_SIGNAL_SPECS:
            wv = winner_ts.get(key) if hasattr(winner_ts, "get") else None
            lv = loser_ts.get(key) if hasattr(loser_ts, "get") else None
            vote = _stat_vote(wv, lv, higher_is_better)
            if vote is not None:
                votes[key] = vote

        history["games"][g["event_id"]] = {
            "season": season_year, "away": away, "home": home,
            "winner": winner, "loser": loser, "votes": votes,
        }

    real_game_count = len(history["games"])
    print(f"  -> {season_year}: {real_game_count} real game(s) with stats on both sides "
          f"({skipped_no_stats} real game(s) skipped -- one side had no matched stats row).")
    return history, real_game_count


def _pooled(histories, exclude_season=None):
    """Merges several seasons' {"games": {...}} dicts into one pooled
    history, optionally leaving one season's games out entirely -- this IS
    the leave-one-season-out training set construction: excluding a
    season here means its games are never seen by tune_stat_weights()."""
    pooled = {"games": {}}
    for season, h in histories.items():
        if season == exclude_season:
            continue
        pooled["games"].update(h["games"])
    return pooled


def run_validation(histories):
    """The real leave-one-season-out loop. For each real season present in
    `histories`, trains (tune_stat_weights) on every OTHER season pooled
    together, then scores (_backtest_accuracy) on the held-out season
    alone. Also computes the "in-sample" number (train and test on the
    SAME single season) for direct side-by-side comparison, and a naive
    baseline (weights fixed at the live model's OWN current picks --
    FEI/F+/Off Havoc Rate, equal-weighted at their held-out win rate) so
    a reader can see all three numbers together per season."""
    results = []
    for season in sorted(histories.keys()):
        test_history = histories[season]
        if not test_history["games"]:
            continue
        train_history = _pooled(histories, exclude_season=season)
        # Real, direct no-leakage check: the training pool must contain
        # NONE of this season's own event ids.
        overlap = set(train_history["games"].keys()) & set(test_history["games"].keys())
        assert not overlap, f"LEAKAGE BUG: {len(overlap)} game(s) from {season} leaked into its own training pool"

        included_train, _acc_train, _c, _d, _t = tune_stat_weights(train_history)
        weights_train = {key: weight for _label, key, weight, _wr, _n in included_train}
        keys_train = [key for _label, key, _w, _wr, _n in included_train]
        ho_correct, ho_decided, ho_total = _backtest_accuracy(test_history, keys_train, weights_train)

        included_insample, _acc_is, is_correct, is_decided, is_total = tune_stat_weights(test_history)

        results.append({
            "season": season,
            "held_out_stats": [k for _l, k, _w, _wr, _n in included_train],
            "held_out_correct": ho_correct, "held_out_decided": ho_decided, "held_out_total": ho_total,
            "insample_stats": [k for _l, k, _w, _wr, _n in included_insample],
            "insample_correct": is_correct, "insample_decided": is_decided, "insample_total": is_total,
        })
    return results


def print_report(results):
    print("\n" + "=" * 78)
    print("CFB STAT-VOTE MODEL: LEAVE-ONE-SEASON-OUT VALIDATION (real, held-out)")
    print("=" * 78)
    pooled_ho_correct = pooled_ho_decided = 0
    pooled_is_correct = pooled_is_decided = 0
    for r in results:
        ho_acc = r["held_out_correct"] / r["held_out_decided"] * 100 if r["held_out_decided"] else 0.0
        is_acc = r["insample_correct"] / r["insample_decided"] * 100 if r["insample_decided"] else 0.0
        print(f"\n{r['season']} ({r['held_out_total']} real games):")
        print(f"  HELD-OUT (weights tuned on the OTHER {len(SEASONS)-1} seasons only): "
              f"{r['held_out_correct']}/{r['held_out_decided']} = {ho_acc:.1f}%  "
              f"[stats used: {', '.join(r['held_out_stats']) or 'none cleared the bar'}]")
        print(f"  IN-SAMPLE (weights tuned on {r['season']} itself, live report's own method): "
              f"{r['insample_correct']}/{r['insample_decided']} = {is_acc:.1f}%  "
              f"[stats used: {', '.join(r['insample_stats']) or 'none cleared the bar'}]")
        pooled_ho_correct += r["held_out_correct"]; pooled_ho_decided += r["held_out_decided"]
        pooled_is_correct += r["insample_correct"]; pooled_is_decided += r["insample_decided"]

    print("\n" + "-" * 78)
    ho_total_acc = pooled_ho_correct / pooled_ho_decided * 100 if pooled_ho_decided else 0.0
    is_total_acc = pooled_is_correct / pooled_is_decided * 100 if pooled_is_decided else 0.0
    print(f"POOLED HELD-OUT ACCURACY across all {len(results)} seasons: "
          f"{pooled_ho_correct}/{pooled_ho_decided} = {ho_total_acc:.1f}%")
    print(f"POOLED IN-SAMPLE ACCURACY (for comparison, same-season-picks-and-scores method): "
          f"{pooled_is_correct}/{pooled_is_decided} = {is_total_acc:.1f}%")
    gap = is_total_acc - ho_total_acc
    print(f"\nOVERFITTING GAP (in-sample minus held-out): {gap:+.1f} points.")
    if gap > 10:
        print("  -> Large gap: the in-sample number is meaningfully inflated by picking stats and")
        print("     scoring them on the same games. Trust the held-out number, not the live report's")
        print("     current single-season one, as the honest read on how well this model generalizes.")
    elif gap > 3:
        print("  -> Modest gap: some real overfitting, but the model is finding a real signal too --")
        print("     the held-out number is the honest one to quote, the in-sample one is optimistic.")
    else:
        print("  -> Small gap: the live report's in-sample number is a reasonably honest estimate of")
        print("     real out-of-sample performance for this model.")
    print("=" * 78)


def main():
    histories = {}
    for season in SEASONS:
        h, n = build_season_history(season)
        histories[season] = h
    results = run_validation(histories)
    if not results:
        print("No real season had usable data -- nothing to validate. Check CFBD_API_KEY and network access.")
        return
    print_report(results)


if __name__ == "__main__":
    main()
