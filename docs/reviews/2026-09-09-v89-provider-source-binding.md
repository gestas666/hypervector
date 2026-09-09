# Historical provider/source binding and the limits of regime equivalence

The isolated provider adapter at `38e1d6a685e963fb93ed3a1f33b32878d38a7732`
reproduces all 280 previously registered September 6 provider probes exactly,
including complete readiness, entry and exit payloads. An auditor importing no
Hypervector code independently verifies the original control identities, all
4,290,048 repeated historical row selections, the independent clocks and the
five emitted entry intents. These are compatibility checks on already examined
history, not new trades or evidence of profitable performance.

The complete future replay remains unqualified. Native funding/source binding,
full cost and trigger handling, every-minute provider behavior and all 24 account
cells remain outstanding. Both prospective studies' outcomes remain sealed.
No live provider, profile, TUI, collector source or trading process was changed.

## What the adapter preserves

Each source window has a completed-market cutoff T and an independent knowledge
clock K. Its exact fourteen-day grid contains no candle completing after T.
Unknown historical receipt times remain absent. Captured observations require
actual receipts no earlier than completion and no later than K; first/latest
ordering is validated across every selected row. Original continuity-proxy
columns and authenticated file/value identities remain attached to the inputs.

The unchanged provider receives that window and observes K, while its completed
decision and conditional modeled entry timestamp remain T. The adapter enforces
the existing inclusive 30/60-second entry deadlines at K and retains the original
provider evaluations, including exits. First-source timeliness is separate from
entry freshness and from the receipt of a selected later revision. This adapter
produces evidence and intents; it neither creates fills nor submits orders.

The original historical controls use a modeled five-second delay, not observed
historical latency. Full payloads remain exactly equal in every probe. Repeated
row-selection counts are a provenance audit, not independent market samples.
Only five entry intents occur in the fixed probe set, so it does not establish
comprehensive coverage of production signal behavior or future opportunities.
All five are XYZ intents (SPCX one, SNDK three, Brent one), and none carries a
regime score. The core probes contain no entries. The auditor's retained
`annotated_intents` counter counts all five output-intent records, including
unweighted ones; it is not a count of nonnull regime scores. The separate
`historical_intent_scope.json` records this distinction. Entry-weighting
acceptance is synthetic; historical canonical checks compare evaluation payloads.

## Native regime source limitation

The frozen study captures 15-minute XYZ candles. The canonical classifier needs
one-minute source bars to produce its existing 1m/5m/15m states, and the live
configuration includes these hourly XYZ providers in canonical telemetry scope.
No minute history is reconstructed from 15-minute OHLC. The 72 XYZ historical
probes explicitly record unavailable native-minute classification.

The other 208 probes produce exactly the same canonical payloads from the source
adapter and a direct call using the original minute price columns. This verifies
input wiring through the unchanged classifier, not an independent implementation
of its indicators. All 208 core windows contain previously registered
`hl_gap_fill` continuity proxies; a complete minute grid is not complete native
observational history. The adapter preserves that provenance.

Fifty-four synthetic cases cover the three XYZ symbols, both intent directions,
flat/long/short positions and supportive/opposed/unknown regime states. With one
intent per symbol, economic routing fields, execution plans, sizing selection
and the fixed 24-hour holding deadline remain identical. Two counterexamples
bound this finding: competing intents for one symbol can select a different
direction under regime preference, and HYPE's soft-hold extension requires
canonical evidence. Full canonical equivalence remains unqualified; the limited
XYZ result must not be generalized to other routes or queued competing intents.

## Modeled entry and funding clocks

Eight synthetic account cases independently calculate signed funding for long
and short positions at settlement offsets 0, 76, 5,000 and 5,001 milliseconds.
They compare a modeled entry at T with one retimed to receipt T+5,000 ms. The
existing account settles funding before entries sharing the exact timestamp.
With the fixture's 50-unit position, $10 proxy and 1% rate, retiming across the
76-ms or 5,000-ms settlement changes the funding cash flow by $5. These deliberately
synthetic quantities are arithmetic controls, not estimates of venue funding.

Moving modeled entry time to receipt time is therefore an economic change, not
a neutral clock correction. The frozen recorded-bar model remains a conditional
price benchmark; this work supplies no evidence that its earlier bar price was
attainable after data receipt. Binding actual native settlement offsets and the
declared opening-price proxy's separate availability/receipt clocks is next.

## Verification and qualification boundary

All 136 targeted offline tests pass, including 130 new cases and six existing
causal regime-preference checks. The two adapter modules cover all 122 executable
statements and 40 branches. The independent auditor validates exact JSON types,
historical source hashes, retained provenance, full provider diagnostics and
signed regime-weight arithmetic; it does not independently classify indicators.

Initial synthetic fixtures were corrected to provide the readiness indicator
required by the existing type and to use the existing directional contract
selector for HYPE. Fault tests then exposed four adapter validation omissions:
unknown origin, fabricated historical receipt, an earlier selected revision in
a preceding row, and disagreement about whether the first receipt was observed.
The original adapter source and failing test log are retained. All four now fail
explicitly before provider/account use, and valid historical outputs are exact.

The source archive contains 5,273 verified Git blobs. Its SHA256 is
`d463a1441cb8d9770c850cd835f6815bb0833c77c8226646249324d49e46e6c3`.
The immutable source passes all 136 tests, reproduces all twelve result files
byte for byte and produces the identical independent audit. Fresh archive
coverage across the five implementation modules is 428/439 statements and
110/122 branches. Eleven driver/auditor rejection lines remain unexercised;
the two adapter modules and historical-control helper have complete statement
and branch coverage. This is not full provider-library or portfolio coverage.
All twelve new source/test files pass Ruff, formatting, function/file-size,
annotation, public-docstring and indentation checks.

At September 9 01:46:17 UTC both unsigned public collectors were alive; all
fifteen pinned collector files and the active profile hash were unchanged. All
2,193 earlier journal evidence files, totaling 791,001,023 bytes, were reverified.
The accompanying journal revision corrects the obsolete `sealed_before_prospective_window`
status: collection is now inside the fixed window, with outcomes still sealed.

Confidence is high for these pinned, tested compatibility and arithmetic claims.
A source or payload mismatch, invented/missing provenance, future data entering
an earlier decision, altered clocks, a routing counterexample inside the stated
single-intent scope, or failed archive reproduction invalidates the relevant
qualification. Future profitability, attainable fills, full native regime parity
and complete prospective replay remain unverified.

Evidence: `data/logs/research/bidirectional_cohort/v89_provider_source_binding_20260909_v1/`.
