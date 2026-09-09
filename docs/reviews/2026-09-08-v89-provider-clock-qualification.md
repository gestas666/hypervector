# Historical provider clock and history qualification

The fixed 280-probe historical comparison found no changed entry, exit or side
when only the observation clock moved five seconds later. Moving the rolling
history cutoff changed five non-crypto stop anchors, by at most
`1.0802114047692157e-7` price units (`6.024267496342735e-7` bps of reference).
This sample supplies no evidence that this numerical effect caused the reported
live losses. It also does not establish future strategy profitability or exact
equivalence between the two history conventions.

Source: `303bd01b7535ee3757d6ae2dee494080658197cd`, isolated research scripts and
tests. Live providers, the live profile, running collectors and both sealed
economic protocols were not modified.

## Fixed scope and measured results

Before inspecting differences, the plan fixed September 6, 2026: every UTC hour
for all seven assets, plus 11:59 and 12:01 for core assets. The eleven sources
are the already-registered first/last core continuity files and common native
XYZ fifteen-minute files. Every consumed Parquet byte was authenticated against
the previous allocation journal before parsing; files extending past the old
September 7 boundary were refused.

Every probe compares the unmodified production provider on a completed window
ending at T, the same window observed at T+5 seconds, and the window trimmed
using T+5 seconds. The completion cutoff stays at T in all three cases. The
configured fourteen-day history and thirty/sixty-second entry deadlines remain
explicit. These delays are model probes, not measured historical network latency.

| Asset | Timestamp/source probes | Observation-only changes | Full-output changes after history trim | Changed stop anchors |
|---|---:|---:|---:|---:|
| BTC | 52 | 0 | 48 | 0 |
| ETH | 52 | 0 | 27 | 0 |
| SOL | 52 | 0 | 44 | 0 |
| HYPE | 52 | 0 | 24 | 0 |
| SPCX | 24 | 0 | 24 | 1 |
| SNDK | 24 | 0 | 24 | 3 |
| Brent | 24 | 0 | 24 | 1 |
| Total | 280 | 0 | 215 | 5 |

The five changed execution fields are exclusively `intents.0.stop_anchor`.
Other changes are diagnostic/readiness values, including recursive ATR/EMA and
small rolling-statistic differences. Both complete payloads and exact changed
paths are retained; no numerical tolerance hides differences. Price rounding,
private fills and resulting account effects were not inferred from these probes.

No selected grid row was missing from these registered inputs. All 208 core
probes nevertheless contained preexisting `hl_gap_fill` continuity proxies.
That provenance is counted explicitly; complete continuity is not complete
native source evidence. XYZ probes use native fifteen-minute files, not the
live poller's one-minute transport and resampling.

## Validation and limits

An independent auditor with no Hypervector or probe-implementation imports
verified all 280 serialized comparisons, source-grid endpoints/counts, retained
proxy counts, clocks, route identities, direction scope and entry-age summaries.
The actual provider/indicator calculations themselves are not independently
reimplemented by that auditor. The complete fixed report has SHA256
`8249a7f151feb76a0ac6bd5b167236cf613a83c20d13f03f4a60635c0367ee74`.

The 130 targeted tests include malformed and changed sources, future values,
incorrect clocks, duplicate decisions, missing report dimensions, altered route
identity/sides and independent-summary tampering. A new fault fixture exposed
Python integer/float equality as insufficient for serialized equality; the
comparison now preserves numerical representation and signed-zero differences.
The stricter rerun retained the same 280-probe findings. Initial outputs and
pre-correction script copies remain preserved as diagnostic provenance.

The source archive passed the same 130 tests and reproduced all twelve result
files and the independent audit byte for byte. Fresh archive coverage measured
384/387 statements and 129/132 branches. The source reader, clock probes and
independent auditor covered every statement and branch; the publication driver
has three unexercised rejection branches. These are component measurements,
not full provider-library or complete portfolio-replay coverage.
The retained source archive contains 5,242 verified Git blobs, is 29,676,446
bytes and has SHA256
`4c094f732ebb80f5c37d560043ab456255a4c3b8f0d400c08b3588d40ae19bdd`.

Confidence is high in the measured fixed-probe differences, conditional on the
pinned source and Python/dependency environment. A changed source identity,
omitted probe/difference, future input affecting an earlier decision, independent
mismatch or failed archived reproduction invalidates that claim. Other dates,
every-minute parity, different history lengths, native transport, actual receipt
eligibility and complete account/funding/exit behavior remain unqualified.

## Next investigation and unchanged economics

Assemble the complete authenticated historical warmup and captured bridge into
the provider input view, preserving separate completed-market and actual-knowledge
clocks. Bind receipt eligibility and metadata to the frozen modeled bar clock
without silently moving entries or funding. The existing generic receipt reader
does not establish that mapping. The already-qualified legacy account controls
remain separate from full signal/source/account reproduction.

Do not add more historical probes merely to turn these exact mismatches into a
pass. Their magnitude and scope are now measured. Any proposed interpretation
that changes registered economics must be explicit before it is used. The old
daily extractor in this worktree also predates the previously verified 9feb625
gap repair; reuse that repair if introducing batched extraction, rather than
allowing a later gap to erase an earlier provider decision.

At September 9 00:02 UTC, both public collectors were alive. The new collector
was in its collecting phase with 1,206 valid requests, zero failed/invalid
requests and zero deferred queries. All fifteen collector source hashes and
the live profile hash were unchanged. This is timestamped health evidence,
not a performance result or future availability guarantee. Neither study's
strategy outcomes were read, and no trading process or TUI was changed.

Evidence: `data/logs/research/bidirectional_cohort/v89_provider_clock_qualification_20260908_v1/`.
