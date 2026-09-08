# Causal source receipt qualification

A separate research receipt tape now preserves the source values actually known
at an explicit timestamp. The source is
`4842a0009a67875fe1f89f729a00bd394cfb979d`, isolated from live deployment and the
running public collectors. The complete prospective strategy replay remains
unqualified and future profitability remains unproven.

The collector's first/last-per-value observation summary is insufficient for
arbitrary intermediate timestamps. A synthetic A/B/A/B/A history and an
A/B/B/B/A history produced identical observation summaries but different middle
values. This does not mean raw evidence was lost: every raw response is retained.
The new tape reconstructs individual receipts from those authenticated responses
instead of trying to recover intermediate states from the summary.

The builder binds the captured manifest and SQLite bytes, verifies each request
and response identity, retains failed/partial requests, and publishes a separate
immutable database. The reader authenticates a private read-only copy. First and
latest queries filter actual receipt and native availability timestamps before
selecting a version. Reversions and equal-clock filename ordering are preserved.
Funding's native settlement offset remains separate from its hour identity.
Metadata retains its actual receipt; publication lag is not inferred.

On the previously pinned public-source qualification snapshot, 30,742 individual
observations generated 122,968 before/at-receipt queries. An independent raw-history
auditor matched every selected hash, identity and timestamp, including 22,858
correctly unavailable answers. The query artifact contains source identities and
hashes rather than prices, signals, positions, returns or equity curves. The
source snapshot's latest request was September 8 at 20:03:06.510 UTC; this is a
fixed source qualification, not a current live trading performance report.

The targeted tests cover repeated revisions, exact receipt boundaries, late and
unfinished data, funding offsets, metadata changes, failed/partial requests,
source and tape tampering, source directory escapes, damaged value caches,
read-only source preservation, immutable publication and exhaustive independent
query checks. The archived source passed all 204 targeted tests, including 54 new
tests. The three receipt modules and two qualification/audit scripts covered all
385 statements and 108 branches. The archived tape database, manifest, 122,968
query answers, summary and independent audit reproduced byte for byte. This
coverage qualifies the exercised component scope, not complete strategy replay.

The archive has 5,230 verified Git blobs and is 29,606,810 bytes, with SHA256
`52b703026d0bccca9ca22c432c8cd140683afdd9854e2cebcaf4e859498f3a75`.
Validation uses Python 3.13.13 and SQLite 3.53.3. Other runtime environments and
full fourteen-day replay throughput are not qualified by this snapshot.

Confidence is high for authenticated receipt reconstruction and point-in-time
selection on this tested scope. A changed source identity, a future receipt in
an earlier query, an omitted intermediate revision or an independent mismatch
invalidates that claim. Late observations remain retained; a returned observation
is not a claim that it met the study's 60-second data threshold or the stricter
30/60-second route entry deadlines.

Remaining work is to assemble the complete historical warmup and captured bridge,
validate full candle/funding grids and metadata size/leverage semantics, bind
source views to the frozen providers and 24 replay cells, and qualify the mapping
between receipt availability, entry eligibility and modeled bar-price execution.
The reader does not convert a modeled bar price into an attainable fill. Provider,
regime, exit-trigger and full prospective account integration remain separate
acceptance requirements. Both study outcome seals and the economic protocol are
unchanged; this component calculates no strategy outcomes.

At 23:09 UTC both public collectors were alive. All fifteen pinned collector
source hashes and the active live profile hash were unchanged. The retained
health snapshot showed 973 valid requests, zero failed/invalid requests and zero
deferred queries. This is a timestamped health observation, not an assurance of
future service. No live strategy, TUI, allocation, signing client, order or trading
process changed during this work.

Evidence: `data/logs/research/bidirectional_cohort/v89_causal_source_receipts_20260908_v1/`.
