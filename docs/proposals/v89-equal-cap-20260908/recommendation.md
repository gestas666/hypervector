# Inactive equal-cap allocation proposal

**Recommendation:** retain the exact equal-cap candidate for the frozen
prospective comparison. The files are concrete and semantically qualified;
the collector/replay acceptance and future results remain outstanding.
Live sizing is not proposed for immediate deployment on the present evidence.

| Asset | Original cap | Candidate cap | Original margin fraction | Candidate margin fraction | Leverage |
|---|---:|---:|---:|---:|---:|
| BTC | $2,500 | $1,071.428571 | 0.05 | 0.0214285714 | 20 |
| ETH | $500 | $1,071.428571 | 0.02 | 0.0428571429 | 15 |
| SOL | $500 | $1,071.428571 | 0.02 | 0.0428571429 | 15 |
| HYPE | $2,500 | $1,071.428571 | 0.08 | 0.0342857143 | 10 |
| SPCX | $500 | $1,071.428571 | 0.02 | 0.0428571429 | 10 |
| SNDK | $500 | $1,071.428571 | 0.02 | 0.0428571429 | 10 |
| Brent | $500 | $1,071.428571 | 0.02 | 0.0428571429 | 10 |

Exact floating values are in `equal.toml`, including the four existing provider
sizing overrides. Summed caps remain $7,500; potential initial margin changes
from $591.666667 to $625. Cap-binding equity thresholds are preserved. The two
files use separate research identities and ledger/stop paths, load in observe
mode without live flags, and do not copy the old transition approval.

| Proposal requirement | Evidence, decision and boundary |
|---|---|
| Why now / observed opportunity | The fixed historical benchmark exposed a concentration trade-off, and current quote probes qualified both quantities. An exact forward comparison can now be specified without fitting new weights. |
| Evidence reviewed | Registered 48-day equal-cap accounting, chronological attribution, current 252-book / 720-probe capacity study, fresh fee/size/leverage metadata, and the full inactive configuration semantic comparison. |
| Applicable market regime | The unchanged routes' configured conditions and existing canonical regime interpretation. There is no validated new regime filter or claim that recent weakness is caused by regime shift. |
| Proposed live change, if separately approved later | Only the listed asset/provider sizing values plus a separately reviewed profile transition. No route, side, stop, target or leverage change is part of this allocation. A live transition requires fresh venue state and its own exact authorization; these research files contain none. |
| Observed upside, not a forecast | In the explored first-source/adverse/original-exit history, net changes $96.12 → $369.09. All 36 historical allocation comparisons improve full-window net. This does not estimate future returns or win probability. |
| Main risks and failure modes | Dollar drawdown rises $198.69 → $288.19 in that comparison; average entry-notional exposure rises $871.82 → $1,763.33 despite equal summed caps. Later adverse net remains negative (−$52.43); later full-fee stress worsens −$137.28 → −$159.23. Larger non-crypto exposure increases dependence on SNDK and longer holds. Current depth can change, fees can change, and candle execution assumptions can fail. |
| Validation completed | Historical controls/accounting and archived replay; all current quantity probes complete; exact typed and independent raw-TOML parity for both inactive files; independent cap-budget and cap-binding-equity arithmetic; staged serializer regression qualification. |
| Validation still required | Qualify prospective collection and replay without reading either seal early; complete the fixed September 9–23 comparison; assess source gaps and all 24 cells; independently reconcile and archive results. Any later live proposal also needs current execution/TUI acceptance and fresh account/venue state. |
| Success measurements | Paired marked net, dollar/percentage drawdown, exposure and margin occupancy, fee/funding contribution, route concentration, opportunity count and first-seven/last-seven-day behavior. Performance remains a measured trade-off, not automatic approval or an implicit trial abort rule. |
| Failure / rollback | Invalid source, arithmetic or configuration parity prevents a technical qualification claim. Unfavorable performance stays in the report. These artifacts are inactive, so rollback is withdrawal of the proposal; any later live transition needs its own state-aware rollback that preserves open-position management. |
| Confidence | High in configuration/accounting and this captured quote sample; low in future edge, durable liquidity or actual hypothetical fills. Changed hashes, failed parity, changed metadata/depth or the future paired result would update the recommendation. |
| Explicit approval requested | None for already authorized research or these inactive artifacts. No live allocation/deployment approval is requested at this stage. The independently reviewable staging-code correction has a separate technical deployment proposal. |

| Alternative | Evidence and trade-off |
|---|---|
| Keep original allocation | Preserves the current contract and lower modeled exposure/drawdown; retains the observed concentration and later weakness. It remains the paired control. |
| Fixed equal caps | Improves explored full-window net while increasing exposure/drawdown; current sample depth supports it. Requires prospective evidence before a stronger growth claim. |
| Fit intermediate weights now | Would add outcome-selected variants on repeatedly explored history. Deferred; no new evidence currently justifies that search. |

See `prospective-protocol.md` for the frozen observation boundary and
`comparison.json` for exact fingerprints and file hashes. This proposal is not a
running paper study, a live profile transition, or a forecast of profitability.
