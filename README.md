# College Football Matchup Analytics

A Python pipeline that pulls team stats from several sources every week, ranks every team against the FBS, and generates a set of PDF matchup reports from one command.

| | |
|---|---|
| **Language** | Python 3.9+ |
| **Libraries** | pandas, NumPy, reportlab, requests, BeautifulSoup, pypdf, pdfplumber |
| **Data sources** | TeamRankings, ESPN (FPI, Strength of Record, efficiency, QBR), bcftoys (F+, FEI), CollegeFootballData.com (advanced and per-game stats), The Odds API (betting lines) |
| **Run it** | `python3 cfb_run_all.py` |

## What it does

Each week the pipeline pulls the live schedule and every stat source, lines up team names across the different sites, ranks each team against the rest of the FBS, and rebuilds all of the reports. It records every game's numbers before kickoff and grades them against the final score afterwards, so each model's accuracy is measured on real results rather than assumed.

## The reports it generates

| Report | What it shows |
|---|---|
| Matrices report (about 120 pages) | The densest report: every stat, rank and head-to-head matrix for every game of the week, plus the full write-up of the stat-vote prediction. |
| Deep-dive report (about 240 pages) | Every stat as a two-sided matchup delta, the Fraud Index (points vs yards), percentile bands recomputed each run, and a projected score with a narrative per game. |
| The Skinny (about 60 pages) | The print-and-carry sheet: one game per page, dark theme. Records, offense-vs-defense ranks (green to red against the FBS, purple for the top 10%), and a short written read. |
| Grid report (about 15 pages) | A one-page-per-game grid of the matchup deltas with highlights for the big ones, plus a predicted team total and spread. |
| The Nuts (about 8 pages) | Projected point spreads for every game, built from the matrices report, next to the Vegas line and each team's record against the spread. |
| Delta Scale Report (text) | Grades saved pre-game deltas against final scores: how often, and by how much, the team a delta favors won as the gap gets bigger. |

## How a run works

| Step | Script | Output |
|---|---|---|
| 1 | `cfb_working_schedule.py` | Matrices report; pulls and merges every stat source; logs finished games |
| 2 | `cfb_matchup_deep_dive.py` | Deep-dive report (uses `cfb_matchup_card_v4.py` and `cfb_matchup_deltas.py`) |
| 3 | `the_skinny.py` | The Skinny |
| 4 | `new.py` | Grid report |
| 5 | `spread.py` | The Nuts: projected spreads with Vegas lines and ATS records |
| 6 | `cfb_delta_study.py` | Grades saved deltas against final scores; writes the Delta Scale Report |

## Methods

**Stat-vote model.** Each stat on the sheet votes for the team with the better number, and the pick is the weighted vote. A greedy search keeps whichever stats improve accuracy on completed games. The accuracy it reports is *in-sample*; a separate script runs a leave-one-season-out test (tune on four seasons, score on the fifth) for the honest figure.

**Game Flow Forecast (projected score and win probability).** A five-factor regression on FPI, efficiency, scoring, yardage and turnover margins, fit by least squares on completed games. The latest fit is R² 0.71 with a mean absolute error of 8.5 points, in-sample, on 140 games. It is a separate model from the stat-vote pick and the two are deliberately not reconciled.

**Season averages instead of home/road splits.** The ranked grid uses each team's season average against FBS opponents. An earlier home-versus-road split was dropped because a team with a single home game could rank in the top 10% on one blowout; games against non-FBS opponents are excluded.

**Delta study.** The first time a game appears, its matchup deltas are saved before kickoff (games already final are skipped, since stats pulled after a game are flattered by it). They are graded against the final score later, giving a test with no look-ahead.

## Technical stack

Python 3, about 11,800 lines across 17 core scripts plus stand-alone research and backtest scripts. State is kept in JSON history and cache files (no database).

| Package | Used for |
|---|---|
| pandas | Merging stat tables from different sources, groupby, percentile ranks, outer joins onto a canonical team list |
| NumPy | Least-squares fits and the matchup delta math |
| requests | API and page pulls from CollegeFootballData, ESPN, TeamRankings, bcftoys and The Odds API |
| beautifulsoup4 | Parses HTML tables from sites without an API |
| pypdf, pdfplumber | Read the finished matrices PDF back into structured data for the grid and spread scripts |
| reportlab | Builds every PDF: tables, heat-map cell colors, a dark-theme pass over finished tables |

Standard library: json, os, sys, subprocess, re, datetime, math, hashlib, tempfile, random, io.

**Skills shown:** API and HTML data acquisition with incremental caching, entity resolution across five sources (a normalization function plus an alias table), percentile ranking, regression, greedy feature selection, pre-game snapshot logging to avoid look-ahead bias, leave-one-season-out cross-validation, data-quality debugging, and programmatic PDF reporting.

## Results, stated honestly

| Test | Result |
|---|---|
| Delta study (about 130 graded games, one season) | The team a delta favors won 57% of the time when the gap was small, 64% medium, 75% large and 78% massive (top 10%). Its average final margin was +2.9, +7.4, +14.3 and +17.6 points. |
| Which deltas track the score best | FEI gap, offensive efficiency, passing-down panic, net success rate, havoc and points-per-game gap (correlation with margin about 0.55 to 0.74). Rushing Reality showed essentially none. |
| Stat-vote accuracy | Reported in-sample (about 90%, flattered by design). Use the leave-one-season-out result for the honest number. |
| Game Flow Forecast | 8.5 points of mean absolute error, in-sample. |

> **What this means:** the stats clearly track which team is better and by how much, but big gaps are often obvious mismatches that betting lines already price in. These results show the numbers track the score, **not** that they beat the spread. One season is a small sample, and the spread numbers are projections, not proven picks or betting advice.

## Setup and usage

```bash
pip install -r requirements.txt
export CFBD_API_KEY="your-key"     # free key from collegefootballdata.com
python3 cfb_run_all.py             # all reports, in order
```

Reports are written to `generated/`. Caches and history files (`cfb_*.json`) are rebuilt automatically. Run it from a normal terminal; the data sites block sandboxed or proxied environments. Betting lines need an Odds API key set as an environment variable. **Never commit a real key.**

## Data and licensing

The pipeline reads from third-party sites, each with its own terms of use. Check those terms before redistributing any pulled data, and keep cached data files and generated reports out of the repository; it should hold the code only.

## Repository layout

| File / folder | Purpose |
|---|---|
| `cfb_run_all.py` | The one command that runs every step |
| `cfb_working_schedule.py` | Data pulls, matrices report and the stat-vote model |
| `the_skinny.py`, `new.py`, `spread.py` | The Skinny, the grid report and The Nuts |
| `cfb_matchup_deep_dive.py`, `cfb_matchup_card_v4.py`, `cfb_matchup_deltas.py` | Deep-dive report, its card renderer and the Game Flow Forecast |
| `cfb_split_grid.py`, `cfb_home_away_splits.py` | Per-team averages used by the Skinny's ranked grid |
| `cfb_delta_study.py` | Records deltas before kickoff and grades them against final scores |
| `cfb_ats_odds.py` | Betting lines, against-the-spread records and team-name matching across sources |
| `research_and_backtests/` | One-off validation scripts |
| `espn_data/`, `schedule_pull/` | ESPN data pull and weekly schedule pull |
