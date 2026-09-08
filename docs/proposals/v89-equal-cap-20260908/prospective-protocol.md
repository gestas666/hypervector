# Frozen prospective allocation comparison

Study `v89_equal_cap_prospective_20260909_v1`. Research execution authority only.
This document freezes the economic comparison before its observation window.
The source collector and replay implementation are not yet qualified or running.
Do not describe planned collection as observed evidence.

## Window, seal and comparison

The exclusive interval is **2026-09-09 00:00:00 UTC through
2026-09-23 00:00:00 UTC**. Do not move its start, extend its end or choose a
favorable subwindow after seeing data. Missing early or later source observations
remain technical deficiencies. Retain the fixed interval even if implementation
or collection is delayed. Qualification failure is a reported result.

Do not calculate or inspect strategy outcomes from this new interval before its
end. Source health, hashes, counts, timestamps, missing intervals and revisions
may be inspected without signals, positions, trades, returns or equity curves.
Keep the separate September 8 04:00–September 22 04:00 SNDK/Brent experiment
sealed on its original terms. This comparison overlaps its market environment;
it is not an independent replication of that experiment or permission to reuse
its early outcomes. Data collection alone does not unseal either study.

Compare only `control.toml` and `equal.toml` in this directory, whose complete
typed comparison is in `comparison.json`. Original controls use the current
allocation; the challenger uses the previously tested equal caps and margin
fractions. Signals, directions, routes, stops, targets, leverage and timing
contracts are held fixed. Do not fit intermediate weights, add session filters,
change stops, or select individual assets after observing this interval.

Both hypothetical accounts start flat with **$4,857.58724349**. This is the
registered benchmark's reference capital, not a claim about current real funds.
Each account uses its own evolving equity, rounded quantities, reservations,
costs and explicit available-margin constraints. Do not obtain candidate PnL
merely by multiplying already realized control PnL. Record differences in
accepted opportunities if shared cash constraints cause them.

## Causal sources and implementation qualification

Collect core BTC/ETH/SOL/HYPE one-minute candles, XYZ SPCX/SNDK/Brent
fifteen-minute candles, hourly funding and current core/XYZ size/leverage
metadata through unsigned mainnet Info reads. Preserve raw bytes, request and
receipt timestamps, native event identities, HTTP/transport failures, first
observations and every distinct later revision. No signer or order client.
No writes to live execution paths or the existing sealed collector.

Warmup is the fourteen days preceding the fixed start, assembled from registered
historical data and independently acquired missing intervals. Distinguish late
bootstrap receipt from timely prospective availability. Validate the complete
unique candle/funding grid, source units and schema; do not impute missing prices
or zero funding. A missing funding observation is not a zero settlement.

Prospective first receipts are timely when retained within **60 seconds of the
candle close or funding settlement**. The stricter configured route entry
deadline still applies to entry eligibility; a timely data observation alone
does not prove an eligible entry. Preserve first and latest revisions separately.
First-receipt data is the primary causal input; latest revisions provide a
declared sensitivity only and cannot replace an unfavorable first result.

The collector must demonstrate offline scheduling, unsigned-method restrictions,
bounded retry/failure retention, clock handling, restart preservation, raw/index
parity, and at least one actual scheduled receipt before being described as
qualified. Bound requests and disk use from measured source sizes; retain
failures rather than adding favorable replacement samples. Technical changes to
collection require a dated revision before use and cannot change economics.

Before outcome computation, pin the exact replay source and validate its date
parameterization on previously registered historical controls. Require equality
with original controls, meaningful fault tests and independent accounting.
Runtime strategy providers and configured directions must match both inactive
files; the canonical regime remains conflict preference, not a standalone
confidence gate. Preserve the existing 5m primary, 1m confirmation and 15m
context classifier and unavailable-regime handling.

## Economic assumptions and outputs

Use the frozen original-exit lifecycle contract; do not transfer the retrospective
single-SNDK-event sampled-stop replacement into future exits. Preserve the
original conservative intrabar ordering assumptions and explicitly label
candle-based execution prices and liquidation/stop ordering as modeled, not
private fills or continuous native protection. Size steps come from available
venue metadata; rounding down must flow through fees, funding and reserved
margin. Current six-minute quote capacity does not prove future fills.

Retain the historical model's three fixed cost cases: nominal with 2.5 bps
additional friction per ordinary side; adverse with 5.5 bps; and the same
adverse friction with full HIP-3 fees. Core ordinary taker fees remain 4.5 bps
per side; XYZ fees are 0.9 bps in nominal/adverse and 9 bps in full-fee stress.
These are explicit model assumptions, not assertions about future charged fees.
Retain each route's existing special exit/liquidation cost treatment, documented
in `cost-contracts.json` with its three original source hashes. Apply actual observed funding rates at their
settlement clocks with signed position exposure and the declared price proxy.

Report both first/latest sources, all three costs, both original recorded-bar
and late-intrabar exit clocks, and both allocations: **24 cells / 12 paired
comparisons**. The primary comparison is **first receipts, adverse cost,
recorded-bar clock**. Do not pick another primary after outcomes appear. Do not
mix modeled bar clocks with claims of achievable receipt-time fills.

For each case retain every eligible/missed/rejected opportunity, lifecycle,
rounded quantity, fee, funding settlement, reservation and marked equity point.
Report total marked equity change, realized/unrealized components, dollar and
percentage drawdown, minimum available cash, gross exposure, average deployed
entry notional/initial margin, trade counts, holding time and asset/route/side
contributions. Open positions at the terminal boundary remain explicitly marked;
do not invent an actual forced close. Describe liquidation losses and unresolved
execution/source assumptions separately.

Retain all fourteen UTC daily contributions and the predeclared first-seven /
last-seven-day split. Report paired net and drawdown changes, exposure changes,
fee/funding attribution and concentration. The short correlated sample does
not support a claim of durable edge or a precise future win probability. Zero
or few trades remain reported evidence, not a reason to extend or retune.

Success means a technically qualified, fully reconciled comparison that answers
whether the allocation's observed return change warrants its exposure/drawdown
trade-off in this new interval. Adverse performance is not an implicit abort
gate; positive performance is not automatic deployment approval. Hash changes,
noncausal inputs, missing essential source coverage, account arithmetic mismatch
or failed independent/archive replay weaken or invalidate the corresponding
claim. Publish the complete result and explicit limitations regardless of sign.

Live strategy, allocation or deployment changes remain a separate human decision
under the active mandate. This protocol authorizes no real-money execution.
