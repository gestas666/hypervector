# V33 SPCX Swing route-retirement review

## Decision under test

V33 is an inactive exact-delta candidate derived from inactive v32. Its only
semantic change is moving
`hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SPCX` from executable to
observe-only. SPCX remains visible in both directions, its breakout-pressure
route remains executable, SP500 Swing remains executable, and every unrelated
asset, provider, side, priority, risk, sizing, stop, target, hold, margin,
capacity, ledger, and polling field remains identical.

## Evidence

The earlier exact SPCX study evaluated 317 source trades across provider,
alignment-onset, next-bar-confirmation, and fast-EMA-pullback clocks; long and
short; development and validation; and nominal and stressed friction. Zero of
eight side/timing arms stayed nonempty, net-positive, PF above one, and
positive after removing the largest winner in every required cell. Provider
long reversed from positive development to negative validation, while provider
short reversed from negative development to positive validation but failed
largest-winner removal.

Fresh live v25 evidence is consistent with that instability rather than an
independent rescue. SPCX Swing has three completed long trades: one winner and
two losses, +$0.305183 net, PF 1.241725, and −$1.262519 after excluding its
single winner. The live sample is descriptive and too small to establish the
route's expectation; it is used only as corroboration of the larger frozen
study. SPCX is flat in the 2026-08-09 23:05 UTC checkpoint. BTC, HYPE, GOLD,
and BRENTOIL remain open and venue-stop protected, so no portfolio-wide flat
transition boundary currently exists.

SOL HT-Breakout is intentionally untouched. Its current three long closes are
+$1.727925 net, PF 3.532248, and +$0.145048 after excluding its largest winner.
Those numbers remain sparse, but they contradict removing or weakening that
route in this candidate.

## Exact candidate contract

The parsed v32-to-v33 diff contains one route-authority change. V33 retains
nine assets, nine providers, nine-position capacity, isolated margin, both-side
observation, 20 executable provider-symbol routes, and four observe-only
routes. It has no automatic promotion or transition authority and has not been
loaded by the live engine.

## Risks, confidence, and falsifiers

Confidence is medium that the exact SPCX Swing route should be retired from
execution. The frozen 317-trade study and the small live sample agree, but the
historical partitions are opened and live observations cover only three longs.
Removing the route can also expose a later SPCX provider opportunity through
the shared router; that portfolio interaction has not yet been observed under
v33.

Reject the technical candidate if any parsed difference beyond SPCX Swing
execution authority appears, if either SPCX observation side disappears, if
SP500 Swing or SPCX breakout authority changes, or if evidence hashes drift.
Revise the economic decision if preregistered independent SPCX Swing evidence
survives both sides, observed costs, validation, largest-winner removal, and
shared-router interaction. V33 must remain inactive until a new exact
transition contract, flat/order-free drain, backup, explicit live-risk
authorization, and candidate-specific post-start acceptance exist.
