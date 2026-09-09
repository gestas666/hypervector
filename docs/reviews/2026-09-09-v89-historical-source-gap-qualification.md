# Historical source gaps: retained evidence qualification

The bounded retained-source search does not recover executable prices for the
missing core minutes. It qualifies their provenance and timing without modifying
the original provider grids or evaluating account outcomes. Confidence is high in
the authenticated counts and low in any inference about exact venue trading,
stop behavior or financial impact. Research source is `24c8ad14fe7593ebadce692fc60b0b2e46d1ca2e`.

Both first/latest grids retain 76 missing asset-minutes during the complete
July 21–September 7 account window: BTC 18, ETH 20, SOL 19 and HYPE 19.
The nominal July 7–21 warmup adds 21 missing asset-minutes: 5, 5, 6 and 5.
These are per-asset counts; simultaneous gaps are counted separately.

Recorded telemetry covers 41 of the 76 account-window gaps: BTC 10, ETH 11,
SOL 9 and HYPE 11. All 53 underlying observations have zero volume and equal
open/high/low/close. Their prices, timestamps, observation times, run identities
and source paths reconcile exactly to six raw recorded candle events. Raw event
bars omit a source label, so their origin as native empty candles versus locally
constructed continuity values remains unproven. Neither interpretation establishes
a traded execution price or continuous stop path. No warmup gaps have recorded
observations in this retained export.

Four frozen annual caches contain all 21 missing warmup rows and the 12 July 25
account rows. Every one is explicitly `hl_gap_fill`. They are modeled continuity
values and cannot be promoted to recovered trades. The caches end July 27;
their absence at later timestamps is not evidence that no other source exists.

Official scheduled-maintenance records overlap 71 account-window gaps; another
three are the minute immediately before the September 5 scheduled start.
Twenty warmup gaps also overlap scheduled windows. These windows are approximate
and their endpoints do not prove the exact interruption or resumption of trading.
Sources: [official maintenance archive](https://hyperliquid.statuspage.io/api/v2/scheduled-maintenances.json),
[August 29 record](https://hyperliquid.statuspage.io/incidents/wxjhfbmhdyvh),
[September 5 record](https://hyperliquid.statuspage.io/incidents/29c2sm6hbxjk).
The raw status response and acquisition receipt are retained by hash.

The unmatched intervals are SOL July 12 10:32 UTC in warmup and August 1
13:55/16:47 UTC in the account window. The July 12 cache row is a gap fill;
the two August 1 intervals have neither recorded observations nor annual-cache
coverage in the sources inspected here.

An independent DuckDB implementation reconstructs all 97 missing intervals from
both original grids and reconciles all 53 observations directly to raw event JSON.
Independent datetime comparisons agree on each maintenance association. Four
deliberately altered count, execution-price assertion, price and provenance
records are rejected. Both final report artifacts reproduce byte-for-byte from
the authenticated source archive; all 5,447 archived Git blobs and modes verify.
The two offline analysis scripts pass Ruff and checked file/function/indentation
and annotation limits. No trading business logic was changed.

Initial verifier attempts exposed a reserved SQL alias and local-time formatting;
the final verifier sets UTC explicitly. A later probe refactor passed a scalar to
an existing mapping-based integer validator; correcting the call restores exact
output. Failed logs remain separate from successful final and archived runs.

Accept this source qualification. Do not insert these rows into frozen provider
inputs or treat maintenance windows as observed execution. Continue the complete
[historical account plan](../plans/2026-09-09-v89-historical-account-source-gaps.md):
first inspect retained native/vendor evidence for the two unmatched August 1 SOL
minutes and the remaining intervals, then specify explicit gap-bearing market
availability for the dynamic account. Preserve all 48 days and every original
source/cost/clock/allocation axis. Exact no-trade/price evidence could update this
assessment; changed hashes, missing rows, failed raw reconciliation or archive
differences would falsify the affected findings. Both prospective outcome seals
remain intact, and no profitable live change is established.

Evidence: [journal revision 1](../research-journal/v89-historical-source-gaps-20260909-v1.json).
