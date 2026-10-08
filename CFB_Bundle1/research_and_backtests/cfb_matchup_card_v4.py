"""
CFB MATCHUP CARD -- layout preview / mockup only.

Built to a redesign spec, tested with placeholder numbers
for Tulsa @ Arkansas so the LAYOUT can be judged before wiring in real
live data. This is NOT a live report -- every stat value below is a
clearly-labeled placeholder, not a real scrape. Once the layout itself is
approved, the next step is wiring these same cells to cfb_working_schedule's
real stats_lookup / cws.fetch_* functions (that needs live network access, so the wiring happens on a local machine).

Layout spec implemented here:
  - Team names moved into the header. FPI sits on the OUTSIDE of each
    name (away from the center "at"), SOR sits on the INSIDE (toward the
    center). Record sits under each team's name. The score prediction /
    win probability sits centered between the two records.
  - FEI / F+ / OFEI / DFEI / NSR / OSR / DSR / PPA / stuff rate: unchanged,
    one stat per line (away value | label | home value), same as the real
    report's ADVANCED RATINGS block.
  - Every offense-vs-defense section (scoring / passing / rushing /
    trenches) is broken into ONE INDIVIDUAL GRID PER STAT (never bundled
    together), and each of those grids shows both pairings stacked:
        line 1: Team A OFFENSE  vs  Team B DEFENSE
        line 2: Team A DEFENSE  vs  Team B OFFENSE
  - TFL (tackles for loss) moves out of the scoring section and into the
    rushing section, with its own commentary blurb (the old template had
    "TTL" mislabeled here with commentary that was actually about
    play-calling identity, not TFL -- rewritten below to actually be
    about TFL).
  - Heat map (green/red cell backgrounds vs. a national baseline) is the
    same solid-color-cell style cfb_working_schedule.py already uses --
    not changed.
"""
import os
import sys
import hashlib
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfb_matchup_deltas as deltas_mod

# ---------------------------------------------------------------------------
# PLACEHOLDER DATA -- Tulsa @ Arkansas, for layout evaluation ONLY. Every
# number below is a made-up, round, illustrative value -- NOT a real scrape
# (no live pull from TeamRankings/ESPN/bcftoys/CFBD). Swap this dict
# for cws.stats_lookup.loc[team] once the layout itself is approved.
# ---------------------------------------------------------------------------
PLACEHOLDER = True

away, home = "Tulsa", "Arkansas"
away_record, home_record = "3-1", "2-2"
away_fpi, home_fpi = "-4.2", "9.8"
away_sor, home_sor = "#94", "#61"
score_pred = "Arkansas 31.4 - Tulsa 20.6 (79% Arkansas)"

away_ts = {
    "Off_PPG": 27.4, "Def_PPG": 30.1, "Off_Yds_PG": 401.2, "Def_Yds_PG": 430.5,
    "Off_YPP": 5.4, "Def_YPP": 6.1, "Off_RZ_%": 78.0, "Def_RZ_%": 85.0,
    "Off_3rd_%": 38.0, "Def_3rd_%": 44.0, "Off_Sacks_Allowed_PG": 2.1, "Def_Sacks_PG": 1.4,
    "Off_Pass_PG": 210.0, "Def_Pass_PG": 245.0, "Off_Pass_Att": 6.9, "Def_Pass_Att": 7.8,
    "QBR": 62.3, "Def_Eff": 58.1, "Off_Explosiveness": 1.35, "Def_Explosiveness": 1.52,
    "Off_Rush_PG": 191.0, "Def_Rush_PG": 185.0, "Off_Rush_Att": 4.4, "Def_Rush_Att": 4.9,
    "TFL_Def_PG": 4.8, "Stuffs_Off_PG": 5.2,
    "Off_Line_Yards": 2.7, "Def_Line_Yards": 2.9, "Off_Power_Success": 68.0, "Def_Power_Success": 71.0,
    "Off_Stuff_Rate": 18.0, "Def_Stuff_Rate": 16.0, "Off_Havoc": 15.0, "Def_Havoc": 13.0,
    "Off_Second_Level_Yards": 1.1, "Def_Second_Level_Yards": 1.3,
    "Off_Open_Field_Yards": 0.6, "Def_Open_Field_Yards": 0.8,
    "F+": -0.35, "OF+": -0.20, "DF+": -0.50, "FEI": -0.28, "OFEI": -0.15, "DFEI": -0.40,
    "NSR": -3.1, "OSR": 39.5, "DSR": 43.0, "Off_PPA": 0.08, "Def_PPA": 0.19,
    "Off_Comp_Pct": 61.2, "Off_QB_Rush_PG": 45.3,
    "Off_INT_PG": 0.8, "Def_INT_PG": 0.6, "Pass_Pct": 52.0,
    "Off_Eff": 48.2, "Off_Success_Rate": 0.41, "Def_Success_Rate": 0.36, "Off_Plays_PG": 64.0, "Def_Plays_Faced_PG": 68.0,
}
home_ts = {
    "Off_PPG": 33.9, "Def_PPG": 22.7, "Off_Yds_PG": 452.8, "Def_Yds_PG": 355.0,
    "Off_YPP": 6.2, "Def_YPP": 5.0, "Off_RZ_%": 88.0, "Def_RZ_%": 72.0,
    "Off_3rd_%": 46.0, "Def_3rd_%": 34.0, "Off_Sacks_Allowed_PG": 1.3, "Def_Sacks_PG": 2.9,
    "Off_Pass_PG": 265.0, "Def_Pass_PG": 200.0, "Off_Pass_Att": 8.4, "Def_Pass_Att": 6.6,
    "QBR": 78.9, "Def_Eff": 72.4, "Off_Explosiveness": 1.58, "Def_Explosiveness": 1.22,
    "Off_Rush_PG": 187.0, "Def_Rush_PG": 140.0, "Off_Rush_Att": 5.1, "Def_Rush_Att": 3.9,
    "TFL_Def_PG": 7.2, "Stuffs_Off_PG": 3.8,
    "Off_Line_Yards": 3.1, "Def_Line_Yards": 2.4, "Off_Power_Success": 74.0, "Def_Power_Success": 62.0,
    "Off_Stuff_Rate": 14.0, "Def_Stuff_Rate": 21.0, "Off_Havoc": 11.0, "Def_Havoc": 19.0,
    "Off_Second_Level_Yards": 1.4, "Def_Second_Level_Yards": 0.9,
    "Off_Open_Field_Yards": 0.9, "Def_Open_Field_Yards": 0.5,
    "F+": 0.61, "OF+": 0.48, "DF+": 0.55, "FEI": 0.44, "OFEI": 0.30, "DFEI": 0.38,
    "NSR": 5.4, "OSR": 47.2, "DSR": 39.8, "Off_PPA": 0.24, "Def_PPA": 0.05,
    "Off_Comp_Pct": 68.5, "Off_QB_Rush_PG": 12.1,
    "Off_INT_PG": 0.5, "Def_INT_PG": 1.1, "Pass_Pct": 58.0,
    "Off_Eff": 62.7, "Off_Success_Rate": 0.47, "Def_Success_Rate": 0.31, "Off_Plays_PG": 69.0, "Def_Plays_Faced_PG": 63.0,
}

# National baselines -- same real, computed-league-average concept
# cfb_working_schedule.py uses for its heat map (illustrative round
# numbers here, not the real computed average).
NATIONAL_BASELINE = {
    "Off_PPG": 28.0, "Def_PPG": 28.0, "Off_Yds_PG": 400.0, "Def_Yds_PG": 400.0,
    "Off_YPP": 5.5, "Def_YPP": 5.5, "Off_RZ_%": 80.0, "Def_RZ_%": 80.0,
    "Off_3rd_%": 40.0, "Def_3rd_%": 40.0,
    "Off_Pass_PG": 225.0, "Def_Pass_PG": 225.0, "Off_Pass_Att": 7.5, "Def_Pass_Att": 7.5,
    "QBR": 65.0, "Def_Eff": 60.7, "Off_Explosiveness": 1.4, "Def_Explosiveness": 1.4,
    "Off_Rush_PG": 175.0, "Def_Rush_PG": 175.0, "Off_Rush_Att": 4.1, "Def_Rush_Att": 4.1,
    "Pass_Pct": 45.6,
    "Off_Line_Yards": 2.8, "Def_Line_Yards": 2.8, "Off_Power_Success": 70.0, "Def_Power_Success": 70.0,
    "Off_Stuff_Rate": 17.0, "Def_Stuff_Rate": 17.0, "Off_Havoc": 14.0, "Def_Havoc": 14.0,
    "Off_Second_Level_Yards": 1.2, "Def_Second_Level_Yards": 1.2,
    "Off_Open_Field_Yards": 0.7, "Def_Open_Field_Yards": 0.7,
    "TFL_Def_PG": 2.1, "Stuffs_Off_PG": 2.1,
    "F+": 0.0, "OF+": 0.0, "DF+": 0.0, "FEI": 0.0, "OFEI": 0.0, "DFEI": 0.0,
    "NSR": 0.0, "OSR": 43.0, "DSR": 43.0, "Off_PPA": 0.15, "Def_PPA": 0.15,
    # the 3 finds -- real, already-tracked in cfb_working_schedule.py but
    # missing from this card. Real bands re-derived from the live
    # cfb_matrices_outlook.pdf, same method as everything else. Off_Eff and
    # Def_Eff are genuinely different real scales (not a bug -- Def Eff runs
    # noticeably higher in the real data), so each gets its own real mean.
    "Off_Eff": 51.7,
    "Off_Success_Rate": 0.45, "Def_Success_Rate": 0.39,  # CFBD-sourced -- a distinct real series from bcftoys OSR/DSR above
    "Off_Plays_PG": 66.6, "Def_Plays_Faced_PG": 66.6,   # approximated from real pass-plays+rush-plays per game
}


def _fmt(v):
    if v is None:
        return "--"
    if isinstance(v, float) and abs(v) < 10:
        return f"{v:.2f}" if abs(v) < 3 else f"{v:.1f}"
    return f"{v:.1f}" if isinstance(v, float) else str(v)


# ---------------------------------------------------------------------------
# HEAT MAP -- same solid-color-cell heat map cfb_working_schedule.py's
# grade_bg()/adv_cell() already use: green = better than the national
# baseline, red = worse, gray = no baseline to grade against. side='O'
# means higher is better; side='D' means lower is better (this project's
# existing convention for the paired offense/defense grids).
# ---------------------------------------------------------------------------
color_green = colors.HexColor('#48BB78')
color_red = colors.HexColor('#F56565')
color_purple = colors.HexColor('#805AD5')   # v4: true top-10% (by real per-stat band) -- the "elite" tier
color_orange = colors.HexColor('#ED8936')   # v4: true bottom-10% -- the "bottom" tier
neutral_bg = colors.HexColor('#CBD5E0')
near_avg_bg = colors.HexColor('#EDEDED')   # within-band-of-average -- left white
missing_bg = colors.HexColor('#3A3A3A')
label_bg = colors.HexColor('#2A2A2A')
text_white = colors.HexColor('#FFFFFF')
black_txt = colors.HexColor('#111111')
accent_blue = colors.HexColor('#000000')  # header is black (was navy #1A365D)
card_bg = colors.HexColor('#1E1E1E')
# Same real, tested highlight colors cfb_working_schedule.py's skinny report
# already uses for "this is the model's pick" / "risky pick" in the header
# team name -- reused here verbatim (not reinvented) so the deep-dive card's
# team-name highlighting means exactly the same thing as the skinny report's.
TURQUOISE_HIGHLIGHT = colors.HexColor('#2DD4BF')
ORANGE_CAUTION_HIGHLIGHT = colors.HexColor('#F5A623')

# ---------------------------------------------------------------------------
# MATCHUP DELTAS: "i think i want all the deltas off these
# sheets so it is mostly team vs team, can you put the delta to the right
# of each grid on the ones that end up a single number on the side it
# favors, on the ones that have 2 numbers put it on the team side beside
# that grid and use the labels on the sheet". Colors kept deliberately
# distinct from the green/red/purple/orange heat map above -- these are a
# different kind of signal (a real computed differential, not a
# rank-against-the-field grade), so they get their own gold/slate look.
# ---------------------------------------------------------------------------
delta_panel_bg = colors.HexColor('#1F2937')     # slate -- delta number panel
delta_num_color = colors.HexColor('#FBBF24')    # gold -- the delta number itself
delta_desc_bg = colors.HexColor('#F5F5F0')      # light -- analytical-scale text panel
delta_desc_color = colors.HexColor('#333333')
DELTA_PANEL_WIDTH = 240   # legacy width, kept for delta_summary_block's standalone (non-grid) blocks
# REDESIGNED: grid now rides in the MIDDLE, with the delta
# number and description/scale each getting their own outer column on
# either side of it (whichever side the delta favors), instead of both
# living together in one panel to the grid's right. Grid shrinks a little
# (270 -> 250, trimming only its two value columns, not the label column,
# so team-name labels don't get squeezed) to make room on both sides.
# 130 (side) + 250 (grid) + 130 (side) = 510, same total content width.
GRID_WIDTH = 250
DELTA_SIDE_WIDTH = (510 - GRID_WIDTH) / 2.0   # 130


def _fmt_delta(v):
    if v is None:
        return "--"
    if abs(v) < 1:
        return f"{v:+.2f}"
    if abs(v) < 10:
        return f"{v:+.2f}"
    return f"{v:+.1f}"


def _delta_num_para(v, size=10):
    styles = getSampleStyleSheet()
    st = ParagraphStyle('dnum', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=size,
                         leading=size + 2, textColor=delta_num_color, alignment=1)
    return Paragraph(_fmt_delta(v), st)


def _delta_text_para(text, size=5.3):
    styles = getSampleStyleSheet()
    st = ParagraphStyle('dtext', parent=styles['Normal'], fontName='Helvetica', fontSize=size,
                         leading=size + 1.3, textColor=delta_desc_color, alignment=1)
    return Paragraph(text, st)


def _delta_num_cell(value, width):
    t = Table([[_delta_num_para(value)]], colWidths=[width])
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), delta_panel_bg),
                            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                            ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    return t


def _delta_desc_cell(text, width):
    t = Table([[_delta_text_para(text)]], colWidths=[width])
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), delta_desc_bg),
                            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                            ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    return t


def _single_delta_panel(label, value, favored, width=DELTA_SIDE_WIDTH):
    """SINGLE-number delta (the manual's Universal Formula, or a simple
    per-team composite like NSR/FEI). REDESIGNED: "keep
    stats in the middle... put the deltas on the side they favor, and
    then the description on the other teams side since there is room" --
    so this now returns (left_cell, right_cell) as two SEPARATE outer
    columns (the grid itself rides in the middle between them), rather
    than one merged panel beside the grid. The real final number renders
    on whichever side it favors; the OTHER side carries that delta's real
    analytical scale + what-it-means text."""
    meta_text = deltas_mod.METRIC_META.get(label, "")
    if value is None:
        empty_desc = _delta_desc_cell(f"{label}: -- (real data unavailable this week)", width)
        blank = Table([[""]], colWidths=[width])
        blank.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), delta_desc_bg)]))
        return empty_desc, blank
    # Tie (favored is None but a real value exists) -- number defaults to
    # the away side, description to the home side; the near-zero number
    # itself already communicates "this one's basically even."
    fav = favored or 'away'
    num_cell = _delta_num_cell(value, width)
    txt_cell = _delta_desc_cell(meta_text, width)
    if fav == 'away':
        return num_cell, txt_cell   # number on away/left side, description on home/right side
    else:
        return txt_cell, num_cell   # description on away/left side, number on home/right side


def _net_cell(value, net, width):
    """Same gold number as _delta_num_cell, plus a small head-to-head line under it. (Both
    edges can be negative -- each is measured vs league average -- so the bigger number looked 'better'.
    The net line is this team's edge minus the other team's, so + always means this side wins the matchup.)"""
    styles = getSampleStyleSheet()
    st = ParagraphStyle('dnet', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=6.2,
                         leading=7.6, textColor=colors.HexColor('#E5E7EB'), alignment=1)
    t = Table([[_delta_num_para(value)], [Paragraph("head-to-head " + _fmt_delta(net), st)]], colWidths=[width])
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), delta_panel_bg),
                            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                            ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
    return t


def _paired_delta_panel(away_val, home_val, width=DELTA_SIDE_WIDTH, show_net=False):
    """TWO-number delta (each team's own real one-sided edge). REDESIGNED
   : returns (left_cell, right_cell) as two separate
    outer columns -- away's real number on the away (left) side, home's
    on the home (right) side -- "put each teams deltas on their side" --
    mirroring the grid's own away-left/home-right convention, with the
    grid itself riding in the middle between them. No description
    embedded here; the caller attaches the real analytical scale +
    description as one blurb below the whole grid instead (the description goes under that specific grid)."""
    if show_net and away_val is not None and home_val is not None:
        # show only the winning side's number (the higher edge) + its head-to-head line;
        # the losing side is left blank so there is no second number to misread.
        net = away_val - home_val
        blank = Table([[Paragraph("", getSampleStyleSheet()['Normal'])]], colWidths=[width])
        if net >= 0:
            return _net_cell(away_val, net, width), blank
        return blank, _net_cell(home_val, -net, width)
    return _delta_num_cell(away_val, width), _delta_num_cell(home_val, width)


def delta_scale_blurb(label):
    """The below-grid description+scale box for a paired (2-number) delta
    -- same boxed-outline look as the report's existing narrative blurb()
    boxes, just holding real reference text instead of hype commentary."""
    meta_text = deltas_mod.METRIC_META.get(label, "")
    styles = getSampleStyleSheet()
    st = ParagraphStyle('deltablurb', parent=styles['Normal'], fontSize=6.6, leading=8.4,
                         textColor=colors.HexColor('#6B4E00'))
    box = Table([[Paragraph(f"<b>{label.upper()}:</b> {meta_text}", st)]], colWidths=[510])
    box.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.75, delta_num_color),
                             ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                             ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6)]))
    return box

# ---------------------------------------------------------------------------
# EXPERIMENT (v4): two-tier heat map -- top 10% purple, bottom 10%
# orange, layered on top of a looser 25% band
# so cells don't stay mostly white the way the strict v3/10%-only version
# did on this placeholder matchup.
#
# Both the 10% AND 25% numbers below are freshly re-derived from the real,
# live cfb_matrices_outlook.pdf (65 games this week -- re-parsed directly
# from the PDF text, restricted to the actual per-game matchup tables, not
# the leaderboard section up top which reuses the same stat names for a
# different number and would have corrupted the sample). For each stat:
#   band10 = how far the real top/bottom 10% of appearances sits from the
#            real average of every offense/defense number seen this week
#   band25 = the same, for the real top/bottom 25%
# Just like before, stats with a real league average near zero (F+, FEI,
# OF+, DF+, DFEI, NSR, Def PPA) can't use percent-of-average at all, so
# those use a real ABSOLUTE point-band instead.
#
# Tiering (mag = how far a value sits from the baseline, in the stat's own
# units): within band25 -> white (near average). Between band25 and band10
# -> green (better) / red (worse) -- "leaning" tier. Beyond band10 -> the
# NEW purple (top 10%, elite) / orange (bottom 10%, real outlier) tier.
#
# Annotation: any colored cell (green/red/purple/orange) shows "% over/below
# average" when that's a meaningful number for the stat; the absolute-banded
# zero-centered composites keep showing rank instead, same as v3.
# ---------------------------------------------------------------------------
STAT_BAND = {
    # key: ('pct'|'abs', +/-band10, +/-band25)
    "Off_PPG": ('pct', 53, 29), "Def_PPG": ('pct', 53, 29),
    "Off_Yds_PG": ('pct', 28, 14), "Def_Yds_PG": ('pct', 28, 14),
    "Off_YPP": ('pct', 26, 13), "Def_YPP": ('pct', 26, 13),
    "Off_RZ_%": ('pct', 20, 15), "Def_RZ_%": ('pct', 20, 15),
    "Off_3rd_%": ('pct', 32, 17), "Def_3rd_%": ('pct', 32, 17),
    "Off_Sacks_Allowed_PG": ('pct', 79, 39), "Def_Sacks_PG": ('pct', 79, 39),
    "Off_Pass_PG": ('pct', 38, 20), "Def_Pass_PG": ('pct', 38, 20),
    "Off_Pass_Att": ('pct', 29, 16), "Def_Pass_Att": ('pct', 29, 14),
    "QBR": ('pct', 34, 17), "Def_Eff": ('pct', 39, 22),           # QBR uses Def Eff's real band (no direct QBR match)
    "Off_Explosiveness": ('pct', 12, 7), "Def_Explosiveness": ('pct', 14, 8),
    "Off_Rush_PG": ('pct', 49, 28), "Def_Rush_PG": ('pct', 49, 28),
    "Off_Rush_Att": ('pct', 33, 16), "Def_Rush_Att": ('pct', 38, 20),
    "Pass_Pct": ('abs', 11.9, 5.9),
    "TFL_Def_PG": ('pct', 135, 95), "Stuffs_Off_PG": ('pct', 135, 95),
    "Off_Line_Yards": ('pct', 17, 9), "Def_Line_Yards": ('pct', 18, 11),
    "Off_Power_Success": ('pct', 22, 10), "Def_Power_Success": ('pct', 23, 11),
    "Off_Stuff_Rate": ('pct', 33, 20), "Def_Stuff_Rate": ('pct', 32, 20),
    "Off_Havoc": ('pct', 33, 18), "Def_Havoc": ('pct', 28, 16),
    "Off_Second_Level_Yards": ('pct', 25, 11), "Def_Second_Level_Yards": ('pct', 33, 16),
    "Off_Open_Field_Yards": ('pct', 69, 37), "Def_Open_Field_Yards": ('pct', 73, 38),
    "F+": ('abs', 1.394, 0.769), "OF+": ('abs', 1.38, 0.746), "DF+": ('abs', 1.397, 0.784),
    "FEI": ('abs', 0.88, 0.506), "OFEI": ('abs', 0.453, 0.25), "DFEI": ('abs', 0.422, 0.263),
    "NSR": ('abs', 0.395, 0.194),
    "OSR": ('pct', 34, 14), "DSR": ('pct', 49, 24),
    "Off_PPA": ('pct', 93, 55), "Def_PPA": ('abs', 0.171, 0.103),
    "Off_Eff": ('pct', 54, 34),
    "Off_Success_Rate": ('pct', 16, 9), "Def_Success_Rate": ('pct', 18, 12),
    "Off_Plays_PG": ('pct', 15, 6), "Def_Plays_Faced_PG": ('pct', 15, 6),
}


FLAT_NEAR_AVG_PCT = 15  # within 15% of average counts as near average; beyond that the stat number itself is red or green


# ---------------------------------------------------------------------------
# POLARITY -- taken from _STAT_SIGNAL_SPECS in cfb_working_schedule.py, which
# defines which direction is "good" for every graded stat. Defensive stats
# aren't uniform: Def_PPG, Def_Yds_PG, etc. are things the defense allows
# (lower is better), but Havoc, Stuff Rate, Sacks, and TFL are forced by the
# defense (higher is better). DSR, Def_PPA, and Def_Success_Rate (CFBD) are
# higher = worse.
# ---------------------------------------------------------------------------
HIGHER_IS_BETTER = {
    "Off_Yds_PG": True, "Def_Yds_PG": False,
    "Off_YPP": True, "Def_YPP": False,
    "Off_Pass_PG": True, "Def_Pass_PG": False,
    "Off_Pass_Att": True, "Def_Pass_Att": False,
    "Off_Rush_PG": True, "Def_Rush_PG": False,
    "Off_Rush_Att": True, "Def_Rush_Att": False,
    "Off_PPG": True, "Def_PPG": False,
    "Off_3rd_%": True, "Def_3rd_%": False,
    "Off_RZ_%": True, "Def_RZ_%": False,
    "Off_Sacks_Allowed_PG": False, "Def_Sacks_PG": True,
    "Off_Eff": True, "Def_Eff": False,
    "QBR": True,
    "TFL_Def_PG": True, "Stuffs_Off_PG": False,
    "F+": True, "OF+": True, "DF+": True,
    "FEI": True, "OFEI": True, "DFEI": True,
    "NSR": True, "OSR": True,
    "DSR": False,
    "Off_PPA": True, "Def_PPA": False,
    "Off_Stuff_Rate": False, "Def_Stuff_Rate": True,
    "Off_Havoc": False, "Def_Havoc": True,
    "Off_Line_Yards": True, "Def_Line_Yards": False,
    "Off_Second_Level_Yards": True, "Def_Second_Level_Yards": False,
    "Off_Open_Field_Yards": True, "Def_Open_Field_Yards": False,
    "Off_Power_Success": True, "Def_Power_Success": False,
    "Off_Success_Rate": True, "Def_Success_Rate": False,
    "Off_Explosiveness": True, "Def_Explosiveness": False,
    # Real stats added for the deep-dive real-data pipeline (not in the
    # production _STAT_SIGNAL_SPECS yet, since cfb_working_schedule.py
    # doesn't track these -- see cfb_matchup_deep_dive.py's own fetch).
    # Explicit here rather than relying on heat_cell's side=='O' fallback,
    # which would get Off_INT_PG backwards (higher thrown is BAD, not good).
    "Off_Comp_Pct": True, "Off_INT_PG": False, "Def_INT_PG": True,
}

# Tempo/volume stats -- the production spec deliberately excludes these
# from directional grading ("more plays isn't 'better,' it's just pace"),
# so these always render neutral gray, never green/red/purple/orange, while
# still showing the real +/-% deviation as plain informational text.
NON_DIRECTIONAL = {"Off_Plays_PG", "Def_Plays_Faced_PG"}


def heat_cell(val, key, side):
    """Returns (display_text, cell_bg, text_color, note).

    The real, intended tiering was already written as a
    comment on STAT_BAND above but the code below it never actually
    implemented the middle tier -- it only ever painted the WHOLE cell
    (white/green-red/purple-orange), so there was no visual difference
    between "leaning" and "elite/outlier" and the described 15%-25% tier
    never rendered anywhere, on any stat, any game. Real 4-tier scheme now:
      mag <= near_bound (flat 15%)            -> white cell, plain black text
      near_bound < mag <= band25 (real top/    -> still white cell, but the
        bottom 25% population line)               NUMBER's text itself turns
                                                    green/red ("leaning")
      band25 < mag <= band10 (real top/bottom  -> the WHOLE CELL turns
        10% population line)                       green/red
      mag > band10                             -> the whole cell turns
                                                    purple (elite) / orange
                                                    (bottom, real outlier)
    band25/band10 are the real, live-computed per-stat percentile bands
    (_set_live_band), not guesses -- "top 25%"/"top 10%" means this stat's
    actual real FBS-wide distribution, recomputed fresh every run.
    """
    if val is None:
        return "--", missing_bg, black_txt, None
    disp = _fmt(val)
    base = NATIONAL_BASELINE.get(key)
    band = STAT_BAND.get(key)
    if base is None or band is None:
        return disp, neutral_bg, black_txt, None
    kind, band10, band25 = band
    # Polarity: use the real, per-stat higher_is_better lookup when we have
    # one; only fall back to the old O/D guess for stats not in the real
    # spec (the new no-baseline placeholders like Sack%/Completion%/INT/QB
    # Rush Yards, which never reach here anyway since they have no
    # NATIONAL_BASELINE entry, plus a harmless safety net for anything else).
    higher_is_better = HIGHER_IS_BETTER.get(key, side == 'O')
    if kind == 'pct':
        pct_dev = (val - base) / abs(base) if base != 0 else 0.0
        signed = pct_dev if higher_is_better else -pct_dev
        mag = abs(pct_dev) * 100
        near_bound = FLAT_NEAR_AVG_PCT
    else:
        # zero-centered composites (F+/FEI family, NSR, Def_PPA) have no
        # "percent of average" concept (their real average sits near 0), so
        # a flat 15% doesn't translate here -- these keep the real,
        # per-stat-calibrated absolute band25 as the white/color line
        # instead, and, for the pct-kind stats,
        # skip straight to the full-cell tier once past
        # that line -- there's no natural "leaning" sub-tier for a
        # near-zero-mean composite the way there is for a real percentage.
        diff = val - base
        signed = diff if higher_is_better else -diff
        mag = abs(diff)
        near_bound = band25
    if key in NON_DIRECTIONAL:
        return disp, near_avg_bg, black_txt, None
    lean_color = color_green if signed > 0 else color_red
    extreme_color = color_purple if signed > 0 else color_orange
    if mag <= near_bound:
        return disp, near_avg_bg, black_txt, None
    if kind == 'pct' and mag <= band25:
        return disp, near_avg_bg, lean_color, None
    elif mag <= band10:
        return disp, lean_color, black_txt, None
    else:
        return disp, extreme_color, black_txt, None


# ---------------------------------------------------------------------------
# ILLUSTRATIVE RANKS -- "beside every metric so I know where the stat sits"
# (the same feature already built into cfb_working_schedule.py's real
# _build_stat_rank_lookup, which ranks a team against the full, real
# FBS-wide stats_lookup table). This preview only has two teams' worth of
# placeholder data, not the ~134-team real table needed for a genuine
# rank -- so these numbers are ALSO illustrative placeholders, deterministic
# per team+stat just so the layout looks the same as the real thing. Once
# wired to cws.stats_lookup on a local machine, swap this for the real
# rank_lookup dict already validated in cfb_working_schedule.py.
# ---------------------------------------------------------------------------
def _illustrative_rank(team, key):
    h = int(hashlib.md5(f"{team}|{key}".encode()).hexdigest(), 16)
    return (h % 133) + 1


# Set by the real deep-dive pipeline (cws._build_stat_rank_lookup(stats_lookup),
# the exact same real, tested FBS-wide rank engine cfb_working_schedule.py's
# own report already uses) before calling render_one_matchup(). Left None in
# PREVIEW mode, where _rk() falls back to the illustrative hash rank instead.
RANK_LOOKUP = None


def _rk(text, key, team, pct_note=None):
    if text in ("--", None):
        return text
    if pct_note is not None:
        return f"{text} ({pct_note})"
    if RANK_LOOKUP is not None:
        real_rank = RANK_LOOKUP.get(key, {}).get(team)
        # No real rank for this stat/team (not tracked, or no real value) --
        # show the bare value rather than inventing one, same as
        # cws._with_rank()'s own behavior.
        return f"{text} ({real_rank})" if real_rank is not None else text
    return f"{text} ({_illustrative_rank(team, key)})"


def make_cell(text, fg, bold=False, size=6.6, align=1):
    styles = getSampleStyleSheet()
    st = ParagraphStyle('c', parent=styles['Normal'], fontName='Helvetica-Bold' if bold else 'Helvetica',
                         fontSize=size, leading=size + 2, textColor=fg, alignment=align)
    return Paragraph(text, st)


# ---------------------------------------------------------------------------
# ONE STAT = ONE GRID, BOTH DIRECTIONS. Replaces the old bundled
# scoring/passing/rushing tables -- every individual stat now gets its own
# tiny 2-line grid: Team A offense vs Team B defense on top, Team A
# defense vs Team B offense right below it.
# ---------------------------------------------------------------------------
def stat_pair_grid(label, off_key, def_key, away_ts, home_ts, delta=None, delta_label=None, show_scale_blurb=True):
    """delta (optional): a raw entry from cfb_matchup_deltas.compute_all(),
    either ("single", value, favored) or ("paired", away_val, home_val) --
    rendered as a panel to the right of this grid. Pass
    delta_label when the delta's own METRIC_META label differs from this
    grid's stat `label` (e.g. a volume/efficiency half of a combined
    delta like Air Depth, attached across two different grids -- pass
    show_scale_blurb=False on the first of the two so the real analytical-
    scale text only prints once, under whichever grid it actually applies
    to, not twice)."""
    a_off_v, a_off_bg, a_off_fg, a_off_pct = heat_cell(away_ts.get(off_key), off_key, 'O')
    b_def_v, b_def_bg, b_def_fg, b_def_pct = heat_cell(home_ts.get(def_key), def_key, 'D')
    b_off_v, b_off_bg, b_off_fg, b_off_pct = heat_cell(home_ts.get(off_key), off_key, 'O')
    a_def_v, a_def_bg, a_def_fg, a_def_pct = heat_cell(away_ts.get(def_key), def_key, 'D')

    a_off_v = _rk(a_off_v, off_key, away, a_off_pct)
    b_def_v = _rk(b_def_v, def_key, home, b_def_pct)
    b_off_v = _rk(b_off_v, off_key, home, b_off_pct)
    a_def_v = _rk(a_def_v, def_key, away, a_def_pct)

    data = [
        [make_cell(a_off_v, a_off_fg, True), make_cell(f"{away} OFF vs {home} DEF", text_white, True, size=6),
         make_cell(b_def_v, b_def_fg, True)],
        [make_cell(a_def_v, a_def_fg, True), make_cell(f"{away} DEF vs {home} OFF", text_white, True, size=6),
         make_cell(b_off_v, b_off_fg, True)],
    ]

    def _build_grid_table(value_col_width, label_col_width):
        gt = Table(data, colWidths=[value_col_width, label_col_width, value_col_width])
        gt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), a_off_bg), ('BACKGROUND', (1, 0), (1, 0), label_bg),
            ('BACKGROUND', (2, 0), (2, 0), b_def_bg),
            ('BACKGROUND', (0, 1), (0, 1), a_def_bg), ('BACKGROUND', (1, 1), (1, 1), label_bg),
            ('BACKGROUND', (2, 1), (2, 1), b_off_bg),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
        ]))
        return gt

    below_blurb = None
    if delta is not None:
        dlabel = delta_label or label
        kind = delta[0]
        # Grid shrinks (270 -> GRID_WIDTH) and moves to the MIDDLE column;
        # a delta side-panel now flanks it on both the left (away) and
        # right (home) side.
        t = _build_grid_table(60, GRID_WIDTH - 120)
        if kind == 'single':
            _, value, favored = delta
            left_cell, right_cell = _single_delta_panel(dlabel, value, favored, width=DELTA_SIDE_WIDTH)
        else:  # 'paired'
            _, away_val, home_val = delta
            left_cell, right_cell = _paired_delta_panel(away_val, home_val, width=DELTA_SIDE_WIDTH,
                                                         show_net=not dlabel.startswith("The Fraud Index"))
            if show_scale_blurb:
                below_blurb = delta_scale_blurb(dlabel)
        row = Table([[left_cell, t, right_cell]], colWidths=[DELTA_SIDE_WIDTH, GRID_WIDTH, DELTA_SIDE_WIDTH])
        row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                  ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                                  ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
        header = Table([[make_cell(label.upper(), text_white, True, size=6.8)]], colWidths=[510])
        header.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), accent_blue),
                                     ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
        out = [header, row, Spacer(1, 4)]
        if below_blurb is not None:
            out = [header, row, Spacer(1, 3), below_blurb, Spacer(1, 4)]
        return out

    # No delta for this stat -- grid stays full-size and standalone, same
    # as always.
    t = _build_grid_table(70, 130)
    header = Table([[make_cell(label.upper(), text_white, True, size=6.8)]], colWidths=[270])
    header.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), accent_blue),
                                 ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
    return [header, t, Spacer(1, 4)]


# ---------------------------------------------------------------------------
# ONE-SIDED STAT ROW -- for a stat shown per-team with no offense-vs-
# opposing-defense pairing (Completion %, QB Rush Yards/Game): a single row,
# both teams, same shape as stat_pair_grid's header+box but only one line.
# tag_fn(raw_value) -> optional short qualifier appended after the number
# (used for the Pocket Passer / Mobile QB call on rush yards/game).
# ---------------------------------------------------------------------------
def single_stat_grid(label, key, away_ts, home_ts, tag_fn=None):
    a_v, a_bg, a_fg, a_pct = heat_cell(away_ts.get(key), key, 'O')
    h_v, h_bg, h_fg, h_pct = heat_cell(home_ts.get(key), key, 'O')
    a_v = _rk(a_v, key, away, a_pct)
    h_v = _rk(h_v, key, home, h_pct)
    if tag_fn is not None:
        a_raw, h_raw = away_ts.get(key), home_ts.get(key)
        if a_raw is not None:
            a_v = f"{a_v} {tag_fn(a_raw)}"
        if h_raw is not None:
            h_v = f"{h_v} {tag_fn(h_raw)}"
    data = [[make_cell(a_v, a_fg, True), make_cell(f"{away} vs {home}", text_white, True, size=6),
             make_cell(h_v, h_fg, True)]]
    t = Table(data, colWidths=[70, 130, 70])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), a_bg), ('BACKGROUND', (1, 0), (1, 0), label_bg),
        ('BACKGROUND', (2, 0), (2, 0), h_bg),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    header = Table([[make_cell(label.upper(), text_white, True, size=6.8)]], colWidths=[270])
    header.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), accent_blue),
                                 ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
    return [header, t, Spacer(1, 4)]


def single_line_row(label, key, away_ts, home_ts):
    av, abg, afg, apct = heat_cell(away_ts.get(key), key, 'O')
    hv, hbg, hfg, hpct = heat_cell(home_ts.get(key), key, 'O')
    av = _rk(av, key, away, apct)
    hv = _rk(hv, key, home, hpct)
    return [make_cell(av, afg, True), make_cell(label, text_white, True, size=6), make_cell(hv, hfg, True)], abg, hbg


def advanced_ratings_block(specs, away_ts, home_ts):
    rows = [single_line_row(lbl, key, away_ts, home_ts) for lbl, key in specs]
    data = [r[0] for r in rows]
    t = Table(data, colWidths=[70, 130, 70])
    style = [
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.black),
    ]
    for i, (_cells, abg, hbg) in enumerate(rows):
        style.append(('BACKGROUND', (0, i), (0, i), abg))
        style.append(('BACKGROUND', (1, i), (1, i), label_bg))
        style.append(('BACKGROUND', (2, i), (2, i), hbg))
    t.setStyle(TableStyle(style))
    return t


def delta_summary_block(entries):
    """Standalone delta attachment for sections that aren't a single
    stat_pair_grid (the Advanced Ratings F+/FEI, Success Rate, and PPA
    blocks bundle several stats into one shared table, so there's no
    single grid to render a delta beside) plus the Fraud Gap, which is
    itself built from two OTHER grids (Yards/Game + Points/Game) already
    shown above it, not a grid of its own. `entries` is a list of
    (label, delta_entry) pairs, each delta_entry shaped like
    stat_pair_grid's own `delta` param. Renders one small header + row per
    entry, single-kind numbers on their favored side (scale/description on
    the other), paired-kind numbers on each team's own side plus one
    real-analytical-scale blurb underneath -- same rules as beside a grid,
    just full standalone blocks instead of riding next to an existing
    away/home stat table."""
    out = []
    for label, delta_entry in entries:
        kind = delta_entry[0]
        header = Table([[make_cell(label.upper(), text_white, True, size=6.8)]], colWidths=[510])
        header.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), accent_blue),
                                     ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
        out.append(header)
        if kind == 'single':
            _, value, favored = delta_entry
            # Standalone block (no companion grid beside it) -- left/right
            # cell pair rendered directly as one full-width row, same
            # favored-side-gets-the-number rule as stat_pair_grid uses.
            left_cell, right_cell = _single_delta_panel(label, value, favored, width=255)
            row = Table([[left_cell, right_cell]], colWidths=[255, 255])
            row.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                                      ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
            out.append(row)
            out.append(Spacer(1, 4))
        else:  # 'paired'
            _, away_val, home_val = delta_entry
            if not label.startswith("The Fraud Index"):
                # show only the team the numbers favor (+ its head-to-head line)
                left_cell, right_cell = _paired_delta_panel(away_val, home_val, width=255, show_net=True)
                t = Table([[left_cell, right_cell]], colWidths=[255, 255])
                t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), delta_panel_bg),
                                        ('LINEAFTER', (0, 0), (0, 0), 0.5, colors.HexColor('#4B5563')),
                                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
                out.append(t)
                out.append(Spacer(1, 3))
                out.append(delta_scale_blurb(label))
                out.append(Spacer(1, 4))
                continue
            t = Table([[_delta_num_para(away_val), _delta_num_para(home_val)]], colWidths=[255, 255])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), delta_panel_bg),
                ('LINEAFTER', (0, 0), (0, 0), 0.5, colors.HexColor('#4B5563')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            out.append(t)
            out.append(Spacer(1, 3))
            out.append(delta_scale_blurb(label))
            out.append(Spacer(1, 4))
    return out


def section_header(title):
    # Bumped from size=8 to size=10 so these section banners read clearly
    # bigger than the 6.8pt individual stat headers below them, now that both
    # share the same black background.
    t = Table([[make_cell(title, text_white, True, size=10)]], colWidths=[510])
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), accent_blue),
                            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
    return t


def blurb(text):
    # Previously a solid navy-filled box with white text; now a white box with a
    # thin black outline and navy text instead.
    styles = getSampleStyleSheet()
    st = ParagraphStyle('blurb', parent=styles['Normal'], fontSize=7.2, leading=9.2,
                         textColor=colors.HexColor('#1A365D'))
    box = Table([[Paragraph(text, st)]], colWidths=[510])
    box.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.75, colors.black),
                             ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                             ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6)]))
    return box


def build():
    filename = "generated/cfb_matchup_card_PREVIEW_v4_purple_orange.pdf"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    doc = SimpleDocTemplate(filename, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36,
                             title="CFB Matchup Card -- Layout Preview")
    story = []
    styles = getSampleStyleSheet()

    warn_style = ParagraphStyle('warn', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#B00020'))
    story.append(Paragraph(
        "LAYOUT PREVIEW ONLY -- every number below is a placeholder for design review, not a real live stat "
        "(no live pull from TeamRankings/ESPN/bcftoys/CFBD). Judge the STRUCTURE, not the numbers. "
        "v4 EXPERIMENT: two-tier heat map, both tiers calibrated per-stat from the live "
        "cfb_matrices_outlook.pdf run -- white = within 10%% of average (near average), "
        "green/red = beyond 10%% but not yet a real outlier, PURPLE/ORANGE = real top/bottom 10%% (a true outlier). "
        "(Zero-centered composite ratings with no real 'percent of average' -- F+/FEI family, NSR, Def PPA -- use "
        "their own real absolute band as the white/color line instead of the flat 10%%.) "
        "Every cell shows a rank in parentheses (illustrative only in this preview); the color alone -- white/green/"
        "red/purple/orange -- signals real direction and severity.",
        warn_style))
    story.append(Spacer(1, 8))

    preview_deltas = deltas_mod.compute_all(away_ts, home_ts)
    render_one_matchup(story, away, home, away_ts, home_ts, away_fpi, home_fpi,
                        away_sor, home_sor, away_record, home_record, score_pred,
                        deltas=preview_deltas)

    doc.build(story)
    return filename


def render_one_matchup(story, away_, home_, away_ts_, home_ts_, away_fpi_, home_fpi_,
                        away_sor_, home_sor_, away_record_, home_record_, score_pred_,
                        model_pick_side=None, pick_is_risky=False, deltas=None):
    """Renders ONE full matchup's deep-dive card (header through Advanced
    Ratings) by appending flowables to `story` -- does NOT call doc.build()
    itself, so callers can combine many games into one document (see
    cfb_matchup_deep_dive.py, which calls this once per game with a
    PageBreak() between them) or just one (see build() above, PREVIEW mode).

    model_pick_side ('away'/'home'/None) and pick_is_risky highlight the
    team name the tuned stat-vote model picks for this matchup -- turquoise
    for the pick, orange if Def_Sacks_PG disagrees with it. Same real,
    already-tested convention cfb_working_schedule.py's own skinny report
    uses (TURQUOISE_HIGHLIGHT/ORANGE_CAUTION_HIGHLIGHT, _team_name_span) --
    reused here, not reinvented. Both default to no highlight (PREVIEW mode
    passes neither).

    deltas (optional): the dict cfb_matchup_deltas.compute_all(away_ts,
    home_ts) returns for this matchup, keyed by delta label. When given,
    every delta from the 3 reference sheets is attached beside (single-
    number deltas) or beside-plus-below (2-number/paired deltas) its
    matching grid -- see the DELTA_ATTACH_* mappings just below this
    docstring. None (PREVIEW mode's default) renders every grid exactly as
    before, with no delta panels at all.
    """
    global away, home, away_ts, home_ts, away_fpi, home_fpi, away_sor, home_sor, away_record, home_record, score_pred
    away, home = away_, home_
    away_ts, home_ts = away_ts_, home_ts_
    away_fpi, home_fpi = away_fpi_, home_fpi_
    away_sor, home_sor = away_sor_, home_sor_
    away_record, home_record = away_record_, home_record_
    score_pred = score_pred_

    deltas = deltas or {}

    def _dget(label):
        return deltas.get(label)

    styles = getSampleStyleSheet()

    # ---- HEADER: FPI outside, SOR inside, record under name, score
    # prediction centered between the two records. ----
    name_style = ParagraphStyle('name', parent=styles['Normal'], fontSize=13, alignment=TA_CENTER,
                                 textColor=text_white, fontName='Helvetica-Bold')
    rec_style = ParagraphStyle('rec', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER, textColor=text_white)
    split_style = ParagraphStyle('split', parent=styles['Normal'], fontSize=6.5, alignment=TA_CENTER,
                                  textColor=colors.HexColor('#B8C4D9'))
    center_style = ParagraphStyle('center', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER, textColor=text_white,
                                   fontName='Helvetica-Bold')

    # pass%/rush% play-calling split under each team's record. This
    # one DOES have a real baseline -- re-parsed directly from the live
    # cfb_matrices_outlook.pdf (PASS PLAYS/GAME vs RUSH PLAYS/GAME, both
    # sides of all 65 games this week, restricted to the real per-game pages,
    # not the leaderboard section): real mean pass-play share is 45.6% of
    # offensive plays, real top/bottom-25% band is +/-5.9 points, real
    # top/bottom-10% band is +/-11.9 points -- same STAT_BAND/NATIONAL_
    # BASELINE entries the heat map above already uses for "Pass_Pct".
    def _split_text(pass_pct):
        # the deep-dive run showed "Pass 50% / Rush 50%" on literally
        # every game -- that was this .get()'s old default (50.0) silently
        # standing in for missing real data on every single team, not an
        # actual computed split. Real mode now computes a real Pass_Pct from
        # already-fetched Off_Pass_Plays_PG/Off_Rush_Plays_PG (see
        # cfb_matchup_deep_dive.py) and passes None when that can't be
        # computed for a team -- show that honestly as "--" rather than
        # ever guessing 50/50 again.
        if pass_pct is None:
            return "Pass -- / Rush --"
        return f"Pass {pass_pct:.0f}% / Rush {100 - pass_pct:.0f}%"

    # Team names are highlighted: turquoise when this side is the
    # tuned stat-vote model's real pick for this matchup, orange instead
    # when that pick is flagged risky (Def_Sacks_PG disagrees with it),
    # plain white otherwise. Both args are None/False in PREVIEW mode.
    def _name_color(side):
        if model_pick_side != side:
            return text_white
        return ORANGE_CAUTION_HIGHLIGHT if pick_is_risky else TURQUOISE_HIGHLIGHT
    away_name_color = _name_color('away')
    home_name_color = _name_color('home')

    away_block = Table([
        [make_cell(f"FPI {away_fpi}", text_white, True, size=8, align=0),
         make_cell(away.upper(), away_name_color, True, size=13),
         make_cell(f"SOR {away_sor}", text_white, True, size=8, align=2)],
        [Paragraph("", rec_style), Paragraph(away_record, rec_style), Paragraph("", rec_style)],
        [Paragraph("", split_style), Paragraph(_split_text(away_ts.get("Pass_Pct")), split_style),
         Paragraph("", split_style)],
    ], colWidths=[50, 90, 50])
    away_block.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))

    home_block = Table([
        [make_cell(f"SOR {home_sor}", text_white, True, size=8, align=0),
         make_cell(home.upper(), home_name_color, True, size=13),
         make_cell(f"FPI {home_fpi}", text_white, True, size=8, align=2)],
        [Paragraph("", rec_style), Paragraph(home_record, rec_style), Paragraph("", rec_style)],
        [Paragraph("", split_style), Paragraph(_split_text(home_ts.get("Pass_Pct")), split_style),
         Paragraph("", split_style)],
    ], colWidths=[50, 90, 50])
    home_block.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                     # Home team's FPI sat right against the header's right edge -- nudge it in a bit
                                     ('RIGHTPADDING', (2, 0), (2, -1), 8)]))

    center_block = Table([
        [Paragraph("at", center_style)],
        [Paragraph(score_pred, center_style)],
    ], colWidths=[160])

    header_row = Table([[away_block, center_block, home_block]], colWidths=[190, 160, 190])
    header_row.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), accent_blue),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(header_row)
    story.append(Spacer(1, 8))
    story.append(blurb(
        "<b>THE STAKES:</b> This is where you lay down the baseline reality. Before you look at anything else, "
        "what does the scoreboard math say? This sets up the entire blueprint of who is coming in hot and who "
        "is projected to slide or conquer."
    ))
    story.append(Spacer(1, 10))

    # ---- SCORING ----
    story.append(section_header("BREAKDOWN"))
    story.append(Spacer(1, 4))
    # Plays/Game (tempo/volume) is real and already tracked in
    # cfb_working_schedule.py (ESPN's plays-per-game / opponent-plays-per-
    # game), but wasn't in this card. That ESPN
    # endpoint isn't called directly here, so the real band here is approximated from the live
    # matrices PDF instead (real pass-plays/game + real rush-plays/game,
    # summed per team) -- same underlying "snaps run" concept, a different
    # real source than ESPN's own count. Placed first since total snaps run
    # is context for every rate stat below it.
    story.extend(stat_pair_grid("Plays / Game", "Off_Plays_PG", "Def_Plays_Faced_PG", away_ts, home_ts,
                                 delta=_dget("Plays Per Game (Pace) Delta"), delta_label="Plays Per Game (Pace) Delta"))
    story.extend(stat_pair_grid("Points / Game", "Off_PPG", "Def_PPG", away_ts, home_ts,
                                 delta=_dget("Points Per Game (PPG) Delta"), delta_label="Points Per Game (PPG) Delta"))
    story.extend(stat_pair_grid("Yards / Game", "Off_Yds_PG", "Def_Yds_PG", away_ts, home_ts,
                                 delta=_dget("Yards Per Game (YPG) Delta"), delta_label="Yards Per Game (YPG) Delta"))
    story.extend(stat_pair_grid("Yards / Play", "Off_YPP", "Def_YPP", away_ts, home_ts,
                                 delta=_dget("Yards Per Play (YPP) Delta"), delta_label="Yards Per Play (YPP) Delta"))
    story.append(blurb(
        "<b>SPEED VS SUBSTANCE:</b> Sure, you put up a mountain of yards, but are you eating up chunks of turf "
        "on every snap, or just snapping the ball 90 times a game? Yards per play blows the lid off fake "
        "offenses and exposes who is actually explosive."
    ))
    story.append(Spacer(1, 4))
    # Fraud Index & Fraud Gap: derived FROM the Yards/Game + Points/Game
    # grids just above (each team's real yards-edge vs. real points-edge),
    # not from a grid of its own -- standalone block, same placement rule
    # as the Advanced Ratings attachments below.
    fraud_entry = _dget("The Fraud Index & Fraud Gap (Points vs. Yards)")
    if fraud_entry is not None:
        story.extend(delta_summary_block([("The Fraud Index & Fraud Gap (Points vs. Yards)", fraud_entry)]))
    story.extend(stat_pair_grid("Red Zone %", "Off_RZ_%", "Def_RZ_%", away_ts, home_ts,
                                 delta=_dget("Red Zone % (Blood Zone) Delta"), delta_label="Red Zone % (Blood Zone) Delta"))
    story.append(blurb(
        "<b>THE BLOOD ZONE:</b> The field shrinks, the space vanishes, and the big boys in the interior start "
        "throwing hands! Settling for field goals here is a slow death. Do you punch it into the dirt for 6, "
        "or does the defense stand tall on the goal line?"
    ))
    story.append(Spacer(1, 4))
    story.extend(stat_pair_grid("3rd Down %", "Off_3rd_%", "Def_3rd_%", away_ts, home_ts,
                                 delta=_dget("3rd Down % (Money Down) Delta"), delta_label="3rd Down % (Money Down) Delta"))
    story.append(blurb(
        "<b>MONEY DOWN EXECUTION:</b> The stadium is roaring, the chains are set, and it's time to find out who "
        "has the ice in their veins! Can the quarterback find the soft spot in the zone, or will the pass rush "
        "crash the party and force the punting unit onto the field?"
    ))
    story.append(Spacer(1, 4))

    # ---- PASSING ----
    story.append(section_header("PASSING GAME"))
    story.append(Spacer(1, 4))
    # Air Depth Delta (Passing Volume vs. Efficiency) spans these two grids
    # -- the real volume half (Yards/Game) beside the first, the real
    # efficiency half (Yards/Attempt, i.e. YPA) beside the second, with the
    # actual YPA-based analytical scale printed once, under the second.
    air_depth = _dget("Air Depth Delta (Passing Volume vs. Efficiency)")
    if air_depth is not None:
        _, a_vol, a_eff, h_vol, h_eff = air_depth
        air_depth_vol, air_depth_eff = ("paired", a_vol, h_vol), ("paired", a_eff, h_eff)
    else:
        air_depth_vol = air_depth_eff = None
    story.extend(stat_pair_grid("Pass Yards / Game", "Off_Pass_PG", "Def_Pass_PG", away_ts, home_ts,
                                 delta=air_depth_vol, delta_label="Air Depth Delta (Passing Volume vs. Efficiency)",
                                 show_scale_blurb=False))
    story.extend(stat_pair_grid("Pass Yards / Attempt", "Off_Pass_Att", "Def_Pass_Att", away_ts, home_ts,
                                 delta=air_depth_eff, delta_label="Air Depth Delta (Passing Volume vs. Efficiency)"))
    story.append(blurb(
        "<b>THE AERIAL ASSAULT:</b> Are we talking about a conservative dink-and-dunk scheme or an absolute "
        "vertical circus? This showcases the raw capability of the passing attack to stretch boundaries and "
        "force safeties to drop deep."
    ))
    story.append(Spacer(1, 4))
    story.extend(single_stat_grid("QBR", "QBR", away_ts, home_ts))
    story.append(blurb(
        "<b>THE GENERALS' DUEL:</b> This is the ultimate test of quarterback processing speed vs. secondary "
        "lockouts. Can the signal-caller read the blitz and drop a dime into a tight window, or will a ballhawk "
        "safety read his eyes and take it the other way?"
    ))
    story.append(Spacer(1, 4))
    # Off_Eff is real and already tracked in cfb_working_schedule.py
    # (ESPN's own overall offensive efficiency rating) but wasn't in this card
    # -- only its Def_Eff sibling was (paired with QBR above). Standard
    # off-vs-opposing-defense pairing, same real band methodology as
    # everything else, placed right next to its QBR/Def_Eff sibling.
    story.extend(stat_pair_grid("Offensive Efficiency", "Off_Eff", "Def_Eff", away_ts, home_ts))
    story.append(Spacer(1, 4))
    # The fake "Sack %" (no real
    # source anywhere) is replaced with the REAL Sacks Allowed/Game pair
    # cfb_working_schedule.py already tracks (Off_Sacks_Allowed_PG /
    # Def_Sacks_PG -- the exact same two real TeamRankings columns the
    # Trenches/TFL section already uses elsewhere in this file), same shape
    # as every other real stat_pair_grid.
    #
    # Completion % and Interceptions/Game: "for the rest can we pull it" --
    # real, pulled by cfb_matchup_deep_dive.py from two new TeamRankings
    # pages cfb_working_schedule.py doesn't fetch yet (Off_Comp_Pct,
    # Off_INT_PG/Def_INT_PG). NATIONAL_BASELINE/STAT_BAND for these three
    # keys aren't hardcoded here -- the deep-dive script computes them live
    # from the real, full stats_lookup it just fetched (same real "how far
    # the top/bottom 10%/25% sits from the average" methodology as every
    # other stat, just computed from this week's live pull instead of a
    # PDF snapshot) and sets them before rendering. In PREVIEW mode (no real
    # pull), these three still fall back to neutral gray, same as always.
    #
    # QB Rush Yards/Game: NOT pulled real yet -- there's no team-level source
    # for this anywhere (TeamRankings only has whole-team rushing splits,
    # not isolated QB rushing), it would need a real per-player CFBD pull
    # plus a real "who is this team's starting QB" judgment call that hasn't
    # been made yet -- so this stays an honestly-disclosed illustrative
    # placeholder (still neutral gray) until that's worked out.
    story.extend(stat_pair_grid("Sacks Allowed / Game", "Off_Sacks_Allowed_PG", "Def_Sacks_PG", away_ts, home_ts,
                                 delta=_dget("The Finishing Delta (Sack Rate vs. Havoc Allowed)"),
                                 delta_label="The Finishing Delta (Sack Rate vs. Havoc Allowed)"))
    story.extend(single_stat_grid("Completion %", "Off_Comp_Pct", away_ts, home_ts))
    story.extend(single_stat_grid("QB Rush Yards / Game", "Off_QB_Rush_PG", away_ts, home_ts,
                                   tag_fn=lambda v: "(Mobile)" if v >= 20 else "(Pocket)"))
    story.extend(stat_pair_grid("Passing Explosiveness", "Off_Explosiveness", "Def_Explosiveness", away_ts, home_ts,
                                 delta=_dget("Vertical Lightning Strike Delta (Passing Explosiveness)"),
                                 delta_label="Vertical Lightning Strike Delta (Passing Explosiveness)"))
    story.append(blurb(
        "<b>CHUNK PLAY HAZARD:</b> The deep bombs that make the entire stadium jump out of their seats! This "
        "tells you if an offense can strike like lightning in one play, or if the defense is a lock to give up "
        "catastrophic breakdowns in the secondary."
    ))
    story.append(Spacer(1, 4))
    # Interceptions/Game -- real now too (see note above): Off_INT_PG/
    # Def_INT_PG pulled live by cfb_matchup_deep_dive.py.
    story.extend(stat_pair_grid("Interceptions / Game", "Off_INT_PG", "Def_INT_PG", away_ts, home_ts))
    story.append(Spacer(1, 4))

    # ---- RUSHING (TFL relocated here) ----
    story.append(section_header("RUSHING GAME"))
    story.append(Spacer(1, 4))
    # Per-Carry Reality Delta (Rushing Volume vs. Efficiency) -- same
    # split-across-two-grids treatment as Air Depth Delta above.
    per_carry = _dget("Per-Carry Reality Delta (Rushing Volume vs. Efficiency)")
    if per_carry is not None:
        _, a_vol, a_eff, h_vol, h_eff = per_carry
        per_carry_vol, per_carry_eff = ("paired", a_vol, h_vol), ("paired", a_eff, h_eff)
    else:
        per_carry_vol = per_carry_eff = None
    story.extend(stat_pair_grid("Rush Yards / Game", "Off_Rush_PG", "Def_Rush_PG", away_ts, home_ts,
                                 delta=per_carry_vol, delta_label="Per-Carry Reality Delta (Rushing Volume vs. Efficiency)",
                                 show_scale_blurb=False))
    story.extend(stat_pair_grid("Rush Yards / Attempt", "Off_Rush_Att", "Def_Rush_Att", away_ts, home_ts,
                                 delta=per_carry_eff, delta_label="Per-Carry Reality Delta (Rushing Volume vs. Efficiency)"))
    story.append(blurb(
        "<b>THE GROUND POUND:</b> This isn't pretty -- it's pure, unadulterated willpower. Are you chipping "
        "away at the defense with 5 yards a carry, or are you getting completely stuffed into a brick wall "
        "every time you hand the ball off?"
    ))
    story.append(Spacer(1, 4))
    # TFL: cfb_working_schedule.py already tracks BOTH real
    # halves of this stat (line 2148 there: ('TFL','O'): 'Stuffs_Off_PG',
    # ('TFL','D'): 'TFL_Def_PG') -- Stuffs_Off_PG is how often THIS team's
    # offense got blown up for a loss, TFL_Def_PG is how many THIS team's
    # defense forces. That's a real off-vs-def pair, same shape as every
    # other stat here -- was wrongly shown as a single defense-only line
    # before. Both real-calibrated from the same pooled "TFL" data in the
    # live matrices PDF (that PDF's real TFL column mixes both sides
    # together the same way, so one real band covers both keys).
    story.extend(stat_pair_grid("TFL / Game", "Stuffs_Off_PG", "TFL_Def_PG", away_ts, home_ts))
    # Renamed from the template's misapplied "THE CHAOS FACTOR" (that title
    # actually belongs to Havoc Rate down in Trenches, below) -- this is the
    # rewritten TFL-specific commentary.
    story.append(blurb(
        "<b>BACKFIELD DEMOLITION:</b> Tackles for loss measure pure defensive disruption at the point of attack -- "
        "a defense racking these up is blowing up run plays before they start, putting the offense behind schedule "
        "on early downs and forcing exactly the kind of long-yardage situations a defense wants to see."
    ))
    story.append(Spacer(1, 4))

    # ---- TRENCHES ----
    story.append(section_header("THE TRENCHES (O-LINE VS D-LINE)"))
    story.append(Spacer(1, 4))
    story.extend(stat_pair_grid("Line Yards", "Off_Line_Yards", "Def_Line_Yards", away_ts, home_ts,
                                 delta=_dget("Heavy Artillery Line Push (Line Yards Delta)"),
                                 delta_label="Heavy Artillery Line Push (Line Yards Delta)"))
    story.append(blurb(
        "<b>THE HEAVY ARTILLERY TRENCH WAR:</b> This is where the big boys battle it out to see who owns the turf! "
        "This isn't about running backs; this is about the offensive line moving a mountain of humanity backwards. "
        "Elite line yards mean your front wall is clearing out whole lanes before anyone even touches the back!"
    ))
    story.append(Spacer(1, 4))
    story.extend(stat_pair_grid("Power Success Rate", "Off_Power_Success", "Def_Power_Success", away_ts, home_ts,
                                 delta=_dget("4th & Inches Manhood Test (Power Success Rate)"),
                                 delta_label="4th & Inches Manhood Test (Power Success Rate)"))
    story.append(blurb(
        "<b>4TH AND INCHES MANHOOD TEST:</b> It's short yardage, everyone in the stadium knows exactly what is "
        "coming, and it's a test of sheer absolute physical dominance. Can you move the pile to move the chains, "
        "or does the defensive interior stone you cold at the line of scrimmage?"
    ))
    story.append(Spacer(1, 4))
    story.extend(stat_pair_grid("Stuff Rate", "Off_Stuff_Rate", "Def_Stuff_Rate", away_ts, home_ts,
                                 delta=_dget("Drive-Killer Penetration (Stuff Rate Delta)"),
                                 delta_label="Drive-Killer Penetration (Stuff Rate Delta)"))
    story.append(blurb(
        "<b>THE DRIVE KILLER:</b> The percentage of runs stopped dead at or behind the line of scrimmage! A high "
        "defensive stuff rate means the defensive front seven is penetrating into the backfield and setting up "
        "camp. If you get caught behind the chains, your playbook is officially dead."
    ))
    story.append(Spacer(1, 4))
    story.extend(stat_pair_grid("Havoc Rate", "Off_Havoc", "Def_Havoc", away_ts, home_ts,
                                 delta=_dget("The Chaos Coefficient Mismatch (Havoc Delta)"),
                                 delta_label="The Chaos Coefficient Mismatch (Havoc Delta)"))
    story.append(blurb(
        "<b>THE CHAOS FACTOR:</b> Sacks, tackles for loss, forced fumbles, and tipped passes! This tracks pure "
        "defensive disruption. If a defense forces chaos, they break your rhythm, rattle your quarterback, and "
        "turn an orderly drive into complete and utter panic."
    ))
    story.append(Spacer(1, 4))
    story.extend(stat_pair_grid("2nd Level Yards", "Off_Second_Level_Yards", "Def_Second_Level_Yards", away_ts, home_ts,
                                 delta=_dget("2nd Level Delta (The Front-7 Matchup)"),
                                 delta_label="2nd Level Delta (The Front-7 Matchup)"))
    story.append(blurb(
        "<b>LINEBACKER EVASION:</b> This tracks the yardage picked up 5 to 10 yards past the line of scrimmage. "
        "It shows how clean the blocking is downfield and how effectively the running backs are slicing through "
        "the secondary level before safety help arrives."
    ))
    story.append(Spacer(1, 4))
    story.extend(stat_pair_grid("Open Field Yards", "Off_Open_Field_Yards", "Def_Open_Field_Yards", away_ts, home_ts,
                                 delta=_dget("Open Field Delta (The Secondary Matchup)"),
                                 delta_label="Open Field Delta (The Secondary Matchup)"))
    story.append(blurb(
        "<b>THE BREAKOUT GEIGER COUNTER:</b> Anything gained past 10 yards! This isn't on the big uglies up front "
        "-- this is pure credit to your playmakers making guys miss in space, breaking ankles, and turning a "
        "simple run into a house call!"
    ))
    story.append(Spacer(1, 4))

    # ---- ADVANCED RATINGS -- unchanged, one line per stat, split into the
    # same 3 logical groups the template's commentary addresses ----
    story.append(section_header("ADVANCED RATINGS (F+/FEI/DSR/PPA)"))
    story.append(Spacer(1, 4))
    power_specs = [("F+", "F+"), ("OF+", "OF+"), ("DF+", "DF+"), ("FEI", "FEI"), ("OFEI", "OFEI"), ("DFEI", "DFEI")]
    story.append(advanced_ratings_block(power_specs, away_ts, home_ts))
    story.append(blurb(
        "<b>THE BRAIN TRUST POWER RANKINGS:</b> Forget about records and luck against the spread! These are the "
        "heavy-duty computer models stripping away all the schedule bias. This tells you who the true "
        "heavyweights are when you strip down the raw, independent efficiencies of both programs."
    ))
    story.append(Spacer(1, 4))
    power_delta_entries = [(lbl, _dget(lbl)) for lbl in
                            ("Net Efficiency Delta (The Vegas Filter)", "FEI Delta") if _dget(lbl) is not None]
    if power_delta_entries:
        story.extend(delta_summary_block(power_delta_entries))
    success_specs = [("NET SUCCESS RATE", "NSR"), ("OFF SUCCESS RATE (OSR)", "OSR"), ("OPP SUCCESS RATE (DSR)", "DSR"),
                      ("OFF SUCCESS RATE (CFBD)", "Off_Success_Rate"), ("DEF SUCCESS RATE (CFBD)", "Def_Success_Rate")]
    # cfb_working_schedule.py also tracks a SECOND, CFBD-sourced
    # success rate pair, distinct from the bcftoys OSR/DSR above (real,
    # different values in the matrices PDF -- confirmed by section,
    # not just by matching label text, since both series print under the
    # identical "OFF SUCCESS RATE" label in different report sections).
    # Labeled "(CFBD)" here to keep the two series clearly apart.
    story.append(advanced_ratings_block(success_specs, away_ts, home_ts))
    story.append(blurb(
        "<b>DOWN-TO-DOWN CONSISTENCY:</b> This is the ultimate baseline of smashmouth execution! Forget the "
        "lucky 80-yard fluke plays. Gaining 5 yards on 1st down, moving the chains, and staying ahead of "
        "schedule -- whoever owns this stays out of 3rd-and-long hell."
    ))
    story.append(Spacer(1, 4))
    success_delta_entries = [(lbl, _dget(lbl)) for lbl in
                              ("Net Success Rate Delta", "'Stay-on-Schedule' Rushing Delta (Success Rate)")
                              if _dget(lbl) is not None]
    if success_delta_entries:
        story.extend(delta_summary_block(success_delta_entries))
    ppa_specs = [("OFF PPA", "Off_PPA"), ("DEF PPA ALLOWED", "Def_PPA")]
    story.append(advanced_ratings_block(ppa_specs, away_ts, home_ts))
    story.append(blurb(
        "<b>THE VALUE ADDED:</b> Advanced expected points added! Every single snap either moves you closer to a "
        "touchdown or hurts your chances. This tracks who maximizes value on every single play and who bleeds "
        "points under pressure."
    ))
    ppa_delta_entry = _dget("Passing Down Panic Index (PPA)")
    if ppa_delta_entry is not None:
        story.append(Spacer(1, 4))
        story.extend(delta_summary_block([("Passing Down Panic Index (PPA)", ppa_delta_entry)]))


if __name__ == "__main__":
    path = build()
    print(f"Wrote {path}")
