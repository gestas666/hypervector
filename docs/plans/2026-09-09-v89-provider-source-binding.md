# Bind source windows to unchanged providers and modeled clocks

Continue the frozen allocation replay qualification after source assembly
`478b284` and journal revision 8. No September 9–23 or September 8–22 strategy
outcomes may be computed. Use synthetic cases and the already registered
historical September 6 provider probes. Do not change a live provider, profile,
collector, order client or deployment.

The adapter must consume an authenticated source window with separate completed
market time T and knowledge time K. Preserve the original provider timestamp T;
feed no candle completing after T even when K is later. Validate identity, exact
requested history/grid, source availability and ordering before calling the
unchanged factory collector. Preserve complete provider evaluations and exits.
Use the existing inclusive 30/60-second entry-age filter with K. Keep first-source
timeliness separate from the selected revision and from entry freshness. The
historical probes have modeled knowledge delays, not observed receipt timing.
Do not fabricate a first receipt for historical rows.

Preserve canonical 1m/5m/15m classification on native minute inputs using the
unchanged telemetry collector and existing conflict-preference attachment.
Inspection found a material source limitation: this study's XYZ capture is 15m,
but `configured_canonical_regime_symbols` includes its hourly XYZ routes and the
canonical collector consumes 1m bars. Do not upsample OHLC into invented minute
history. Record native canonical input as unavailable for those routes, and
prove with synthetic routing/position cases what that absence can and cannot
change. The fixed configuration has one provider per symbol, noncrypto fixed
holding policies and sizing without a regime multiplier. That suggests limited
economic impact for a single eligible intent, but it is a hypothesis requiring
tests; it does not establish classified regime parity. Multiple competing
intents remain a distinct case where regime preference can matter.

Recorded-bar execution is a conditional price benchmark, explicitly distinguished
in the protocol from an attainable receipt-time fill. This adapter must not
substitute K for an entry timestamp T. Native funding has a separate settlement
clock S and a declared settlement-hour opening-price proxy. Preserve S and
the source/price-proxy knowledge clocks; do not round S down to the hour or
silently reinterpret a modeled settlement as a contemporaneously observed fill.
Demonstrate with the incremental account that moving entry T to K can change
funding and holding-time economics. Such a change is not a technical clock fix.

Validation requires malformed/future/missing inputs to fail before provider use,
complete provider-output parity with the previously pinned historical probe
outputs, synthetic stale entries with retained exit evaluations, canonical
future-evaluation exclusion, explicit unavailable XYZ canonical inputs, and
independent clock/funding arithmetic. Keep full first/latest payloads and exact
hashes; differences are evidence, not an invitation to retune. Archive/reproduce
the qualified source and journal both accepted contracts and unresolved limits.

High confidence is conditional on authenticated source identity, unchanged
provider output, exact clock/side routing and independent accounting agreement.
Any source leak, changed provider output, hidden regime substitution, altered
modeled entry/funding clock or inconsistent archive replay invalidates the
affected component. Full cost/trigger/account orchestration, all 24 cell bindings
and future native regime/transport equivalence remain separate requirements.
