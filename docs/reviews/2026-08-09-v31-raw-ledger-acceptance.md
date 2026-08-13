# v31 raw-ledger acceptance verifier

## Problem restatement

The aggregate v31 acceptance verifier can prove that its checkpoint contains
finite pressure metrics and continuous funding summaries. It cannot by itself
prove that those values came from the latest causal exact-symbol books or that
the funding query cursor advanced without a gap, overlap, or duplicate payment.

## Implemented control

`scripts/v31_raw_ledger_acceptance.py` snapshots stable prefixes of the exact
v31 cohort ledger and all nine asset ledgers, then writes one immutable,
report-only acceptance artifact. The implementation in
`src/hypervector/research/v31_raw_ledger_acceptance.py` requires an already
accepted aggregate report and independently verifies:

- exact v31 run, profile, configuration, and aggregate-report identity;
- top-ten imbalance recomputed from each exact-symbol Hyperliquid L2 book;
- one common provider cutoff reconstructed from book receive time and the
  reported pressure age;
- selection of the latest admissible book at or before that cutoff;
- valid positive ten-level bid and ask depth from the mainnet L2 source;
- one typed funding-window commitment per routing cycle in causal event order;
- exact funding target cutoff and contiguous cursor boundaries; and
- unique funding payments across BTC, ETH, SOL, HYPE, SP500, SPCX, SNDK, GOLD,
  and BRENTOIL inside the committed windows.

The command imports no venue execution client. A valid technical rejection is
preserved with `accepted=false` and exit status 2. It cannot transition, route,
size, enter, close, restart, or promote a strategy.

## Runtime telemetry change

Future cohort runs now append a typed `funding_reconciliation_window` event
after reconciliation. The event binds the requested start, committed end,
provider cutoff, action count, and next cursor. Cursor advancement is derived
from this validated record rather than an unjournaled local assignment.

This source change is staged only. The protected v25 process was not restarted,
so its historical ledger is not rewritten and cannot pass the new v31 raw
contract by construction.

## Validation evidence

- Red phases failed first for the absent raw verifier and then for invalid
  funding action typing and event ordering.
- Accepted, non-latest-book, inconsistent-cutoff, funding-gap, misordered-window,
  duplicate-payment, immutable-output, and report-only contracts pass.
- The aggregate and raw v31 focused tests pass together with the existing live
  runner, telemetry, transition, and route-monitor tests.
- The complete non-network Python suite passed: 4,359 tests, four intentional
  deselections, and 27 dependency/deprecation warnings.
- Changed-path Ruff, formatting, `git diff --check`, and the 500-line file
  limit pass. The live v25, checkpoint, and report-only tracker processes each
  retained launchd run count one.

## Uncertainties, failure modes, and falsifiers

Cursor continuity proves internal query-window continuity; it does not prove
that Hyperliquid returned every economically relevant funding record. Exact
causal public books do not reveal private queue rank, hidden liquidity, or the
fill that a counterfactual order would have received. Technical acceptance is
not evidence of positive expectancy.

Confidence is high for deterministic identity, causal-book arithmetic, and
internal cursor continuity under the tested schema. An accepted report with a
wrong book, mismatched cutoff, cursor gap or overlap, duplicate funding payment,
wrong profile, or any execution side effect falsifies the technical claim.
Economic confidence remains medium and must be updated by independently
resolved, both-side, after-cost v31 outcomes.
