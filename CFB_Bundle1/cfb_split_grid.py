"""
cfb_split_grid.py -- home / road OFFENSE-vs-DEFENSE split stats for the Skinny.   (added 2026-10-07)

For every team, in its HOME games and its ROAD games separately, per-game averages of a long list of stats for its offense
and for its defense (what it allowed / forced):
    points, rush yds & yds/play, pass yds & yds/play, 3rd down %, sacks, tackles for loss, turnovers
    (from CFBD /games/teams) and line yards, 2nd level yards, open field yards, stuff rate, success rate, explosiveness
    (from CFBD /stats/game/advanced).
Red zone % is NOT here: CFBD only has it from play-by-play, so it can't be split home/road without a much bigger pull.

Convention for every stat: the OFFENSE number is what that offense produced/suffered; the DEFENSE number is the same stat measured on
the offenses it faced (so defense "Sacks" = sacks it made, "Points" = points allowed, "Turnovers" = takeaways).

Cache: cfb_split_grid_cache.json (finished weeks are never re-pulled; the two most recent weeks refresh each run).
Never fatal: if CFBD refuses, the saved weeks are used; with no data the Skinny falls back to its simple rush/pass/points grid.

    python3 cfb_split_grid.py            # pull + print a few teams and every stat category CFBD sent (send me that list if a row is blank)
    python3 cfb_split_grid.py --selftest # offline logic test
"""
import os, sys, json
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(_HERE, "cfb_split_grid_cache.json")
_CFBD_BASE = "https://api.collegefootballdata.com"
MAX_WEEK = 16

# key, label, higher-is-better-for-the-OFFENSE, decimals
METRICS = [
    ("pts",      "Points/G",                       True,  1),
    ("rush_ypp", "Rush Yds/Play",                  True,  2),
    ("pass_ypp", "Pass Yds/Play",                  True,  2),
    ("rush_yds", "Rush Yds/G",                     True,  1),
    ("pass_yds", "Pass Yds/G",                     True,  1),
    ("third",    "3rd Down %",                     True,  1),
    ("success",  "Success Rate",                   True,  3),
    ("explo",    "Explosiveness",                  True,  3),
    ("line",     "Line Yards",                     True,  2),
    ("second",   "2nd Level Yds",                  True,  2),
    ("open",     "Open Field Yds",                 True,  2),
    ("stuff",    "Stuff Rate (OFF stuffed / DEF stuffs)", False, 3),
    ("sacks",    "Sacks/G (OFF allowed / DEF made)", False, 2),
    ("tfl",      "TFL/G (OFF allowed / DEF made)",  False, 2),
    ("to",       "Turnovers/G (OFF lost / DEF forced)", False, 2),
]


def _num(x):
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- reduce raw CFBD records
def _reduce_game(g):
    teams = g.get("teams") or []
    if len(teams) != 2:
        return None
    out = []
    for t in teams:
        st = {}
        for s in t.get("stats") or []:
            if not isinstance(s, dict):
                continue
            cat, val = str(s.get("category")), s.get("stat")
            if isinstance(val, str) and "-" in val and val.replace("-", "").replace(" ", "").isdigit():
                a, b = val.split("-", 1)
                st[cat + "_made"], st[cat + "_att"] = _num(a), _num(b)          # "5-12" style (3rd down, completions)
            elif isinstance(val, str) and ":" in val:
                try:
                    m, sec = val.split(":", 1)
                    st[cat] = float(m) * 60 + float(sec)
                except ValueError:
                    pass
            else:
                v = _num(val)
                if v is not None:
                    st[cat] = v
        pts = _num(t.get("points"))
        if pts is None:
            pts = st.get("points")
        out.append({"team": t.get("team"), "home": str(t.get("homeAway", "")).lower() == "home", "points": pts, "stats": st})
    return {"id": g.get("id"), "teams": out}


def _adv_block(b):
    if not isinstance(b, dict):
        return {}
    return {"line": _num(b.get("lineYards")), "second": _num(b.get("secondLevelYards")), "open": _num(b.get("openFieldYards")),
            "stuff": _num(b.get("stuffRate")), "success": _num(b.get("successRate")), "explo": _num(b.get("explosiveness"))}


def _reduce_adv(r):
    if not isinstance(r, dict):
        return None
    gid = r.get("gameId", r.get("id"))
    if gid is None or not r.get("team"):
        return None
    return {"gameId": gid, "team": r.get("team"), "off": _adv_block(r.get("offense")), "def": _adv_block(r.get("defense"))}


# ---------------------------------------------------------------- per-game metrics -> per-team/side averages
def _off_metrics(me, opp):
    """The offense metrics of team record `me` (opponent record `opp`, for sacks/TFL which are credited to the other side)."""
    s, o = me["stats"], opp["stats"]
    m = {"pts": me.get("points"), "rush_yds": s.get("rushingYards"),
         "pass_yds": s.get("netPassingYards", s.get("passingYards")),
         "sacks": o.get("sacks"), "tfl": o.get("tacklesForLoss")}
    ra, ry = s.get("rushingAttempts"), s.get("rushingYards")
    m["rush_ypp"] = s.get("yardsPerRushAttempt", (ry / ra) if (ry is not None and ra) else None)
    m["pass_ypp"] = s.get("yardsPerPass")
    to = s.get("turnovers")
    if to is None and (s.get("interceptions") is not None or s.get("fumblesLost") is not None):
        to = (s.get("interceptions") or 0) + (s.get("fumblesLost") or 0)
    m["to"] = to
    m["_third_made"], m["_third_att"] = s.get("thirdDownEff_made"), s.get("thirdDownEff_att")
    return m


def _fbs_filter(games, fbs_names):
    """FBS-only: keep only games where BOTH teams are FBS, so a team's home/road numbers match the
    FBS-only season stats on the other sheets (a 52-7 win over an FCS/D-II team no longer counts). fbs_names=None -> keep all."""
    if not fbs_names:
        return games
    try:
        import cfb_ats_odds as _o
        want = set()
        for n in fbs_names:
            want |= _o.name_keys(n)
    except Exception:
        return games
    memo = {}

    def is_fbs(t):
        if t not in memo:
            memo[t] = bool(_o.name_keys(t) & want)
        return memo[t]
    return [g for g in games if len(g.get("teams") or []) == 2 and all(is_fbs(t.get("team")) for t in g["teams"])]


def build_grid(weeks, fbs_names=None, season_avg=True):
    """weeks: {wk: {'games': [reduced], 'adv': [reduced]}} -> {team: {'home': agg, 'away': agg}}; agg = {'n', 'off': {k: v}, 'def': {k: v}}."""
    adv = {}
    for w in weeks.values():
        for r in w.get("adv") or []:
            adv[(r["gameId"], r["team"])] = r
    acc = {}
    for w in weeks.values():
        for g in _fbs_filter(w.get("games") or [], fbs_names):
            a, b = g["teams"]
            for me, opp in ((a, b), (b, a)):
                if not me.get("team"):
                    continue
                sides = acc.setdefault(me["team"], {"home": [], "away": []})
                off, dfn = _off_metrics(me, opp), _off_metrics(opp, me)
                ad = adv.get((g.get("id"), me["team"]))
                if ad:
                    off.update({k: v for k, v in (ad.get("off") or {}).items() if v is not None})
                    dfn.update({k: v for k, v in (ad.get("def") or {}).items() if v is not None})
                # SEASON AVERAGE: every game counts on BOTH keys, so 'home' and 'away' both hold the
                # team's full-season (FBS-vs-FBS) average -- the Skinny no longer splits by venue.
                if season_avg:
                    sides["home"].append((off, dfn))
                    sides["away"].append((off, dfn))
                else:                                   # true venue split (kept for the selftest / future use)
                    sides["home" if me["home"] else "away"].append((off, dfn))
    out = {}
    for team, sides in acc.items():
        out[team] = {}
        for side, rows in sides.items():
            if not rows:
                continue

            def avg(idx, key):
                vals = [r[idx].get(key) for r in rows if r[idx].get(key) is not None]
                return sum(vals) / len(vals) if vals else None

            def third(idx):
                mk = sum(r[idx].get("_third_made") or 0 for r in rows)
                at = sum(r[idx].get("_third_att") or 0 for r in rows)
                return 100.0 * mk / at if at else None

            agg = {"n": len(rows), "off": {}, "def": {}}
            for k, _l, _hi, _d in METRICS:
                if k == "third":
                    agg["off"][k], agg["def"][k] = third(0), third(1)
                else:
                    agg["off"][k], agg["def"][k] = avg(0, k), avg(1, k)
            out[team][side] = agg
    return out


# ---------------------------------------------------------------- fetch
def _load_cache():
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def fetch_weeks(year):
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
        hdr = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
        have = sorted(int(w) for w in weeks)
        refresh_from = (have[-2] if len(have) >= 2 else (have[0] if have else 1))
        printed = False
        for wk in range(1, MAX_WEEK + 1):
            if str(wk) in weeks and wk < refresh_from:
                continue
            try:
                r = requests.get(f"{_CFBD_BASE}/games/teams", params={"year": year, "week": wk, "seasonType": "regular"}, headers=hdr, timeout=40)
                r.raise_for_status()
                data = r.json()
                spent += 1
            except Exception as e:
                failed.append(f"games/teams week {wk} ({e})")
                continue
            if not isinstance(data, list) or not data:
                if wk > 1 and str(wk) not in weeks:
                    break
                continue
            if not printed:
                printed = True
                t0 = (data[0].get("teams") or [{}])[0]
                cats = sorted({s.get("category") for g in data[:5] for t in (g.get("teams") or []) for s in (t.get("stats") or [])})
                print(f" -> [debug] CFBD /games/teams stat categories: {cats}")
            games = [x for x in (_reduce_game(g) for g in data) if x]
            adv = []
            try:
                r2 = requests.get(f"{_CFBD_BASE}/stats/game/advanced", params={"year": year, "week": wk, "seasonType": "regular"}, headers=hdr, timeout=40)
                r2.raise_for_status()
                d2 = r2.json()
                spent += 1
                adv = [x for x in (_reduce_adv(a) for a in (d2 if isinstance(d2, list) else [])) if x]
                if wk == 1 or not adv:
                    print(f" -> [debug] CFBD /stats/game/advanced week {wk}: {len(adv)} team-games" + (f"; keys {list(d2[0].keys())}" if d2 else ""))
            except Exception as e:
                failed.append(f"stats/game/advanced week {wk} ({e})")
            weeks[str(wk)] = {"fetched_at": datetime.now().isoformat(), "games": games, "adv": adv}
        cache = {"season_year": year, "weeks": weeks}
        try:
            with open(CACHE_PATH, "w") as f:
                json.dump(cache, f)
        except OSError as e:
            print(f" -> ⚠ could not write the split-grid cache ({e})")
    except Exception as e:
        failed.append(str(e))
    note = f"{len(weeks)} week(s) on file; {spent} CFBD call(s) spent"
    if failed:
        note += f"; problems: {failed[:3]}"
    return weeks, note


def get_grid(year, fbs_names=None):
    try:
        weeks, note = fetch_weeks(year)
        print(f" -> Home/road offense-vs-defense grid data: {note}" + (" (FBS-vs-FBS games only)" if fbs_names else ""))
        return build_grid(weeks, fbs_names)
    except Exception as e:
        print(f" -> Home/road grid skipped ({e})")
        return {}


def lookup(grid, team_name):
    if not grid:
        return None
    try:
        import cfb_ats_odds as _o
    except Exception:
        return grid.get(team_name)
    want = _o.name_keys(team_name)
    hits = [t for t in grid if _o.name_keys(t) & want]
    return grid[hits[0]] if hits else None


def pool(grid, side, role, key):
    """Sorted values of one stat across all teams for one spot (side 'home'/'away', role 'off'/'def')."""
    return sorted(v[side][role][key] for v in (grid or {}).values()
                  if isinstance(v, dict) and v.get(side) and v[side][role].get(key) is not None)


def goodness(pool_vals, val, higher_is_better):
    """0..1, 1 = best of all teams for that unit (None when there is no value or too few teams)."""
    if val is None or len(pool_vals) < 8:
        return None
    worse = sum(1 for x in pool_vals if (x < val if higher_is_better else x > val))
    return worse / (len(pool_vals) - 1)


def fbs_team_set(grid, fbs_names):
    """Teams in the grid that are FBS (match one of fbs_names under any spelling) -- so ranks are 'out of the FBS', not out of every team CFBD lists."""
    try:
        import cfb_ats_odds as _o
        want = set()
        for n in fbs_names:
            want |= _o.name_keys(n)
        return {t for t in grid if _o.name_keys(t) & want}
    except Exception:
        return set(grid)


def ranked_pool(grid, side, role, key, teams=None):
    out = []
    for t, v in (grid or {}).items():
        if teams is not None and t not in teams:
            continue
        if isinstance(v, dict) and v.get(side) and v[side][role].get(key) is not None:
            out.append(v[side][role][key])
    return sorted(out)


def rank_of(pool_vals, val, higher_is_better):
    """1 = best of the pool (ties share a rank). Returns (rank, pool size) or (None, n)."""
    n = len(pool_vals)
    if val is None or n < 8:
        return None, n
    better = sum(1 for x in pool_vals if (x > val if higher_is_better else x < val))
    return better + 1, n


# ---------------------------------------------------------------- selftest / CLI
def _selftest():
    def team(name, home, pts, stats):
        return {"team": name, "homeAway": "home" if home else "away", "points": pts,
                "stats": [{"category": k, "stat": v} for k, v in stats.items()]}
    S = lambda **k: k
    g1 = {"id": 1, "teams": [team("A", True, 30, S(rushingYards="150", rushingAttempts="30", netPassingYards="250", yardsPerPass="8.0",
                                                  thirdDownEff="6-12", sacks="3", tacklesForLoss="7", turnovers="1")),
                             team("B", False, 20, S(rushingYards="90", rushingAttempts="30", netPassingYards="200", yardsPerPass="6.0",
                                                  thirdDownEff="3-12", sacks="1", tacklesForLoss="4", turnovers="3"))]}
    g2 = {"id": 2, "teams": [team("B", True, 10, S(rushingYards="60", rushingAttempts="20", netPassingYards="100", thirdDownEff="2-10",
                                                  sacks="0", tacklesForLoss="2", turnovers="2")),
                             team("A", False, 27, S(rushingYards="200", rushingAttempts="40", netPassingYards="150", thirdDownEff="5-10",
                                                  sacks="4", tacklesForLoss="8", turnovers="0"))]}
    adv = [{"gameId": 1, "team": "A", "offense": {"lineYards": 3.0, "stuffRate": 0.1, "successRate": 0.5}, "defense": {"lineYards": 2.0, "stuffRate": 0.2}},
           {"gameId": 1, "team": "B", "offense": {"lineYards": 2.0, "stuffRate": 0.2}, "defense": {"lineYards": 3.0, "stuffRate": 0.1}}]
    weeks = {"1": {"games": [_reduce_game(g1)], "adv": [_reduce_adv(a) for a in adv]}, "2": {"games": [_reduce_game(g2)], "adv": []}}
    sa = build_grid(weeks)                      # default = season average: both keys hold every game
    assert sa["A"]["home"]["n"] == 2 and sa["A"]["away"]["n"] == 2 and sa["A"]["home"]["off"]["pts"] == 28.5
    grid = build_grid(weeks, season_avg=False)
    a_home, a_away = grid["A"]["home"], grid["A"]["away"]
    assert a_home["n"] == 1 and a_away["n"] == 1
    assert a_home["off"]["pts"] == 30 and a_home["def"]["pts"] == 20
    assert abs(a_home["off"]["rush_ypp"] - 5.0) < 1e-9 and abs(a_away["off"]["rush_ypp"] - 5.0) < 1e-9
    assert a_home["off"]["pass_ypp"] == 8.0 and a_home["def"]["pass_ypp"] == 6.0
    assert abs(a_home["off"]["third"] - 50.0) < 1e-9 and abs(a_home["def"]["third"] - 25.0) < 1e-9
    assert a_home["off"]["sacks"] == 1 and a_home["def"]["sacks"] == 3          # sacks suffered by A's offense / made by A's defense
    assert a_home["off"]["tfl"] == 4 and a_home["def"]["tfl"] == 7
    assert a_home["off"]["to"] == 1 and a_home["def"]["to"] == 3                # A lost 1, forced 3
    assert a_home["off"]["line"] == 3.0 and a_home["def"]["line"] == 2.0 and a_home["off"]["stuff"] == 0.1
    assert a_away["off"]["line"] is None                                        # week 2 had no advanced data
    assert grid["B"]["away"]["off"]["pts"] == 20 and grid["B"]["home"]["off"]["pts"] == 10
    r, n = rank_of(list(range(1, 11)), 9, True)
    assert (r, n) == (2, 10), (r, n)
    r, n = rank_of(list(range(1, 11)), 2, False)
    assert (r, n) == (2, 10), (r, n)
    print("selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        yr = datetime.now().year
        g = get_grid(yr)
        print(f"{len(g)} teams")
        for t in list(g)[:3]:
            print(t, json.dumps(g[t])[:600])
