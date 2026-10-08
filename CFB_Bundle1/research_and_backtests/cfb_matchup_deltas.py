"""
cfb_matchup_deltas.py -- real, live-computed "matchup delta" metrics, per
the 3 uploaded reference sheets (2026-09-27):
  - cfb_matchup_delta_manual.pdf              ("the manual" below)
  - cfb_matchup_evaluation_deltas.pdf          ("sheet 2" below)
  - cfb_matchup_evaluation_deltas2_copy.pdf    ("the blueprint" below,
    13 core deltas with a worked Tulsa-vs-Arkansas example for each --
    used here as a correctness check on every formula's arithmetic, and
    to pull the exact real-world "Analytical Scale" tables
    attached beside/below each grid)

Every delta below is computed ONLY from real stats cfb_matchup_deep_dive.py
already fetches into stats_lookup -- no new network calls, nothing faked.
Anything missing on either side returns None (rendered as "--"), never a
guessed number.

Two delta SHAPES, matching the placement instruction ("on the ones
that end up a single number on the side it favors... on the ones that
have 2 numbers put it on the team side beside that grid"):

  SINGLE -- the manual's "Universal Matchup Formula Rule":
      Bracket A = Away Off  - Home Def
      Bracket B = Home Off  - Away Def
      Final Delta = Bracket A - Bracket B
    One number. Positive favors away, negative favors home. Used for every
    stat the manual gives its own bucketed real-world scale for (PPG, YPG,
    YPP, Pace, RZ%, 3rd Down%, Line Yards, Stuff Rate), plus Net Efficiency
    (OFEI/DFEI -- "the Vegas Filter", same Bracket-A/Bracket-B shape,
    confirmed against the blueprint's own Tulsa/Arkansas worked example:
    -0.53 - 0.70 = -1.23, exactly what universal_single() reproduces) and
    Net Success Rate / FEI (already per-team composite numbers, so it's
    just Away - Home directly, no bracket needed -- the add, "add an
    fei delta" (2026-09-27), same composite shape as Net Success Rate
    since FEI is on the same real OFEI/DFEI-family scale).

  PAIRED -- each team's own one-sided real edge (that team's real Off stat
    minus the OPPOSING team's real Def stat), not collapsed further. Used
    for every delta sheet 2 / the blueprint present as two side-by-side
    numbers rather than a single final one: Havoc, Power Success (4th &
    Inches), Passing Explosiveness (Vertical Lightning), PPA (Passing Down
    Panic Index), the Fraud Gap ratio, Stay-on-Schedule Rushing (OSR/DSR),
    and the two volume-vs-efficiency pairs (Air Depth, Per-Carry Reality).

Where the exact same underlying stat appears in BOTH the manual's
bucketed/single system and sheet 2 / the blueprint's paired framing (3rd
Down%, Red Zone%, Line Yards, Stuff Rate), the manual's single-number
version is used -- it's the more complete treatment (it has a real
worked-out scale), and showing the same comparison twice in two different
shapes would just be clutter, not new information.

Correctness check against the blueprint's own Tulsa-vs-Arkansas worked
numbers (2026-09-27, done by hand against every formula below before
wiring this into the report):
  - Net Efficiency Delta: universal_single(OFEI, DFEI) with away=Tulsa
    (-0.15 OFEI / -0.40 DFEI), home=Arkansas (0.30 OFEI / 0.38 DFEI) ->
    Bracket A = -0.15 - 0.38 = -0.53, Bracket B = 0.30 - (-0.40) = 0.70,
    Final = -0.53 - 0.70 = -1.23 -- matches the blueprint's own stated
    -1.23 exactly.
  - Stay-on-Schedule Rushing Delta: the blueprint's own worked arithmetic
    (39.5% - 39.8% = -0.3%, 47.2% - 43.0% = +4.2%) uses OSR/DSR (bcftoys'
    real percent-scale success-rate ratings, already pulled and already
    shown in this card's own Advanced Ratings block), NOT the CFBD
    Off_Success_Rate/Def_Success_Rate fraction columns an earlier draft of
    this file mistakenly wired up -- fixed below to paired_edge(OSR, DSR),
    which reproduces both of the blueprint's own worked numbers exactly.
  - Fraud Gap, Vertical Lightning, Passing Down Panic Index, Air Depth, 4th
    & Inches, Havoc/Chaos -- every other worked Tulsa/Arkansas number in
    the blueprint was independently reproduced by hand against
    paired_edge()/fraud_gap()/volume_vs_efficiency() below before this was
    wired in; no other key-mapping bugs found.

Two real, disclosed limitations (not guesses -- see each docstring below):
  - "Passing Explosiveness" / "Passing Down Panic Index (PPA)" use the
    same OVERALL Off_Explosiveness/Off_PPA cfb_matchup_card_v4.py's
    existing "Passing Explosiveness" / "Advanced Ratings" rows already
    use -- CFBD's real data as currently fetched here doesn't split these
    by pass vs. rush play, so this reuses the same existing, already-
    accepted convention rather than inventing a pass-specific number that
    doesn't exist in the real pull.
  - "'Stay-on-Schedule' Rushing Delta" reuses bcftoys' real OSR/DSR
    (overall success rate, not split by rush vs. pass -- same real
    columns the Advanced Ratings block already labels "OFF SUCCESS RATE
    (OSR)" / "OPP SUCCESS RATE (DSR)"), so this is overall down-to-down
    consistency, not a rushing-specific number, same kind of real-data gap
    as the Explosiveness/PPA reuse above.

Real-data unit fix (2026-09-27, found from the first real cfb_run_all.py
run): CFBD's real stuffRate/powerSuccess/havoc.total fields, and bcftoys'
real OSR/DSR/NSR columns, all come back as a 0-1 FRACTION (confirmed from
that real run's own live-band log: "Off_Power_Success: real live
mean=0.732", "Off_Havoc: real live mean=0.142", bcftoys' own raw HTML row
literally printing ".600" for Ohio State's OSR) -- not the 0-100 PERCENT
scale this file's every "Analytical Scale" text (and the reference sheets'
own worked examples, e.g. "68.0% - 62.0% = +6.0%") is written in. This
card's placeholder Tulsa/Arkansas dict (used to validate every formula
above against the blueprint's worked numbers) happens to already be in
percent-scale for these same keys, which is exactly why that validation
never caught this -- it only surfaced once real, live CFBD/bcftoys data
actually flowed through. _get() below auto-detects and rescales just
these known-fraction fields (a real value for any of them is always well
under 1.5 in magnitude; a real PERCENT-scale value for the same stats
never is, so the two can't be confused) so every delta here reports in
the same percentage-point units its scale text describes, on both real
and placeholder/mock data, without changing anything else in the report
(stats_lookup, the heat map, and the existing Advanced Ratings display
are untouched -- this rescale is local to this module's own delta math).

PARTIAL REVERSAL: after seeing a real -53.3 "Stay-on-
Schedule Rushing Delta" (North Texas's real 0.07 OSR vs Tulsa's real 0.60
DSR -- a real, legitimate 53-point gap once rescaled, not a bug), the question was
which of these 9 fraction-scale keys actually need to be presented as a
percentage at all. The blueprint's own Analytical Scale text answers that
question directly: Stuff Rate/Power Success/Havoc are each written with an
explicit "%" in their own scale buckets ("0-2.5%", "+5.0%", "-3.0%"), but
OSR/DSR ("Stay-on-Schedule Rushing") and NSR are written in plain "pts"/
bare-number buckets, never "%". So _FRACTION_SCALE_KEYS below now only
rescales Stuff Rate/Power Success/Havoc (still genuinely percent-framed by
the blueprint's own wording); OSR/DSR/NSR are real, plain subtraction of
whatever scale bcftoys returns them in (a 0-1 fraction), same as every
non-fraction stat in this file already was. Their own Analytical Scale
buckets below are divided by 100 to match (the underlying real evidence
those buckets were built on -- the 2026-09-29 54-game NSR recalibration --
didn't change, only its units did).
"""
import math
import os
import json
import numpy as np
import pandas as pd

# Real CFBD (stuffRate/powerSuccess/havoc.total) and bcftoys (OSR/DSR/NSR)
# columns that come back as a 0-1 fraction from their real APIs, but whose
# real analytical-scale text here is written in percentage points (see the
# module docstring's "Real-data unit fix" note).
# (2026-09-30) OSR/DSR/NSR removed -- see the module docstring's "PARTIAL
# REVERSAL" note: the blueprint's own scale text never labels these "%"
# (it uses "pts"/bare numbers), unlike Stuff Rate/Power Success/Havoc which
# do, so only those 3 stay rescaled -- OSR/DSR/NSR are now real plain
# subtraction of bcftoys' raw 0-1 values, no hidden unit conversion.
_FRACTION_SCALE_KEYS = {"Off_Stuff_Rate", "Def_Stuff_Rate", "Off_Power_Success", "Def_Power_Success",
                         "Off_Havoc", "Def_Havoc"}


def _num(v):
    """Real numeric coercion -- None (never 0.0) for anything missing, so
    a missing real stat produces a missing delta, never a fabricated one."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return f


# SIGN FIX (deep-dive 3rd Down % pointed to Southern Miss when Troy had the edge on both
# sides -- 27th/80th vs 114th/108th). The old formula, (Away Off - Home Def) - (Home Off - Away Def), is only
# right when the DEFENSE number is "higher = better" (OFEI/DFEI, FEI). For every stat where the defense number is
# what it ALLOWS (PPG, YPG, YPP, 3rd Down %, Red Zone %, Line Yards, Power Success, ...), a leaky defense got
# credited as if it were stingy. Each stat now carries a direction (below): 1 = higher is better for the team
# that owns the number, -1 = lower is better. Everything is then done in "goodness" terms, so a bad defense
# always HELPS the opposing offense and a bad offense always HURTS its own side.
#   single:  Final = so*(Away Off - Home Off) - sd*(Home Def - Away Def)        (+ favors away, - favors home)
#   paired:  edge  = so*(Off - league avg)   - sd*(Opp Def - league avg)       (+ = good for that offense)
_LOWER_IS_BETTER = {
    # defense numbers that are what the defense ALLOWS
    "Def_PPG", "Def_Yds_PG", "Def_YPP", "Def_Pass_PG", "Def_Pass_Att", "Def_Rush_PG", "Def_Rush_Att",
    "Def_3rd_%", "Def_RZ_%", "Def_Line_Yards", "Def_Second_Level_Yards", "Def_Open_Field_Yards",
    "Def_Power_Success", "Def_Success_Rate", "Def_Explosiveness", "Def_PPA", "DSR",
    # offense numbers where MORE is bad for the offense
    "Off_Stuff_Rate", "Off_Havoc", "Off_Sacks_Allowed_PG", "Off_INT_PG",
}


def _dir(key):
    return -1.0 if key in _LOWER_IS_BETTER else 1.0


# League averages per stat (every FBS team's value), set once per run by cfb_matchup_deep_dive.py. Used only to
# centre the PAIRED edges. If never set (e.g. the card's own placeholder preview), paired_edge falls back to
# centring on the average of the two teams in this matchup -- still the right side, just less informative.
_LEAGUE = {}


def set_league_means(stats_lookup):
    _LEAGUE.clear()
    try:
        for col in stats_lookup.columns:
            vals = pd.to_numeric(stats_lookup[col], errors="coerce").dropna()
            if len(vals) < 20:
                continue
            v = vals.values.astype(float)
            if col in _FRACTION_SCALE_KEYS:
                v = np.where(np.abs(v) <= 1.5, v * 100.0, v)
            _LEAGUE[col] = float(np.mean(v))
    except Exception:
        _LEAGUE.clear()


def _get(ts, key):
    if not hasattr(ts, 'get'):
        return None
    v = _num(ts.get(key))
    if v is not None and key in _FRACTION_SCALE_KEYS and abs(v) <= 1.5:
        # A real fraction-scale value for these stats is always <=~1.0; a
        # real percent-scale one for the same stats never dips this low
        # (see the module docstring) -- so this only ever fires on the
        # genuinely-fraction real data, never on placeholder/mock values
        # that are already in percent scale.
        v *= 100.0
    return v


def universal_single(away_ts, home_ts, off_key, def_key):
    """The manual's Universal Matchup Formula Rule. Returns
    (final_delta, favored_side) -- favored_side is 'away' (final_delta>0),
    'home' (<0), or None (tie, or missing real data on either side)."""
    away_off, home_def = _get(away_ts, off_key), _get(home_ts, def_key)
    home_off, away_def = _get(home_ts, off_key), _get(away_ts, def_key)
    if None in (away_off, home_def, home_off, away_def):
        return None, None
    # SIGN FIX (2026-10-06): see _LOWER_IS_BETTER. For higher-is-better defense numbers (OFEI/DFEI, pace) this is
    # algebraically identical to the old (Away Off - Home Def) - (Home Off - Away Def).
    so, sd = _dir(off_key), _dir(def_key)
    final_delta = so * (away_off - home_off) - sd * (home_def - away_def)
    if final_delta > 0:
        favored = 'away'
    elif final_delta < 0:
        favored = 'home'
    else:
        favored = None
    return final_delta, favored


def composite_single(away_ts, home_ts, key):
    """For a stat that's already a per-team composite/net number (Net
    Success Rate, FEI) -- just Away's real value minus Home's, no
    bracketing."""
    a, h = _get(away_ts, key), _get(home_ts, key)
    if a is None or h is None:
        return None, None
    d = a - h
    favored = 'away' if d > 0 else ('home' if d < 0 else None)
    return d, favored


def paired_edge(away_ts, home_ts, off_key, def_key):
    """Each team's own one-sided real edge: that team's real Off stat
    minus the OPPOSING team's real Def stat, not collapsed further.
    Returns (away_edge, home_edge)."""
    away_off, home_def = _get(away_ts, off_key), _get(home_ts, def_key)
    home_off, away_def = _get(home_ts, off_key), _get(away_ts, def_key)
    # SIGN FIX (2026-10-06): the old edge was just Off - Opp Def, which for "allowed" defense stats rewarded a
    # stingy defense (it made the offense's edge BIGGER). Now each side is measured against the league average
    # and signed by which direction is good -- see _LOWER_IS_BETTER. Positive = good for that team's offense.
    so, sd = _dir(off_key), _dir(def_key)
    l_off = _LEAGUE.get(off_key)
    l_def = _LEAGUE.get(def_key)
    if l_off is None:
        offs = [v for v in (away_off, home_off) if v is not None]
        l_off = sum(offs) / len(offs) if offs else None
    if l_def is None:
        defs = [v for v in (away_def, home_def) if v is not None]
        l_def = sum(defs) / len(defs) if defs else None

    def _edge(off_v, opp_def_v):
        if None in (off_v, opp_def_v, l_off, l_def):
            return None
        return so * (off_v - l_off) - sd * (opp_def_v - l_def)
    return _edge(away_off, home_def), _edge(home_off, away_def)


def fraud_gap(away_ts, home_ts):
    """The Fraud Index & Fraud Gap (Points vs. Yards) -- per team:
    Yards Delta = that team's real Off Yds/Game - opponent's real Def
    Yds/Game allowed; Points Delta = same for points; Gap Ratio =
    Yards Delta / Points Delta. Lower ratio = more efficient (converts
    yardage into points cleanly); a high ratio exposes empty-yardage
    volume. Returns (away_ratio, home_ratio)."""
    away_yds, home_yds = paired_edge(away_ts, home_ts, "Off_Yds_PG", "Def_Yds_PG")
    away_pts, home_pts = paired_edge(away_ts, home_ts, "Off_PPG", "Def_PPG")

    def _ratio(yds, pts):
        # this is a division, so a team whose real
        # Points-edge sits near zero (a close-scoring matchup) sends the
        # ratio toward +/-infinity for reasons that have nothing to do
        # with real yardage efficiency -- not a scale problem, a ratio-
        # instability problem. Below this threshold the number is not
        # meaningful, so it renders as "--" (same "real data unavailable"
        # convention _fmt_delta already uses for None) instead of a wild
        # number.
        FRAUD_GAP_MIN_POINTS_EDGE = 3.0
        if yds is None or pts is None or abs(pts) < FRAUD_GAP_MIN_POINTS_EDGE:
            return None
        return yds / pts

    return _ratio(away_yds, away_pts), _ratio(home_yds, home_pts)


SACK_RATE_DENOM_PLAYS = 65  # average offensive snaps per game (historically around 65 plays in modern football) -- a fixed constant for converting Sacks/Game into a rate, not a live-computed number


def finishing_delta(away_ts, home_ts):
    """The Finishing Delta ('Method 2: The Pure Rate Delta')
    -- per team, THAT team's real defense sack rate minus the OPPOSING
    team's real offensive havoc-allowed rate:
      Defense Sack Rate = (that team's real Def_Sacks_PG) / 65
      Delta = Defense Sack Rate - (opponent's real Off_Havoc / 100)
    Off_Havoc is already stored here as a percent (e.g. 15.0 = 15%);
    the sack rate is put on that same percent scale (real sacks/game
    divided by 65 real snaps, times 100) before subtracting -- an
    algebraic apples-to-apples delta in percentage points, matching the
    -15%/-5% scale the worked interpretation uses, not a
    percent-vs-raw-fraction mismatch. Large negative = disruption that
    doesn't finish (a slippery/quick-release QB evades sacks despite real
    pressure); small negative = the defense converts most of its real
    disruption into actual sacks. Returns (away_def_vs_home_off,
    home_def_vs_away_off) -- away's number describes AWAY's defense
    against HOME's offensive line/QB, and vice versa, same "team's own
    side" placement as every other paired delta here."""
    def _calc(def_ts, off_ts):
        def_sacks = _get(def_ts, 'Def_Sacks_PG')
        off_havoc = _get(off_ts, 'Off_Havoc')
        if def_sacks is None or off_havoc is None:
            return None
        return (def_sacks / SACK_RATE_DENOM_PLAYS * 100.0) - off_havoc
    return _calc(away_ts, home_ts), _calc(home_ts, away_ts)


def volume_vs_efficiency(away_ts, home_ts, vol_off_key, vol_def_key, eff_off_key, eff_def_key):
    """Air Depth Delta / Per-Carry Reality Delta -- per team, a pair of
    real one-sided edges: total-yardage volume edge vs. per-play
    efficiency edge, for the same unit (passing or rushing). Returns
    (away_vol, away_eff, home_vol, home_eff)."""
    away_vol, home_vol = paired_edge(away_ts, home_ts, vol_off_key, vol_def_key)
    away_eff, home_eff = paired_edge(away_ts, home_ts, eff_off_key, eff_def_key)
    return away_vol, away_eff, home_vol, home_eff


# ---------------------------------------------------------------------------
# Full spec: every delta to add, in the shape it should render.
# 'kind' controls both the math above and how cfb_matchup_card_v4.py
# formats/places the result: 'single' -> universal_single, 'composite' ->
# composite_single, 'paired' -> paired_edge, 'fraud' / 'volEff' -> their
# own special-shaped functions above.
# ---------------------------------------------------------------------------
SINGLE_DELTA_SPECS = [
    # (label exactly as the manual/blueprint title it, off_key, def_key, kind)
    ("Points Per Game (PPG) Delta", "Off_PPG", "Def_PPG", "single"),
    ("Yards Per Game (YPG) Delta", "Off_Yds_PG", "Def_Yds_PG", "single"),
    ("Yards Per Play (YPP) Delta", "Off_YPP", "Def_YPP", "single"),
    ("Plays Per Game (Pace) Delta", "Off_Plays_PG", "Def_Plays_Faced_PG", "single"),
    ("Red Zone % (Blood Zone) Delta", "Off_RZ_%", "Def_RZ_%", "single"),
    ("3rd Down % (Money Down) Delta", "Off_3rd_%", "Def_3rd_%", "single"),
    ("Heavy Artillery Line Push (Line Yards Delta)", "Off_Line_Yards", "Def_Line_Yards", "single"),
    ("Drive-Killer Penetration (Stuff Rate Delta)", "Off_Stuff_Rate", "Def_Stuff_Rate", "single"),
    ("Net Efficiency Delta (The Vegas Filter)", "OFEI", "DFEI", "single"),
    ("Net Success Rate Delta", "NSR", None, "composite"),
    ("FEI Delta", "FEI", None, "composite"),
]

# "'Stay-on-Schedule' Rushing Delta" keyed to OSR/DSR
# (bcftoys' real percent-scale success-rate ratings), per the blueprint's
# own worked Tulsa/Arkansas arithmetic -- see module docstring.
PAIRED_DELTA_SPECS = [
    ("Vertical Lightning Strike Delta (Passing Explosiveness)", "Off_Explosiveness", "Def_Explosiveness"),
    ("Passing Down Panic Index (PPA)", "Off_PPA", "Def_PPA"),
    ("'Stay-on-Schedule' Rushing Delta (Success Rate)", "OSR", "DSR"),
    ("4th & Inches Manhood Test (Power Success Rate)", "Off_Power_Success", "Def_Power_Success"),
    ("The Chaos Coefficient Mismatch (Havoc Delta)", "Off_Havoc", "Def_Havoc"),
    # "The Run-Game Explosion Delta" -- 2A/2B. Both are
    # already the standard paired_edge shape (that team's real offense
    # number minus the OPPOSING team's real defense number allowed), using
    # the same real Off/Def Second-Level-Yards and Open-Field-Yards
    # columns this card's own "2nd Level Yards"/"Open Field Yards" grids
    # already display -- no new fetch, no new function needed.
    ("2nd Level Delta (The Front-7 Matchup)", "Off_Second_Level_Yards", "Def_Second_Level_Yards"),
    ("Open Field Delta (The Secondary Matchup)", "Off_Open_Field_Yards", "Def_Open_Field_Yards"),
]


def compute_all(away_ts, home_ts):
    """Computes every real delta for this one matchup's already-fetched
    away_ts/home_ts. Returns a dict keyed by label -> result tuple, ready
    for cfb_matchup_card_v4.py to place beside each grid."""
    out = {}
    for label, off_key, def_key, kind in SINGLE_DELTA_SPECS:
        if kind == "single":
            out[label] = ("single",) + universal_single(away_ts, home_ts, off_key, def_key)
        else:
            out[label] = ("single",) + composite_single(away_ts, home_ts, off_key)
    for label, off_key, def_key in PAIRED_DELTA_SPECS:
        out[label] = ("paired",) + paired_edge(away_ts, home_ts, off_key, def_key)
    out["The Fraud Index & Fraud Gap (Points vs. Yards)"] = ("paired",) + fraud_gap(away_ts, home_ts)
    out["The Finishing Delta (Sack Rate vs. Havoc Allowed)"] = ("paired",) + finishing_delta(away_ts, home_ts)
    out["Air Depth Delta (Passing Volume vs. Efficiency)"] = (
        "volEff",) + volume_vs_efficiency(away_ts, home_ts, "Off_Pass_PG", "Def_Pass_PG", "Off_Pass_Att", "Def_Pass_Att")
    out["Per-Carry Reality Delta (Rushing Volume vs. Efficiency)"] = (
        "volEff",) + volume_vs_efficiency(away_ts, home_ts, "Off_Rush_PG", "Def_Rush_PG", "Off_Rush_Att", "Def_Rush_Att")
    return out


# ---------------------------------------------------------------------------
# METRIC_META -- the exact "what it tells you" + "Analytical Scale" text
# from the 3 uploaded sheets, condensed to fit beside/below a report grid.
# cfb_matchup_card_v4.py reads this dict directly (imports this module) so
# there's exactly one copy of this text, not a second one drifting out of
# sync inside the card file. 'text' is the single combined string rendered
# next to (single-kind) or below (paired-kind) each delta's grid.
# ---------------------------------------------------------------------------
METRIC_META = {
    "Points Per Game (PPG) Delta":
        "Isolates the real scoring separation when both offenses face their true defensive matchups. "
        "Scale: 0-3 Toss-Up, 3.1-7 Standard Edge, 7.1-13 Dominant, 14+ Blowout.",
    "Yards Per Game (YPG) Delta":
        "Raw space-generation gap -- audit against YPP to filter out junk-time yards. "
        "Scale: 0-25 Even, 26-60 Volume Edge, 61-100 Major Push, 101+ Dominance.",
    "Yards Per Play (YPP) Delta":
        "Down-to-down per-snap efficiency; exposes fake high-tempo offenses. "
        "Scale: 0.0-0.2 Dead Even, 0.3-0.5 Clear Edge, 0.6-0.9 Mismatch, 1.0+ Overmatch.",
    "Plays Per Game (Pace) Delta":
        "Snapping-speed control -- can a tempo team force extra possessions? "
        "Scale: 0-3 Neutral, 3.1-6 Tempo Edge, 6.1-9 Fatigue Risk, 9.1+ Style Clash.",
    "Red Zone % (Blood Zone) Delta":
        "Execution inside the 20 when the field contracts and space vanishes. "
        "Scale: 0-4% Even, 4.1-10% RZ Advantage, 10.1%+ Liquidation.",
    "3rd Down % (Money Down) Delta":
        "Drive survival and conversion sustainability on money downs. "
        "Scale: 0-3% Even, 3.1-7% Chain Edge, 7.1%+ Monopoly.",
    "Heavy Artillery Line Push (Line Yards Delta)":
        "Pure O-line block-displacement power, independent of RB talent. "
        "Scale: 0.00-0.15 Even Fronts, 0.16-0.35 Line Leverage, 0.36+ Trench Control.",
    "Drive-Killer Penetration (Stuff Rate Delta)":
        "How often running plays are stopped dead at/behind the line of scrimmage. "
        "Scale: 0-2.5% Balanced, 2.6-6% Breached Gaps, 6.1%+ Caved Front.",
    "Net Efficiency Delta (The Vegas Filter)":
        "Anchor efficiency metric (OFEI/DFEI) that filters out schedule softness and raw luck. "
        "Scale: greater than +0.50 = dominant edge (away), -0.50 to +0.50 = razor-thin wash, "
        "less than -0.50 = dominant edge (home).",
    "Net Success Rate Delta":
        "Down-to-down consistency, ignoring single fluke breakaway plays. NSR is already each "
        "team's own net number (Off Success Rate minus Def Success Rate allowed), so this delta is "
        "the gap between two already-net values, not a single raw stat gap -- its real range runs "
        "far wider than a typical single-stat delta. Scale (recalibrated 2026-09-29 against a real "
        "54-game week, where 19 of 54 games exceeded the old top bucket; rescaled again "
        "2026-09-30 to real plain NSR units -- same real evidence, no longer a percentage-"
        "point conversion, see module docstring): 0-0.10 Even Clash, 0.101-0.25 Script "
        "Control, 0.251-0.45 Total Monopoly, 0.451+ Annihilation (full mismatch).",
    "FEI Delta":
        "Away FEI minus Home FEI -- same composite power-rating differential as Net Success Rate, "
        "on the real OFEI/DFEI-family scale. Scale: greater than +0.50 / less than -0.50 = lopsided "
        "edge, -0.50 to +0.50 = close.",
    "Vertical Lightning Strike Delta (Passing Explosiveness)":
        "Each team's real Off Explosiveness minus the opposing Def Explosiveness allowed -- predicts "
        "explosive-play volatility. Scale: greater than +0.15 Chunk Play Hazard, 0.00-0.15 Methodical "
        "Rhythm, less than 0.00 Capsized Skies (secondary locks down the deep ball).",
    "Passing Down Panic Index (PPA)":
        "Each team's real Off PPA minus the opposing Def PPA allowed. Scale: greater than +0.10 Ice "
        "in the Veins, 0.00-0.10 Stable Execution, less than 0.00 Pocket Collapse risk.",
    "'Stay-on-Schedule' Rushing Delta (Success Rate)":
        "Each team's real Off Success Rate (OSR) minus the opposing Def Success Rate allowed (DSR). "
        "Scale (2026-09-30, rescaled to real plain OSR/DSR units -- no longer a "
        "percentage-point conversion, see module docstring): greater than +0.05 Ground "
        "Dominance, 0.0-0.05 Hard-Nosed Chipping, less than 0.0 Behind the Chains.",
    "4th & Inches Manhood Test (Power Success Rate)":
        "Each team's real Off Power Success % minus the opposing Def Power Success % allowed. Scale: "
        "greater than +5.0% Short-Yardage Hammer, -5.0 to +5.0% Line Push Stalemate, less than -5.0% "
        "Interior Brick Wall.",
    "The Chaos Coefficient Mismatch (Havoc Delta)":
        "Each team's real Off Havoc allowed minus the opposing Def Havoc forced. Scale: positive = "
        "elite ball security, 0 to -3.0% standard variance, worse than -3.0% = Avalanche Zone "
        "(turnover risk).",
    "The Fraud Index & Fraud Gap (Points vs. Yards)":
        "Each team's real Yards-edge divided by their real Points-edge -- exposes empty-yardage "
        "volume. This is a ratio: when a team's real Points-edge sits near zero (a close-scoring "
        "matchup) the ratio is mathematically unstable, not analytically meaningful, so it shows as "
        "'--' whenever the real Points-edge is under 3. Scale: under 7.0 Hyper-Efficient, 7.0-11.0 "
        "Balanced, over 11.0 Yardage Illusion (hollow stats).",
    "Air Depth Delta (Passing Volume vs. Efficiency)":
        "Compares each team's real passing-yardage edge against their real yards/attempt edge -- true "
        "deep threat vs. system volume. Scale (YPA differential): greater than +0.5 Lethal Air Strike, "
        "0.0-0.5 Horizontal Distribution, less than 0.0 Strangled Lanes.",
    "Per-Carry Reality Delta (Rushing Volume vs. Efficiency)":
        "Compares each team's real rushing-yardage edge against their real yards/attempt edge -- flags "
        "a 'one-hit wonder' run game riding a single breakaway rather than real consistency.",
    "The Finishing Delta (Sack Rate vs. Havoc Allowed)":
        "Each team's real Def Sack Rate (Def Sacks/Game divided by 65 real offensive snaps) minus the "
        "opposing offense's real Havoc-Allowed rate. Large negative (around -15%) = disruption that "
        "doesn't finish -- a slippery or quick-release QB evades sacks despite real pressure. Small "
        "negative (around -5%) = the defense converts most of its real disruption into actual sacks.",
    "2nd Level Delta (The Front-7 Matchup)":
        "Each team's real Off 2nd Level Yards/Carry (5-10 yards past the line) minus the opposing "
        "defense's real 2nd Level Yards/Carry allowed -- the O-line-reaching-the-second-level vs. "
        "linebackers-filling-gaps battle. Positive = the offense is efficient here relative to what "
        "that defense usually allows (expect chunk plays); negative = the defense's linebacker corps "
        "is a real bottleneck that suppresses it.",
    "Open Field Delta (The Secondary Matchup)":
        "Each team's real Off Open Field Yards/Carry (11+ yards past the line) minus the opposing "
        "defense's real Open Field Yards/Carry allowed -- home-run rushing ability vs. a secondary's "
        "real open-field tackling. Positive = green flag for the offense, expect explosive runs; "
        "negative = red flag, the secondary's tacklers suppress the breakaway threat.",
}


# SIGN FIX note (2026-10-06): the paired/edge descriptions used to say "Off stat MINUS the opposing Def stat". That is
# no longer how the number is built (see _LOWER_IS_BETTER near the top of this file), so the wording is updated here
# and a short note is appended so the card says what the numbers now mean.
_EDGE_NOTE = " (Each side is measured against league average; a leaky defense now helps the offense.)"
for _lbl in list(METRIC_META):
    _t = METRIC_META[_lbl]
    if _lbl in [l for l, _o, _d in PAIRED_DELTA_SPECS]:
        _t = _t.replace("minus the opposing", "vs. the opposing")
        _t = _t.replace("Positive = the offense is efficient here relative to what that defense usually allows (expect chunk plays); "
                        "negative = the defense's linebacker corps is a real bottleneck that suppresses it.",
                        "Positive = a better-than-average run game and/or a leakier-than-average front (expect chunk plays); "
                        "negative = the linebacker corps is a real bottleneck that suppresses it.")
    if _lbl in [l for l, _o, _d in PAIRED_DELTA_SPECS] + [
            "The Fraud Index & Fraud Gap (Points vs. Yards)",
            "Air Depth Delta (Passing Volume vs. Efficiency)",
            "Per-Carry Reality Delta (Rushing Volume vs. Efficiency)"]:
        if _EDGE_NOTE not in _t:
            _t = _t + _EDGE_NOTE
    METRIC_META[_lbl] = _t


# ==========================================
# BACKTESTED MARGIN/SPREAD MODEL
# The GAME FLOW FORECAST's projected margin in cfb_working_schedule.py used
# hand-picked weights (_FORECAST_WEIGHTS = fpi 35% / efficiency 25% /
# scoring 20% / yardage 10% / turnovers 10%) that were never checked against
# a completed game, unlike the win/loss pick model (tune_stat_weights), which
# is backtested. This section replaces them with fitted coefficients.
#
# This section fits a real ordinary-least-squares regression of
# (actual final margin - that team's real home-field rating) against the
# same 5 raw factor values cfb_working_schedule.py's own
# compute_forecast_factors() already computes (FPI gap, efficiency gap,
# scoring gap, yardage gap, turnover gap) -- replacing the hand-picked
# weighted-average blend with real, data-fitted coefficients, same spirit
# as tune_stat_weights() but continuous regression instead of greedy
# classification.
#
# Real, disclosed limitation (same one the existing win/loss backtest
# already has, and accepted for the bootstrap): no
# historical day-by-day snapshot of each team's stats exists, so
# backfilling uses each team's CURRENT season averages for games that
# already happened -- meaning a game's own box score is already folded
# into both teams' season numbers by the time it's used as a training
# row. Early season, with few games banked, this can matter more; it
# should get quieter as more of the season accumulates. This is disclosed
# in the report via the real sample size (n) and in-sample MAE/R^2 shown
# next to the fitted weights -- never a bare number with no context,
# same rule as everywhere else in this project.
# ==========================================

FORECAST_HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cfb_forecast_history.json")  # anchored to this script's own folder (not the cwd)

# The same 5 factor keys compute_forecast_factors() in
# cfb_working_schedule.py produces -- kept as a module-level constant here
# (not re-derived) so a typo in one place can't silently drop a factor
# from the regression without erroring.
MARGIN_FACTOR_KEYS = ['fpi', 'efficiency', 'scoring', 'yardage', 'turnovers']

# Below this many real, complete (all 5 factors present) training rows, an
# OLS fit is more likely to overfit noise than beat the original reasoned
# defaults -- tune_forecast_weights() returns None below this bar, and the
# caller falls back to the original hand-picked weights rather than trust
# a fit with too little real data behind it.
MIN_MARGIN_SAMPLES = 15


def load_forecast_history():
    """Loads the persistent margin-factor training history (mirrors
    cfb_working_schedule.py's own load_stat_history() pattern, but this is
    a wholly separate file/history -- one tracks per-stat win/loss votes,
    this tracks continuous point-margin regression rows)."""
    if os.path.exists(FORECAST_HISTORY_FILE):
        try:
            with open(FORECAST_HISTORY_FILE) as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("games"), dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"games": {}}


def save_forecast_history(history):
    with open(FORECAST_HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)


def _as_series(ts):
    """Same duplicate-index guard used throughout cfb_working_schedule.py:
    a duplicate Clean_Name makes stats_lookup.loc[team] return a
    multi-row DataFrame instead of a Series. Falls back to the first row
    rather than letting every .get() call below throw."""
    if isinstance(ts, pd.DataFrame):
        return ts.iloc[0]
    return ts


def backfill_forecast_history(forecast_history, stat_history, stats_lookup,
                               compute_factors_fn, compute_hfa_fn):
    """One-time-per-game, idempotent backfill: for every REAL completed
    game already on record in cfb_working_schedule.py's own
    cfb_stat_history.json (which already has the real final score for
    every completed game this season), if that game isn't already in the
    margin-forecast history, compute its 5 real factor values from each
    team's CURRENT stats_lookup row and record them alongside the real
    actual margin and the real home-field number that would have been
    used. Keyed by the same real ESPN Event_Id as cfb_stat_history.json,
    so re-running this never double-counts a game.

    compute_factors_fn / compute_hfa_fn are passed in (rather than
    imported) so this stays a real function of cfb_working_schedule.py's
    own real compute_forecast_factors()/compute_home_field_adv() --
    calling the actual live logic, not a re-implementation that could
    silently drift from it.

    Returns how many NEW games were added this call."""
    added = 0
    for event_id, game in stat_history.get("games", {}).items():
        if event_id in forecast_history["games"]:
            continue
        away, home = game.get("away"), game.get("home")
        away_score, home_score = game.get("away_score"), game.get("home_score")
        if away_score is None or home_score is None:
            continue
        if away not in stats_lookup.index or home not in stats_lookup.index:
            continue
        away_ts = _as_series(stats_lookup.loc[away])
        home_ts = _as_series(stats_lookup.loc[home])

        factors, _home_proj, _away_proj = compute_factors_fn(away_ts, home_ts)
        if factors is None:
            continue
        hfa, hfa_is_real = compute_hfa_fn(home_ts)

        forecast_history["games"][event_id] = {
            "date": game.get("date"), "away": away, "home": home,
            "actual_margin": home_score - away_score,
            "hfa_used": hfa, "hfa_is_real": hfa_is_real,
            "factors": factors,
        }
        added += 1

    if added:
        save_forecast_history(forecast_history)
    return added


def tune_forecast_weights(forecast_history, min_samples=MIN_MARGIN_SAMPLES):
    """Real ordinary-least-squares fit of (actual_margin - hfa_used)
    against the 5 raw margin factors, over every real recorded game that
    has ALL FIVE factors present (a partial row is dropped rather than
    imputed -- guessing a missing factor's value would quietly bias the
    fit, and there's no honest way to know what it "should" have been).

    Returns None -- caller falls back to the original hand-picked
    _FORECAST_WEIGHTS -- when fewer than min_samples complete rows exist;
    an OLS fit on too few real games is worse than reasoned defaults, not
    better. Otherwise returns a dict: intercept, coefs (per factor key),
    n (real sample size used), r2 and mae (both IN-SAMPLE -- fit and
    evaluated on the same rows, not held-out -- disclosed as such
    wherever this is shown, same rule as every other backtest number in
    this project)."""
    rows, targets = [], []
    for game in forecast_history.get("games", {}).values():
        factors = game.get("factors") or {}
        if not all(factors.get(k) is not None for k in MARGIN_FACTOR_KEYS):
            continue
        actual_margin = game.get("actual_margin")
        if actual_margin is None:
            continue
        hfa = game.get("hfa_used", 0.0) or 0.0
        rows.append([factors[k] for k in MARGIN_FACTOR_KEYS])
        targets.append(actual_margin - hfa)

    n = len(rows)
    if n < min_samples:
        return None

    X = np.asarray(rows, dtype=float)
    y = np.asarray(targets, dtype=float)
    X_design = np.column_stack([np.ones(n), X])
    fit, _residuals, _rank, _sv = np.linalg.lstsq(X_design, y, rcond=None)
    intercept = float(fit[0])
    coefs = {k: float(fit[i + 1]) for i, k in enumerate(MARGIN_FACTOR_KEYS)}

    preds = X_design @ fit
    resid = y - preds
    mae = float(np.mean(np.abs(resid)))
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return {"intercept": intercept, "coefs": coefs, "n": n, "r2": r2, "mae": mae}


def predict_margin_from_fitted(fitted, factors):
    """intercept + sum(coef * value) over whichever of the 5 factors this
    SPECIFIC matchup actually has data for. Missing factors are simply
    omitted (the statistically correct default for an already-fitted
    linear model -- it does not renormalize the way the old hand-weighted
    average did, since that renormalization only made sense for averaging
    already-scaled independent estimates, not for a regression's own
    coefficients)."""
    total = fitted["intercept"]
    for k, v in factors.items():
        if k in fitted["coefs"] and v is not None:
            total += fitted["coefs"][k] * v
    return total


def describe_fitted_margin_model(fitted, factors_used):
    """Builds the same kind of disclosed, real-sample-size-first string
    the rest of this project always shows next to a backtested number --
    e.g. 'FPI +0.92/pt, Efficiency +1.10/pt, ... (real OLS fit, n=187,
    R^2=0.38, MAE=9.4 pts, in-sample)' -- for the weights_note line that
    replaces the old hand-picked-weights disclosure."""
    _labels = {'fpi': 'FPI', 'efficiency': 'Efficiency', 'scoring': 'Scoring',
               'yardage': 'Yardage', 'turnovers': 'Turnovers'}
    parts = [f"{_labels[k]} {fitted['coefs'][k]:+.2f}/pt" for k in factors_used if k in fitted['coefs']]
    return (f"{', '.join(parts)} (real OLS fit, n={fitted['n']}, R²={fitted['r2']:.2f}, "
            f"MAE={fitted['mae']:.1f} pts, in-sample)")
