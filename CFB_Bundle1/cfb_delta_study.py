"""
GRID DELTA SCALE STUDY: "how much of a % does it matter when a delta on the grid is massive?"

WHY THIS EXISTS (and why it waits for games to finish)
  The grid's deltas (Line Yards, Stuff Rate, Sacks, TFL, Havoc, Total Pass, Passing Explosiveness, Open Field, Panic,
  Power Success, OSR vs DSR, Rushing Reality, 2nd Level, Offensive Efficiency, Net Success Rate, plus FEI / PPG / SOR gaps and
  the PPD Spread) are built from season-to-date stats. A test run on stats pulled AFTER a game is played is flattered by that
  game (in a 2026-10-07 check, "massive" tiers read 11-25 points too high). So this study does it the clean way:

    1. new.py (grid step) calls record() every run: it saves each matchup's deltas the FIRST time the game is seen, i.e.
       before kickoff, into cfb_delta_history.json. Games CFBD already shows as finished are skipped, never recorded late.
    2. This script (run by cfb_run_all.py as the last step, or by hand: python3 cfb_delta_study.py) asks CFBD for final
       scores (1 call), grades the saved games, and prints/writes the scale: for every delta, win % of the team the delta
       favors when the gap is small / medium / large / massive.

  Tiers are set from the size of each delta across ALL saved games (small = below the median |delta|, medium = median-75th,
  large = 75th-90th, massive = top 10%), and the thresholds are printed in the grid's own units so you can read them straight
  off the grid. Sign convention is the grid's: positive favors AWAY, negative favors HOME.

  Expect ~55 games a week: a few weeks in, the pooled tiers get usable; a single delta's "massive" tier (top 10%) needs several
  weeks before it means much. Every table prints its sample sizes and a +/- margin so it can't pretend to be more exact than it is.

  python3 cfb_delta_study.py             grade finished games + print/write the report
  python3 cfb_delta_study.py --selftest  checks the math on made-up games (no network)
"""
import os
import re
import sys
import json
import math
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
HIST_PATH = os.path.join(_HERE, "cfb_delta_history.json")
REPORT_PATH = os.path.join(_HERE, "generated", "Delta_Scale_Report.txt")
SCALE_PATH = os.path.join(_HERE, "cfb_delta_scale.json")      # read by new.py to color large deltas (replaces its built-in estimates)
MIN_GRADED_FOR_SCALE = 120
_CFBD = "https://api.collegefootballdata.com"
MIN_SAMPLE_FOR_THRESHOLDS = 20


# ---------------------------------------------------------------- storage
def _load():
    try:
        with open(HIST_PATH) as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("games"), dict):
            return d
    except Exception:
        pass
    return {"games": {}}


def _save(d):
    try:
        os.makedirs(os.path.dirname(HIST_PATH) or ".", exist_ok=True)
        with open(HIST_PATH, "w") as f:
            json.dump(d, f, indent=1)
    except Exception as e:
        print(f" -> delta study: could not save {HIST_PATH} ({e})")


def _key(away, home, season):
    return f"{season}|{away}@{home}"


# ---------------------------------------------------------------- names + CFBD finals
def _name_variants(name, cws=None):
    out = set()
    try:
        c = (cws.clean_team_name(name) or name).upper()
    except Exception:
        c = name.upper()
    out.add(c)
    out.add(c.replace(" STATE", " ST"))
    out.add(c.replace(" ST", " STATE") if c.endswith(" ST") else c)
    out.add(name.upper())
    for v in list(out):
        if v.startswith("SOUTH "):
            out.add("S " + v[6:])
        out.add(v.replace("'", "").replace(".", ""))
    return out


def _fetch_finals(season, cws):
    """{(away_variant, home_variant): (home_pts, away_pts)} for every finished game, or None if CFBD can't be reached."""
    try:
        import requests
        if not cws.CFBD_API_KEY:
            return None
        resp = requests.get(f"{_CFBD}/games", params={"year": season, "seasonType": "regular"},
                            headers={"Authorization": f"Bearer {cws.CFBD_API_KEY}", "Accept": "application/json"}, timeout=30)
        if resp.status_code != 200:
            print(f" -> delta study: CFBD returned HTTP {resp.status_code}.")
            return None
        games = resp.json()
    except Exception as e:
        print(f" -> delta study: could not reach CFBD ({e}).")
        return None
    finals = {}
    for g in games:
        if not g.get("completed"):
            continue
        hp, ap = g.get("homePoints"), g.get("awayPoints")
        if hp is None or ap is None:
            continue
        for hv in _name_variants(g.get("homeTeam", ""), cws):
            for av in _name_variants(g.get("awayTeam", ""), cws):
                finals[(av, hv)] = (hp, ap)
    return finals


def _lookup_final(finals, away, home, cws):
    for av in _name_variants(away, cws):
        for hv in _name_variants(home, cws):
            hit = finals.get((av, hv))
            if hit:
                return hit
    return None


# ---------------------------------------------------------------- 1. record (called by new.py)
def record(delta_log, season=None):
    """delta_log = {(away_team, home_team): {delta name: value}} from new.py. Saves each game's deltas the first time it is
    seen, unless CFBD already shows it finished. Never raises."""
    season = season or datetime.now().year
    try:
        cws = None
        try:
            import cfb_working_schedule as cws
        except Exception:
            cws = None
        d = _load()
        finals = _fetch_finals(season, cws) if cws is not None else None
        now = datetime.now(timezone.utc).isoformat()
        n_new = n_late = n_have = 0
        for (away, home), deltas in delta_log.items():
            k = _key(away, home, season)
            if k in d["games"]:
                n_have += 1
                d["games"][k]["last_seen"] = now
                continue
            if finals is not None and _lookup_final(finals, away, home, cws):
                n_late += 1
                continue
            clean = {n: round(float(v), 4) for n, v in deltas.items() if v is not None}
            if not clean:
                continue
            d["games"][k] = {"away": away, "home": home, "season": season, "first_seen": now, "last_seen": now,
                             "deltas": clean, "home_margin": None, "finals_checked": finals is not None}
            n_new += 1
        _save(d)
        print(f" -> delta study: saved pre-game deltas for {n_new} new game(s); {n_have} already on file"
              + (f"; skipped {n_late} that were already final" if n_late else "")
              + ("" if finals is not None else " (could not check CFBD for finished games -- those saves are marked unchecked)")
              + ".")
    except Exception as e:
        print(f" -> delta study: could not record deltas ({e}).")


# ---------------------------------------------------------------- 2. grade
def grade(season=None):
    season = season or datetime.now().year
    d = _load()
    pending = [g for g in d["games"].values() if g.get("home_margin") is None and g.get("season") == season]
    if not pending:
        return 0
    try:
        import cfb_working_schedule as cws
    except Exception:
        return 0
    finals = _fetch_finals(season, cws)
    if finals is None:
        return 0
    n = 0
    for g in pending:
        hit = _lookup_final(finals, g["away"], g["home"], cws)
        if hit:
            g["home_margin"] = hit[0] - hit[1]
            g["home_pts"], g["away_pts"] = hit[0], hit[1]
            n += 1
    if n:
        _save(d)
    print(f" -> delta study: graded {n} newly finished game(s); {len(pending) - n} still waiting on a final score.")
    return n


# ---------------------------------------------------------------- 3. analysis
def _pct(sorted_vals, q):
    return sorted_vals[min(int(q * len(sorted_vals)), len(sorted_vals) - 1)]


def _moe(p, n):
    return 0.0 if n == 0 else 1.96 * math.sqrt(max(p * (1 - p), 1e-9) / n)


def analyze(d):
    """Returns {'n_recorded','n_graded','deltas':{name:{...}},'pooled':{...},'counts':{...}}"""
    games = [g for g in d["games"].values()]
    graded = [g for g in games if g.get("home_margin") not in (None, 0) and g.get("finals_checked", True)]
    names = sorted({n for g in games for n in g["deltas"]})
    out = {"n_recorded": len(games), "n_graded": len(graded), "deltas": {}, "pooled": {}, "counts": {}}
    thr = {}
    for nm in names:
        allabs = sorted(abs(g["deltas"][nm]) for g in games if nm in g["deltas"] and g["deltas"][nm] != 0)
        if len(allabs) < MIN_SAMPLE_FOR_THRESHOLDS:
            continue
        thr[nm] = (_pct(allabs, .5), _pct(allabs, .75), _pct(allabs, .9))

    def tier(nm, v):
        t50, t75, t90 = thr[nm]
        a = abs(v)
        return 0 if a < t50 else 1 if a < t75 else 2 if a < t90 else 3

    pooled = [[0, 0] for _ in range(4)]
    for nm, (t50, t75, t90) in thr.items():
        tiers = [[0, 0] for _ in range(4)]
        for g in graded:
            v = g["deltas"].get(nm)
            if v is None or v == 0:
                continue
            won = 1 if (v > 0) == (g["home_margin"] < 0) else 0       # delta > 0 favors away; home_margin < 0 = away won
            t = tier(nm, v)
            tiers[t][0] += won
            tiers[t][1] += 1
            pooled[t][0] += won
            pooled[t][1] += 1
        out["deltas"][nm] = {"thresholds": [t50, t75, t90], "tiers": tiers}
    out["pooled"] = pooled
    # how many deltas are massive / large for the SAME side
    for label, level in (("massive", 3), ("large_or_more", 2)):
        cnt = {}
        for g in graded:
            net = 0
            for nm in thr:
                v = g["deltas"].get(nm)
                if v is None or v == 0:
                    continue
                if tier(nm, v) >= level:
                    net += 1 if v > 0 else -1
            if net == 0:
                continue
            k = min(abs(net), 5)
            c = cnt.setdefault(k, [0, 0])
            c[0] += 1 if (net > 0) == (g["home_margin"] < 0) else 0
            c[1] += 1
        out["counts"][label] = cnt
    return out


def report_lines(res):
    L = []
    L.append("GRID DELTA SCALE -- how often the team a delta favors actually won, by how big the delta was")
    L.append(f"{res['n_recorded']} games saved pre-game, {res['n_graded']} graded. Sign: + favors AWAY, - favors HOME (same as the grid).")
    if res["n_graded"] < 30:
        L.append("!! Under 30 graded games so far -- treat every number below as a first look, not a scale. It firms up each week.")
    L.append("")
    L.append(f"{'delta':32s} {'small':>11s} {'medium':>11s} {'large':>11s} {'MASSIVE':>11s}   |delta| at median / 75th / 90th")
    cell = lambda t: f"{t[1]:3d} {t[0] / t[1]:5.0%}" if t[1] else "    -    "
    rows = sorted(res["deltas"].items(), key=lambda kv: -(kv[1]["tiers"][3][0] / kv[1]["tiers"][3][1] if kv[1]["tiers"][3][1] else -1))
    for nm, r in rows:
        th = r["thresholds"]
        L.append(f"{nm:32s} " + " ".join(f"{cell(t):>11s}" for t in r["tiers"]) + f"   {th[0]:.3g} / {th[1]:.3g} / {th[2]:.3g}")
    pl = res["pooled"]
    if any(t[1] for t in pl):
        L.append("")
        L.append("ALL deltas pooled (games repeat across deltas, so read as a scale, not independent samples):")
        for name, t in zip(("small", "medium", "large", "massive"), pl):
            if t[1]:
                p = t[0] / t[1]
                L.append(f"   {name:8s} n={t[1]:4d}  leader won {p:5.1%}  (+/- {_moe(p, t[1]):.1%})")
    for label, title in (("massive", "Games where several deltas are MASSIVE for the same team"),
                         ("large_or_more", "Games where several deltas are LARGE-or-bigger for the same team")):
        cnt = res["counts"].get(label) or {}
        if cnt:
            L.append("")
            L.append(title + " (net of any that favor the other side):")
            for k in sorted(cnt):
                w, n = cnt[k]
                L.append(f"   {k}{'+' if k == 5 else ' '} deltas: n={n:3d}  that team won {w / n:5.1%}")
    return L


def write_scale(res, path=None):
    """Once enough games are graded, save each delta's REAL pre-game win % for the large / massive tiers. new.py uses these (a tier
    needs 15+ games behind it) instead of its built-in estimates, so the green / light green / teal colors turn into measured numbers."""
    path = path or SCALE_PATH
    if res["n_graded"] < MIN_GRADED_FOR_SCALE:
        return False
    out = {"source": "cfb_delta_study.py -- pre-game deltas graded against final scores", "n_graded": res["n_graded"],
           "updated": datetime.now(timezone.utc).isoformat(), "deltas": {}}
    for nm, r in res["deltas"].items():
        (lw, ln), (mw, mn) = r["tiers"][2], r["tiers"][3]
        out["deltas"][nm] = {"large": round(100.0 * lw / ln, 1) if ln else None, "n_large": ln,
                             "massive": round(100.0 * mw / mn, 1) if mn else None, "n_massive": mn}
    try:
        with open(path, "w") as f:
            json.dump(out, f, indent=1)
        return True
    except Exception as e:
        print(f" -> could not write {path} ({e})")
        return False


def main():
    grade()
    d = _load()
    if not d["games"]:
        print("Delta study: nothing saved yet -- the grid step (new.py) saves each week's pre-game deltas; run cfb_run_all.py first.")
        return
    res = analyze(d)
    lines = report_lines(res)
    if write_scale(res):
        lines.append("")
        lines.append(f"Saved cfb_delta_scale.json -- the grid's green / teal colors now use these measured win %s ({res['n_graded']} graded games).")
    elif res["n_graded"] < MIN_GRADED_FOR_SCALE:
        lines.append("")
        lines.append(f"The grid's green / teal colors still use built-in estimates; they switch to measured numbers once {MIN_GRADED_FOR_SCALE} games are graded "
                     f"({res['n_graded']} so far).")
    print("\n".join(lines))
    try:
        os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
        with open(REPORT_PATH, "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"\nWrote {REPORT_PATH}")
    except Exception as e:
        print(f" -> could not write the report file ({e})")


# ---------------------------------------------------------------- self test
def _selftest():
    import random
    import tempfile
    global HIST_PATH
    random.seed(7)
    HIST_PATH = os.path.join(tempfile.mkdtemp(), "h.json")
    games = {}
    for i in range(400):
        v = random.gauss(0, 1)                      # a delta; the bigger it is, the likelier the favored side wins
        p_away = 1 / (1 + math.exp(-1.6 * v))
        away_won = random.random() < p_away
        m = -random.randint(1, 20) if away_won else random.randint(1, 20)
        games[f"2026|A{i}@H{i}"] = {"away": f"A{i}", "home": f"H{i}", "season": 2026, "deltas": {"Fake Delta": v, "Noise Delta": random.gauss(0, 1)},
                                    "home_margin": m, "finals_checked": True}
    res = analyze({"games": games})
    t = res["deltas"]["Fake Delta"]["tiers"]
    rates = [x[0] / x[1] for x in t]
    assert rates[3] > rates[0] + 0.15, rates                       # a real signal gets a clearly higher massive tier
    n_rates = [x[0] / x[1] for x in res["deltas"]["Noise Delta"]["tiers"]]
    assert abs(n_rates[3] - 0.5) < 0.2, n_rates                    # pure noise stays near 50%
    assert sum(x[1] for x in t) > 350
    # sign convention: delta > 0 favors away; away won => home_margin < 0 => counted as a win for the leader
    one = {"games": {f"2026|a{i}@h{i}": {"away": "a", "home": "h", "season": 2026, "deltas": {"X": 1.0 + i}, "home_margin": -3, "finals_checked": True}
                     for i in range(30)}}
    assert all(x[0] == x[1] for x in analyze(one)["deltas"]["X"]["tiers"] if x[1])
    lines = report_lines(res)
    assert any("Fake Delta" in l for l in lines)
    sp = os.path.join(os.path.dirname(HIST_PATH), "scale.json")
    assert write_scale(res, sp) and json.load(open(sp))["deltas"]["Fake Delta"]["massive"] > 55
    assert not write_scale({"n_graded": 10, "deltas": {}}, sp + "x")
    # record() with no network still saves and is first-sighting only
    globals()["_fetch_finals"] = lambda season, cws: None
    record({("AWAY ONE", "HOME ONE"): {"Line Yards Delta": 0.5}}, season=2026)
    record({("AWAY ONE", "HOME ONE"): {"Line Yards Delta": 9.9}}, season=2026)
    saved = _load()["games"]["2026|AWAY ONE@HOME ONE"]["deltas"]["Line Yards Delta"]
    assert saved == 0.5, saved
    print("selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        main()
