"""
Win probability + predicted winner for THE NUTS.

WHAT IT DOES
  For every matchup it looks at the five stats highlighted yellow on the grid -- SOR, points per game (Off PPG), FEI,
  Offensive Efficiency delta, Net Success Rate -- counts how many of them favor each team, adds how big the
  Offensive Efficiency gap is, and turns that into a win % for the home team. The side with the higher win % is the
  predicted winner (yellow on The Nuts); when that is NOT who Vegas has favored, the whole row is highlighted.

THE MODEL (a 3-number logistic regression, fit on every graded game in the history files)
      z      = b0 + b_count * (agreeing-stat count) + b_gap * (Off Efficiency gap in points / 5)
      P(home win) = 1 / (1 + e^-z)      (kept between 5% and 95% -- 150 games can't justify more certainty than that)
  * agreeing-stat count = (FEI vote + Off PPG vote + Net Success Rate vote + Off Eff vote) / 4, each vote +1 for the
    home team / -1 for the away team (0 when tied or missing), plus SOR as a HALF vote (see below).
  * Off Efficiency gap = 0.3 x ((home Off Eff - away Def Eff) - (away Off Eff - home Def Eff)), the same double
    difference the grid's "Offensive Efficiency Delta" row shows (sign flipped: here + = home).
  * b0 is the home-field edge (home teams won 58% of the 150 games).

WHAT THE 150-GAME BACKTEST SHOWED (cfb_stat_history.json + cfb_forecast_history.json; "led the stat" = that team won)
  alone:    Off PPG 79.9%   FEI 79.4%   Off Eff delta 83.5%   Net Success Rate 71.4%
  together: all 4 agree 92.9% (79/85)   3 of 4 agree 63.3% (19/30)   2-2 split 70.6% (12/17, mostly the home team)
  model, tested on games it was NOT trained on (leave-one-out): picks the winner ~83% (vs 58% for "always home"),
  and the win % it prints runs close to how often those picks really won.
  Net Success Rate adds almost nothing once FEI, PPG and Off Eff are in (it is mostly the same information) -- it still
  counts in the vote, it just doesn't move the number much on its own. A bigger Off Efficiency gap = a bigger win %.

HONEST LIMITS
  * The history only recorded WHO LED each stat, not by how much, so the only stat whose gap size could be backtested is
    Off Efficiency (the forecast history kept it in points). FEI/PPG/NSR gaps can't be weighed by size yet.
  * SOR has no pre-game history, so it is NOT fit: it counts as a half vote (an assumption). The Nuts tracker saves each
    game's pre-game SOR and these inputs, so it can be fit for real once enough games are graded.
  * History stats are "current-at-the-time" snapshots (see PROJECT_NOTES), and ~150 games is small: treat a 60% as
    "lean", not "lock". Every run re-fits from the history files (once the history has 150+ games; below that the built-in numbers are used), so the numbers sharpen as games finish.
"""
import os
import re
import json
import math

_HERE = os.path.dirname(os.path.abspath(__file__))
_SEARCH_DIRS = [_HERE, os.path.join(_HERE, "research_and_backtests"), os.path.dirname(_HERE),
                os.path.join(os.path.dirname(_HERE), "research_and_backtests")]

# Fit on the 150 real games on 2026-10-07 (ridge 1.0, slopes kept >= 0). Used when history can't be read.
DEFAULT_PARAMS = {"b0": 0.33, "b_count": 0.96, "b_gap": 0.69}
SOR_VOTE_WEIGHT = 0.5      # SOR counts as half a vote -- an assumption, not a fit (no pre-game SOR history yet)
P_MIN, P_MAX = 0.05, 0.95
MIN_GAMES_TO_REFIT = 150   # the built-in defaults were fit on 150 games; only re-fit once history has at least that many
RIDGE = 1.0

_params_cache = {}


def _sign(x):
    if x is None:
        return 0
    return 1 if x > 0 else (-1 if x < 0 else 0)


def _sigmoid(z):
    z = max(min(z, 30.0), -30.0)
    return 1.0 / (1.0 + math.exp(-z))


# ---------------------------------------------------------------- fitting
def _solve(A, b):
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for i in range(n):
        piv = max(range(i, n), key=lambda r: abs(M[r][i]))
        if abs(M[piv][i]) < 1e-12:
            return None
        M[i], M[piv] = M[piv], M[i]
        for r in range(i + 1, n):
            f = M[r][i] / M[i][i]
            for c in range(i, n + 1):
                M[r][c] -= f * M[i][c]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (M[i][n] - sum(M[i][c] * x[c] for c in range(i + 1, n))) / M[i][i]
    return x


def fit_logistic(rows, lam=RIDGE, iters=60):
    """rows = [(count_feature, gap_feature, home_won 0/1)]. Returns (b0, b_count, b_gap) with both slopes >= 0."""
    k = 3
    free = [0, 1, 2]
    w = [0.0, 0.0, 0.0]
    for _ in range(iters):
        g = [0.0] * k
        H = [[0.0] * k for _ in range(k)]
        for c, gp, y in rows:
            x = (1.0, c, gp)
            p = _sigmoid(sum(w[j] * x[j] for j in range(k)))
            for a in range(k):
                g[a] += x[a] * (p - y)
                for b in range(k):
                    H[a][b] += x[a] * x[b] * p * (1 - p)
        for j in (1, 2):
            g[j] += lam * w[j]
            H[j][j] += lam
        for j in range(k):
            H[j][j] += 1e-9
        idx = [j for j in free]
        step = _solve([[H[a][b] for b in idx] for a in idx], [g[a] for a in idx])
        if step is None:
            break
        for a, j in enumerate(idx):
            w[j] -= step[a]
        for j in (1, 2):
            if j in free and w[j] < 0:
                w[j] = 0.0
                free.remove(j)
    return tuple(w)


def _load_history_rows():
    sh = fh = None
    for d in _SEARCH_DIRS:
        p = os.path.join(d, "cfb_stat_history.json")
        if sh is None and os.path.exists(p):
            try:
                sh = json.load(open(p)).get("games")
            except Exception:
                pass
        p = os.path.join(d, "cfb_forecast_history.json")
        if fh is None and os.path.exists(p):
            try:
                fh = json.load(open(p)).get("games")
            except Exception:
                pass
    if not sh:
        return []
    fh = fh or {}
    rows = []
    for k, g in sh.items():
        v = g.get("votes") or {}
        home_won = 1 if g.get("winner") == g.get("home") else 0
        s = 1 if home_won else -1                  # votes are stored winner-oriented (+1 = led the stat and won)

        def hv(key):
            x = v.get(key)
            return 0 if x is None else x * s
        eff = (fh.get(k, {}).get("factors") or {}).get("efficiency")
        cnt = (hv("FEI") + hv("Off_PPG") + hv("NSR") + _sign(eff)) / 4.0
        rows.append((cnt, (eff or 0.0) / 5.0, home_won))
    return rows


def get_params(verbose=True):
    if "p" in _params_cache:
        return _params_cache["p"]
    p, note = dict(DEFAULT_PARAMS), "built-in defaults (150-game fit, 2026-10-07)"
    try:
        rows = _load_history_rows()
        if len(rows) >= MIN_GAMES_TO_REFIT:
            b0, bc, bg = fit_logistic(rows)
            if (bc + bg) > 0:
                p = {"b0": b0, "b_count": bc, "b_gap": bg}
                ok = sum(1 for c, gp, y in rows if (_sigmoid(b0 + bc * c + bg * gp) > 0.5) == (y == 1))
                note = f"re-fit on {len(rows)} graded games in the history files (in-sample picks {ok}/{len(rows)})"
    except Exception as e:
        note = f"built-in defaults (history re-fit skipped: {e})"
    _params_cache["p"] = p
    _params_cache["note"] = note
    if verbose:
        print(f" -> win-% model: {note}; home edge {p['b0']:+.2f}, stat-count {p['b_count']:.2f}, gap {p['b_gap']:.2f}")
    return p


# ---------------------------------------------------------------- SOR
_SOR_ALIASES = {"FLORIDA INTL": "FLORIDA INTERNATIONAL", "UMASS": "MASSACHUSETTS", "N ILLINOIS": "NORTHERN ILLINOIS",
                "S FLORIDA": "SOUTH FLORIDA", "S ALABAMA": "SOUTH ALABAMA", "UCONN": "CONNECTICUT"}
_sor_cache = {}


def sor_for(team):
    if "look" not in _sor_cache:
        look = {}
        for d in _SEARCH_DIRS:
            p = os.path.join(d, "cfb_espn_power_index_cache.json")
            if os.path.exists(p):
                try:
                    teams = json.load(open(p)).get("teams") or {}
                    look = {re.sub(r"\s+", " ", k).strip().upper(): (v or {}).get("SOR") for k, v in teams.items()}
                    break
                except Exception:
                    pass
        _sor_cache["look"] = look
    k = re.sub(r"\s+", " ", team or "").strip().upper()
    for cand in (k, _SOR_ALIASES.get(k), re.sub(r" ST$", " STATE", k), re.sub(r"^S ", "SOUTH ", k)):
        if cand and _sor_cache["look"].get(cand) is not None:
            try:
                return float(_sor_cache["look"][cand])
            except (TypeError, ValueError):
                return None
    return None


# ---------------------------------------------------------------- prediction
STAT_LABELS = {"fei": "FEI", "ppg": "PPG", "nsr": "NSR", "eff": "Off Eff", "sor": "SOR"}


def predict(inp, away_name=None, home_name=None, params=None):
    """inp = {'fei': (away, home), 'ppg': (away_off_ppg, home_off_ppg), 'nsr': (away, home),
              'oeff': (away, home), 'deff': (away, home)}  (any value may be None).
    Returns a dict with p_home, pick ('home'/'away'), p_pick, votes (+1 home / -1 away), n_for, n_votes, backers."""
    params = params or get_params(verbose=False)

    def pair(key):
        v = inp.get(key) or (None, None)
        return v if len(v) == 2 else (None, None)

    def lead(key):
        a, h = pair(key)
        return 0 if None in (a, h) else _sign(h - a)

    votes = {"fei": lead("fei"), "ppg": lead("ppg"), "nsr": lead("nsr")}
    ao, ho = pair("oeff")
    ad, hd = pair("deff")
    eff_pts = None
    if None not in (ao, ho, ad, hd):
        eff_pts = 0.3 * ((ho - ad) - (ao - hd))
    votes["eff"] = _sign(eff_pts)
    sa = sor_for(away_name) if away_name else None
    sh = sor_for(home_name) if home_name else None
    votes["sor"] = 0 if None in (sa, sh) else _sign(sa - sh)         # lower SOR rank = better; + = home

    count = (votes["fei"] + votes["ppg"] + votes["nsr"] + votes["eff"] + SOR_VOTE_WEIGHT * votes["sor"]) / 4.0
    z = params["b0"] + params["b_count"] * count + params["b_gap"] * ((eff_pts or 0.0) / 5.0)
    p_home = min(max(_sigmoid(z), P_MIN), P_MAX)
    pick = "home" if p_home >= 0.5 else "away"
    s = 1 if pick == "home" else -1
    backers = [STAT_LABELS[k] for k in ("fei", "ppg", "nsr", "eff", "sor") if votes[k] == s]
    n_votes = sum(1 for k in votes if votes[k] != 0)
    return {"p_home": p_home, "pick": pick, "p_pick": p_home if pick == "home" else 1 - p_home,
            "votes": votes, "n_for": len(backers), "n_votes": n_votes, "backers": backers,
            "eff_pts": eff_pts, "sor": (sa, sh)}


def attach_winprob(results):
    """Adds wp_* keys to each result dict (needs r['wp_inputs'] from spread.py's parser). Call AFTER the Vegas lines
    are attached so wp_vs_vegas can be set: 'agree' / 'DISAGREE' / '' (no line, or pick'em)."""
    params = get_params()
    for r in results:
        inp = r.get("wp_inputs")
        if not inp:
            continue
        try:
            w = predict(inp, r.get("away"), r.get("home"), params)
        except Exception as e:
            print(f" -> win % skipped for {r.get('away')} @ {r.get('home')} ({e})")
            continue
        r["wp_home"], r["wp_pick"], r["wp_pick_prob"] = w["p_home"], w["pick"], w["p_pick"]
        r["wp_n_for"], r["wp_n_votes"], r["wp_backers"], r["wp_votes"] = w["n_for"], w["n_votes"], w["backers"], w["votes"]
        r["wp_pick_team"] = r["home"] if w["pick"] == "home" else r["away"]
        vg = r.get("vegas")
        if vg is None or vg == 0:
            r["wp_vs_vegas"] = ""
        else:
            vegas_side = "home" if vg < 0 else "away"
            r["wp_vs_vegas"] = "agree" if vegas_side == w["pick"] else "DISAGREE"
    return results


# ---------------------------------------------------------------- self test / CLI
def _selftest():
    assert _sign(2) == 1 and _sign(-0.1) == -1 and _sign(None) == 0
    # fitter recovers a known relationship (pure-python Newton)
    import random
    random.seed(1)
    rows = []
    for _ in range(2000):
        c = random.choice([-1, -0.5, 0, 0.5, 1])
        gp = random.uniform(-3, 3)
        p = _sigmoid(0.3 + 1.2 * c + 0.5 * gp)
        rows.append((c, gp, 1 if random.random() < p else 0))
    b0, bc, bg = fit_logistic(rows, lam=0.0001)
    assert abs(b0 - 0.3) < 0.15 and abs(bc - 1.2) < 0.2 and abs(bg - 0.5) < 0.1, (b0, bc, bg)
    # all four testable stats for the home team + big efficiency gap -> strong home pick (> 90%)
    inp = {"fei": (0.1, 0.9), "ppg": (20, 35), "nsr": (0.0, 0.2), "oeff": (30, 60), "deff": (30, 30)}
    w = predict(inp, params=DEFAULT_PARAMS)
    assert w["pick"] == "home" and w["p_pick"] > 0.9 and w["n_for"] == 4, w
    # mirror image -> away pick, same strength
    inp2 = {"fei": (0.9, 0.1), "ppg": (35, 20), "nsr": (0.2, 0.0), "oeff": (60, 30), "deff": (30, 30)}
    w2 = predict(inp2, params=DEFAULT_PARAMS)
    assert w2["pick"] == "away" and w2["p_pick"] > 0.8, w2
    # a 2-2 split with no gap leans home (home edge only), well under 70%
    inp3 = {"fei": (0.5, 0.1), "ppg": (30, 20), "nsr": (0.0, 0.1), "oeff": (40, 45), "deff": (45, 45)}
    w3 = predict(inp3, params=DEFAULT_PARAMS)
    assert 0.5 <= w3["p_home"] < 0.7 or w3["pick"] == "away", w3
    # Vegas comparison
    res = [{"away": "A", "home": "B", "wp_inputs": inp, "vegas": 3.5}, {"away": "C", "home": "D", "wp_inputs": inp, "vegas": -3.5},
           {"away": "E", "home": "F", "wp_inputs": inp, "vegas": None}]
    attach_winprob(res)
    assert [r["wp_vs_vegas"] for r in res] == ["DISAGREE", "agree", ""], [r["wp_vs_vegas"] for r in res]
    print("selftest OK")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
    else:
        rows = _load_history_rows()
        print(f"{len(rows)} graded games found in the history files")
        if rows:
            b0, bc, bg = fit_logistic(rows)
            ok = sum(1 for c, gp, y in rows if (_sigmoid(b0 + bc * c + bg * gp) > 0.5) == (y == 1))
            print(f"fit: home edge {b0:+.3f}, stat-count {bc:.3f}, gap {bg:.3f}; in-sample picks {ok}/{len(rows)} = {ok / len(rows):.1%}")
