# Complete the outstanding band-history correction

The September 7 band correction remains absent from the September 15 installed
source and prestart bundle. The preserved regression fails today: identical last
20 hourly closes yield different means around 111.76 after older history is
removed. The current live process must not be restarted or otherwise controlled.

1. Preserve current source, the failing regression, and the prior candidate's
   provenance. Reuse the existing fixed-window correction, not a new tolerance.
2. Before changing implementation, rerun the original frozen SPCX history study
   on current source: full, 333-quarter and 1344-quarter histories; the three
   declared nominal/adverse/full-fee costs for each. Preserve every result.
3. Apply only window-local mean/population-deviation reductions. Retain gap
   resets, 20-hour lookback, completed-bar timing, ATR initialization, strategy
   rules, sizing, leverage and execution controls. Re-run the same study.
4. Compare all entry/exit decisions, band values and complete trade audit lists.
   Document any difference instead of accepting a numerical tolerance at an
   execution boundary. Check current native inputs separately where available;
   do not claim the old unretained startup seed can be reconstructed.
5. Run affected provider/causality/restart tests and bounded coverage, preserve
   rollback bytes, and install the verified source under existing corrective
   authorization. Activation waits for a normal user-controlled backend start.
6. Append current evidence to the original candidate hypothesis. Separately
   reconcile the older deadline candidate with its authenticated installed
   successor. Preserve historical revisions and unopened prospective outcomes.

Success requires history-independent band/exit results for identical complete
windows, current integration tests, explicit economic comparisons and source
provenance. ATR remains history-dependent by design. This correction does not
establish profitable expectancy or universal numerical behavior.
