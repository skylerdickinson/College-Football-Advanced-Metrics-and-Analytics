# Real Per-Stat Predictive Power -- CFB Project

Computed directly from your own `cfb_stat_history.json` real game/vote record -- 48 real logged games as of this run. Not a generic internet claim: this is your program's own actual track record, same real data `compute_sacks_agreement_breakdown()` already uses for the Def Sacks/Game caution flag, just run across every stat instead of one.

**How to read this:** for each stat, "win % when better" is the real share of your logged games where the team with the better number on that specific stat (already direction-corrected -- e.g. for an *allowed* stat, "better" means lower) actually won the game. The record shown (e.g. 31/44) is real hits over real games where BOTH teams had real data for that stat -- not every stat has data for every game, so sample sizes vary and are shown honestly rather than padded.

**Sample size caveat, stated plainly:** 48 games is a real early-season sample (2026 season, a few weeks in), not a full-season or multi-year record. A handful of games can swing a percentage several points -- treat anything under ~30 games as noisier, and expect these numbers to sharpen as more real games get logged through the season. This isn't a one-time report -- rerun the aggregation periodically as cfb_stat_history.json grows.

## Full ranked breakdown

| Stat | Win % When Better | Real Record |
|---|---:|---:|
| F+ | 85.1% | 40/47 |
| FEI | 85.1% | 40/47 |
| Off Points/Game | 83.3% | 40/48 |
| Off Havoc Rate (suffered) | 83.3% | 40/48 |
| Off F+ | 83.0% | 39/47 |
| Off FEI | 80.4% | 37/46 |
| Net Turnover Margin | 79.5% | 31/39 |
| FPI | 79.3% | 23/29 |
| Off Efficiency | 79.3% | 23/29 |
| Off PPA | 77.1% | 37/48 |
| Def Open Field Yards Allowed | 77.1% | 37/48 |
| Def F+ | 76.6% | 36/47 |
| Def FEI | 76.6% | 36/47 |
| Def Sacks/Game | 75.6% | 31/41 |
| Def PPA Allowed | 75.0% | 36/48 |
| Def Yards/Rush Att Allowed | 74.5% | 35/47 |
| Off Yards/Play | 72.9% | 35/48 |
| Def Rush Yards/Game Allowed | 72.9% | 35/48 |
| Off Success Rate (CFBD) | 72.9% | 35/48 |
| Def Success Rate Allowed (CFBD) | 72.9% | 35/48 |
| QBR | 72.4% | 21/29 |
| Def Yards/Play Allowed | 72.3% | 34/47 |
| Off Yards/Pass Attempt | 70.8% | 34/48 |
| Off Sacks Allowed/Game | 70.7% | 29/41 |
| FG% | 70.6% | 12/17 |
| Opp Success Rate Allowed (DSR) | 70.5% | 31/44 |
| Def Yards/Pass Att Allowed | 70.2% | 33/47 |
| Def Points/Game Allowed | 70.2% | 33/47 |
| Net Success Rate | 69.6% | 32/46 |
| Off Success Rate (bcftoys) | 68.9% | 31/45 |
| Def Yards/Game Allowed | 68.8% | 33/48 |
| Def Havoc Rate (forced) | 68.8% | 33/48 |
| Off Rush Yards/Game | 68.1% | 32/47 |
| Def Power Success Rate Allowed | 68.1% | 32/47 |
| Off Yards/Game | 66.0% | 31/47 |
| Off Yards/Rush Attempt | 65.2% | 30/46 |
| Def 2nd Level Yards Allowed | 64.6% | 31/48 |
| Off Explosiveness | 64.6% | 31/48 |
| Def Stuff Rate (forced) | 60.4% | 29/48 |
| Def TFL/Game | 59.3% | 16/27 |
| Off Power Success Rate | 59.1% | 26/44 |
| Off Pass Yards/Game | 56.2% | 27/48 |
| Def Line Yards Allowed | 56.2% | 27/48 |
| Def Explosiveness Allowed | 56.2% | 27/48 |
| Off Stuff Rate (suffered) | 54.2% | 26/48 |
| Off Line Yards | 52.1% | 25/48 |
| Off 2nd Level Yards | 52.1% | 25/48 |
| Off Open Field Yards | 50.0% | 24/48 |
| Def Pass Yards/Game Allowed | 45.8% | 22/48 |
| Def Efficiency | 41.4% | 12/29 |

## Stats tracked but with ZERO real logged votes

These are defined in `_STAT_SIGNAL_SPECS` as included stats, but never show up in any real game's `votes` dict across all 48 games -- meaning something in the pull or vote-computation is silently dropping them, not that they're genuinely 0% predictive. Real gap, not a guessed one:

- Def 3rd Down % Allowed (`Def_3rd_%`)
- Def Red Zone % Allowed (`Def_RZ_%`)
- Off 3rd Down % (`Off_3rd_%`)
- Off Red Zone % (`Off_RZ_%`)
- Off Stuffs Allowed/Game (`Stuffs_Off_PG`)
