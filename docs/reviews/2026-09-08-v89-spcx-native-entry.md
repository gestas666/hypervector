# V89 SPCX native entry reconciliation

High confidence in this bounded technical reconciliation: the SPCX entry, fee,
funding settlement and sampled protection agree between the durable ledger and
unsigned venue responses. This is one open lifecycle, with no completed-trade
profitability inference. A conflicting fill identity, cash settlement, position
quantity or protective order would falsify the corresponding finding.

## Evidence and results

The entry is run `bidirectional-live-1788809099824`, order `538846317314`,
trade `451793086136313`, at 2026-09-08 02:00:22.492 UTC. The native capture
completed at 03:38:56.644741 UTC. Each request retains its own timestamps, exact
response bytes and checksum. The later bounded ledger capture preserves raw
partial edges and validates contiguous sequences and the five previously frozen
entry events. These are sequential observations, not an atomic account snapshot.

| Check | Observed result |
| --- | --- |
| Entry | Filled buy IOC, 3.34 SPCX at 149.70, approximately $499.998 notional |
| Quantity | Matches $500 requested notional, 149.69 reference, two venue size decimals |
| Fee | $0.043199, approximately 0.863983 bps |
| Current fee projection | 0.864 bps; observed fee differs by less than $0.000001 |
| Funding | +$0.00842 at 03:00:00.017 UTC, exact ledger/native cash match |
| Position | 3.34 long, isolated 10x; native maximum 20x |
| Protection | Open full-size reduce-only sell Stop Market, order 538846363686, trigger 148.67 |
| Subsequent ledger protection | 395 sampled reconciliations through the native capture cutoff match |
| Entry acknowledgement | 1,213.681 ms after local intent |
| Native fill to stop open | 2,809 ms on the same venue clock |

The earlier quote was 7,981.704 ms old at local intent. Reference-to-fill
slippage is +0.668047 bps: +0.334024 bps from reference to midpoint and
+0.334024 bps from midpoint to ask, with zero residual from that earlier ask to
the fill. The aged quote cannot establish instantaneous market impact. Sampled
stop presence does not establish continuous presence or its eventual fill price.

The research contract used 0.9 bps entry fee and 2.5 bps entry slippage. This
single observed entry does not qualify historical fee regimes or future exit
costs. The existing fee parser explicitly retains unresolved aligned-quote
status rather than inventing that discount. Its formula source is the
[venue fee documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees).

## Validation and disposition

The existing price-decomposition regression passed all 25 tests. The audit
accepted actual evidence and rejected 13 deliberate mutations of fill identity,
price, size, fees, side and stop protection. Ruff passed; the new analysis has
438 lines and no function longer than 50 lines. No live code, configuration,
position, order, process lifecycle or execution authority changed.

Retain the reconciled entry evidence. Next economic evidence is the actual
completed lifecycle with exit, funding and fee reconciliation; an open mark
does not justify a strategy change. The independent prospective research study
started at 04:00 UTC, captured its first funding observations on time, and has
not evaluated candidate outcomes.

Artifacts under `data/logs/research/bidirectional_cohort/`:
`v89_spcx_native_20260908_v1/`, `v89_spcx_entry_acceptance_20260908_v1/`,
`v89_spcx_price_helper_regression_20260908_v1.log`, and
`v89_storage_spcx_runtime_20260908_v1/`. The analysis report pins its inputs and
executed source. The research journal indexes these immutable artifacts.
