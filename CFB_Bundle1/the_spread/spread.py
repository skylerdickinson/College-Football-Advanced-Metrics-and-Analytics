import os
import re
from pypdf import PdfReader

def find_pdf_in_folder():
    """Finds any PDF file inside the active script folder."""
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

    return {
        "away": away_team,
        "home": home_team,
        "spread": vegas_spread
    }

def build_pdf_report(results, filename="The Nuts.pdf"):
    """Plain, no-frills PDF -- one row per game, same info the console
    table shows. Nothing fancy per your ask: no color grading, no logos,
    just a readable table."""
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(filename, pagesize=letter,
                             leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36,
                             title="The Nuts")

    elements = [Paragraph("THE NUTS", styles['Title']), Spacer(1, 4),
                Paragraph("Projected spreads -- FPI/FEI/PPG/YPP/TO delta model, "
                          "weights fit against real Vegas lines (2026-09-28, 47-game refit).",
                          styles['Normal']),
                Spacer(1, 12)]

    table_data = [["AWAY", "HOME", "PROJECTED LINE"]]
    for r in results:
        spread_str = f"{r['spread']:.2f}" if r['spread'] < 0 else f"+{r['spread']:.2f}"
        table_data.append([r['away'], r['home'], f"{r['home']} ({spread_str})"])

    t = Table(table_data, colWidths=[170, 170, 180])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#222222')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F2F2F2')]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t)
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
    print(f"Calculation complete. Successfully calculated spreads for {len(results)} games.")

    if results:
        build_pdf_report(results, filename="The Nuts.pdf")
        print("Wrote The Nuts.pdf")

if __name__ == "__main__":
    process_all_games()
