"""
cfb_ats_odds.py -- Vegas lines + against-the-spread (ATS) records for The Nuts (spread.py).   (added 2026-10-06)

What it gives spread.py, for every game on the slate:
  * the Vegas line (home-team spread, negative = home favored) and the over/under, from CFBD's /lines endpoint
  * each team's ATS record this season vs. those lines: overall, and AT HOME / ON THE ROAD
    (W-L-P, cover %, and average margin vs. the number)

One CFBD call (/lines?year=...) is spent at most every 6 hours; every good pull is saved to cfb_odds_cache.json and
that file is used if CFBD refuses (quota / network) -- same fallback idea as the CFBD advanced-stats pull.

NOT YET LIVE-VERIFIED (written where CFBD couldn't be reached). Run it STANDALONE first:
        python3 cfb_ats_odds.py            # pulls, prints the raw field names it saw, a few sample games + records
        python3 cfb_ats_odds.py --selftest # offline logic test with made-up games (no network)
CFBD's documented /lines fields: homeTeam, awayTeam, homeScore, awayScore, startDate, week, and lines[] with
provider, spread (negative = HOME favored), formattedSpread ("Kansas St -4.5"), overUnder.
"""
import os, re, sys, json, time, unicodedata
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(_HERE, "cfb_odds_cache.json")
CACHE_MAX_AGE_HOURS = 6
_CFBD_BASE = "https://api.collegefootballdata.com"
# first provider in this list that has a spread wins; otherwise the first line that has any spread
PROVIDER_PREFERENCE = ["consensus", "DraftKings", "ESPN Bet", "Bovada", "teamrankings", "Caesars", "BetMGM"]


# ---------------------------------------------------------------- name matching
_FOLD = {"connecticut": "uconn", "central florida": "ucf", "lsu": "louisiana state", "ole miss": "mississippi",
         "umass": "massachusetts", "florida intl": "florida international", "fiu": "florida international",
         "ul monroe": "louisiana monroe", "sam houston": "sam houston state", "app state": "appalachian state",
         "miami fl": "miami", "miami florida": "miami", "miami ohio": "miami oh", "pitt": "pittsburgh",
         "texas san antonio": "utsa", "ut san antonio": "utsa", "san jose state": "san jose state",
         "hawaii": "hawaii", "middle tennessee state": "middle tennessee", "middle tenn": "middle tennessee",
         "georgia so": "georgia southern", "n illinois": "northern illinois", "w michigan": "western michigan",
         "e michigan": "eastern michigan", "c michigan": "central michigan", "w kentucky": "western kentucky",
         "e carolina": "east carolina", "s alabama": "south alabama", "s florida": "south florida",
         "sacramento st": "sacramento state",
         "southern mississippi": "southern miss", "southern miss": "southern miss",
         "north carolina state": "nc state", "north carolina st": "nc state", "nc st": "nc state",
         "n c state": "nc state", "ncsu": "nc state",
         "ga southern": "georgia southern", "la tech": "louisiana tech", "middle tenn st": "middle tennessee",
         "mid tenn": "middle tennessee", "s carolina": "south carolina", "n carolina": "north carolina",
         "w virginia": "west virginia", "s diego state": "san diego state", "e washington": "eastern washington"}


def _base_key(name):
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode("ascii").lower()
    s = s.replace("&", " and ").replace("'", "")
    s = re.sub(r"[().,]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def name_keys(name):
    """All spellings a team might be written as, folded to comparable keys (a match = any key in common)."""
    b = _base_key(name)
    keys = {b}
    keys.add(_FOLD.get(b, b))
    more = set()
    for k in list(keys):
        k2 = re.sub(r"\bst$", "state", k)            # "kansas st"  -> "kansas state"
        more.add(k2)
        more.add(re.sub(r"\bstate$", "st", k))       # "kansas state" -> "kansas st"
        more.add(k.replace(" and ", " "))
    keys |= more
    for k in list(keys):
        keys.add(_FOLD.get(k, k))
    return keys


# ---------------------------------------------------------------- fetch + cache
def _load_cache():
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _save_cache(year, games):
    try:
        with open(CACHE_PATH, "w") as f:
            json.dump({"season_year": year, "fetched_at": datetime.now().isoformat(), "games": games}, f)
    except OSError as e:
        print(f" -> ⚠ could not write the odds cache ({e})")


def fetch_lines(year, force=False):
    """Returns (games list, note). Uses a fresh-enough cache, else CFBD, else the stale cache."""
    cache = _load_cache()
    if cache and cache.get("season_year") == year and cache.get("games") and not force:
        try:
            age_h = (datetime.now() - datetime.fromisoformat(cache["fetched_at"])).total_seconds() / 3600.0
        except Exception:
            age_h = 1e9
        if age_h < CACHE_MAX_AGE_HOURS:
            return cache["games"], f"odds cache is {age_h:.1f}h old -- reused, no CFBD call spent"
    key = os.environ.get("CFBD_API_KEY")
    if not key:
        try:
            import cfb_working_schedule as _cws          # same key the rest of the project already uses
            key = _cws.CFBD_API_KEY
        except Exception:
            key = None
    try:
        import requests
        resp = requests.get(f"{_CFBD_BASE}/lines", params={"year": year, "seasonType": "regular"},
                            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not (isinstance(data, list) and data):
            raise ValueError("CFBD /lines returned no games")
        first = data[0]
        print(f" -> [debug] CFBD /lines first record keys: {list(first.keys())}; "
              f"lines[0] keys: {list((first.get('lines') or [{}])[0].keys())}")
        _save_cache(year, data)
        return data, f"pulled {len(data)} games from CFBD /lines"
    except Exception as e:
        if cache and cache.get("games"):
            return cache["games"], f"CFBD /lines failed ({e}) -- using the saved pull from {cache.get('fetched_at')}"
        return [], f"CFBD /lines failed ({e}) and there is no saved pull -- Vegas/ATS columns will show N/A"


# ---------------------------------------------------------------- parsing
def _num(x):
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def pick_line(game):
    """Returns (home_spread, over_under, provider) for one CFBD game record, or (None, None, None)."""
    lines = [l for l in (game.get("lines") or []) if isinstance(l, dict)]
    with_spread = [l for l in lines if _num(l.get("spread")) is not None]
    if not with_spread:
        return None, None, None
    chosen = None
    for p in PROVIDER_PREFERENCE:
        chosen = next((l for l in with_spread if str(l.get("provider", "")).lower() == p.lower()), None)
        if chosen:
            break
    chosen = chosen or with_spread[0]
    spread = _num(chosen.get("spread"))              # CFBD: negative = HOME favored
    # sanity check against formattedSpread ("Kansas St -4.5") -- if it names a team and the sign disagrees, trust it
    fs = chosen.get("formattedSpread")
    if isinstance(fs, str):
        m = re.match(r"^(.*?)\s+([+-]?\d+(?:\.\d+)?)$", fs.strip())
        if m:
            fav_val = float(m.group(2))
            if fav_val != 0:
                names = name_keys(m.group(1))
                if names & name_keys(game.get("homeTeam")):
                    spread = fav_val
                elif names & name_keys(game.get("awayTeam")):
                    spread = -fav_val
    ou = next((_num(l.get("overUnder")) for l in [chosen] + with_spread if _num(l.get("overUnder")) is not None), None)
    return spread, ou, chosen.get("provider")


def spread_bucket(team_spread):
    """team_spread = that team's own number (negative = favorite). -> (bucket key, role). Buckets: close (inside 3), 3-9.5, 10+."""
    a = abs(team_spread)
    role = "pk" if a < 3 else ("fav" if team_spread < 0 else "dog")
    if a < 3:
        return "close", "pk"
    return (f"{role}10+" if a >= 10 else f"{role}3-9.5"), role


def spread_label(team_spread):
    a = abs(team_spread)
    if a < 3:
        return "close game"
    return ("10+ " if a >= 10 else "3-9 ") + ("fav" if team_spread < 0 else "dog")


def build_ats(games):
    """team-key -> {'all','home','away'} each {'w','l','p','margin_sum','n'}; also per-team display name."""
    recs = {}

    def bump(team, venue, result, cover_margin, team_spread=None):
        r = recs.setdefault(team, {v: {"w": 0, "l": 0, "p": 0, "m": 0.0, "n": 0} for v in ("all", "home", "away")})
        for v in ("all", venue):
            r[v][result] += 1
            r[v]["m"] += cover_margin
            r[v]["n"] += 1
        if team_spread is not None:      # situation records (2026-10-07): by spread size/role, home and road games together
            sit = r.setdefault("sit", {})
            for key in (spread_bucket(team_spread)[0], "role:" + spread_bucket(team_spread)[1]):
                x = sit.setdefault(key, {"w": 0, "l": 0, "p": 0, "m": 0.0, "n": 0})
                x[result] += 1
                x["m"] += cover_margin
                x["n"] += 1

    for g in games:
        hs, as_ = _num(g.get("homeScore")), _num(g.get("awayScore"))
        if hs is None or as_ is None:
            continue
        spread, _ou, _p = pick_line(g)
        if spread is None:
            continue
        home_cover = (hs - as_) + spread        # >0: home covered
        res_home = "w" if home_cover > 0 else ("l" if home_cover < 0 else "p")
        res_away = {"w": "l", "l": "w", "p": "p"}[res_home]
        bump(g.get("homeTeam"), "home", res_home, home_cover, spread)       # spread = home team's number (negative = home favored)
        bump(g.get("awayTeam"), "away", res_away, -home_cover, -spread)
    return recs


def fmt_record(r):
    if not r or not r.get("n"):
        return "--"
    dec = r["w"] + r["l"]
    pct = f"{100.0 * r['w'] / dec:.0f}%" if dec else "--"
    return f"{r['w']}-{r['l']}-{r['p']} ({pct}, {r['m'] / r['n']:+.1f}/g)"


# ---------------------------------------------------------------- what spread.py calls
def attach_odds(results, year=None, games=None):
    """Adds r['vegas'] (home spread), r['vegas_total'], r['vegas_provider'], r['ats_away'] (the away team's
    {'all','away'} records) and r['ats_home'] ({'all','home'}) to each result dict. Never raises."""
    year = year or datetime.now().year
    try:
        if games is None:
            games, note = fetch_lines(year)
            print(f" -> Vegas / ATS: {note}")
        recs = build_ats(games)
        rec_by_key = {}
        for team, r in recs.items():
            for k in name_keys(team):
                rec_by_key.setdefault(k, []).append(team)

        def find_team(name):
            hits = set()
            for k in name_keys(name):
                hits.update(rec_by_key.get(k, []))
            return next(iter(hits)) if len(hits) == 1 else (None if not hits else sorted(hits)[0])

        # upcoming games by (home-key, away-key)
        upcoming = {}
        for g in games:
            if _num(g.get("homeScore")) is None:
                for hk in name_keys(g.get("homeTeam")):
                    for ak in name_keys(g.get("awayTeam")):
                        upcoming[(hk, ak)] = g
        no_line, no_ats = [], []
        for r in results:
            g = None
            for hk in name_keys(r["home"]):
                for ak in name_keys(r["away"]):
                    g = g or upcoming.get((hk, ak))
            if g:
                sp, ou, prov = pick_line(g)
                r["vegas"], r["vegas_total"], r["vegas_provider"] = sp, ou, prov
            else:
                r["vegas"] = r["vegas_total"] = r["vegas_provider"] = None
            if r["vegas"] is None:
                no_line.append(f"{r['away']} @ {r['home']}")
            at, ht = find_team(r["away"]), find_team(r["home"])
            r["sit_away"] = r["sit_home"] = None
            if r["vegas"] is not None and at and ht:
                for _side, _t, _sp in (("sit_away", at, -r["vegas"]), ("sit_home", ht, r["vegas"])):
                    _b, _role = spread_bucket(_sp)
                    _sit = recs[_t].get("sit", {})
                    r[_side] = {"label": spread_label(_sp), "role": _role, "bucket": _sit.get(_b), "role_rec": _sit.get("role:" + _role)}
            r["ats_away"] = ({"all": recs[at]["all"], "away": recs[at]["away"]} if at else None)
            r["ats_home"] = ({"all": recs[ht]["all"], "home": recs[ht]["home"]} if ht else None)
            if not at or not ht:
                no_ats.append(r["away"] if not at else r["home"])
        if no_line:
            print(f" -> Vegas: no line found yet for {len(no_line)} game(s): {no_line[:8]}{' ...' if len(no_line) > 8 else ''}")
        if no_ats:
            print(f" -> ATS: no spread-graded games found for: {sorted(set(no_ats))[:10]}")
    except Exception as e:
        print(f" -> Vegas / ATS skipped ({e})")
        for r in results:
            r.setdefault("vegas", None); r.setdefault("vegas_total", None); r.setdefault("vegas_provider", None)
            r.setdefault("ats_away", None); r.setdefault("ats_home", None); r.setdefault("sit_away", None); r.setdefault("sit_home", None)
    return results


# ---------------------------------------------------------------- selftest / standalone
def _selftest():
    games = [
        {"homeTeam": "Kennesaw State", "awayTeam": "Jacksonville State", "homeScore": 20, "awayScore": 27,
         "lines": [{"provider": "Bovada", "spread": -3.0, "formattedSpread": "Kennesaw State -3", "overUnder": 51.5}]},
        {"homeTeam": "Kennesaw State", "awayTeam": "Troy", "homeScore": 31, "awayScore": 28,
         "lines": [{"provider": "DraftKings", "spread": 3.0, "overUnder": 50}]},
        {"homeTeam": "Troy", "awayTeam": "Jacksonville State", "homeScore": 24, "awayScore": 17,
         "lines": [{"provider": "DraftKings", "spread": -7.0}]},
        {"homeTeam": "Kennesaw State", "awayTeam": "Jacksonville State", "homeScore": None, "awayScore": None,
         "lines": [{"provider": "DraftKings", "spread": 0.5, "formattedSpread": "Jacksonville State -0.5", "overUnder": 55.0}]},
        {"homeTeam": "South Florida", "awayTeam": "UTSA", "homeScore": None, "awayScore": None,
         "lines": [{"provider": "Bovada", "spread": 2.0, "formattedSpread": "South Florida -2", "overUnder": 60.5}]},  # sign conflict
    ]
    recs = build_ats(games)
    k, j, t = recs["Kennesaw State"], recs["Jacksonville State"], recs["Troy"]
    g = lambda r: (r["w"], r["l"], r["p"])
    assert g(k["all"]) == (1, 1, 0) and g(k["home"]) == (1, 1, 0) and g(k["away"]) == (0, 0, 0), k
    assert g(j["all"]) == (1, 0, 1) and g(j["away"]) == (1, 0, 1) and g(j["home"]) == (0, 0, 0), j
    assert g(t["all"]) == (0, 1, 1) and g(t["home"]) == (0, 0, 1) and g(t["away"]) == (0, 1, 0), t
    res = [{"away": "JACKSONVILLE ST", "home": "KENNESAW STATE"}, {"away": "UTSA", "home": "S FLORIDA"}]
    attach_odds(res, year=2026, games=games)
    assert res[0]["vegas"] == 0.5 and res[0]["vegas_total"] == 55.0, res[0]
    assert res[1]["vegas"] == -2.0, res[1]                      # formattedSpread overrides the conflicting sign
    assert g(res[0]["ats_away"]["all"]) == (1, 0, 1) and g(res[0]["ats_home"]["home"]) == (1, 1, 0), res[0]
    assert res[1]["ats_home"] is None                           # no graded games yet for South Florida
    print("selftest OK")
    print("  Jacksonville St:", fmt_record(j["all"]), "| away:", fmt_record(j["away"]))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        yr = datetime.now().year
        games, note = fetch_lines(yr, force="--force" in sys.argv)
        print(note)
        recs = build_ats(games)
        print(f"{len(games)} games, {len(recs)} teams with at least one spread-graded game")
        upcoming = [x for x in games if _num(x.get("homeScore")) is None and pick_line(x)[0] is not None][:6]
        for x in upcoming:
            print("  upcoming:", x.get("awayTeam"), "@", x.get("homeTeam"), pick_line(x))
        for team in list(recs)[:6]:
            print(f"  {team}: all {fmt_record(recs[team]['all'])} | home {fmt_record(recs[team]['home'])} | away {fmt_record(recs[team]['away'])}")
