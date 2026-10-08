"""
For every game the CFB stat-vote model picked WRONG so far this season,
checks whether the strongest overlapping "story" stats (Off/Def Stuff
Rate) and each team's strength of schedule (SOS/FPI) would have looked
any different -- or flagged the upset at all -- using REAL data AS OF
RIGHT BEFORE that specific game, instead of today's stats (which have
since absorbed that game's own result and possibly more games).

WHY THIS IS DIFFERENT FROM THE EARLIER GAP CHECK: cfb_miss_stat_gap_check.py
only had access to TODAY's cumulative season stats (the model's own vote
history doesn't store raw values, only +1/-1 votes -- see that file's
docstring). This script gets around that for the two sources that
actually support it: CFBD's /stats/season/advanced endpoint takes a real
startWeek/endWeek range, and ESPN's Power Index is published per-week --
so for Off/Def Stuff Rate (CFBD) and SOS/FPI (ESPN), a REAL walk-forward
"as of right before this game" snapshot is achievable (bcftoys FEI/F+
still isn't -- see the validation backtest script's docstring for why).

WHAT IT ANSWERS, per miss:
  1. Off/Def Stuff Rate for winner and loser, as of the week BEFORE the
     game (real, no leakage) vs. TODAY (drift = how much it's moved).
  2. Whether the stuff-rate "vote" (who it favored) is the SAME using the
     as-of-that-week number as it is using today's number -- i.e. would
     this miss get flagged the same way if checked in real time, or did
     the signal only show up in hindsight once later games moved the
     season average?
  3. SOS/FPI for both teams as of that week -- a real, direct check on
     "were they just playing a weak schedule so far," not a guess.

Run this locally (needs real network access to api.collegefootballdata.com
and ESPN's site API):

    python3 research_and_backtests/cfb_miss_stat_drift_check.py
"""
import os
import sys
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cfb_working_schedule import (              # noqa: E402
    load_stat_history, tune_stat_weights, clean_team_name,
    fetch_espn_team_directory, fetch_espn_power_index,
    CFBD_API_KEY, _CFBD_BASE,
)

SEASON_YEAR = 2026


def find_misses(history, included_keys, weights_by_key):
    misses = []
    for game in history["games"].values():
        votes = game.get("votes", {})
        score = sum(weights_by_key.get(k, 0) * votes[k] for k in included_keys if k in votes)
        if score < 0:
            misses.append({"winner": game.get("winner"), "loser": game.get("loser"), "date": game.get("date")})
    return misses


def fetch_cfbd_games_with_week(season_year):
    """Real completed games with their real CFBD week number, used to look
    up which week each miss actually happened in."""
    if not CFBD_API_KEY:
        print(" -> ⚠ No CFBD_API_KEY set.")
        return []
    url = f"{_CFBD_BASE}/games"
    headers = {"Authorization": f"Bearer {CFBD_API_KEY}", "Accept": "application/json"}
    resp = requests.get(url, headers=headers, params={"year": season_year, "seasonType": "regular"}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    out = []
    for g in data:
        if not g.get("completed"):
            continue
        out.append({
            "week": g.get("week"),
            "away": clean_team_name(g.get("awayTeam")),
            "home": clean_team_name(g.get("homeTeam")),
        })
    return out


def find_week_for_matchup(games, team_a, team_b):
    for g in games:
        if {g["away"], g["home"]} == {team_a, team_b}:
            return g["week"]
    return None


def fetch_cfbd_stuff_havoc_asof(season_year, end_week=None):
    """Real Off/Def Stuff Rate + Havoc Rate, cumulative through end_week
    (inclusive) if given, else the current full season-to-date snapshot.
    Uses CFBD's own real startWeek/endWeek params -- a genuine walk-forward
    snapshot, not an approximation."""
    if not CFBD_API_KEY:
        return {}
    url = f"{_CFBD_BASE}/stats/season/advanced"
    headers = {"Authorization": f"Bearer {CFBD_API_KEY}", "Accept": "application/json"}
    params = {"year": season_year}
    if end_week is not None:
        params["startWeek"] = 1
        params["endWeek"] = end_week
    resp = requests.get(url, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    out = {}
    for item in data:
        team = clean_team_name(item.get("team"))
        offense = item.get("offense") or {}
        defense = item.get("defense") or {}
        out[team] = {
            "Off_Stuff_Rate": offense.get("stuffRate"),
            "Def_Stuff_Rate": defense.get("stuffRate"),
            "Off_Havoc": (offense.get("havoc") or {}).get("total"),
            "Def_Havoc": (defense.get("havoc") or {}).get("total"),
        }
    return out


def main():
    history = load_stat_history()
    included_stats, acc, correct, decided, total = tune_stat_weights(history)
    weights_by_key = {key: weight for _, key, weight, _, _ in included_stats}
    included_keys = [key for _, key, _, _, _ in included_stats]

    misses = find_misses(history, included_keys, weights_by_key)
    if not misses:
        print("No real misses on record yet.")
        return
    print(f"{len(misses)} real miss(es) on record. Current model: {included_keys} -> {correct}/{decided} = {acc*100:.1f}%\n")

    print("Pulling real completed games with week numbers...")
    games = fetch_cfbd_games_with_week(SEASON_YEAR)

    print("Pulling TODAY's current CFBD stuff-rate/havoc snapshot...")
    current_cfbd = fetch_cfbd_stuff_havoc_asof(SEASON_YEAR)

    print("Pulling ESPN team directory (needed for per-week Power Index/SOS)...")
    team_dir = fetch_espn_team_directory()
    current_week = max((g["week"] for g in games if g["week"] is not None), default=1)
    print(f"Pulling TODAY's ESPN Power Index/SOS (week {current_week})...")
    current_espn = fetch_espn_power_index(SEASON_YEAR, current_week, team_dir)

    espn_cache = {}

    def espn_asof(week):
        if week not in espn_cache:
            print(f"Pulling ESPN Power Index/SOS as of week {week}...")
            espn_cache[week] = fetch_espn_power_index(SEASON_YEAR, week, team_dir)
        return espn_cache[week]

    cfbd_cache = {}

    def cfbd_asof(end_week):
        if end_week not in cfbd_cache:
            print(f"Pulling CFBD stuff-rate/havoc as of week {end_week} (real startWeek=1..{end_week})...")
            cfbd_cache[end_week] = fetch_cfbd_stuff_havoc_asof(SEASON_YEAR, end_week=end_week)
        return cfbd_cache[end_week]

    for m in misses:
        winner, loser = m["winner"], m["loser"]
        week = find_week_for_matchup(games, winner, loser)
        print(f"\n{'='*78}\n{winner} over {loser}  ({m['date']}, real week {week})\n{'='*78}")
        if week is None or week <= 1:
            print("  Couldn't match this game to a real week number (or it's week 1, with no prior-week "
                  "snapshot to compare against) -- skipping the as-of comparison for this one.")
            continue

        asof_cfbd = cfbd_asof(week - 1)
        w_asof, l_asof = asof_cfbd.get(winner, {}), asof_cfbd.get(loser, {})
        w_now, l_now = current_cfbd.get(winner, {}), current_cfbd.get(loser, {})

        print("  Off/Def Stuff Rate -- as of right before this game (real, no leakage) vs. TODAY:")
        for label, key, higher_is_better in [
            ("Loser's Off Stuff Rate (suffered, lower=better)", "Off_Stuff_Rate", False),
            ("Loser's Def Stuff Rate (forced, higher=better)", "Def_Stuff_Rate", True),
            ("Winner's Off Stuff Rate (suffered, lower=better)", "Off_Stuff_Rate", False),
            ("Winner's Def Stuff Rate (forced, higher=better)", "Def_Stuff_Rate", True),
        ]:
            side_asof = l_asof if "Loser" in label else w_asof
            side_now = l_now if "Loser" in label else w_now
            av, nv = side_asof.get(key), side_now.get(key)
            if av is None or nv is None:
                print(f"    {label:50s} (no real data on one side)")
                continue
            drift = nv - av
            print(f"    {label:50s} as-of-week-{week-1}={av:.4f}  today={nv:.4f}  drift={drift:+.4f}")

        w_flag_asof = (l_asof.get("Off_Stuff_Rate") is not None and w_asof.get("Def_Stuff_Rate") is not None
                       and l_asof["Off_Stuff_Rate"] > w_asof.get("Off_Stuff_Rate", 0))
        loser_stuff_asof, winner_stuff_asof = l_asof.get("Off_Stuff_Rate"), w_asof.get("Off_Stuff_Rate")
        loser_stuff_now, winner_stuff_now = l_now.get("Off_Stuff_Rate"), w_now.get("Off_Stuff_Rate")
        if loser_stuff_asof is not None and winner_stuff_asof is not None:
            flagged_asof = loser_stuff_asof > winner_stuff_asof  # loser got stuffed more -> favors winner
            print(f"  Would 'loser gets stuffed more' have been flagged AS OF THAT WEEK? {flagged_asof}")
        if loser_stuff_now is not None and winner_stuff_now is not None:
            flagged_now = loser_stuff_now > winner_stuff_now
            print(f"  Does today's data flag it (with hindsight)?                        {flagged_now}")

        w_sos = espn_asof(week).get(winner, {}).get("SOS")
        l_sos = espn_asof(week).get(loser, {}).get("SOS")
        w_sos_now = current_espn.get(winner, {}).get("SOS")
        l_sos_now = current_espn.get(loser, {}).get("SOS")
        print(f"  SOS as of week {week}: winner({winner})={w_sos}  loser({loser})={l_sos}")
        print(f"  SOS today:            winner({winner})={w_sos_now}  loser({loser})={l_sos_now}")


if __name__ == "__main__":
    main()
