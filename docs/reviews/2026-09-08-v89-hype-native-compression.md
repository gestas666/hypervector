# Native HYPE compression inputs match the frozen live publications

Native minute candles independently reproduce the finite HYPE compression and
candle-body inputs in all **907 evaluations** through **2026-09-08
10:40:18.410578 UTC**. No comparison exceeds the predeclared absolute tolerance
of 1e-9. High confidence in this bounded arithmetic finding; it does not establish
strategy profitability or independent correctness of the regime classifier.

This completes the input follow-up from the
[core inactivity audit](2026-09-08-v89-core-opportunity-attribution.md).
The run is `bidirectional-live-1788809099824`, profile fingerprint
`39e334fc97f3cbe21bac30e53e91524d6a4cf9727370a0f69bc2d51039667f7a`.

## Native data and causal reconstruction

One unsigned public Info request preserved **3,520 HYPE/1m candles**, September
6 00:00 UTC through September 8 10:40 UTC, exclusive. Request clocks, HTTP 200,
exact response bytes, hashes and the complete ordered minute grid were retained.
No wallet credentials or signing client were loaded by the capture.

All **1,266 overlapping frozen market candles** agree exactly with that response:
**6,330 OHLCV comparisons**, zero residuals. This covers September 7 13:34 UTC
through September 8 10:39 UTC. Earlier native history supplies the five-minute
indicator warmup but is not independently bound to the original startup snapshot.

The reference computes squared Bollinger width with 50-digit Decimal arithmetic,
sample variance over 20 closes and an inclusive rank over 240 valid widths.
Ranking squared positive widths preserves their order without square-root
rounding. Only complete five-minute groups become available at their closing
time. Each decision uses the preceding completed minute; the prior compression
window contains exactly 15 earlier minutes and excludes the current minute.
Directional body uses `(close/open - 1) * 10000`, with its sign reversed for shorts.
The reference does not call production indicator, aggregation or classifier code.

| Compared input | Comparisons | Maximum absolute residual |
|---|---:|---:|
| Reference close | 907 | 0 |
| Current 1m BBWP | 907 | 0 |
| Prior 15-minute minimum BBWP | 907 | 0 |
| Prior count strictly below BBWP 25 | 907 | 0 |
| Authoritative 5m BBWP | 907 | 0 |
| Directional candle body, bps | 907 | 2.4775e-12 |

There are **5,442 metric comparisons**. Independent native values pass the fixed
5m compression condition in 642 evaluations, prior compression in 608, and
directional pullback in 436. These are overlapping component counts, not entry
opportunities or independent trades.

## The two already identified onsets

| Decision UTC, September 8 | Recorded side | Native 5m BBWP / maximum 50 | Prior BBWP minimum / maximum 40 | Directional body / maximum 0 bps |
|---|---|---:|---:|---:|
| 02:55 | Short | 83.3333, fails | 95.4167, fails | +4.7397, fails |
| 06:35 | Short | 33.3333, passes | 57.5000, fails | +9.4244, fails |

Both fail compression/pullback using independently reconstructed inputs. The
recorded state transitions, sides, readiness counts and blocker lists also remain
internally consistent under the earlier predicate audit. HYPE is configured for
long entries; its short observations do not authorize opening short positions.
Zero eligible HYPE entries remain in this prefix.

## Validation and evidence

Research source revision is `2d66a935f847a5b4c6a30a990384a40cde7e0c8b` in the
isolated research worktree. **21 production configuration/source files** match
the pre-start archive and both current worktrees, including the indicator,
aggregation, feature telemetry and provider definitions.

**109 offline tests pass** in the working tree and an extracted source archive,
with network access denied. The independent reference covers **80/80 statements
and 30/30 branches**. Tests plus the real replay cover **179/180 statements and
65/66 branches** across the two analysis modules; the uncovered path is the
module-entry guard, exercised separately by the initial CLI run. The
**5,029-member archive** is hash-verified and reproduces the report exactly.
Ruff, formatting, file/function limits, annotations and public docstrings pass.

Artifacts under the primary repository's
`data/logs/research/bidirectional_cohort/`:

- `v89_hype_compression_native_20260908_v1`
- `v89_hype_compression_audit_20260908_v1`
- Reused `v89_core_opportunity_inputs_20260908_v1`

The initial report retained a verbose decision-time list; the final report uses
a cadence summary, while all detailed comparisons retain their timestamps.
The initial executed audit source was recovered and checked against its recorded
SHA-256. Numerical findings were not changed.

## Disposition, limits and next investigation

Retain this as descriptive source evidence. No live strategy, threshold, asset,
sizing, leverage, execution, deployment or process lifecycle was changed.
The rejected HYPE onset-removal experiment was not reopened.

The remaining limitations are retrospective startup history, unverified recursive
EMA seeds and independent regime/side classification. A newly identified native
input mismatch, missing causal publication, incorrect window boundary or changed
source identity would update this diagnosis. Numerical parity does not validate
profitability, fills at larger size or a forecast of future trade frequency.

Correction, September 8: the proposed follow-up
`v89_seven_asset_common_window_joint_marking_v1` is withdrawn because the
[seven-asset shared study](2026-09-07-v89-seven-asset-shared-marking.md) and
[recorded-source sensitivity](2026-09-07-v89-recorded-native-source-sensitivity.md)
already existed in another worktree and DuckDB. The earlier expansion review
was no longer the latest evidence. Revision 2 of this hypothesis records the
correction; the original revision and its frozen review remain unchanged.

The distinct [chronological attribution](2026-09-08-v89-shared-chronological-stability.md)
is now complete. It identifies later-period modeled losses and makes historical
executable-price reconstruction of the known August 26 HYPE source-sensitive
entry the next investigation. See the
[current research index](../research-journal/v89-current-index.md) before
selecting another experiment. This correction changes no input-parity finding
or live behavior.
