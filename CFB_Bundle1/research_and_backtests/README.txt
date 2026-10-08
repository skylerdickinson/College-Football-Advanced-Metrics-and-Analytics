research_and_backtests/
========================
On-demand research tools -- NOT run automatically by cfb_working_schedule.py
and NOT needed for the weekly PDF report. Run these by hand only when you
want to dig into how well the model is really doing.

cfb_stat_vote_validation_backtest.py
  Validates the PDF's "STAT-WEIGHTED WIN PREDICTION MODEL" (FEI/F+/Off
  Havoc Rate, currently reported at 87.5% off 48 in-season games) against
  5 real, complete past seasons (2021-2025) using leave-one-season-out
  cross-validation -- tunes stat weights on 4 seasons, scores on the 5th
  (held-out) season, so the reported accuracy isn't graded on the same
  games that picked which stats to use. Needs a real CFBD_API_KEY (already
  set in cfb_working_schedule.py) and real network access to bcftoys.com
  and api.collegefootballdata.com. Takes a few minutes to run (pulls 5
  real seasons of bcftoys + CFBD data). Run it with:

      python3 research_and_backtests/cfb_stat_vote_validation_backtest.py

  Read the big docstring at the top of the file before trusting the
  number it prints -- it's honest about exactly what kind of "backtest"
  this is and isn't (season-level held-out validation, not the same
  week-by-week walk-forward the NFL project's calibration backtest does --
  bcftoys doesn't publish historical week-by-week FEI/F+ snapshots, only
  each season's final numbers, so that's not achievable here the same way).
