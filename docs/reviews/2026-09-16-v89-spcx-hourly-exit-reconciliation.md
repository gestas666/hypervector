# V89 SPCX hourly exit reconciliation — September 16, 2026

The SPCX long closed at 09:00:15.611 UTC with **+$0.567607 net**. Independent Decimal arithmetic matched sixteen records to their exact native ledger bytes: two fills and fourteen hourly funding receipts. This is a small realized win, not evidence of improved strategy expectancy.

| Item | Retained native evidence |
| --- | --- |
| Lifecycle | `xyz:SPCX:546010609566` |
| Entry | 3.47 long at 144.01; September 15, 19:00:20.653 UTC |
| Exit | 3.47 at 144.21; OID `546576225156`; September 16, 09:00:15.611 UTC |
| Gross | +$0.694000 |
| Fill fees | −$0.086410 |
| Fourteen funding receipts | −$0.039983 |
| Net | **+$0.567607** |
| Holding time | 50,394,958 ms, just under fourteen hours |
| Observed leverage | 10x |

The native close chain contains the hourly recipe decision, one reduce-only close intent, one accepted filled acknowledgement, verified flat, the fill receipt, and a final `FLAT` state. Recorded reconciliation shows no open orders. No transport or restart recovery is reported in that chain. The captured checkpoint generated before the 09:02:44 evidence freeze reports all seven cohort assets flat and zero faults. Those are dated observations, not a guarantee about later positions.

The configured band-reentry recipe closes a long when the completed hourly close is at or above the band mean. Its recorded close reference was 144.23 versus a reported mean of 143.85250000000002. The predicate is consistent with the recorded exit. The twenty underlying hourly candles and band calculation were not independently reconstructed in this event audit. Entry readiness being false does not invalidate a separate exit-side decision.

The retained completed-path report covers 839 completed one-minute bars. It reports approximately 29.859 bps favorable excursion, 111.798 bps adverse excursion and 15.971 bps peak giveback. These observed candle extrema are not executable counterfactual profits. The gross realized move was approximately 13.888 bps. No stop, profit-lock or regime change is justified by this single path.

The frozen compatible-profile history now contains 22 fills, ten closed lifecycles, two wins, eight losses and zero open lifecycles, with net **−$29.487144**. These totals include compatible history and are not ten new trades from the current backend run. The small, correlated sample remains insufficient to establish durable strategy edge or diagnose a logic defect from losses alone.

## Evidence and monitoring

The evidence directory is `data/logs/research/bidirectional_cohort/v89_captured_provider_assembly_20260916_v1/spcx_exit_20260916_v1/`:

- `capture.json` authenticates frozen native portfolio/SPCX ledger ranges and checkpoint bytes.
- `accounting_source_records.json` retains all sixteen native-byte-matched funding/fill records, including source offsets and hashes.
- `accounting_reconciliation.json` retains the read-only database query and exact independent Decimal reconciliation.
- `execution_reconciliation.json` records the native close chain, scope, recipe consistency and limitations.
- `trade_reflection.json` preserves the exact closed lifecycle projection.

The former lifecycle and diagnostic observers both returned `native_transition` and exit 0. Successors resumed their exact cursors after the event was reviewed. Only the lifecycle observer's SPCX cursor advanced through already-reconciled close/fill sequences 394560 and 394564, with proof retained in its anchor; other ledger cursors were preserved. The new observers have PID 57652/session 69919 and PID 57672/session 44554. They own no financial processes. The backend remains PID 30603 with the original bound run identity.

**Recommendation / why now:** retain the verified outcome and continue observing new native execution. **Applicable context:** configured hourly band-reentry mean-reversion exit; canonical context is descriptive, not an invented replacement exit rule. **Alternative:** infer a defect or retune from one realized path; the available sample does not support that conclusion.

**Proposed live change:** none. **Expected upside:** reliable outcome attribution and detection of future divergence, without a claimed return uplift. **Main risks / remaining validation:** later receipts can update dated state, candle extrema omit achievable execution, and the reported band mean has not been independently recomputed here. The separate full-native account research remains unfinished.

**Success metrics / falsifiers:** unique native entry/exit fills, contiguous owned funding hours, exact cash reconciliation, correct side/size and verified empty protection after close. A missing funding receipt, duplicate close, changed ledger byte, inconsistent recipe input or residual position/order reopens the audit.

**Confidence:** high for the authenticated accounting and retained execution prefix; limited for strategy expectancy and counterfactual exit changes. **Rollback:** no live change was made. **Explicit approval requested:** none for this read-only audit.
