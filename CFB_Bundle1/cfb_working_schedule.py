# ==========================================
# PART 1: IMPORTS & DATA CLEANING START
# ==========================================
import io
import os
import re
import sys
import json
import time
import math
import unicodedata
import pandas as pd
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# FIX (2026-09-28): cfb_matchup_deltas.py lives in research_and_backtests/,
# one level below this script, not beside it. A bare "import
# cfb_matchup_deltas" (used twice below) only resolves when something has
# already put research_and_backtests on sys.path -- which happened
# whenever this script was launched through cfb_run_all.py, but NOT when
# this file is run standalone/directly. Adding it here makes the import
# work either way, regardless of how this script gets launched.
_RESEARCH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "research_and_backtests")
if _RESEARCH_DIR not in sys.path:
    sys.path.insert(0, _RESEARCH_DIR)

# ReportLab Visual Layer Components
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def clean_team_name(name):
    """
    Cleans raw web string inputs into sanitized school names.
    Strips rankings symbols like '#' and chops text appended in parentheses.
    """
    if not isinstance(name, str):
        return ""
    # NEW (2026-10-06): CFBD spells it "Miami (OH)" -- the parenthetical strip just below turned that
    # into plain "Miami", colliding with Miami (FL) (one overwrote the other in the PPD cache and the
    # CFBD stats). Fold it onto the same "Miami OH" form TeamRankings/ESPN use first.
    if name.strip() in ("Miami (OH)", "Miami (Ohio)", "Miami Ohio"):
        name = "Miami OH"
    if '(' in name:
        name = name.split('(')[0]
    name = name.replace("#", "").strip()

    # Strip accent/diacritic marks (e.g. ESPN's "San José State" -> "San Jose
    # State") -- confirmed real, not guessed: TeamRankings' own page for this
    # school is teamrankings.com/college-football/team/san-jose-state-spartans,
    # plain ASCII "Jose", no accent. Without this, the accented ESPN name never
    # matches TeamRankings' stat tables and the whole game gets silently
    # dropped -- exactly what a real run's drop-log showed on 2026-09-20
    # ("Fresno State at San José State -> no stats match for: HOME: San José
    # State"), the same failure mode as the LSU/Ole Miss bug fixed earlier,
    # just triggered by a diacritic instead of a nickname-vs-formal-name gap.
    # NFKD-normalizing and dropping combining marks handles this generically
    # for any other accented school name too, instead of needing a one-off
    # mapping entry for each.
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')

    mapping = {
        # CONFIRMED real name mismatches that were silently dropping entire
        # real FBS-vs-FBS games (not FCS buy games) -- ESPN's scoreboard
        # "location" field uses the popular nickname, but TeamRankings'
        # stat tables index these two under the school's official/formal
        # name (verified directly against TeamRankings' own team pages --
        # e.g. teamrankings.com/college-football/team/louisiana-state-tigers
        # and .../mississippi-rebels -- both confirm the formal name is
        # what the stat tables actually key on). Since the pre-fix dict had
        # no entry for either, they passed through unchanged ("LSU" / "Ole
        # Miss"), never matched TeamRankings' "Louisiana State" / "Mississippi"
        # rows, and the whole game got dropped by the known_teams filter in
        # main() -- exactly what was reported missing (LSU, Ole Miss, and
        # likely others sharing this same nickname-vs-formal-name pattern).
        # NEW (2026-10-06): the 3 games still showing '--' for their home team -- ESPN's schedule spells
        # these out, TeamRankings abbreviates them (names taken from TeamRankings' own stat tables).
        "Florida International": "Florida Intl",
        "Northern Illinois": "N Illinois",
        "Massachusetts": "UMass",
        "LSU": "Louisiana State",
        "Ole Miss": "Mississippi",
        "Miami OH": "Miami (OH)",
        "NC State": "North Carolina State",
        "App State": "Appalachian State",
        "E Carolina": "East Carolina",
        "Arizona St": "Arizona State",
        "Texas A&M": "Texas A&M",
        "Penn St": "Penn State",
        "Kent St": "Kent State",
        "W Kentucky": "Western Kentucky",
        "West Virginia": "West Virginia",
        "C Michigan": "Central Michigan",
        "Ball St": "Ball State",
        "Mississippi St": "Mississippi State",
        "Utah St": "Utah State",
        "Texas St": "Texas State",
        "Akron": "Akron",
        "E Michigan": "Eastern Michigan",
        "Michigan St": "Michigan State",
        "J Madison": "James Madison",
        "Florida St": "Florida State",
        "San Jose St": "San Jose State",
        "Ohio St": "Ohio State",
        "Texas Tech": "Texas Tech",
        "Oregon St": "Oregon State",
        "Iowa St": "Iowa State",
        "Coastal Car": "Coastal Carolina",
        "Florida Atlantic": "Florida Atlantic",
        "Southern Miss": "Southern Mississippi",
        "Kennesaw St": "Kennesaw State",
        "Sam Houston": "Sam Houston State",
        "Missouri St": "Missouri State",
        "Arkansas St": "Arkansas State",
        "Colorado St": "Colorado State",
        "Georgia Tech": "Georgia Tech",
        "San Diego St": "San Diego State",
        "Fresno St": "Fresno State",
        # CONFIRMED real name mismatch found 2026-09-30: TeamRankings' own
        # stat-table "Team" column uses the abbreviated forms "New Mexico
        # St" and "N Texas" for these two schools, while ESPN's scoreboard
        # "location" field for the same two schools is already the full
        # "New Mexico State" / "North Texas" -- confirmed directly against
        # both live sources (see diag_thursday.py). Since clean_team_name()
        # runs on both sides but only ESPN's side was already correct, the
        # TeamRankings row never matched and both real FBS games (Western
        # Kentucky at New Mexico State, North Texas at Tulsa -- both on the
        # Thursday 10/1/2026 slate) were silently dropped by the
        # known_teams filter in main().
        "New Mexico St": "New Mexico State",
        "N Texas": "North Texas",
        # CONFIRMED real name mismatch found 2026-10-04 (real run drop-log, then re-confirmed
        # clean after this fix -- "Western Michigan" no longer appears in the "no stats match"
        # debug block on the next run): same pattern as every other "___ St"/"C Michigan"/
        # "E Michigan" entry above.
        "Western Michigan": "W Michigan",
        # CONFIRMED real name mismatches found 2026-10-04 via the new "closest known_teams
        # name(s) sharing a real word..." debug line (no more guessing -- that line printed
        # 'Middle Tenn' and 'Georgia So' directly as the real TeamRankings-table names, after
        # the first two guesses here ("Middle Tenn St", "Ga Southern") turned out wrong).
        "Middle Tennessee": "Middle Tenn",
        "Georgia Southern": "Georgia So",
        # NOTE: "Massachusetts" and "Texas Southern" were checked the same way
        # and have ZERO candidates sharing any real word with anything in known_teams -- Texas
        # Southern is a genuine FCS/SWAC opponent (no TeamRankings page at all, same as McNeese/
        # Samford), and Massachusetts (UMass) is a real FBS independent that TeamRankings simply
        # doesn't carry stats for some weeks -- not a naming bug, nothing to map here. Both will
        # correctly show '--' for TeamRankings-sourced stats; re-check in-season if TeamRankings
        # adds UMass later.
    }
    return mapping.get(name, name)


# NEW: the known_teams filter in main() has now silently
# dropped real FBS-vs-FBS games THREE separate times this season because
# clean_team_name()'s mapping dict had no entry for that one school's
# ESPN-vs-TeamRankings naming gap (LSU/Ole Miss on 2026-09-20, Miami OH/NC
# State/etc. around the same time, then New Mexico St/N Texas on
# 2026-09-30) -- every time, the fix was "add one more exact-string entry
# to the dict," which only ever catches the NEXT mismatch after it's
# already cost a dropped game on a real report. Rather than keep whack-a-moling the static dict one school
# at a time, this adds a GENERIC second-chance matcher that runs in main()
# (see the known_teams/keep_mask block below) right before a game would be
# dropped: it normalizes both the unmatched schedule name and every name
# already in known_teams (lowercase, strip punctuation, expand the exact
# same directional/state abbreviations the dict above already hand-codes
# -- "St"->"State", "N "->"North ", "S "->"South ", "E "->"East ",
# "W "->"West ", "C "->"Central ") and looks for a UNIQUE match. This is
# real, not guessed: it only ever maps a schedule name onto a TeamRankings
# name that's ALREADY in this week's real known_teams set (never invents
# or hardcodes a stat value), it's auditable (every auto-match is printed
# so it can be checked), and it only acts when exactly one known team
# normalizes to the same string -- any ambiguous/no-match case still falls
# through to the original drop-and-report behavior unchanged.
def _normalize_team_for_fuzzy_match(name):
    if not isinstance(name, str):
        return ""
    n = name.strip().lower()
    n = n.replace(".", "").replace("'", "").replace("-", " ")
    n = re.sub(r"\s+", " ", n).strip()
    prefix_expansions = {
        "n ": "north ", "s ": "south ", "e ": "east ", "w ": "west ",
        "c ": "central ", "nw ": "northwest ", "ne ": "northeast ",
        "sw ": "southwest ", "se ": "southeast ", "mt ": "mount ",
    }
    for abbr, full in prefix_expansions.items():
        if n.startswith(abbr):
            n = full + n[len(abbr):]
            break
    # Word-boundary "st" -> "state" (also matches at end-of-string, since
    # \b counts the string boundary too) -- careful to use \b so this
    # never mangles a word that merely contains "st" (e.g. "west", "coast").
    n = re.sub(r"\bst\b", "state", n)
    return n.strip()


def fuzzy_match_unknown_team(team_name, known_teams):
    """
    Given a schedule-side team name that isn't an exact match in
    known_teams, tries to rescue it via generic name normalization instead
    of letting the game get silently dropped. Returns the matching
    known_teams name (so the caller can remap schedule_df onto it) if
    exactly one known team normalizes the same way, else None (ambiguous
    or genuinely no match -- e.g. a real FCS opponent).
    """
    target = _normalize_team_for_fuzzy_match(team_name)
    if not target:
        return None
    matches = [kt for kt in known_teams if _normalize_team_for_fuzzy_match(kt) == target]
    if len(matches) == 1:
        return matches[0]
    return None

# NEW: FPI / QBR / bcftoys F+ / CFBD PPA / PPD-last-3 are all keyed by each
# source's OWN spelling of a school ("South Florida", "Jacksonville State", "Washington State",
# "Kansas State"...) while the TeamRankings rows the sheet is built on use the abbreviated forms
# ("S Florida", "Jacksonville St", "Washington St", "Kansas St"...). The old outer merge on
# Clean_Name never joined them, so those teams silently showed "--" for FPI/QBR/F+/PPA/PPD (and
# the grid report's Predicted Team Total / Spread went N/A, since they need PPD). This lines each
# source's names up onto the TeamRankings names BEFORE merging, using the same normalizer the
# schedule fuzzy-matcher already uses. It only renames when exactly ONE TeamRankings name matches,
# never invents a value, and prints every rename so it can be audited.
_NAME_FOLD = {"connecticut": "uconn", "central florida": "ucf", 
              "miami florida": "miami", "miami fl": "miami",
              "fiu": "florida international", "north illinois": "northern illinois", "n illinois": "northern illinois",
              "umass": "massachusetts", "florida intl": "florida international",
              "ul monroe": "louisiana monroe", "ul lafayette": "louisiana", "louisiana lafayette": "louisiana"}


def _align_key(name):
    k = _normalize_team_for_fuzzy_match(name)
    k = re.sub(r"[()]", "", k)
    k = re.sub(r"\s+", " ", k).strip()
    return _NAME_FOLD.get(k, k)


def _align_names(df, known_names, label=""):
    """Rename df['Clean_Name'] values that aren't already a TeamRankings name onto the one
    TeamRankings name that normalizes the same way (if exactly one does)."""
    if df is None or df.empty or 'Clean_Name' not in df.columns:
        return df
    known = [k for k in known_names if isinstance(k, str) and k]
    known_set = set(known)
    by_key = {}
    for k in known:
        by_key.setdefault(_align_key(k), []).append(k)
    ren = {}
    for nm in df['Clean_Name'].dropna().unique():
        if nm in known_set:
            continue
        hit = by_key.get(_align_key(nm), [])
        if len(hit) == 1:
            ren[nm] = hit[0]
    if ren:
        print(f" -> name-align [{label}]: " + ", ".join(f"{a} -> {b}" for a, b in sorted(ren.items())))
        df = df.copy()
        df['Clean_Name'] = df['Clean_Name'].replace(ren)
        df = df.drop_duplicates(subset=['Clean_Name'], keep='first')
    return df

# ==========================================
# PART 1: IMPORTS & DATA CLEANING END
# ==========================================
# ==========================================
# PART 2: LIVE SCHEDULE SCRAPER START
# ==========================================
def fetch_live_cfb_schedule():
    """
    Pulls this week's actual FBS schedule LIVE from ESPN's public scoreboard
    API -- no more copying/pasting a schedule by hand. Uses groups=80 to
    filter to FBS games only, which also means the old hardcoded FCS-name
    exclusion list is no longer needed at all -- the API only ever returns
    FBS games to begin with. Uses an explicit Tuesday-through-Monday date
    window (recomputed fresh from today's date every run) rather than
    trusting ESPN's bare default, which can lag behind the actual current
    week right around the rollover point -- the same issue already found
    and fixed for the NFL version of this pipeline. Also passes limit=1000,
    since a single FBS Saturday is 60-90+ games and ESPN's default page
    size (~25) would otherwise silently truncate the response.

    Also pulls, straight out of the same API response (no extra scrape
    needed): each game's kickoff date/time, each team's overall win-loss
    record, and the ESPN week/season numbers -- the week number is needed
    later to pull that week's FPI snapshot from ESPN's Power Index feed.

    IMPORTANT, confirmed against live traffic and cross-checked against
    other projects hitting the same ESPN endpoint: as of ~September 15,
    2026, ESPN's scoreboard API started outright REJECTING the "dates"
    parameter when it's a range ("YYYYMMDD-YYYYMMDD") with a 400 --
    something changed on ESPN's side, across every sport, not specific to
    this script. A single date ("dates=YYYYMMDD", no dash) still works
    fine. Separately, "limit" silently caps around 500 regardless of what
    you ask for -- requesting limit=1000 on a real 68-game Saturday was
    quietly only returning 25 games, no error, just a truncated result.
    So instead of one request for the whole week, this tries the range
    once (cheap, and lets it self-heal if ESPN reverts the change), and if
    that 400s, falls back to one request per individual day in the
    Tuesday-Monday window (dates=YYYYMMDD, limit=500 -- comfortably above
    any single day's real game count) and merges them, de-duplicated by
    ESPN's own event id.
    """
    print("Pulling live FBS schedule from ESPN...")

    today = datetime.now()
    days_since_tuesday = (today.weekday() - 1) % 7   # Mon=0 ... Tue=1 in Python's weekday()
    week_start = today - timedelta(days=days_since_tuesday)
    week_dates = [week_start + timedelta(days=i) for i in range(7)]   # Tue ... Mon
    date_range = f"{week_dates[0].strftime('%Y%m%d')}-{week_dates[-1].strftime('%Y%m%d')}"

    url = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

    def _get_json(params):
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        return response.json()

    week_number = None
    season_year = today.year
    all_events = {}   # keyed by event id, so day-by-day merging can't double count

    try:
        # Attempt 1: the whole week in one shot. Cheap to try even though
        # it's currently known to 400 -- if ESPN ever reverts the change
        # this goes back to a single request instead of seven.
        data = None
        try:
            data = _get_json({"groups": 80, "dates": date_range, "limit": 500})
        except Exception as range_err:
            print(f" -> Range request rejected ({range_err}); falling back to one request per day...")
            data = None

        if data is not None:
            for event in data.get("events", []):
                all_events[event.get("id", event.get("name"))] = event
            week_number = data.get("week", {}).get("number")
            season_year = data.get("season", {}).get("year", season_year)
        else:
            # Attempt 2: one request per day in the window. Slower (7
            # requests instead of 1) but each single-day request is small
            # and, per the above, actually works right now.
            for day in week_dates:
                day_str = day.strftime("%Y%m%d")
                try:
                    data = _get_json({"groups": 80, "dates": day_str, "limit": 500})
                except Exception as day_err:
                    print(f" -> ⚠ {day_str} request failed ({day_err}); skipping that day.")
                    continue
                for event in data.get("events", []):
                    all_events[event.get("id", event.get("name"))] = event
                if week_number is None:
                    week_number = data.get("week", {}).get("number")
                season_year = data.get("season", {}).get("year", season_year)

        games_list = []
        skipped = []
        for event in all_events.values():
            competition = event.get("competitions", [{}])[0]
            competitors = competition.get("competitors", [])
            away_name, home_name = None, None
            away_record, home_record = "--", "--"
            away_score, home_score = None, None
            away_extra = home_extra = {"Conf": "--", "Home": "--", "Road": "--"}
            for c in competitors:
                school = c.get("team", {}).get("location")
                record_summary = "--"
                for rec in c.get("records", []) or []:
                    if rec.get("name") == "overall" or rec.get("type") == "total":
                        record_summary = rec.get("summary", "--")
                        break
                else:
                    recs = c.get("records", []) or []
                    if recs:
                        record_summary = recs[0].get("summary", "--")

                # conference / home / road records for the Skinny, read from the same ESPN
                # "records" list (type 'total' / 'home' / 'road' / 'vsconf'). Missing ones stay "--".
                _rm = {}
                for rec in c.get("records", []) or []:
                    _k = str(rec.get("type") or rec.get("name") or "").lower()
                    _rm[_k] = rec.get("summary", "--")
                    _n = str(rec.get("name") or "").lower()
                    if _n and _n not in _rm:
                        _rm[_n] = rec.get("summary", "--")
                def _pick(*keys):
                    for _kk in keys:
                        if _kk in _rm:
                            return _rm[_kk]
                    for _kk, _vv in _rm.items():
                        if any(x in _kk for x in keys):
                            return _vv
                    return "--"
                _extra_recs = {"Conf": _pick("vsconf", "conference", "conf"), "Home": _pick("home"),
                               "Road": _pick("road", "away")}
                if not globals().get("_REC_TYPES_PRINTED"):
                    globals()["_REC_TYPES_PRINTED"] = True
                    print(f" -> [debug] ESPN record types on the first competitor this run: "
                          f"{[(r.get('type'), r.get('name'), r.get('summary')) for r in (c.get('records') or [])]}")

                # Real field path confirmed against ESPN's own documented
                # scoreboard schema (competitions[].competitors[].score) --
                # added for the stat-signal tracker below, which needs to
                # know each completed game's actual final score to identify
                # the real winner, not just season win-loss records.
                raw_score = c.get("score")
                score_val = None
                if raw_score is not None:
                    try:
                        score_val = int(float(raw_score))
                    except (TypeError, ValueError):
                        score_val = None

                if c.get("homeAway") == "home":
                    home_name = school
                    home_record = record_summary
                    home_score = score_val
                    home_extra = _extra_recs
                else:
                    away_name = school
                    away_record = record_summary
                    away_score = score_val
                    away_extra = _extra_recs

            if not away_name or not home_name:
                skipped.append(event.get("name", "unknown game"))
                continue

            away_clean = clean_team_name(away_name)
            home_clean = clean_team_name(home_name)

            # Format the ISO kickoff timestamp ("2026-09-19T23:30Z") into
            # something readable for the report header, e.g. "Sat, Sep 19".
            raw_date = event.get("date")
            display_date = "--"
            if raw_date:
                try:
                    dt = datetime.strptime(raw_date, "%Y-%m-%dT%H:%MZ")
                    display_date = dt.strftime("%a, %b %-d")
                except ValueError:
                    try:
                        dt = datetime.strptime(raw_date[:16], "%Y-%m-%dT%H:%M")
                        display_date = dt.strftime("%a, %b %-d")
                    except Exception:
                        display_date = raw_date

            # Real field paths confirmed against ESPN's own documented
            # scoreboard schema: competitions[].status.type.completed
            # (bool) and .type.name ("STATUS_FINAL" etc.) -- used by the
            # stat-signal tracker below to know which of today's games are
            # actually finished (not just scheduled) before treating a
            # score as real.
            status_type = competition.get("status", {}).get("type", {})
            is_completed = bool(status_type.get("completed")) or status_type.get("name") == "STATUS_FINAL"
            winner_clean = None
            if is_completed and away_score is not None and home_score is not None and away_score != home_score:
                winner_clean = home_clean if home_score > away_score else away_clean

            games_list.append({
                "Game": f"{away_clean} at {home_clean}",
                "Away_Team": away_clean,
                "Home_Team": home_clean,
                "Date": display_date,
                "Away_Record": away_record,
                "Home_Record": home_record,
                "Away_Conf_Record": away_extra["Conf"], "Away_Home_Record": away_extra["Home"], "Away_Road_Record": away_extra["Road"],
                "Home_Conf_Record": home_extra["Conf"], "Home_Home_Record": home_extra["Home"], "Home_Road_Record": home_extra["Road"],
                "Event_Id": event.get("id"),
                "Completed": is_completed,
                "Away_Score": away_score,
                "Home_Score": home_score,
                "Winner": winner_clean,
            })

        print(f" -> Successfully loaded {len(games_list)} live FBS matchups.")
        if skipped:
            print(f" -> ⚠ Skipped {len(skipped)} event(s) missing team data: {skipped}")

    except Exception as e:
        games_list = []
        print(f" -> ⚠ Live schedule pull failed ({e}). Returning an empty schedule.")

    return pd.DataFrame(games_list), week_number, season_year

# ==========================================
# PART 2: LIVE SCHEDULE SCRAPER END
# ==========================================
# ==========================================
# PART 3: MATRIX STATS CONSOLIDATOR START
# ==========================================
def fetch_all_teamrankings_stats():
    """Gathers stats using isolated structural indexing to forcefully block repetition errors."""
    turnover_slug = "/college-football/stat/turnover-margin-per-game"

    offense_metrics = {
        "/college-football/stat/yards-per-game": "Off_Yds_PG",
        "/college-football/stat/yards-per-play": "Off_YPP",
        "/college-football/stat/passing-yards-per-game": "Off_Pass_PG",
        "/college-football/stat/yards-per-pass-attempt": "Off_Pass_Att",
        "/college-football/stat/rushing-yards-per-game": "Off_Rush_PG",
        "/college-football/stat/yards-per-rush-attempt": "Off_Rush_Att",
        "/college-football/stat/points-per-game": "Off_PPG",
        "/college-football/stat/third-down-conversion-pct": "Off_3rd_%",
        "/college-football/stat/red-zone-scoring-pct": "Off_RZ_%",
        # Added per request: sacks allowed and offensive tempo.
        "/college-football/stat/qb-sacked-per-game": "Off_Sacks_Allowed_PG",
        "/college-football/stat/plays-per-game": "Off_Plays_PG",
        # Added per request: split total plays into passing vs rushing play
        # counts, for the new Passing/Rushing sub-grids.
        "/college-football/stat/pass-attempts-per-game": "Off_Pass_Plays_PG",
        "/college-football/stat/rushing-attempts-per-game": "Off_Rush_Plays_PG",
    }

    defense_metrics = {
        "/college-football/stat/opponent-yards-per-game": "Def_Yds_PG",
        "/college-football/stat/opponent-yards-per-play": "Def_YPP",
        "/college-football/stat/opponent-passing-yards-per-game": "Def_Pass_PG",
        "/college-football/stat/opponent-yards-per-pass-attempt": "Def_Pass_Att",
        "/college-football/stat/opponent-rushing-yards-per-game": "Def_Rush_PG",
        "/college-football/stat/opponent-yards-per-rush-attempt": "Def_Rush_Att",
        "/college-football/stat/opponent-points-per-game": "Def_PPG",
        "/college-football/stat/opponent-third-down-conversion-pct": "Def_3rd_%",
        "/college-football/stat/opponent-red-zone-scoring-pct": "Def_RZ_%",
        # Added per request: sacks recorded and defensive tempo (plays faced).
        "/college-football/stat/sacks-per-game": "Def_Sacks_PG",
        "/college-football/stat/opponent-plays-per-game": "Def_Plays_Faced_PG",
        # Added per request: passing vs rushing plays faced, for the new
        # Passing/Rushing sub-grids on the defense side.
        "/college-football/stat/opponent-pass-attempts-per-game": "Def_Pass_Plays_PG",
        "/college-football/stat/opponent-rushing-attempts-per-game": "Def_Rush_Plays_PG",
    }

    # Added per request: point differential (scoring margin).
    scoring_margin_slug = "/college-football/stat/average-scoring-margin"
    # Added per request: real per-team home-field-advantage rating (points),
    # used by the forecast engine instead of a flat constant -- CFB home
    # advantage varies enormously by program (research puts the CFB-wide
    # average around 2.6 points, but ranges from roughly +9.5 for a team
    # like Jacksonville State down to negative for a team that historically
    # plays worse at home, like Charlotte). This is a "/ranking/" page, a
    # different TeamRankings URL family than the "/stat/" pages used
    # everywhere else in this function, but it publishes the same
    # Rank | Team | Rating table layout, so the same iloc[:,1]/iloc[:,2]
    # parse applies.
    home_adv_slug = "/college-football/ranking/home-adv-by-other"

    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    master_df = None

    def scrape_metric_group(metrics_dict, group_label):
        """Same real per-metric TeamRankings scrape as before, now with a
        real per-slug diagnostic print on failure (HTTP status code, or the
        real exception) instead of a silent `except: pass`. This is exactly
        the kind of silent-missing-data failure the project's own 'real
        data, no guessing' rule exists to catch -- a whole metrics group
        (e.g. every real DEFENSE/opponent-stat page) can fail on every
        single slug with zero visible error anywhere, and the report just
        quietly shows '--' for all of it. Behavior is unchanged (a failed
        slug is still skipped, not fatal) -- this only adds visibility into
        WHY, plus a real per-group success/fail count so it's obvious at a
        glance whether an entire group came back empty."""
        group_df = None
        ok_count, fail_count = 0, 0
        for slug, col_name in metrics_dict.items():
            url = f"https://teamrankings.com{slug}"
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code != 200:
                    print(f" -> [{group_label}] {col_name} ({slug}) FAILED: real HTTP {response.status_code} response")
                    fail_count += 1
                    continue
                tables = pd.read_html(io.StringIO(response.text))
                raw_df = tables[0]

                team_series = raw_df.iloc[:, 1]
                value_series = raw_df.iloc[:, 2]
                # Real bug fix (found while investigating why Off/Def 3rd
                # Down % and Off/Def Red Zone % had ZERO real logged votes
                # across 48 real games despite pulling and displaying fine):
                # TeamRankings' percentage-stat pages render this column
                # with a literal '%' suffix (e.g. "42.3%"), which pandas
                # leaves as a string instead of auto-detecting a float --
                # unlike the plain-decimal yardage/points pages, which parse
                # to float64 on their own. _stat_vote()'s float() cast then
                # silently fails on that string every time (caught, treated
                # as "no data"), so these 4 stats never cast a real vote.
                # Every other metric in this function is a plain decimal
                # already, so this strip is a no-op for those -- safe to
                # apply unconditionally rather than special-casing by slug.
                value_series = pd.to_numeric(
                    value_series.astype(str).str.replace('%', '', regex=False),
                    errors='coerce')

                df_clean = pd.DataFrame({'Clean_Name': team_series, col_name: value_series})
                df_clean['Clean_Name'] = df_clean['Clean_Name'].apply(clean_team_name)

                if group_df is None:
                    group_df = df_clean
                else:
                    group_df = pd.merge(group_df, df_clean, on="Clean_Name", how="outer")
                ok_count += 1
            except Exception as e:
                print(f" -> [{group_label}] {col_name} ({slug}) FAILED: real {type(e).__name__}: {e}")
                fail_count += 1
        print(f" -> [{group_label}] {ok_count}/{len(metrics_dict)} real metric page(s) scraped successfully"
              + (f", {fail_count} failed (see above)." if fail_count else "."))
        return group_df

    try:
        to_url = f"https://teamrankings.com{turnover_slug}"
        to_response = requests.get(to_url, headers=headers, timeout=10)
        to_tables = pd.read_html(io.StringIO(to_response.text))
        raw_to_df = to_tables[0]

        master_df = pd.DataFrame({
            'Clean_Name': raw_to_df.iloc[:, 1],
            'Net_TO_Margin': raw_to_df.iloc[:, 2]
        })
        master_df['Clean_Name'] = master_df['Clean_Name'].apply(clean_team_name)
        # Defensive: this is a live per-game AVERAGE TeamRankings recomputes
        # after every game (it's the "2026" season-to-date column, not a
        # value this script accumulates itself, and nothing here caches it
        # -- every run re-scrapes this page fresh). TeamRankings shows
        # signed values (e.g. "+0.50" / "-0.50"); pd.read_html usually
        # infers that column as numeric on its own, but coerce it explicitly
        # so a stray '+' prefix or footnote character never silently turns
        # this into a string that slips past later float() parsing.
        master_df['Net_TO_Margin'] = pd.to_numeric(master_df['Net_TO_Margin'], errors='coerce')
    except Exception:
        master_df = pd.DataFrame(columns=['Clean_Name', 'Net_TO_Margin'])

    # Point differential -- scraped the same lightweight way as turnover margin.
    try:
        pd_response = requests.get(f"https://teamrankings.com{scoring_margin_slug}", headers=headers, timeout=10)
        pd_tables = pd.read_html(io.StringIO(pd_response.text))
        raw_pd_df = pd_tables[0]
        pd_clean = pd.DataFrame({
            'Clean_Name': raw_pd_df.iloc[:, 1],
            'Point_Diff': raw_pd_df.iloc[:, 2]
        })
        pd_clean['Clean_Name'] = pd_clean['Clean_Name'].apply(clean_team_name)
        pd_clean['Point_Diff'] = pd.to_numeric(pd_clean['Point_Diff'], errors='coerce')
        master_df = pd.merge(master_df, pd_clean, on="Clean_Name", how="outer")
    except Exception:
        pass

    # Per-team home-field-advantage rating -- same lightweight scrape shape.
    try:
        hfa_response = requests.get(f"https://teamrankings.com{home_adv_slug}", headers=headers, timeout=10)
        hfa_tables = pd.read_html(io.StringIO(hfa_response.text))
        raw_hfa_df = hfa_tables[0]
        hfa_clean = pd.DataFrame({
            'Clean_Name': raw_hfa_df.iloc[:, 1],
            'Home_Adv': raw_hfa_df.iloc[:, 2]
        })
        hfa_clean['Clean_Name'] = hfa_clean['Clean_Name'].apply(clean_team_name)
        hfa_clean['Home_Adv'] = pd.to_numeric(hfa_clean['Home_Adv'], errors='coerce')
        master_df = pd.merge(master_df, hfa_clean, on="Clean_Name", how="outer")
    except Exception:
        pass

    off_df = scrape_metric_group(offense_metrics, "OFFENSE")
    def_df = scrape_metric_group(defense_metrics, "DEFENSE")

    # Check: if the OFFENSE and DEFENSE TeamRankings pages spell
    # team names differently from each other (a different naming convention
    # between the "/stat/..." and "/stat/opponent-..." page families, not
    # just an isolated one-off like Tulane/Kansas State), the outer merge
    # below will silently produce two separate rows per team instead of one
    # combined row -- one with real Off_* values and NaN Def_*, one with
    # real Def_* values and NaN Off_* under a differently-spelled
    # Clean_Name -- and the later groupby('Clean_Name').first() can only
    # collapse rows that already share the EXACT same Clean_Name, so a
    # spelling mismatch would sail right through it undetected. Comparing
    # the two raw name sets directly (before any merge) is the only way to
    # confirm or rule this out with real evidence instead of guessing.
    if off_df is not None and def_df is not None:
        # NEW (2026-10-06): TeamRankings spells a few schools differently between its offense and
        # defense page families (e.g. "FIU"), which left those teams' DEFENSE numbers as a separate
        # half-empty row -> "--" on the sheet. Line the defense names up onto the offense names first.
        def_df = _align_names(def_df, off_df['Clean_Name'].dropna().unique(), 'TeamRankings defense->offense')
        off_names = set(off_df['Clean_Name'])
        def_names = set(def_df['Clean_Name'])
        only_off = off_names - def_names
        only_def = def_names - off_names
        print(f" -> [debug] OFFENSE scrape produced {len(off_names)} distinct real team name(s); "
              f"DEFENSE scrape produced {len(def_names)} distinct real team name(s)")
        if only_off or only_def:
            print(f" -> ⚠ [debug] {len(only_off)} real team name(s) appear in OFFENSE but NOT in DEFENSE "
                  f"(e.g. {sorted(only_off)[:8]}); {len(only_def)} appear in DEFENSE but NOT in OFFENSE "
                  f"(e.g. {sorted(only_def)[:8]}) -- if these numbers are large, this IS the real bug: a "
                  f"naming-convention mismatch between the two TeamRankings page families is silently "
                  f"splitting every team into two half-empty rows.")
        else:
            print(f" -> [debug] OFFENSE and DEFENSE real team-name sets match exactly -- the merge below "
                  f"is not the source of any real name-mismatch split.")

    if off_df is not None:
        master_df = pd.merge(master_df, off_df, on="Clean_Name", how="outer")
    if def_df is not None:
        master_df = pd.merge(master_df, def_df, on="Clean_Name", how="outer")

    # Teams spelled slightly differently across scraped pages (whitespace, etc.)
    # can leave two partial rows after the outer merges (Tulane and Kansas State
    # did). Group by Clean_Name and take the first non-null per column to
    # collapse them into one row.
    master_df = master_df.groupby('Clean_Name', as_index=False).first()

    # Quick sanity print so it's easy to eyeball that this is a fresh,
    # live-scraped number every run (nothing in this function caches
    # anything -- it's a plain network request each time) and to cross-check
    # it directly against https://www.teamrankings.com/college-football/stat/turnover-margin-per-game
    # Net_TO_Margin is TeamRankings' own season-to-date PER-GAME AVERAGE, so
    # it will only land on exactly 0 if the team's turnover margins across
    # ALL games played so far net out to zero -- not just its most recent
    # two games.
    _debug_row = master_df.loc[master_df['Clean_Name'] == 'Syracuse']
    if not _debug_row.empty:
        print(f" -> [debug] Syracuse Net_TO_Margin scraped this run: {_debug_row['Net_TO_Margin'].iloc[0]}")
        if 'Home_Adv' in _debug_row.columns:
            print(f" -> [debug] Syracuse Home_Adv scraped this run: {_debug_row['Home_Adv'].iloc[0]} "
                  f"(cross-check at https://www.teamrankings.com/college-football/ranking/home-adv-by-other)")

    # Real, targeted check against the exact teams the real PDF showed with
    # blank defense columns (Liberty, Coastal Carolina, Army, Temple) --
    # after the groupby('Clean_Name').first() collapse above, does this
    # team's real row actually carry a real Def_PPG value, or is it NaN?
    # This is the single most direct piece of evidence: if Off_PPG is real
    # but Def_PPG is NaN for these exact teams post-collapse, the bug is
    # confirmed to be a merge/name-matching issue upstream of this point
    # (not a report-rendering issue downstream, and not the scrape itself,
    # which the "13/13" success count already cleared).
    for _watch_team in ("Liberty", "Coastal Carolina", "Army", "Temple"):
        _row = master_df.loc[master_df['Clean_Name'] == _watch_team]
        if _row.empty:
            print(f" -> ⚠ [debug] '{_watch_team}' has NO row at all in master_df after the Clean_Name "
                  f"collapse -- real name mismatch is dropping this team entirely, not just its defense side.")
            continue
        _off_val = _row['Off_PPG'].iloc[0] if 'Off_PPG' in _row.columns else 'COLUMN MISSING'
        _def_val = _row['Def_PPG'].iloc[0] if 'Def_PPG' in _row.columns else 'COLUMN MISSING'
        print(f" -> [debug] {_watch_team}: real Off_PPG={_off_val!r}  real Def_PPG={_def_val!r}"
              + ("  <-- Def_PPG is null/NaN despite a real Off_PPG value: confirms a real name-mismatch "
                 "or merge issue on the defense side for this team" if pd.isna(_def_val) and not pd.isna(_off_val) else ""))

    return master_df


# ==========================================
# BCFTOYS: F+, FEI, DRIVE SUCCESS RATE (OSR/DSR/NSR)
# ==========================================
# Real column layout -- corrected 2026-09-20 against an actual raw-row dump
# from a live run (a [rawrow] diagnostic print of every cell, by position,
# for both Ohio State and Kent State). The layout below WAS guessed by
# analogy to the fplus page's shape and was wrong for fei/dsr: those two
# pages have an extra BLANK spacer cell immediately after the lead combined
# stat (FEI / NSR) that fplus does not have, so every column after it sits
# two positions further right than the old guess assumed. The old
# "OFEI":5/"DFEI":7 and "OSR":5/"DSR":13 positions were actually landing on
# a genuinely-blank cell (5) and, further along, each stat's own RANK
# number instead of its value -- which is exactly why DFEI/DSR silently
# looked "plausible" for elite teams (a small rank number like 1 or 2 reads
# like a real small FEI-scale value) but obviously broken for bad teams
# (Kent State showed DFEI=117.0, DSR=133.0 -- unmistakably rank numbers,
# not rates). Verified against real live data for both an elite team (Ohio
# State: OFEI rank 2, DFEI rank 1 -- makes sense for the #1 overall team)
# and a bad one (Kent State: OFEI rank 117, DFEI rank 138 -- makes sense
# for a team ranked 137th overall), on both the fei and dsr pages. F+ page
# needed no fix -- its real layout matches what was already coded.
# Each page is a single wide ranking table, same "Rk | Team | Rec | FBS |
# ... " shape TeamRankings uses, just with more columns and repeated "Rk"
# sub-columns interspersed -- so this uses the same "trust the column
# position, not the header text" approach as scrape_metric_group() above,
# since a repeated "Rk" header would collide if read_html tried to key by
# column name.
#   2026-fplus  -> Rk, Team, Rec, FBS, F+, OF+, Rk, DF+, Rk, SF+, Rk, [blank], v10..vO
#   2026-fei    -> Rk, Team, Rec, FBS, FEI, [blank], OFEI, Rk, DFEI, Rk, SFEI, Rk, [blank], ...
#   2026-dsr    -> Rk, Team, Rec, FBS, NSR, [blank], OSR, Rk, OSS, Rk, OSV, Rk, OSM, Rk, [blank], DSR, Rk, ...
_BCFTOYS_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

_BCFTOYS_PAGES = {
    "fplus": {"slug": "fplus", "cols": {"F+": 4, "OF+": 5, "DF+": 7}},
    "fei":   {"slug": "fei",   "cols": {"FEI": 4, "OFEI": 6, "DFEI": 8}},
    "dsr":   {"slug": "dsr",   "cols": {"NSR": 4, "OSR": 6, "DSR": 15}},
}


def fetch_bcftoys_ratings(season_year):
    """
    Pulls Brian Fremeau's real F+ (bcftoys.com/{year}-fplus), FEI
    (.../{year}-fei), and Drive Success Rate (.../{year}-dsr) ratings --
    every FBS team, not just this week's teams, so the average across all
    of them below is a real, computed national baseline rather than a
    guessed constant.

    Returns a DataFrame with a 'Clean_Name' COLUMN (not the index -- this
    docstring used to (wrongly) claim it was; confirmed live 2026-09-22
    when a caller's .loc[team_name] silently matched 0 rows because of
    that -- callers that need Clean_Name as the index must
    .set_index('Clean_Name') themselves) and columns:
    F+, OF+, DF+, FEI, OFEI, DFEI, NSR, OSR, DSR -- plus, on the module
    dict BCFTOYS_LEAGUE_AVG, the real mean of each column across every
    team that came back with a real (non-NaN) value for it, for grading.
    """
    master = None
    for key, meta in _BCFTOYS_PAGES.items():
        url = f"https://bcftoys.com/{season_year}-{meta['slug']}"
        try:
            resp = requests.get(url, headers=_BCFTOYS_HEADERS, timeout=15)
            resp.raise_for_status()
            tables = pd.read_html(io.StringIO(resp.text))

            # Confirmed live on 2026-09-20 (via a real fetch of this exact
            # page, cross-checked against the console debug output from a
            # real run): bcftoys does NOT publish one big ranking table --
            # it splits the full ~130-138-team rankings into ~9 SEPARATE
            # <table> elements of ~15 rows each (likely a print-pagination
            # layout), all sharing the same column structure. Reading only
            # tables[0] (the old behavior) silently grabbed just the first
            # chunk -- ranks ~1-15 -- and left every other team's F+/FEI/DSR
            # as a real, verified-missing '--' instead of the real number
            # that was sitting a few tables further down the same page. This
            # is exactly why a live run showed real data for Ohio State
            # (rank 1) but '--' for the ~85% of teams ranked outside the top
            # 15 (Pittsburgh #31, Syracuse #73, etc. -- confirmed by
            # cross-checking bcftoys' real page). Concatenating every table
            # that shares tables[0]'s column count (guards against
            # accidentally sweeping in an unrelated small table elsewhere on
            # the page, e.g. a nav/ad table with a different shape) recovers
            # the full real dataset instead of just the first slice of it.
            same_shape_tables = [t for t in tables if t.shape[1] == tables[0].shape[1]]

            # Confirmed live on 2026-09-20 (a real run after the concat fix
            # above shipped): raw label-based pd.concat is NOT safe here.
            # Each of the ~9 chunks gets its own independent
            # duplicate-column auto-renaming from pd.read_html (bcftoys'
            # real header repeats "Rk" many times per row -- see the
            # module-level comment above this function -- and pandas
            # dedupes those into Rk, Rk.1, Rk.2... separately for EACH
            # table). If two chunks don't produce the exact same label
            # sequence (e.g. one chunk is missing a sub-stat column that
            # another has), pd.concat's default LABEL-based alignment
            # silently unions/misaligns columns instead of stacking rows
            # straight down -- this is almost certainly what produced a
            # real run's corrupted Ohio State row (OSR came back NaN, DSR
            # came back "19.0", a raw rank number, instead of a real rate)
            # even though the column-position math (NSR=4/OSR=5/DSR=13) is
            # confirmed correct against bcftoys' actual page. Resetting
            # every chunk's columns to a plain 0..N-1 range before
            # concatenating forces pure POSITIONAL stacking -- exactly the
            # "trust column position, not header text" approach this file
            # already commits to for these wide bcftoys tables, now applied
            # consistently across chunks instead of just within one.
            positional_tables = []
            for t in same_shape_tables:
                t_pos = t.copy()
                t_pos.columns = range(t_pos.shape[1])
                positional_tables.append(t_pos)
            raw_df = pd.concat(positional_tables, ignore_index=True) if positional_tables else tables[0]
            print(f" -> [debug] bcftoys {key}: pd.read_html found {len(tables)} table(s) on the page, "
                  f"{len(same_shape_tables)} sharing tables[0]'s {tables[0].shape[1]}-column shape -- "
                  f"combined into {len(raw_df)} total rows (vs. {len(tables[0])} from tables[0] alone).")

            cols = {"Clean_Name": raw_df.iloc[:, 1].apply(clean_team_name)}
            for stat_name, pos in meta["cols"].items():
                if pos >= raw_df.shape[1]:
                    print(f" -> ⚠ bcftoys {key}: expected a column at position {pos} for {stat_name} "
                          f"but the table only has {raw_df.shape[1]} columns -- bcftoys likely changed "
                          f"its layout. Skipping {stat_name} this run rather than reading the wrong column.")
                    continue
                cols[stat_name] = pd.to_numeric(raw_df.iloc[:, pos], errors='coerce')
            df_clean = pd.DataFrame(cols)

            # One real row printed so a changed layout is obvious on sight
            # instead of silently reading the wrong column as a real stat.
            sample = df_clean[df_clean['Clean_Name'] == 'Ohio State']
            if not sample.empty:
                vals = {k: sample.iloc[0].get(k) for k in meta["cols"]}
                print(f" -> [debug] bcftoys {key} Ohio State this run: {vals} "
                      f"(cross-check at {url})")
            else:
                print(f" -> ⚠ bcftoys {key}: couldn't find 'Ohio State' in the parsed table at all -- "
                      f"the Team column position may have shifted. Cross-check at {url}.")

            # RAW ROW DUMP -- added 2026-09-20 to chase a real, still-open
            # bug: even after fixing the multi-table concat (which fixed
            # coverage) and switching to positional-not-label concat (which
            # did NOT fix this), a live run still shows garbage for teams
            # like Kent State -- its DFEI printed as "117.0" and DSR as
            # "133.0", both suspiciously exactly what that team's real RANK
            # is for those stats, not the real rate. Ohio State's own row
            # is fine every time. That pattern (good for one team, a
            # right-shifted rank number for another) points at something
            # going wrong INSIDE a single table's row parsing -- most likely
            # pd.read_html mishandling a rowspan/colspan cell (e.g. bcftoys
            # sharing one "Rk" cell across tied teams), which would silently
            # shorten just THAT row and shift every value after the missing
            # cell one column to the left -- rather than anything the concat
            # step does. Printing the COMPLETE raw row (every column, by
            # position) for both a known-good team and a known-bad one, side
            # by side, will show exactly where the two rows' cell counts or
            # values diverge -- can't diagnose this further without seeing
            # that directly, since the raw HTML for bcftoys.com wasn't available any other way.
            for watch_team in ("Ohio State", "Kent State"):
                watch_mask = raw_df.iloc[:, 1].apply(clean_team_name) == watch_team
                watch_rows = raw_df[watch_mask]
                if not watch_rows.empty:
                    for ridx, row in watch_rows.iterrows():
                        print(f" -> [rawrow] bcftoys {key} row for '{watch_team}' "
                              f"(raw_df index {ridx}, {len(row)} cells): {row.tolist()}")
                else:
                    print(f" -> [rawrow] bcftoys {key}: no row matched '{watch_team}' at all.")

            master = df_clean if master is None else pd.merge(master, df_clean, on="Clean_Name", how="outer")
        except Exception as e:
            print(f" -> ⚠ bcftoys {key} pull failed ({e}); {', '.join(meta['cols'])} will show as '--'.")

    if master is None:
        return pd.DataFrame(columns=['Clean_Name']), {}

    master = master.groupby('Clean_Name', as_index=False).first()
    league_avg = {col: master[col].mean() for col in master.columns if col != 'Clean_Name' and master[col].notna().any()}
    return master, league_avg


# ==========================================
# COLLEGEFOOTBALLDATA.COM: OFF/DEF PPA (EPA) AND STUFF RATE
# ==========================================
# CFBD requires a free API key -- get one at https://collegefootballdata.com/key
# and either set it as an environment variable (CFBD_API_KEY) or paste it
# into CFBD_API_KEY below. This script does NOT ship with a key and never
# will (an account/key is something only you can create) -- with no key
# set, this just prints that once and every CFBD-sourced number shows as
# '--', same honest-gap behavior as every other missing-data path in this
# file.
CFBD_API_KEY = os.environ.get("CFBD_API_KEY", "Mo7Q+Fh7LBrA8xWkxwZnKID6mnxvp+0FZAYgbEN1u+3vS1xpzFhkgAmn5PrZopl8")
_CFBD_BASE = "https://api.collegefootballdata.com"

# Real field names confirmed against CFBD's own official schema (the
# /stats/season/advanced response nests these under "offense"/"defense"
# sub-objects per team: offense.ppa, offense.stuffRate, defense.ppa,
# defense.stuffRate -- verified against the CFBD API's published schema,
# not guessed). ppa = "Predicted Points Added per play", CFBD's real name
# for the EPA-equivalent stat; stuffRate = share of opponent (offense) or
# own (defense) rush attempts stopped at or behind the line of scrimmage.
#
# Extended per request ("grab any stats I can use") with the rest of
# CFBD's real advanced-stats payload -- same endpoint, same call, no extra
# API cost. Field names cross-checked against the CFBD API's published
# schema (mirrored one-to-one, just snake_cased, in cfbfastR's documented
# columns for this exact endpoint -- cfbfastr.sportsdataverse.org/reference/
# cfbd_stats_season_advanced.html -- off_havoc_total, off_line_yds,
# off_second_lvl_yds, off_open_field_yds, off_power_success, off_success_rate,
# off_explosiveness and their def_ counterparts, which map straight back to
# CFBD's raw camelCase: offense.havoc.total, offense.lineYards,
# offense.secondLevelYards, offense.openFieldYards, offense.powerSuccess,
# offense.successRate, offense.explosiveness):
#   - havoc.total: rate of plays blown up by a TFL/forced fumble/INT/PBU.
#     Under "offense" it's the rate THIS team's own offense got disrupted
#     (lower is better); under "defense" it's the rate THIS team's defense
#     disrupts opponents (higher is better) -- same "offense = describes
#     this team's own unit" convention already established for PPA/stuff
#     rate above.
#   - lineYards / secondLevelYards / openFieldYards: Football-Outsiders-style
#     run-blocking zone breakdown (yards created 0-4/5-10/10+ yards past the
#     line) -- the closest real, free stand-in for PFF's O-line/run-blocking
#     grades. Higher is better on offense, lower is better on defense
#     (yards given up in that zone).
#   - powerSuccess: conversion rate on 3rd/4th-and-2-or-less and goal-to-go
#     runs -- short-yardage trench performance. Higher better on offense,
#     lower better on defense.
#   - successRate / explosiveness: CFBD's own down-and-distance-weighted
#     "did this play succeed" rate and its big-play (explosive play) index.
#     Higher better on offense, lower better on defense.
def _cfbd_advanced_json_with_fallback(url, headers, season_year):
    """CFBD season-advanced JSON; saves every good pull to disk and falls back to the last saved pull when CFBD
    refuses (e.g. HTTP 429 'Monthly call quota exceeded'), so the report keeps its PPA/havoc/line-yards numbers
    (slightly older) instead of showing '--' for every team."""
    cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cfb_cfbd_advanced_cache.json")
    try:
        resp = requests.get(url, headers=headers, params={"year": season_year}, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if data and isinstance(data, list):
            with open(cache_path, "w") as f:
                json.dump({"season_year": season_year, "fetched_at": datetime.now().isoformat(), "data": data}, f)
        return data
    except Exception as e:
        try:
            with open(cache_path) as f:
                saved = json.load(f)
            if saved.get("season_year") == season_year and saved.get("data"):
                print(f" -> ⚠ CFBD advanced stats pull failed ({e}) -- using the last saved pull from "
                      f"{saved.get('fetched_at')} instead (numbers are from that date).")
                return saved["data"]
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        raise


def fetch_cfbd_advanced_stats(season_year):
    """
    Pulls CFBD's real season-to-date advanced stats for every FBS team:
    offensive/defensive PPA, stuff rate, havoc rate, line/second-level/
    open-field yards, power success rate, success rate, and explosiveness.

    Returns (DataFrame with a 'Clean_Name' COLUMN -- not the index, same
    real fix/note as fetch_bcftoys_ratings() above -- and one column per
    stat above (Off_/Def_ prefixed), real-computed league-average dict for
    grading) -- both empty if no API key is set or the request fails.
    """
    if not CFBD_API_KEY:
        print(" -> ⚠ No CFBD_API_KEY set -- get a free one at https://collegefootballdata.com/key "
              "and set it as the CFBD_API_KEY environment variable. Off/Def PPA and stuff rate will "
              "show as '--' until then (not guessed).")
        return pd.DataFrame(columns=['Clean_Name']), {}

    url = f"{_CFBD_BASE}/stats/season/advanced"
    headers = {"Authorization": f"Bearer {CFBD_API_KEY}", "Accept": "application/json"}
    rows = []
    try:
        data = _cfbd_advanced_json_with_fallback(url, headers, season_year)
        if data and isinstance(data, list):
            # One real raw record printed so a schema change (CFBD does
            # occasionally rename/restructure fields) is visible immediately
            # instead of every value silently coming back None.
            _first_offense = data[0].get('offense') or {}
            print(f" -> [debug] CFBD raw keys on first record this run: {list(data[0].keys())} "
                  f"(offense sub-keys: {list(_first_offense.keys())}, "
                  f"offense.havoc sub-keys: {list((_first_offense.get('havoc') or {}).keys())})")
        for item in data:
            team_name = clean_team_name(item.get("team"))
            offense = item.get("offense") or {}
            defense = item.get("defense") or {}
            off_havoc = offense.get("havoc") or {}
            def_havoc = defense.get("havoc") or {}
            rows.append({
                "Clean_Name": team_name,
                "Off_PPA": offense.get("ppa"),
                "Def_PPA": defense.get("ppa"),
                "Off_Stuff_Rate": offense.get("stuffRate"),
                "Def_Stuff_Rate": defense.get("stuffRate"),
                "Off_Havoc": off_havoc.get("total"),
                "Def_Havoc": def_havoc.get("total"),
                "Off_Line_Yards": offense.get("lineYards"),
                "Def_Line_Yards": defense.get("lineYards"),
                "Off_Second_Level_Yards": offense.get("secondLevelYards"),
                "Def_Second_Level_Yards": defense.get("secondLevelYards"),
                "Off_Open_Field_Yards": offense.get("openFieldYards"),
                "Def_Open_Field_Yards": defense.get("openFieldYards"),
                "Off_Power_Success": offense.get("powerSuccess"),
                "Def_Power_Success": defense.get("powerSuccess"),
                "Off_Success_Rate": offense.get("successRate"),
                "Def_Success_Rate": defense.get("successRate"),
                "Off_Explosiveness": offense.get("explosiveness"),
                "Def_Explosiveness": defense.get("explosiveness"),
            })
    except Exception as e:
        print(f" -> ⚠ CFBD advanced stats pull failed ({e}); all CFBD-sourced numbers will show as '--'.")
        return pd.DataFrame(columns=['Clean_Name']), {}

    df = pd.DataFrame(rows)
    if df.empty:
        return df, {}

    # Defensive dedup -- same fix already applied in fetch_all_teamrankings_stats
    # (see the Tulane/Kansas State comment there) and fetch_bcftoys_ratings:
    # CFBD's season-advanced endpoint can return more than one row for the
    # same team in a realignment year (confirmed live on 2026-09-20 -- this
    # exact bug crashed a real run: a duplicated Clean_Name here survives the
    # merge into stats_lookup, and stats_lookup.set_index('Clean_Name') then
    # leaves that team with two rows sharing one index label, so
    # stats_lookup.loc[team_name] silently returns a 2-row DataFrame instead
    # of a Series -- every '.get()' call on it then returns a whole Series
    # instead of a scalar, which blew up with "The truth value of a Series
    # is ambiguous" the first time a real duplicate went through this path.
    # Collapsing to one row per Clean_Name (first non-null value wins, same
    # as the other two fetchers) fixes this at the source instead of leaving
    # every downstream .get() to defend against a shape it doesn't expect.
    dupes = df['Clean_Name'][df['Clean_Name'].duplicated(keep=False)].unique()
    if len(dupes):
        print(f" -> ⚠ CFBD returned more than one row for: {list(dupes)} "
              f"(likely a mid-season conference-realignment duplicate) -- keeping the first row for each.")
    df = df.groupby('Clean_Name', as_index=False).first()

    _CFBD_NUMERIC_COLS = [
        "Off_PPA", "Def_PPA", "Off_Stuff_Rate", "Def_Stuff_Rate",
        "Off_Havoc", "Def_Havoc",
        "Off_Line_Yards", "Def_Line_Yards",
        "Off_Second_Level_Yards", "Def_Second_Level_Yards",
        "Off_Open_Field_Yards", "Def_Open_Field_Yards",
        "Off_Power_Success", "Def_Power_Success",
        "Off_Success_Rate", "Def_Success_Rate",
        "Off_Explosiveness", "Def_Explosiveness",
    ]
    for c in _CFBD_NUMERIC_COLS:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    league_avg = {c: df[c].mean() for c in _CFBD_NUMERIC_COLS if df[c].notna().any()}
    return df, league_avg


# NEW: Off/Def points-per-drive, last 3 completed games,
# used for new.py's "Predicted Team Total"/"Spread" rows. This does NOT call CFBD
# itself -- cfb_ppd_cache_builder.py already does that (confirmed working
# against real data the same day: real startOffenseScore/endOffenseScore/
# startDefenseScore/endDefenseScore drive fields, method="score_delta",
# 137/138 teams cached) and is run as its own step right before this one
# (see cfb_run_all.py Step 0). This just reads that cache file -- a local
# read, no network, same "build a DataFrame mergeable into stats_lookup"
# shape every other fetch_*() above returns -- and prints the two new
# values into the ADVANCED RATINGS table below so new.py can pull them
# back out of the matrices PDF text the same way it reads every other
# stat on this sheet (via find_h_b()), instead of reading this cache
# file itself.
def load_ppd_cache():
    cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cfb_ppd_cache.json")
    empty = pd.DataFrame(columns=['Clean_Name', 'Off_PPD_L3', 'Def_PPD_L3'])
    try:
        with open(cache_path) as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        print(f" -> ⚠ no PPD cache found at {cache_path} ({e}) -- run cfb_ppd_cache_builder.py "
              f"(or cfb_run_all.py, which now runs it as Step 0) to generate it. OFF/DEF PPD "
              f"(LAST 3) will show as '--' on the report until then.")
        return empty

    rows = []
    for upper_name, vals in (cache.get("teams") or {}).items():
        rows.append({
            # Cache keys are clean_team_name(...).upper() (see
            # cfb_ppd_cache_builder.py) -- matched case-insensitively
            # against stats_lookup's own (non-uppercased) Clean_Name at
            # the merge site below, not relied on to match here.
            "Clean_Name": upper_name,
            "Off_PPD_L3": vals.get("off_ppd_l3"),
            "Def_PPD_L3": vals.get("def_ppd_l3"),
        })
    df = pd.DataFrame(rows) if rows else empty
    print(f" -> PPD cache loaded from {cache_path}: {len(df)} team(s) "
          f"(fetched_at={cache.get('fetched_at')}, games_used={cache.get('games_used')}, "
          f"method={cache.get('ppd_method')}).")
    return df


# ==========================================
# ESPN EXTRAS: FPI, OFF/DEF EFFICIENCY, QBR, TFL, TIME OF POSSESSION, FG%
# ==========================================
_ESPN_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
_ESPN_CORE_BASE = "https://sports.core.api.espn.com/v2/sports/football/leagues/college-football"


def fetch_espn_team_directory():
    """
    Builds a lookup of ESPN's internal numeric team ID -> our clean school
    name. Several ESPN "core" API feeds (Power Index, QBR, per-team season
    statistics) only return each team as a bare {"$ref": ".../teams/59"}
    pointer rather than an embedded name, so resolving those IDs back to a
    school name needs this directory built once up front from the light,
    already-embedded "site" teams list (the same API family the schedule
    scraper already uses successfully).

    Returns a dict: {"59": "Ohio State", ...}
    """
    url = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams"
    directory = {}
    try:
        # groups=80 returns every division, not just FBS, and limit=400 was truncating
        # the list at exactly 400 teams. That dropped a block of FBS team ids (32 of
        # the 138 in the power index had no match), so teams like Iowa, TCU, and
        # Oregon showed no FPI or SOR. Use a high limit and print the count returned
        # so any remaining cap is visible.
        resp = requests.get(url, headers=_ESPN_HEADERS, params={"groups": 80, "limit": 2000}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        for sport in data.get("sports", []):
            for league in sport.get("leagues", []):
                for entry in league.get("teams", []):
                    team = entry.get("team", entry)
                    tid = str(team.get("id", ""))
                    location = team.get("location") or team.get("displayName", "")
                    if tid:
                        directory[tid] = clean_team_name(location)
        print(f" -> [debug] ESPN team directory this run: {len(directory)} real team id(s) collected "
              f"(requested limit=2000) -- if this comes back as exactly 2000, the real total is even "
              f"higher and this limit needs raising again.")
    except Exception as e:
        print(f" -> ⚠ ESPN team directory pull failed ({e}); FPI/QBR/TFL numbers will show as '--'.")
    return directory


def build_name_to_id(team_directory):
    """name -> ESPN team id, for the per-team stats pulls. FIX (2026-10-06): this used to be a plain dict
    inversion, so when two ESPN entries cleaned down to the same school name (the directory also lists non-FBS
    schools -- that's why Troy and Charlotte 404'd every run), whichever came LAST silently won and the stats
    call went to the wrong team. Now the lowest numeric id wins (the real FBS schools have the low ids), and
    any name that had more than one id is printed so a wrong pick is visible instead of silent."""
    by_name = {}
    for tid, name in team_directory.items():
        by_name.setdefault(name, []).append(tid)
    out, dups = {}, []
    for name, tids in by_name.items():
        tids = sorted(tids, key=lambda t: int(t) if str(t).isdigit() else 10**9)
        out[name] = tids[0]
        if len(tids) > 1:
            dups.append(f"{name}: using {tids[0]} (also {', '.join(tids[1:])})")
    if dups:
        print(" -> [debug] ESPN team ids shared by more than one directory entry -- lowest id used: " + "; ".join(dups))
    return out


def _extract_team_id(ref_obj):
    """Pulls the trailing numeric team ID out of a {"$ref": ".../teams/59?..."} pointer."""
    ref = (ref_obj or {}).get("$ref", "")
    match = re.search(r"/teams/(\d+)", ref)
    return match.group(1) if match else None


def fetch_espn_power_index(season_year, week_number, team_directory):
    """
    Pulls ESPN's Football Power Index snapshot for the given week, which --
    conveniently -- bundles the overall FPI number together with ESPN's
    Offensive Efficiency and Defensive Efficiency sub-ratings in one payload,
    so a single request covers three of the requested numbers at once.

    Returns a dict: {"Ohio State": {"FPI": 14.2, "Off_Eff": 89.5, "Def_Eff": 90.2}, ...}

    NOTE on the response shape (confirmed against the raw JSON, not just a
    summarized description of it): FPI is NOT a flat field directly on each
    item. Each item looks like:
        {"team": {"$ref": ...},
         "predictives": [{"name": "fpi", "value": 30.4, ...}, {"name": "fpirank", ...}, ...],
         "efficiencies": [{"name": "offefficiency", "value": 89.6, ...}, {"name": "defefficiency", ...}, ...]}
    i.e. both "predictives" and "efficiencies" are lists of {name, value}
    entries that have to be searched by name, not dict keys you can .get()
    directly off the item.
    """
    week_number = week_number or 1
    url = f"{_ESPN_CORE_BASE}/seasons/{season_year}/types/2/weeks/{week_number}/powerindex"
    out = {}

    def _find_value(entries, name):
        for entry in entries or []:
            if entry.get("name") == name:
                return entry.get("value")
        return None

    # SOS (strength of schedule): unlike fpi/offefficiency/defefficiency
    # above, this wasn't verified against a live raw response before this
    # was written (the
    # exact \"name\" key couldn't be confirmed against ESPN's API). ESPN's FPI page always shows an SOS
    # column, so it's real and in this payload somewhere, but the literal
    # key could be "sos", "strengthofschedule", or something else -- this
    # tries the plausible candidates in order AND prints every real
    # {name: value} pair found on the first team's "predictives" list, so
    # whichever one is actually correct is visible in the console instead
    # of SOS just silently coming back '--' with no way to tell why.
    # CONFIRMED against a real live response (2026-09-22, via cfb_miss_stat_drift_check.py's
    # own debug dump): ESPN's Power Index API does NOT expose a raw decimal
    # SOS value at all -- only rank-based SOS fields. 'avgsosrank' (season-
    # to-date strength of schedule rank, 1 = toughest) is the real, present
    # field; 'sosremainingrank' (rest-of-season SOS rank) and 'topsosrank'
    # are also real but describe a different thing (future schedule, not
    # this team's played-so-far schedule) so they're kept as fallbacks
    # only, not tried first. This means every "SOS" number this project
    # has ever shown is a RANK now, not a raw score -- see the label change
    # in the PDF banner text below this function's docstring reference.
    _sos_candidates = ["avgsosrank", "sosremainingrank", "topsosrank"]
    # SOR (Strength of Record): CONFIRMED against a real live response
    # (2026-09-26, the run) that there is NO field literally named
    # "sor" anywhere in this payload -- the real 'predictives' list that
    # run was: ['fpi','fpirank','projectedw','projectedl','projectedt',
    # 'projectedwpctrank','probwinout','probwinconf','sosremainingrank',
    # 'accomplishment','accomplishmentrank','adjwins','adjlosses',
    # 'adjwinpctrank','gamecontrol','gamecontrolrank','adjavgingamewp',
    # 'adjavgingamewprank','avgingamewp','avgingamewprank','avgsosrank',
    # 'topsosrank','epaoffense','epadefense','epaspecialteams',
    # 'probwindiv','probmakeplayoffs','probmaketitlegame','numwins',
    # 'numlosses','numties','probwintitle','rankchange7days','prob6wins',
    # 'rank']. 'accomplishment'/'accomplishmentrank' is the real, present
    # candidate: real SOR is "the record a top-25-caliber team
    # would be expected to get against this exact same schedule, compared
    # to this team's real record" -- a schedule-adjusted resume grade, not
    # a performance rating like F+/FEI. 'accomplishment' paired with a
    # rank (same base-value/rank shape as avgsosrank) matches that concept
    # well, but the literal field name isn't confirmed from ESPN's own
    # docs, so cross-check the printed value against a real team's actual
    # SOR on espn.com/college-football/fpi (a debug line below prints one
    # team's real value each run for this).
    _sor_candidates = ["accomplishmentrank", "accomplishment"]
    _printed_predictives_sample = False
    _printed_sor_gap_sample = False
    _printed_unmapped_tid_sample = False

    def _find_sos(entries):
        for cand in _sos_candidates:
            v = _find_value(entries, cand)
            if v is not None:
                return v
        return None

    def _find_sor(entries):
        for cand in _sor_candidates:
            v = _find_value(entries, cand)
            if v is not None:
                return v
        return None

    try:
        # About two dozen teams (Iowa, TCU, Oregon, South Carolina, Purdue, etc.)
        # kept coming back with no FPI, SOR, or anything else. Ohio State's
        # accomplishmentrank matching the PDF rules out a SOR field-name bug, so
        # either (1) the ESPN core API paginates this endpoint and only page 1 was
        # being fetched, or (2) some numeric ids here never match a key in
        # team_directory (built from the "site" API), so the
        # "if not team_name: continue" check drops them. This follows pageCount to
        # handle (1) and prints a debug line to catch (2).
        all_items = []
        page_index = 1
        page_count = 1
        while page_index <= page_count:
            resp = requests.get(
                url, headers=_ESPN_HEADERS,
                params={"limit": 400, "pageIndex": page_index}, timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            page_items = data.get("items", [])
            all_items.extend(page_items)
            page_count = data.get("pageCount") or 1
            if page_index == 1:
                print(f" -> [debug] ESPN power index pagination this run: "
                      f"count={data.get('count')}, pageIndex={data.get('pageIndex')}, "
                      f"pageSize={data.get('pageSize')}, pageCount={page_count}, "
                      f"items on page 1={len(page_items)} -- if pageCount > 1, the old "
                      f"code was silently dropping every team on the later page(s).")
            page_index += 1

        pi_tids_seen = set()
        for item in all_items:
            tid = _extract_team_id(item.get("team"))
            if tid:
                pi_tids_seen.add(tid)
            team_name = team_directory.get(tid)
            if not team_name:
                if tid and not _printed_unmapped_tid_sample:
                    print(f" -> [debug] ESPN power index has a real team id ({tid}) with no "
                          f"match in team_directory -- this team will show as '--' for FPI/SOR/"
                          f"everything. Raw team ref: {item.get('team')}")
                    _printed_unmapped_tid_sample = True
                continue

            fpi_val = _find_value(item.get("predictives"), "fpi")
            sor_val = _find_sor(item.get("predictives"))

            if not _printed_predictives_sample:
                print(f" -> [debug] ESPN power index 'predictives' names available this run: "
                      f"{[e.get('name') for e in item.get('predictives') or []]} -- if SOS or SOR "
                      f"isn't showing up, the real key name is in that list; add it to _sos_candidates "
                      f"/ _sor_candidates above.")
                print(f" -> [debug] {team_name} real 'accomplishmentrank'/'accomplishment' this run: "
                      f"{sor_val} -- cross-check against this team's real SOR at "
                      f"https://www.espn.com/college-football/fpi to confirm this is really SOR "
                      f"(not confirmed by name from ESPN's own docs, just the closest real candidate).")
                _printed_predictives_sample = True

            # SOR shows up for most teams but not all, even when FPI (from the same
            # response and team entry) is present, so this isn't a missing-team problem;
            # it's specific to the accomplishment field for that team. Print the raw
            # entry once per run for the first team hit by this, so the actual ESPN
            # payload shape is visible.
            if fpi_val is not None and sor_val is None and not _printed_sor_gap_sample:
                print(f" -> [debug] {team_name} has real FPI ({fpi_val}) but no real accomplishment/"
                      f"accomplishmentrank this run -- raw predictives for this team: "
                      f"{item.get('predictives')}")
                _printed_sor_gap_sample = True

            out[team_name] = {
                "FPI": fpi_val,
                "Off_Eff": _find_value(item.get("efficiencies"), "offefficiency"),
                "Def_Eff": _find_value(item.get("efficiencies"), "defefficiency"),
                "SOS": _find_sos(item.get("predictives")),
                "SOR": sor_val,
            }

        # Full accounting:
        # this compares the real team ids ESPN's power index actually returned
        # against the real team ids in team_directory, both ways, so the exact
        # size and shape of the gap is visible instead of just one sample line.
        dir_tids = set(team_directory.keys())
        unmapped_pi_tids = pi_tids_seen - dir_tids
        missing_from_pi = dir_tids - pi_tids_seen
        missing_names = sorted(team_directory[t] for t in missing_from_pi)
        print(f" -> [debug] ESPN power index accounting this run: {len(pi_tids_seen)} real team id(s) "
              f"returned by the power index endpoint, {len(dir_tids)} real team id(s) in team_directory. "
              f"{len(unmapped_pi_tids)} power-index id(s) have no match in team_directory: "
              f"{sorted(unmapped_pi_tids)[:10]}{'...' if len(unmapped_pi_tids) > 10 else ''}. "
              f"{len(missing_from_pi)} real team_directory team(s) never appeared in the power index "
              f"items at all this run: {missing_names[:15]}{'...' if len(missing_names) > 15 else ''}.")
    except Exception as e:
        print(f" -> ⚠ ESPN FPI/efficiency pull failed ({e}); those numbers will show as '--'.")

    # NEW: persist this run's real fetched FPI/SOS/SOR data to a local cache file, so other
    # tools that can't reach ESPN themselves (e.g. the delta's-folder matchup report, new.py, which has no
    # network access at all) can read real, current numbers instead of working from no data or a stale
    # manually-run one-off snapshot. No hardcoded values in any PDF -- this cache is written ONLY
    # from this function's own real, live ESPN response, never a placeholder or guessed value. Written only
    # when the fetch actually returned something, so a failed run doesn't overwrite a good prior cache with an
    # empty one. Every real run of this function -- whether from cfb_working_schedule.py itself or from
    # cfb_matchup_deep_dive.py importing it directly -- refreshes this file with that run's real data.
    if out:
        try:
            cache_payload = {
                "fetched_at": datetime.utcnow().isoformat() + "Z",
                "season_year": season_year,
                "week_number": week_number,
                "teams": out,
            }
            with open("cfb_espn_power_index_cache.json", "w") as _cache_f:
                json.dump(cache_payload, _cache_f, indent=2)
        except Exception as cache_err:
            print(f" -> ⚠ couldn't write cfb_espn_power_index_cache.json ({cache_err}) -- this run's real "
                  f"FPI/SOS/SOR data is still used below, it just won't be cached for other tools to reuse.")

    return out


def fetch_espn_qbr(season_year, team_directory):
    """
    Pulls ESPN's season-to-date Total QBR leaderboard (qualifying QBs only,
    split=0 for season totals across FBS -- group 80). The feed is a flat,
    QBR-ranked list of individual quarterbacks rather than one row per team,
    so this groups by team and keeps each team's highest-QBR entry, which in
    practice is that team's starter (ESPN's own qualifying-attempts filter
    already screens out mop-up/backup snaps).

    Returns a dict: {"Ohio State": 82.4, ...}
    """
    url = f"{_ESPN_CORE_BASE}/seasons/{season_year}/types/2/groups/80/qbr/0"
    out = {}
    try:
        resp = requests.get(url, headers=_ESPN_HEADERS, params={"limit": 400}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("items", []):
            tid = _extract_team_id(item.get("team"))
            team_name = team_directory.get(tid)
            if not team_name:
                continue

            qbr_val = None
            for cat in item.get("splits", {}).get("categories", []):
                for stat in cat.get("stats", []):
                    if stat.get("name") == "qbr":
                        qbr_val = stat.get("value")
                        break
                if qbr_val is not None:
                    break

            if qbr_val is None:
                continue
            if team_name not in out or qbr_val > out[team_name]:
                out[team_name] = qbr_val
    except Exception as e:
        print(f" -> ⚠ ESPN QBR pull failed ({e}); QBR will show as '--'.")
    return out


_ESPN_STUFFS_DIAG_PRINTED = {"done": False}
_ESPN_STUFFS_FOUND_PRINTED = {"done": False}


def fetch_espn_extra_team_stats(team_id, season_year, team_name=None):
    """
    Pulls ESPN's per-team season statistics -- the only clean source found
    for tackles for loss (TeamRankings doesn't publish a team-level TFL
    stat for college football), time of possession, and field goal
    percentage. Called once per team that's actually playing this week
    (not all ~130 FBS teams), since it's a per-team endpoint rather than a
    single bulk page.

    Returns a dict of per-game/percentage-ready values, or an all-None dict
    on any failure so the report can fall back to '--' cleanly.
    """
    empty = {
        "TFL_Def_PG": None, "Stuffs_Off_PG": None,
        "ToP_Display": None, "FG_Pct": None,
    }
    url = f"{_ESPN_CORE_BASE}/seasons/{season_year}/types/2/teams/{team_id}/statistics"
    # FIX (2026-09-28): this endpoint has been timing out transiently under
    # back-to-back per-team calls -- real teams playing this week (Georgia,
    # Florida, Miami, Virginia Tech, South Carolina, Iowa State, Nevada,
    # Sam Houston State, Florida International, Wyoming, confirmed on a
    # real run) have hit this, not just teams ESPN genuinely lacks data
    # for. A real 404/4xx (e.g. Troy, Stonehill, Charlotte, Mercyhurst --
    # this endpoint just doesn't have them) is a permanent answer and is
    # NOT retried. A timeout/connection hiccup gets up to 2 retries with a
    # short pause first, since the whole point of this report is complete
    # real data whenever ESPN actually has it to give.
    resp = None
    last_exc = None
    for _attempt in range(3):
        try:
            resp = requests.get(url, headers=_ESPN_HEADERS, timeout=15)
            resp.raise_for_status()
            break
        except requests.exceptions.HTTPError as e:
            last_exc = e
            resp = None
            break
        except requests.exceptions.RequestException as e:
            last_exc = e
            resp = None
            if _attempt < 2:
                time.sleep(2)
    if resp is None:
        label = team_name or f"team_id={team_id}"
        print(f" -> [ESPN extra stats] {label} FAILED: real {type(last_exc).__name__}: {last_exc}")
        return empty

    try:
        data = resp.json()

        flat = {}
        for cat in data.get("splits", {}).get("categories", []):
            cat_name = cat.get("name")
            for stat in cat.get("stats", []):
                flat[(cat_name, stat.get("name"))] = stat.get("value")

        games = flat.get(("general", "gamesPlayed")) or 0
        tfl = flat.get(("defensive", "tacklesForLoss"))
        stuffs = flat.get(("rushing", "stuffs"))
        # Stuffs_Off_PG has been None for every team so far, so ("rushing", "stuffs")
        # is probably not ESPN's field name for this stat, or it's in another
        # category. Print every (category, stat_name) pair ESPN returns for this
        # team, once per run, to find the right key.
        if stuffs is None and not _ESPN_STUFFS_DIAG_PRINTED["done"]:
            _ESPN_STUFFS_DIAG_PRINTED["done"] = True
            print(f" -> DIAG: real ESPN stat keys available for {team_id} (looking for the real "
                  f"'stuffs' equivalent -- category, stat_name):")
            for (cat_name, stat_name) in sorted(flat.keys()):
                if "stuff" in stat_name.lower() or "loss" in stat_name.lower() or "tfl" in stat_name.lower():
                    print(f"      ** LIKELY MATCH ** ({cat_name!r}, {stat_name!r}) = {flat[(cat_name, stat_name)]!r}")
            print(f"    Full real key list: {sorted(flat.keys())}")
        elif stuffs is not None and not _ESPN_STUFFS_FOUND_PRINTED["done"]:
            _ESPN_STUFFS_FOUND_PRINTED["done"] = True
            label = team_name or team_id
            print(f" -> [debug] real ESPN 'stuffs' value confirmed present this run -- "
                  f"{label}: raw stuffs={stuffs!r}, games={games!r} -> Stuffs_Off_PG="
                  f"{round(stuffs / games, 1) if games else None!r}")
        top_secs = flat.get(("miscellaneous", "possessionTimeSeconds"))
        fg_pct = flat.get(("kicking", "fieldGoalPct"))
        # Note: ESPN's "passingYardsAfterCatch" field exists in their schema
        # but is never actually populated for college football -- it comes
        # back as a literal 0 for every team, every week (confirmed directly
        # against the raw feed), and neither ESPN nor TeamRankings publishes
        # a real team-level YAC/rushing-yards-after-contact number for CFB.
        # So this isn't scraped at all -- there's no real data to show.

        tfl_pg = round(tfl / games, 1) if tfl is not None and games else None
        stuffs_pg = round(stuffs / games, 1) if stuffs is not None and games else None

        top_display = None
        if top_secs is not None and games:
            avg_secs = top_secs / games
            top_display = f"{int(avg_secs // 60)}:{int(avg_secs % 60):02d}"

        return {
            "TFL_Def_PG": tfl_pg,
            "Stuffs_Off_PG": stuffs_pg,
            "ToP_Display": top_display,
            "FG_Pct": round(fg_pct, 1) if fg_pct is not None else None,
        }
    except Exception as e:
        # Log failures instead of swallowing them, as scrape_metric_group() now does.
        # TFL_Def_PG only has data for 27 of 48 historical games, which suggests this
        # path fails fairly often.
        label = team_name or f"team_id={team_id}"
        print(f" -> [ESPN extra stats] {label} FAILED: real {type(e).__name__}: {e}")
        return empty

# ==========================================
# PART 3: MATRIX STATS CONSOLIDATOR END
# ==========================================
# ==========================================
# PART 3.5: STAT-WEIGHTED WIN PREDICTION MODEL START
# ==========================================
# "Machine learning that learns from previous games" -- built in the same
# spirit as the rest of this project (nothing here is ever faked): this is
# a transparent, auditable WEIGHTED VOTING model, not a black-box. Every
# completed game gets recorded into a persistent history file
# (cfb_stat_history.json, saved next to this script) so the model actually
# accumulates knowledge across every day the script gets run, not just
# today's slate. For every stat, we track "which team led this stat, and
# did that team go on to win" across the full history, then a greedy
# weight-tuning pass combines whichever individually-predictive stats push
# backtest accuracy toward >80%, stopping as soon as the target is hit (or
# once adding more stats stops helping). Every accuracy number this
# produces is shown next to its real sample size (e.g. "17/20 = 85.0%"),
# never a bare percentage -- early-season sample sizes are small and that
# is disclosed here, not hidden.

_STAT_HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cfb_stat_history.json")
_TARGET_ACCURACY = 0.80

# (label, stats_lookup column key, higher_is_better) for every numeric
# per-team stat in stats_lookup that has a clean, defensible "which value
# is better" direction. Deliberately EXCLUDES:
#   - pure tempo/volume stats (Off_Plays_PG, Def_Plays_Faced_PG,
#     Off_Pass_Plays_PG, Off_Rush_Plays_PG, Def_Pass_Plays_PG,
#     Def_Rush_Plays_PG) -- more plays isn't "better," it's just pace.
#   - Home_Adv -- a fixed per-team historical constant, not a "who's
#     playing better" signal.
#   - SOS -- strength of schedule cuts both ways with no clean win-
#     direction (a tough schedule can mean a battle-tested team or just a
#     brutal slate that's beaten them up).
# Every other numeric column already in stats_lookup (TeamRankings raw
# production/allowed, ESPN FPI/efficiency/QBR/FG%/TFL/turnover margin, and
# the bcftoys F+/FEI/DSR + CFBD advanced-stats columns added earlier in
# this file) is included.
_STAT_SIGNAL_SPECS = [
    # -- TeamRankings core production/allowed --
    ("Off Yards/Game", "Off_Yds_PG", True), ("Def Yards/Game Allowed", "Def_Yds_PG", False),
    ("Off Yards/Play", "Off_YPP", True), ("Def Yards/Play Allowed", "Def_YPP", False),
    ("Off Pass Yards/Game", "Off_Pass_PG", True), ("Def Pass Yards/Game Allowed", "Def_Pass_PG", False),
    ("Off Yards/Pass Attempt", "Off_Pass_Att", True), ("Def Yards/Pass Att Allowed", "Def_Pass_Att", False),
    ("Off Rush Yards/Game", "Off_Rush_PG", True), ("Def Rush Yards/Game Allowed", "Def_Rush_PG", False),
    ("Off Yards/Rush Attempt", "Off_Rush_Att", True), ("Def Yards/Rush Att Allowed", "Def_Rush_Att", False),
    ("Off Points/Game", "Off_PPG", True), ("Def Points/Game Allowed", "Def_PPG", False),
    ("Off 3rd Down %", "Off_3rd_%", True), ("Def 3rd Down % Allowed", "Def_3rd_%", False),
    ("Off Red Zone %", "Off_RZ_%", True), ("Def Red Zone % Allowed", "Def_RZ_%", False),
    ("Off Sacks Allowed/Game", "Off_Sacks_Allowed_PG", False), ("Def Sacks/Game", "Def_Sacks_PG", True),
    # -- ESPN extras --
    ("FPI", "FPI", True),
    ("Off Efficiency", "Off_Eff", True), ("Def Efficiency", "Def_Eff", False),
    ("QBR", "QBR", True),
    ("FG%", "FG_Pct", True),
    ("Def TFL/Game", "TFL_Def_PG", True), ("Off Stuffs Allowed/Game", "Stuffs_Off_PG", False),
    ("Net Turnover Margin", "Net_TO_Margin", True),
    # -- bcftoys advanced ratings --
    ("F+", "F+", True), ("Off F+", "OF+", True), ("Def F+", "DF+", True),
    ("FEI", "FEI", True), ("Off FEI", "OFEI", True), ("Def FEI", "DFEI", True),
    ("Net Success Rate", "NSR", True), ("Off Success Rate (bcftoys)", "OSR", True),
    ("Opp Success Rate Allowed (DSR)", "DSR", False),
    # -- CFBD advanced stats --
    ("Off PPA", "Off_PPA", True), ("Def PPA Allowed", "Def_PPA", False),
    ("Off Stuff Rate (suffered)", "Off_Stuff_Rate", False), ("Def Stuff Rate (forced)", "Def_Stuff_Rate", True),
    ("Off Havoc Rate (suffered)", "Off_Havoc", False), ("Def Havoc Rate (forced)", "Def_Havoc", True),
    ("Off Line Yards", "Off_Line_Yards", True), ("Def Line Yards Allowed", "Def_Line_Yards", False),
    ("Off 2nd Level Yards", "Off_Second_Level_Yards", True), ("Def 2nd Level Yards Allowed", "Def_Second_Level_Yards", False),
    ("Off Open Field Yards", "Off_Open_Field_Yards", True), ("Def Open Field Yards Allowed", "Def_Open_Field_Yards", False),
    ("Off Power Success Rate", "Off_Power_Success", True), ("Def Power Success Rate Allowed", "Def_Power_Success", False),
    ("Off Success Rate (CFBD)", "Off_Success_Rate", True), ("Def Success Rate Allowed (CFBD)", "Def_Success_Rate", False),
    ("Off Explosiveness", "Off_Explosiveness", True), ("Def Explosiveness Allowed", "Def_Explosiveness", False),
]

# Quick key -> higher_is_better lookup, built once from the spec list above,
# so the live (not-yet-played) matchup pick below doesn't have to re-scan
# _STAT_SIGNAL_SPECS for every included stat on every game.
_HIGHER_IS_BETTER_BY_KEY = {key: higher_is_better for _label, key, higher_is_better in _STAT_SIGNAL_SPECS}


def load_stat_history():
    """Loads the persistent cross-run game/vote history from disk. Returns
    the {"games": {}} fallback structure if the file doesn't exist yet or
    is unreadable, so a first-ever run (or a corrupted file) never crashes
    the report -- it just starts the model from zero history."""
    try:
        with open(_STAT_HISTORY_PATH, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "games" not in data:
            return {"games": {}}
        return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"games": {}}


def save_stat_history(history):
    """Writes the history back to disk. Best-effort -- a write failure
    (e.g. a read-only filesystem) shouldn't take down the whole report,
    since the PDF itself doesn't strictly depend on persistence succeeding
    for THIS run (it just means today's new games won't be there next
    time)."""
    try:
        with open(_STAT_HISTORY_PATH, "w") as f:
            json.dump(history, f, indent=2)
    except OSError as e:
        print(f" -> ⚠ Couldn't save stat history to disk ({e}); this run's newly completed games won't persist for next time.")


def _stat_vote(winner_val, loser_val, higher_is_better):
    """Returns +1 if the eventual WINNER led this stat, -1 if the loser
    led it, or None if the stat is missing or tied for this game (a tie
    casts no vote either way -- it's not evidence for either team)."""
    if winner_val is None or loser_val is None:
        return None
    try:
        w, l = float(winner_val), float(loser_val)
    except (TypeError, ValueError):
        return None
    if pd.isna(w) or pd.isna(l):
        return None
    if w == l:
        return None
    winner_led = (w > l) if higher_is_better else (w < l)
    return 1 if winner_led else -1


def _live_stat_lean(away_val, home_val, higher_is_better):
    """Same idea as _stat_vote() above, but for a game that HASN'T been
    played yet -- there's no winner/loser to compare against, so this
    compares the away side directly to the home side instead. Returns +1 if
    AWAY currently leads this stat, -1 if HOME does, or None if either
    value is missing or the two are tied (a tie casts no vote, same as
    _stat_vote)."""
    if away_val is None or home_val is None:
        return None
    try:
        a, h = float(away_val), float(home_val)
    except (TypeError, ValueError):
        return None
    if pd.isna(a) or pd.isna(h):
        return None
    if a == h:
        return None
    away_leads = (a > h) if higher_is_better else (a < h)
    return 1 if away_leads else -1


def stat_vote_model_pick(away_ts, home_ts, included_stats):
    """Applies the SAME tuned weighted stat set that tune_stat_weights()
    selected and _backtest_accuracy() scores historically, to one specific
    upcoming matchup's CURRENT real stats -- i.e. this is the live version
    of the exact model the report's headline accuracy number describes, so
    "which team does the model pick" means precisely that model, not a
    separate guess.

    Mirrors _backtest_accuracy()'s own "score == 0 -> not decided" rule
    exactly: if the included stats fully cancel out, or none of them have
    real data for both teams, this correctly returns None (no pick) rather
    than breaking a tie arbitrarily.

    Returns 'away', 'home', or None.
    """
    if not included_stats:
        return None
    score = 0.0
    for _label, key, weight, _win_rate, _n in included_stats:
        higher_is_better = _HIGHER_IS_BETTER_BY_KEY.get(key)
        if higher_is_better is None:
            continue
        away_val = away_ts.get(key) if hasattr(away_ts, "get") else None
        home_val = home_ts.get(key) if hasattr(home_ts, "get") else None
        lean = _live_stat_lean(away_val, home_val, higher_is_better)
        if lean is not None:
            score += weight * lean
    if score > 0:
        return "away"
    if score < 0:
        return "home"
    return None


def compute_sacks_agreement_breakdown(history, included_keys, weights):
    """Tested finding: games where the model's own
    weighted pick and Def Sacks/Game favor the SAME team vs. games where
    they favor DIFFERENT teams -- and the model's real hit rate in each
    group. Recomputed fresh every run (not a hardcoded snapshot) so the
    PDF's caution-flag caption always reflects the current real numbers,
    the same way the headline accuracy % already does.

    Returns a dict: {"agree": (hits, n), "disagree": (hits, n)} -- 'agree'
    also covers games where Def_Sacks_PG had no real data (that bucket
    was 100% on record too, so it's treated as "not flagged" the same way
    _pick_is_risky() in generate_pdf_report does)."""
    agree_hits = agree_n = disagree_hits = disagree_n = 0
    for game in history["games"].values():
        votes = game.get("votes", {})
        score = sum(weights.get(k, 0) * votes[k] for k in included_keys if k in votes)
        if score == 0:
            continue
        winner, loser = game.get("winner"), game.get("loser")
        model_pick = loser if score < 0 else winner
        is_hit = (model_pick == winner)

        sacks_vote = votes.get("Def_Sacks_PG")
        sacks_favors = None if sacks_vote is None else (winner if sacks_vote == 1 else loser)

        if sacks_favors is None or sacks_favors == model_pick:
            agree_n += 1
            agree_hits += 1 if is_hit else 0
        else:
            disagree_n += 1
            disagree_hits += 1 if is_hit else 0

    return {"agree": (agree_hits, agree_n), "disagree": (disagree_hits, disagree_n)}


# Same exact boundaries as cfb_fei_margin_check.py's own `edges` and
# cfb_weekly_diagnostics_check.py's MARGIN_EDGES (kept in sync by hand,
# same convention used elsewhere in this file) -- so the "narrow"/"wide"
# label on a live PDF page always means the exact same thing as it does in
# either research script's report.
_MARGIN_EDGES = [(0.0, 0.15, "very narrow"), (0.15, 0.35, "narrow"),
                  (0.35, 0.70, "moderate"), (0.70, 999.0, "wide")]


def _bucket_label(margin, edges):
    for lo, hi, label in edges:
        if lo <= margin < hi:
            return label
    return "other"


def compute_margin_bucket_stats(history, included_keys, weights, stats_lookup, margin_key):
    """Real historical miss rate for each margin bucket (very narrow/
    narrow/moderate/wide) of the given rating (FEI or F+), computed the
    same way cfb_fei_margin_check.py's own bucket table is -- every decided
    stat-vote game, TODAY's current rating for both teams (a real,
    disclosed post-hoc limitation: bcftoys doesn't publish a historical
    week-by-week archive, so this can't be a frozen game-day snapshot),
    bucketed by the real gap between them. Returns {bucket_label: (n,
    misses)}. Added per request (2026-09-22) so the live PDF shows the
    same narrow/wide context the research scripts do, not just the
    terminal output."""
    buckets = {label: [0, 0] for _, _, label in _MARGIN_EDGES}  # [n, misses]
    for game in history["games"].values():
        votes = game.get("votes", {})
        score = sum(weights.get(k, 0) * votes[k] for k in included_keys if k in votes)
        if score == 0:
            continue
        is_miss = score < 0
        winner, loser = game.get("winner"), game.get("loser")
        if winner not in stats_lookup.index or loser not in stats_lookup.index:
            continue
        w_ts, l_ts = stats_lookup.loc[winner], stats_lookup.loc[loser]
        if isinstance(w_ts, pd.DataFrame):
            w_ts = w_ts.iloc[0]
        if isinstance(l_ts, pd.DataFrame):
            l_ts = l_ts.iloc[0]
        try:
            wv, lv = float(w_ts.get(margin_key)), float(l_ts.get(margin_key))
        except (TypeError, ValueError):
            continue
        margin = abs(wv - lv)
        label = _bucket_label(margin, _MARGIN_EDGES)
        if label not in buckets:
            continue
        buckets[label][0] += 1
        buckets[label][1] += 1 if is_miss else 0
    return {label: tuple(v) for label, v in buckets.items()}


def _format_margin_with_bucket(margin, bucket_stats):
    """'0.160 (narrow, 14.3% historical miss)' -- or 'n/a' if the margin
    itself is missing, or '(bucket, n/a)' if that bucket has no real
    historical games in it yet."""
    if margin is None or bucket_stats is None:
        return "n/a"
    label = _bucket_label(margin, _MARGIN_EDGES)
    n, misses = bucket_stats.get(label, (0, 0))
    if n == 0:
        return f"{margin:.3f} ({label}, n/a)"
    rate = misses / n * 100
    return f"{margin:.3f} ({label}, {rate:.1f}% miss)"


def record_completed_games(history, schedule_df, stats_lookup):
    """Scans today's schedule for real ESPN-confirmed COMPLETED games and
    records each one's per-stat votes into the persistent history, keyed by
    ESPN's own Event_Id so re-running the script later today (or any other
    day) never double-counts the same game. Returns how many NEW games
    were recorded this run."""
    if schedule_df is None or schedule_df.empty or "Completed" not in schedule_df.columns:
        return 0

    new_count = 0
    for _, row in schedule_df.iterrows():
        if not row.get("Completed") or not row.get("Winner"):
            continue
        event_id = row.get("Event_Id")
        if event_id is None:
            continue
        event_id = str(event_id)
        if event_id in history["games"]:
            continue

        away, home = row["Away_Team"], row["Home_Team"]
        winner = row["Winner"]
        loser = home if winner == away else away
        if winner not in stats_lookup.index or loser not in stats_lookup.index:
            continue

        winner_ts = stats_lookup.loc[winner]
        loser_ts = stats_lookup.loc[loser]
        # Same duplicate-index guard used elsewhere in this file (see the
        # comment above the stats_lookup dedup in main()) -- if a stray
        # duplicate Clean_Name ever slips through, .loc[] returns a
        # multi-row DataFrame instead of a Series, and every stat lookup
        # below would silently break. Falling back to the first row keeps
        # this one game's recording going instead of crashing the report.
        if isinstance(winner_ts, pd.DataFrame):
            winner_ts = winner_ts.iloc[0]
        if isinstance(loser_ts, pd.DataFrame):
            loser_ts = loser_ts.iloc[0]

        votes = {}
        for label, key, higher_is_better in _STAT_SIGNAL_SPECS:
            wv = winner_ts.get(key) if hasattr(winner_ts, "get") else None
            lv = loser_ts.get(key) if hasattr(loser_ts, "get") else None
            vote = _stat_vote(wv, lv, higher_is_better)
            if vote is not None:
                votes[key] = vote

        history["games"][event_id] = {
            "date": row.get("Date"),
            "away": away, "home": home,
            "away_score": row.get("Away_Score"), "home_score": row.get("Home_Score"),
            "winner": winner, "loser": loser,
            "votes": votes,
        }
        new_count += 1

    if new_count:
        save_stat_history(history)
    return new_count


def _individual_stat_win_rates(history):
    """For every stat, what % of games did the team that led it go on to
    win, and over how many games. Filtered to stats with at least 3 games
    of signal -- below that, a "100%" or "0%" reading is just noise, not a
    real pattern."""
    tallies = {}
    for game in history["games"].values():
        for key, vote in game.get("votes", {}).items():
            t = tallies.setdefault(key, [0, 0])  # [correct, total]
            t[1] += 1
            if vote == 1:
                t[0] += 1
    results = {}
    for key, (correct, total) in tallies.items():
        if total >= 3:
            results[key] = (correct / total, total)
    return results


def _backtest_accuracy(history, included_keys, weights):
    """Runs the given weighted stat set against every recorded game and
    returns (correct, decided, total) -- 'decided' is games where at least
    one included stat actually cast a vote (a game with zero overlapping
    signal is neither a hit nor a miss, it's just unscored)."""
    correct, decided, total = 0, 0, 0
    for game in history["games"].values():
        total += 1
        votes = game.get("votes", {})
        score = sum(weights.get(k, 0) * votes[k] for k in included_keys if k in votes)
        if score == 0:
            continue
        decided += 1
        if score > 0:
            correct += 1
    return correct, decided, total


# NEW: FEI is always part of the stat-vote model. The learning step used to be free to drop it
# (it did, on 2026-10-04, when Off Points/Game edged it 79.9% to 79.4% on the season so far); now it is seeded in as
# the first stat and the greedy search only decides what ELSE to add on top. Set to () to go back to fully automatic.
_REQUIRED_STAT_KEYS = ("FEI",)


def tune_stat_weights(history, target_accuracy=_TARGET_ACCURACY):
    """Greedy forward-selection: repeatedly adds whichever remaining stat
    improves combined backtest accuracy the most, and keeps going until
    NOTHING left improves it any further -- it does not stop the moment
    accuracy clears the 80% target. That means it shoots for the highest
    accuracy it can actually find (ideally 100%), rather than settling for
    "good enough" and leaving other genuinely useful stats on the table
    (a single very strong stat like FEI can clear 80% on its own early in
    the season, but that doesn't mean it's using everything available --
    this keeps testing every remaining stat against the current best
    combination and only stops when adding the single best remaining
    candidate no longer beats what's already included). target_accuracy is
    kept only as the number reported/colored against in the PDF ("target:
    80%") -- it no longer controls when the search stops.

    Each included stat's weight is (its own individual win rate - 0.5), so
    a stat that's right 70% of the time on its own gets weight 0.2, a
    coin-flip stat (50%) contributes nothing, and nothing ever pulls votes
    in the "wrong" direction. Requires at least 60% of history to produce
    an actual decided pick before a candidate counts -- a stat that leaves
    too many games undecided is skipped rather than let a lucky 2-game
    streak look like a breakthrough.

    Returns (included, accuracy, correct, decided, total_games) where
    included is a list of (label, key, weight, individual_win_rate,
    sample_size) tuples for the stats that made the final cut, in the
    order they were added (most impactful first)."""
    win_rates = _individual_stat_win_rates(history)
    total_games = len(history["games"])
    label_by_key = {key: label for label, key, _ in _STAT_SIGNAL_SPECS}

    # Only stats that beat a coin flip are useful as positive-weight votes.
    candidates = {k: wr for k, (wr, n) in win_rates.items() if wr > 0.5}
    weights = {k: (win_rates[k][0] - 0.5) for k in candidates}

    included_keys = []
    best_accuracy, best_correct, best_decided = 0.0, 0, 0
    remaining = set(candidates.keys())
    min_decided = max(1, int(round(total_games * 0.6))) if total_games else 0
    # Pinned stats go in first (only if they actually beat a coin flip on this history, so a pinned stat can
    # never vote the wrong way); the search below then keeps adding whatever else improves accuracy.
    for _req in _REQUIRED_STAT_KEYS:
        if _req in remaining:
            included_keys.append(_req)
            remaining.discard(_req)
    if included_keys:
        _c, _d, _t = _backtest_accuracy(history, included_keys, weights)
        if _d:
            best_accuracy, best_correct, best_decided = _c / _d, _c, _d

    while remaining:
        best_add, best_add_result = None, None
        # FIX (reproduced against the actual
        # cfb_stat_history.json -- confirmed by running this function under
        # several different PYTHONHASHSEED values on the identical, real
        # 48-game history and getting a DIFFERENT included stat set each
        # time, e.g. ['F+','FEI','Off_Havoc'] vs ['FEI','F+','Def_Power_
        # Success'], both landing on the exact same 42/48 = 87.5% accuracy):
        # iterating a plain `set` here meant that whenever two candidate
        # stats tied exactly on marginal accuracy (`acc > best_add_result[0]`
        # is a strict >, so whichever candidate the loop reaches FIRST wins
        # a tie), the winner depended on Python's per-process string-hash
        # randomization -- not on anything about the stats themselves. That
        # meant the live model's actual stat set (and therefore its actual
        # picks on games where the tied stats disagreed) could silently
        # change between two runs of this exact script on the exact same
        # data. Iterating a deterministic ordering instead -- sorted by each
        # candidate's own individual win rate (a real, defensible tie-break:
        # prefer the stronger standalone predictor), then by key name only
        # as a final tiebreak for full reproducibility -- makes tie
        # resolution depend only on the data, never on process-level
        # randomness.
        for k in sorted(remaining, key=lambda kk: (-weights[kk], kk)):
            trial_keys = included_keys + [k]
            correct, decided, _total = _backtest_accuracy(history, trial_keys, weights)
            if decided < min_decided:
                continue
            acc = correct / decided if decided else 0.0
            if best_add_result is None or acc > best_add_result[0]:
                best_add, best_add_result = k, (acc, correct, decided)
        if best_add is None:
            break  # nothing left clears the min-decided bar
        acc, correct, decided = best_add_result
        if acc <= best_accuracy and included_keys:
            # Adding anything else no longer helps -- stop rather than
            # dilute a model that already found its best combination.
            break
        included_keys.append(best_add)
        remaining.discard(best_add)
        best_accuracy, best_correct, best_decided = acc, correct, decided
        # No early exit on hitting target_accuracy -- keeps testing every
        # remaining stat against the current best combination, shooting for
        # the highest accuracy actually achievable (not just "cleared 80%").

    included = [
        (label_by_key.get(k, k), k, weights[k], win_rates[k][0], win_rates[k][1])
        for k in included_keys
    ]
    return included, best_accuracy, best_correct, best_decided, total_games


def generate_miss_postmortems(history, included_keys, weights, max_items=8):
    """For games the tuned model picked WRONG, lists which stats favored
    the real winner but were outweighed (or not included at all) -- this
    is the "what it would do different" description: concretely, which
    signals it should have leaned on more for this game. Returns the most
    recent misses first, capped at max_items so the PDF section stays a
    reasonable length."""
    label_by_key = {key: label for label, key, _ in _STAT_SIGNAL_SPECS}
    postmortems = []

    for game in history["games"].values():
        votes = game.get("votes", {})
        score = sum(weights.get(k, 0) * votes[k] for k in included_keys if k in votes)
        if score >= 0:
            continue  # model got this one right (or had no opinion either way)

        # Which stats -- included in the model or not -- actually favored
        # the real winner on this game, ranked by how individually
        # reliable that stat has been across all history (most trustworthy
        # first), so the postmortem highlights the strongest missed signal.
        favored_winner = []
        for key, vote in votes.items():
            if vote != 1:
                continue
            label = label_by_key.get(key, key)
            reliability = weights.get(key, 0) + 0.5 if key in weights else 0.5
            favored_winner.append((key, label, reliability))
        favored_winner.sort(key=lambda x: x[2], reverse=True)

        postmortems.append({
            "date": game.get("date"),
            "away": game.get("away"), "home": game.get("home"),
            "winner": game.get("winner"), "loser": game.get("loser"),
            "away_score": game.get("away_score"), "home_score": game.get("home_score"),
            "favored_winner": favored_winner[:6],
        })

    return postmortems[-max_items:]

# ==========================================
# PART 3.5: STAT-WEIGHTED WIN PREDICTION MODEL END
# ==========================================
# ==========================================
# PART 4: PDF DOCUMENT GENERATOR START
# ==========================================
def _xml_escape(text):
    """Escapes characters that would otherwise break ReportLab's Paragraph
    markup parser (e.g. the '&' in 'Texas A&M')."""
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _is_missing(val):
    """True for None, and for NaN -- which is what a missing value in a
    pandas DataFrame column actually becomes after a merge/concat (not
    None), so checking `val is None` alone silently lets 'nan' leak into
    the rendered PDF text instead of '--'."""
    if val is None:
        return True
    try:
        return bool(pd.isna(val))
    except (TypeError, ValueError):
        return False


def _fmt_signed(val):
    """Formats a margin-style number (turnover margin, point differential)
    with an explicit '+' on positive values; returns '--' on anything
    missing or non-numeric."""
    if _is_missing(val):
        return "--"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "--"
    if v == int(v):
        v_str = str(int(v))
    else:
        v_str = f"{v:.1f}"
    return f"+{v_str}" if v > 0 else v_str


def _fmt_num(val, decimals=1, suffix=""):
    """Formats a plain numeric stat, falling back to '--' when missing."""
    if _is_missing(val):
        return "--"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "--"
    if decimals == 0:
        return f"{v:.0f}{suffix}"
    return f"{v:.{decimals}f}{suffix}"


def _num(val):
    """Best-effort float conversion for a scraped stat -- returns None
    (never a crash, never a silent 0) for anything missing/non-numeric."""
    if _is_missing(val) or val == '--':
        return None
    try:
        return float(str(val).replace('%', ''))
    except (TypeError, ValueError):
        return None


# ==========================================
# PART 3.5: GAME-FLOW FORECAST ENGINE START
# ==========================================
# NOTE: _FORECAST_WEIGHTS below is now
# ONLY a fallback. The real, data-fitted margin model lives in
# cfb_matchup_deltas.py (tune_forecast_weights, an actual OLS regression
# against real completed games' real final margins -- same spirit as
# tune_stat_weights() above, just continuous instead of classification).
# main() fits it fresh each run and passes it into build_matchup_forecast()
# as fitted_margin_model; these hand-picked weights only get used when
# there isn't yet enough real recorded history to trust a fit (see
# MIN_MARGIN_SAMPLES), or when build_matchup_forecast() is called without
# a fitted model at all (the_skinny.py's own call site doesn't pass one).
#
# Original reasoning for the hand-picked numbers below (kept for when the
# fallback fires): not every stat is an equally good predictor of the
# final margin, so the forecast blends several independent "who wins this
# margin" estimates through explicit weights rather than averaging
# everything equally:
#   - FPI is ESPN's own opponent-adjusted power rating (it's already
#     built from a full season of results against schedule strength), so
#     it gets the largest single weight.
#   - Off/Def efficiency ratings are also opponent-adjusted and are widely
#     regarded (see: Bill Connelly's SP+, Football Outsiders' DVOA-style
#     work) as better predictors of future scoring than raw box-score
#     numbers, so they're weighted above raw points or yardage.
#   - Raw points-per-game (offense vs. opponent's points allowed) is real
#     signal but noisier (garbage time, opponent quality varies game to
#     game), so it's weighted below FPI/efficiency.
#   - Yards-per-play is a solid but secondary efficiency signal.
#   - Turnover margin is high-variance/less persistent week to week, so it
#     gets the smallest weight even though a single game's turnovers can
#     swing the outcome.
# Weights sum to 1.0; if any single factor's inputs are missing for this
# matchup, it's dropped and the remaining weights are renormalized instead
# of silently biasing the projection toward zero.
_FORECAST_WEIGHTS = {
    'fpi': 0.35,
    'efficiency': 0.25,
    'scoring': 0.20,
    'yardage': 0.10,
    'turnovers': 0.10,
}


def compute_forecast_factors(away_ts, home_ts):
    """Extracted from build_matchup_forecast (2026-09-27, part of making
    the margin/spread forecast real -- see _FORECAST_WEIGHTS' comment and
    the fitted_margin_model parameter below): the five independent
    home-minus-away point-margin estimates (FPI, efficiency, scoring,
    yardage, turnovers), each simply absent from the returned dict when
    this matchup is missing that factor's real inputs -- never a guessed
    zero. Split out into its own function so cfb_matchup_deltas.py's real
    margin-regression backfill/training code can call the EXACT same live
    logic build_matchup_forecast() itself uses, rather than a separate
    reimplementation that could silently drift from it.

    Returns (factors, home_scoring_proj, away_scoring_proj), or
    (None, None, None) if the core PPG inputs aren't available for both
    teams (nothing to safely project)."""
    def g(ts, key):
        return _num(ts.get(key) if hasattr(ts, 'get') else None)

    home_off_ppg, away_def_ppg = g(home_ts, 'Off_PPG'), g(away_ts, 'Def_PPG')
    away_off_ppg, home_def_ppg = g(away_ts, 'Off_PPG'), g(home_ts, 'Def_PPG')
    if None in (home_off_ppg, away_def_ppg, away_off_ppg, home_def_ppg):
        return None, None, None

    # ---- Each factor below is its own home-minus-away point-margin
    # estimate; None means "no data for this matchup", which drops that
    # factor out of the weighted blend rather than counting as a zero edge.
    factors = {}

    home_fpi, away_fpi = g(home_ts, 'FPI'), g(away_ts, 'FPI')
    if home_fpi is not None and away_fpi is not None:
        # FPI is already scaled in expected-points-vs-average-team terms,
        # so the raw gap between the two teams' FPI *is* a point margin.
        factors['fpi'] = home_fpi - away_fpi

    home_oeff, away_deff = g(home_ts, 'Off_Eff'), g(away_ts, 'Def_Eff')
    away_oeff, home_deff = g(away_ts, 'Off_Eff'), g(home_ts, 'Def_Eff')
    if None not in (home_oeff, away_deff, away_oeff, home_deff):
        # Efficiency ratings are 0-100-ish scores, not points -- scale the
        # double-differential down onto a game-point scale.
        eff_gap = (home_oeff - away_deff) - (away_oeff - home_deff)
        factors['efficiency'] = eff_gap * 0.3

    home_scoring_proj = (home_off_ppg + away_def_ppg) / 2
    away_scoring_proj = (away_off_ppg + home_def_ppg) / 2
    factors['scoring'] = home_scoring_proj - away_scoring_proj

    home_oypp, away_dypp = g(home_ts, 'Off_YPP'), g(away_ts, 'Def_YPP')
    away_oypp, home_dypp = g(away_ts, 'Off_YPP'), g(home_ts, 'Def_YPP')
    if None not in (home_oypp, away_dypp, away_oypp, home_dypp):
        ypp_gap = (home_oypp - away_dypp) - (away_oypp - home_dypp)
        # Rule-of-thumb conversion: roughly 4 points of scoring advantage
        # per extra net yard-per-play edge across a full game's snap count.
        factors['yardage'] = ypp_gap * 4.0

    home_to, away_to = g(home_ts, 'Net_TO_Margin'), g(away_ts, 'Net_TO_Margin')
    if home_to is not None and away_to is not None:
        # Rule-of-thumb conversion: roughly 4 points of expected value per
        # net turnover.
        factors['turnovers'] = (home_to - away_to) * 4.0

    return factors, home_scoring_proj, away_scoring_proj


def compute_home_field_adv(home_ts):
    """Extracted from build_matchup_forecast (2026-09-27, same reason as
    compute_forecast_factors above): this specific team's real, scraped
    home-advantage rating (TeamRankings) when available -- it varies
    enormously by program (research: roughly +9.5 for a team like
    Jacksonville State down to negative for a team that historically plays
    worse at home) -- rather than a flat number applied to every team
    alike. Falls back to 2.6, the researched CFB-wide average, only when
    this specific team has no scraped rating. Clamped to a sane [-8, 12]
    range as a guard against a malformed scrape, not because real ratings
    outside that band are implausible.

    Returns (HFA, is_real_rating)."""
    home_adv = _num(home_ts.get('Home_Adv') if hasattr(home_ts, 'get') else None)
    if home_adv is not None:
        return max(min(home_adv, 12.0), -8.0), True
    return 2.6, False


def build_matchup_forecast(away, home, away_ts, home_ts, fitted_margin_model=None):
    """Builds a from-scratch game-flow forecast (projected score, win
    probability, and a short reasoned narrative) purely from the stats
    already pulled into this report -- no external prediction feed, no
    black box. The method, spelled out step by step:

      1. Five independent estimates of the home-minus-away point margin
         are computed (compute_forecast_factors), each from a different
         stat family (FPI, efficiency, scoring, yardage, turnovers).
      2. Those five estimates are combined into one weighted margin. When
         fitted_margin_model is given (a real dict from
         cfb_matchup_deltas.tune_forecast_weights -- an actual OLS
         regression fit against real completed games' real final margins,
         see that function's docstring), its real, data-fitted
         coefficients are used. Otherwise falls back to _FORECAST_WEIGHTS,
         the original hand-picked/reasoned-about (never backtested)
         weights, renormalized over whichever factors actually have data
         for this matchup -- this fallback only fires when there isn't yet
         enough real recorded history to trust a fit (see
         MIN_MARGIN_SAMPLES in cfb_matchup_deltas.py), or when this
         function is called without a fitted model at all (e.g. from
         the_skinny.py, which doesn't currently pass one).
      3. That team's own real home-field-advantage rating (scraped from
         TeamRankings, not a flat constant -- home advantage varies hugely
         by program) is added on top, falling back to the researched
         CFB-wide average of 2.6 points only if this team has no rating
         (compute_home_field_adv).
      4. Final score projections are built by splitting the two teams'
         blended PPG-based scoring baseline around that weighted margin,
         so the projected score and the weighted margin always agree with
         each other.
      5. The margin is run through a logistic curve (scale = 13.5, roughly
         matching real-world CFB scoring variance) to produce a win
         probability.
      6. Separately, the two biggest real statistical edges (rushing,
         passing, and a turnover-margin gap if it's notable) are picked out
         and turned into the reasoning sentences.

    Returns None if the core PPG inputs aren't available for both teams
    (nothing to safely project), so the caller can render an explicit
    "forecast unavailable" note instead of guessing.
    """
    def g(ts, key):
        return _num(ts.get(key) if hasattr(ts, 'get') else None)

    factors, home_scoring_proj, away_scoring_proj = compute_forecast_factors(away_ts, home_ts)
    if factors is None:
        return None

    if fitted_margin_model is not None:
        # Real, data-fitted margin (see cfb_matchup_deltas.py's
        # tune_forecast_weights/predict_margin_from_fitted) -- replaces
        # the hand-picked weighted average below entirely when available.
        import cfb_matchup_deltas as _deltas_mod
        weighted_margin = _deltas_mod.predict_margin_from_fitted(fitted_margin_model, factors)
        used_weights = _deltas_mod.describe_fitted_margin_model(fitted_margin_model, factors.keys())
    else:
        weight_total = sum(_FORECAST_WEIGHTS[k] for k in factors)
        weighted_margin = sum(_FORECAST_WEIGHTS[k] * v for k, v in factors.items()) / weight_total
        _weight_labels = {
            'fpi': 'FPI', 'efficiency': 'Efficiency', 'scoring': 'Scoring',
            'yardage': 'Yardage', 'turnovers': 'Turnovers',
        }
        used_weights = ", ".join(
            f"{_weight_labels[k]} {_FORECAST_WEIGHTS[k]/weight_total*100:.0f}%" for k in factors
        )

    HFA, home_adv_is_real = compute_home_field_adv(home_ts)
    margin = weighted_margin + HFA

    # Final scores: keep the same total-points expectation as the raw PPG
    # blend, but split it around the weighted (not just PPG-only) margin so
    # the printed score and the printed margin never contradict each other.
    total_points = home_scoring_proj + away_scoring_proj
    home_score = max(total_points / 2 + margin / 2, 0)
    away_score = max(total_points / 2 - margin / 2, 0)

    home_win_prob = 1 / (1 + math.exp(-margin / 13.5))
    away_win_prob = 1 - home_win_prob

    favored_team = home if margin >= 0 else away
    favored_prob = max(home_win_prob, away_win_prob)
    favored_score = home_score if margin >= 0 else away_score
    other_team = away if margin >= 0 else home
    other_score = away_score if margin >= 0 else home_score

    sentences = [
        f"Projection favors {favored_team} {favored_score:.1f}-{other_score:.1f} over {other_team} "
        f"({favored_prob*100:.0f}% win probability), a projected margin of {abs(margin):.1f}."
    ]

    # ---- Rushing matchup
    # Comparing (home_off - away_def) to (away_off - home_def) directly breaks
    # down when one defense is elite: Syracuse (118 yds/g) vs. Pittsburgh's run
    # defense (23.5 allowed) gave Syracuse a big raw edge even though Pittsburgh
    # is dominant there. Instead, project each team's rushing output the same way
    # as the scoring projection above (average of its own rush offense and the
    # opponent's rush defense allowed) and compare the projections.
    home_rush_off, away_rush_def = g(home_ts, 'Off_Rush_PG'), g(away_ts, 'Def_Rush_PG')
    away_rush_off, home_rush_def = g(away_ts, 'Off_Rush_PG'), g(home_ts, 'Def_Rush_PG')
    if None not in (home_rush_off, away_rush_def, away_rush_off, home_rush_def):
        home_rush_proj = (home_rush_off + away_rush_def) / 2
        away_rush_proj = (away_rush_off + home_rush_def) / 2
        if home_rush_proj >= away_rush_proj:
            sentences.append(
                f"On the ground, {home}'s rush offense ({home_rush_off:.1f} yds/g) lines up against "
                f"{away}'s rush defense ({away_rush_def:.1f} yds/g allowed) -- edge {home}."
            )
        else:
            sentences.append(
                f"On the ground, {away}'s rush offense ({away_rush_off:.1f} yds/g) lines up against "
                f"{home}'s rush defense ({home_rush_def:.1f} yds/g allowed) -- edge {away}."
            )

    # ---- Passing matchup: same projected-output comparison through the air.
    home_pass_off, away_pass_def = g(home_ts, 'Off_Pass_PG'), g(away_ts, 'Def_Pass_PG')
    away_pass_off, home_pass_def = g(away_ts, 'Off_Pass_PG'), g(home_ts, 'Def_Pass_PG')
    if None not in (home_pass_off, away_pass_def, away_pass_off, home_pass_def):
        home_pass_proj = (home_pass_off + away_pass_def) / 2
        away_pass_proj = (away_pass_off + home_pass_def) / 2
        if home_pass_proj >= away_pass_proj:
            sentences.append(
                f"Through the air, {home}'s pass offense ({home_pass_off:.1f} yds/g) faces "
                f"{away}'s pass defense ({away_pass_def:.1f} yds/g allowed) -- edge {home}."
            )
        else:
            sentences.append(
                f"Through the air, {away}'s pass offense ({away_pass_off:.1f} yds/g) faces "
                f"{home}'s pass defense ({home_pass_def:.1f} yds/g allowed) -- edge {away}."
            )

    # ---- Wildcard: only mention turnover margin if the gap between the two
    # teams is large enough to plausibly swing a game (>= 1.0 net/game).
    home_to, away_to = g(home_ts, 'Net_TO_Margin'), g(away_ts, 'Net_TO_Margin')
    if home_to is not None and away_to is not None and abs(home_to - away_to) >= 1.0:
        to_leader = home if home_to > away_to else away
        sentences.append(
            f"{to_leader} also carries the turnover-margin edge ({home_to:+.1f} vs {away_to:+.1f})."
        )

    # Transparency footnote: which weighted factors actually fed this
    # specific projection (a factor drops out, rather than silently
    # counting as zero, whenever this matchup is missing its inputs) --
    # used_weights itself was already built above (either the real fitted
    # model's coefficients, or the hand-picked/renormalized fallback).
    hfa_note = (
        f"{home}'s home-field rating ({HFA:+.1f})" if home_adv_is_real
        else f"CFB-wide average home-field bump ({HFA:+.1f}, {home} has no scraped rating)"
    )

    # Expose whether the home-field-advantage bump is
    # WHY this projection differs from the raw stat blend -- the real
    # mechanism behind "everything favors the away team but it still picks
    # home": HFA is added on top of the stat-only weighted_margin, and
    # when the away team's stat edge is smaller than this specific team's
    # real home-field rating, HFA alone can flip the final pick. Both
    # margins below are real, already-computed local values -- nothing
    # new is guessed, this just surfaces what was already happening.
    hfa_flipped_pick = (weighted_margin != 0) and ((weighted_margin >= 0) != (margin >= 0))

    weights_prefix = "Real backtested margin model" if fitted_margin_model is not None else "Model weights (renormalized to available data, hand-picked -- not backtested)"
    return {
        'home_score': home_score, 'away_score': away_score,
        'home_win_prob': home_win_prob, 'away_win_prob': away_win_prob,
        'favored_team': favored_team, 'margin': abs(margin),
        'narrative': " ".join(sentences),
        'weights_note': f"{weights_prefix}: {used_weights}. Home-field: {hfa_note}.",
        'weighted_margin_pre_hfa': weighted_margin,
        'hfa_used': HFA,
        'hfa_flipped_pick': hfa_flipped_pick,
        'stat_favored_team': home if weighted_margin >= 0 else away,
        'is_fitted_margin_model': fitted_margin_model is not None,
    }
# ==========================================
# PART 3.5: GAME-FLOW FORECAST ENGINE END
# ==========================================


# Per-stat FBS-wide rank lookup: a rank beside every metric, e.g. rush yards
# per play 5.6 (87), for all 59 data points. Reuses _HIGHER_IS_BETTER_BY_KEY -- the exact same real,
# tested direction table the stat-vote model and every color-graded cell
# in this report already rely on -- so a stat's rank always points the
# same way its color-grading and vote-direction already do; no separate
# direction judgment call is made here. _EXTRA_RANK_DIRECTION covers the
# couple of displayed numbers (currently just Point_Diff) that have a
# real, unambiguous direction but were never added to _STAT_SIGNAL_SPECS
# itself -- kept separate so this purely-cosmetic rank display can never
# silently change which stats the real, backtested vote model uses.
_EXTRA_RANK_DIRECTION = {
    "Point_Diff": True,  # real scoring margin -- higher is unambiguously better
    # NEW: without an entry here, "OFF PPD (LAST 3)"/"DEF PPD (LAST 3)"
    # print with no "(rank)" suffix at all (unlike every other line on this sheet) --
    # which silently broke new.py's find_h_b() parser, since it requires that "(rank)"
    # to recognize a stat line (confirmed real: printed as "1.611\n\nOFF PPD (LAST 3)"
    # with nothing after the value, so Predicted Team Total/Spread came back N/A for
    # every matchup, even ones with full real data on both sides).
    "Off_PPD_L3": True,   # real points scored per drive, own offense -- higher is better
    "Def_PPD_L3": False,  # real points allowed per drive, own defense -- lower is better
}


def _build_stat_rank_lookup(stats_lookup):
    """Returns {stats_lookup_column: {team_name: rank_int_or_None}}, one
    real FBS-wide rank per team per tracked stat -- computed directly from
    the same stats_lookup values already displayed everywhere in this
    report, not re-scraped or guessed. Ties share the same rank (pandas'
    'min' method -- the standard sports-ranking convention TeamRankings
    itself uses: two teams tied for 2nd both show (2), the next team shows
    (4)). A team with no real value for a given stat gets None (no rank
    shown) rather than being silently counted as if it had one."""
    direction_by_key = {**_HIGHER_IS_BETTER_BY_KEY, **_EXTRA_RANK_DIRECTION}
    rank_lookup = {}
    for key, higher_is_better in direction_by_key.items():
        if key not in stats_lookup.columns:
            continue
        series = pd.to_numeric(stats_lookup[key], errors='coerce')
        ranks = series.rank(method='min', ascending=not higher_is_better, na_option='keep')
        rank_lookup[key] = {team: (int(r) if pd.notna(r) else None) for team, r in ranks.items()}
    return rank_lookup


# Maps the short (side-agnostic) keys grid_row()/grid_row_with_pct() use --
# e.g. ('PPG', 'O') -- to the real stats_lookup column that value actually
# comes from (see get_team_metrics() above, which builds away_m/home_m
# with these exact same short keys from these exact same real columns).
# Deliberately leaves out the tempo/pace keys (PASPLAYS, RUSPLAYS) --
# same real reason _STAT_SIGNAL_SPECS already excludes them from the vote
# model: more plays isn't "better," so there's no real rank direction to
# show for them.
_GRID_KEY_COLUMN = {
    ('PPG', 'O'): 'Off_PPG', ('PPG', 'D'): 'Def_PPG',
    ('YDS', 'O'): 'Off_Yds_PG', ('YDS', 'D'): 'Def_Yds_PG',
    ('YPP', 'O'): 'Off_YPP', ('YPP', 'D'): 'Def_YPP',
    ('RZ', 'O'): 'Off_RZ_%', ('RZ', 'D'): 'Def_RZ_%',
    ('3RD', 'O'): 'Off_3rd_%', ('3RD', 'D'): 'Def_3rd_%',
    ('SACK', 'O'): 'Off_Sacks_Allowed_PG', ('SACK', 'D'): 'Def_Sacks_PG',
    ('TFL', 'O'): 'Stuffs_Off_PG', ('TFL', 'D'): 'TFL_Def_PG',
    ('PAS', 'O'): 'Off_Pass_PG', ('PAS', 'D'): 'Def_Pass_PG',
    ('PAA', 'O'): 'Off_Pass_Att', ('PAA', 'D'): 'Def_Pass_Att',
    ('RUS', 'O'): 'Off_Rush_PG', ('RUS', 'D'): 'Def_Rush_PG',
    ('RUA', 'O'): 'Off_Rush_Att', ('RUA', 'D'): 'Def_Rush_Att',
}


def _with_rank(disp_text, column_key, team_name, rank_lookup):
    """Appends ' (rank)' to an already-formatted display string, e.g.
    '5.6' -> '5.6 (87)'. Leaves '--' (missing data) and any stat with no
    real rank available (column not tracked, or this team has no real
    value for it) untouched."""
    if disp_text in ('--', None) or column_key is None or team_name is None:
        return disp_text
    rank = rank_lookup.get(column_key, {}).get(team_name)
    if rank is None:
        return disp_text
    return f"{disp_text} ({rank})"


def generate_pdf_report(schedule_df, stats_lookup, filename="generated/cfb_matrices_outlook.pdf", extra_baselines=None, model_results=None, fitted_margin_model=None):
    """Compiles schedules into a black-background stacked comparison layout with color conditional metrics.
    fitted_margin_model (2026-09-27): real OLS-fitted margin coefficients
    from cfb_matchup_deltas.tune_forecast_weights, threaded down to every
    game's build_matchup_forecast() call below. None falls back to the
    original hand-picked _FORECAST_WEIGHTS."""
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    # Real per-stat FBS-wide rank for every metric on this sheet -- see
    # _build_stat_rank_lookup() above. One real computation per report run,
    # reused by every game's grid/advanced/trench rows and banner stats
    # below.
    rank_lookup = _build_stat_rank_lookup(stats_lookup)

    doc = SimpleDocTemplate(
        filename, pagesize=letter,
        rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36,
        title="College Football On-Field Matchup Explorer"
    )
    styles = getSampleStyleSheet()

    # Core Color Palette (Dark Theme Strategy)
    bg_dark = colors.HexColor('#121212')
    card_bg = colors.HexColor('#1E1E1E')
    text_white = colors.HexColor('#FFFFFF')
    accent_blue = colors.HexColor('#1A365D')
    sub_header_blue = colors.HexColor('#15294A')
    color_green = colors.HexColor('#48BB78')
    color_red = colors.HexColor('#F56565')
    team_cyan = colors.HexColor('#4FD1C5') # Sharp Cyber Cyan to pop team names out
    fpi_gold = colors.HexColor('#F6C453')
    # Same turquoise the NFL ("grind it out") project uses for its own
    # >=80%-win-probability team-name highlight -- reused here as the "this
    # is the stat-vote model's actual pick" color so the two projects read
    # the same way at a glance.
    TURQUOISE_HIGHLIGHT = '#2DD4BF'
    # Tested finding (cross-checked directly
    # against cfb_stat_history.json): when Def Sacks/Game -- the one stat
    # that favored the real winner in every miss on record so far -- picks
    # a DIFFERENT team than the model's own weighted pick, the model's
    # real hit rate on those games drops from 100% (25/25, when they
    # agree) to 62.5% (10/16, when they disagree). Same orange the NFL
    # project already uses for its own "worst tier" caution color, reused
    # here for the same "be careful" meaning.
    ORANGE_CAUTION_HIGHLIGHT = '#F5A623'

    # National Baseline Benchmarks Matrix
    national_baselines = {
        'YDS': 400.0, 'YPP': 5.5, 'PAS': 225.0, 'PAA': 7.2,
        'RUS': 175.0, 'RUA': 4.2, 'PPG': 28.0, '3RD': 40.0, 'RZ': 80.0
    }
    # Real, computed-from-the-full-FBS-field averages for the new bcftoys/
    # CFBD stats (F+, FEI, NSR/OSR/DSR, PPA, stuff rate) -- passed in from
    # main() rather than hardcoded here, since (unlike the constants above)
    # these are indices with no widely-known "normal" value to guess at;
    # grading them against a real computed league mean is the honest option.
    if extra_baselines:
        national_baselines.update(extra_baselines)

    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=15, leading=18, textColor=text_white, alignment=1, spaceAfter=12)
    # Row 1 of the header banner, now three cells: away info (left-aligned),
    # the date stacked directly above "at" (centered), and home info --
    # centered within its own cell per request, rather than just following
    # the away text inline.
    header_away_style = ParagraphStyle('MatchHeaderAway', fontName='Helvetica-Bold', fontSize=9, leading=12, textColor=text_white, alignment=0)
    header_home_style = ParagraphStyle('MatchHeaderHome', fontName='Helvetica-Bold', fontSize=9, leading=12, textColor=text_white, alignment=1)
    header_center_style = ParagraphStyle('MatchHeaderCenter', fontName='Helvetica-Bold', fontSize=9, leading=11, textColor=text_white, alignment=1)
    # Row 2 of the header: QBR / Off Eff / Def Eff / FG% / ToP, centered
    # under each team's own side.
    header_stub_style = ParagraphStyle('HeaderStub', fontName='Helvetica', fontSize=7.3, leading=10, textColor=colors.HexColor('#CBD5E0'), alignment=1)

    def make_cell_p(text, color_obj=text_white, is_bold=False, size=6.6, align=1):
        f_name = 'Helvetica-Bold' if is_bold else 'Helvetica'
        return Paragraph(f'<font color="{color_obj.hexval()}">{text}</font>',
                         ParagraphStyle('cell', fontName=f_name, fontSize=size, leading=size+2.5, alignment=align))

    story = [Paragraph("COLLEGE FOOTBALL METRIC MATCHUP SYMMETRY", title_style), Spacer(1, 10)]

    # ---- Stat-weighted win prediction model summary (built from real,
    # persistent cross-run game history in cfb_stat_history.json -- see
    # PART 3.5 above). Rendered once, up front, before the per-game
    # matchup pages. Every accuracy figure is shown with its real sample
    # size right next to it (e.g. "17/20 = 85.0%") -- never a bare
    # percentage -- since early-season sample sizes are small and that is
    # disclosed here, not hidden.
    if model_results is not None:
        mr = model_results
        model_elements = [Paragraph("STAT-WEIGHTED WIN PREDICTION MODEL", title_style)]

        total_games = mr.get("total_games", 0)
        decided = mr.get("decided", 0)
        correct = mr.get("correct", 0)
        accuracy = mr.get("accuracy", 0.0)
        target = mr.get("target_accuracy", 0.80)

        if total_games == 0:
            model_elements.append(Paragraph(
                '<font color="#CBD5E0" size=8>No completed games recorded yet -- this model builds itself '
                'automatically as games finish (checked every time this script runs) and will start showing '
                'real accuracy numbers once results start coming in.</font>',
                ParagraphStyle('modelEmpty', fontName='Helvetica', fontSize=8, leading=11)
            ))
            story.append(KeepTogether(model_elements))
            story.append(Spacer(1, 10))
            story.append(PageBreak())
        else:
            hit_target = accuracy >= target
            summary_color = color_green if hit_target else color_red
            summary_text = (
                f'<font color="{text_white.hexval()}" size=9>Backtested against '
                f'<b>{total_games}</b> completed game(s) on record ({decided} produced a decided pick) -- '
                f'</font><font color="{summary_color.hexval()}" size=11><b>{correct}/{decided} = {accuracy*100:.1f}%</b></font>'
                f'<font color="{text_white.hexval()}" size=9> accuracy (target: {target*100:.0f}%).</font>'
                f'<br/><font color="{TURQUOISE_HIGHLIGHT}" size=8><b>&#9679;</b></font>'
                f'<font color="#CBD5E0" size=8> On each matchup page below, the team name highlighted turquoise '
                f'is this exact model\'s pick (its included stats, weighted as shown, net out in that team\'s favor) '
                f'-- not the separate, not-yet-backtested projected-score forecast further down each page.</font>'
            )
            _sacks_agree_hits, _sacks_agree_n = mr.get("sacks_agreement", {}).get("agree", (0, 0))
            _sacks_dis_hits, _sacks_dis_n = mr.get("sacks_agreement", {}).get("disagree", (0, 0))
            if _sacks_agree_n or _sacks_dis_n:
                _agree_pct = _sacks_agree_hits / _sacks_agree_n * 100 if _sacks_agree_n else 0.0
                _dis_pct = _sacks_dis_hits / _sacks_dis_n * 100 if _sacks_dis_n else 0.0
                summary_text += (
                    f'<br/><font color="{ORANGE_CAUTION_HIGHLIGHT}" size=8><b>&#9679;</b></font>'
                    f'<font color="#CBD5E0" size=8> ORANGE instead of turquoise means the same pick, flagged: Def '
                    f'Sacks/Game (this team\'s season-long pass-rush production vs the other side\'s) favors the '
                    f'OTHER team instead. Tested against every decided game on record so far -- when the pick and '
                    f'Def Sacks/Game agree (or Def Sacks/Game has no real data either way), the model is '
                    f'{_sacks_agree_hits}/{_sacks_agree_n} ({_agree_pct:.1f}%); when they disagree, it\'s '
                    f'{_sacks_dis_hits}/{_sacks_dis_n} ({_dis_pct:.1f}%). Still the pick, just a real reason for '
                    f'extra caution.</font>'
                )
            summary_box = Table(
                [[Paragraph(summary_text, ParagraphStyle('modelSummary', fontName='Helvetica', fontSize=9, leading=13))]],
                colWidths=[510]
            )
            summary_box.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), card_bg),
                ('TOPPADDING', (0,0), (-1,-1), 8), ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                ('LEFTPADDING', (0,0), (-1,-1), 10), ('RIGHTPADDING', (0,0), (-1,-1), 10),
            ]))
            model_elements.append(summary_box)
            model_elements.append(Spacer(1, 8))

            # ---- Included stats and their tuned weights ----
            included = mr.get("included", [])
            if included:
                weights_header = Table(
                    [[make_cell_p("STATS THE MODEL WEIGHTS (in the order they were added)", text_white, True, size=6.8, align=1)]],
                    colWidths=[510]
                )
                weights_header.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), accent_blue),
                    ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ]))
                weights_data = [[
                    make_cell_p("STAT", text_white, True, size=6.6, align=0),
                    make_cell_p("WEIGHT", text_white, True, size=6.6, align=1),
                    make_cell_p("WIN RATE (SAMPLE)", text_white, True, size=6.6, align=1),
                ]]
                weights_style = [
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('TOPPADDING', (0,0), (-1,-1), 3), ('BOTTOMPADDING', (0,0), (-1,-1), 3),
                    ('LEFTPADDING', (0,0), (-1,-1), 6), ('RIGHTPADDING', (0,0), (-1,-1), 6),
                    ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor('#000000')),
                    ('BACKGROUND', (0,0), (-1,0), sub_header_blue),
                ]
                for i, (label, key, weight, win_rate, n) in enumerate(included, start=1):
                    weights_data.append([
                        make_cell_p(_xml_escape(label), text_white, False, size=6.8, align=0),
                        make_cell_p(f"+{weight:.3f}", color_green, True, size=6.8, align=1),
                        make_cell_p(f"{win_rate*100:.1f}% ({n})", text_white, False, size=6.8, align=1),
                    ])
                    weights_style.append(('BACKGROUND', (0,i), (-1,i), card_bg))
                weights_table = Table(weights_data, colWidths=[280, 100, 130])
                weights_table.setStyle(TableStyle(weights_style))
                model_elements.append(weights_header)
                model_elements.append(weights_table)
                model_elements.append(Spacer(1, 10))
            else:
                model_elements.append(Paragraph(
                    '<font color="#CBD5E0" size=8>Not enough completed games yet to tune any stat weights '
                    '(needs at least 3 games of signal per stat before it counts).</font>',
                    ParagraphStyle('modelNoStats', fontName='Helvetica', fontSize=8, leading=11)
                ))
                model_elements.append(Spacer(1, 10))

            story.append(KeepTogether(model_elements))

            # ---- Every tracked stat's individual win rate, not just the
            # ones the weighted model above happened to select -- this is
            # the literal "common denominator across winning teams" list:
            # for every stat tracked, what % of winning teams actually led
            # it, full stop, regardless of whether combining it with others
            # ended up helping the tuned model. "IN MODEL" marks the ones
            # that made the final weighted cut above.
            all_rates = mr.get("all_stat_rates", [])
            if all_rates:
                story.append(Spacer(1, 4))
                all_header = Table(
                    [[make_cell_p("EVERY STAT'S WIN RATE THIS SEASON (full list, most predictive first)",
                                   text_white, True, size=6.8, align=1)]],
                    colWidths=[510]
                )
                all_header.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), accent_blue),
                    ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ]))
                story.append(all_header)

                included_keys_set = set(mr.get("included_keys", []))
                all_data = [[
                    make_cell_p("STAT", text_white, True, size=6.4, align=0),
                    make_cell_p("WIN RATE (SAMPLE)", text_white, True, size=6.4, align=1),
                    make_cell_p("IN MODEL", text_white, True, size=6.4, align=1),
                ]]
                all_style = [
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('TOPPADDING', (0,0), (-1,-1), 2.5), ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
                    ('LEFTPADDING', (0,0), (-1,-1), 6), ('RIGHTPADDING', (0,0), (-1,-1), 6),
                    ('LINEBELOW', (0,0), (-1,-1), 0.4, colors.HexColor('#000000')),
                    ('BACKGROUND', (0,0), (-1,0), sub_header_blue),
                ]
                for i, (label, key, win_rate, n) in enumerate(all_rates, start=1):
                    in_model = key in included_keys_set
                    all_data.append([
                        make_cell_p(_xml_escape(label), text_white, in_model, size=6.4, align=0),
                        make_cell_p(f"{win_rate*100:.1f}% ({n})", text_white, in_model, size=6.4, align=1),
                        make_cell_p("YES" if in_model else "--", color_green if in_model else colors.HexColor('#666666'), in_model, size=6.4, align=1),
                    ])
                    all_style.append(('BACKGROUND', (0,i), (-1,i), card_bg if in_model else bg_dark))
                all_table = Table(all_data, colWidths=[280, 130, 100])
                all_table.setStyle(TableStyle(all_style))
                story.append(all_table)
                story.append(Spacer(1, 10))

            # ---- Miss post-mortems: "what it would do different" -- kept
            # OUTSIDE the KeepTogether above (this list can run long) so it
            # flows across pages naturally instead of forcing everything
            # onto one page or spilling over awkwardly.
            postmortems = mr.get("postmortems", [])
            if postmortems:
                pm_header = Table(
                    [[make_cell_p("MISSED PICKS: WHAT WOULD HAVE MADE THE PICK BETTER", text_white, True, size=6.8, align=1)]],
                    colWidths=[510]
                )
                pm_header.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), accent_blue),
                    ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ]))
                story.append(Spacer(1, 4))
                story.append(pm_header)
                story.append(Spacer(1, 4))
                for pm in postmortems:
                    away_s = pm.get("away_score")
                    home_s = pm.get("home_score")
                    score_str = f"{away_s}-{home_s}" if away_s is not None and home_s is not None else "--"
                    title_line = (
                        f'<font color="{text_white.hexval()}" size=7.6><b>{_xml_escape(pm.get("winner"))}</b> beat '
                        f'{_xml_escape(pm.get("loser"))} ({_xml_escape(pm.get("away"))} {score_str} {_xml_escape(pm.get("home"))}, '
                        f'{_xml_escape(pm.get("date") or "--")}) -- model missed this one.</font>'
                    )
                    favored = pm.get("favored_winner") or []
                    if favored:
                        stat_names = ", ".join(_xml_escape(label) for _, label, _ in favored)
                        detail_line = f'<font color="#CBD5E0" size=7>Stats that favored the real winner: {stat_names}</font>'
                    else:
                        detail_line = '<font color="#CBD5E0" size=7>No tracked stat favored the real winner on this one -- a genuine upset.</font>'
                    pm_box = Table(
                        [[Paragraph(title_line, ParagraphStyle('pmTitle', fontName='Helvetica', fontSize=7.6, leading=10))],
                         [Paragraph(detail_line, ParagraphStyle('pmDetail', fontName='Helvetica', fontSize=7, leading=9))]],
                        colWidths=[510]
                    )
                    pm_box.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,-1), card_bg),
                        ('TOPPADDING', (0,0), (-1,-1), 3), ('BOTTOMPADDING', (0,0), (-1,-1), 3),
                        ('LEFTPADDING', (0,0), (-1,-1), 8), ('RIGHTPADDING', (0,0), (-1,-1), 8),
                    ]))
                    story.append(KeepTogether([pm_box, Spacer(1, 3)]))

            story.append(Spacer(1, 10))
            story.append(PageBreak())

    # The tuned stat set (label, key, weight, win_rate, n) the model report
    # page above just described -- reused below, once per game, to work out
    # which team that SAME model actually picks for each upcoming matchup
    # (see stat_vote_model_pick()). Computed once here rather than inside
    # the per-game loop since it doesn't change game to game.
    _included_stats_for_pick = model_results.get("included", []) if model_results else []
    _fei_bucket_stats = model_results.get("fei_bucket_stats") if model_results else None
    _fplus_bucket_stats = model_results.get("fplus_bucket_stats") if model_results else None

    for _game_idx, (_, row) in enumerate(schedule_df.iterrows()):
        away, home = row['Away_Team'], row['Home_Team']
        # Escaped copies for anything that gets dropped into ReportLab
        # Paragraph markup (which parses '&' as the start of an XML entity
        # -- "Texas A&M" would otherwise render as "Texas A&M;" or worse).
        # The raw (unescaped) away/home are still used for stats_lookup
        # lookups below.
        away_esc, home_esc = _xml_escape(away), _xml_escape(home)
        game_date = row.get('Date', '--')
        away_record = row.get('Away_Record', '--')
        home_record = row.get('Home_Record', '--')
        matchup_elements = []

        def team_lookup(team_name):
            try:
                return stats_lookup.loc[team_name]
            except KeyError:
                return {}

        away_ts = team_lookup(away)
        home_ts = team_lookup(home)

        away_to = _with_rank(_fmt_signed(away_ts.get('Net_TO_Margin') if hasattr(away_ts, 'get') else None), 'Net_TO_Margin', away, rank_lookup)
        home_to = _with_rank(_fmt_signed(home_ts.get('Net_TO_Margin') if hasattr(home_ts, 'get') else None), 'Net_TO_Margin', home, rank_lookup)
        away_pd = _with_rank(_fmt_signed(away_ts.get('Point_Diff') if hasattr(away_ts, 'get') else None), 'Point_Diff', away, rank_lookup)
        home_pd = _with_rank(_fmt_signed(home_ts.get('Point_Diff') if hasattr(home_ts, 'get') else None), 'Point_Diff', home, rank_lookup)

        away_fpi = _with_rank(_fmt_num(away_ts.get('FPI') if hasattr(away_ts, 'get') else None, decimals=1), 'FPI', away, rank_lookup)
        home_fpi = _with_rank(_fmt_num(home_ts.get('FPI') if hasattr(home_ts, 'get') else None, decimals=1), 'FPI', home, rank_lookup)
        # decimals=0: SOS is a real ESPN RANK (1 = toughest schedule played
        # so far), not a decimal score -- see the _find_sos fix/comment in
        # fetch_espn_power_index for why (confirmed 2026-09-22 against a
        # real live response; ESPN's API doesn't expose a raw SOS number).
        away_sos = _fmt_num(away_ts.get('SOS') if hasattr(away_ts, 'get') else None, decimals=0)
        home_sos = _fmt_num(home_ts.get('SOS') if hasattr(home_ts, 'get') else None, decimals=0)

        # Which team the tuned stat-vote model (the one the summary page
        # above just backtested and reported accuracy for) actually picks
        # for THIS matchup, using each side's real current stats. None if
        # the included stats cancel out or aren't available for one side --
        # matches _backtest_accuracy()'s own "not every game gets decided" rule.
        model_pick_side = stat_vote_model_pick(away_ts, home_ts, _included_stats_for_pick)

        # Real "be careful" flag (see ORANGE_CAUTION_HIGHLIGHT's comment
        # above for the tested 100% vs 62.5% split this is based on): does
        # Def Sacks/Game, applied to THIS matchup's real current sides,
        # favor a DIFFERENT team than the model's own pick? None (no real
        # sacks data for one side) is treated as "not flagged" -- that
        # bucket was also 100% on record, not a risk case.
        def _pick_is_risky(pick_side):
            if pick_side is None:
                return False
            away_sacks = away_ts.get('Def_Sacks_PG') if hasattr(away_ts, 'get') else None
            home_sacks = home_ts.get('Def_Sacks_PG') if hasattr(home_ts, 'get') else None
            lean = _live_stat_lean(away_sacks, home_sacks, True)  # higher Def_Sacks_PG is better
            if lean is None:
                return False
            sacks_side = 'away' if lean == 1 else 'home'
            return sacks_side != pick_side

        pick_is_risky = _pick_is_risky(model_pick_side)

        def _team_name_span(name_upper, is_pick):
            # Same turquoise "this is the model's pick" treatment on both
            # sides -- bold is already implied by the surrounding
            # Helvetica-Bold header style, so only the color needs to
            # change. When the pick is flagged risky (Def Sacks/Game
            # favors the OTHER team), it's shown in orange instead of
            # turquoise -- still visibly "the pick," just flagged.
            if is_pick and pick_is_risky:
                return f'<font size=13 color="{ORANGE_CAUTION_HIGHLIGHT}">{name_upper}</font>'
            if is_pick:
                return f'<font size=13 color="{TURQUOISE_HIGHLIGHT}">{name_upper}</font>'
            return f'<font size=13>{name_upper}</font>'

        # ---- Row 1: away info (left) | date stacked over "at" (center) | home info (centered in its own cell) ----
        away_banner_text = (
            f"FPI {away_fpi}  SOS Rk {away_sos}  {_team_name_span(_xml_escape(away.upper()), model_pick_side == 'away')} "
            f"({_xml_escape(away_record)}, {away_to} TO, {away_pd} PD)"
        )
        home_banner_text = (
            f"FPI {home_fpi}  SOS Rk {home_sos}  {_team_name_span(_xml_escape(home.upper()), model_pick_side == 'home')} "
            f"({_xml_escape(home_record)}, {home_to} TO, {home_pd} PD)"
        )
        center_banner_text = f"<font size=7>{_xml_escape(game_date)}</font><br/>at"

        header_table = Table(
            [[
                Paragraph(away_banner_text, header_away_style),
                Paragraph(center_banner_text, header_center_style),
                Paragraph(home_banner_text, header_home_style),
            ]],
            colWidths=[222, 66, 222]
        )
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), accent_blue),
            ('TOPPADDING', (0,0), (-1,-1), 6), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 8), ('RIGHTPADDING', (0,0), (-1,-1), 8),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        matchup_elements.append(header_table)

        # ---- Row 2: QBR / Off Eff / Def Eff / FG% / ToP, centered per team ----
        def header_stub(ts, team_name):
            get = ts.get if hasattr(ts, 'get') else (lambda *_a, **_k: None)
            qbr = _with_rank(_fmt_num(get('QBR'), decimals=1), 'QBR', team_name, rank_lookup)
            off_eff = _with_rank(_fmt_num(get('Off_Eff'), decimals=1), 'Off_Eff', team_name, rank_lookup)
            def_eff = _with_rank(_fmt_num(get('Def_Eff'), decimals=1), 'Def_Eff', team_name, rank_lookup)
            fg_pct = _with_rank(_fmt_num(get('FG_Pct'), decimals=1, suffix="%"), 'FG_Pct', team_name, rank_lookup)
            top_raw = get('ToP_Display')
            top = '--' if _is_missing(top_raw) or not top_raw else top_raw
            return f"QBR {qbr}   Off Eff {off_eff}   Def Eff {def_eff}   FG% {fg_pct}   ToP {top}"

        stub_row = Table(
            [[Paragraph(header_stub(away_ts, away), header_stub_style), Paragraph(header_stub(home_ts, home), header_stub_style)]],
            colWidths=[255, 255]
        )
        stub_row.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), sub_header_blue),
            ('TOPPADDING', (0,0), (-1,-1), 3), ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor('#2D2D2D')),
        ]))
        matchup_elements.append(stub_row)
        # Separation between the QBR/Eff/FG%/ToP line and the stat grids below.
        matchup_elements.append(Spacer(1, 7))

        def get_team_metrics(team_name):
            try:
                ts = stats_lookup.loc[team_name]
                return {
                    'O_PPG': ts.get('Off_PPG','--'), 'O_YDS': ts.get('Off_Yds_PG','--'), 'O_YPP': ts.get('Off_YPP','--'),
                    'O_RZ': ts.get('Off_RZ_%','--'), 'O_3RD': ts.get('Off_3rd_%','--'),
                    'O_SACK': ts.get('Off_Sacks_Allowed_PG', '--'), 'O_TFL': ts.get('Stuffs_Off_PG', '--'),
                    'O_PAS': ts.get('Off_Pass_PG','--'), 'O_PAA': ts.get('Off_Pass_Att','--'),
                    'O_PASPLAYS': ts.get('Off_Pass_Plays_PG', '--'),
                    'O_RUS': ts.get('Off_Rush_PG','--'), 'O_RUA': ts.get('Off_Rush_Att','--'),
                    'O_RUSPLAYS': ts.get('Off_Rush_Plays_PG', '--'),
                    'O_PLAYS': ts.get('Off_Plays_PG', '--'),

                    'D_PPG': ts.get('Def_PPG','--'), 'D_YDS': ts.get('Def_Yds_PG','--'), 'D_YPP': ts.get('Def_YPP','--'),
                    'D_RZ': ts.get('Def_RZ_%','--'), 'D_3RD': ts.get('Def_3rd_%','--'),
                    'D_SACK': ts.get('Def_Sacks_PG', '--'), 'D_TFL': ts.get('TFL_Def_PG', '--'),
                    'D_PAS': ts.get('Def_Pass_PG','--'), 'D_PAA': ts.get('Def_Pass_Att','--'),
                    'D_PASPLAYS': ts.get('Def_Pass_Plays_PG', '--'),
                    'D_RUS': ts.get('Def_Rush_PG','--'), 'D_RUA': ts.get('Def_Rush_Att','--'),
                    'D_RUSPLAYS': ts.get('Def_Rush_Plays_PG', '--'),
                    'D_PLAYS': ts.get('Def_Plays_Faced_PG', '--'),
                }
            except KeyError:
                keys = ['O_PPG','O_YDS','O_YPP','O_RZ','O_3RD','O_SACK','O_TFL','O_PAS','O_PAA','O_PASPLAYS','O_RUS','O_RUA','O_RUSPLAYS','O_PLAYS',
                        'D_PPG','D_YDS','D_YPP','D_RZ','D_3RD','D_SACK','D_TFL','D_PAS','D_PAA','D_PASPLAYS','D_RUS','D_RUA','D_RUSPLAYS','D_PLAYS']
                return {k: '--' for k in keys}

        away_m = get_team_metrics(away)
        home_m = get_team_metrics(home)

        # ---- Combined value|label|value grid, styled after the reference
        # sheet (nfl_matchup_sheet.pdf): every stat is one
        # row spanning the full width, with the label centered in the middle
        # and each side's value shown as a solid color-graded block (green =
        # better than the national baseline, red = worse, gray = neutral /
        # no published baseline to grade against).
        black_txt = colors.HexColor('#111111')
        label_bg = colors.HexColor('#2A2A2A')
        neutral_bg = colors.HexColor('#CBD5E0')
        missing_bg = colors.HexColor('#3A3A3A')

        def grade_bg(val, key, side):
            """Returns (display_text, bg_color) for a nationally-graded stat."""
            if val == '--' or _is_missing(val):
                return '--', missing_bg
            base = national_baselines.get(key)
            disp = str(val)
            if base is None:
                return disp, neutral_bg
            try:
                clean_val = float(str(val).replace('%', ''))
            except ValueError:
                return disp, neutral_bg
            better = clean_val > base if side == 'O' else clean_val < base
            worse = clean_val < base if side == 'O' else clean_val > base
            if better:
                return disp, color_green
            if worse:
                return disp, color_red
            return disp, neutral_bg

        def plain_cell(val):
            """Un-graded stat (sacks/TFL/play counts) -- plain neutral box,
            no national baseline exists to color-grade these against."""
            if val == '--' or _is_missing(val):
                return '--', missing_bg
            return _fmt_num(val, decimals=1), neutral_bg

        def build_combo_grid(rows):
            """rows: list of (left_text, left_bg, label_text, right_text, right_bg)."""
            data = []
            style_cmds = [
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('TOPPADDING', (0,0), (-1,-1), 3), ('BOTTOMPADDING', (0,0), (-1,-1), 3),
                ('LEFTPADDING', (0,0), (-1,-1), 4), ('RIGHTPADDING', (0,0), (-1,-1), 4),
                ('LINEBELOW', (0,0), (-1,-2), 0.5, colors.HexColor('#000000')),
            ]
            for i, (left_text, left_bg, label_text, right_text, right_bg) in enumerate(rows):
                data.append([
                    make_cell_p(left_text, black_txt, is_bold=True, size=6.6, align=1),
                    make_cell_p(label_text, text_white, is_bold=True, size=6, align=1),
                    make_cell_p(right_text, black_txt, is_bold=True, size=6.6, align=1),
                ])
                style_cmds.append(('BACKGROUND', (0,i), (0,i), left_bg))
                style_cmds.append(('BACKGROUND', (1,i), (1,i), label_bg))
                style_cmds.append(('BACKGROUND', (2,i), (2,i), right_bg))
            # Half-page-width grid (this table lives inside one side of the
            # left/right pairing_row below) -- 66+114+66 = 246pt, safely
            # inside each ~249pt-available half-column.
            t = Table(data, colWidths=[66, 114, 66])
            t.setStyle(TableStyle(style_cmds))
            return t

        def build_pairing_block(left_label, left_m, left_side, left_team, right_label, right_m, right_side, right_team):
            def grid_row(label, key, plain=False):
                lv, rv = left_m[f'{left_side}_{key}'], right_m[f'{right_side}_{key}']
                if plain:
                    lt, lbg = plain_cell(lv)
                    rt, rbg = plain_cell(rv)
                else:
                    lt, lbg = grade_bg(lv, key, left_side)
                    rt, rbg = grade_bg(rv, key, right_side)
                lt = _with_rank(lt, _GRID_KEY_COLUMN.get((key, left_side)), left_team, rank_lookup)
                rt = _with_rank(rt, _GRID_KEY_COLUMN.get((key, right_side)), right_team, rank_lookup)
                return (lt, lbg, label, rt, rbg)

            def _play_pct(m, side, plays_key):
                """Real share of this team's own total snaps that were pass
                (PASPLAYS) or rush (RUSPLAYS) plays -- both numbers are
                already-scraped real TeamRankings per-game counts
                (plays-per-game / pass- or rushing-attempts-per-game), just
                divided here, not a separately sourced stat."""
                plays = m.get(f'{side}_{plays_key}')
                total = m.get(f'{side}_PLAYS')
                if _is_missing(plays) or _is_missing(total) or plays == '--' or total == '--':
                    return None
                try:
                    total_f = float(total)
                    if total_f <= 0:
                        return None
                    return float(plays) / total_f * 100.0
                except (TypeError, ValueError):
                    return None

            def grid_row_with_pct(label, yard_key, plays_key):
                """Same yardage row as grid_row, but with the real FBS
                rank and the real % of total plays that were pass/rush
                snaps appended to the displayed number -- e.g.
                "260 (87) (48%)"."""
                lv, rv = left_m[f'{left_side}_{yard_key}'], right_m[f'{right_side}_{yard_key}']
                lt, lbg = grade_bg(lv, yard_key, left_side)
                rt, rbg = grade_bg(rv, yard_key, right_side)
                lt = _with_rank(lt, _GRID_KEY_COLUMN.get((yard_key, left_side)), left_team, rank_lookup)
                rt = _with_rank(rt, _GRID_KEY_COLUMN.get((yard_key, right_side)), right_team, rank_lookup)
                l_pct = _play_pct(left_m, left_side, plays_key)
                r_pct = _play_pct(right_m, right_side, plays_key)
                if l_pct is not None and lt != '--':
                    lt = f"{lt} ({l_pct:.0f}%)"
                if r_pct is not None and rt != '--':
                    rt = f"{rt} ({r_pct:.0f}%)"
                return (lt, lbg, label, rt, rbg)

            scoring_rows = [
                grid_row("POINTS / GAME", 'PPG'),
                grid_row("YARDS / GAME", 'YDS'),
                grid_row("YARDS / PLAY", 'YPP'),
                grid_row("RED ZONE %", 'RZ'),
                grid_row("3RD DOWN %", '3RD'),
                grid_row("SACKS ALLOWED", 'SACK', plain=True),
                grid_row("TFL", 'TFL', plain=True),
            ]
            passing_rows = [
                grid_row_with_pct("PASS YARDS / GAME (% OF PLAYS)", 'PAS', 'PASPLAYS'),
                grid_row("PASS YARDS / PLAY", 'PAA'),
                grid_row("PASS PLAYS / GAME", 'PASPLAYS', plain=True),
            ]
            rushing_rows = [
                grid_row_with_pct("RUSH YARDS / GAME (% OF PLAYS)", 'RUS', 'RUSPLAYS'),
                grid_row("RUSH YARDS / PLAY", 'RUA'),
                grid_row("RUSH PLAYS / GAME", 'RUSPLAYS', plain=True),
            ]

            header_text = f"{left_label} vs {right_label}"
            header_row = Table([[make_cell_p(header_text, text_white, True, size=6.8, align=1)]], colWidths=[246])
            header_row.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), accent_blue),
                ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ]))

            block = Table(
                [[[
                    header_row, Spacer(1, 3),
                    build_combo_grid(scoring_rows), Spacer(1, 6),
                    build_combo_grid(passing_rows), Spacer(1, 6),
                    build_combo_grid(rushing_rows),
                ]]],
                colWidths=[246]
            )
            block.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), card_bg),
                ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0),
                ('TOPPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ]))
            return block

        # Two separate, self-contained grids side by side in one row --
        # matching the reference sheet's layout exactly: away offense/home
        # defense grid on the LEFT half of the page, home offense/away
        # defense grid on the RIGHT half, each with its own header and its
        # own centered label column (not one grid stacked on top of another,
        # and not one shared label column spanning the full page width).
        left_block = build_pairing_block(
            f"{away_esc.upper()} OFFENSE", away_m, 'O', away,
            f"{home_esc.upper()} DEFENSE", home_m, 'D', home,
        )
        right_block = build_pairing_block(
            f"{home_esc.upper()} OFFENSE", home_m, 'O', home,
            f"{away_esc.upper()} DEFENSE", away_m, 'D', away,
        )
        pairing_row = Table([[left_block, right_block]], colWidths=[255, 255])
        pairing_row.setStyle(TableStyle([
            ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        matchup_elements.append(pairing_row)

        # Built here, rather than in the GAME FLOW FORECAST section, so the
        # win-probability margin line under the FEI/F+ table can use it too.
        forecast = build_matchup_forecast(away, home, away_ts, home_ts, fitted_margin_model=fitted_margin_model)

        # ---- Advanced ratings: bcftoys F+/FEI/Drive-Success-Rate and CFBD
        # PPA/stuff rate, shown away-vs-home (not O-vs-D split like the
        # trench grid above, since these are composite team ratings, not
        # paired offense/allowed stats). Each stat is graded against the
        # real league-wide average computed in fetch_bcftoys_ratings() /
        # fetch_cfbd_advanced_stats() (extra_baselines), not a guess.
        # higher_is_better is per-metric: F+/OF+/DF+/FEI/OFEI/DFEI/NSR/OSR
        # are all built so a HIGHER number is better on both offense and
        # defense (confirmed against real bcftoys data -- e.g. Ohio State's
        # #1-ranked defense shows DF+ 2.19, a large POSITIVE number, not a
        # small/negative one). DSR is the opposite -- it's opponent success
        # rate allowed, so lower is better (confirmed the same way: a bad
        # defense in the real data shows a high DSR). Off_PPA and
        # Off_Stuff_Rate are "how well this team's OWN offense did," so
        # higher PPA is better but LOWER stuff rate is better (getting
        # stuffed less); Def_PPA/Def_Stuff_Rate are what the defense forces
        # onto opponents, so lower Def_PPA is better but HIGHER
        # Def_Stuff_Rate is better (stuffing more opposing runs).
        adv_specs = [
            ("F+",  'F+',  True),  ("OF+", 'OF+', True),  ("DF+", 'DF+', True),
            ("FEI", 'FEI', True),  ("OFEI", 'OFEI', True), ("DFEI", 'DFEI', True),
            ("NET SUCCESS RATE", 'NSR', True), ("OFF SUCCESS RATE", 'OSR', True),
            ("OPP SUCCESS RATE (DSR)", 'DSR', False),
            ("OFF PPA (EPA/PLAY)", 'Off_PPA', True), ("DEF PPA (EPA/PLAY ALLOWED)", 'Def_PPA', False),
            ("OFF STUFF RATE", 'Off_Stuff_Rate', False), ("DEF STUFF RATE FORCED", 'Def_Stuff_Rate', True),
            # NEW: last-3-completed-games points-per-drive (see
            # load_ppd_cache() above) -- printed here, right by FEI/PPA, specifically so
            # new.py can pull it back out of this table's text via find_h_b() the same
            # way it already does for every other line here, per the instruction
            # ("add what new.py needs to the matrices"). Higher is better on offense,
            # lower is better on defense allowed -- same convention as every other
            # Off_*/Def_* pair above.
            ("OFF PPD (LAST 3)", 'Off_PPD_L3', True), ("DEF PPD (LAST 3)", 'Def_PPD_L3', False),
        ]

        def adv_cell(val, key, higher_is_better):
            if val == '--' or _is_missing(val):
                return '--', missing_bg
            base = national_baselines.get(key)
            try:
                clean_val = float(val)
            except (TypeError, ValueError):
                return str(val), neutral_bg
            disp = f"{clean_val:.3f}" if abs(clean_val) < 10 else f"{clean_val:.1f}"
            if base is None:
                return disp, neutral_bg
            better = clean_val > base if higher_is_better else clean_val < base
            worse = clean_val < base if higher_is_better else clean_val > base
            if better:
                return disp, color_green
            if worse:
                return disp, color_red
            return disp, neutral_bg

        def adv_row(label, key, higher_is_better):
            av = away_ts.get(key) if hasattr(away_ts, 'get') else '--'
            hv = home_ts.get(key) if hasattr(home_ts, 'get') else '--'
            at, abg = adv_cell(av, key, higher_is_better)
            ht, hbg = adv_cell(hv, key, higher_is_better)
            at = _with_rank(at, key, away, rank_lookup)
            ht = _with_rank(ht, key, home, rank_lookup)
            return (at, abg, label, ht, hbg)

        adv_rows = [adv_row(label, key, hib) for label, key, hib in adv_specs]

        adv_header = Table(
            [[make_cell_p(f"ADVANCED RATINGS: {away_esc.upper()} vs {home_esc.upper()} (bcftoys F+/FEI/DSR, CFBD PPA/stuff rate)",
                           text_white, True, size=6.8, align=1)]],
            colWidths=[510]
        )
        adv_header.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), accent_blue),
            ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        adv_data = []
        adv_style = [
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 3), ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('LEFTPADDING', (0,0), (-1,-1), 4), ('RIGHTPADDING', (0,0), (-1,-1), 4),
            ('LINEBELOW', (0,0), (-1,-2), 0.5, colors.HexColor('#000000')),
        ]
        for i, (lt, lbg, label, rt, rbg) in enumerate(adv_rows):
            adv_data.append([
                make_cell_p(lt, black_txt, is_bold=True, size=6.6, align=1),
                make_cell_p(label, text_white, is_bold=True, size=6, align=1),
                make_cell_p(rt, black_txt, is_bold=True, size=6.6, align=1),
            ])
            adv_style.append(('BACKGROUND', (0,i), (0,i), lbg))
            adv_style.append(('BACKGROUND', (1,i), (1,i), label_bg))
            adv_style.append(('BACKGROUND', (2,i), (2,i), rbg))
        adv_table = Table(adv_data, colWidths=[130, 250, 130])
        adv_table.setStyle(TableStyle(adv_style))

        matchup_elements.append(Spacer(1, 8))
        matchup_elements.append(adv_header)
        matchup_elements.append(adv_table)

        # ---- FEI/F+ margin, with its real historical bucket + miss rate
        # (added per request, 2026-09-22 -- this is the actual "add the
        # narrow/moderate/wide labels" ask; an earlier pass only added it to
        # the terminal research script, not here, which was a real miss).
        # Same real, tested finding as everywhere else this shows up: a
        # narrow gap here is a genuine but WEAK, standalone lean (misses
        # happen in every bucket, not just narrow ones) -- it does NOT
        # compound with the sacks flag above, so this is shown for
        # visibility, not as a second thing to weigh against the orange
        # highlight.
        def _fmt_margin_bucket(key, bucket_stats):
            av = away_ts.get(key) if hasattr(away_ts, 'get') else None
            hv = home_ts.get(key) if hasattr(home_ts, 'get') else None
            try:
                margin = abs(float(av) - float(hv))
            except (TypeError, ValueError):
                return None
            return _format_margin_with_bucket(margin, bucket_stats)

        fei_bucket_str = _fmt_margin_bucket('FEI', _fei_bucket_stats)
        fplus_bucket_str = _fmt_margin_bucket('F+', _fplus_bucket_stats)
        if fei_bucket_str or fplus_bucket_str:
            margin_bucket_line = Table(
                [[make_cell_p(
                    f"FEI MARGIN: {fei_bucket_str or 'n/a'}   |   F+ MARGIN: {fplus_bucket_str or 'n/a'}   "
                    f"(historical bucket + real miss rate -- a real but weak lean, doesn't stack with the sacks flag)",
                    text_white, True, size=6.8, align=1
                )]],
                colWidths=[510]
            )
            margin_bucket_line.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#000000')),
                ('TOPPADDING', (0,0), (-1,-1), 3), ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ]))
            matchup_elements.append(margin_bucket_line)

        # ---- Win probability margin (added per request, 2026-09-22): how
        # far the GAME FLOW FORECAST below leans off a coin flip, shown right
        # here next to FEI/F+/DSR since that's the natural place to check it
        # against those numbers -- NOT the same model as the FEI/F+ table
        # above it. The tracked, backtested stat-vote model (FEI/F+/Off_Havoc
        # right now) is what actually drives the turquoise/orange pick
        # highlight; this win-prob number comes from the separate,
        # hand-weighted, never-backtested forecast engine (FPI/efficiency/
        # scoring/yardage/turnovers/home-field) -- the two can and sometimes
        # do favor different teams (confirmed live: Liberty @ Coastal
        # Carolina, where the stat-vote model picked Liberty while this
        # forecast favored Coastal Carolina at 57%). Labeled explicitly below
        # so that's never ambiguous again.
        if forecast is not None:
            wp_margin_pts = max(forecast['home_win_prob'], forecast['away_win_prob']) * 100 - 50.0
            wp_margin_line = Table(
                [[make_cell_p(
                    f"WIN PROB MARGIN (game-flow forecast, not the tracked pick above): "
                    f"{_xml_escape(forecast['favored_team'])} +{wp_margin_pts:.1f} pts over a coin flip",
                    text_white, True, size=6.8, align=1
                )]],
                colWidths=[510]
            )
            wp_margin_line.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#000000')),
                ('TOPPADDING', (0,0), (-1,-1), 3), ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ]))
            matchup_elements.append(wp_margin_line)

        # ---- Trench & efficiency ratings: the rest of CFBD's real
        # season-advanced payload -- havoc rate (closest free stand-in for
        # pass-rush/DB disruption), the Football-Outsiders-style run-block
        # zone breakdown (line/second-level/open-field yards -- closest free
        # stand-in for PFF's run-blocking grades), power success (short-
        # yardage trench conversion), and the two core CFBD efficiency
        # indices (success rate, explosiveness). Same away-vs-home layout
        # and same real-league-average grading as the ADVANCED RATINGS panel
        # above -- reuses adv_cell/adv_row since the shape is identical, just
        # a different metric list. Direction logic (see the comment above
        # fetch_cfbd_advanced_stats): every "Off_" stat describes this team's
        # OWN offense (higher is better, except Off_Havoc -- lower is better,
        # since that's the rate this team's offense got disrupted); every
        # "Def_" stat describes what this team's DEFENSE forces onto
        # opponents (opposite direction from the matching Off_ stat).
        trench_specs = [
            ("OFF HAVOC RATE (SUFFERED)", 'Off_Havoc', False), ("DEF HAVOC RATE (FORCED)", 'Def_Havoc', True),
            ("OFF LINE YARDS", 'Off_Line_Yards', True), ("DEF LINE YARDS ALLOWED", 'Def_Line_Yards', False),
            ("OFF 2ND LEVEL YARDS", 'Off_Second_Level_Yards', True), ("DEF 2ND LEVEL YARDS ALLOWED", 'Def_Second_Level_Yards', False),
            ("OFF OPEN FIELD YARDS", 'Off_Open_Field_Yards', True), ("DEF OPEN FIELD YARDS ALLOWED", 'Def_Open_Field_Yards', False),
            ("OFF POWER SUCCESS RATE", 'Off_Power_Success', True), ("DEF POWER SUCCESS RATE ALLOWED", 'Def_Power_Success', False),
            ("OFF SUCCESS RATE", 'Off_Success_Rate', True), ("DEF SUCCESS RATE ALLOWED", 'Def_Success_Rate', False),
            ("OFF EXPLOSIVENESS", 'Off_Explosiveness', True), ("DEF EXPLOSIVENESS ALLOWED", 'Def_Explosiveness', False),
        ]
        trench_rows = [adv_row(label, key, hib) for label, key, hib in trench_specs]

        trench_header = Table(
            [[make_cell_p(f"TRENCH & EFFICIENCY: {away_esc.upper()} vs {home_esc.upper()} (CFBD havoc/line yards/power success)",
                           text_white, True, size=6.8, align=1)]],
            colWidths=[510]
        )
        trench_header.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), accent_blue),
            ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        trench_data = []
        trench_style = [
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 3), ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('LEFTPADDING', (0,0), (-1,-1), 4), ('RIGHTPADDING', (0,0), (-1,-1), 4),
            ('LINEBELOW', (0,0), (-1,-2), 0.5, colors.HexColor('#000000')),
        ]
        for i, (lt, lbg, label, rt, rbg) in enumerate(trench_rows):
            trench_data.append([
                make_cell_p(lt, black_txt, is_bold=True, size=6.6, align=1),
                make_cell_p(label, text_white, is_bold=True, size=6, align=1),
                make_cell_p(rt, black_txt, is_bold=True, size=6.6, align=1),
            ])
            trench_style.append(('BACKGROUND', (0,i), (0,i), lbg))
            trench_style.append(('BACKGROUND', (1,i), (1,i), label_bg))
            trench_style.append(('BACKGROUND', (2,i), (2,i), rbg))
        trench_table = Table(trench_data, colWidths=[130, 250, 130])
        trench_table.setStyle(TableStyle(trench_style))

        matchup_elements.append(Spacer(1, 8))
        matchup_elements.append(trench_header)
        matchup_elements.append(trench_table)

        # ---- Game-flow forecast: a self-built (no external prediction
        # feed), weighted projection derived from the stats already in this
        # report -- rendered after the stat grids, as a wrap-up on top of
        # the raw numbers above it. `forecast` was already computed once,
        # further up (right before the ADVANCED RATINGS table), so the win-
        # probability margin line up there could use it too -- not recomputed
        # here.
        forecast_header = Table(
            [[make_cell_p("GAME FLOW FORECAST", text_white, True, size=7.5, align=1)]],
            colWidths=[510]
        )
        forecast_header.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), accent_blue),
            ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        matchup_elements.append(Spacer(1, 8))
        matchup_elements.append(forecast_header)

        if forecast is not None:
            fav_is_home = forecast['favored_team'] == home
            away_prob_bg = color_red if fav_is_home else color_green
            home_prob_bg = color_green if fav_is_home else color_red

            box = Table(
                [
                    [make_cell_p(f"{forecast['away_win_prob']*100:.0f}%", black_txt, True, size=8, align=1),
                     make_cell_p("WIN PROBABILITY", text_white, True, size=6.5, align=1),
                     make_cell_p(f"{forecast['home_win_prob']*100:.0f}%", black_txt, True, size=8, align=1)],
                    [make_cell_p(f"{forecast['away_score']:.1f}", black_txt, True, size=8, align=1),
                     make_cell_p("PROJECTED SCORE", text_white, True, size=6.5, align=1),
                     make_cell_p(f"{forecast['home_score']:.1f}", black_txt, True, size=8, align=1)],
                ],
                colWidths=[170, 170, 170]
            )
            box.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (0,0), away_prob_bg),
                ('BACKGROUND', (2,0), (2,0), home_prob_bg),
                ('BACKGROUND', (0,1), (0,1), neutral_bg),
                ('BACKGROUND', (2,1), (2,1), neutral_bg),
                ('BACKGROUND', (1,0), (1,-1), label_bg),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('LINEBELOW', (0,0), (-1,-2), 0.5, colors.HexColor('#000000')),
            ]))
            matchup_elements.append(box)

            margin_line = Table(
                [[make_cell_p(
                    f"PROJECTED MARGIN: {_xml_escape(forecast['favored_team'])} by {forecast['margin']:.1f}   |   "
                    f"PROJECTED TOTAL: {(forecast['home_score'] + forecast['away_score']):.1f}",
                    text_white, True, size=7, align=1
                )]],
                colWidths=[510]
            )
            margin_line.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#000000')),
                ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ]))
            matchup_elements.append(margin_line)

            narrative_style = ParagraphStyle(
                'forecastNarrative', fontName='Helvetica', fontSize=7.2, leading=10.5,
                textColor=colors.HexColor('#E2E8F0'), alignment=0
            )
            weights_style = ParagraphStyle(
                'forecastWeights', fontName='Helvetica-Oblique', fontSize=5.8, leading=8,
                textColor=colors.HexColor('#7A7A7A'), alignment=0
            )
            narrative_box = Table(
                [[[
                    Paragraph(_xml_escape(forecast['narrative']), narrative_style),
                    Spacer(1, 3),
                    Paragraph(_xml_escape(forecast['weights_note']), weights_style),
                ]]],
                colWidths=[510]
            )
            narrative_box.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), card_bg),
                ('LEFTPADDING', (0,0), (-1,-1), 8), ('RIGHTPADDING', (0,0), (-1,-1), 8),
                ('TOPPADDING', (0,0), (-1,-1), 6), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ]))
            matchup_elements.append(narrative_box)
        else:
            unavailable = Table(
                [[make_cell_p(
                    "Forecast unavailable -- insufficient scoring-offense/defense data for this matchup.",
                    colors.HexColor('#888888'), False, size=7, align=1
                )]],
                colWidths=[510]
            )
            unavailable.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), card_bg),
                ('TOPPADDING', (0,0), (-1,-1), 6), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ]))
            matchup_elements.append(unavailable)

        matchup_elements.append(Spacer(1, 14))
        story.append(KeepTogether(matchup_elements))
        # One game per page.
        if _game_idx < len(schedule_df) - 1:
            story.append(PageBreak())

    def draw_background(canvas, document):
        canvas.saveState()
        canvas.setFillColor(bg_dark)
        # --- FIXED LINE: Properly unpack the page width and height from the tuple ---
        p_width, p_height = document.pagesize
        canvas.rect(0, 0, p_width, p_height, fill=1, stroke=0)
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_background, onLaterPages=draw_background)

def main():
    print("Loading schedule file coordinates...")
    schedule_df, week_number, season_year = fetch_live_cfb_schedule()
    if schedule_df.empty:
        print("Schedule matrix empty.")
        return

    print("Pulling global on-field matrix layers...")
    stats_lookup = fetch_all_teamrankings_stats()
    if stats_lookup is None or stats_lookup.empty:
        print("Could not load stats data.")
        return

    _TR_NAMES = list(stats_lookup['Clean_Name'].dropna().unique())    # the names every other source gets aligned onto
    print("Pulling ESPN team directory, FPI/efficiency, and QBR...")
    team_directory = fetch_espn_team_directory()
    name_to_id = build_name_to_id(team_directory)

    fpi_lookup = fetch_espn_power_index(season_year, week_number, team_directory)
    qbr_lookup = fetch_espn_qbr(season_year, team_directory)

    fpi_rows = []
    for team_name, vals in fpi_lookup.items():
        fpi_rows.append({'Clean_Name': team_name, 'FPI': vals.get('FPI'), 'Off_Eff': vals.get('Off_Eff'), 'Def_Eff': vals.get('Def_Eff')})
    if fpi_rows:
        stats_lookup = pd.merge(stats_lookup, _align_names(pd.DataFrame(fpi_rows), _TR_NAMES, 'FPI'), on='Clean_Name', how='outer')

    if qbr_lookup:
        qbr_rows = [{'Clean_Name': k, 'QBR': v} for k, v in qbr_lookup.items()]
        stats_lookup = pd.merge(stats_lookup, _align_names(pd.DataFrame(qbr_rows), _TR_NAMES, 'QBR'), on='Clean_Name', how='outer')

    # TFL / stuffs / time-of-possession / FG% only come from a per-team
    # ESPN endpoint (no bulk "all teams" page exists for these), so this
    # only calls it for the teams actually playing this week rather than
    # every FBS team.
    print("Pulling per-team TFL / time of possession / FG% for this week's teams...")
    playing_teams = set(schedule_df['Away_Team']).union(set(schedule_df['Home_Team']))
    extra_rows = []
    # NEW (2026-10-06): ESPN's per-team endpoint times out in streaks. Good results are saved to a local cache;
    # a team that still fails after the normal retries gets one more try after a pause, and if that fails too
    # it reuses its last good cached values (stale by at most a week or so) instead of showing '--'.
    _extra_cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cfb_espn_extra_cache.json")
    try:
        with open(_extra_cache_path) as _f:
            _extra_cache = json.load(_f)
    except Exception:
        _extra_cache = {}
    _is_empty = lambda d: all(d.get(k) is None for k in ("TFL_Def_PG", "Stuffs_Off_PG", "ToP_Display", "FG_Pct"))
    _failed = []
    for team_name in playing_teams:
        tid = name_to_id.get(team_name)
        if not tid:
            continue
        extra = fetch_espn_extra_team_stats(tid, season_year, team_name=team_name)
        if _is_empty(extra):
            _failed.append((team_name, tid))
            continue
        _extra_cache[team_name] = extra
        extra['Clean_Name'] = team_name
        extra_rows.append(extra)
    if _failed:
        print(f" -> retrying {len(_failed)} ESPN extra-stat failure(s) after a short pause: {[t for t, _ in _failed]}")
        time.sleep(8)
        for team_name, tid in _failed:
            extra = fetch_espn_extra_team_stats(tid, season_year, team_name=team_name)
            if _is_empty(extra) and team_name in _extra_cache:
                extra = dict(_extra_cache[team_name])
                print(f" -> [ESPN extra stats] {team_name}: still failing -- using last saved values.")
            elif not _is_empty(extra):
                _extra_cache[team_name] = extra
            extra['Clean_Name'] = team_name
            extra_rows.append(extra)
    try:
        with open(_extra_cache_path, "w") as _f:
            json.dump({k: {kk: vv for kk, vv in v.items() if kk != 'Clean_Name'} for k, v in _extra_cache.items()}, _f)
    except Exception as _e:
        print(f" -> (could not save ESPN extra-stats cache: {_e})")
    if extra_rows:
        stats_lookup = pd.merge(stats_lookup, _align_names(pd.DataFrame(extra_rows), _TR_NAMES, 'ESPN extra'), on='Clean_Name', how='outer')

    # F+ / FEI / Drive Success Rate (bcftoys.com) and PPA / stuff rate
    # (CFBD, needs your own free API key -- see CFBD_API_KEY above). Pulled
    # for every FBS team (not just this week's), so extra_baselines below
    # is a real, computed league average for each stat, not a guess -- used
    # to color-grade these the same way everything else on the sheet is
    # graded, instead of leaving them plain/ungraded.
    print("Pulling bcftoys F+ / FEI / Drive Success Rate ratings...")
    bcftoys_df, bcftoys_avg = fetch_bcftoys_ratings(season_year)
    if not bcftoys_df.empty:
        stats_lookup = pd.merge(stats_lookup, _align_names(bcftoys_df, _TR_NAMES, 'bcftoys'), on='Clean_Name', how='outer')

    print("Pulling CFBD off/def PPA and stuff rate...")
    cfbd_df, cfbd_avg = fetch_cfbd_advanced_stats(season_year)
    if not cfbd_df.empty:
        stats_lookup = pd.merge(stats_lookup, _align_names(cfbd_df, _TR_NAMES, 'CFBD'), on='Clean_Name', how='outer')

    # NEW: local cache read (see load_ppd_cache() above), not a live
    # fetch -- merged case-insensitively since the cache's keys are uppercased
    # (clean_team_name(...).upper()) while stats_lookup's real Clean_Name column isn't.
    # A plain on='Clean_Name' merge here would silently match nothing.
    ppd_df = _align_names(load_ppd_cache(), _TR_NAMES, 'PPD')
    if not ppd_df.empty:
        stats_lookup['_ppd_merge_key'] = stats_lookup['Clean_Name'].str.upper()
        ppd_df['_ppd_merge_key'] = ppd_df['Clean_Name'].str.upper()
        stats_lookup = pd.merge(
            stats_lookup, ppd_df.drop(columns=['Clean_Name']), on='_ppd_merge_key', how='left'
        )
        stats_lookup.drop(columns=['_ppd_merge_key'], inplace=True)

    extra_baselines = {**bcftoys_avg, **cfbd_avg}

    # Belt-and-suspenders duplicate guard, on top of the dedup already done
    # inside fetch_all_teamrankings_stats/fetch_bcftoys_ratings/
    # fetch_cfbd_advanced_stats individually: if ANY future merge source
    # ever slips a duplicate Clean_Name through anyway, stats_lookup.loc
    # [team_name] below would silently return a multi-row DataFrame instead
    # of a Series for that team, and every '.get()' call on it downstream
    # would then throw "The truth value of a Series is ambiguous" -- exactly
    # what crashed a real run on 2026-09-20 (traced to a CFBD duplicate).
    # This is the last line of defense right before the index is set, so a
    # duplicate from ANY source (not just CFBD) gets caught here too.
    dup_names = stats_lookup['Clean_Name'][stats_lookup['Clean_Name'].duplicated(keep=False)].unique()
    if len(dup_names):
        print(f" -> ⚠ stats_lookup had duplicate Clean_Name row(s) after all merges: {list(dup_names)} "
              f"-- keeping the first row for each so the report doesn't crash. If this keeps happening for "
              f"the same team, check which fetch_*() function is the source.")
        stats_lookup = stats_lookup.groupby('Clean_Name', as_index=False).first()

    stats_lookup.set_index('Clean_Name', inplace=True)

    # groups=80 in the schedule pull means "at least one FBS team," not "both
    # teams are FBS," so early-season FCS buy-games still come through.
    # TeamRankings only covers FBS, so the FCS side would show as a blank "--" row
    # for every stat. Rather than maintain a list of FCS school names, drop any
    # game where either side has no stats at all.
    # Checking that the team is in stats_lookup.index isn't enough: the later outer
    # merges (FPI/QBR/TFL-ToP-FG%, all ESPN-sourced) can add a row for a team
    # TeamRankings has no core numbers for, leaving every core column NaN. Check
    # that Off_Yds_PG, which only TeamRankings provides, has a value instead.
    known_teams = set(stats_lookup.index[stats_lookup['Off_Yds_PG'].notna()])

    # NEW: before dropping anything, try to rescue schedule
    # names that are only MISSING from known_teams because of an unmapped
    # abbreviation/formatting gap (the same failure mode as LSU/Ole Miss and
    # New Mexico St/N Texas before it) -- see fuzzy_match_unknown_team()'s
    # docstring above for exactly how/why this is safe. Only renames
    # schedule_df's own team labels onto a name ALREADY present in this
    # week's real known_teams; never fabricates a team or a stat value.
    unmatched_names = (set(schedule_df['Away_Team']) | set(schedule_df['Home_Team'])) - known_teams
    rescued = {}
    for raw_name in unmatched_names:
        hit = fuzzy_match_unknown_team(raw_name, known_teams)
        if hit:
            rescued[raw_name] = hit
    if rescued:
        print(f" -> Auto-matched {len(rescued)} team name(s) that would otherwise have been dropped "
              f"(ESPN/TeamRankings naming gap, resolved by generic abbreviation normalization -- add a "
              f"permanent entry to clean_team_name()'s mapping dict if this list keeps repeating):")
        for raw_name, matched_name in rescued.items():
            print(f"      '{raw_name}'  ->  '{matched_name}'")
        schedule_df['Away_Team'] = schedule_df['Away_Team'].replace(rescued)
        schedule_df['Home_Team'] = schedule_df['Home_Team'].replace(rescued)
        for raw_name, matched_name in rescued.items():
            schedule_df['Game'] = schedule_df['Game'].str.replace(raw_name, matched_name, regex=False)

    before_count = len(schedule_df)
    away_known = schedule_df['Away_Team'].isin(known_teams)
    home_known = schedule_df['Home_Team'].isin(known_teams)
    # CHANGED: this used to require BOTH sides to have real TeamRankings
    # stats (AND) before a game was kept -- which meant a real, known FBS team (Louisiana
    # State, UAB, Florida Atlantic) got silently hidden from the WHOLE report just because
    # its opponent that week happened to be a genuine FCS/Div II buy-game (McNeese, Samford,
    # Texas Southern) with no TeamRankings page at all. Reported missing 2026-10-04: "LSU was
    # not on there" (plus Middle Tennessee @ Kansas, Western Michigan @ Buffalo, Eastern
    # Michigan @ Massachusetts, Georgia Southern @ Coastal Carolina -- confirmed via a real
    # run's drop-log the same day). Now a game is only dropped if NEITHER side has stats,
    # which groups=80 in the schedule pull should make essentially impossible (that filter
    # already guarantees at least one real FBS team per game). The known side still prints
    # its real graded stats as always; the unmatched side gracefully shows "--" everywhere
    # (team_lookup() already handles a missing team this way -- it returns {} instead of
    # raising) instead of the whole matchup disappearing.
    keep_mask = away_known | home_known
    dropped_df = schedule_df[~keep_mask]
    partial_df = schedule_df[keep_mask & ~(away_known & home_known)]
    schedule_df = schedule_df[keep_mask].reset_index(drop=True)
    dropped = before_count - len(schedule_df)
    if dropped:
        print(f" -> Dropped {dropped} game(s) where NEITHER side has a TeamRankings stats "
              f"match (should be rare -- groups=80 guarantees at least one FBS team/game):")
        for _, r in dropped_df.iterrows():
            print(f"      {r['Game']}")
    if len(partial_df):
        # Print exactly which side of each partial game has no stats match --
        # this is the ONLY way to tell a genuine FCS buy-game (no real stats
        # exist anywhere for that opponent -- nothing to fix) apart from a
        # real FBS team just getting missed by clean_team_name's mapping
        # (e.g. LSU/"Louisiana State" and Ole Miss/"Mississippi" -- both
        # fixed above, but this print is what will catch the *next* one
        # instead of it silently showing as a blank "--" row).
        print(f" -> Kept {len(partial_df)} game(s) with a real FBS team on one side whose "
              f"opponent has no TeamRankings stats match (genuine FCS/Div II buy-game, or a "
              f"naming gap) -- that side will show '--' throughout instead of being hidden:")
        def _candidate_names(bad_name, known):
            """Finds any known_teams entry that shares a real word (4+ letters, so
            "at"/"the"-type noise can't match) with the unmatched name -- e.g.
            "Middle Tennessee" sharing "Middle" or "Tennessee" with whatever
            TeamRankings' own scraped name for that school actually is. This is
            how a real naming gap gets found WITHOUT guessing: if the school is
            real FBS, its TeamRankings row is in `known` under some name, and
            that name almost always shares at least one real word with the
            ESPN-side name -- print it and the exact string TeamRankings uses is
            right there, no more trial and error.
            """
            bad_words = {w for w in re.split(r"\s+", bad_name) if len(w) >= 4}
            if not bad_words:
                return []
            hits = [kt for kt in known if bad_words & {w for w in re.split(r"\s+", kt) if len(w) >= 4}]
            return sorted(hits)[:5]

        for _, r in partial_df.iterrows():
            missing_side = []
            if r['Away_Team'] not in known_teams:
                missing_side.append(f"AWAY: {r['Away_Team']}")
            if r['Home_Team'] not in known_teams:
                missing_side.append(f"HOME: {r['Home_Team']}")
            print(f"      {r['Game']}  ->  no stats match for: {', '.join(missing_side)}")
            for side in missing_side:
                bad_name = side.split(": ", 1)[1]
                candidates = _candidate_names(bad_name, known_teams)
                if candidates:
                    print(f"          -> closest known_teams name(s) sharing a real word with "
                          f"'{bad_name}': {candidates}  (if one of these is really the same "
                          f"school, add '{bad_name}' -> '<that name>' to clean_team_name()'s dict)")
                else:
                    print(f"          -> no known_teams name shares a word with '{bad_name}' at "
                          f"all -- likely a genuine FCS/Div II opponent with no TeamRankings page, "
                          f"not a naming gap.")
        print("    If any of the names above are actually real FBS teams (not FCS/Div II "
              "opponents), clean_team_name()'s mapping dict is missing that one -- add it "
              "there using the exact name TeamRankings' stat tables use.")

    print("Updating stat-weighted win prediction model...")
    stat_history = load_stat_history()
    newly_recorded = record_completed_games(stat_history, schedule_df, stats_lookup)
    if newly_recorded:
        print(f" -> Recorded {newly_recorded} newly completed game(s) into the persistent stat history "
              f"({len(stat_history['games'])} total game(s) on record).")
    else:
        print(f" -> No new completed games to record this run ({len(stat_history['games'])} total game(s) on record).")
    included_stats, model_accuracy, model_correct, model_decided, model_total = tune_stat_weights(stat_history)
    weights_by_key = {key: weight for _, key, weight, _, _ in included_stats}
    included_keys = [key for _, key, _, _, _ in included_stats]
    miss_postmortems = generate_miss_postmortems(stat_history, included_keys, weights_by_key)
    sacks_agreement = compute_sacks_agreement_breakdown(stat_history, included_keys, weights_by_key)
    fei_bucket_stats = compute_margin_bucket_stats(stat_history, included_keys, weights_by_key, stats_lookup, "FEI")
    fplus_bucket_stats = compute_margin_bucket_stats(stat_history, included_keys, weights_by_key, stats_lookup, "F+")
    if model_total:
        print(f" -> Model backtest: {model_correct}/{model_decided} = "
              f"{(model_correct/model_decided*100 if model_decided else 0):.1f}% accuracy "
              f"using {len(included_stats)} weighted stat(s), across {model_total} total game(s) on record.")

    # Full "common denominator" list -- every tracked stat's own individual
    # win rate across all recorded games, not just whichever ones the
    # weighted model above happened to select. This is the literal answer
    # to "what % of winning teams had this stat in common," for every stat,
    # so nothing is hidden behind the tuned model's final picks.
    raw_win_rates = _individual_stat_win_rates(stat_history)
    _label_by_key = {key: label for label, key, _ in _STAT_SIGNAL_SPECS}
    all_stat_rates = sorted(
        [(_label_by_key.get(k, k), k, wr, n) for k, (wr, n) in raw_win_rates.items()],
        key=lambda x: x[2], reverse=True
    )

    model_results = {
        "included": included_stats,
        "included_keys": included_keys,
        "accuracy": model_accuracy,
        "correct": model_correct,
        "decided": model_decided,
        "total_games": model_total,
        "postmortems": miss_postmortems,
        "target_accuracy": _TARGET_ACCURACY,
        "all_stat_rates": all_stat_rates,
        "sacks_agreement": sacks_agreement,
        "fei_bucket_stats": fei_bucket_stats,
        "fplus_bucket_stats": fplus_bucket_stats,
    }

    # ---- Backtested margin/spread model
    # The old GAME FLOW FORECAST margin used hand-picked weights that had never
    # been checked against a completed game. This mirrors the stat-vote model's
    # pattern immediately above: load a persistent history, backfill/record real
    # games into it, fit fresh every run. See cfb_matchup_deltas.py's
    # tune_forecast_weights() docstring for the limitation (backfilled rows use
    # each team's CURRENT stats, not a pre-game snapshot -- same tradeoff the
    # stat-vote model above already accepts).
    print("Updating real backtested margin/spread model...")
    import cfb_matchup_deltas as deltas_mod
    forecast_history = deltas_mod.load_forecast_history()
    newly_backfilled = deltas_mod.backfill_forecast_history(
        forecast_history, stat_history, stats_lookup,
        compute_forecast_factors, compute_home_field_adv,
    )
    if newly_backfilled:
        print(f" -> Backfilled {newly_backfilled} completed game(s) into the real margin-forecast "
              f"history ({len(forecast_history['games'])} total game(s) on record).")
    else:
        print(f" -> No new completed games to backfill into the margin-forecast history "
              f"({len(forecast_history['games'])} total game(s) on record).")
    fitted_margin_model = deltas_mod.tune_forecast_weights(forecast_history)
    if fitted_margin_model:
        print(f" -> Margin model: real OLS fit on {fitted_margin_model['n']} game(s), "
              f"R²={fitted_margin_model['r2']:.3f}, MAE={fitted_margin_model['mae']:.1f} pts "
              f"(in-sample). Replacing the hand-picked _FORECAST_WEIGHTS for this run.")
    else:
        print(f" -> Margin model: only {len(forecast_history['games'])} complete real game(s) on record "
              f"(need {deltas_mod.MIN_MARGIN_SAMPLES}) -- using the original hand-picked weights for now.")

    print("Building full weekly PDF document summary report...")
    generate_pdf_report(schedule_df, stats_lookup, extra_baselines=extra_baselines, model_results=model_results,
                         fitted_margin_model=fitted_margin_model)
    print("Success! Generated layout report at: 'generated/cfb_matrices_outlook.pdf'")

if __name__ == "__main__":
    main()

# ==========================================
# PART 4: PDF DOCUMENT GENERATOR END
# ==========================================
