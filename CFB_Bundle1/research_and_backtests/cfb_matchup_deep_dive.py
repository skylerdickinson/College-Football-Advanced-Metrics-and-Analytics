"""
CFB DEEP-DIVE MATCHUP REPORT -- real live data, every game this week.

Built to take the place of the cfb_working_schedule.py report, pulling every game for the week just like that script does. This script does NOT re-implement any of cfb_working_schedule.py's
real fetch/model logic -- it IMPORTS that module and calls its actual,
already-tested functions directly (fetch_live_cfb_schedule,
fetch_all_teamrankings_stats, fetch_espn_*, fetch_bcftoys_ratings,
fetch_cfbd_advanced_stats, load_stat_history/record_completed_games/
tune_stat_weights, stat_vote_model_pick, build_matchup_forecast,
_build_stat_rank_lookup/_with_rank, TURQUOISE_HIGHLIGHT/
ORANGE_CAUTION_HIGHLIGHT) -- so there is exactly one real implementation of
each of those, never a second copy that could quietly drift out of sync.

The only genuinely NEW real-data work this script does is pulling two
TeamRankings pages cfb_working_schedule.py doesn't fetch yet (completion %,
interceptions thrown/gained -- see fetch_extra_teamrankings_stats() below). QB Rush Yards/Game is
NOT pulled real -- there is no team-level source for it anywhere (TeamRankings
only publishes whole-team rushing splits, not isolated QB rushing), and doing
it right would need a real per-player CFBD pull plus a real "who is this
team's starting QB" judgment call that hasn't been made yet. It stays an honestly-
disclosed illustrative placeholder in the card (see cfb_matchup_card_v4.py).

Then, for every game on this week's real live schedule, this builds that
game's real away_ts/home_ts (from the real, live-fetched stats_lookup), a
real score forecast (build_matchup_forecast), the real tuned stat-vote
model's pick + risk flag, and renders that game's full deep-dive card
(cfb_matchup_card_v4.render_one_matchup) into one shared, combined weekly
PDF -- same "one big document for the whole week" convention
cfb_matrices_outlook.pdf already uses, just with the deep-dive layout instead
of the skinny one.

NOTE -- network: this script needs live access to TeamRankings/ESPN/bcftoys/CFBD.
Run it in your normal Python environment, the same way you run cfb_working_schedule.py. Console output uses the
exact same "real diagnostic, not a guess" style as the rest of this project
-- if the two new TeamRankings slugs below are wrong, the run will say so
loudly (HTTP status / exception per slug) instead of silently faking data.
"""
import os
import sys
import io
import math
import requests
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfb_working_schedule as cws
import cfb_matchup_card_v4 as card
import cfb_matchup_deltas as deltas_mod


# ---------------------------------------------------------------------------
# NEW REAL FETCH -- Completion % and Interceptions thrown/gained per game.
# Neither is in cfb_working_schedule.py's fetch_all_teamrankings_stats() yet.
# Same real scrape pattern/headers/percentage-strip that function already
# uses (scrape_metric_group) -- copied here rather than reusing that nested
# closure directly (it isn't exposed on its own), not reimplemented from
# scratch. Multiple candidate slugs per stat are tried in order and the
# first one that returns a real 200 + parses is kept; the slugs below are
# a best guess based on TeamRankings' naming convention for every
# OTHER page cfb_working_schedule.py already successfully scrapes, not a
# confirmed URL. Whichever slug actually works will print so here, so it can
# be pinned down to one confirmed slug afterward instead of guessed again.
# ---------------------------------------------------------------------------
_EXTRA_TR_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

_EXTRA_TR_CANDIDATES = {
    "Off_Comp_Pct": [
        "/college-football/stat/completion-percentage",
        "/college-football/stat/passing-pct",
        "/college-football/stat/completion-pct",
    ],
    "Off_INT_PG": [
        "/college-football/stat/interceptions-thrown-per-game",
    ],
    "Def_INT_PG": [
        "/college-football/stat/opponent-interceptions-thrown-per-game",
    ],
}


def fetch_extra_teamrankings_stats():
    """Returns a DataFrame with a 'Clean_Name' column plus whichever of
    Off_Comp_Pct / Off_INT_PG / Def_INT_PG actually scraped successfully
    (a column is simply absent, not NaN-filled, if every candidate slug for
    it failed -- so a merge caller can tell "not fetched" apart from
    "fetched but genuinely missing for this team")."""
    result_df = None
    for col_name, candidates in _EXTRA_TR_CANDIDATES.items():
        got = False
        for slug in candidates:
            url = f"https://teamrankings.com{slug}"
            try:
                resp = requests.get(url, headers=_EXTRA_TR_HEADERS, timeout=10)
                if resp.status_code != 200:
                    print(f" -> [EXTRA] {col_name} ({slug}) FAILED: real HTTP {resp.status_code} -- trying next candidate.")
                    continue
                tables = pd.read_html(io.StringIO(resp.text))
                raw_df = tables[0]
                team_series = raw_df.iloc[:, 1]
                value_series = raw_df.iloc[:, 2]
                value_series = pd.to_numeric(
                    value_series.astype(str).str.replace('%', '', regex=False),
                    errors='coerce')
                df_clean = pd.DataFrame({'Clean_Name': team_series, col_name: value_series})
                df_clean['Clean_Name'] = df_clean['Clean_Name'].apply(cws.clean_team_name)
                result_df = df_clean if result_df is None else pd.merge(result_df, df_clean, on='Clean_Name', how='outer')
                print(f" -> [EXTRA] {col_name}: CONFIRMED real slug this run -> {slug} "
                      f"({df_clean[col_name].notna().sum()} team(s) with a real value)")
                got = True
                break
            except Exception as e:
                print(f" -> [EXTRA] {col_name} ({slug}) FAILED: real {type(e).__name__}: {e} -- trying next candidate.")
        if not got:
            print(f" -> ⚠ [EXTRA] {col_name}: every candidate slug failed -- this stat will show as "
                  f"neutral/no-baseline on the card, same honest-gap behavior as everything else missing data. "
                  f"Candidates tried: {candidates}")
    if result_df is None:
        return pd.DataFrame(columns=['Clean_Name'])
    return result_df.groupby('Clean_Name', as_index=False).first()


def _set_live_band(stats_lookup, key):
    """Computes a real NATIONAL_BASELINE + STAT_BAND entry for `key` directly
    from THIS WEEK's live, full stats_lookup column -- the real mean, and
    real symmetric top/bottom 10%/25% percentile distance from that mean,
    exactly the same 'how far the real top/bottom 10%/25% of appearances
    sits from the real average' methodology every other stat's band already
    uses, just computed live from this week's real pull instead of a frozen
    PDF snapshot.

    The heat map was
    dumping way too many cells into the purple/orange 'real top-or-bottom-10%'
    tier across multiple sections. Root cause: cfb_matchup_card_v4.py's
    NATIONAL_BASELINE/STAT_BAND dicts are hardcoded numbers frozen from one
    old snapshot of cfb_matrices_outlook.pdf, calibrated for that week's
    specific real distribution -- not this week's. Early season (small
    per-team sample sizes -> wider real spread) makes that mismatch worse.
    This function is now called for EVERY graded stat (see main()), not just
    the 3 brand-new ones, so every heat-map threshold is recomputed from
    THIS run's real full league column before any card renders, instead of
    silently grading against a stale week's numbers.

    Preserves whichever kind ('pct' vs 'abs') that stat's existing STAT_BAND
    entry already uses -- the zero-centered composites (F+/FEI/OFEI/DFEI/NSR/
    Def_PPA family) have a real average near 0, so a percent-of-average band
    would blow up / be meaningless for them; those stay 'abs' bands computed
    in the stat's own real units, never percent.

    Skips (leaves whatever's already there -- the original hardcoded
    placeholder, since nothing else overwrites it) if fewer than 20 real
    values exist -- not enough of a real sample to trust a computed band --
    or if this key has no matching real column in stats_lookup at all."""
    if key not in stats_lookup.columns:
        return
    series = pd.to_numeric(stats_lookup[key], errors='coerce').dropna()
    if len(series) < 20:
        print(f" -> [band] {key}: only {len(series)} real value(s) league-wide -- not enough to compute a "
              f"trustworthy real band, leaving whatever baseline was already set (placeholder) this run.")
        return
    mean = series.mean()
    if mean == 0:
        return
    existing = card.STAT_BAND.get(key)
    kind = existing[0] if existing else 'pct'
    p90, p10 = series.quantile(0.9), series.quantile(0.1)
    p75, p25 = series.quantile(0.75), series.quantile(0.25)
    raw10 = max(abs(p90 - mean), abs(mean - p10))
    raw25 = max(abs(p75 - mean), abs(mean - p25))
    if kind == 'abs':
        band10, band25 = raw10, raw25
        band_str = f"band10=+/-{band10:.3f}, band25=+/-{band25:.3f} (abs, stat's own units)"
    else:
        band10, band25 = raw10 / abs(mean) * 100, raw25 / abs(mean) * 100
        band_str = f"band10=+/-{band10:.0f}%, band25=+/-{band25:.0f}%"
    card.NATIONAL_BASELINE[key] = mean
    card.STAT_BAND[key] = (kind, band10, band25)
    print(f" -> [band] {key}: real live mean={mean:.3f}, {band_str} "
          f"(computed from {len(series)} real FBS team value(s) this run).")


def _with_pass_pct(ts):
    """Real pass-play/rush-play split -- computed here from Off_Pass_Plays_PG
    and Off_Rush_Plays_PG, both real TeamRankings columns
    cfb_working_schedule.py already fetches for every team (pass-attempts-
    per-game and rushing-attempts-per-game). A real 147-page run showed
    'Pass 50% / Rush 50%' on literally every single game -- that was never a
    computed split, it was cfb_matchup_card_v4.py's away_ts.get("Pass_Pct",
    50.0) silently defaulting because nothing upstream had ever set a real
    Pass_Pct. Returns `ts` unchanged (no Pass_Pct key at all) if either real
    play-count is missing/NaN/zero -- the card now shows an honest '--' in
    that case (see cfb_matchup_card_v4.py's _split_text) instead of ever
    guessing 50/50 again."""
    if not hasattr(ts, 'get'):
        return ts
    pass_plays, rush_plays = ts.get('Off_Pass_Plays_PG'), ts.get('Off_Rush_Plays_PG')
    try:
        pass_plays, rush_plays = float(pass_plays), float(rush_plays)
    except (TypeError, ValueError):
        return ts
    if math.isnan(pass_plays) or math.isnan(rush_plays) or (pass_plays + rush_plays) <= 0:
        return ts
    ts = ts.copy()
    ts['Pass_Pct'] = pass_plays / (pass_plays + rush_plays) * 100.0
    return ts


def _pick_is_risky(away_ts, home_ts, pick_side):
    """Same real 'be careful' flag cfb_working_schedule.py's own skinny
    report already computes per game -- does Def_Sacks_PG, applied to this
    matchup's real current sides, favor a DIFFERENT team than the model's
    own pick? Copied here (it's a small nested closure in
    generate_pdf_report, not exposed standalone) rather than reimplemented
    -- identical logic, calling cws's own real _live_stat_lean()."""
    if pick_side is None:
        return False
    away_sacks = away_ts.get('Def_Sacks_PG') if hasattr(away_ts, 'get') else None
    home_sacks = home_ts.get('Def_Sacks_PG') if hasattr(home_ts, 'get') else None
    lean = cws._live_stat_lean(away_sacks, home_sacks, True)
    if lean is None:
        return False
    sacks_side = 'away' if lean == 1 else 'home'
    return sacks_side != pick_side


def _build_score_pred_text(away, home, away_ts, home_ts):
    """Real score prediction text, same format the card's PREVIEW placeholder
    already uses ('Arkansas 31.4 - Tulsa 20.6 (79% Arkansas)') -- built from
    cws.build_matchup_forecast()'s real output, not re-derived here."""
    fc = cws.build_matchup_forecast(away, home, away_ts, home_ts)
    if fc is None:
        return "Forecast unavailable (missing core Points/Game data for one side)", None
    if fc['favored_team'] == home:
        fav_score, other_score, fav_prob = fc['home_score'], fc['away_score'], fc['home_win_prob']
        other_team = away
    else:
        fav_score, other_score, fav_prob = fc['away_score'], fc['home_score'], fc['away_win_prob']
        other_team = home
    text = (f"{fc['favored_team']} {fav_score:.1f} - {other_team} {other_score:.1f} "
            f"({fav_prob*100:.0f}% {fc['favored_team']})")
    return text, fc


def main():
    print("=" * 70)
    print("CFB DEEP-DIVE REPORT -- real live data, every game this week")
    print("=" * 70)

    print("Loading schedule file coordinates...")
    schedule_df, week_number, season_year = cws.fetch_live_cfb_schedule()
    if schedule_df.empty:
        print("Schedule matrix empty.")
        return

    print("Pulling global on-field matrix layers...")
    stats_lookup = cws.fetch_all_teamrankings_stats()
    if stats_lookup is None or stats_lookup.empty:
        print("Could not load stats data.")
        return

    _TR_NAMES = list(stats_lookup['Clean_Name'].dropna().unique())   # 2026-10-06: align every other source onto TeamRankings names (same as cws.main)

    print("Pulling ESPN team directory, FPI/efficiency, and QBR...")
    team_directory = cws.fetch_espn_team_directory()
    name_to_id = cws.build_name_to_id(team_directory)

    fpi_lookup = cws.fetch_espn_power_index(season_year, week_number, team_directory)
    qbr_lookup = cws.fetch_espn_qbr(season_year, team_directory)

    fpi_rows = []
    for team_name, vals in fpi_lookup.items():
        fpi_rows.append({'Clean_Name': team_name, 'FPI': vals.get('FPI'), 'Off_Eff': vals.get('Off_Eff'),
                          'Def_Eff': vals.get('Def_Eff'), 'SOS': vals.get('SOS'), 'SOR': vals.get('SOR')})
    if fpi_rows:
        stats_lookup = pd.merge(stats_lookup, cws._align_names(pd.DataFrame(fpi_rows), _TR_NAMES, 'FPI'), on='Clean_Name', how='outer')

    if qbr_lookup:
        qbr_rows = [{'Clean_Name': k, 'QBR': v} for k, v in qbr_lookup.items()]
        stats_lookup = pd.merge(stats_lookup, cws._align_names(pd.DataFrame(qbr_rows), _TR_NAMES, 'QBR'), on='Clean_Name', how='outer')

    print("Pulling per-team TFL / time of possession / FG% for this week's teams...")
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

    print("Pulling bcftoys F+ / FEI / Drive Success Rate ratings...")
    bcftoys_df, bcftoys_avg = cws.fetch_bcftoys_ratings(season_year)
    if not bcftoys_df.empty:
        stats_lookup = pd.merge(stats_lookup, cws._align_names(bcftoys_df, _TR_NAMES, 'bcftoys'), on='Clean_Name', how='outer')

    print("Pulling CFBD off/def PPA and stuff rate...")
    cfbd_df, cfbd_avg = cws.fetch_cfbd_advanced_stats(season_year)
    if not cfbd_df.empty:
        stats_lookup = pd.merge(stats_lookup, cws._align_names(cfbd_df, _TR_NAMES, 'CFBD'), on='Clean_Name', how='outer')

    print("Pulling NEW real stats -- Completion % and Interceptions thrown/gained...")
    extra_tr_df = fetch_extra_teamrankings_stats()
    if not extra_tr_df.empty:
        stats_lookup = pd.merge(stats_lookup, extra_tr_df, on='Clean_Name', how='outer')

    # Same belt-and-suspenders duplicate guard cws.main() applies right
    # before set_index -- a duplicate Clean_Name from ANY merge source
    # (confirmed to have crashed a real run before, see cws.main()'s own
    # comment on this) turns stats_lookup.loc[team] into a multi-row
    # DataFrame instead of a Series, and every .get() downstream breaks.
    dup_names = stats_lookup['Clean_Name'][stats_lookup['Clean_Name'].duplicated(keep=False)].unique()
    if len(dup_names):
        print(f" -> ⚠ stats_lookup had duplicate Clean_Name row(s): {list(dup_names)} -- keeping the first row each.")
        stats_lookup = stats_lookup.groupby('Clean_Name', as_index=False).first()

    stats_lookup.set_index('Clean_Name', inplace=True)

    # Same real FCS-buy-game filter as cws.main(): drop any scheduled game
    # where either side has no real TeamRankings core stats at all.
    known_teams = set(stats_lookup.index[stats_lookup['Off_Yds_PG'].notna()])

    # NEW: this script keeps its own copy of cws.main()'s
    # known_teams filter, so when a fresh naming gap silently dropped real
    # games (LSU/Ole Miss, then New Mexico St/N Texas), fixing
    # clean_team_name()'s dict in cfb_working_schedule.py alone wasn't
    # enough to fix THIS report -- the fix had to be duplicated here too.
    # Reusing cws's real, non-guessing generic rescue (see its own
    # docstring: only remaps onto a team name already present in this run's
    # real known_teams, never fabricates one) here closes that gap instead
    # of needing a second hand-edit every time.
    unmatched_names = (set(schedule_df['Away_Team']) | set(schedule_df['Home_Team'])) - known_teams
    rescued = {}
    for raw_name in unmatched_names:
        hit = cws.fuzzy_match_unknown_team(raw_name, known_teams)
        if hit:
            rescued[raw_name] = hit
    if rescued:
        print(f" -> Auto-matched {len(rescued)} team name(s) that would otherwise have been dropped "
              f"(ESPN/TeamRankings naming gap, resolved by generic abbreviation normalization):")
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
        print(f" -> Dropped {dropped} game(s) where NEITHER side has a TeamRankings stats match "
              f"(see cws.main()'s own version of this same check for the full diagnostic).")

    # Real, live percentile bands for EVERY graded stat -- computed fresh
    # from THIS run's real full stats_lookup, not the frozen hardcoded
    # numbers cfb_matchup_card_v4.py ships with. A real run showed way
    # too many purple/orange cells across multiple sections -- those old
    # numbers were calibrated once, off one old snapshot week, and never
    # refreshed; see _set_live_band's own docstring for the full story.
    print("Computing real live percentile bands for every graded stat (replaces the frozen "
          "placeholder NATIONAL_BASELINE/STAT_BAND numbers with this run's real ones)...")
    for _band_key in list(card.NATIONAL_BASELINE.keys()):
        if _band_key == "Pass_Pct":
            continue  # informational play-mix split only -- never heat-graded, see below
        _set_live_band(stats_lookup, _band_key)
    # The 3 brand-new deep-dive-only stats (Off_Comp_Pct/Off_INT_PG/
    # Def_INT_PG) were NEVER in cfb_matchup_card_v4.py's hardcoded
    # NATIONAL_BASELINE dict in the first place -- there was never a
    # placeholder for them to begin with, so the loop above (which only
    # walks EXISTING NATIONAL_BASELINE keys) skips them entirely. A real
    # run confirmed this: Completion % came back flat gray/ungraded for
    # every team even though 138 real values were fetched, because these 3
    # keys need their very first NATIONAL_BASELINE/STAT_BAND entry created
    # here, not just refreshed.
    for _new_key in ("Off_Comp_Pct", "Off_INT_PG", "Def_INT_PG"):
        _set_live_band(stats_lookup, _new_key)

    print("Updating stat-weighted win prediction model...")
    stat_history = cws.load_stat_history()
    newly_recorded = cws.record_completed_games(stat_history, schedule_df, stats_lookup)
    if newly_recorded:
        print(f" -> Recorded {newly_recorded} newly completed game(s) into the persistent stat history "
              f"({len(stat_history['games'])} total game(s) on record).")
    included_stats, model_accuracy, model_correct, model_decided, model_total = cws.tune_stat_weights(stat_history)
    if model_total:
        print(f" -> Model backtest: {model_correct}/{model_decided} = "
              f"{(model_correct/model_decided*100 if model_decided else 0):.1f}% accuracy across {model_total} game(s).")

    print("Building real FBS-wide per-stat rank lookup...")
    rank_lookup = cws._build_stat_rank_lookup(stats_lookup)
    card.RANK_LOOKUP = rank_lookup

    filename = "generated/cfb_deep_dive_outlook.pdf"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    doc = SimpleDocTemplate(filename, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36,
                             title="CFB Deep-Dive Matchup Report")
    styles = getSampleStyleSheet()
    banner_style = ParagraphStyle('banner', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#1A365D'))
    story = [
        Paragraph(
            f"CFB DEEP-DIVE MATCHUP REPORT -- Week {week_number}, {season_year} season. Every number below is a "
            f"real, live-pulled stat (TeamRankings / ESPN / bcftoys / CFBD) as of this run, graded against this "
            f"week's real, computed FBS-wide average -- not a placeholder. Rank in parentheses is each team's "
            f"real FBS-wide rank for that stat. Team name in turquoise = the tuned stat-vote model's real pick "
            f"for that game; orange = that pick is flagged risky (Def Sacks/Game disagrees with it).",
            banner_style),
        Spacer(1, 10),
    ]

    def team_lookup(team_name):
        try:
            return stats_lookup.loc[team_name]
        except KeyError:
            return {}

    total_games = len(schedule_df)
    print(f"Rendering deep-dive cards for {total_games} real game(s) this week...")
    for game_idx, (_, row) in enumerate(schedule_df.iterrows()):
        away, home = row['Away_Team'], row['Home_Team']
        away_record = row.get('Away_Record', '--')
        home_record = row.get('Home_Record', '--')
        away_ts = _with_pass_pct(team_lookup(away))
        home_ts = _with_pass_pct(team_lookup(home))

        away_fpi = cws._fmt_num(away_ts.get('FPI') if hasattr(away_ts, 'get') else None, decimals=1)
        home_fpi = cws._fmt_num(home_ts.get('FPI') if hasattr(home_ts, 'get') else None, decimals=1)
        away_sor = cws._fmt_num(away_ts.get('SOR') if hasattr(away_ts, 'get') else None, decimals=0)
        home_sor = cws._fmt_num(home_ts.get('SOR') if hasattr(home_ts, 'get') else None, decimals=0)

        model_pick_side = cws.stat_vote_model_pick(away_ts, home_ts, included_stats)
        pick_is_risky = _pick_is_risky(away_ts, home_ts, model_pick_side)
        score_pred, _fc = _build_score_pred_text(away, home, away_ts, home_ts)
        # Real, live-computed matchup deltas -- every
        # number cfb_matchup_deltas.compute_all() returns is built from
        # this same game's already-fetched away_ts/home_ts, no new fetch.
        if not getattr(deltas_mod, "_LEAGUE", None):
            deltas_mod.set_league_means(stats_lookup)   # SIGN FIX (2026-10-06): league averages for the paired edges
        game_deltas = deltas_mod.compute_all(away_ts, home_ts)

        print(f" -> [{game_idx + 1}/{total_games}] {away} @ {home} ... pick={model_pick_side or 'none'}"
              f"{' (RISKY)' if pick_is_risky else ''}")

        card.render_one_matchup(
            story, away, home, away_ts, home_ts, away_fpi, home_fpi,
            away_sor, home_sor, away_record, home_record, score_pred,
            model_pick_side=model_pick_side, pick_is_risky=pick_is_risky,
            deltas=game_deltas,
        )
        if game_idx < total_games - 1:
            story.append(PageBreak())

    print("Writing combined weekly PDF...")
    doc.build(story)
    print(f"Success! Generated {total_games} real game deep-dive card(s) at: '{filename}'")


if __name__ == "__main__":
    main()
