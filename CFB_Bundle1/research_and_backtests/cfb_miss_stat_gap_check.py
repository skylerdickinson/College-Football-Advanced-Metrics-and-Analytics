"""
For every game the CFB stat-vote model has picked WRONG so far this
season, shows the REAL, quantified GAP (not just "which side it favored")
between the winner's and loser's number on: (1) the stat(s) currently
weighted in the model, and (2) the strongest stats that favored the real
winner but aren't in the model -- most notably whichever stat(s) showed up
favoring the real winner in EVERY miss (a real, computed check, not
assumed -- see _find_universal_stats() below).

WHY THIS EXISTS: after finding that Def Sacks/Game favored the real winner
in all 6 of this season's misses so far, the natural next question is
"how big was that gap, every time -- something to actually watch for, not
just a yes/no." This script answers that with real numbers.

A REAL, DISCLOSED LIMIT: cfb_stat_history.json only stores each game's
+1/-1 VOTES, not the raw stat values that produced them (that's all the
model itself ever needed). So the raw gaps shown here are pulled from
TODAY's current season-to-date stats, not a preserved snapshot from the
exact day each game was played -- for teams that have played again since,
their season average has moved a little since that game. Good enough to
see real magnitude and direction, not a perfectly frozen game-day snapshot.

ANOTHER REAL LIMIT: 6 misses (or however many are on record right now) is
a very small sample to draw a hard "gap > X means trouble" threshold from.
This script reports the real numbers -- averages, ranges, how many of the
misses had a "large" gap by a couple of reasonable-sounding cutoffs -- but
deliberately stops short of declaring a rule. Treat it as "here's what
actually happened," not "here's a new stat to add to the model" (that
question -- does adding it actually improve real backtested accuracy --
is answered separately, and as of this writing the answer for Def Sacks/
Game specifically was no; see cfb_stat_history.json).

Run this locally (needs real network access to TeamRankings, bcftoys,
and CFBD):

    python3 research_and_backtests/cfb_miss_stat_gap_check.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cfb_working_schedule import (              # noqa: E402
    load_stat_history, tune_stat_weights, _STAT_SIGNAL_SPECS,
    fetch_all_teamrankings_stats, fetch_bcftoys_ratings, fetch_cfbd_advanced_stats,
)
import pandas as pd

SEASON_YEAR = 2026


def find_misses(history, included_keys, weights_by_key):
    """Real misses (score < 0), with the FULL (uncapped) set of stats that
    favored the real winner on each one -- not the PDF's own top-6-per-game
    cap, since a stat common to every miss could sit just past that cutoff."""
    misses = []
    for game in history["games"].values():
        votes = game.get("votes", {})
        score = sum(weights_by_key.get(k, 0) * votes[k] for k in included_keys if k in votes)
        if score < 0:
            favored = {k for k, v in votes.items() if v == 1}
            misses.append({
                "winner": game.get("winner"), "loser": game.get("loser"),
                "date": game.get("date"), "favored": favored,
            })
    return misses


def find_universal_stats(misses):
    """Real intersection: which stat(s), if any, favored the actual
    (upset) winner in EVERY recorded miss so far."""
    if not misses:
        return set()
    return set.intersection(*(m["favored"] for m in misses))


def build_current_stats_lookup():
    """Pulls today's TeamRankings + bcftoys + CFBD stats and merges them
    the same way main() does, so real raw values (not just +1/-1 votes)
    are available for the gap math below."""
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


def real_value(ts, key):
    if ts is None or not hasattr(ts, "get"):
        return None
    v = ts.get(key)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    history = load_stat_history()
    included_stats, acc, correct, decided, total = tune_stat_weights(history)
    weights_by_key = {key: weight for _, key, weight, _, _ in included_stats}
    included_keys = [key for _, key, _, _, _ in included_stats]
    label_by_key = {key: label for label, key, _ in _STAT_SIGNAL_SPECS}
    higher_is_better_by_key = {key: hib for _, key, hib in _STAT_SIGNAL_SPECS}

    misses = find_misses(history, included_keys, weights_by_key)
    if not misses:
        print("No real misses on record yet -- nothing to check.")
        return
    print(f"{len(misses)} real miss(es) on record. Current model: {included_keys} -> {correct}/{decided} = {acc*100:.1f}%\n")

    universal = find_universal_stats(misses)
    print("=== STAT(S) THAT FAVORED THE REAL (UPSET) WINNER IN EVERY SINGLE MISS ===")
    if universal:
        for k in sorted(universal):
            print(f"  {label_by_key.get(k, k)}  (currently in model: {k in included_keys})")
    else:
        print("  None this time -- no single stat has favored the winner in every recorded miss.")
    print()

    stats_lookup = build_current_stats_lookup()

    # Watch-list: whatever's universal across all misses, plus the model's
    # own included stats (useful to see how close those actually ran too).
    watch_keys = sorted(universal) + [k for k in included_keys if k not in universal]
    if not watch_keys:
        print("Nothing to compute real gaps for.")
        return

    print("=== REAL GAP (winner's value minus loser's value, sign-adjusted so POSITIVE always means "
          "'in the direction that favored the real winner') for each miss ===\n")
    gap_records = {k: [] for k in watch_keys}
    for m in misses:
        winner, loser = m["winner"], m["loser"]
        try:
            w_ts = stats_lookup.loc[winner]
            l_ts = stats_lookup.loc[loser]
        except KeyError:
            print(f"{winner} over {loser}: (couldn't match one or both teams to today's stats -- name mismatch, skipping)")
            continue
        if isinstance(w_ts, pd.DataFrame):
            w_ts = w_ts.iloc[0]
        if isinstance(l_ts, pd.DataFrame):
            l_ts = l_ts.iloc[0]

        print(f"{winner} over {loser} ({m['date']}):")
        for k in watch_keys:
            wv, lv = real_value(w_ts, k), real_value(l_ts, k)
            if wv is None or lv is None:
                print(f"    {label_by_key.get(k, k):32s} -- (no current real value for one side)")
                continue
            hib = higher_is_better_by_key.get(k, True)
            raw_gap = (wv - lv) if hib else (lv - wv)
            print(f"    {label_by_key.get(k, k):32s} winner={wv:.3f}  loser={lv:.3f}  "
                  f"real gap (in winner's favor) = {raw_gap:+.3f}")
            gap_records[k].append(raw_gap)
        print()

    print("=== SUMMARY: real gap size across all misses (small sample -- see caveat in the file's docstring) ===")
    for k in watch_keys:
        vals = gap_records[k]
        if not vals:
            continue
        avg = sum(vals) / len(vals)
        print(f"  {label_by_key.get(k, k):32s} n={len(vals)}  avg gap={avg:+.3f}  "
              f"min={min(vals):+.3f}  max={max(vals):+.3f}  "
              f"({sum(1 for v in vals if v > 0)}/{len(vals)} times the real winner led it at all)")


if __name__ == "__main__":
    main()
