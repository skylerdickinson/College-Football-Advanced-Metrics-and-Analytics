"""
cfb_home_away_splits.py -- each team's home / road split stats for the Skinny.   (added 2026-10-07)

For every team: games played at home and on the road, and per-game averages of rushing yards, passing yards,
points scored, and the same allowed by its defense (opponent rushing yards, passing yards, points), in each. Built from CFBD's per-game team stats (/games/teams, one call per
week). Finished weeks are saved to cfb_splits_cache.json and never re-pulled; only the two most recent weeks are
refreshed each run, so a normal run spends 1-2 CFBD calls. If CFBD refuses, the saved weeks are used.

NOT YET LIVE-VERIFIED (written where CFBD couldn't be reached). Run it standalone first:
        python3 cfb_home_away_splits.py            # pulls, prints the raw field names, a few sample teams
        python3 cfb_home_away_splits.py --selftest # offline logic test
Fields it expects (CFBD v2 /games/teams): [{id, teams:[{team, homeAway, points, stats:[{category, stat}]}]}] with
stat categories 'rushingYards' and 'netPassingYards' (falls back to 'passingYards').
"""
import os, sys, json
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(_HERE, "cfb_splits_cache.json")
_CFBD_BASE = "https://api.collegefootballdata.com"
MAX_WEEK = 16


def _num(x):
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _reduce_game(g):
    """One raw /games/teams record -> {'teams': [{'team','home','points','rush','pass'} x2]} or None."""
    teams = g.get("teams") or []
    if len(teams) != 2:
        return None
    out = []
    for t in teams:
        stats = {}
        for s in t.get("stats") or []:
            if isinstance(s, dict):
                stats[str(s.get("category"))] = s.get("stat")
        pts = _num(t.get("points"))
        if pts is None:
            pts = _num(stats.get("points"))
        rush = _num(stats.get("rushingYards"))
        pas = _num(stats.get("netPassingYards"))
        if pas is None:
            pas = _num(stats.get("passingYards"))
        out.append({"team": t.get("team"), "home": str(t.get("homeAway", "")).lower() == "home",
                    "points": pts, "rush": rush, "pass": pas})
    return {"teams": out}


def _load_cache():
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def fetch_games(year):
    """Returns (list of reduced games, note)."""
    cache = _load_cache()
    weeks = cache.get("weeks", {}) if cache.get("season_year") == year else {}
    key = os.environ.get("CFBD_API_KEY")
    if not key:
        try:
            import cfb_working_schedule as _cws
            key = _cws.CFBD_API_KEY
        except Exception:
            key = None
    spent, failed = 0, []
    try:
        import requests
        have = sorted(int(w) for w in weeks)
        refresh_from = (have[-2] if len(have) >= 2 else (have[0] if have else 1))
        printed = False
        for wk in range(1, MAX_WEEK + 1):
            if str(wk) in weeks and wk < refresh_from:
                continue
            try:
                r = requests.get(f"{_CFBD_BASE}/games/teams", params={"year": year, "week": wk, "seasonType": "regular"},
                                 headers={"Authorization": f"Bearer {key}", "Accept": "application/json"}, timeout=40)
                r.raise_for_status()
                data = r.json()
                spent += 1
            except Exception as e:
                failed.append(f"week {wk} ({e})")
                continue
            if not isinstance(data, list) or not data:
                if wk > 1 and str(wk) not in weeks:
                    break
                continue
            if not printed:
                printed = True
                t0 = (data[0].get("teams") or [{}])[0]
                print(f" -> [debug] CFBD /games/teams first record keys: {list(data[0].keys())}; team keys: {list(t0.keys())}; "
                      f"stat categories: {[s.get('category') for s in (t0.get('stats') or [])][:12]}")
            red = [x for x in (_reduce_game(g) for g in data) if x]
            weeks[str(wk)] = {"fetched_at": datetime.now().isoformat(), "games": red}
        cache = {"season_year": year, "weeks": weeks}
        try:
            with open(CACHE_PATH, "w") as f:
                json.dump(cache, f)
        except OSError as e:
            print(f" -> ⚠ could not write the splits cache ({e})")
    except Exception as e:
        failed.append(str(e))
    games = [g for w in sorted(weeks, key=int) for g in weeks[w]["games"]]
    note = f"{len(games)} games across {len(weeks)} week(s); {spent} CFBD call(s) spent"
    if failed:
        note += f"; problems: {failed[:3]}"
    return games, note


def build_splits(games, fbs_names=None, season_avg=True):
    """{team: {'home': agg, 'away': agg}}, agg = {'n','rush','pass','pts','allowed'} (per-game averages)."""
    if fbs_names:                      # FBS-only: drop games vs non-FBS teams, same as the other sheets
        try:
            import cfb_split_grid as _sg
            games = _sg._fbs_filter(games, fbs_names)
        except Exception:
            pass
    acc = {}
    for g in games:
        a, b = g["teams"]
        for me, opp in ((a, b), (b, a)):
            if not me.get("team"):
                continue
            sides = acc.setdefault(me["team"], {"home": [], "away": []})
            row = (me["rush"], me["pass"], me["points"], opp["points"], opp["rush"], opp["pass"])
            if season_avg:                 # SEASON AVERAGE: every game counts on both keys
                sides["home"].append(row)
                sides["away"].append(row)
            else:
                sides["home" if me["home"] else "away"].append(row)
    out = {}
    for team, sides in acc.items():
        out[team] = {}
        for side, rows in sides.items():
            def avg(i):
                vals = [r[i] for r in rows if r[i] is not None]
                return sum(vals) / len(vals) if vals else None
            out[team][side] = {"n": len(rows), "rush": avg(0), "pass": avg(1), "pts": avg(2), "allowed": avg(3),
                               "rush_allowed": avg(4), "pass_allowed": avg(5)}
    return out


def get_splits(year, fbs_names=None):
    try:
        games, note = fetch_games(year)
        print(f" -> Home/road splits: {note}" + (" (FBS-vs-FBS games only)" if fbs_names else ""))
        return build_splits(games, fbs_names)
    except Exception as e:
        print(f" -> Home/road splits skipped ({e})")
        return {}


def lookup(splits, team_name):
    """Find a team's splits under any spelling (CFBD 'South Florida' vs the report's 'S Florida')."""
    if not splits:
        return None
    try:
        import cfb_ats_odds as _o
    except Exception:
        return splits.get(team_name)
    want = _o.name_keys(team_name)
    hits = [t for t in splits if _o.name_keys(t) & want]
    return splits[hits[0]] if len(hits) == 1 else (splits[hits[0]] if hits else None)


def fmt_side(agg):
    """-> ((off rush, off pass, pts scored), (def rush allowed, def pass allowed, pts allowed)) display strings for one
    side; '--' everywhere when there are no games."""
    if not agg or not agg.get("n"):
        return ("--", "--", "--"), ("--", "--", "--")
    f = lambda v: "--" if v is None else f"{v:.1f}"
    return ((f(agg["rush"]), f(agg["pass"]), f(agg["pts"])),
            (f(agg["rush_allowed"]), f(agg["pass_allowed"]), f(agg["allowed"])))


def _selftest():
    def G(h, a, hp, ap, hr, ar, hpa, apa):
        return {"teams": [
            {"team": h, "homeAway": "home", "points": hp, "stats": [{"category": "rushingYards", "stat": str(hr)}, {"category": "netPassingYards", "stat": str(hpa)}]},
            {"team": a, "homeAway": "away", "points": ap, "stats": [{"category": "rushingYards", "stat": str(ar)}, {"category": "passingYards", "stat": str(apa)}]}]}
    raw = [G("Troy", "Rice", 30, 14, 150, 90, 250, 200), G("Troy", "UTSA", 20, 24, 100, 120, 200, 180),
           G("Rice", "Troy", 10, 17, 80, 160, 190, 210)]
    games = [_reduce_game(g) for g in raw]
    ssa = build_splits(games)                  # default = season average
    assert ssa["Troy"]["home"]["n"] == 3 and ssa["Troy"]["away"]["n"] == 3 and abs(ssa["Troy"]["home"]["pts"] - (30 + 20 + 17) / 3) < 1e-9
    sp = build_splits(games, season_avg=False)
    t = sp["Troy"]
    assert t["home"]["n"] == 2 and abs(t["home"]["rush"] - 125.0) < 1e-9 and abs(t["home"]["pts"] - 25.0) < 1e-9 and abs(t["home"]["allowed"] - 19.0) < 1e-9, t
    assert t["away"]["n"] == 1 and t["away"]["rush"] == 160 and t["away"]["pass"] == 210 and t["away"]["allowed"] == 10, t
    assert sp["Rice"]["away"]["pass"] == 200 and sp["Rice"]["away"]["pts"] == 14      # passingYards fallback
    assert fmt_side(None) == (("--",) * 3, ("--",) * 3)
    assert fmt_side(t["away"]) == (("160.0", "210.0", "17.0"), ("80.0", "190.0", "10.0")), fmt_side(t["away"])
    assert t["home"]["rush_allowed"] == 105.0 and t["home"]["pass_allowed"] == 190.0, t["home"]
    print("selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        yr = datetime.now().year
        sp = get_splits(yr)
        print(f"{len(sp)} teams")
        for team in list(sp)[:5]:
            print(f"  {team}: home {fmt_side(sp[team].get('home'))} | road {fmt_side(sp[team].get('away'))}")
