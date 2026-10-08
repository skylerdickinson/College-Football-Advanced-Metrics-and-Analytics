"""
THE SKINNY -- a simple, printer-friendly, black-and-white per-game breakdown.

This is a companion report to cfb_working_schedule.py, not a replacement.
It reuses that script's own tested data-pulling and prediction functions
(imported as a module -- nothing here re-implements a scrape, a formula,
or a weight that's already been built and backtested over there) and just
lays the same real numbers out in a much simpler page: no color, no
grading, one page per game. A Pass%/Rush% identity line and a Stuff Rate
snapshot always show (so you know what kind of team each side is up
front, regardless of how predictive that particular number is), and below
that is a single ranked table of the REAL highest-win-rate stats in the
whole sheet -- recomputed fresh every run from cfb_stat_history.json, not
a fixed list -- followed by a short real-stats-grounded commentary
paragraph ending in the same model's actual prediction for that game.

Run it from the same folder as cfb_working_schedule.py:
    python3 the_skinny.py
Output: generated/the_skinny.pdf
"""
import os
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, PageBreak, Spacer

import cfb_working_schedule as cws
import cfb_matchup_deltas as deltas_mod


# ==========================================
# DATASET -- same real pull sequence as cws.main(), stopping short of
# cws.main()'s own PDF build so this script can build its own instead.
# Nothing below re-implements a scrape or a formula; every call is the
# exact same tested function cfb_working_schedule.py already uses.
# ==========================================
def build_dataset():
    print("[the skinny] Loading schedule file coordinates...")
    schedule_df, week_number, season_year = cws.fetch_live_cfb_schedule()
    if schedule_df.empty:
        print("[the skinny] Schedule matrix empty.")
        return None

    print("[the skinny] Pulling global on-field matrix layers...")
    stats_lookup = cws.fetch_all_teamrankings_stats()
    if stats_lookup is None or stats_lookup.empty:
        print("[the skinny] Could not load stats data.")
        return None

    _TR_NAMES = list(stats_lookup['Clean_Name'].dropna().unique())   # 2026-10-06: align every other source onto TeamRankings names (same as cws.main)

    print("[the skinny] Pulling ESPN team directory, FPI/efficiency, and QBR...")
    team_directory = cws.fetch_espn_team_directory()
    name_to_id = cws.build_name_to_id(team_directory)

    fpi_lookup = cws.fetch_espn_power_index(season_year, week_number, team_directory)
    qbr_lookup = cws.fetch_espn_qbr(season_year, team_directory)

    fpi_rows = []
    for team_name, vals in fpi_lookup.items():
        fpi_rows.append({'Clean_Name': team_name, 'FPI': vals.get('FPI'),
                          'Off_Eff': vals.get('Off_Eff'), 'Def_Eff': vals.get('Def_Eff'),
                          'SOR': vals.get('SOR')})
    if fpi_rows:
        stats_lookup = pd.merge(stats_lookup, cws._align_names(pd.DataFrame(fpi_rows), _TR_NAMES, 'FPI'), on='Clean_Name', how='outer')

    if qbr_lookup:
        qbr_rows = [{'Clean_Name': k, 'QBR': v} for k, v in qbr_lookup.items()]
        stats_lookup = pd.merge(stats_lookup, cws._align_names(pd.DataFrame(qbr_rows), _TR_NAMES, 'QBR'), on='Clean_Name', how='outer')

    print("[the skinny] Pulling per-team TFL / time of possession / FG% for this week's teams...")
    playing_teams = set(schedule_df['Away_Team']).union(set(schedule_df['Home_Team']))
    extra_rows = []
    for team_name in playing_teams:
        tid = name_to_id.get(team_name)
        if not tid:
            continue
        extra = cws.fetch_espn_extra_team_stats(tid, season_year, team_name=team_name)
        extra['Clean_Name'] = team_name
        extra_rows.append(extra)
    if extra_rows:
        stats_lookup = pd.merge(stats_lookup, cws._align_names(pd.DataFrame(extra_rows), _TR_NAMES, 'ESPN extra'), on='Clean_Name', how='outer')

    print("[the skinny] Pulling bcftoys F+ / FEI / Drive Success Rate ratings...")
    bcftoys_df, _bcftoys_avg = cws.fetch_bcftoys_ratings(season_year)
    if not bcftoys_df.empty:
        stats_lookup = pd.merge(stats_lookup, cws._align_names(bcftoys_df, _TR_NAMES, 'bcftoys'), on='Clean_Name', how='outer')

    print("[the skinny] Pulling CFBD off/def PPA and stuff rate...")
    cfbd_df, _cfbd_avg = cws.fetch_cfbd_advanced_stats(season_year)
    if not cfbd_df.empty:
        stats_lookup = pd.merge(stats_lookup, cws._align_names(cfbd_df, _TR_NAMES, 'CFBD'), on='Clean_Name', how='outer')

    dup_names = stats_lookup['Clean_Name'][stats_lookup['Clean_Name'].duplicated(keep=False)].unique()
    if len(dup_names):
        print(f"[the skinny] -> duplicate Clean_Name row(s) after merges: {list(dup_names)} "
              f"-- keeping the first row for each.")
        stats_lookup = stats_lookup.groupby('Clean_Name', as_index=False).first()

    stats_lookup.set_index('Clean_Name', inplace=True)

    known_teams = set(stats_lookup.index[stats_lookup['Off_Yds_PG'].notna()])

    # NEW: same real, non-guessing generic name-match
    # rescue as cws.main() and cfb_matchup_deep_dive.py now both use --
    # see cws.fuzzy_match_unknown_team()'s docstring. Without this, a
    # naming gap fixed in cfb_working_schedule.py's dict still silently
    # dropped the same real game from THIS report until it got its own
    # copy of the fix too.
    unmatched_names = (set(schedule_df['Away_Team']) | set(schedule_df['Home_Team'])) - known_teams
    rescued = {}
    for raw_name in unmatched_names:
        hit = cws.fuzzy_match_unknown_team(raw_name, known_teams)
        if hit:
            rescued[raw_name] = hit
    if rescued:
        print(f"[the skinny] -> Auto-matched {len(rescued)} team name(s) that would otherwise have been "
              f"dropped (ESPN/TeamRankings naming gap, resolved by generic abbreviation normalization):")
        for raw_name, matched_name in rescued.items():
            print(f"      '{raw_name}'  ->  '{matched_name}'")
        schedule_df['Away_Team'] = schedule_df['Away_Team'].replace(rescued)
        schedule_df['Home_Team'] = schedule_df['Home_Team'].replace(rescued)
        for raw_name, matched_name in rescued.items():
            schedule_df['Game'] = schedule_df['Game'].str.replace(raw_name, matched_name, regex=False)

    before_count = len(schedule_df)
    # CHANGED: same real-LSU-hiding bug fixed in cfb_working_schedule.py's
    # main() -- requiring BOTH sides to have stats (AND) silently hid real FBS teams whose
    # opponent that week was a genuine FCS buy-game. Now only drops if NEITHER side matches.
    keep_mask = (schedule_df['Away_Team'].isin(known_teams) | schedule_df['Home_Team'].isin(known_teams))
    schedule_df = schedule_df[keep_mask].reset_index(drop=True)
    dropped = before_count - len(schedule_df)
    if dropped:
        print(f"[the skinny] -> Dropped {dropped} game(s) where NEITHER side has a TeamRankings "
              f"stats match (same drop rule cfb_working_schedule.py uses).")

    print("[the skinny] Loading the real backtested stat-vote model...")
    stat_history = cws.load_stat_history()
    included_stats, model_accuracy, model_correct, model_decided, model_total = cws.tune_stat_weights(stat_history)
    weights_by_key = {key: weight for _, key, weight, _, _ in included_stats}
    included_keys = [key for _, key, _, _, _ in included_stats]
    sacks_agreement = cws.compute_sacks_agreement_breakdown(stat_history, included_keys, weights_by_key)
    raw_win_rates = cws._individual_stat_win_rates(stat_history)
    if model_total:
        print(f"[the skinny] -> Model backtest: {model_correct}/{model_decided} = "
              f"{(model_correct/model_decided*100 if model_decided else 0):.1f}% accuracy, "
              f"{model_total} total game(s) on record.")

    # ---- Backtested margin/spread model
    # Uses the same OLS fit as main() in cfb_working_schedule.py, shared through
    # cfb_forecast_history.json so both scripts' "Projection favors..." lines
    # agree. See cfb_matchup_deltas.tune_forecast_weights() for the methodology
    # and its limitations.
    print("[the skinny] Loading the real backtested margin/spread model...")
    forecast_history = deltas_mod.load_forecast_history()
    newly_backfilled = deltas_mod.backfill_forecast_history(
        forecast_history, stat_history, stats_lookup,
        cws.compute_forecast_factors, cws.compute_home_field_adv,
    )
    if newly_backfilled:
        print(f"[the skinny] -> Backfilled {newly_backfilled} completed game(s) into the real "
              f"margin-forecast history ({len(forecast_history['games'])} total on record).")
    fitted_margin_model = deltas_mod.tune_forecast_weights(forecast_history)
    if fitted_margin_model:
        print(f"[the skinny] -> Margin model: real OLS fit on {fitted_margin_model['n']} game(s), "
              f"R²={fitted_margin_model['r2']:.3f}, MAE={fitted_margin_model['mae']:.1f} pts (in-sample).")
    else:
        print(f"[the skinny] -> Margin model: only {len(forecast_history['games'])} complete real game(s) "
              f"on record (need {deltas_mod.MIN_MARGIN_SAMPLES}) -- using the original hand-picked weights.")

    # FBS names (TeamRankings list) so the home/road splits count FBS-vs-FBS games only
    _fbs_names = None
    try:
        _fn = list(stats_lookup['Clean_Name'].dropna().unique()) if 'Clean_Name' in stats_lookup.columns else list(stats_lookup.index)
        _fbs_names = _fn if len(_fn) >= 100 else None      # too short a list = something is off; don't filter on it
    except Exception:
        _fbs_names = None

    # Home / road split stats (rush, pass, points, points allowed per game) -- cfb_home_away_splits.py, never fatal
    splits = {}
    try:
        import cfb_home_away_splits as _hs
        splits = _hs.get_splits(season_year, _fbs_names)
    except Exception as _e:
        print(f"[the skinny] home/road splits skipped ({_e})")

    # Full home / road OFFENSE-vs-DEFENSE stat grid data (cfb_split_grid.py, 2026-10-07) -- never fatal
    split_grid = {}
    try:
        import cfb_split_grid as _sg
        split_grid = _sg.get_grid(season_year, _fbs_names)
    except Exception as _e:
        print(f"[the skinny] home/road offense-vs-defense grid skipped ({_e})")

    return {
        "split_grid": split_grid,
        "splits": splits,
        "schedule_df": schedule_df,
        "stats_lookup": stats_lookup,
        "included_stats": included_stats,
        "sacks_agreement": sacks_agreement,
        "raw_win_rates": raw_win_rates,
        "fitted_margin_model": fitted_margin_model,
    }


# ==========================================
# FORMATTING HELPERS -- thin wrappers around cws.'s own tested formatters,
# plus the one extra decimal-precision rule (3 decimals under 10, else 1)
# already used for F+/FEI/stuff-rate style stats elsewhere in that file.
# ==========================================
def _fmt(val, key):
    if cws._is_missing(val):
        return "--"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "--"
    if key in ("F+", "OF+", "DF+", "FEI", "OFEI", "DFEI", "Off_Stuff_Rate", "Def_Stuff_Rate"):
        return f"{v:.3f}" if abs(v) < 10 else f"{v:.1f}"
    if key in ("Net_TO_Margin",):
        return cws._fmt_signed(v)
    return f"{v:.1f}"


def _fmt_sor(val):
    """Real ESPN Strength of Record for one team. Unverified formatting
    pending a live run (see the SOR candidate-list comment in
    cfb_working_schedule.py's fetch_espn_power_index) -- ESPN's own SOS
    field on this same endpoint is rank-only, not a raw score, so SOR is
    shown as a rank ('#12') by default; if a live run shows it's actually
    a raw decimal instead, this is the one place to change."""
    if cws._is_missing(val):
        return "--"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "--"
    return f"#{int(round(v))}"


def _pass_rush_identity(ts):
    """Real, computed play-calling identity -- pass plays vs rush plays,
    self-normalized to the two real numbers we have (not assumed against
    a third 'total plays' field that may count things differently).
    Returns (pass_pct, rush_pct) or (None, None) if either count is
    missing."""
    pass_plays = cws._num(ts.get('Off_Pass_Plays_PG')) if hasattr(ts, 'get') else None
    rush_plays = cws._num(ts.get('Off_Rush_Plays_PG')) if hasattr(ts, 'get') else None
    if pass_plays is None or rush_plays is None or (pass_plays + rush_plays) == 0:
        return None, None
    total = pass_plays + rush_plays
    return (pass_plays / total * 100.0, rush_plays / total * 100.0)


# ==========================================
# PDF BUILD -- one plain black-and-white page per game.
# ==========================================
# Always shown, regardless of how predictive they are on their own --
# these are here to show what KIND of team each side is (trench identity),
# not because they rank at the top of the win-rate list.
_STUFF_RATE_ROWS = [
    ("Off Stuff Rate (suffered)", "Off_Stuff_Rate", False),
    ("Def Stuff Rate (forced)", "Def_Stuff_Rate", True),
]

# These 3 always show and always get the green
# highlight treatment (regardless of where they'd otherwise rank in the
# dynamic win-rate list below) -- F+/FEI are bcftoys' own overall team
# ratings, Def Sacks/Game is the same real trench stat cfb_working_schedule.py
# already flags in orange when it disagrees with the model's pick.
_HEADLINE_STAT_ROWS = [
    ("F+", "F+", True),
    ("FEI", "FEI", True),
    ("Def Sacks/Game", "Def_Sacks_PG", True),
]
_HEADLINE_STAT_KEYS = {key for _label, key, _hib in _HEADLINE_STAT_ROWS}
_HIGHLIGHT_GREEN = colors.HexColor("#A8E6A3")
_HIGHLIGHT_YELLOW = "#FFF176"
_COMPACT = True      # tightened layout so a whole game fits on ONE page
_GAMES_PER_PAGE = 1  # 1 = stacked, full width, one game per page; 2 = side-by-side columns, two games per page
_ONE = (_GAMES_PER_PAGE == 1)   # one game per page -> a little more room, so slightly bigger type

# dark mode switch + palette (see the dark-mode helpers above generate_the_skinny_pdf)
_DARK_MODE = True
_PAGE_BG = "#0F131A"
_PANEL_BG = "#171C26"
_TEXT = "#EEF1F6" if _DARK_MODE else "#000000"
_MUTED = "#A7B0C0" if _DARK_MODE else "#555555"
_SUBTEXT = "#D3D8E2" if _DARK_MODE else "#333333"
_HDR_MAP = {"0xdddddd": "#2D3646", "0xeeeeee": "#222A38", "0x888888": "#4A5366"}

# How many of the real highest-win-rate stats to show in "THE STATS THAT
# MATTER" below. Real backtested number, recomputed fresh every run from
# cfb_stat_history.json (via cws._individual_stat_win_rates) -- this is
# not a fixed/guessed list of "the good stats," it's whichever stats
# actually rank highest THIS run, in order.
_TOP_STATS_COUNT = 15


def _top_stats_by_win_rate(raw_win_rates, top_n=_TOP_STATS_COUNT, exclude_keys=frozenset()):
    """Ranks every real, currently-tracked stat (cws._STAT_SIGNAL_SPECS)
    by its real win-rate-when-better from cws._individual_stat_win_rates,
    highest first, and returns the top `top_n` as
    (label, key, higher_is_better, win_rate, n) tuples. A stat only shows
    up here if it has real recorded votes (>=3 games) AND a known
    higher_is_better direction -- nothing guessed or hardcoded. Pass
    exclude_keys to skip stats already shown elsewhere (the fixed
    F+/FEI/Def Sacks headline trio shouldn't also show up a second time
    in this dynamic list)."""
    label_by_key = {key: label for label, key, _ in cws._STAT_SIGNAL_SPECS}
    ranked = sorted(raw_win_rates.items(), key=lambda kv: kv[1][0], reverse=True)
    specs = []
    for key, (win_rate, n) in ranked:
        if key in exclude_keys:
            continue
        hib = cws._HIGHER_IS_BETTER_BY_KEY.get(key)
        if hib is None:
            continue
        specs.append((label_by_key.get(key, key), key, hib, win_rate, n))
        if len(specs) >= top_n:
            break
    return specs


def _stat_row_data(away_ts, home_ts, label, key, higher_is_better):
    av = away_ts.get(key) if hasattr(away_ts, 'get') else None
    hv = home_ts.get(key) if hasattr(home_ts, 'get') else None
    lean = cws._live_stat_lean(av, hv, higher_is_better)  # +1 away better, -1 home better, None tie/missing
    return _fmt(av, key), label, _fmt(hv, key), lean


def _section_table(away_ts, home_ts, rows_spec, col_widths, body_style, label_style, highlight_keys=frozenset()):
    header = [Paragraph("AWAY", label_style), Paragraph("STAT", label_style), Paragraph("HOME", label_style)]
    data = [header]
    box_cmds = []
    for row_i, (label, key, higher_is_better) in enumerate(rows_spec, start=1):
        av_disp, label_disp, hv_disp, lean = _stat_row_data(away_ts, home_ts, label, key, higher_is_better)
        data.append([Paragraph(av_disp, body_style), Paragraph(label_disp, body_style), Paragraph(hv_disp, body_style)])
        col = 0 if lean == 1 else (2 if lean == -1 else None)
        if col is not None:
            if key in highlight_keys:
                # A real edge on one of the headline
                # stats (F+/FEI/Def Sacks/Game, or the next 2 highest real
                # win-rate stats) gets a green fill instead of just a box,
                # so it stands out from the rest of the sheet.
                box_cmds.append(('BACKGROUND', (col, row_i), (col, row_i), _HIGHLIGHT_GREEN))
            else:
                box_cmds.append(('BOX', (col, row_i), (col, row_i), 1.6, colors.black))
            box_cmds.append(('FONTNAME', (col, row_i), (col, row_i), 'Helvetica-Bold'))
    t = Table(data, colWidths=col_widths)
    style = [
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#888888')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#DDDDDD')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ] + box_cmds
    t.setStyle(TableStyle(style))
    return t


def _records_table(row, col_widths, body_style, label_style, splits=None, away=None, home=None):
    """Overall / conference / home / road records (ESPN scoreboard) and, under the home and road records, that team's
    per-game rush yds / pass yds / points scored / points allowed in those games (CFBD, cfb_home_away_splits.py)."""
    import cfb_home_away_splits as _hs
    def _g(col):
        try:
            v = row.get(col, "--")
        except Exception:
            v = "--"
        return "--" if v is None or (isinstance(v, float) and v != v) else str(v)
    small = ParagraphStyle('SkinnyRecSmall', parent=body_style, fontSize=((7.4 if _ONE else 6.8) if _COMPACT else 7.8), leading=((8.8 if _ONE else 8.2) if _COMPACT else 9.4))
    small_lbl = ParagraphStyle('SkinnyRecLbl', parent=body_style, fontSize=6.8, leading=8, textColor=colors.HexColor(_MUTED))
    a_sp = _hs.lookup(splits, away) if (splits and away) else None
    h_sp = _hs.lookup(splits, home) if (splits and home) else None

    def _rec_cell(rec, side_key, sp):
        off, dfn = _hs.fmt_side((sp or {}).get(side_key))
        n = ((sp or {}).get(side_key) or {}).get("n")
        gtxt = ""      # season-average mode: the split game count no longer applies to the home/road record cells
        return Paragraph(f"<b>{rec}</b>{gtxt}", small)      # the per-game OFF/DEF numbers moved to the heat-map grid below (2026-10-07)

    data = [[Paragraph("AWAY", label_style), Paragraph("RECORD", label_style), Paragraph("HOME", label_style)]]
    for label, a_col, h_col in (("Overall", "Away_Record", "Home_Record"),
                                ("Conference", "Away_Conf_Record", "Home_Conf_Record")):
        data.append([Paragraph(_g(a_col), body_style), Paragraph(label, body_style), Paragraph(_g(h_col), body_style)])
    center = lambda t: Paragraph(t, body_style)
    data.append([_rec_cell(_g("Away_Home_Record"), "home", a_sp), center("Home"),
                 _rec_cell(_g("Home_Home_Record"), "home", h_sp)])
    data.append([_rec_cell(_g("Away_Road_Record"), "away", a_sp), center("Road"),
                 _rec_cell(_g("Home_Road_Record"), "away", h_sp)])
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#888888')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#DDDDDD')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ]))
    return t


def _heat(p):
    """Heat-map color. p in [0, 1]: 0 = best (green) -> 0.5 = yellow -> 1 = worst (red)."""
    p = max(0.0, min(1.0, float(p)))
    if p <= 0.10:                      # top 10% in the country -> purple
        return "#B15CFF"
    g, y, r = (0x00, 0xD0, 0x4F), (0xFF, 0xE0, 0x00), (0xFF, 0x2D, 0x2D)   # vibrant: saturated green -> yellow -> red
    a, b, t = (g, y, p * 2) if p < 0.5 else (y, r, (p - 0.5) * 2)
    return "#%02X%02X%02X" % tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3))


_HEAT_NOTE = ParagraphStyle('SkinnyHeatNote', fontName='Helvetica-Oblique', fontSize=6.8, leading=8.2,
                            textColor=colors.HexColor(_MUTED), spaceBefore=2)

_RANK_PAIRS = [("RUSH", "Off_Rush_PG", "Def_Rush_PG"), ("PASS", "Off_Pass_PG", "Def_Pass_PG")]


def _rank_table(away, home, away_ts, home_ts, rank_lookup, col_widths, body_style, label_style):
    """OFFENSE vs DEFENSE, ranks only (FBS rank by yards per game; defense = yards allowed, #1 = stingiest). Two blocks:
    away offense vs home defense, home offense vs away defense, rush and pass. Heat map: each rank colored green (elite) to
    red (poor); EDGE = how many rank spots the offense is ahead of (OFF +) or behind (DEF +) the defense it faces."""
    tot = float(sum(col_widths))
    widths = [tot * 0.27, tot * 0.14, tot * 0.27, tot * 0.32]
    _ranks = [x for v in rank_lookup.values() if v for x in v.values() if isinstance(x, (int, float)) and x == x]
    n_teams = int(max(_ranks)) if _ranks else 136
    body_style = ParagraphStyle('SkinnyRankCtr', parent=body_style, alignment=TA_CENTER)
    data, cmds = [], []

    def _rk(team, key):
        return rank_lookup.get(key, {}).get(team)

    def _block(off_team, def_team):
        r0 = len(data)
        data.append([Paragraph(f"<b>{off_team.upper()} OFFENSE</b> &nbsp;vs&nbsp; <b>{def_team.upper()} DEFENSE</b>", label_style), "", "", ""])
        cmds.extend([('SPAN', (0, r0), (-1, r0)), ('BACKGROUND', (0, r0), (-1, r0), colors.HexColor('#DDDDDD'))])
        for lab, ok, dk in _RANK_PAIRS:
            o, d = _rk(off_team, ok), _rk(def_team, dk)
            r = len(data)
            if o is None or d is None:
                data.append([Paragraph("--" if o is None else f"#{o}", body_style), Paragraph(lab, body_style),
                             Paragraph("--" if d is None else f"#{d}", body_style), Paragraph("--", body_style)])
                continue
            gap = d - o                                  # >0: the offense out-ranks the defense it faces
            edge = "even" if gap == 0 else (f"OFF +{gap}" if gap > 0 else f"DEF +{-gap}")
            data.append([Paragraph(f"#{o}", body_style), Paragraph(lab, body_style), Paragraph(f"#{d}", body_style),
                         Paragraph(edge, body_style)])
            cmds.append(('BACKGROUND', (0, r), (0, r), colors.HexColor(_heat((o - 1) / max(1, n_teams - 1)))))
            cmds.append(('BACKGROUND', (2, r), (2, r), colors.HexColor(_heat((d - 1) / max(1, n_teams - 1)))))
            cmds.append(('BACKGROUND', (3, r), (3, r), colors.HexColor(_heat(0.5 - gap / 140.0))))
            if gap != 0:
                col = 0 if gap > 0 else 2
                cmds.append(('BOX', (col, r), (col, r), 1.6, colors.black))
                cmds.append(('FONTNAME', (col, r), (col, r), 'Helvetica-Bold'))

    _block(away, home)
    _block(home, away)
    t = Table(data, colWidths=widths)
    t.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#888888')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ] + cmds))
    return t


def _split_pool(splits, side, key):
    return sorted(v[side][key] for v in (splits or {}).values()
                  if isinstance(v, dict) and v.get(side) and v[side].get("n", 0) >= 1 and v[side].get(key) is not None)


def _heat_vs_pool(pool, val, higher_is_better):
    """Share of teams with a better value than this one (0 = best in the country -> green). None if the pool is too small."""
    if val is None or len(pool) < 8:
        return None
    better = sum(1 for x in pool if (x > val if higher_is_better else x < val))
    return better / (len(pool) - 1)


def _splits_grid(away, home, splits, col_widths, body_style, label_style):
    """Home / road split grid, OFFENSE vs DEFENSE: the away team's ROAD offense against the home team's HOME defense (per game rush yds,
    pass yds, points), and the home team's HOME offense against the away team's ROAD defense, with EXPECTED = the average of the two.
    Heat map: each number is colored by where it ranks among all teams in that same spot (green = best for that unit; for EXPECTED,
    green = a big number for the offense)."""
    import cfb_home_away_splits as _hs
    a_sp = _hs.lookup(splits, away) if splits else None
    h_sp = _hs.lookup(splits, home) if splits else None
    tot = float(sum(col_widths))
    widths = [tot * 0.40, tot * 0.20, tot * 0.20, tot * 0.20]
    data = [[Paragraph("", label_style), Paragraph("RUSH YDS/G", label_style), Paragraph("PASS YDS/G", label_style), Paragraph("POINTS/G", label_style)]]
    cmds = [('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#DDDDDD'))]
    f = lambda v: "--" if v is None else f"{v:.1f}"
    ctr = ParagraphStyle('SkinnyGridCtr', parent=body_style, alignment=TA_CENTER)

    def _block(off_team, off_sp, off_side, def_team, def_sp, def_side, off_word, def_word):
        o = (off_sp or {}).get(off_side) or {}
        d = (def_sp or {}).get(def_side) or {}
        r0 = len(data)
        data.append([Paragraph(f"<b>{off_team.upper()} OFFENSE</b> ({off_word}, {o.get('n', 0)} g) &nbsp;vs&nbsp; "
                               f"<b>{def_team.upper()} DEFENSE</b> ({def_word}, {d.get('n', 0)} g)", label_style), "", "", ""])
        cmds.extend([('SPAN', (0, r0), (-1, r0)), ('BACKGROUND', (0, r0), (-1, r0), colors.HexColor('#EEEEEE'))])
        okeys, dkeys = ("rush", "pass", "pts"), ("rush_allowed", "pass_allowed", "allowed")
        r1 = len(data)
        data.append([Paragraph(f"{off_team} offense, {off_word}", body_style)] + [Paragraph(f(o.get(k)), ctr) for k in okeys])
        r2 = len(data)
        data.append([Paragraph(f"{def_team} defense, {def_word} (allowed)", body_style)] + [Paragraph(f(d.get(k)), ctr) for k in dkeys])
        r3 = len(data)
        exp = []
        for k_o, k_d in zip(okeys, dkeys):
            exp.append(None if o.get(k_o) is None or d.get(k_d) is None else (o[k_o] + d[k_d]) / 2.0)
        data.append([Paragraph("<b>EXPECTED</b> (average of the two)", body_style)] +
                    [Paragraph("--" if g is None else f"<b>{g:.1f}</b>", ctr) for g in exp])
        for ci, (k_o, k_d) in enumerate(zip(okeys, dkeys), start=1):
            po = _heat_vs_pool(_split_pool(splits, off_side, k_o), o.get(k_o), True)
            pd_ = _heat_vs_pool(_split_pool(splits, def_side, k_d), d.get(k_d), False)
            if po is not None:
                cmds.append(('BACKGROUND', (ci, r1), (ci, r1), colors.HexColor(_heat(po))))
            if pd_ is not None:
                cmds.append(('BACKGROUND', (ci, r2), (ci, r2), colors.HexColor(_heat(pd_))))
            pe = _heat_vs_pool(_split_pool(splits, off_side, k_o), exp[ci - 1], True)
            if pe is not None:
                cmds.append(('BACKGROUND', (ci, r3), (ci, r3), colors.HexColor(_heat(pe))))

    _block(away, a_sp, "away", home, h_sp, "home", "on the road", "at home")
    _block(home, h_sp, "home", away, a_sp, "away", "at home", "on the road")
    t = Table(data, colWidths=widths)
    t.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#888888')),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ] + cmds))
    return t


def _split_grid_table(away, home, grid, total_width, body_style, label_style, fbs_teams=None):
    """Full home/road grid, RANKS ONLY: [STAT | away OFF (road) | home DEF (home) | EDGE | home OFF (home) | away DEF (road) | EDGE].
    Rank = place among FBS teams in that same spot (home games only / road games only), 1 = best; heat-mapped green (elite) to red (poor).
    EDGE = rank spots the offense is ahead of (OFF +) or behind (DEF +) the defense it faces."""
    import cfb_split_grid as _sg
    a_g, h_g = _sg.lookup(grid, away), _sg.lookup(grid, home)
    a_road, h_home = (a_g or {}).get("away") or {}, (h_g or {}).get("home") or {}
    ctr = ParagraphStyle('SkinnyGrid7Ctr', parent=body_style, alignment=TA_CENTER, fontSize=8, leading=9.5)
    lft = ParagraphStyle('SkinnyGrid7Lft', parent=body_style, fontSize=7.6, leading=9)
    hdr = ParagraphStyle('SkinnyGrid7Hdr', parent=label_style, alignment=TA_CENTER, fontSize=7.4, leading=8.8)
    w0 = total_width * 0.25
    wr = (total_width - w0) / 6.0
    widths = [w0] + [wr] * 6
    ng = lambda d: d.get("n", 0)
    data = [[Paragraph("", hdr),
             Paragraph(f"<b>{away.upper()} OFFENSE</b> (season, {ng(a_road)} g) vs <b>{home.upper()} DEFENSE</b> (season, {ng(h_home)} g)", hdr), "", "",
             Paragraph(f"<b>{home.upper()} OFFENSE</b> (season, {ng(h_home)} g) vs <b>{away.upper()} DEFENSE</b> (season, {ng(a_road)} g)", hdr), "", ""],
            [Paragraph("STAT (rank)", hdr)] + [Paragraph(t, hdr) for t in ("OFF", "DEF", "EDGE", "OFF", "DEF", "EDGE")]]
    cmds = [('SPAN', (1, 0), (3, 0)), ('SPAN', (4, 0), (6, 0)),
            ('BACKGROUND', (0, 0), (-1, 1), colors.HexColor('#DDDDDD')),
            ('LINEAFTER', (3, 0), (3, -1), 1.4, colors.black)]
    for key, label, off_hi, dec in _sg.METRICS:
        row, any_val = [Paragraph(label, lft)], False
        r = len(data)
        for ci0, (off_blk, off_side, def_blk, def_side) in enumerate(((a_road, "away", h_home, "home"), (h_home, "home", a_road, "away"))):
            ov = (off_blk.get("off") or {}).get(key)
            dv = (def_blk.get("def") or {}).get(key)
            ro, no = _sg.rank_of(_sg.ranked_pool(grid, off_side, "off", key, fbs_teams), ov, off_hi)
            rd, nd = _sg.rank_of(_sg.ranked_pool(grid, def_side, "def", key, fbs_teams), dv, not off_hi)   # defense is better when it holds the offense stat DOWN (or forces it UP)
            any_val = any_val or ro is not None or rd is not None
            c0 = 1 + ci0 * 3
            row += [Paragraph("--" if ro is None else f"#{ro}", ctr), Paragraph("--" if rd is None else f"#{rd}", ctr)]
            if ro is not None:
                cmds.append(('BACKGROUND', (c0, r), (c0, r), colors.HexColor(_heat((ro - 1) / max(1, no - 1)))))
            if rd is not None:
                cmds.append(('BACKGROUND', (c0 + 1, r), (c0 + 1, r), colors.HexColor(_heat((rd - 1) / max(1, nd - 1)))))
            if ro is not None and rd is not None:
                gap = rd - ro                                   # >0: the offense out-ranks the defense it faces
                row.append(Paragraph("even" if gap == 0 else (f"OFF +{gap}" if gap > 0 else f"DEF +{-gap}"), ctr))
                cmds.append(('BACKGROUND', (c0 + 2, r), (c0 + 2, r), colors.HexColor(_heat(0.5 - gap / 140.0))))
            else:
                row.append(Paragraph("--", ctr))
        if any_val:
            data.append(row)
    t = Table(data, colWidths=widths, repeatRows=2)
    t.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#888888')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ] + cmds))
    return t


def _edge_cell(gap, scale=60.0):
    """gap = defense rank - offense rank (>0: the OFFENSE out-ranks the defense it faces). -> (text, background hex or None, 'off'/'def'/None).
    The edge cell is white-to-green by SIZE of the gap no matter who has it (the text and the bold box on the winning cell say who);
    red is reserved for poor ranks, so a defensive edge no longer shows up red (2026-10-07)."""
    if gap is None:
        return "--", None, None
    if abs(gap) < 5:
        return "even", None, None
    t = min(1.0, abs(gap) / float(scale))
    g = (0x63, 0xBE, 0x7B)
    hx = "#%02X%02X%02X" % tuple(int(255 + (g[k] - 255) * t) for k in range(3))
    return (f"OFF +{gap}" if gap > 0 else f"DEF +{-gap}"), hx, ("off" if gap > 0 else "def")


_SHOW_EDGE = False     # 2026-10-07: backtest (85 games, wk 4-5) showed bigger off-rank-vs-def-rank gaps do NOT win more often, so the EDGE column is off. Set True to bring it (and its boxes) back.


def _rank_block(off_team, def_team, rank_lookup, col_widths, body_style, label_style):
    """ONE block: {off_team} OFFENSE rank vs {def_team} DEFENSE rank, rush and pass (FBS rank by yards per game, #1 = best). Heat-mapped ranks."""
    tot = float(sum(col_widths))
    ncol = 4 if _SHOW_EDGE else 3
    widths = ([tot * 0.27, tot * 0.16, tot * 0.27, tot * 0.30] if _SHOW_EDGE else [tot * 0.34, tot * 0.32, tot * 0.34])
    ctr = ParagraphStyle('SkinnyRankCtr2', parent=body_style, alignment=TA_CENTER)
    hdr = ParagraphStyle('SkinnyRankHdr2', parent=label_style, alignment=TA_CENTER)
    n_all = [x for v in rank_lookup.values() if v for x in v.values() if isinstance(x, (int, float)) and x == x]
    n_teams = int(max(n_all)) if n_all else 136
    pad = [""] * (ncol - 1)
    data = [[Paragraph(f"<b>{off_team.upper()} OFFENSE</b> rank &nbsp;vs&nbsp; <b>{def_team.upper()} DEFENSE</b> rank", hdr)] + pad,
            [Paragraph("OFF RANK", hdr), Paragraph("", hdr), Paragraph("DEF RANK", hdr)] + ([Paragraph("EDGE", hdr)] if _SHOW_EDGE else [])]
    cmds = [('SPAN', (0, 0), (-1, 0)), ('BACKGROUND', (0, 0), (-1, 1), colors.HexColor('#DDDDDD'))]
    for lab, ok, dk in _RANK_PAIRS:
        o, d = rank_lookup.get(ok, {}).get(off_team), rank_lookup.get(dk, {}).get(def_team)
        r = len(data)
        if o is None or d is None:
            data.append([Paragraph("--" if o is None else f"#{o}", ctr), Paragraph(lab, ctr), Paragraph("--" if d is None else f"#{d}", ctr)] + ([Paragraph("--", ctr)] if _SHOW_EDGE else []))
            continue
        txt, bg, win = _edge_cell(d - o)
        data.append([Paragraph(f"#{o}", ctr), Paragraph(lab, ctr), Paragraph(f"#{d}", ctr)] + ([Paragraph(txt, ctr)] if _SHOW_EDGE else []))
        cmds.append(('BACKGROUND', (0, r), (0, r), colors.HexColor(_heat((o - 1) / max(1, n_teams - 1)))))
        cmds.append(('BACKGROUND', (2, r), (2, r), colors.HexColor(_heat((d - 1) / max(1, n_teams - 1)))))
        if _SHOW_EDGE:
            if bg:
                cmds.append(('BACKGROUND', (3, r), (3, r), colors.HexColor(bg)))
            if win:
                col = 0 if win == "off" else 2
                cmds.append(('BOX', (col, r), (col, r), 1.6, colors.black))
                cmds.append(('FONTNAME', (col, r), (col, r), 'Helvetica-Bold'))
    t = Table(data, colWidths=widths)
    t.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#888888')), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                           ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)] + cmds))
    return t


def _stat_block(off_team, off_side, def_team, def_side, grid, total_width, body_style, label_style, fbs_teams=None):
    """ONE block of the home/road stat grid, RANKS ONLY: [STAT | OFF | DEF] for {off_team}'s offense in its {off_side} games vs {def_team}'s
    defense in its {def_side} games. Rank = place among FBS teams in that same spot, 1 = best for that unit. Heat-mapped."""
    import cfb_split_grid as _sg
    o_g, d_g = _sg.lookup(grid, off_team), _sg.lookup(grid, def_team)
    o_blk, d_blk = (o_g or {}).get(off_side) or {}, (d_g or {}).get(def_side) or {}
    ctr = ParagraphStyle('SkinnyGrid7Ctr', parent=body_style, alignment=TA_CENTER, fontSize=((7.4 if _ONE else 6.8) if _COMPACT else 8), leading=((8.8 if _ONE else 7.8) if _COMPACT else 9.5))
    lft = ParagraphStyle('SkinnyGrid7Lft', parent=body_style, fontSize=((7.2 if _ONE else 6.6) if _COMPACT else 7.8), leading=((8.8 if _ONE else 7.8) if _COMPACT else 9.2))
    hdr = ParagraphStyle('SkinnyGrid7Hdr', parent=label_style, alignment=TA_CENTER, fontSize=((7.0 if _ONE else 6.4) if _COMPACT else 7.6), leading=((8.4 if _ONE else 7.6) if _COMPACT else 9))
    ncol = 4 if _SHOW_EDGE else 3
    widths = ([total_width * 0.34, total_width * 0.17, total_width * 0.17, total_width * 0.32] if _SHOW_EDGE
              else [total_width * 0.44, total_width * 0.28, total_width * 0.28])
    wd = {"away": "season", "home": "season"}
    _title = (f"<b>{off_team.upper()} OFF</b> ({wd[off_side]}, {o_blk.get('n', 0)} g) &nbsp;vs&nbsp; "
              f"<b>{def_team.upper()} DEF</b> ({wd[def_side]}, {d_blk.get('n', 0)} g)") if _COMPACT else (
              f"<b>{off_team.upper()} STATS</b> ({wd[off_side]}, {o_blk.get('n', 0)} g) &nbsp;vs&nbsp; "
              f"<b>{def_team.upper()} DEFENSE</b> ({wd[def_side]}, {d_blk.get('n', 0)} g) -- ranks")
    data = [[Paragraph(_title, hdr)] + [""] * (ncol - 1),
            [Paragraph("STAT", hdr), Paragraph("OFF", hdr), Paragraph("DEF", hdr)] + ([Paragraph("EDGE", hdr)] if _SHOW_EDGE else [])]
    cmds = [('SPAN', (0, 0), (-1, 0)), ('BACKGROUND', (0, 0), (-1, 1), colors.HexColor('#DDDDDD'))]
    for key, label, off_hi, dec in _sg.METRICS:
        ov, dv = (o_blk.get("off") or {}).get(key), (d_blk.get("def") or {}).get(key)
        ro, no = _sg.rank_of(_sg.ranked_pool(grid, off_side, "off", key, fbs_teams), ov, off_hi)
        rd, nd = _sg.rank_of(_sg.ranked_pool(grid, def_side, "def", key, fbs_teams), dv, not off_hi)   # defense is better when it holds the offense stat DOWN (or forces it UP)
        if ro is None and rd is None:
            continue
        r = len(data)
        txt, bg, win = _edge_cell(None if (ro is None or rd is None) else rd - ro)
        data.append([Paragraph(label, lft), Paragraph("--" if ro is None else f"#{ro}", ctr), Paragraph("--" if rd is None else f"#{rd}", ctr)]
                    + ([Paragraph(txt, ctr)] if _SHOW_EDGE else []))
        if ro is not None:
            cmds.append(('BACKGROUND', (1, r), (1, r), colors.HexColor(_heat((ro - 1) / max(1, no - 1)))))
        if rd is not None:
            cmds.append(('BACKGROUND', (2, r), (2, r), colors.HexColor(_heat((rd - 1) / max(1, nd - 1)))))
        if _SHOW_EDGE:
            if bg:
                cmds.append(('BACKGROUND', (3, r), (3, r), colors.HexColor(bg)))
            if win:
                col = 1 if win == "off" else 2
                cmds.append(('BOX', (col, r), (col, r), 1.4, colors.black))
                cmds.append(('FONTNAME', (col, r), (col, r), 'Helvetica-Bold'))
    t = Table(data, colWidths=widths, repeatRows=2)
    t.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#888888')), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                           ('TOPPADDING', (0, 0), (-1, -1), ((1.3 if _ONE else 1.0) if _COMPACT else 2.2)), ('BOTTOMPADDING', (0, 0), (-1, -1), ((1.3 if _ONE else 1.0) if _COMPACT else 2.2))] + cmds))
    return t


def _trench_lean(away_ts, home_ts):
    """Combined lean across the 4 real trench stats (stuff rate x2, sacks
    x2), majority-vote style -- same _live_stat_lean building block the
    model itself uses, just summed instead of weighted, since this is a
    plain-language 'who wins the line of scrimmage' read, not the model's
    own pick."""
    keys = [("Off_Stuff_Rate", False), ("Def_Stuff_Rate", True),
            ("Off_Sacks_Allowed_PG", False), ("Def_Sacks_PG", True)]
    score = 0
    votes = 0
    for key, hib in keys:
        av = away_ts.get(key) if hasattr(away_ts, 'get') else None
        hv = home_ts.get(key) if hasattr(home_ts, 'get') else None
        lean = cws._live_stat_lean(av, hv, hib)
        if lean is not None:
            score += lean
            votes += 1
    if votes == 0:
        return None
    if score > 0:
        return "away"
    if score < 0:
        return "home"
    return None


def _build_commentary(away, home, away_ts, home_ts, included_stats, sacks_agreement, top_specs, fitted_margin_model=None):
    sentences = []

    forecast = cws.build_matchup_forecast(away, home, away_ts, home_ts, fitted_margin_model=fitted_margin_model)

    # ---- Trenches lead-in, grounded in the real stuff-rate/sack numbers
    # above (not the score -- this is specifically an O-line/D-line read).
    trench_side = _trench_lean(away_ts, home_ts)
    trench_team = away if trench_side == "away" else (home if trench_side == "home" else None)
    if trench_team:
        sentences.append(
            f"Up front, {trench_team} wins the line of scrimmage on our stuff-rate and sack numbers above -- "
            f"expect this one to be a smash-mouth, grind-it-out fight, yards coming in small chunks between the tackles."
        )
    else:
        sentences.append(
            "Up front, the stuff-rate and sack numbers are close to even -- this one likely comes down to "
            "who wins on the perimeter instead of at the line of scrimmage."
        )

    # ---- The real backtested headline stat: whichever stat ACTUALLY
    # shown in "THE STATS THAT MATTER" table above has the highest real
    # win-rate AND a real live edge in THIS specific matchup -- so the
    # commentary never cites a stat the reader can't also see on the page.
    best_call = None  # (label, team, win_rate, n)
    for label, key, hib, win_rate, n in top_specs:
        av = away_ts.get(key) if hasattr(away_ts, 'get') else None
        hv = home_ts.get(key) if hasattr(home_ts, 'get') else None
        lean = cws._live_stat_lean(av, hv, hib)
        if lean is None:
            continue
        team = away if lean == 1 else home
        best_call = (label, team, win_rate, n)
        break  # top_specs is already sorted highest win-rate first
    if best_call:
        label, team, win_rate, n = best_call
        sentences.append(
            f"The clearest real edge on the sheet is {label}, which favors {team} -- in our own "
            f"{n} logged games, the team with the better {label} has won {win_rate*100:.0f}% of the time."
        )

    # ---- The model's actual prediction (reuses cws.build_matchup_forecast
    # verbatim -- same projected score, win probability, and rushing/
    # passing-edge reasoning the main report uses).
    weights_note = None
    if forecast:
        sentences.append(forecast["narrative"])
        weights_note = forecast.get("weights_note")
        # Real, direct answer to "everything favors
        # one team but it picks the other" -- if this team's home-field
        # rating is what flipped the pick (the raw stat blend alone
        # actually favored the OTHER team), say so explicitly and
        # highlight it, same treatment as the other caution flags.
        if forecast.get("hfa_flipped_pick"):
            stat_team = forecast.get("stat_favored_team")
            sentences.append(
                f"<font color='#111111' backColor='{_HIGHLIGHT_YELLOW}'><b>Caution: without {home}'s "
                f"{forecast['hfa_used']:+.1f}-point home-field edge, the underlying stat blend alone "
                f"actually favors {stat_team}.</b></font>"
            )
    else:
        sentences.append("No score projection this week -- one side is missing real Points/Game data.")

    # ---- The real sack-vs-model-pick caution flag, same tested logic
    # cfb_working_schedule.py's own PDF flags in orange for.
    weights_by_key = {key: weight for _, key, weight, _, _ in included_stats}
    included_keys = [key for _, key, _, _, _ in included_stats]
    model_pick_side = cws.stat_vote_model_pick(away_ts, home_ts, included_stats)
    if model_pick_side:
        away_sacks = away_ts.get('Def_Sacks_PG') if hasattr(away_ts, 'get') else None
        home_sacks = home_ts.get('Def_Sacks_PG') if hasattr(home_ts, 'get') else None
        sacks_lean = cws._live_stat_lean(away_sacks, home_sacks, True)
        if sacks_lean is not None:
            sacks_side = 'away' if sacks_lean == 1 else 'home'
            if sacks_side != model_pick_side:
                sacks_team = away if sacks_side == 'away' else home
                agree_hits, agree_n = sacks_agreement.get("agree", (0, 0))
                dis_hits, dis_n = sacks_agreement.get("disagree", (0, 0))
                agree_pct = (agree_hits / agree_n * 100) if agree_n else None
                dis_pct = (dis_hits / dis_n * 100) if dis_n else None
                pct_note = ""
                if agree_pct is not None and dis_pct is not None:
                    pct_note = (f" (in our logged games, the model hits {agree_pct:.1f}% when Def Sacks/Game "
                                f"agrees with its pick, {dis_pct:.1f}% when it doesn't)")
                sentences.append(
                    f"Heads up: {sacks_team} does have the better Def Sacks/Game number in this game, which "
                    f"runs against the model's own pick above{pct_note} -- be aware."
                )

    # ---- F+ / FEI vs. model-pick caution, highlighted YELLOW -- fires only when F+ AND FEI both independently favor
    # the SAME team, and that team is the OPPOSITE of the model's own
    # pick above. Both must agree with each other first, so this doesn't
    # fire on a single stat's noise -- same "real signals disagree with
    # the model" idea as the Def Sacks/Game caution above, just for
    # bcftoys' own overall team ratings instead of one trench stat.
    if model_pick_side:
        away_fplus = away_ts.get('F+') if hasattr(away_ts, 'get') else None
        home_fplus = home_ts.get('F+') if hasattr(home_ts, 'get') else None
        away_fei = away_ts.get('FEI') if hasattr(away_ts, 'get') else None
        home_fei = home_ts.get('FEI') if hasattr(home_ts, 'get') else None
        fplus_lean = cws._live_stat_lean(away_fplus, home_fplus, True)
        fei_lean = cws._live_stat_lean(away_fei, home_fei, True)
        if fplus_lean is not None and fei_lean is not None and fplus_lean == fei_lean:
            fplus_fei_side = 'away' if fplus_lean == 1 else 'home'
            if fplus_fei_side != model_pick_side:
                opp_team = away if fplus_fei_side == 'away' else home
                sentences.append(
                    f"<font color='#111111' backColor='{_HIGHLIGHT_YELLOW}'><b>Caution: both F+ and FEI favor {opp_team}, "
                    f"the opposite of the model's own pick above.</b></font>"
                )

    return " ".join(sentences), weights_note


# ---------------------------------------------------------------------------------------------------------------
# DARK MODE. Set _DARK_MODE = False for the old white page.
# Page is painted dark, plain text turns light, and any table cell sitting on a bright fill (heat map cells) keeps
# dark text so it stays readable. Done as a post-pass over the finished tables, so the heat map code is untouched.
# ---------------------------------------------------------------------------------------------------------------


def _luma(c):
    return 0.299 * c.red + 0.587 * c.green + 0.114 * c.blue


def _norm(idx, n):
    return idx + n if idx < 0 else idx


def _darkify_table(t):
    """Post-process one finished Table for the dark page."""
    from reportlab.lib import colors as _c
    import copy as _copy
    if getattr(t, "_dark_done", False):
        return
    t._dark_done = True
    nr, nc = len(t._cellvalues), len(t._cellvalues[0]) if t._cellvalues else 0
    # 1) header/grid grays -> dark slate; everything else keeps its color
    new_bg = []
    for cmd in t._bkgrndcmds:
        col = cmd[3]
        try:
            key = col.hexval().lower()
        except Exception:
            key = None
        if key in _HDR_MAP:
            cmd = (cmd[0], cmd[1], cmd[2], _c.HexColor(_HDR_MAP[key]))
        new_bg.append(cmd)
    t._bkgrndcmds = [("BACKGROUND", (0, 0), (-1, -1), _c.HexColor(_PANEL_BG))] + new_bg
    # 2) effective background of each cell (last BACKGROUND covering it wins)
    bg = [[_c.HexColor(_PANEL_BG)] * nc for _ in range(nr)]
    for cmd in new_bg:
        (c0, r0), (c1, r1) = cmd[1], cmd[2]
        c0, c1, r0, r1 = _norm(c0, nc), _norm(c1, nc), _norm(r0, nr), _norm(r1, nr)
        if not hasattr(cmd[3], "red"):
            continue
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                bg[r][c] = cmd[3]
    # 3) grid + boxes visible on dark: grid lines slate, black boxes -> white (or stay black on a bright cell)
    new_lines = []
    for cmd in t._linecmds:
        cmd = list(cmd)
        col = cmd[4]
        try:
            key = col.hexval().lower()
        except Exception:
            key = None
        if key in _HDR_MAP:
            cmd[4] = _c.HexColor(_HDR_MAP[key])
        elif key == "0x000000":
            keep_black = False
            if cmd[0] == "BOX" and tuple(cmd[1]) == tuple(cmd[2]):
                cc, rr = _norm(cmd[1][0], nc), _norm(cmd[1][1], nr)
                keep_black = _luma(bg[rr][cc]) > 0.55
            cmd[4] = _c.black if keep_black else _c.HexColor("#F4F6FA")
        new_lines.append(tuple(cmd))
    t._linecmds = new_lines
    # 4) text color per cell: dark on bright fills, light otherwise
    for r in range(nr):
        for c in range(nc):
            cell = t._cellvalues[r][c]
            if isinstance(cell, Paragraph):
                dark_text = _luma(bg[r][c]) > 0.35
                st = _copy.copy(cell.style)
                st.textColor = _c.HexColor("#0B0E14") if dark_text else _c.HexColor(_TEXT)
                t._cellvalues[r][c] = Paragraph(cell.text, st)


def _paint_page(canvas, doc):
    from reportlab.lib import colors as _c
    canvas.saveState()
    canvas.setFillColor(_c.HexColor(_PAGE_BG))
    canvas.rect(0, 0, doc.pagesize[0], doc.pagesize[1], stroke=0, fill=1)
    canvas.restoreState()


def _darkify_story(story):
    for fl in story:
        if isinstance(fl, Table):
            _darkify_table(fl)
        else:
            for sub in getattr(fl, "_content", None) or []:
                if isinstance(sub, Table):
                    _darkify_table(sub)




_LEGEND = ("Ranks only, #1 = best for that unit. Purple = top 10% nationally, green = strong, red = poor. OFF = what that offense produced; DEF = the same stat on the offenses it faced "
           "(allowed / made / forced). Stats are each team's season average vs FBS opponents only; the 'g' counts show how many games that is. "
           "Rush/pass blocks rank FBS yards per game. Red zone % is not split. Yellow highlight in THE READ = F+ and FEI both favor the team opposite the model's pick; "
           "win rates are recomputed each run from cfb_stat_history.json (see cfb_matrices_outlook.pdf).")


def _page_decor(canvas, doc):
    """Dark page fill (if dark mode) + one legend at the foot of every page (replaces the per-game notes)."""
    from reportlab.lib import colors as _c
    from reportlab.lib.utils import simpleSplit
    canvas.saveState()
    if _DARK_MODE:
        canvas.setFillColor(_c.HexColor(_PAGE_BG))
        canvas.rect(0, 0, doc.pagesize[0], doc.pagesize[1], stroke=0, fill=1)
    canvas.setFillColor(_c.HexColor(_MUTED))
    canvas.setFont("Helvetica-Oblique", 5.8)
    lines = simpleSplit(_LEGEND, "Helvetica-Oblique", 5.8, doc.pagesize[0] - 80)
    y = 8 + 7 * (len(lines) - 1)
    for ln in lines:
        canvas.drawString(40, y, ln)
        y -= 7
    canvas.restoreState()


def _tight(t, pad=1.2):
    t.setStyle(TableStyle([('TOPPADDING', (0, 0), (-1, -1), pad), ('BOTTOMPADDING', (0, 0), (-1, -1), pad)]))
    return t


def _compact_game(row, away, home, away_ts, home_ts, game_date, dataset, rank_lookup, sgrid, fbs_teams, commentary, weights_note):
    """One game sized to HALF a page: header, records, then two side-by-side columns -- LEFT = away offense vs home defense
    (rush/pass ranks, then the stat ranks), RIGHT = home offense vs away defense -- then THE READ."""
    base = ParagraphStyle('CBase', fontName='Helvetica', fontSize=(7.4 if _ONE else 6.8), leading=(8.8 if _ONE else 8.2), textColor=colors.HexColor(_TEXT))
    body = ParagraphStyle('CBody', parent=base, alignment=TA_CENTER)
    label = ParagraphStyle('CLabel', parent=base, fontName='Helvetica-Bold', alignment=TA_CENTER)
    head = ParagraphStyle('CHead', parent=base, fontName='Helvetica-Bold', fontSize=(14 if _ONE else 12), leading=(17 if _ONE else 14), alignment=TA_CENTER)
    meta = ParagraphStyle('CMeta', parent=base, alignment=TA_CENTER, textColor=colors.HexColor(_SUBTEXT))
    read = ParagraphStyle('CRead', parent=base, fontSize=(8.2 if _GAMES_PER_PAGE == 1 else 7.1), leading=(10.2 if _GAMES_PER_PAGE == 1 else 8.7), alignment=TA_LEFT)
    wnote = ParagraphStyle('CWNote', parent=base, fontName='Helvetica-Oblique', fontSize=5.8, leading=7, textColor=colors.HexColor(_MUTED), spaceBefore=2)
    ar, hr = row.get('Away_Record', '--'), row.get('Home_Record', '--')
    out = [Paragraph(f"{away.upper()} at {home.upper()}", head),
           Paragraph(f"{game_date} &nbsp;|&nbsp; {away} ({ar}) @ {home} ({hr}) &nbsp;|&nbsp; Strength of Record: {away} "
                     f"{_fmt_sor(away_ts.get('SOR') if hasattr(away_ts, 'get') else None)}, {home} "
                     f"{_fmt_sor(home_ts.get('SOR') if hasattr(home_ts, 'get') else None)}", meta)]
    ap, ar_ = _pass_rush_identity(away_ts)
    hp, hr_ = _pass_rush_identity(home_ts)
    if ap is not None and hp is not None:
        out.append(Paragraph(f"Offensive identity: {away} {ap:.0f}% pass / {ar_:.0f}% run &nbsp;|&nbsp; {home} {hp:.0f}% pass / {hr_:.0f}% run", meta))
    out.append(Spacer(1, 3))
    col_widths = [150, 210, 150]
    rec = _records_table(row, col_widths, body, label, splits=dataset.get("splits"), away=away, home=home)
    _tight(rec, 1.3 if _ONE else 1.0)
    if _DARK_MODE:
        _darkify_table(rec)
    out += [rec, Spacer(1, 4)]
    if _GAMES_PER_PAGE == 1:
        # stacked, in this order: away OFF rank vs home DEF rank, away stats vs home D, then home OFF vs away DEF, home stats vs away D
        tw = float(sum(col_widths))
        for off, off_side, dfn, def_side in ((away, "away", home, "home"), (home, "home", away, "away")):
            if rank_lookup:
                rb = _tight(_rank_block(off, dfn, rank_lookup, col_widths, body, label), 1.3)
                if _DARK_MODE:
                    _darkify_table(rb)
                out += [rb, Spacer(1, 4)]
            if sgrid:
                sb = _stat_block(off, off_side, dfn, def_side, sgrid, tw, body, label, fbs_teams=fbs_teams)
                if _DARK_MODE:
                    _darkify_table(sb)
                out += [sb, Spacer(1, 5)]
        out.append(Paragraph("<b>THE READ</b> &nbsp;" + commentary, read))
        if weights_note:
            out.append(Paragraph(weights_note, wnote))
        return out
    colw = 253.0
    cols = []
    for off, off_side, dfn, def_side in ((away, "away", home, "home"), (home, "home", away, "away")):
        items = []
        if rank_lookup:
            rb = _rank_block(off, dfn, rank_lookup, [colw / 3, colw / 3, colw / 3], body, label)
            _tight(rb, 1.0)
            items += [rb, Spacer(1, 3)]
        if sgrid:
            sb = _stat_block(off, off_side, dfn, def_side, sgrid, colw, body, label, fbs_teams=fbs_teams)
            items.append(sb)
        if _DARK_MODE:
            for it in items:
                if isinstance(it, Table):
                    _darkify_table(it)
        cols.append(items)
    two = Table([[cols[0], "", cols[1]]], colWidths=[colw, 4, colw])
    two.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                             ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
    two._dark_done = True
    out += [two, Spacer(1, 4), Paragraph("<b>THE READ</b> &nbsp;" + commentary, read)]
    if weights_note:
        out.append(Paragraph(weights_note, wnote))
    return out


def _flow_height(flowables, width=532):
    h = 0
    for f in flowables:
        try:
            h += f.wrap(width, 5000)[1] + (f.getSpaceBefore() or 0) + (f.getSpaceAfter() or 0)
        except Exception:
            pass
    return h


def generate_the_skinny_pdf(dataset, filename="generated/the_skinny.pdf"):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    schedule_df = dataset["schedule_df"]
    stats_lookup = dataset["stats_lookup"]
    included_stats = dataset["included_stats"]
    sacks_agreement = dataset["sacks_agreement"]
    raw_win_rates = dataset["raw_win_rates"]
    fitted_margin_model = dataset.get("fitted_margin_model")

    doc = SimpleDocTemplate(
        filename, pagesize=letter,
        rightMargin=40, leftMargin=40, topMargin=(24 if _COMPACT else 36), bottomMargin=(40 if _COMPACT else 36),
        title="The Skinny"
    )
    styles = getSampleStyleSheet()
    styles['Normal'].textColor = colors.HexColor(_TEXT)
    title_style = ParagraphStyle('SkinnyTitle', parent=styles['Normal'], fontName='Helvetica-Bold',
                                  fontSize=18, leading=22, alignment=TA_CENTER, spaceAfter=2)
    sub_style = ParagraphStyle('SkinnySub', parent=styles['Normal'], fontName='Helvetica',
                                fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.HexColor(_SUBTEXT), spaceAfter=8)
    matchup_style = ParagraphStyle('SkinnyMatchup', parent=styles['Normal'], fontName='Helvetica-Bold',
                                    fontSize=15, leading=19, alignment=TA_CENTER, spaceAfter=3)
    meta_style = ParagraphStyle('SkinnyMeta', parent=styles['Normal'], fontName='Helvetica',
                                 fontSize=9, leading=12, alignment=TA_CENTER, spaceAfter=8)
    section_style = ParagraphStyle('SkinnySection', parent=styles['Normal'], fontName='Helvetica-Bold',
                                    fontSize=10.5, alignment=TA_LEFT, spaceBefore=8, spaceAfter=3)
    body_style = ParagraphStyle('SkinnyBody', parent=styles['Normal'], fontName='Helvetica',
                                 fontSize=9, alignment=TA_CENTER, leading=11)
    label_style = ParagraphStyle('SkinnyLabel', parent=styles['Normal'], fontName='Helvetica-Bold',
                                  fontSize=8.5, alignment=TA_CENTER)
    identity_style = ParagraphStyle('SkinnyIdentity', parent=styles['Normal'], fontName='Helvetica-Oblique',
                                     fontSize=9, alignment=TA_CENTER, spaceBefore=4, spaceAfter=4)
    commentary_style = ParagraphStyle('SkinnyCommentary', parent=styles['Normal'], fontName='Helvetica',
                                       fontSize=10, alignment=TA_LEFT, leading=13.5, spaceBefore=4)
    commentary_header_style = ParagraphStyle('SkinnyCommentaryHead', parent=styles['Normal'], fontName='Helvetica-Bold',
                                              fontSize=10.5, alignment=TA_LEFT, spaceBefore=10, spaceAfter=3)

    # Dataset-wide, not per-game -- the real win-rate ranking is the same
    # for every game this run, so it's computed once here.
    top_specs = _top_stats_by_win_rate(raw_win_rates, exclude_keys=_HEADLINE_STAT_KEYS)
    # The list stops at Off Havoc Rate (suffered).
    # Trimmed here (not just in the table) so THE READ below never cites a stat that is no longer shown.
    # ...but QBR stays.
    _all_specs = _top_stats_by_win_rate(raw_win_rates, top_n=200, exclude_keys=_HEADLINE_STAT_KEYS)
    _cut = next((i for i, _s in enumerate(_all_specs) if _s[1] == "Off_Havoc"), None)
    if _cut is not None:
        top_specs = [_s for i, _s in enumerate(_all_specs) if i <= _cut or _s[1] == "QBR"]
    # Real FBS-wide ranks (same ranking the matrices report uses: ties share a rank, 1 = best).
    try:
        _rank_lookup = cws._build_stat_rank_lookup(stats_lookup)
    except Exception as _e:
        print(f"[the skinny] pass/rush ranks skipped ({_e})")
        _rank_lookup = {}
    top_stats_rows_spec = [
        (f"{label} ({win_rate*100:.0f}% real win rate)", key, hib)
        for label, key, hib, win_rate, n in top_specs
    ]
    min_n = min((n for *_r, n in top_specs), default=None)
    max_n = max((n for *_r, n in top_specs), default=None)
    # The next 2 highest real win-rate stats beyond
    # the fixed F+/FEI/Def Sacks headline trio -- whichever those actually
    # are this run, recomputed fresh, not a guessed/fixed pair.
    _next2_highlight_keys = {key for _label, key, _hib, _wr, _n in top_specs[:2]}

    story = []
    col_widths = [150, 210, 150]
    _fbs_grid_teams = None
    if dataset.get("split_grid"):
        try:
            import cfb_split_grid as _sg0
            _fbs_grid_teams = _sg0.fbs_team_set(dataset["split_grid"], list(stats_lookup.index))
        except Exception:
            _fbs_grid_teams = None

    for game_idx, (_, row) in enumerate(schedule_df.iterrows()):
        away, home = row['Away_Team'], row['Home_Team']
        game_date = row.get('Date', '--')
        away_record = row.get('Away_Record', '--')
        home_record = row.get('Home_Record', '--')

        def team_lookup(name):
            try:
                return stats_lookup.loc[name]
            except KeyError:
                return {}

        away_ts = team_lookup(away)
        home_ts = team_lookup(home)

        if _COMPACT:
            _cm, _wn = _build_commentary(away, home, away_ts, home_ts, included_stats, sacks_agreement, top_specs, fitted_margin_model=fitted_margin_model)
            _fl = _compact_game(row, away, home, away_ts, home_ts, game_date, dataset, _rank_lookup, dataset.get("split_grid"), _fbs_grid_teams, _cm, _wn)
            _h = _flow_height(_fl)
            _lim = 725 if _GAMES_PER_PAGE == 1 else 372
            if _h > _lim:
                print(f"[the skinny] note: {away} @ {home} is {_h:.0f}pt tall (limit ~{_lim}) -- it will spill onto a second page")
            story.extend(_fl)
            if game_idx < len(schedule_df) - 1:
                if _GAMES_PER_PAGE == 2 and game_idx % 2 == 0:
                    from reportlab.platypus.flowables import HRFlowable
                    story += [Spacer(1, 5), HRFlowable(width="100%", thickness=0.6, color=colors.HexColor(_MUTED)), Spacer(1, 5)]
                else:
                    story.append(PageBreak())
            continue

        story.append(Paragraph("THE SKINNY", title_style))
        story.append(Paragraph(f"{game_date}", sub_style))
        story.append(Paragraph(f"{away.upper()} at {home.upper()}", matchup_style))
        story.append(Paragraph(f"{away} ({away_record})  @  {home} ({home_record})", meta_style))

        away_sor = away_ts.get('SOR') if hasattr(away_ts, 'get') else None
        home_sor = home_ts.get('SOR') if hasattr(home_ts, 'get') else None
        story.append(Paragraph(
            f"Strength of Record -- {away}: {_fmt_sor(away_sor)}   |   {home}: {_fmt_sor(home_sor)}",
            identity_style
        ))

        away_pass_pct, away_rush_pct = _pass_rush_identity(away_ts)
        home_pass_pct, home_rush_pct = _pass_rush_identity(home_ts)
        if away_pass_pct is not None and home_pass_pct is not None:
            story.append(Paragraph(
                f"Offensive identity -- {away}: {away_pass_pct:.0f}% pass / {away_rush_pct:.0f}% run   |   "
                f"{home}: {home_pass_pct:.0f}% pass / {home_rush_pct:.0f}% run",
                identity_style
            ))

        story.append(Paragraph("RECORDS & HOME / ROAD SPLITS", section_style))
        story.append(_records_table(row, col_widths, body_style, label_style,
                                     splits=dataset.get("splits"), away=away, home=home))
        if dataset.get("splits") and not dataset.get("split_grid"):
            story.append(Paragraph("HOME / ROAD SPLITS: OFFENSE vs DEFENSE (per game)", section_style))
            story.append(_splits_grid(away, home, dataset.get("splits"), col_widths, body_style, label_style))
            story.append(Paragraph("Each number is colored by where it ranks among all teams in that same spot (green = best, red = worst). "
                                   "EXPECTED = average of what the offense produces and what the defense allows; green = a big number for the offense, red = a small one. Defense = what it allowed.", _HEAT_NOTE))

        # trenches / headline ratings / stats-that-matter removed. Under the records: away OFF rank vs home DEF rank, away stats vs home D,
        # then home OFF rank vs away DEF rank, home stats vs away D.
        _sgrid = dataset.get("split_grid")
        if _rank_lookup:
            story.append(_rank_block(away, home, _rank_lookup, col_widths, body_style, label_style))
            story.append(Spacer(1, 6))
        if _sgrid:
            story.append(_stat_block(away, "away", home, "home", _sgrid, sum(col_widths), body_style, label_style, fbs_teams=_fbs_grid_teams))
            story.append(Spacer(1, 6))
        if _rank_lookup:
            story.append(_rank_block(home, away, _rank_lookup, col_widths, body_style, label_style))
            story.append(Spacer(1, 6))
        if _sgrid:
            story.append(_stat_block(home, "home", away, "away", _sgrid, sum(col_widths), body_style, label_style, fbs_teams=_fbs_grid_teams))
        story.append(Paragraph("Ranks only, #1 = best for that unit (rush/pass: FBS rank by yards per game; stat blocks: rank among FBS teams on their season average vs FBS opponents). Green = elite rank, red = poor. OFF = what that offense produced; DEF = the same stat on the offenses "
                               "it faced (allowed / made / forced). Red zone % is not split (CFBD only has it from play-by-play). "
                               "The 'g' counts show how many FBS games each average covers.", _HEAT_NOTE))

        story.append(Paragraph("THE READ", commentary_header_style))
        commentary, weights_note = _build_commentary(away, home, away_ts, home_ts, included_stats, sacks_agreement, top_specs, fitted_margin_model=fitted_margin_model)
        story.append(Paragraph(commentary, commentary_style))
        if weights_note:
            story.append(Paragraph(
                weights_note,
                ParagraphStyle('SkinnyWeightsNote', parent=styles['Normal'], fontName='Helvetica-Oblique',
                                fontSize=7.5, alignment=TA_LEFT, textColor=colors.HexColor(_MUTED), spaceBefore=4)
            ))

        sample_note = (f"based on {min_n}-{max_n} logged games per stat" if min_n != max_n
                        else f"based on {min_n} logged games per stat")
        story.append(Paragraph(
            f"Yellow highlight in THE READ = F+ and FEI both favor the team OPPOSITE the model's own pick. Win rates {sample_note}, "
            f"recomputed fresh this run from cfb_stat_history.json -- see cfb_matrices_outlook.pdf for the full stat sheet.",
            ParagraphStyle('SkinnyFoot', parent=styles['Normal'], fontName='Helvetica-Oblique',
                            fontSize=7, alignment=TA_CENTER, textColor=colors.HexColor(_MUTED), spaceBefore=10)
        ))

        if game_idx < len(schedule_df) - 1:
            story.append(PageBreak())

    if _DARK_MODE:
        _darkify_story(story)
        doc.build(story, onFirstPage=_page_decor, onLaterPages=_page_decor)
    else:
        doc.build(story, onFirstPage=_page_decor, onLaterPages=_page_decor) if _COMPACT else doc.build(story)


def main():
    dataset = build_dataset()
    if dataset is None:
        return
    print("[the skinny] Building simple black-and-white per-game report...")
    generate_the_skinny_pdf(dataset)
    print("[the skinny] Success! Generated 'generated/the_skinny.pdf'")


if __name__ == "__main__":
    main()
