import os
import re
from pypdf import PdfReader

def find_pdf_in_folder():
    """MERGED (2026-10-05): prefers this run's generated/cfb_matrices_outlook.pdf (made by
    cfb_run_all.py) so no manual copying is needed; falls back to the old behavior (first PDF
    found in the current folder) only if that file doesn't exist."""
    _here = os.path.dirname(os.path.abspath(__file__))
    _gen = os.path.join(_here, "generated", "cfb_matrices_outlook.pdf")
    if os.path.exists(_gen):
        return _gen
    for file in os.listdir('.'):
        if file.lower().endswith('.pdf'):
            return file
    return None

def _safe_float(s, default=0.0):
    """float(s), but a missing/placeholder stat ("--", a bare "-", or
    anything else that isn't a real number) becomes `default` instead of
    crashing the whole run."""
    try:
        return float(s)
    except (TypeError, ValueError):
        return default

# Turnover margin is real, but it's also one of the least persistent team
# stats in football -- Harvard's Sports Analysis Collective found ~45.3%
# skill / ~54.7% luck in a team's season turnover differential (year-to-year
# correlation ~0.086). UPDATED (2026-09-28, later same day): the first OLS
# refit here only matched 45 of the 47 real Vegas lines to their games --
# a team-name alias bug (LSU printed as "Louisiana State", Miami (OH) printed
# as bare "Miami") silently dropped 2 games from the fit, including the
# single worst-missed game in the whole sample (UConn @ Miami (OH)). Once
# that bug was fixed and all 47 games refit together, turnover margin's real
# fitted weight came out essentially at zero (and unstable in sign, -0.001 to
# -0.04, across every capping threshold tried) -- i.e. once FPI/FEI are
# weighted correctly, turnover margin isn't adding real signal on top of
# them, it's mostly noise. So it's floored near zero below rather than
# trusted at a meaningfully positive weight; this fixed most (not all) of
# the worst turnover-driven misses (e.g. UCLA @ Maryland: happy-medium error
# 10.31 -> 4.01; Liberty @ Coastal Carolina: 6.59 -> 2.87). A couple of
# outliers (Missouri State @ SMU, UConn @ Miami (OH)) stayed big misses even
# after this -- likely genuine blowout/anomaly games no linear combination of
# these 5 season-average stats was ever going to catch.

def clean_text_block(text):
    """Cleans up formatting noise and strips ranking parenthesis completely
    (the '(87)'-style rank the report prints after every stat)."""
    return re.sub(r'\(\d+\)', '', text)

def parse_single_matchup(page_text):
    """Extracts stats and executes the spread delta model for a single page text block.

    FIXED (2026-09-28): the real PDF (built by cfb_working_schedule.py's
    build_stat_panel) never puts a leading number or the abbreviations
    "OFF"/"DEF" next to the team names -- the real header line is just
    "TEAM NAME OFFENSE vs OTHER TEAM DEFENSE" on its own, and every stat
    row below it renders as three SEPARATE table cells -- away value, then
    the label, then home value -- each on its own line/paragraph, e.g.:
        32.7
        POINTS / GAME
        29.0
    not "32.7 TEAM OFF vs TEAM DEF 29.0" on one line the way the old
    regexes assumed. That mismatch (plus "OFF"/"DEF" vs the real
    "OFFENSE"/"DEFENSE") is why nothing was extracting. Rebuilt every
    pattern below against the real extracted text (verified against your
    actual cfb_matrices_outlook.pdf, all 47 real matchup pages)."""
    text = clean_text_block(page_text)

    # --- 1. DYNAMICALLY EXTRACT TEAM NAMES ---
    # Real layout: "LIBERTY OFFENSE vs COASTAL CAROLINA DEFENSE" -- no
    # leading number, "OFFENSE"/"DEFENSE" spelled out in full, team names
    # in caps (allows multi-word names, &, ', ., (), - e.g. "TEXAS A&M").
    team_match = re.search(
        r"([A-Z][A-Z0-9&'.() -]*?)\s+OFFENSE\s+vs\s+([A-Z][A-Z0-9&'.() -]*?)\s+DEFENSE",
        text
    )
    if not team_match:
        return None

    away_team = team_match.group(1).strip()
    home_team = team_match.group(2).strip()

    # --- 2. GLOBAL REGEX STAT MATCHING ---
    # FPI Extraction -- header prose format ("FPI -2.1 SOS Rk -- LIBERTY..."),
    # appears once per team, away first (listed before "at"), home second.
    fpi_matches = re.findall(r'FPI\s*([\d\.\-]+)', text)
    if len(fpi_matches) < 2:
        return None
    away_fpi = _safe_float(fpi_matches[0])
    home_fpi = _safe_float(fpi_matches[1])

    # FEI Extraction -- FIXED: real layout is a table row (ADVANCED
    # RATINGS panel) shaped like every other stat row -- "away_value FEI
    # home_value" on three lines, not "FEI value" twice like the FPI
    # header prose. \b...\b keeps this from matching inside "OFEI"/"DFEI"
    # (both real, separate rows on the same panel).
    fei_row = re.search(r'([\d\.\-]+)\s*\bFEI\b\s*([\d\.\-]+)', text)
    away_fei = _safe_float(fei_row.group(1)) if fei_row else 0.0
    home_fei = _safe_float(fei_row.group(2)) if fei_row else 0.0

    # Turnover Margin Extraction -- same header-prose format as FPI, works
    # unchanged against the real text.
    to_matches = re.findall(r'TO,\s*([\d\.\-\+]+)', text)
    away_to = _safe_float(to_matches[0].replace('+', '')) if len(to_matches) > 0 else 0.0
    home_to = _safe_float(to_matches[1].replace('+', '')) if len(to_matches) > 1 else 0.0

    # Points Per Game Parsing -- FIXED: real rows are "value POINTS / GAME
    # value" (no team name/OFF/DEF text mixed in). This appears once per
    # stat panel, and there are two panels per page (away-off-vs-home-def,
    # then home-off-vs-away-def) -- findall picks up both, in that order.
    points_pattern = r'([\d\.\-]+)\s*POINTS\s*/\s*GAME\s*([\d\.\-]+)'
    points_matches = re.findall(points_pattern, text)

    if len(points_matches) >= 2:
        away_off_ppg = _safe_float(points_matches[0][0])   # away's own offense PPG
        home_def_ppg = _safe_float(points_matches[0][1])   # home's defense PPG allowed (shown alongside away's offense)
        home_off_ppg = _safe_float(points_matches[1][0])   # home's own offense PPG
        away_def_ppg = _safe_float(points_matches[1][1])   # away's defense PPG allowed (shown alongside home's offense)
    else:
        away_off_ppg, away_def_ppg, home_off_ppg, home_def_ppg = 0.0, 0.0, 0.0, 0.0

    # Yards Per Play Parsing -- FIXED the same way. Negative lookbehind
    # keeps this off "PASS YARDS / PLAY" and "RUSH YARDS / PLAY", which
    # are real, separate rows on the same panel and would otherwise also
    # match the bare "YARDS / PLAY" pattern.
    ypp_pattern = r'([\d\.\-]+)\s*(?<!PASS )(?<!RUSH )\bYARDS\s*/\s*PLAY\b\s*([\d\.\-]+)'
    ypp_matches = re.findall(ypp_pattern, text)

    if len(ypp_matches) >= 2:
        away_off_ypp = _safe_float(ypp_matches[0][0])
        home_def_ypp = _safe_float(ypp_matches[0][1])
        home_off_ypp = _safe_float(ypp_matches[1][0])
        away_def_ypp = _safe_float(ypp_matches[1][1])
    else:
        away_off_ypp, away_def_ypp, home_off_ypp, home_def_ypp = 0.0, 0.0, 0.0, 0.0

    # Home Field Advantage Check -- unchanged; this note doesn't appear on
    # every page/report, so the 2.60 default is the normal, expected path.
    hfa_match = re.search(r'home\-field bump\s*\(\+([\d\.]+)', text, re.IGNORECASE)
    hfa = float(hfa_match.group(1)) if hfa_match else 2.60

    # --- 3. MODEL FORMULA ENGINE ---
    fpi_delta = home_fpi - away_fpi
    fei_delta = home_fei - away_fei
    # FIXED (2026-09-28, 3rd pass): these were one-sided -- only "home's
    # offense vs away's defense," completely ignoring the mirror-image
    # matchup the page also prints ("away's offense vs home's defense" --
    # away_off_ppg/home_def_ppg and away_off_ypp/home_def_ypp were parsed
    # above but never used). A real delta for "which team is better in this
    # category" needs both halves of the matchup: how home's attack does
    # against this specific away defense, MINUS how away's attack does
    # against this specific home defense. That nets out to an expected
    # scoring/yardage MARGIN, not just a one-sided lean.
    scoring_delta = (home_off_ppg - away_def_ppg) - (away_off_ppg - home_def_ppg)
    ypp_delta = (home_off_ypp - away_def_ypp) - (away_off_ypp - home_def_ypp)
    turnover_delta = home_to - away_to

    # Weights refit 2026-09-28 (second pass, all 47 games, alias bug fixed):
    # OLS-regressed all five weights together against every real, verified
    # Vegas closing line (MAE 4.99 -> 3.41 for the raw fit), then blended
    # ~40% of the way from the prior hand-tuned weights toward that fit
    # (MAE 3.74) -- except turnover, which is floored near zero per the note
    # above rather than mechanically blended, since its fitted value is
    # noise-level regardless of blend fraction. 47 games / 5 parameters is
    # still a small sample, so FPI/FEI's exact magnitudes could still move
    # with more data -- but the DIRECTION (FEI >> FPI >> everything else) is
    # independently confirmed by the CFB project's own per-stat win-rate
    # ranking (FEI ~82.6% vs FPI ~77.3%). Original hand-picked weights, for
    # reference: FPI 35%, FEI 25%, PPG 20%, YPP 10%, TO 10%.
    fpi_points = (fpi_delta * 0.85) * 0.37
    fei_points = (fei_delta * 7.50) * 1.47
    scoring_points = (scoring_delta * 0.50) * 0.11
    ypp_points = (ypp_delta * 6.50) * 0.01
    turnover_points = (turnover_delta * 4.00) * 0.01

    net_metric_margin = fpi_points + fei_points + scoring_points + ypp_points + turnover_points + hfa
    vegas_spread = -net_metric_margin

    # --- WIN-% INPUTS (2026-10-07): the five yellow-highlight stats, handed to cfb_nuts_winprob.py ---
    _nsr = re.search(r'([-\d.]+)\s*NET SUCCESS RATE\s*([-\d.]+)', text)
    _eff = re.findall(r"Off Eff\s+([-\d.]+)\s*\(\d+\)\s+Def Eff\s+([-\d.]+)\s*\(\d+\)", page_text)
    def _f(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None
    wp_inputs = {
        "fei": (_f(fei_row.group(1)), _f(fei_row.group(2))) if fei_row else (None, None),
        "ppg": (away_off_ppg or None, home_off_ppg or None),
        "nsr": (_f(_nsr.group(1)), _f(_nsr.group(2))) if _nsr else (None, None),
        "oeff": (_f(_eff[0][0]), _f(_eff[1][0])) if len(_eff) >= 2 else (None, None),
        "deff": (_f(_eff[0][1]), _f(_eff[1][1])) if len(_eff) >= 2 else (None, None),
    }

    return {
        "away": away_team,
        "home": home_team,
        "wp_inputs": wp_inputs,
        "spread": vegas_spread
    }

def build_pdf_report(results, filename="The Nuts.pdf"):
    """Plain, no-frills PDF -- one row per game, same info the console
    table shows. Nothing fancy per your ask: no color grading, no logos,
    just a readable table."""
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(filename, pagesize=landscape(letter),
                             leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36,
                             title="The Nuts")

    elements = [Paragraph("THE NUTS", styles['Title']), Spacer(1, 4),
                Paragraph("Projected spreads -- FPI/FEI/PPG/YPP/TO delta model, "
                          "weights fit against real Vegas lines (2026-09-28, 47-game refit).",
                          styles['Normal']),
                Spacer(1, 12)]

    from reportlab.lib.styles import ParagraphStyle
    _ps = ParagraphStyle('nutscell', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, leading=9)
    _P = lambda txt: Paragraph(txt, _ps)
    _fmt = lambda v: f"{v:.2f}" if v < 0 else f"+{v:.2f}"
    _fmt1 = lambda v: f"{v:.1f}" if v < 0 else f"+{v:.1f}"

    # Teal marker (2026-10-07): grid step (new.py) saves generated/grid_flags.json; a team with a 90%+ (teal) large delta gets a teal name here
    _flags = {}
    try:
        import json as _json
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated", "grid_flags.json")) as _ff:
            _flags = _json.load(_ff).get("games", {})
    except Exception:
        _flags = {}
    _norm = lambda x: re.sub(r"\s+", " ", x).strip().upper()

    def _teal(r, side):
        g = _flags.get(f"{_norm(r['away'])}@{_norm(r['home'])}") or {}
        return bool((g.get(side) or {}).get("teal"))

    def _nm(r, side):
        """Team name; the predicted winner also gets its win % beside the name; a teal-marked team's name is teal (2026-10-07)."""
        nm = r[side]
        if _teal(r, side):
            nm = f"<font color='#00897B'><b>{nm}</b></font>"
        if r.get("wp_pick") == side:
            return f"<b>{nm} {r['wp_pick_prob']:.0%}</b>"
        return nm

    def _stats_txt(r):
        if "wp_pick" not in r:
            return "N/A"
        return f"{r['wp_n_for']} of {r['wp_n_votes']}: " + ", ".join(r["wp_backers"]) if r["wp_backers"] else f"0 of {r['wp_n_votes']}"

    # ATS COLOR GRID (2026-10-07; spread-size version same day): colors the VEGAS cell by how each team has done vs. the spread
    # in games with a SIMILAR NUMBER (same role + size: 10+ fav, 3-9 fav, close, 3-9 dog, 10+ dog). Falls back to fav/dog of any size
    # when the exact size has fewer than 2 games. Line 2 of the cell also shows the home-team-at-home / away-team-on-road record.
    _ATS_COL = {("fav", 1): "#C8E6C9", ("fav", 2): "#66BB6A", ("dog", 1): "#E1BEE7", ("dog", 2): "#BA68C8", ("pk", 1): "#BBDEFB", ("pk", 2): "#64B5F6", ("thin", 0): "#E0E0E0"}

    def _ats_info(r):
        """-> (extra lines for the Vegas cell as markup, background hex or None)."""
        vg = r.get("vegas")
        if vg is None:
            return "", None
        _rec = lambda x: "--" if not x or not x.get("n") else (f"{x['w']}-{x['l']}" + (f"-{x['p']}" if x.get("p") else ""))
        hh = (r.get("ats_home") or {}).get("home")
        aa = (r.get("ats_away") or {}).get("away")
        venue = f"H {_rec(hh)} | A {_rec(aa)}"
        sh, sa = r.get("sit_home"), r.get("sit_away")

        def _pick(sit):
            """-> (record, label text, decided games). Exact size bucket if it has 2+ decided games, else fav/dog of any size."""
            if not sit:
                return None, "--", 0
            for rec_, star in ((sit.get("bucket"), ""), (sit.get("role_rec"), "*")):
                if rec_ and rec_["w"] + rec_["l"] >= 2:
                    return rec_, f"{sit['label']}{star} {_rec(rec_)}", rec_["w"] + rec_["l"]
            rec_ = sit.get("bucket") or sit.get("role_rec")
            return rec_, f"{sit['label']} {_rec(rec_)}", ((rec_["w"] + rec_["l"]) if rec_ else 0)

        rh, th, dh = _pick(sh)
        ra, ta, da = _pick(sa)
        line2 = f"<br/><font size=6 color='#555555'>{venue}</font>"
        sit_txt = f"{th} | {ta}"
        if dh < 2 or da < 2:
            return line2 + f"<br/><font size=6 color='#555555'>{sit_txt} | thin</font>", _ATS_COL[("thin", 0)]
        edge = rh["w"] / dh - ra["w"] / da             # >0: the situation records favor the HOME side
        if abs(edge) < 0.25:
            return line2 + f"<br/><font size=6 color='#555555'>{sit_txt} | even</font>", None
        lean_home = edge > 0
        kind = "pk" if vg == 0 else ("fav" if lean_home == (vg < 0) else "dog")
        word = {"fav": "FAV", "dog": "DOG", "pk": "HOME" if lean_home else "AWAY"}[kind]
        return line2 + f"<br/><font size=6 color='#333333'>{sit_txt} | lean {word}</font>", _ATS_COL[(kind, 2 if abs(edge) >= 0.6 else 1)]

    table_data = [["AWAY", "HOME", "NUTS LINE", "VEGAS", "O/U", "NUTS vs VEGAS", "STATS FOR PICK"]]
    for r in results:
        spread_str = _fmt(r['spread'])
        vg = r.get("vegas")
        if vg is None:
            vegas_str, lean_str = "N/A", ""
        else:
            vegas_str = f"{r['home']} ({_fmt1(vg)})"
            d = vg - r['spread']          # >0: the Nuts like the HOME team more than the market does
            lean_str = "same" if abs(d) < 0.05 else (f"{r['home']} +{d:.1f}" if d > 0 else f"{r['away']} +{abs(d):.1f}")
        ou = r.get("vegas_total")
        table_data.append([_P(_nm(r, 'away')), _P(_nm(r, 'home')), _P(f"{r['home']} ({spread_str})"),
                           _P(vegas_str + _ats_info(r)[0]), "N/A" if ou is None else f"{ou:g}", _P(lean_str), _P(_stats_txt(r))])

    t = Table(table_data, colWidths=[100, 100, 120, 120, 36, 100, 120], repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#222222')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 7.5),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F2F2F2')]),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    # Predicted winner = yellow; if the stats pick a different winner than Vegas, the WHOLE row is tinted (winner cell stays yellow)
    _wp_cmds = []
    for _i, _r in enumerate(results, start=1):
        if _r.get("wp_vs_vegas") == "DISAGREE":
            _wp_cmds.append(('BACKGROUND', (0, _i), (-1, _i), colors.HexColor('#FFB74D')))
        if _r.get("wp_pick") in ("away", "home"):
            _wp_cmds.append(('BACKGROUND', (0 if _r["wp_pick"] == "away" else 1, _i), (0 if _r["wp_pick"] == "away" else 1, _i),
                             colors.HexColor('#FFF176')))
    _vcol = table_data[0].index("VEGAS")
    for _i, _r in enumerate(results, start=1):
        _bg = _ats_info(_r)[1]
        if _bg:
            _wp_cmds.append(('BACKGROUND', (_vcol, _i), (_vcol, _i), colors.HexColor(_bg)))
    if _wp_cmds:
        t.setStyle(TableStyle(_wp_cmds))
    elements.append(t)
    elements.append(Spacer(1, 4))
    elements.append(Paragraph("YELLOW = the team the five highlighted stats (SOR, PPG, FEI, Off Eff, Net Success Rate) say wins, with its win %. "
                              "ORANGE ROW = that pick is NOT the team Vegas favors. TEAL NAME = that team has a 90%+ delta on the grid. STATS FOR PICK = how many of the five back it "
                              "(SOR counts as half a vote). 83% of games were called right in a backtest on 150 graded games it wasn't trained on; "
                              "treat 55-65% as a lean, not a lock.", styles['Normal']))
    elements.append(Spacer(1, 3))
    elements.append(Paragraph("VEGAS = home-team spread from CFBD's betting lines (negative = home favored), O/U = total. "
                              "NUTS vs VEGAS = which side the Nuts like more than the market, in points.", styles['Normal']))
    elements.append(Spacer(1, 3))
    elements.append(Paragraph("VEGAS CELL COLOR = how each team has done against a SIMILAR number: the home team as a favorite/underdog of this size and the away team as a "
                              "favorite/underdog of this size (sizes: 10+, 3-9, close; W-L-Push, home and road games together). Needs 2+ graded games for both; if the exact size is too thin it uses "
                              "fav/dog of any size (marked *). Second line = home team's record at home (H) and away team's record on the road (A). "
                              "<font backColor='#66BB6A'>&nbsp;GREEN&nbsp;</font> = those records favor the team Vegas has as the FAVORITE (darker = bigger gap). "
                              "<font backColor='#BA68C8'>&nbsp;PURPLE&nbsp;</font> = they favor the UNDERDOG. "
                              "<font backColor='#E0E0E0'>&nbsp;GRAY&nbsp;</font> = too few games to read. No color = even. "
                              "Reality check: so far in 2026, favorites of every size cover about 50% league-wide, and the side with the better same-size record covered 46-56% "
                              "(noise). Treat it as context, not a pick.", styles['Normal']))

    # AGAINST THE SPREAD (added 2026-10-06): each team's season record vs. the number, overall and at home / on the road
    if any(r.get("ats_away") or r.get("ats_home") for r in results):
        import cfb_ats_odds as _ats
        from reportlab.platypus import PageBreak as _PB
        elements.append(_PB())
        elements.append(Paragraph("AGAINST THE SPREAD", styles['Title']))
        elements.append(Spacer(1, 4))
        elements.append(Paragraph("Season record vs. the Vegas number for every graded game: W-L-Push (cover %, average points vs. the "
                                  "number per game). Games with no posted line (mostly FCS buy games) are not counted.", styles['Normal']))
        elements.append(Spacer(1, 8))
        ats_rows = [["AWAY", "AWAY: ALL GAMES", "AWAY: ON THE ROAD", "HOME", "HOME: ALL GAMES", "HOME: AT HOME"]]
        for r in results:
            aa, hh = r.get("ats_away") or {}, r.get("ats_home") or {}
            ats_rows.append([_P(r['away']), _P(_ats.fmt_record(aa.get("all"))), _P(_ats.fmt_record(aa.get("away"))),
                             _P(r['home']), _P(_ats.fmt_record(hh.get("all"))), _P(_ats.fmt_record(hh.get("home")))])
        t2 = Table(ats_rows, colWidths=[100, 118, 118, 100, 118, 118], repeatRows=1)
        t2.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#222222')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F2F2F2')]),
            ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(t2)
    doc.build(elements)

def process_all_games():
    pdf_filename = find_pdf_in_folder()
    if not pdf_filename:
        print("Error: Put a matchup report PDF in this folder before running.")
        return

    print(f"Reading Matchup Report: {pdf_filename}")
    print("Processing all matches across report layers...\n")

    reader = PdfReader(pdf_filename)
    results = []

    print(f"{'AWAY TEAM':<24} @ {'HOME TEAM':<24} | {'PROJECTED LINE':<15}")
    print("-" * 72)

    for page in reader.pages:
        page_text = page.extract_text()
        if not page_text:
            continue

        result = parse_single_matchup(page_text)
        if result:
            results.append(result)
            spread_str = f"{result['spread']:.2f}" if result['spread'] < 0 else f"+{result['spread']:.2f}"
            print(f"{result['away']:<24} @ {result['home']:<24} | {result['home']} ({spread_str})")

    print("-" * 72)
    # Vegas line + against-the-spread records (cfb_ats_odds.py); never stops the run if CFBD is unreachable
    try:
        import cfb_ats_odds as _ats
        _ats.attach_odds(results)
        print("\nVEGAS vs NUTS, and each team's ATS (season W-L-P):")
        print(f"{'GAME':<46} | {'VEGAS':<22} | {'O/U':<5} | AWAY ATS (road) / HOME ATS (home)")
        for _r in results:
            _vg = _r.get("vegas")
            _vs = "N/A" if _vg is None else f"{_r['home']} ({_vg:+.1f})"
            _ou = "N/A" if _r.get("vegas_total") is None else f"{_r['vegas_total']:g}"
            _aa, _hh = _r.get("ats_away") or {}, _r.get("ats_home") or {}
            def _short(_x):
                return "--" if not _x or not _x.get("n") else f"{_x['w']}-{_x['l']}-{_x['p']}"
            print(f"{(_r['away'] + ' @ ' + _r['home'])[:46]:<46} | {_vs[:22]:<22} | {_ou:<5} | "
                  f"{_short(_aa.get('away'))} / {_short(_hh.get('home'))}")
    except Exception as _e:
        print(f" -> Vegas / ATS skipped ({_e})")

    # Predicted winner + win % (cfb_nuts_winprob.py), compared with Vegas; never stops the run
    try:
        import cfb_nuts_winprob as _wp
        _wp.attach_winprob(results)
        print("\nPREDICTED WINNER + WIN % (5 highlighted stats), and where it DISAGREES with Vegas:")
        print(f"{'GAME':<46} | {'PICK':<26} | {'STATS':<5} | VS VEGAS")
        for _r in results:
            if "wp_pick" not in _r:
                continue
            _tag = "<<< DISAGREES" if _r["wp_vs_vegas"] == "DISAGREE" else _r["wp_vs_vegas"]
            print(f"{(_r['away'] + ' @ ' + _r['home'])[:46]:<46} | {(_r['wp_pick_team'] + ' ' + format(_r['wp_pick_prob'], '.0%'))[:26]:<26} | "
                  f"{str(_r['wp_n_for']) + '/' + str(_r['wp_n_votes']):<5} | {_tag}")
        _dis = [_r for _r in results if _r.get("wp_vs_vegas") == "DISAGREE"]
        print(f"{len(_dis)} of {len(results)} games: the stats pick a different winner than Vegas.")
    except Exception as _e:
        print(f" -> win % skipped ({_e})")
    print(f"Calculation complete. Successfully calculated spreads for {len(results)} games.")

    if results:
        _out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated", "The Nuts.pdf")
        os.makedirs(os.path.dirname(_out), exist_ok=True)
        build_pdf_report(results, filename=_out)
        print(f"Wrote {_out}")

if __name__ == "__main__":
    process_all_games()
