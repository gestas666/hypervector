# Equal-cap quote capacity and current costs

Study `v89_equal_cap_quote_feasibility_20260908_v1`; research authority only.
Source `c28c241c9415296557476704941f8ab24af9fa1f`. The capture itself was
committed as `293b0a7` before the sample. The frozen protocol and preceding
allocation journal revision were authenticated before acquisition.

## Decision

**Retain the equal-cap allocation as an inactive research candidate.** Every
observed book supported both quantities on the configured entry and opposing
hypothetical close sides. This removes a current snapshot-capacity unknown; it
does not repair the historical candidate's greater drawdown, roughly doubled
average deployed notional, or weaker later full-fee stress.

Confidence is **high for this captured sample and its arithmetic**, and **low
for future liquidity or profitability**. A different book, fee mode, size rule,
source mismatch, or failed independent reproduction would update the capacity
claim. Actual fills, production latency, resting stops, cancellations and future
returns were not measured.

## Inputs and observation boundary

The sample contains exactly 36 rounds, seven books per round, from September 8
**18:03:20.973–18:09:13.185 UTC**. All 252 Info responses were successful and
usable. The ten configured asset/direction combinations, each under original
and equal caps, produced **720 complete probes in 20 cells**. There were no
missing books, invalid books, zero rounded quantities, insufficient-depth
probes or receipt/venue clock inversions in this sample.

The typed configuration fingerprint remains
`39e334fc97f3cbe21bac30e53e91524d6a4cf9727370a0f69bc2d51039667f7a`.
BTC, ETH and HYPE execute long; SOL executes short; SPCX, SNDK and Brent permit
both directions. Seven route identities and configured leverage are unchanged.
Original caps are $2,500 for BTC/HYPE and $500 for the other five assets. The
comparison is $7,500 / 7 per asset, rounded down from each same observed midpoint.
This is a standalone size probe, not a reconstruction of a backend order.

All current metadata limits match configured venue maxima and support requested
leverage. Size decimals are BTC 5, ETH 4, SOL 2, HYPE 2, SPCX 2, SNDK 3 and
Brent 2. Equal-cap notional lost to rounding ranges up to $1.787371 on SNDK;
every quantity, step and notional difference is retained in the comparison data.

The [venue size specification](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/tick-and-lot-size)
locates size precision in metadata. The
[Info specification](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint)
limits each returned book side to 20 levels. The study requested full precision
and did not extrapolate beyond those levels. Its scheduled book demand was 84
REST weight/minute against the documented 1,200/minute per-IP budget; other
clients' consumption was not measured. See the
[rate-limit specification](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits).
Exact documentation bodies, URLs, request/receipt times and hashes are archived.

## Equal-cap measurements

The minimum capacity is the smallest of entry or opposing close visible quantity
divided by the rounded probe quantity across the 36 observations. The hurdle is
the instantaneous round-trip spread/impact plus current taker fees, divided by
rounded midpoint notional. Both directions of each XYZ asset have the same
round-trip hurdle because their entry and close sides exchange roles.

| Asset | Minimum visible capacity / quantity | Maximum book-only hurdle, bps | Current fee + book hurdle, median / maximum bps |
|---|---:|---:|---:|
| BTC | 1,267.69 | 1.1028 | 8.7673 / 9.7432 |
| ETH | 3,612.99 | 1.7749 | 9.0414 / 10.4149 |
| SOL | 3,275.90 | 2.9702 | 9.6030 / 11.6111 |
| HYPE | 20.95 | 2.5268 | 8.7748 / 11.1660 |
| SPCX | 1,597.95 | 1.9624 | 2.3819 / 3.6905 |
| SNDK | 1,401.43 | 2.2113 | 2.3048 / 3.9391 |
| Brent | 86.13 | 1.8736 | 2.1427 / 3.6016 |

All original-cap probes also completed. HYPE had the smallest original-cap
visible capacity multiple, 8.98. Increasing the five $500 caps slightly increased
some multi-level costs; reducing BTC/HYPE quantities slightly reduced their
worst observed costs. The full original/equal cells, every VWAP, level count,
entry/close impact and capacity are retained rather than selected by favorability.

Unsigned `userFees` again reported a 4.5-bps base taker rate and 4% referral
discount. Current XYZ metadata reported enabled growth mode and deployer scale
1.0 for each of the three assets. The existing typed implementation of the
[published fee formula](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees)
therefore gives **4.32 bps per side for core** and **0.864 bps for XYZ**, assuming
no aligned-collateral discount. Aligned status remains unresolved, explicitly
uncredited; actual fill fees remain authoritative. Disabling growth mode while
holding other observed inputs constant yields 8.64 bps per side for XYZ. Under
that stress, maximum equal-cap book-plus-fee hurdles are 19.2436 bps SPCX,
19.4898 bps SNDK and 19.1536 bps Brent. These are current fee scenarios, not
historical fee corrections or profitability forecasts.

Additional 2.5 and 5.5 bps per side are separately reported as friction stress.
They may overlap visible book impact. They exclude funding and do not represent
measured future slippage. Requests within each round were sequential: round
collection spans were 1.985–2.820 seconds. Start lateness was 0–9 ms; per-asset
request intervals ranged 9.422–10.504 seconds. Exchange age at receipt ranged
313–970 ms. These client measurements are not production execution latency or
an atomic cross-asset snapshot.

## Verification and limits

- **57 offline tests pass.** The two pure capacity/metadata modules cover all
  92 statements and 24 branches. Tests include direction, rounding, failure
  retention, invalid/crossed/nonfinite books, unavailable metadata, changed
  leverage limits, delisting, fee modifiers, request clocks and tampering.
- An implementation-independent Decimal auditor authenticates **293 capture
  files**, checks raw/normalized parity for **252 books**, and recalculates all
  **720 probes / 27,216 numeric fields**, including every worst-capacity cell.
  Maximum absolute discrepancy is `1e-9`; tolerance is `1e-8`. Deliberate
  arithmetic corruption and partial-depth reference behavior are tested.
- All **5,147 Git source blobs** match the frozen source archive. Offline replay
  from that archive reproduces all three output JSON files byte-for-byte; the
  separate audit reproduces byte-for-byte too.
- Ruff and new-file size/function/annotation/docstring checks pass. Coverage is
  scoped to the stated modules, not the complete trading system or network I/O.

No live configuration, strategy, sizing, leverage, execution behavior, TUI or
trading/reporter process lifecycle was changed. At **18:14:25 UTC**, the tracked
backend/supervisor/reporter/TUI PIDs were absent, configuration bytes remained
unchanged, and the checkpoint was still from 14:04:48 UTC. Account positions
were not refreshed by this quote study; the older 14:11 account observation
cannot establish a current flat state.

## Next investigation

Prepare the exact inactive equal-cap configuration and a separate prospective
comparison contract, keeping original controls, unchanged signal/stop rules and
the measured capital/drawdown trade-offs explicit. The sample does not justify
fitting intermediate weights. Keep the September 8–22 SNDK/Brent experiment
sealed; do not inspect or reconstruct its early outcomes. A later live sizing
or deployment proposal requires explicit human approval under the active goal's
Human control instruction.

Evidence root:
`data/logs/research/bidirectional_cohort/v89_equal_cap_quote_feasibility_20260908_v1/`.
Key artifacts: `protocol.md`, `preregistration.json`, `capture/manifest.json`,
`first_run/{report,observations,comparisons}.json`, `independent_audit.json`,
`source_archive_verification.json`, `archive_replay_comparison.json`,
`tests.log`, `coverage_final.json` and `runtime_observation.json`.
