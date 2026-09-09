# Frozen route costs and entry barriers: independently reproduced synthetic controls

The isolated research implementation at
`fd8c0eb832a98b155c77542fbd31fe799e2d6c51` preserves all 21 registered execution
contracts and binds their prices, fees and entry barriers to the incremental
accounting components. All 253 focused offline tests pass in the worktree and
from the full source archive. The synthetic catalog report and independent audit
reproduce byte for byte.

Confidence is high for the tested price, geometry and synthetic cash arithmetic.
This does not qualify complete route lifecycles, actual venue fills, the full
portfolio evaluator or future profitability. No prospective strategy outcomes
were read or calculated. No live implementation, profile, order, trading process,
TUI or collector source changed.

## What is preserved and verified

The binder requires the complete original execution field set and exact primitive
types before constructing the existing shared or HYPE model. Missing fields,
unknown fields, booleans in numeric fields, invalid prices and unsupported exit
reasons fail explicitly. Original allocation parameters remain retained metadata;
they do not determine the future account's dynamic sizing.

The catalog uses artificial entry/exit prices of 100 and 110. Seven assets,
three cost assumptions and both arithmetic directions produce 42 cases and
198 entry/exit quotes. Testing both directions does not expand configured route
eligibility. Ordinary, target and liquidation fee/slippage classes remain distinct;
the shared liquidation class retains its registered zero slippage.

An independent auditor imports no Hypervector implementation. It authenticates
the fixed preregistration, all six economic files and three original cost-source
identities, then recalculates quotes and entry geometry with 50-digit Decimal
arithmetic. Every original execution value and type must match exactly. Only
computed prices permit an absolute 1e-12 tolerance, with no relative tolerance.
The largest observed residual is 1.4210854715202004e-14. All 1,379 implementation
file identities recorded by the catalog also match.

The barrier component reuses existing fixed stops, XYZ structural stops and
20–250 bps clamps. Tests cover missing anchors, entry gaps that invalidate a
stop, simultaneous touches, liquidation/stop/target precedence and adverse
opening gaps. HYPE retains its protective-stop model. Its frozen historical
simulator has no liquidation trigger; the adapter reports that missing model
and rejects an invented shared liquidation boundary. This is a historical
simulation limitation, not a diagnosis of absent live protection.

Eighteen synthetic account cases cover BTC, HYPE and SPCX, all three cost
assumptions and both sides. They independently reconcile rounded quantities,
entry/exit fees, signed price PnL and signed funding to final cash. Synthetic
entry marks are explicit. Their artificial sizing is an arithmetic control,
not evidence of configured route leverage or allocation behavior. Additional
fixtures distinguish all fee/slippage categories and preserve explicit zero costs.

## Verification and preserved failures

Both new adapter modules have complete unit coverage: 167/167 executable
statements and 62/62 branches. Across the adapters and two drivers, unit tests
cover 285/350 statements and 78/90 branches. Adding authenticated metadata-only
driver runs covers 348/350 statements and 88/90 branches; two qualification-driver
rejection paths remain unexercised. The independent driver's complete combined
coverage is not a unit-only coverage claim.

The expected missing-module failures preceded implementation. Two early barrier
assertions required an explicit absolute tolerance for inherited floating-point
reconstruction. Eighteen account fixtures initially omitted the account's required
contemporaneous mark; the fixtures were corrected without changing account logic.
One coverage invocation mistakenly supplied filenames as module names and
collected no data. The corrected include-based run passes all 253 tests and
records the coverage above. These failed attempts remain in the evidence directory.

Ten source/test files pass Ruff, formatting, file/function size limits, annotation,
public-docstring and indentation checks. All 5,299 Git blobs in the full archive
match their committed identities. Archive SHA256:
`f77d77b140cc58a55334192d8a2b570516f185b74041b9b19cb7b763525c1c14`.
The 368,012-byte report and 745-byte audit reproduce exactly from archived code.

At September 9 03:30:41 UTC both public collectors were alive. All fifteen pinned
collector source files and the live profile hash were unchanged. All 2,306 prior
journal evidence files, totaling 862,491,125 bytes, were reverified. This is a
bounded source-health check, not a venue account reconciliation.

## Remaining work and falsification

Next integrate causal pending exits, maximum holding periods, HYPE regime
extensions and hard deadlines. Then qualify source/decision/execution clocks,
funding-adjusted liquidation boundaries, rounded positions, metadata semantics
and all 24 account cells. The HYPE liquidation limitation must remain explicit;
changing that frozen economic model requires a separate decision.

Any changed source, missing cost field, altered type, double slippage, wrong fee
class, independent arithmetic mismatch, invented trigger, omitted probe or failed
archive reproduction invalidates the affected qualification. Full lifecycle and
economic conclusions require their own completed validation. Both prospective
outcome seals remain in force.

Evidence: `data/logs/research/bidirectional_cohort/v89_route_execution_binding_20260909_v1/`.
