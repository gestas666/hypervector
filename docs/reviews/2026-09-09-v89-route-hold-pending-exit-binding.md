# Accepted-position holds and pending exits: bounded synthetic qualification

Source `b32374dc10f59165369e5455e23da26f15a9f380` binds accepted incremental
positions to their configured provider, original costs, entry geometry and
holding clocks. The combined suite passes 375 tests in the isolated worktree
and from its complete source archive. All 24 complete synthetic HYPE reports
match the preserved pre-extraction implementation exactly, and the archived
report reproduces byte for byte.

Confidence is high for this tested policy/ordering scope. Full portfolio
orchestration, source-bound execution timing, dynamic liquidation and future
profitability remain unqualified. No real prospective signals, positions,
cash flows or returns were read or calculated. No live implementation, profile,
order, trading process, TUI or collector source changed.

## Behavior and source fidelity

The lifecycle binding requires an accepted incremental account position with
matching strategy, symbol, configured side, entry price and barriers. Its typed
execution parameters must match the entire retained original source payload,
including JSON numeric/boolean types. Shared leverage and provider/model holding
contracts must agree. Unsupported nonfrozen exit/position policies fail explicitly.

Source-bar time, modeled opening time, bar completion and knowledge time remain
separate. Shared wall-clock holds preserve observed opening offsets and the exact
greater-than-or-equal deadline. HYPE preserves inclusive completed-minute counts:
no hold exit before 480 minutes, conditional support through minute 1439, and
the hard exit at minute 1440. The existing HYPE helper and weighted assessment
were extracted for reuse without changing the legacy wrapper's valid behavior.

HYPE support requires its original structural direction and 1m/5m/15m fields
when an extension decision actually needs them. Missing context is explicit
unavailability. Its configured 60-second evidence-age boundary is inclusive;
older context fails as stale. Neither a pre-soft-boundary decision nor an already
due hard exit needs a regime query. The age check is a synthetic binding control,
not a claim about actual historical receipt latency.

Provider recipe-ignore/honor behavior is preserved. An opposite HYPE signal can
close an authorized long even when a new short entry is outside configured scope
or past the entry freshness deadline. Pending exits retain their cost source,
trade identity, side, decision bar, decision/knowledge timestamps and immutable
decision evidence. Opening validation rejects mismatched identities, off-grid
or same-bar execution, future knowledge, unsupported reasons and reasons that
cannot be reproduced from the original saved decision evidence.

HYPE's opening protective stop precedes its queued ordinary exit. Shared queued
exits and wall-clock expiry precede that model's subsequent intrabar barrier
checks. Proposed opening exits use the existing cost class once and can be
committed through the account's atomic batch. A hard-exit decision at the final
study boundary stays pending while the account marks its remaining open exposure;
the policy layer does not import the legacy forced terminal close.

## Verification and corrections

The 122 lifecycle/hold/legacy regression tests combine with the prior 253
cost/barrier tests. The two new business modules have complete unit coverage:
207/207 statements and 94/94 branches. Including the modified legacy HYPE replay
gives 436/444 statements and 168/176 branches; eight untouched legacy paths remain
uncovered. The qualification driver's source/I/O guards are exercised by actual
synthetic runs, not included in that unit-coverage claim.

The complete-report comparison covers all three frozen HYPE cost records, both
arithmetic directions and four artificial scenarios: supported extension to the
hard deadline, loss of support at the soft deadline, opposite intent, and a
protective-stop opening gap competing with a queued exit. Each input has 1,444
minute bars in 2030 and explicit synthetic hourly funding. Every resulting report
field matches the preserved original, with no numeric tolerance. These are 24
synthetic regression scenarios, not market opportunities or independent trials.

Fault tests exposed prototype omissions in pending-bar alignment, saved-evidence
validation, desired-side validation on revalidation, and typed-cost/source
consistency. Each initial failure is retained alongside its passing regression.
The first driver also needed structural refactoring and explicit original-source
and catalog authentication. Its 24 case results agree exactly with the hardened
driver. Two nested fixture docstrings were added during structural verification.

All eight changed/new source and test files pass Ruff, formatting, annotations,
public docstrings and size/indentation limits. All 5,309 Git blobs in the archive
match their committed identities. Archive SHA256:
`80d09758acf944d2cc36616ea48604a63b7c3a73e34364d802d3d06a4bd32cd1`.
The 40,442-byte synthetic report has SHA256
`20450b1dee65e7b5a5e9df2ac3c93a6cd4d0960a9a22e96609986663b16a9df3`.

At September 9 04:03:54 UTC both public collectors were alive; all fifteen pinned
collector sources and the live profile hash were unchanged. All 2,360 prior
evidence files, totaling 895,195,727 bytes, were reverified. This source-health
observation is not a current venue account reconciliation.

## Remaining work and falsification

The caller still owns chronological bar delivery, pending-state persistence,
source/provider provenance, accepted position refresh after funding, intrabar
events and account-batch commitment. Passing these functions does not prove
that a complete evaluator cannot drop or reorder an event. Native cadence is
checked per supplied bar, but this layer is not a complete source-grid reader.

Next bind funding-adjusted liquidation to accepted rounded positions and qualify
both frozen intrabar clock variants. Then connect source metadata and the full
chronological portfolio loop, including all 24 registered account cells. HYPE's
frozen historical model still has no liquidation trigger; no shared trigger was
silently introduced. Any proposed economic-model change needs a separate decision.

A changed legacy trace, shifted deadline, missing or forged pending decision,
wrong source/position binding, invented regime, double cost, unregistered terminal
close or failed archive reproduction invalidates the affected qualification.
Both prospective outcome seals remain in force.

Evidence: `data/logs/research/bidirectional_cohort/v89_route_lifecycle_binding_20260909_v1/`.
