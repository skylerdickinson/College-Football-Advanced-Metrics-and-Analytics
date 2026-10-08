"""
Runs all THREE real reports with one command:
  1. the matrices report      (cfb_working_schedule.py's own real main())
  2. the deep-dive report     (cfb_matchup_deep_dive.py's real main())
  3. the skinny report        (the_skinny.py's real main() -- the original
                                print-and-carry sheet; a DIFFERENT script
                                from cfb_working_schedule.py, despite the
                                similar name -- see the naming note below)

Naming note: cfb_working_schedule.py produces the MATRICES report
(cfb_matrices_outlook.pdf), and the_skinny.py produces the actual SKINNY
report (the_skinny.pdf). Two different scripts, two different PDFs.

Deliberately calls each script's real, already-tested main() separately
rather than trying to splice one script's already-fetched stats_lookup
into another's report-builder to save a duplicate fetch. That would mean
hand-reconstructing each script's own real intermediate state here
(model_results / dataset dicts -- several real, non-trivial computations
each), which risks silently drifting from what each report actually
produces on its own. This way is slower (every real stat gets pulled
three times, once per script's own real fetch sequence) but it's the
honest, zero-risk way to guarantee every report stays byte-for-byte what
running that script alone would have produced.

Safe to run twice in a row, or run any of the three scripts standalone
too -- record_completed_games() (used by cfb_working_schedule.py and
the_skinny.py) is keyed by ESPN's own real Event_Id and
backfill_forecast_history() (used by all three, for the real backtested
margin model) is keyed the same way, so calling them once per script in
the same run never double-counts a completed game into either persistent
history file.
"""
import sys
import os
import subprocess

# this only ever put research_and_backtests/ itself on
# sys.path, which is fine for the "import cfb_matchup_deltas" calls that
# happen *inside* cfb_working_schedule.py later, but does nothing for the
# "import cfb_working_schedule as cws" line right below -- that module
# lives one directory UP, in cfb/. Without cfb/ also on sys.path, this
# script only worked if something outside itself (an IDE's run config, a
# stray PYTHONPATH, running from the exact right cwd with -m, etc.) was
# quietly supplying that. Adding both directories here makes this file
# runnable on its own from anywhere, regardless of cwd or how it's launched.
# This doesn't assume where THIS file sits: it collects its own directory, that
# directory's parent, and a "research_and_backtests" subfolder under
# either one (whichever actually exists), so cfb_working_schedule.py,
# cfb_matchup_deep_dive.py, cfb_matchup_deltas.py, and the_skinny.py all
# resolve regardless of whether this file is at the top level of cfb/ or
# tucked inside research_and_backtests/.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_THIS_DIR)
_CANDIDATES = {
    _THIS_DIR,
    _PARENT_DIR,
    os.path.join(_THIS_DIR, "research_and_backtests"),
    os.path.join(_PARENT_DIR, "research_and_backtests"),
}
for _p in _CANDIDATES:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import cfb_working_schedule as cws
import cfb_matchup_deep_dive as dd
import the_skinny


def main():
    print("=" * 70)
    print("STEP 1/6 -- MATRICES weekly report (cfb_working_schedule.py, unchanged)")
    print("=" * 70)
    cws.main()

    print()
    print("=" * 70)
    print("STEP 2/6 -- DEEP-DIVE weekly report (cfb_matchup_deep_dive.py)")
    print("=" * 70)
    dd.main()

    print()
    print("=" * 70)
    print("STEP 3/6 -- SKINNY weekly report (the_skinny.py)")
    print("=" * 70)
    the_skinny.main()

    # STEPS 4 and 5 are standalone scripts (they parse the matrices PDF step 1 just made), so each runs as its
    # own process from this folder. A failure in one doesn't undo the reports above -- it's reported below.
    extra_failures = []
    for n, label, script in [(4, "GRID report (new.py -- All_Matchups_Grid_Report.pdf)", "new.py"),
                             (5, "SPREAD / The Nuts (spread.py -- The Nuts.pdf)", "spread.py"),
                             (6, "DELTA SCALE (cfb_delta_study.py -- grades saved pre-game deltas, prints how much a big delta matters)", "cfb_delta_study.py")]:
        print()
        print("=" * 70)
        print(f"STEP {n}/6 -- {label}")
        print("=" * 70)
        rc = subprocess.run([sys.executable, os.path.join(_THIS_DIR, script)], cwd=_THIS_DIR).returncode
        if rc != 0:
            extra_failures.append(f"{script} (exit code {rc})")

    print()
    print("=" * 70)
    print("All real reports generated:")
    print("  - generated/cfb_matrices_outlook.pdf   (matrices)")
    print("  - generated/cfb_deep_dive_outlook.pdf  (deep-dive)")
    print("  - generated/the_skinny.pdf              (skinny)")
    print("  - generated/All_Matchups_Grid_Report.pdf (grid / delta report -- new.py)")
    print("  - generated/The Nuts.pdf                (spreads -- spread.py)")
    print("  - generated/Delta_Scale_Report.txt      (how much a big grid delta matters -- cfb_delta_study.py)")
    if extra_failures:
        print("!! These steps failed -- scroll up for the error: " + ", ".join(extra_failures))
    print("=" * 70)


if __name__ == "__main__":
    main()
