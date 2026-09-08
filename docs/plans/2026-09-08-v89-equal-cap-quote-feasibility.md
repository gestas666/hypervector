# Equal-cap quote and cost feasibility

Hypothesis `v89_equal_cap_quote_feasibility_20260908_v1`.
Research authority only. No signing clients, orders, trade management, live
configuration changes or trading/reporter process lifecycle actions.
Register before acquiring the comparison sample or inspecting its outcomes.

## Decision and scope

The fixed equal-cap historical benchmark increases full-window modeled net but
also raises drawdown and roughly doubles average entry-notional exposure. Its
later full-HIP-3-fee stress loses more than the original allocation. Retain it
as a research candidate, with execution feasibility unresolved. Do not fit
intermediate weights from those outcomes or imply that higher historical net
establishes future edge.

Use the exact seven assets, execution sides, route identities and unchanged
leverage in profile fingerprint
`39e334fc97f3cbe21bac30e53e91524d6a4cf9727370a0f69bc2d51039667f7a`.
Compare original per-route caps with **$7,500 / 7** per route. Five assets
increase from $500; BTC/HYPE decrease from $2,500. This study does not evaluate
or change their signals or stops.

## Source qualification and bounded observation

Inventory existing typed unsigned native Info clients, size-normalization code,
fee evidence and vendor/native book normalization before adding helpers. Verify
current primary venue documentation and the method/schema contract if needed.
Keep wallet/API secrets out of outputs. Mainnet public/unsigned reads only.

Capture current venue size precision and leverage metadata for core and XYZ,
with per-route fee assumptions kept distinct from historically unverified fees.
Requalify the available unsigned fee evidence; missing or contradictory metadata
remains unavailable rather than falling back to a favorable default. Preserve
request/receipt clocks, raw responses, source method and hashes. Endpoint or
asset identity changes require a reported protocol correction before comparison.

Take **36 rounds at ten-second target spacing**, collecting one current L2
snapshot for each of the seven assets per round: at most **252 book requests**.
Use bounded timeouts and retain failed or late rounds; do not extend the sample
to obtain favorable liquidity. If rate-limit documentation requires a slower
schedule, record that technical adjustment before the first round. Snapshots
are not atomic across assets; measure actual sampling intervals and gaps.

For each configured side and both cap assumptions, derive a clearly labeled
probe quantity from the same observed midpoint and current venue size step,
rounding down. This is a public-book capacity probe, not a reconstructed backend
order. Walk the full entry side and hypothetical opposing close side at that
quantity. Keep unavailable midpoint, invalid/crossed books, zero rounded size,
insufficient depth and notional rounding differences explicit. Do not invent
liquidity beyond returned levels or use a signing client to check eligibility.

## Measurements and validation

Report every asset/side/cap cell: usable/missing sample count, notional after
rounding, quantity/step, best spread, full-depth VWAP, consumed levels, visible
capacity, entry/close impact, instantaneous round-trip spread/impact hurdle,
and applicable fee scenarios. Preserve the original 2.5/5.5-bps additional
friction assumptions as separate stress fields; they can overlap book impact.
Fee-weighted profitability forecasts are out of scope. Do not infer historical
execution quality or production latency from current snapshot data.

Offline tests cover route identity, rounded quantities, long/short direction,
missing metadata, depth insufficiency, nonfinite/crossed inputs, costs, response
clocks and input tampering. Verify raw-to-normalized parity and independently
recalculate selected and worst-capacity observations using Decimal. Freeze
source and replay the complete capture without network calls before journaling.
No low-liquidity sample or unfavorable cost is a strategy-performance abort gate.

Success is a complete, qualified comparison showing what the existing book can
support under both declared quantities. Changing metadata, inconsistent raw
normalization, insufficient size or independent arithmetic disagreement updates
the corresponding feasibility claim. Even uniformly sufficient samples do not
establish queue priority, actual fills, stop protection or durable returns.

## Prospective and approval boundary

Do not read or reconstruct outcomes from the sealed September 8–22 SNDK/Brent
experiment. Current quote-capacity measurements contain no strategy replay or
performance score. A later prospective allocation test must have its own frozen
contract and observation boundary and must preserve the existing seal.

After qualification, prepare a concrete inactive allocation/prospective proposal
with the measured trade-offs, remaining tests and rollback conditions. Do not
deploy, resize, arm, start trading or request live approval before that proposal
is complete and reviewable. A failed capacity or source check is a recorded
finding, not permission to alter caps or quietly replace the benchmark.
