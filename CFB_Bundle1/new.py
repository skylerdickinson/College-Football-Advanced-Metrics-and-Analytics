# =====================================================================
# HEADER: SECTION 1 - DEPENDENCIES & GLOBAL TYPOGRAPHY STYLES
# DESCRIPTION: Imports processing modules, sets letter landscape 
# canvas sizes, and initializes tight micro-style formatting rules.
# =====================================================================

import re
import os
import json
from pypdf import PdfReader
import pdfplumber

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, PageBreak, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# FIX: Corrected split sequence to target element index [0] before calling string string methods
def clean_stat(value_str):
    if not value_str: return "N/A"
    return str(value_str).split('(')[0].strip() or "N/A"

def safe_float(val):
    try: return float(str(val).replace('%', '').strip())
    except (ValueError, TypeError): return None

# NEW: SOR (Strength of Record -- ESPN's accomplishmentrank: a schedule-adjusted resume
# rank based on games already played, same field cfb_working_schedule.py already calls "SOR"). This script
# has no network access at all, so it can't fetch SOR live itself -- it reads whatever
# cfb_working_schedule.py's fetch_espn_power_index() most recently cached to
# ~/Desktop/cfb/cfb_espn_power_index_cache.json. That function was just updated (2026-10-02) to write this
# cache automatically, from real live ESPN data only, every time it runs -- whether from cfb_working_schedule.py
# itself or from cfb_matchup_deep_dive.py importing it. No hardcoded values in any PDF -- if the
# cache is missing or a team isn't in it, SOR shows as real "N/A" here, never a guessed or placeholder number.
# MERGED (2026-10-05): new.py now lives in the same folder as everything else, so it reads the matrices
# report and the SOR cache from here and writes its output into generated/ -- run via cfb_run_all.py.
_HERE = os.path.dirname(os.path.abspath(__file__))
_MATRICES_PDF = os.path.join(_HERE, "generated", "cfb_matrices_outlook.pdf")
_GRID_OUT_PDF = os.path.join(_HERE, "generated", "All_Matchups_Grid_Report.pdf")
os.makedirs(os.path.join(_HERE, "generated"), exist_ok=True)
_SOR_CACHE_PATH = os.path.join(_HERE, "cfb_espn_power_index_cache.json")
_sor_lookup = {}
_sor_cache_meta = None
try:
    with open(_SOR_CACHE_PATH) as _sor_f:
        _sor_cache = json.load(_sor_f)
    _sor_cache_meta = (_sor_cache.get("fetched_at"), _sor_cache.get("week_number"))
    for _tname, _tvals in (_sor_cache.get("teams") or {}).items():
        _sor_lookup[re.sub(r"\s+", " ", _tname).strip().upper()] = (_tvals or {}).get("SOR")
    print(f" -> SOR cache loaded: {len(_sor_lookup)} team(s) from {_SOR_CACHE_PATH} "
          f"(fetched_at={_sor_cache_meta[0]}, week={_sor_cache_meta[1]}).")
except (FileNotFoundError, json.JSONDecodeError, OSError) as _sor_err:
    print(f" -> ⚠ no SOR cache found at {_SOR_CACHE_PATH} ({_sor_err}) -- SOR will show as N/A until you "
          f"run cfb_working_schedule.py or cfb_matchup_deep_dive.py once to generate it.")

_SOR_ALIASES = {"FLORIDA INTL": "FLORIDA INTERNATIONAL", "UMASS": "MASSACHUSETTS", "N ILLINOIS": "NORTHERN ILLINOIS",
                "S FLORIDA": "SOUTH FLORIDA", "S ALABAMA": "SOUTH ALABAMA", "UCONN": "CONNECTICUT"}

def lookup_sor(team_name):
    # FIX (2026-10-06): the SOR cache is keyed by ESPN's full names ("Boise State", "Jacksonville State") while
    # the matrices pages use TeamRankings' short ones ("Boise St", "Jacksonville St") -- 7 teams came out N/A.
    k = re.sub(r"\s+", " ", team_name).strip().upper()
    for cand in (k, _SOR_ALIASES.get(k), re.sub(r" ST$", " STATE", k), re.sub(r"^S ", "SOUTH ", k)):
        if cand and cand in _sor_lookup:
            return _sor_lookup[cand]
    return "N/A"

# CHANGED: PPD used to be read from its own cfb_ppd_cache.json, same
# pattern as SOR above. That's
# gone now -- cfb_working_schedule.py prints "OFF PPD (LAST 3)"/"DEF PPD (LAST 3)" straight
# into the ADVANCED RATINGS table on every matchup page (sourced from that same cache file,
# just read on that end instead of this one), and away["Off PPD (Last 3)"]/away["Def PPD
# (Last 3)"] etc. below pull it back out of this script's own normal find_h_b() parsing,
# same as every other ADVANCED RATINGS stat (FEI, PPA, ...). No cache file read here anymore.

# FIX: reportlab Paragraph text is parsed as mini-XML, so an unescaped "&" (Texas A&M) breaks
# the parser -- confirmed it was rendering as "TEXAS A&M;", silently mangling the name. Any raw team name that
# gets embedded in a Paragraph/HTML string (titles, headers) needs to go through this first; the clean,
# un-escaped team_name is still what's used for SOR lookup, dict keys, etc.
def _xml_esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

styles = getSampleStyleSheet()
title_style = ParagraphStyle('T_Style', fontName='Helvetica-Bold', fontSize=9, leading=10, alignment=TA_CENTER, textColor=colors.HexColor("#1A365D"))

# Scaled down header banner text to 7pt for clean tight structural sizing
section_style = ParagraphStyle('S_Style', fontName='Helvetica-Bold', fontSize=7, leading=8, alignment=TA_CENTER, textColor=colors.white)
hdr_left = ParagraphStyle('HL', fontName='Helvetica-Bold', fontSize=7, leading=8, alignment=TA_CENTER, textColor=colors.white)
hdr_center = ParagraphStyle('HC', fontName='Helvetica-Bold', fontSize=7, leading=8, alignment=TA_CENTER, textColor=colors.white)
hdr_right = ParagraphStyle('HR', fontName='Helvetica-Bold', fontSize=7, leading=8, alignment=TA_CENTER, textColor=colors.white)

# Compressed data text fields to 6pt with ultra-tight 7pt leading to fit comfortably
cell_center = ParagraphStyle('Cc', fontName='Helvetica-Bold', fontSize=6, leading=7, alignment=TA_CENTER, textColor=colors.HexColor("#2D3748"))
cell_left = ParagraphStyle('Cl', fontName='Helvetica', fontSize=6, leading=7, alignment=TA_LEFT, textColor=colors.HexColor("#1A202C"))
cell_right = ParagraphStyle('Cr', fontName='Helvetica', fontSize=6, leading=7, alignment=TA_RIGHT, textColor=colors.HexColor("#1A202C"))

# NEW: smaller variants used only by the Off-vs-Def mini-grids (under each team), so each
# small bordered grid can stay inside its own 55pt Away/Home column without overflowing it.
cell_center_sm = ParagraphStyle('CcS', fontName='Helvetica-Bold', fontSize=5, leading=6, alignment=TA_CENTER, textColor=colors.HexColor("#2D3748"))
cell_left_sm = ParagraphStyle('ClS', fontName='Helvetica', fontSize=5, leading=6, alignment=TA_LEFT, textColor=colors.HexColor("#1A202C"))
cell_right_sm = ParagraphStyle('CrS', fontName='Helvetica', fontSize=5, leading=6, alignment=TA_RIGHT, textColor=colors.HexColor("#1A202C"))

# =====================================================================
# BOUNDARY LINE: END OF SECTION 1 - PASTE SECTION 2 DIRECTLY BELOW
# =====================================================================
# =====================================================================
# HEADER: SECTION 2 - REGEX TEXT PROCESSING FALLBACK ENGINE
# DESCRIPTION: Looks backward from stat label keys to cleanly slice out
# raw numeric strings when horizontal spacing trips the base regex.
# =====================================================================

def grab_home_stat(keyword, raw_text):
    tokens = raw_text.split()
    for idx, token in enumerate(tokens):
        if token == keyword and idx > 0:
            val = tokens[idx - 1].split('(')[0].strip()
            if val.replace('.', '', 1).replace('-', '', 1).isdigit():
                return val.replace("%", "")
    match = re.search(r"([-\d.]+)\s*\(\d+\)\s+" + re.escape(keyword), re.sub(r'\s+', ' ', raw_text))
    return match.group(1).replace("%", "") if match else "N/A"

# =====================================================================
# BOUNDARY LINE: END OF SECTION 2 - PASTE SECTION 3 DIRECTLY BELOW
# =====================================================================
# =====================================================================
# HEADER: SECTION 3 - METRIC CONFIGURATION SCHEMA
# DESCRIPTION: Maps the mathematical properties and parameter dictionary
# keys for all 14 requested single-number formulas.
# =====================================================================

# =====================================================================
# GREEN / TEAL highlight on LARGE grid deltas.
# A delta is "large" when it is in the top 25% of |delta| across the games on file (this slate + cfb_delta_history.json) and
# "massive" in the top 10%. Each tier has an estimated win % for the team the delta favors (below). The cell of the favored
# team is colored by that win %:  70-80% light green, 80-90% green, 90%+ teal. Under 70% = no color.
# THESE WIN %s ARE CORRECTED ESTIMATES: a same-day test on season-to-date stats (which include the game being predicted) read the
# tiers 11-25 points too high, so the raw results were marked down 14 (large) / 16 (massive) points. Total Pass is a clean
# pre-game number as measured. Deltas with no data yet (Sacks, TFL, Rushing Reality) are never colored.
# cfb_delta_study.py replaces these estimates with real pre-game results (cfb_delta_scale.json) once enough games have been graded.
# =====================================================================
_DELTA_SCALE_DEFAULT = {          # name: (large-tier win %, massive-tier win %)
    "Net Success Rate Delta": (76, 84), "OSR vs. DSR Delta": (76, 84),
    "Offensive Efficiency Delta": (86, 84),
    "Passing Down Panic Delta": (71, 80),
    "Havoc Rate Delta": (79, 77),
    "Line Yards Delta": (61, 77),
    "Open Field Yards Delta": (59, 69.7), "2nd Level Yards Delta": (63.5, 69.7),
    "Stuff Rate Delta": (63.5, 66), "Power Success Rate Delta": (59, 59),
    "Passing Explosiveness Delta": (50, 52),
    "Total Pass Matchup Delta": (69, 68),
}
_BAND_COLORS = {"light": "#D4EFD4", "green": "#7ED08A", "teal": "#3CC9C0"}
_delta_thr = {}                  # name -> (large starts at, massive starts at), in the grid's own units
_scale_override = {}
try:
    with open(os.path.join(_HERE, "cfb_delta_scale.json")) as _sf:
        _scale_override = (json.load(_sf) or {}).get("deltas", {}) or {}
except Exception:
    _scale_override = {}

def _scale_for(name):
    o = _scale_override.get(name) or {}
    lg = o.get("large") if (o.get("n_large") or 0) >= 15 else None
    ms = o.get("massive") if (o.get("n_massive") or 0) >= 15 else None
    d = _DELTA_SCALE_DEFAULT.get(name)
    if d is None and lg is None and ms is None:
        return None
    return (lg if lg is not None else (d[0] if d else None), ms if ms is not None else (d[1] if d else None))

def _band_for(name, value):
    if value is None or value == 0:
        return None
    thr, sc = _delta_thr.get(name), _scale_for(name)
    if not thr or not sc:
        return None
    a = abs(value)
    win = sc[1] if a >= thr[1] else (sc[0] if a >= thr[0] else None)
    if win is None or win < 70:
        return None
    return "light" if win < 80 else ("green" if win < 90 else "teal")

def _compute_delta_thresholds(slate):
    pool = {}
    try:
        from datetime import datetime as _dt
        with open(os.path.join(_HERE, "cfb_delta_history.json")) as _hf:
            for _g in (json.load(_hf).get("games") or {}).values():
                if _g.get("season") == _dt.now().year and not _g.get("backfill"):
                    pool[(_g["away"], _g["home"])] = _g.get("deltas") or {}
    except Exception:
        pass
    pool.update(slate)
    vals = {}
    for dd in pool.values():
        for n, v in dd.items():
            if v:
                vals.setdefault(n, []).append(abs(v))
    for n, v in vals.items():
        if len(v) >= 20:
            sv = sorted(v)
            _delta_thr[n] = (sv[int(.75 * len(sv))], sv[min(int(.9 * len(sv)), len(sv) - 1)])

_GRID_FLAGS = {}   # (away, home) -> {'away': {'teal': [delta names], ...}, 'home': {...}}  (saved to generated/grid_flags.json for The Nuts)

_DELTA_LOG = {}   # (away, home) -> {delta name: value}; saved pre-game by cfb_delta_study.record() at the end of the run

def build_single_matchup_table(home_team, away_team, home_stats, away_stats):
    _row_log = {}
    _row_flags = {}
    # SIGN FIX (2026-10-06): "standard" deltas whose defense number is what the defense ALLOWS (lower = better).
    _DEF_ALLOWED_DELTAS = {"Line Yards Delta", "Total Pass Matchup Delta", "Passing Explosiveness Delta",
                           "Open Field Yards Delta", "Power Success Rate Delta", "OSR vs. DSR Delta", "2nd Level Yards Delta"}
    sections_config = {
        # NEW: raw side-by-side team stats, no delta math -- requested as a block "above"
        # TEAM DELTAS. "SOR" in the request = OSR (Offense Success Rate / "Stay-on-Schedule Rate"), the only
        # stat in this project matching that description; there's no separate "SOR"-labeled stat in the source
        # PDF. Flagging that reading in case something else was meant.
        # REWRITE: back to a real Off-vs-Def cross-matchup display per your latest follow-up
        # ("much better looking grids for off vs def, under each team section") -- two small bordered grids,
        # one under Away, one under Home. The earlier attempt at this ("hanging off the grid") had a real bug:
        # the mini-grid's declared width (76pt) was wider than the actual usable space inside the 55pt Away/
        # Home column once you account for reportlab's default 6pt left+right cell padding (55-12=43pt usable)
        # -- the table doesn't clip, it just draws past the edge. Fixed by (1) zeroing this row's own left/
        # right padding on the Away and Home columns so each gets the full 55pt, and (2) using the new smaller
        # 5pt cell_*_sm styles so the grid itself only needs ~50pt, safely inside that 55pt.
        "OFF_DEF_GRID": [
            {"name": "PPG", "abbr": "PPG", "away_off": "Points Per Game (Offense)", "home_def": "Points Per Game (Defense)", "home_off": "Points Per Game (Offense)", "away_def": "Points Per Game (Defense)"},
            {"name": "YPG", "abbr": "YPG", "away_off": "Yards Per Game (Offense)", "home_def": "Yards Per Game (Defense)", "home_off": "Yards Per Game (Offense)", "away_def": "Yards Per Game (Defense)"},
            {"name": "YPP", "abbr": "YPP", "away_off": "Yards Per Attempt (Offense)", "home_def": "Yards Per Attempt (Defense)", "home_off": "Yards Per Attempt (Offense)", "away_def": "Yards Per Attempt (Defense)"},
            {"name": "RYPP", "abbr": "RYPP", "away_off": "Rush Yards Per Attempt (Offense)", "home_def": "Rush Yards Per Attempt (Defense)", "home_off": "Rush Yards Per Attempt (Offense)", "away_def": "Rush Yards Per Attempt (Defense)"},
            {"name": "PYPP", "abbr": "PYPP", "away_off": "Pass Yards Per Attempt (Offense)", "home_def": "Pass Yards Per Attempt (Defense)", "home_off": "Pass Yards Per Attempt (Offense)", "away_def": "Pass Yards Per Attempt (Defense)"},
        ],
        "TEAM INFO": [
            {"name": "Pass Play %", "type": "raw_pair", "away": "Pass Play Pct (Offense)", "home": "Pass Play Pct (Offense)", "suffix": "%"},
            {"name": "Rush Play %", "type": "raw_pair", "away": "Rush Play Pct (Offense)", "home": "Rush Play Pct (Offense)", "suffix": "%"},
            {"name": "FEI", "type": "raw_pair", "away": "FEI", "home": "FEI"},
            # UPDATE: SOR moved out of this grid and into the header next to each team's name
            # instead (per your follow-up) -- see the header-building block in Section 4.
        ],
        "TEAM DELTAS": [
            {"name": "Offensive Efficiency Delta", "type": "standard", "away_off": "Offensive Efficiency", "home_def": "Defensive Efficiency", "home_off": "Offensive Efficiency", "away_def": "Defensive Efficiency"},
            {"name": "Net Success Rate Delta", "type": "direct_sub", "away": "Net Success Rate", "home": "Net Success Rate"}
            # MOVED: Passing Down Panic Delta moved down to PASS DELTAS -- it's built from
            # each team's overall Off PPA (EPA/play), not a passing-specific number, but conceptually/name-wise
            # it belongs grouped with the passing metrics rather than the general team deltas.
        ],
        "LINE DELTAS": [
            {"name": "Line Yards Delta", "type": "standard", "away_off": "Line Yards (Offense)", "home_def": "Line Yards (Defense)", "home_off": "Line Yards (Offense)", "away_def": "Line Yards (Defense)"},
            {"name": "Stuff Rate Delta", "type": "inverted", "home_def": "Stuff Rate (Defense)", "away_off": "Stuff Rate (Offense)", "away_def": "Stuff Rate (Defense)", "home_off": "Stuff Rate (Offense)"},
            # MOVED: Power Success Rate Delta moved down to RUSH DELTAS -- per the blueprint
            # (line deltas.txt) it's short-yardage 3rd/4th-down conversion rate, which in practice is almost
            # always a run-play stat, so it fits better grouped with the rushing metrics than the line metrics.
            # FIX: blueprint (line deltas.txt) defines Sacks/TFL/Havoc Delta as "(Away's OWN
            # Def stat minus Away's OWN Off-allowed stat) - (Home's OWN Def stat minus Home's OWN Off-allowed
            # stat)" -- each bracket term stays inside ONE team's own two numbers. The old "inverted" type
            # crossed teams within each term instead (home_def vs away_off). Added a new "net_margin" type
            # (Section 4) that matches the real per-team-net-then-subtract shape and rewired all three to it.
            {"name": "Sacks Delta", "type": "net_margin", "away_def": "Sacks Created (Defense)", "away_off": "Sacks Allowed (Offense)", "home_def": "Sacks Created (Defense)", "home_off": "Sacks Allowed (Offense)"},
            {"name": "TFL Delta", "type": "net_margin", "away_def": "TFL Created (Defense)", "away_off": "TFL Allowed (Offense)", "home_def": "TFL Created (Defense)", "home_off": "TFL Allowed (Offense)"},
            {"name": "Havoc Rate Delta", "type": "net_margin", "away_def": "Havoc Rate (Defense/Forced)", "away_off": "Havoc Rate (Offense/Suffered)", "home_def": "Havoc Rate (Defense/Forced)", "home_off": "Havoc Rate (Offense/Suffered)"}
        ],
        "PASS DELTAS": [
            # FIX: blueprint (pass deltas.txt #1) is a plain "standard" bracket on PASS yards
            # per game specifically -- no division by efficiency. Was wired as a "ratio" type dividing by the
            # general (non-pass-specific) Yards Per Attempt, and pulled total-offense Yards Per Game instead of
            # the PDF's own separate "PASS YARDS / GAME" line. Switched to standard + added real pass-yards-
            # per-game extraction in Section 5 (previously never parsed at all).
            {"name": "Total Pass Matchup Delta", "type": "standard", "away_off": "Pass Yards Per Game (Offense)", "home_def": "Pass Yards Per Game (Defense)", "home_off": "Pass Yards Per Game (Offense)", "away_def": "Pass Yards Per Game (Defense)"},
            {"name": "Passing Explosiveness Delta", "type": "standard", "away_off": "Passing Explosiveness (Offense)", "home_def": "Passing Explosiveness (Defense)", "home_off": "Passing Explosiveness (Offense)", "away_def": "Passing Explosiveness (Defense)"},
            # FIX: blueprint (pass deltas.txt #3) is also a plain "standard" bracket, not a
            # volume/efficiency ratio.
            {"name": "Open Field Yards Delta", "type": "standard", "away_off": "Open Field Yards (Offense)", "home_def": "Open Field Yards (Defense)", "home_off": "Open Field Yards (Offense)", "away_def": "Open Field Yards (Defense)"},
            # MOVED: relocated here from TEAM DELTAS, per your call -- see the dated note on
            # what this is actually built from (each team's overall Off PPA/EPA-per-play, not a passing-down-
            # specific stat; no literal "panic"-labeled stat exists in the source PDF).
            {"name": "Passing Down Panic Delta", "type": "direct_sub", "away": "Panic Index (Offense PPA)", "home": "Panic Index (Offense PPA)"}
        ],
        "RUSH DELTAS": [
            # MOVED: relocated here from LINE DELTAS -- short-yardage 3rd/4th-down conversion
            # rate, almost always a run-play stat per your question about it.
            {"name": "Power Success Rate Delta", "type": "standard", "away_off": "Power Success (Offense)", "home_def": "Power Success (Defense)", "home_off": "Power Success (Offense)", "away_def": "Power Success (Defense)"},
            {"name": "OSR vs. DSR Delta", "type": "standard", "away_off": "OSR (Offense Success Rate)", "home_def": "DSR (Defense Success Rate)", "home_off": "OSR (Offense Success Rate)", "away_def": "DSR (Defense Success Rate)"},
            # FIX: blueprint (rushing delta.txt #2) wants the ratio's volume/efficiency terms
            # to be RUSH-specific ("Away_Off_RushYards" / "Away_Off_rushYPA"), not the run-blocking "Line
            # Yards" metric and the general (non-rush-specific) Yards Per Attempt wired here. The "ratio"
            # formula shape was already correct -- only the source keys were wrong. Added real rush-yards-per-
            # game and rush-yards-per-play extraction in Section 5 (previously never parsed).
            {"name": "Rushing Reality Delta", "type": "ratio", "away_vol": "Rush Yards Per Game (Offense)", "home_vol_allowed": "Rush Yards Per Game (Defense)", "away_eff": "Rush Yards Per Attempt (Offense)", "home_eff_allowed": "Rush Yards Per Attempt (Defense)", "home_vol": "Rush Yards Per Game (Offense)", "away_vol_allowed": "Rush Yards Per Game (Defense)", "home_eff": "Rush Yards Per Attempt (Offense)", "away_eff_allowed": "Rush Yards Per Attempt (Defense)"},
            {"name": "2nd Level Yards Delta", "type": "standard", "away_off": "2nd Level Yards (Offense)", "home_def": "2nd Level Yards (Defense)", "home_off": "2nd Level Yards (Offense)", "away_def": "2nd Level Yards (Defense)"}
        ]
    }

# =====================================================================
# BOUNDARY LINE: END OF SECTION 3 - PASTE SECTION 4 DIRECTLY BELOW
# =====================================================================
# =====================================================================
# HEADER: SECTION 4 - MATRIX MATH CALCULATION ENGINE
# DESCRIPTION: Computes values, isolates team advantages, formats rows, 
# and compiles separate 300-point mini-tables.
# =====================================================================

    # NEW: highlight a team's name in the header (green) when they have the better-OR-SAME
    # value in ALL FOUR of FEI, Points Per Game, Open Field Yards (Offense), and Sacks Created (Defense).
    # UPDATE: switched from "strictly better in all 4" to "better or tied in all 4" per your
    # follow-up -- a category where the two teams are exactly equal no longer blocks the sweep. Each side is
    # checked independently (away >= home in all 4, separately from home >= away in all 4), so a true four-way
    # tie across both teams would highlight both names green rather than neither. Missing data in any one of
    # the four still blocks that side's highlight -- can't confirm "better or same in all four" if one is
    # unknown.
    def _at_least(away_val, home_val, side):
        av, hv = safe_float(away_val), safe_float(home_val)
        if av is None or hv is None: return False
        return av >= hv if side == "away" else hv >= av

    _sweep_categories = [
        (away_stats.get("FEI"), home_stats.get("FEI")),
        (away_stats.get("Points Per Game (Offense)"), home_stats.get("Points Per Game (Offense)")),
        (away_stats.get("Open Field Yards (Offense)"), home_stats.get("Open Field Yards (Offense)")),
        (away_stats.get("Sacks Created (Defense)"), home_stats.get("Sacks Created (Defense)")),
    ]
    away_sweeps = all(_at_least(a, h, "away") for a, h in _sweep_categories)
    home_sweeps = all(_at_least(a, h, "home") for a, h in _sweep_categories)

    # NEW: orange highlight when a team is better-or-same in exactly THREE of the same four
    # categories used for the green sweep above (a near-miss on the full sweep), rather than all four.
    # FIX: first version of this counted DATA AVAILABILITY (how many of the 4 stats exist for
    # that team) instead of WINS. Verified against the real Louisville @ North Carolina State page -- both
    # teams actually have all 4 stats on file (confirmed via debug print of the real parsed away/home dicts),
    # so the data-availability version correctly found nothing to flag there, but you said Louisville should
    # be orange. Checking the actual values: Louisville (away) is ahead on FEI (0.510 v 0.070), Points Per
    # Game (35.3 v 26.7), and Sacks Created (Defense) (1.7 v 0.7), and only behind on Open Field Yards
    # (Offense) (1.944 v 2.007) -- exactly 3 of 4 wins, a near-sweep. That's what "only has 3 of those 4"
    # meant. Reuses _at_least so a missing stat still can't count as a win for either side.
    def _win_count(side):
        return sum(1 for a, h in _sweep_categories if _at_least(a, h, side))

    away_partial = _win_count("away") == 3
    home_partial = _win_count("home") == 3

    _GREEN = "#4ADE80"
    _ORANGE = "#FB923C"
    # NEW: SOR next to the team name in the header, per your follow-up -- not inside the
    # green <font> tag, so the highlight (Section 4 note above) still only colors the name itself, not the
    # SOR text next to it.
    away_sor_disp = away_stats.get("SOR", "N/A")
    home_sor_disp = home_stats.get("SOR", "N/A")
    # FIX: escape team names before they go into this Paragraph-bound HTML string (see
    # _xml_esc note above) -- an unescaped "&" (Texas A&M) was breaking reportlab's XML parser.
    away_team_esc, home_team_esc = _xml_esc(away_team), _xml_esc(home_team)
    away_name_html = (f"<font color='{_GREEN}'><b>{away_team_esc}</b></font>" if away_sweeps
                       else f"<font color='{_ORANGE}'><b>{away_team_esc}</b></font>" if away_partial
                       else away_team_esc)
    home_name_html = (f"<font color='{_GREEN}'><b>{home_team_esc}</b></font>" if home_sweeps
                       else f"<font color='{_ORANGE}'><b>{home_team_esc}</b></font>" if home_partial
                       else home_team_esc)
    # yellow highlight on the team the stat favors -- SOR here (lower rank = better resume).
    def _sor_txt(_disp, _win):
        _t = f"(SOR: {_disp})"
        return f"<font color='#111111' backColor='#FFF176'>&nbsp;{_t}&nbsp;</font>" if _win else _t
    _a_sor, _h_sor = safe_float(away_sor_disp), safe_float(home_sor_disp)
    _sor_away_wins = None not in (_a_sor, _h_sor) and _a_sor < _h_sor
    _sor_home_wins = None not in (_a_sor, _h_sor) and _h_sor < _a_sor
    away_hdr_txt = f"<b>AWAY:</b> {away_name_html} {_sor_txt(away_sor_disp, _sor_away_wins)}"
    home_hdr_txt = f"<b>HOME:</b> {home_name_html} {_sor_txt(home_sor_disp, _sor_home_wins)}"

    # FIX: team names were centered within just the native 55pt Away/Home column, which
    # forced long names onto 3-4 cramped lines right at the table's outer edge. Same fix as the OFF_DEF_GRID
    # row below -- SPAN the header row across all 3 outer columns and use a nested wrapper table so each name
    # gets a much wider, comfortable zone to center in (125pt instead of 55pt), still bounded by the METRICS
    # label in the middle and the sheet's outer edge on the far side -- "between metrics and the edge."
    hdr_wrapper = Table([[Paragraph(away_hdr_txt, hdr_left), Paragraph("<b>METRICS</b>", hdr_center), Paragraph(home_hdr_txt, hdr_right)]], colWidths=[125, 50, 125])
    hdr_wrapper.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 4), ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 0.5), ('BOTTOMPADDING', (0,0), (-1,-1), 0.5),
    ]))

    table_data = [[hdr_wrapper, "", ""]]
    
    # Clamped internal vertical cell padding to an ultra-compact 0.5pt
    t_style = [
        # FIX: empty "" placeholder cells (one side of a delta row with no value) were
        # defaulting to reportlab's 10pt Table font, forcing every such row to ~13pt tall regardless of the
        # real 6pt cell styles -- pure dead space. Explicit default font closes that gap (verified: this alone
        # took a single matchup table from ~332pt down to ~242pt tall, with no visible text getting smaller).
        ('FONT', (0,0), (-1,-1), 'Helvetica', 6, 7),
        ('SPAN', (0,0), (-1,0)),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1A365D")), 
        ('ALIGN', (0,0), (-1,0), 'CENTER'), 
        ('LEFTPADDING', (0,0), (-1,0), 0), ('RIGHTPADDING', (0,0), (-1,0), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0.5), 
        ('TOPPADDING', (0,0), (-1,-1), 0.5), 
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")), 
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
    ]
    
    row_idx = 1
    for sec_name, metrics in sections_config.items():
        if sec_name == "OFF_DEF_GRID":
            # Two small bordered grids, no header bar. Previous version pinned these directly into the
            # outer table's native 55pt Away/Home columns with the padding zeroed out -- that's why they
            # ended up smashed flush against the outer left/right edges of the sheet (zero padding = zero
            # breathing room). Per your latest note, they don't need to fit exactly under the team name --
            # so instead this row SPANs the full width and wraps both grids in a simple 2-cell table
            # ([150, 150]) with CENTER alignment, so each grid just floats centered in its own half with
            # normal padding around it, rather than being jammed into the narrow native column.
            def _mini_grid(off_side, def_side):
                off_stats = away_stats if off_side == "away" else home_stats
                def_stats = away_stats if def_side == "away" else home_stats
                rows = []
                for m in metrics:
                    off_raw, def_raw = off_stats.get(m[f"{off_side}_off"]), def_stats.get(m[f"{def_side}_def"])
                    off_disp = f"{off_raw}" if off_raw not in (None, "N/A") else "N/A"
                    def_disp = f"{def_raw}" if def_raw not in (None, "N/A") else "N/A"
                    rows.append([Paragraph(off_disp, cell_left_sm), Paragraph(m["abbr"], cell_center_sm), Paragraph(def_disp, cell_right_sm)])
                # FIX: widened the value columns (20/16/17 -> 26/18/23) alongside the
                # extra padding below -- the first padding-only attempt squeezed "283.8"-style values into too
                # little usable space and wrapped them to 2 lines. This ONLY touches this off/def mini-grid
                # (the PPG/YPG/YPP/RYPP/PYPP rows right under each team header); TEAM INFO/DELTAS below use the
                # outer table's own padding and are untouched.
                g = Table(rows, colWidths=[34, 20, 31])
                _yel = []
                _ppg_a, _ppg_h = safe_float(away_stats.get("Points Per Game (Offense)")), safe_float(home_stats.get("Points Per Game (Offense)"))
                if None not in (_ppg_a, _ppg_h) and _ppg_a != _ppg_h:
                    _own_wins = (_ppg_a > _ppg_h) if off_side == "away" else (_ppg_h > _ppg_a)
                    if _own_wins:
                        _yel.append(('BACKGROUND', (0, 0), (0, 0), colors.HexColor("#FFF176")))   # PPG is the first row
                g.setStyle(TableStyle([
                    ('BOTTOMPADDING', (0,0), (-1,-1), 0.4), ('TOPPADDING', (0,0), (-1,-1), 0.4),
                    ('LEFTPADDING', (0,0), (-1,-1), 1), ('RIGHTPADDING', (0,0), (-1,-1), 1),
                    ('LEFTPADDING', (0,0), (0,-1), 4),
                    ('RIGHTPADDING', (0,0), (0,-1), 14),
                    ('LEFTPADDING', (2,0), (2,-1), 14),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
                ] + _yel))
                return g

            away_grid = _mini_grid("away", "home")
            home_grid = _mini_grid("home", "away")

            wrapper = Table([[away_grid, home_grid]], colWidths=[150, 150])
            wrapper.setStyle(TableStyle([
                ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                ('ALIGN', (1, 0), (1, 0), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))

            table_data.append([wrapper, "", ""])
            t_style.append(('SPAN', (0, row_idx), (2, row_idx)))
            # Give the wrapper the full 300pt row width to center within -- same zero-padding fix as before,
            # now applied across all 3 outer columns since this row spans them.
            t_style.append(('LEFTPADDING', (0, row_idx), (2, row_idx), 0))
            t_style.append(('RIGHTPADDING', (0, row_idx), (2, row_idx), 0))
            if row_idx % 2 == 0: t_style.append(('BACKGROUND', (0, row_idx), (2, row_idx), colors.HexColor("#F8FAFC")))
            row_idx += 1
            continue
        table_data.append([Paragraph(sec_name, section_style), "", ""])
        t_style.extend([('SPAN', (0, row_idx), (2, row_idx)), ('BACKGROUND', (0, row_idx), (2, row_idx), colors.HexColor("#4A5568"))])
        row_idx += 1
        for m in metrics:
            delta_val = None
            aw_c, hm_c = "", ""
            _green = None       # (column, color) when this delta is large enough to earn green/teal
            _hl_col = None      # yellow on the side this row's stat favors (FEI, Off Eff, Net Success Rate)
            if m["type"] == "raw_pair":
                # NEW: not a delta -- just each team's own raw value shown side by side.
                av_raw, hv_raw = away_stats.get(m["away"]), home_stats.get(m["home"])
                suffix = m.get("suffix", "")
                av_disp = f"{av_raw}{suffix}" if av_raw not in (None, "N/A") else "N/A"
                hv_disp = f"{hv_raw}{suffix}" if hv_raw not in (None, "N/A") else "N/A"
                aw_c, hm_c = Paragraph(av_disp, cell_left), Paragraph(hv_disp, cell_right)
                if m["name"] == "FEI":
                    _fa, _fh = safe_float(av_raw), safe_float(hv_raw)
                    if None not in (_fa, _fh) and _fa != _fh:
                        _hl_col = 0 if _fa > _fh else 2          # higher FEI = better
            else:
                if m["type"] == "standard":
                    ao, hd, ho, ad = safe_float(away_stats.get(m["away_off"])), safe_float(home_stats.get(m["home_def"])), safe_float(home_stats.get(m["home_off"])), safe_float(away_stats.get(m["away_def"]))
                    # SIGN FIX (2026-10-06): when the "defense" number is what the defense ALLOWS (lower = better),
                    # (ao - hd) - (ho - ad) credits a leaky defense as if it were stingy. For those stats use
                    # (ao - ho) + (hd - ad): the better offense AND the leakier opposing defense both push toward that team.
                    # Offensive Efficiency's defense number (ESPN Def Eff) is higher = better, so it keeps the original.
                    if None not in (ao, hd, ho, ad):
                        delta_val = ((ao - ho) + (hd - ad)) if m["name"] in _DEF_ALLOWED_DELTAS else (ao - hd) - (ho - ad)
                elif m["type"] == "direct_sub":
                    av, hv = safe_float(away_stats.get(m["away"])), safe_float(home_stats.get(m["home"]))
                    if None not in (av, hv): delta_val = av - hv
                elif m["type"] == "inverted":
                    hd, ao, ad, ho = safe_float(home_stats.get(m["home_def"])), safe_float(away_stats.get(m["away_off"])), safe_float(away_stats.get(m["away_def"])), safe_float(home_stats.get(m["home_off"]))
                    # SIGN FIX (2026-10-06): Stuff Rate (Offense) = how often this offense gets stuffed (higher = worse),
                    # Stuff Rate (Defense) = how often this defense stuffs (higher = better). Old formula had the defense
                    # terms backwards. Positive still favors away: (Away def stuffs - Home def stuffs) + (Home off stuffed - Away off stuffed).
                    if None not in (hd, ao, ad, ho): delta_val = (ad - hd) + (ho - ao)
                elif m["type"] == "net_margin":
                    # NEW: (that team's own Def stat - that team's own Off-allowed stat), per
                    # team, then subtracted. See the dated note on Sacks/TFL/Havoc Rate Delta in Section 3.
                    a_def, a_off = safe_float(away_stats.get(m["away_def"])), safe_float(away_stats.get(m["away_off"]))
                    h_def, h_off = safe_float(home_stats.get(m["home_def"])), safe_float(home_stats.get(m["home_off"]))
                    if None not in (a_def, a_off, h_def, h_off): delta_val = (a_def - a_off) - (h_def - h_off)
                elif m["type"] == "ratio":
                    avol, h_va, aeff, h_ea = safe_float(away_stats.get(m["away_vol"])), safe_float(home_stats.get(m["home_vol_allowed"])), safe_float(away_stats.get(m["away_eff"])), safe_float(home_stats.get(m["home_eff_allowed"]))
                    hvol, a_va, heff, a_ea = safe_float(home_stats.get(m["home_vol"])), safe_float(away_stats.get(m["away_vol_allowed"])), safe_float(home_stats.get(m["home_eff"])), safe_float(away_stats.get(m["away_eff_allowed"]))
                    # FIX: this used to subtract (aeff - h_ea)/(heff - a_ea) BEFORE
                    # checking either side for None, unlike every other branch above -- crashed with
                    # "unsupported operand type(s) for -: 'NoneType' and 'NoneType'" the first time a
                    # team with genuinely no TeamRankings stats (McNeese, Samford, Texas Southern --
                    # real FCS buy-games that used to get silently dropped from the whole report, now
                    # kept per the 2026-10-04 known_teams fix) reached this code path. Guarded the same
                    # way as every other branch: compute d1/d2 only when their own inputs aren't None.
                    d1 = (aeff - h_ea) if None not in (aeff, h_ea) else None
                    d2 = (heff - a_ea) if None not in (heff, a_ea) else None
                    if None not in (avol, h_va, d1, hvol, a_va, d2) and d1 != 0 and d2 != 0: delta_val = ((avol - h_va) / d1) - ((hvol - a_va) / d2)
                if delta_val is not None:
                    # FIX: was `abs(delta_val)` before formatting, so EVERY printed delta
                    # showed a "+" sign no matter which column it landed in -- you could only tell away vs
                    # home by position, not by the sign itself, which contradicts the "positive favors away,
                    # negative favors home" convention stated throughout the blueprint files (team/line/pass/
                    # rushing deltas .txt). Dropped the abs(): the away branch only ever fires when delta_val
                    # is already positive, so it still prints with "+"; the home branch only fires when
                    # delta_val is negative, so it now prints with an actual "-" sign.
                    _row_log[m["name"]] = delta_val          # 2026-10-07: saved for the delta-scale study
                    _band = _band_for(m["name"], delta_val)
                    if _band:
                        _green = (0 if delta_val > 0 else 2, _BAND_COLORS[_band])
                        _row_flags.setdefault("away" if delta_val > 0 else "home", {}).setdefault(_band, []).append(m["name"])
                    disp = f"{delta_val:+.2f}"
                    if m["name"] in ("Offensive Efficiency Delta", "Net Success Rate Delta") and delta_val != 0:
                        _hl_col = 0 if delta_val > 0 else 2
                    if delta_val > 0: aw_c = Paragraph(f"<b>{disp}</b>", cell_left)
                    elif delta_val < 0: hm_c = Paragraph(f"<b>{disp}</b>", cell_right)
                    else: aw_c, hm_c = Paragraph("0.00", cell_left), Paragraph("0.00", cell_right)
                else: aw_c, hm_c = Paragraph("N/A", cell_left), Paragraph("N/A", cell_right)
            table_data.append([aw_c, Paragraph(m["name"], cell_center), hm_c])
            if row_idx % 2 == 0: t_style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor("#F8FAFC")))
            if _hl_col is not None: t_style.append(('BACKGROUND', (_hl_col, row_idx), (_hl_col, row_idx), colors.HexColor("#FFF176")))
            if _green is not None: t_style.append(('BACKGROUND', (_green[0], row_idx), (_green[0], row_idx), colors.HexColor(_green[1])))   # large gap beats plain yellow
            row_idx += 1

        # NEW: "Predicted Team Total" + "Spread" rows, right under FEI (the last TEAM INFO
        # metric above). Formula:
        #   away_rolling_ppd = (Away's own last-3-games Off PPD + Home's own last-3-games Def PPD allowed) / 2
        #   home_rolling_ppd = (Home's own last-3-games Off PPD + Away's own last-3-games Def PPD allowed) / 2
        #   predicted_total  = rolling_ppd * 12.5                              (12.5 = avg drives/game)
        #   havoc_margin     = abs(Havoc Rate Delta) * 0.35, added to whichever team the delta favors
        #                      (same "positive favors away, negative favors home" sign convention as every
        #                      other delta row on this sheet -- see Section 4's Havoc Rate Delta note)
        #   home_total      += 2.5                                             (home-field)
        #   Spread = away_total - home_total, shown like any other delta row (positive -> away column,
        #            negative -> home column), so the number lands under whichever team it favors.
        if sec_name == "TEAM INFO":
            # CHANGED: was lookup_ppd(cache); now read from this script's own
            # already-parsed away/home dicts (see the find_h_b() calls by FEI above), sourced
            # from the matrices PDF text like everything else here instead of a side-channel file.
            away_off_ppd = safe_float(away_stats.get("Off PPD (Last 3)"))
            away_def_ppd = safe_float(away_stats.get("Def PPD (Last 3)"))
            home_off_ppd = safe_float(home_stats.get("Off PPD (Last 3)"))
            home_def_ppd = safe_float(home_stats.get("Def PPD (Last 3)"))

            away_total, home_total = None, None
            if None not in (away_off_ppd, home_def_ppd, home_off_ppd, away_def_ppd):
                away_rolling_ppd = (away_off_ppd + home_def_ppd) / 2
                home_rolling_ppd = (home_off_ppd + away_def_ppd) / 2
                away_total = away_rolling_ppd * 12.5
                home_total = home_rolling_ppd * 12.5

                a_def_hav = safe_float(away_stats.get("Havoc Rate (Defense/Forced)"))
                a_off_hav = safe_float(away_stats.get("Havoc Rate (Offense/Suffered)"))
                h_def_hav = safe_float(home_stats.get("Havoc Rate (Defense/Forced)"))
                h_off_hav = safe_float(home_stats.get("Havoc Rate (Offense/Suffered)"))
                if None not in (a_def_hav, a_off_hav, h_def_hav, h_off_hav):
                    havoc_delta = (a_def_hav - a_off_hav) - (h_def_hav - h_off_hav)
                    havoc_margin = abs(havoc_delta) * 0.35
                    if havoc_delta > 0: away_total += havoc_margin
                    elif havoc_delta < 0: home_total += havoc_margin

                home_total += 2.5

            if away_total is not None and home_total is not None:
                aw_tot_c = Paragraph(f"<b>{away_total:.1f}</b>", cell_left)
                hm_tot_c = Paragraph(f"<b>{home_total:.1f}</b>", cell_right)
            else:
                aw_tot_c, hm_tot_c = Paragraph("N/A", cell_left), Paragraph("N/A", cell_right)
            table_data.append([aw_tot_c, Paragraph("Predicted Team Total", cell_center), hm_tot_c])
            if row_idx % 2 == 0: t_style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor("#F8FAFC")))
            row_idx += 1

            if away_total is not None and home_total is not None:
                # FIX: was showing the FAVORED team's own column with a "+" sign
                # (e.g. Western Kentucky +6.4 while projected to outscore New Mexico State 30.6-24.2)
                # -- backwards from real spread notation, where the favorite is NEGATIVE ("-6.4",
                # favored BY 6.4) and only the underdog shows "+" (getting points). Every other row
                # on this sheet uses "positive favors away/negative favors home" on purpose (that's
                # this project's own delta convention), but "Spread" specifically reads as a real
                # sportsbook line, so it needs the opposite sign on the favored side to not look like
                # that team is picked to lose. Still only prints in the favored team's column (same
                # single-value style as every other row here) -- just negative now instead of positive.
                spread = away_total - home_total
                _row_log["PPD Spread"] = spread          # + favors away (the display flips the sign)
                if spread > 0:  # away favored, by `spread` points
                    aw_spr_c, hm_spr_c = Paragraph(f"<b>-{spread:.1f}</b>", cell_left), ""
                elif spread < 0:  # home favored, by `-spread` points
                    aw_spr_c, hm_spr_c = "", Paragraph(f"<b>-{abs(spread):.1f}</b>", cell_right)
                else: aw_spr_c, hm_spr_c = Paragraph("0.0", cell_left), Paragraph("0.0", cell_right)
            else:
                aw_spr_c, hm_spr_c = Paragraph("N/A", cell_left), Paragraph("N/A", cell_right)
            table_data.append([aw_spr_c, Paragraph("Spread", cell_center), hm_spr_c])
            if row_idx % 2 == 0: t_style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor("#F8FAFC")))
            row_idx += 1

    # FIX: Explicitly filled column widths [55pt Away, 190pt Metric, 55pt Home] totaling 300pt
    # 2026-10-07: raw-stat gaps for the delta-scale study (same sign as the deltas: + favors AWAY)
    try:
        _fa, _fh = safe_float(away_stats.get("FEI")), safe_float(home_stats.get("FEI"))
        if None not in (_fa, _fh): _row_log["FEI Gap"] = _fa - _fh                      # higher FEI = better
        _pa, _ph = safe_float(away_stats.get("Points Per Game (Offense)")), safe_float(home_stats.get("Points Per Game (Offense)"))
        if None not in (_pa, _ph): _row_log["Off PPG Gap"] = _pa - _ph
        _sa, _sh = safe_float(away_stats.get("SOR")), safe_float(home_stats.get("SOR"))
        if None not in (_sa, _sh): _row_log["SOR Gap"] = _sh - _sa                      # lower SOR rank = better
        _DELTA_LOG[(away_team, home_team)] = _row_log
        _GRID_FLAGS[(away_team, home_team)] = _row_flags
    except Exception:
        pass
    t = Table(table_data, colWidths=[55, 190, 55])
    t.setStyle(TableStyle(t_style))
    return t

# =====================================================================
# BOUNDARY LINE: END OF SECTION 4 - PASTE SECTION 5 DIRECTLY BELOW
# =====================================================================
# =====================================================================
# HEADER: SECTION 5 - DATABASE TEXT PARSER LOOP
# DESCRIPTION: Loops pages, handles matchups, pulls vertical/horizontal stats, 
# and populates dictionary containers.
# =====================================================================

matchups_list = []
_pending_tables = []
reader = PdfReader(_MATRICES_PDF)
for current_idx, page in enumerate(reader.pages):
    text = page.extract_text()
    if not text or "OFFENSE VS" not in text.upper(): continue
    # FIX: a matchup that runs long spills its last ADVANCED RATINGS lines (DEF 2ND LEVEL
    # YARDS ALLOWED, DEF OPEN FIELD, etc.) onto the NEXT matrices page, which has no "OFFENSE VS" header.
    # Only page 1 was parsed here, so 2nd Level Yards (Defense) -- and everything else that spilled -- came
    # out N/A in ~51 of 58 games. Append the continuation page's text (same rule the pdfplumber pass below uses).
    if (current_idx + 1) < len(reader.pages):
        _cont = reader.pages[current_idx + 1].extract_text()
        if _cont and "OFFENSE VS" not in _cont.upper():
            text = text + "\n" + _cont
    # FIX: team-name capture only allowed letters/whitespace/hyphen, which silently dropped
    # any matchup with a team name containing another character -- confirmed missing Texas A&M (the "&") and
    # Hawai'i (the apostrophe), 2 of the 47 matchup pages in the source PDF. Widened to also allow apostrophes,
    # ampersands, and periods (covers "St." names too) without changing anything else about the match.
    t_matches = re.findall(r"SOS Rk --\s*([A-Z\s\-'&.()]+?)\s*\(\d+-\d+", text)
    if len(t_matches) < 2: continue
    
    # FIX: the previous "CRITICAL FIX 1" swap was itself backwards. t_matches[0] is the
    # FIRST "SOS Rk --" team on the page, which is always the AWAY team (confirmed against real text: on the
    # Western Kentucky @ New Mexico State page, t_matches[0] = "WESTERN KENTUCKY", t_matches[1] = "NEW MEXICO
    # STATE", and Western Kentucky is away) -- same left/first = away convention used project-wide.
    # FIX: some source pages wrap a team name across two lines mid-extraction (e.g. "SAN
    # JOSE\nSTATE"), which would otherwise leave a literal line break inside the displayed team name. Collapse
    # any run of whitespace (including newlines) to a single space.
    away_team = re.sub(r"\s+", " ", t_matches[0]).strip()
    home_team = re.sub(r"\s+", " ", t_matches[1]).strip()
    
    home, away = {}, {}
    away["SOR"], home["SOR"] = lookup_sor(away_team), lookup_sor(home_team)
    eff_blocks = re.findall(r"Off Eff\s+([\d.\-]+)\s*\(\d+\)\s+Def Eff\s+([\d.\-]+)\s*\(\d+\)", text)
    if len(eff_blocks) >= 2:
        # FIX: old regex never matched real text -- "Off Eff 34.3 (103) Def Eff 27.7 (10)"
        # has a "(rank)" parenthetical between the value and "Def Eff" that the old \s+ couldn't span, so this
        # always fell through silently and Offensive Efficiency Delta showed N/A for every matchup.
        # Also reversed home/away: the first "Off Eff ... Def Eff ..." line on the page belongs to the AWAY
        # team (same left/away, right/home convention as the SOS Rk lines just above it), not home.
        away["Offensive Efficiency"], away["Defensive Efficiency"] = clean_stat(eff_blocks[0][0]), clean_stat(eff_blocks[0][1])
        home["Offensive Efficiency"], home["Defensive Efficiency"] = clean_stat(eff_blocks[1][0]), clean_stat(eff_blocks[1][1])
        
    sections = text.split("OFFENSE vs")
    if len(sections) >= 3:
        b1, b2 = sections[1], sections[2]
        yg_1 = re.search(r"([\d.]+)\s*\(\d+\)\s+YARDS / GAME\s+([\d.]+)", b1)
        yp_1 = re.search(r"([\d.]+)\s*\(\d+\)\s+YARDS / PLAY\s+([\d.]+)", b1)
        sa_1 = re.search(r"([\d.]+)\s*\(\d+\)\s+SACKS ALLOWED\s+([\d.]+)", b1)
        tf_1 = re.search(r"([\d.]+)\s*\(\d+\)\s+TFL\s+([\d.]+)", b1)
        # FIX: b1 is the AWAY team's "OFFENSE vs" block (e.g. "WESTERN KENTUCKY OFFENSE vs
        # NEW MEXICO STATE DEFENSE"), so group(1) is away's offense stat and group(2) is home's defense-allowed
        # stat -- these four lines had it backwards.
        if yg_1: away["Yards Per Game (Offense)"], home["Yards Per Game (Defense)"] = clean_stat(yg_1.group(1)), clean_stat(yg_1.group(2))
        if yp_1: away["Yards Per Attempt (Offense)"], home["Yards Per Attempt (Defense)"] = clean_stat(yp_1.group(1)), clean_stat(yp_1.group(2))
        if sa_1: away["Sacks Allowed (Offense)"], home["Sacks Created (Defense)"] = clean_stat(sa_1.group(1)), clean_stat(sa_1.group(2))
        if tf_1: away["TFL Allowed (Offense)"], home["TFL Created (Defense)"] = clean_stat(tf_1.group(1)), clean_stat(tf_1.group(2))

        # NEW: PTS/Game, PASS & RUSH yards-per-game (+ each team's own play-share %), and
        # PASS & RUSH yards-per-play were never parsed at all before. Needed for the new "TEAM INFO" header
        # block and to source Total Pass Matchup Delta / Rushing Reality Delta from the real play-type-specific
        # stats instead of the general (non-pass/rush-specific) Yards Per Game / Yards Per Attempt numbers.
        pts_1 = re.search(r"([\d.]+)\s*\(\d+\)\s+POINTS / GAME\s+([\d.]+)", b1)
        pass_1 = re.search(r"([\d.]+)\s*\(\d+\)\s*\(([\d.]+)%\)\s*PASS YARDS / GAME \(% OF PLAYS\)\s+([\d.]+)\s*\(\d+\)\s*\(([\d.]+)%\)", b1)
        passp_1 = re.search(r"([\d.]+)\s*\(\d+\)\s+PASS YARDS / PLAY\s+([\d.]+)", b1)
        rush_1 = re.search(r"([\d.]+)\s*\(\d+\)\s*\(([\d.]+)%\)\s*RUSH YARDS / GAME \(% OF PLAYS\)\s+([\d.]+)\s*\(\d+\)\s*\(([\d.]+)%\)", b1)
        rushp_1 = re.search(r"([\d.]+)\s*\(\d+\)\s+RUSH YARDS / PLAY\s+([\d.]+)", b1)
        if pts_1: away["Points Per Game (Offense)"], home["Points Per Game (Defense)"] = clean_stat(pts_1.group(1)), clean_stat(pts_1.group(2))
        if pass_1:
            away["Pass Yards Per Game (Offense)"], away["Pass Play Pct (Offense)"] = clean_stat(pass_1.group(1)), clean_stat(pass_1.group(2))
            home["Pass Yards Per Game (Defense)"], home["Pass Play Pct (Defense)"] = clean_stat(pass_1.group(3)), clean_stat(pass_1.group(4))
        if passp_1: away["Pass Yards Per Attempt (Offense)"], home["Pass Yards Per Attempt (Defense)"] = clean_stat(passp_1.group(1)), clean_stat(passp_1.group(2))
        if rush_1:
            away["Rush Yards Per Game (Offense)"], away["Rush Play Pct (Offense)"] = clean_stat(rush_1.group(1)), clean_stat(rush_1.group(2))
            home["Rush Yards Per Game (Defense)"], home["Rush Play Pct (Defense)"] = clean_stat(rush_1.group(3)), clean_stat(rush_1.group(4))
        if rushp_1: away["Rush Yards Per Attempt (Offense)"], home["Rush Yards Per Attempt (Defense)"] = clean_stat(rushp_1.group(1)), clean_stat(rushp_1.group(2))

        yg_2 = re.search(r"([\d.]+)\s*\(\d+\)\s+YARDS / GAME\s+([\d.]+)", b2)
        yp_2 = re.search(r"([\d.]+)\s*\(\d+\)\s+YARDS / PLAY\s+([\d.]+)", b2)
        sa_2 = re.search(r"([\d.]+)\s*\(\d+\)\s+SACKS ALLOWED\s+([\d.]+)", b2)
        tf_2 = re.search(r"([\d.]+)\s*\(\d+\)\s+TFL\s+([\d.]+)", b2)
        # b2 is the HOME team's "OFFENSE vs" block -- same reasoning, mirrored.
        if yg_2: home["Yards Per Game (Offense)"], away["Yards Per Game (Defense)"] = clean_stat(yg_2.group(1)), clean_stat(yg_2.group(2))
        if yp_2: home["Yards Per Attempt (Offense)"], away["Yards Per Attempt (Defense)"] = clean_stat(yp_2.group(1)), clean_stat(yp_2.group(2))
        if sa_2: home["Sacks Allowed (Offense)"], away["Sacks Created (Defense)"] = clean_stat(sa_2.group(1)), clean_stat(sa_2.group(2))
        if tf_2: home["TFL Allowed (Offense)"], away["TFL Created (Defense)"] = clean_stat(tf_2.group(1)), clean_stat(tf_2.group(2))

        pts_2 = re.search(r"([\d.]+)\s*\(\d+\)\s+POINTS / GAME\s+([\d.]+)", b2)
        pass_2 = re.search(r"([\d.]+)\s*\(\d+\)\s*\(([\d.]+)%\)\s*PASS YARDS / GAME \(% OF PLAYS\)\s+([\d.]+)\s*\(\d+\)\s*\(([\d.]+)%\)", b2)
        passp_2 = re.search(r"([\d.]+)\s*\(\d+\)\s+PASS YARDS / PLAY\s+([\d.]+)", b2)
        rush_2 = re.search(r"([\d.]+)\s*\(\d+\)\s*\(([\d.]+)%\)\s*RUSH YARDS / GAME \(% OF PLAYS\)\s+([\d.]+)\s*\(\d+\)\s*\(([\d.]+)%\)", b2)
        rushp_2 = re.search(r"([\d.]+)\s*\(\d+\)\s+RUSH YARDS / PLAY\s+([\d.]+)", b2)
        # b2 is the HOME team's own block -- same reasoning, mirrored (home gets group1, away gets group2).
        if pts_2: home["Points Per Game (Offense)"], away["Points Per Game (Defense)"] = clean_stat(pts_2.group(1)), clean_stat(pts_2.group(2))
        if pass_2:
            home["Pass Yards Per Game (Offense)"], home["Pass Play Pct (Offense)"] = clean_stat(pass_2.group(1)), clean_stat(pass_2.group(2))
            away["Pass Yards Per Game (Defense)"], away["Pass Play Pct (Defense)"] = clean_stat(pass_2.group(3)), clean_stat(pass_2.group(4))
        if passp_2: home["Pass Yards Per Attempt (Offense)"], away["Pass Yards Per Attempt (Defense)"] = clean_stat(passp_2.group(1)), clean_stat(passp_2.group(2))
        if rush_2:
            home["Rush Yards Per Game (Offense)"], home["Rush Play Pct (Offense)"] = clean_stat(rush_2.group(1)), clean_stat(rush_2.group(2))
            away["Rush Yards Per Game (Defense)"], away["Rush Play Pct (Defense)"] = clean_stat(rush_2.group(3)), clean_stat(rush_2.group(4))
        if rushp_2: home["Rush Yards Per Attempt (Offense)"], away["Rush Yards Per Attempt (Defense)"] = clean_stat(rushp_2.group(1)), clean_stat(rushp_2.group(2))

    def find_h_b(lbl_rgx, pg_txt):
        m = re.search(r"([-\d.]+)\s*\(\d+\)\s+" + lbl_rgx + r"\s+([-\d.]+)", pg_txt)
        return (clean_stat(m.group(1)), clean_stat(m.group(2))) if m else ("N/A", "N/A")

    # FIX: every find_h_b() call below had home/away reversed. find_h_b's regex captures
    # group(1) = the left-hand number (AWAY team's value) and group(2) = the right-hand number (HOME team's
    # value) -- same left=away/right=home convention used everywhere else in this project. Verified against
    # real text, e.g. "0.006 (120) OFF PPA (EPA/PLAY) 0.121 (82)" on the Western Kentucky @ New Mexico State
    # page: 0.006 is Western Kentucky's (away) OFF PPA, 0.121 is New Mexico State's (home) OFF PPA.
    away["Net Success Rate"], home["Net Success Rate"] = find_h_b("NET SUCCESS RATE", text)
    away["OSR (Offense Success Rate)"], home["OSR (Offense Success Rate)"] = find_h_b("OFF SUCCESS RATE", text)
    away["DSR (Defense Success Rate)"], home["DSR (Defense Success Rate)"] = find_h_b(r"OPP SUCCESS RATE \(DSR\)", text)
    # NEW: FEI for the "TEAM INFO" header block. Verified the plain "FEI" label doesn't
    # false-match inside "OFEI"/"DFEI" nearby in the real text -- find_h_b requires whitespace immediately
    # before the label, and "OFEI"/"DFEI" have a letter there instead, so they're real distinct lines/values.
    away["FEI"], home["FEI"] = find_h_b("FEI", text)
    # NEW: last-3-completed-games points-per-drive -- printed into the
    # matrices PDF right by FEI (see cfb_working_schedule.py's adv_specs), pulled out here
    # the exact same way as every other ADVANCED RATINGS line. Feeds the "Predicted Team
    # Total"/"Spread" rows below instead of the old cfb_ppd_cache.json read.
    away["Off PPD (Last 3)"], home["Off PPD (Last 3)"] = find_h_b(r"OFF PPD \(LAST 3\)", text)
    away["Def PPD (Last 3)"], home["Def PPD (Last 3)"] = find_h_b(r"DEF PPD \(LAST 3\)", text)
    away["Line Yards (Offense)"], home["Line Yards (Offense)"] = find_h_b("OFF LINE YARDS", text)
    away["Line Yards (Defense)"], home["Line Yards (Defense)"] = find_h_b("DEF LINE YARDS ALLOWED", text)
    away["Stuff Rate (Offense)"], home["Stuff Rate (Offense)"] = find_h_b("OFF STUFF RATE", text)
    away["Stuff Rate (Defense)"], home["Stuff Rate (Defense)"] = find_h_b("DEF STUFF RATE FORCED", text)
    away["2nd Level Yards (Offense)"], home["2nd Level Yards (Offense)"] = find_h_b("OFF 2ND LEVEL YARDS", text)
    away["2nd Level Yards (Defense)"], home["2nd Level Yards (Defense)"] = find_h_b("DEF 2ND LEVEL YARDS ALLOWED", text)
    away["Open Field Yards (Offense)"], home["Open Field Yards (Offense)"] = find_h_b("OFF OPEN FIELD YARDS", text)
    away["Open Field Yards (Defense)"], home["Open Field Yards (Defense)"] = find_h_b("DEF OPEN FIELD YARDS ALLOWED", text)
    away["Power Success (Offense)"], home["Power Success (Offense)"] = find_h_b("OFF POWER SUCCESS RATE", text)
    away["Power Success (Defense)"], home["Power Success (Defense)"] = find_h_b("DEF POWER SUCCESS RATE ALLOWED", text)
    away["Passing Explosiveness (Offense)"], home["Passing Explosiveness (Offense)"] = find_h_b("OFF EXPLOSIVENESS", text)
    away["Passing Explosiveness (Defense)"], home["Passing Explosiveness (Defense)"] = find_h_b("DEF EXPLOSIVENESS ALLOWED", text)
    away["Havoc Rate (Offense/Suffered)"], home["Havoc Rate (Offense/Suffered)"] = find_h_b(r"OFF_HAVOC RATE \(SUFFERED\)|OFF HAVOC RATE \(SUFFERED\)", text)
    away["Havoc Rate (Defense/Forced)"], home["Havoc Rate (Defense/Forced)"] = find_h_b(r"DEF_HAVOC RATE \(FORCED\)|DEF HAVOC RATE \(FORCED\)", text)
    away["Panic Index (Offense PPA)"], home["Panic Index (Offense PPA)"] = find_h_b(r"OFF PPA \(EPA/PLAY\)", text)
    away["Panic Index (Defense PPA)"], home["Panic Index (Defense PPA)"] = find_h_b(r"DEF PPA \(EPA/PLAY ALLOWED\)", text)

    if away["Panic Index (Offense PPA)"] == "N/A":
        # FIX: actually fixed now, per your call on the fallback-bug question. grab_home_stat
        # can only locate ONE number near the keyword, and since its regex path (re.search, first match in the
        # text) finds AWAY's "OFF PPA ..." line first -- away's is always listed before home's, same order as
        # the SOS Rk lines -- it can only reliably recover AWAY's value, never home's. The old code duplicated
        # that single recovered number into BOTH away and home, which would silently inject a wrong number for
        # home. Now it only ever fills in away's side, and leaves home["Panic Index (Offense PPA)"] exactly as
        # find_h_b() set it (still "N/A" if that also failed) rather than faking a value for it.
        away["Panic Index (Offense PPA)"] = grab_home_stat("OFF PPA (EPA/PLAY)", text)

    with pdfplumber.open(_MATRICES_PDF) as pdf:
        combined_lines = []
        p1_text = pdf.pages[current_idx].extract_text()
        if p1_text: combined_lines.extend(p1_text.split('\n'))
        if (current_idx + 1) < len(pdf.pages):
            p2_text = pdf.pages[current_idx + 1].extract_text()
            if p2_text and "OFFENSE VS" not in p2_text.upper(): combined_lines.extend(p2_text.split('\n'))

        for line in combined_lines:
            line_upper = line.upper().strip()
            m_f = re.findall(r'([-\d\.]+(?:%|)\s*\(\d+\))', line)
            if not m_f: continue
            label = None
            if "HAVOC" in line_upper and "SUFFERED" in line_upper: label = "Havoc Rate (Offense/Suffered)"
            elif "HAVOC" in line_upper and "FORCED" in line_upper: label = "Havoc Rate (Defense/Forced)"
            elif "OPEN FIELD" in line_upper and "ALLOWED" in line_upper: label = "Open Field Yards (Defense)"
            elif "OPEN FIELD" in line_upper: label = "Open Field Yards (Offense)"
            elif "EXPLOSIVENESS" in line_upper and "ALLOWED" in line_upper: label = "Passing Explosiveness (Defense)"
            elif "EXPLOSIVENESS" in line_upper: label = "Passing Explosiveness (Offense)"
            elif "POWER" in line_upper and "ALLOWED" in line_upper: label = "Power Success (Defense)"
            elif "POWER" in line_upper and "SUCCESS" in line_upper: label = "Power Success (Offense)"
            if label:
                # FIX: same left=away/right=home convention as everywhere else -- was backwards.
                if len(m_f) >= 2: away[label], home[label] = clean_stat(m_f[0]), clean_stat(m_f[1])
                elif len(m_f) == 1: away[label], home[label] = clean_stat(m_f[0]), "N/A"

    _pending_tables.append((home_team, away_team, home, away))

# 2026-10-07: two passes. Pass 1 builds every table just to collect the deltas, so "large" (top 25%) and "massive" (top 10%)
# can be measured against every game on the slate (plus the games already saved in cfb_delta_history.json). Pass 2 builds the real tables.
_DELTA_LOG.clear(); _GRID_FLAGS.clear()
for _h, _a, _hs, _as in _pending_tables:
    build_single_matchup_table(_h, _a, _hs, _as)
_compute_delta_thresholds(dict(_DELTA_LOG))
_DELTA_LOG.clear(); _GRID_FLAGS.clear()
for _h, _a, _hs, _as in _pending_tables:
    t_obj = build_single_matchup_table(_h, _a, _hs, _as)
    # FIX: this title string also goes straight into a Paragraph in Section 6 -- escape here too.
    matchups_list.append((f"{_xml_esc(_a)} @ {_xml_esc(_h)}", t_obj))

# Hand the green/teal flags to The Nuts (spread.py colors a team's name teal when it has a teal-marked delta)
try:
    _flag_out = {}
    for (_fa, _fh), _fl in _GRID_FLAGS.items():
        if _fl:
            _flag_out[re.sub(r"\s+", " ", _fa).strip().upper() + "@" + re.sub(r"\s+", " ", _fh).strip().upper()] = _fl
    with open(os.path.join(_HERE, "generated", "grid_flags.json"), "w") as _ff:
        json.dump({"games": _flag_out}, _ff, indent=1)
    _n_teal = sum(1 for _fl in _flag_out.values() for _side in _fl.values() if _side.get("teal"))
    _n_grn = sum(1 for _fl in _flag_out.values() for _side in _fl.values() if _side.get("green"))
    _n_lt = sum(1 for _fl in _flag_out.values() for _side in _fl.values() if _side.get("light"))
    print(f" -> grid highlights: {_n_teal} team(s) with teal (90%+), {_n_grn} with green (80-90%), {_n_lt} with light green (70-80%) large deltas.")
except Exception as _e:
    print(f" -> grid flags not saved ({_e})")

# =====================================================================
# BOUNDARY LINE: END OF SECTION 5 - PASTE SECTION 6 DIRECTLY BELOW
# =====================================================================
# =====================================================================
# HEADER: SECTION 6 - TWO-COLUMN RE-SPACED MULTI-GRID ENGINE
# DESCRIPTION: Packages data 2-per-page (side by side), applies un-smashed layout
# column widths (300pt) and tight block gaps.
# UPDATE: back to 4-per-page (2x2 grid). The original reason this was dropped (see the
# dated note above) was real -- the table genuinely didn't fit two rows on one page -- but that was because
# of the dead-space FONT bug fixed just above in this section, not because 4-per-page is inherently too tall.
# With that bug fixed, a single matchup table is ~242pt instead of ~332pt, so two full rows (~520pt with the
# title rows and inter-row gap) fit comfortably inside the ~582pt usable page height. Verified: 12 pages for
# 45 matchups (ceil(45/4)), no silent mid-table page splitting.
# =====================================================================

# Forced 15pt tight structural canvas margin parameters
doc = SimpleDocTemplate(_GRID_OUT_PDF, pagesize=landscape(letter), leftMargin=15, rightMargin=15, topMargin=15, bottomMargin=15)
story = []

for i in range(0, len(matchups_list), 4):
    chunk = matchups_list[i:i+4]

    # Grid cell structural layout blocks (4 slots -- 2x2)
    grid_slots = []
    for idx in range(4):
        if idx < len(chunk):
            # Extract authentic parsed data tuples
            t_str, table_obj = chunk[idx]
            grid_slots.append((Paragraph(t_str, title_style), table_obj))
        else:
            # FIX: Injects an explicit, non-breaking spacing container to maintain matching size metrics
            grid_slots.append((Paragraph("&nbsp;", title_style), ""))

    m1_title, m1_table = grid_slots[0]
    m2_title, m2_table = grid_slots[1]
    m3_title, m3_table = grid_slots[2]
    m4_title, m4_table = grid_slots[3]

    master_table_data = [
        [m1_title, "", m2_title],
        [m1_table, "", m2_table],
        ["", "", ""],
        [m3_title, "", m4_title],
        [m3_table, "", m4_table],
    ]

    page_grid = Table(master_table_data, colWidths=[300, 40, 300], rowHeights=[11, None, 10, 11, None])
    page_grid.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'), 
        ('ALIGN', (0,0), (-1,-1), 'CENTER'), 
        ('BOTTOMPADDING', (0,0), (-1,-1), 0), 
        ('TOPPADDING', (0,0), (-1,-1), 0)
    ]))
    story.append(page_grid)
    if i + 4 < len(matchups_list): 
        story.append(PageBreak())

doc.build(story)
print(f"Successfully generated un-smashed master file: '{_GRID_OUT_PDF}'!")

# 2026-10-07: save each game's pre-game deltas (first sighting only) so cfb_delta_study.py can measure how much a big delta matters
try:
    import cfb_delta_study as _ds
    _ds.record(_DELTA_LOG)
except Exception as _e:
    print(f" -> delta study skipped ({_e})")

# =====================================================================
# BOUNDARY LINE: END OF ARCHITECTURE SYSTEM - EXECUTION SYSTEM COMPLETE
# =====================================================================
