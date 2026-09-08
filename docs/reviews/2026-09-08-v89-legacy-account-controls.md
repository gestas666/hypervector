# Registered historical account compatibility

The incremental account adapter at `e26305a1e809c7faef6d4e0da722ce095e2a7327`
reproduces all 36 registered July 21–September 7 controls, covering 6,360 trade
records and 2,499,924 marked path rows. Every original twelve-column path, report,
and daily attribution matches exactly. These records reuse the explored historical
source/cost/clock variants; they are not 6,360 independent prospective trades.

The adapter uses the new account's funding, closing and reconciliation arithmetic.
Historical entries retain their supplied quantities, margins, clocks and absolute
fees. Separate registered input types do not enter normal prospective batches.
No rounding precision, decision timestamp, fee rate or venue metadata is invented
to make old inputs fit a prospective sizing request.

Two outputs are deliberately distinguished. The legacy presentation retains the
original floating-point operation order and the verified supplied closed net.
The incremental ledger recomputes balances and reconciles every emitted row at
a predeclared absolute tolerance of 1e-8 USD. The largest observed residual was
2.7284841053187847e-11 USD. An independent auditor imports neither replay engine;
it compares all 29,999,088 numeric path fields, checks original path/daily bytes,
and recomputes trade gross/net, margin and funding with Decimal arithmetic.

An initial exact comparison failed: builtin float `sum()` differed from the
original sequential realized-net addition. The largest resulting close-equity
difference was 9.094947017729282e-13 USD. A focused regression reproduced the
error before correction. The adapter now preserves the original addition order;
the numerical tolerance and exact compatibility criterion were not relaxed.
The failed run and diagnosis remain in the evidence directory.

Validation includes 84 new tests and 186 existing regressions. All 270 pass from
the source archive. The account and legacy modules have complete statement and
branch coverage in the targeted suite. Cases include long/short positions,
funding before same-clock actions, instant exits, changed calendar origins,
absolute fees, source identity/clock corruption, insufficient cash, occupied
symbols and malformed account evidence. All 36 full historical archive replays match the first qualified run exactly,
including account cashflow records. The independent archive audit is byte-identical
to the first independent audit. The independent auditor also has full statement
and branch coverage, including its separate command-line execution.

The source archive contains 5,218 verified Git blobs, is 29,544,544 bytes, and
has SHA256 `f39dafd94a3ea7b1702e741b66fb837cfc33523d6c45df28eb00d7f8d2293d35`.
The archived environment uses Python 3.13.13, pandas 3.0.3, NumPy 2.4.6 and
PyArrow 25.0.0. Reproduction in another dependency environment is untested.

Confidence is high for this registered-input compatibility scope, conditional
on the pinned source identities and arithmetic environment. A changed input,
exact path/report/daily mismatch or ledger residual above 1e-8 USD invalidates
the claim. Future performance confidence remains low. This work neither tests
new economic outcomes nor establishes provider/regime parity, receipt-based
source assembly, route-specific fill timing, trigger behavior or full funding/
metadata/terminal coverage for the prospective replay.

At 22:29 UTC both public research collectors were alive. All fifteen pinned
collector source hashes and the active live profile hash were unchanged. The
new collector's retained health snapshot showed 791 valid requests, zero failed
or invalid requests and zero deferred queries; this is a timestamped observation,
not an assurance of future service. Neither sealed study's outcomes were read.

The next investigation is causal source assembly and receipt-to-modeled-entry
clock mapping against the frozen provider deadlines, followed by provider/regime
and complete strategy replay parity. The September 9–23 protocol remains fixed,
with no automatic promotion and no real-money deployment in this qualification.

Evidence: `data/logs/research/bidirectional_cohort/v89_legacy_account_qualification_20260908_v1/`.
