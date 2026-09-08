# Registered-input compatibility for the incremental account

The source inventory authenticated all 36 previously registered allocation
controls and 6,360 supplied trade records. These are the July 21–September 7
historical controls, including the separately labeled historical sampled-stop
sensitivity. No sampled-stop rule transfers to the frozen future study.

The largest recomputed trade cashflow residual is 2.7711166694643907e-13 USD;
the largest reconstructed funding-sum residual is 2.220446049250313e-16 USD.
Each original path has 69,440–69,444 rows and twelve columns, including close
and adverse intrabar equity, cash, reserved margin, exposure and realized net.
This is verified source evidence, not new economic performance evidence.

## Compatibility contract

Preserve exact supplied quantities, fees, margins, trade identities, entry/exit
timestamps and original funding observations. Do not obtain an old control by
running prospective fractional sizing and hoping its rounded quantity matches.
Introduce distinct registered entry/exit types; the normal prospective batch
must continue to reject those types. Keep the new dynamic account behavior and
its independently reconciled synthetic fixtures unchanged.

Reuse the incremental account's state, funding, close and snapshot arithmetic.
A registered entry books its supplied quantity and margin after explicit symbol,
slot and cash consistency checks. A registered exit carries an absolute fee,
avoiding a fee-to-rate-to-fee round trip. Historical funding uses the actual
registered rate and price proxy and must reproduce the registered cashflow.
No rate, precision metadata, signal time or venue fill is invented.

There are two separately tested outputs:

1. A full legacy presentation preserves the original floating-point operation
   order and supplied closed-trade net serialization, using the incremental
   engine's actual open/closed position state. Require exact equality of every
   original path row/column and the original daily/report results. This is an
   explicit legacy representation, not prospective account arithmetic.
2. At every emitted row, compare the independently reconciled incremental cash,
   equity, reserves and exposures to that representation at the declared 1e-8
   USD numerical tolerance. Recompute each supplied trade net and funding sum
   within that same bound before replay. Export residuals rather than concealing
   the measured floating-point differences. No unchecked supplied PnL may mask
   an account mismatch.

Preserve original chronological event order: settlements and completed marks,
noninstant exits, entries, then declared same-time exits. Entry resets its modeled
mark to the supplied execution price in legacy mode, as the original engine did.
Adverse intrabar marks are a reported stress proxy and never an entry gate.

## Validation and qualification

Use small known long/short, mixed-funding, instant-exit and shifted-calendar
fixtures against the unchanged original marker. Deliberately corrupt a quantity,
fee, margin, funding cashflow, identity and boundary to require explicit failure.
Prove the prospective batch cannot accept registered entry/exit types and rerun
all existing dynamic account/independent Decimal checks after shared changes.

Then replay all 36 authenticated controls, compare every path and daily row,
reconcile all twelve columns, and retain every case regardless of its historical
return. Pin inputs and outputs, independently audit comparisons and reproduce
results from an exact source archive before claiming compatibility qualified.
The future study still requires provider/regime parity, source as-of assembly,
receipt-to-modeled-fill mapping and complete metadata/funding/terminal coverage.

Only research code and immutable evidence change. The running collectors' pinned
source files, active profile, real-money processes and both outcome seals remain
unchanged. A missing source identity, any exact legacy mismatch or residual above
1e-8 invalidates compatibility; do not relax the criterion after seeing results.
