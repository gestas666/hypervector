# Forward shadow trade attribution review

**Date:** 2026-07-29  
**Scope:** report-only DuckDB lifecycle and entry-regime attribution  
**Execution changes:** none  
**Model authority:** unchanged (`observe`)

## Problem and acceptance criteria

Manual ledger inspection was accurate for the first fresh shadow trade but is
not a durable comparison process. The required analytical output is one row per
completed backend position with the order that actually filled, entry and exit
fills, fees, signed funding, gross/net PnL, and only regime evidence causally
available when that order was submitted.

Acceptance requires stale or expired maker intents to be excluded, partial
fills to reconcile, long and short economics to use the correct sign, funding
credits and debits to retain their sign, and all reporting to remain incapable
of placing or influencing orders.

## Implementation and validation

`shadow_completed_trade_attribution` partitions the append-only ledger by
source path, run, symbol, and terminal position lifecycle. It links the first
actual entry fill back to its `client_order_id`, aggregates partial entry and
exit fills, and joins the most recent backend plus pinned strict/legacy source
labels whose availability timestamp is no later than the linked intent.

Focused tests cover:

- an expired entry intent preceding the order that fills;
- multi-fill long entry and target exit;
- a short with partial liquidation and terminal liquidation;
- positive funding drag and negative funding credit;
- absent challenger labels without false disagreement; and
- the report-only CLI contract.

All nine shadow-database tests pass. The full non-network Python suite passes
with 1,178 tests and four explicit deselections; all 33 Rust TUI integration
tests pass. Task-scoped Ruff and format checks pass, and `git diff --check`
reports no whitespace errors. A repository-wide Ruff scan still reports 33
pre-existing findings in unrelated modules; they were not changed as part of
this analytical slice.

## First real forward row

Run `51f44ff36f6b` produced one completed long:

- intent: 2026-07-29 00:10:03.912353 UTC;
- first fill: 00:11:38.879 UTC;
- final fill: 00:45:57.997 UTC;
- entry: 3 fills, 4.37301 BTC at weighted $64,029;
- exit: 38 fills, 4.373010000000001 BTC at weighted $64,158;
- quantity difference: `8.88e-16 BTC`, within the shared `1e-12` tolerance;
- gross PnL: $564.1182900000131;
- fees: $84.08445493049996;
- funding: $0;
- reconstructed net PnL: $480.0338350695131; and
- terminal ledger realized PnL: $480.03383506943646.

The approximately `$7.7e-11` difference is floating-point accumulation. The
position quantities, cash-flow components, and exit reason reconcile.

At the linked intent, the backend reported `TREND_UP`. Both source-pinned
challengers reported `TRANSITION / TR_BOTTOM_FORMING`; they changed to
`TREND_UP` five minutes later. This profitable observation weighs against
requiring source-detector agreement as an entry gate, but one trade is not a
strategy-performance sample.

## Uncertainty and failure modes

**Accounting confidence: high for this row.** It is backed by direct fill sums,
the terminal ledger value, a reconciled position quantity, and deterministic
tests. A material mismatch between reconstructed net PnL and ledger cash flow,
or unequal terminal entry/exit quantity, would falsify that assessment.

**Strategy confidence: low.** One target cannot establish an edge or quantify
regime precision. Additional resolved, venue-matched forward trades could show
that the backend's earlier trend entries are systematically late, wrong-sided,
or liquidation-prone; that would update the current interpretation.

The lifecycle key assumes the canonical append-only ledger path for a run. A
future workflow that shards one run across independent ledgers must add a
durable trade identifier before cross-file lifecycle attribution is valid.

## Recommendation

Keep runtime and ML authority unchanged. Re-run the idempotent shadow import
after each observation window, use `research-db-shadow-trades` for the aggregate
check, and evaluate detector disagreements against resolved trade outcomes.
Do not convert either source challenger into a gate from this single winner.
