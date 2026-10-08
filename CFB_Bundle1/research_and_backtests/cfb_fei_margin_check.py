"""
Tests a real, different hypothesis than the earlier gap checks: not "which
side did FEI/F+ favor" (that's already baked into every pick), but "how
CLOSE were the two teams' raw FEI/F+ numbers" -- because the stat-vote
model throws that away entirely. tune_stat_weights()/_backtest_accuracy()
in cfb_working_schedule.py only ever look at the SIGN of each stat's vote
(+1 if a team leads it, -1 if not) -- a team leading FEI by 0.005 counts
exactly the same as a team leading it by 2.5. If games with a narrow raw
FEI/F+ margin miss more often than games with a wide one, that's a real,
fixable blind spot in how the model is built (magnitude-blind, sign-only
voting) -- not just "the model doesn't have that data," which the earlier
scripts checked and ruled out for stuff rate/SOS.

WHAT THIS SCRIPT DOES: for every game on record (not just the 6 misses),
pulls today's real current FEI/F+ values for both teams, computes the raw
margin between them, and checks whether the model's real hit rate is
different for narrow-margin games vs wide-margin games. Also checks the
specific compound idea: among narrow-margin games, does Def
Sacks/Game disagreeing with the FEI/F+ pick predict a miss more often
than when it agrees.

REAL, DISCLOSED LIMIT: same one as the other post-hoc scripts -- this uses
TODAY's current FEI/F+ (bcftoys doesn't publish a historical week-by-week
archive, only current/final-season values), not a frozen snapshot from
each game's actual date. Fine for looking at margin-size PATTERNS across
many games, not a claim about the exact number on any one game day.

Run this locally (needs real network access to bcftoys.com):

    python3 research_and_backtests/cfb_fei_margin_check.py
"""
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cfb_working_schedule import load_stat_history, tune_stat_weights, fetch_bcftoys_ratings

SEASON_YEAR = 2026


def real_value(ts, key):
    if ts is None or not hasattr(ts, "get"):
        return None
    v = ts.get(key)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


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
    print(f"Current model: {included_keys} -> {correct}/{decided} = {acc*100:.1f}% on {total} games\n")

    print("Pulling fresh bcftoys F+/FEI (today's current values -- see docstring caveat)...")
    bcftoys_df, _ = fetch_bcftoys_ratings(SEASON_YEAR)
    # NOTE: fetch_bcftoys_ratings()'s own docstring
    # claims its return is "indexed by Clean_Name", but the function
    # actually builds it with groupby('Clean_Name', as_index=False) --
    # Clean_Name stays a plain COLUMN, not the index. Every .loc[team_name]
    # lookup below was silently hitting a KeyError (caught, skipped) for
    # every single game. Setting the real index here instead of trusting
    # the docstring.
    if "Clean_Name" in bcftoys_df.columns:
        bcftoys_df = bcftoys_df.set_index("Clean_Name")
    print(f" -> {len(bcftoys_df)} teams\n")

    rows = []
    for game in history["games"].values():
        votes = game.get("votes", {})
        score = sum(weights_by_key.get(k, 0) * votes[k] for k in included_keys if k in votes)
        if score == 0:
            continue  # not a decided pick at all -- excluded the same way _backtest_accuracy excludes it
        is_miss = score < 0

        winner, loser = game.get("winner"), game.get("loser")
        try:
            w_ts, l_ts = bcftoys_df.loc[winner], bcftoys_df.loc[loser]
        except KeyError:
            continue
        # Defensive dedup guard (same real issue the live report already
        # guards against elsewhere -- a duplicate Clean_Name makes .loc[]
        # return a 2-row DataFrame instead of a Series).
        if isinstance(w_ts, pd.DataFrame):
            w_ts = w_ts.iloc[0]
        if isinstance(l_ts, pd.DataFrame):
            l_ts = l_ts.iloc[0]

        fei_margin = abs(real_value(w_ts, "FEI") - real_value(l_ts, "FEI")) if real_value(w_ts, "FEI") is not None and real_value(l_ts, "FEI") is not None else None
        fplus_margin = abs(real_value(w_ts, "F+") - real_value(l_ts, "F+")) if real_value(w_ts, "F+") is not None and real_value(l_ts, "F+") is not None else None

        # CORRECTED (2026-09-22 -- an earlier version of this compound
        # check mislabeled sacks_vote==+1 as "sacks agreed with the pick,"
        # which is wrong: sacks_vote is relative to the real WINNER, not
        # to whichever team the model picked. The two only mean the same
        # thing on a HIT (model_pick == winner). This block instead
        # computes sacks_agrees_with_pick the same, correct way
        # compute_sacks_agreement_breakdown() in cfb_working_schedule.py
        # does it -- by comparing which TEAM sacks favors to which TEAM
        # the model actually picked, not by the raw vote sign alone.
        model_pick = loser if is_miss else winner
        sacks_vote = votes.get("Def_Sacks_PG")
        sacks_favors = None if sacks_vote is None else (winner if sacks_vote == 1 else loser)
        sacks_agrees_with_pick = (sacks_favors is None) or (sacks_favors == model_pick)

        rows.append({
            "winner": winner, "loser": loser, "is_miss": is_miss,
            "fei_margin": fei_margin, "fplus_margin": fplus_margin,
            "sacks_agrees_with_pick": sacks_agrees_with_pick,
        })

    print(f"{len(rows)} real decided games matched to today's FEI/F+ values.\n")

    # ---- Real bucketed miss-rate check, by raw FEI margin ----
    edges = [(0.0, 0.15, "very narrow (<0.15)"), (0.15, 0.35, "narrow (0.15-0.35)"),
             (0.35, 0.70, "moderate (0.35-0.70)"), (0.70, 999, "wide (0.70+)")]
    for stat_name, key in [("FEI", "fei_margin"), ("F+", "fplus_margin")]:
        print(f"=== Real miss rate by raw {stat_name} margin bucket ===")
        buckets = {}
        for r in rows:
            m = r[key]
            if m is None:
                continue
            b = bucket_label(m, edges)
            buckets.setdefault(b, {"n": 0, "misses": 0})
            buckets[b]["n"] += 1
            buckets[b]["misses"] += 1 if r["is_miss"] else 0
        for lo, hi, label in edges:
            d = buckets.get(label, {"n": 0, "misses": 0})
            rate = d["misses"] / d["n"] * 100 if d["n"] else 0.0
            print(f"  {label:24s} n={d['n']:3d}  misses={d['misses']:2d}  miss rate={rate:5.1f}%")
        print()

    # ---- The specific compound idea: narrow FEI/F+ margin AND
    # Def Sacks/Game disagreeing with the model's PICK (not the winner --
    # see the sacks_agrees_with_pick fix above) -- does THAT combination
    # predict a miss more than narrow margin alone, or more than sacks
    # disagreement alone (regardless of margin)? The question is whether the effect only shows up with the 2 together,
    # so this checks the
    # full 2x2 (narrow vs wide margin) x (sacks agrees vs disagrees), not
    # just the narrow-margin slice, so the "together" claim can actually be
    # compared against each half alone.
    print("=== Compound check: does narrow FEI margin (<0.35) PLUS Def Sacks/Game disagreeing with the pick "
          "predict a miss better than either alone? ===\n")

    def _pct(hits_or_misses, n):
        return hits_or_misses / n * 100 if n else 0.0

    # Whole-dataset baselines first, so "together" has something real to beat.
    agree_all = [r for r in rows if r["sacks_agrees_with_pick"]]
    disagree_all = [r for r in rows if not r["sacks_agrees_with_pick"]]
    narrow_all = [r for r in rows if r["fei_margin"] is not None and r["fei_margin"] < 0.35]
    wide_all = [r for r in rows if r["fei_margin"] is not None and r["fei_margin"] >= 0.35]

    def _report(label, subset):
        n = len(subset)
        misses = sum(1 for r in subset if r["is_miss"])
        print(f"  {label:56s} n={n:3d}  misses={misses:2d}  miss rate={_pct(misses, n):5.1f}%")

    print("  -- Sacks alone (any margin) --")
    _report("Sacks AGREES with the pick (or no real data)", agree_all)
    _report("Sacks DISAGREES with the pick", disagree_all)
    print("\n  -- FEI margin alone (any sacks result) --")
    _report("Narrow FEI margin (<0.35)", narrow_all)
    _report("Wide FEI margin (0.35+)", wide_all)

    print("\n  -- The 2 together: narrow margin split by sacks agreement --")
    narrow_agree = [r for r in narrow_all if r["sacks_agrees_with_pick"]]
    narrow_disagree = [r for r in narrow_all if not r["sacks_agrees_with_pick"]]
    _report("Narrow margin AND sacks agrees (or no data)", narrow_agree)
    _report("Narrow margin AND sacks disagrees", narrow_disagree)

    print("\n  -- For comparison: wide margin split by sacks agreement --")
    wide_agree = [r for r in wide_all if r["sacks_agrees_with_pick"]]
    wide_disagree = [r for r in wide_all if not r["sacks_agrees_with_pick"]]
    _report("Wide margin AND sacks agrees (or no data)", wide_agree)
    _report("Wide margin AND sacks disagrees", wide_disagree)

    print("\n  Real read on 'the 2 together': if narrow+disagree's miss rate is meaningfully higher than BOTH "
          "sacks-disagree-alone and narrow-margin-alone, that's the 2-together effect. If "
          "narrow+disagree looks about the same as wide+disagree, the margin isn't adding anything real -- sacks "
          "disagreement alone is doing all the work.")

    print("\n(Small n in some buckets almost certainly -- read the counts, not just the percentages, before trusting any of this.)")


if __name__ == "__main__":
    main()
