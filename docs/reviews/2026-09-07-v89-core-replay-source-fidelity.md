# V89 core replay repair and historical source fidelity

Research correction `9feb625` preserves core decisions that a later source gap
previously erased. The exact 48-day core extraction now finishes with 245
rolling-history checks and zero mismatches at the tested boundaries. Separate
price-source checks establish that archive candles differ from native candles;
the conditional lifecycle screen must retain that limitation.

Confidence is high for the reproduced extraction defect and measured source
differences. Confidence in exact historical live execution is low: private
fills, native mark paths, source timing and every-minute cross-source decision
parity have not been reconstructed. No strategy change is recommended from
this small, already-explored sample alone.

## Scope and provenance

- Worktree: `hypervector-v89-portfolio-20260907`, based on installed main
  `a42afa8`. Original trading checkout and live configuration remain unchanged.
- Exact V89 profile fingerprint:
  `39e334fc97f3cbe21bac30e53e91524d6a4cf9727370a0f69bc2d51039667f7a`.
- Evaluation: July 21 through September 6, 2026; 48 days. Core source history
  starts July 7 for the current 14-day collector retention.
- Existing SPCX numerical correction `9574435` remains isolated and is not
  silently included in this baseline.
- Previous operator-status turn: no progress on the research objective. It
  confirmed an armed backend but did not change its state or complete research.
  This turn advances the goal through code repair and new source/lifecycle evidence.

## Reproduced defect and repair

The production range collector retains the latest contiguous segment of the
bars it receives. The old research extractor supplied a full day at once. A
three-minute gap later in that day caused it to discard earlier observations
that were already available at their original decision time.

The actual ETH collector regression expected 177 decisions in a three-hour
fixture, but the old extractor returned only 87. Adding the later gap also
changed the already-observed first-hour decision prefix. All three regressions
failed before the repair. Batches now end before a gap and resume at the first
actual source bar; missing minutes receive no invented provider decisions.

The replay command also accepts four explicit `--bar-file SYMBOL=PATH` inputs.
It reuses the existing four-core mapping parser, fingerprints the supplied
paths, and rejects malformed, duplicate, incomplete and nonexistent mappings.
Legacy cache defaults and immutable-output refusal are preserved.

Final focused verification: **40 tests passed**, **100% statement coverage**
of `cohort_core_provider_replay.py`, clean Ruff and `git diff --check`.
No trading client or live configuration is involved in this repair.

## Completed extraction and source verification

| Asset | Source rows over 62 days | Missing scoring minutes | Decisions | Rolling checks | Mismatches |
| --- | ---: | ---: | ---: | ---: | ---: |
| BTC | 89,257 | 18 | 1,145 | 51 | 0 |
| ETH | 89,255 | 20 | 69,100 | 74 | 0 |
| SOL | 89,255 | 19 | 69,101 | 66 | 0 |
| HYPE | 89,256 | 19 | 69,101 | 54 | 0 |

All four candle bundles reproduce exactly from their vendor raw pages. Each
has nine pages and complete pagination; the longest missing interval is three
minutes. Complete pagination is not a complete minute grid. Native 15-minute
bars and funding files also reproduce exactly from their saved API payloads.
All 1,152 scoring hourly funding records per asset are present, and every
funding boundary has an actual minute-candle observation.

Rolling parity covers every batch-eligible entry, every batch exit and daily
noon controls. It does not prove that an untested nonactionable minute would
remain nonactionable under rolling history, nor does it compare different feeds.

## Material source disagreement

Complete minute aggregates and native 15-minute candles disagree at some OHLC
values. The largest tested discrepancies include:

| Symbol / UTC quarter | Field | Archive aggregate | Native 15m | Absolute difference |
| --- | --- | ---: | ---: | ---: |
| ETH / Aug 19 20:45 | High | 2,283.10 | 2,247.00 | 160.66 bps |
| SOL / Aug 22 05:00 | Low | 86.720 | 87.688 | 110.39 bps |
| BTC / Aug 19 20:45 | High | 69,744 | 69,628 | 16.66 bps |
| HYPE / Aug 19 19:15 | High | 73.754 | 73.368 | 52.61 bps |

Four independent bounded archive requests returned three 15-minute bars each.
All twelve match their one-minute archive OHLC aggregates exactly. Further
raw-page reproduction yielded 9,242 ETH and 3,901 SOL public trades, with the
same disputed extrema. This corroborates the vendor's own candle construction;
it is not independent proof of native venue candle or stop-trigger semantics.

A fresh unsigned native one-minute capture for September 5–6 contains exactly
2,880 bars per core asset. Archive versus native open/close differences persist
at this identical cadence, reaching 7.03 bps for HYPE opens. Thus timeframe
aggregation alone cannot explain the disagreement. Cause and exact strategy
impact remain unresolved. Neither source was overwritten or chosen for its PnL.

The [native API documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint)
limits candle history to the most recent 5,000 bars. The
[archive candle documentation](https://docs.0xarchive.io/rest-api/candles)
defines OHLC and interval timestamps, but does not resolve the measured native
discrepancy. Full historical native minute parity is not available from the
recent native sample alone.

## Conditional lifecycle results

The existing fixed-core and HYPE exit engines use the unchanged current routes,
native hourly funding rates, and explicitly modeled 4.5 bps fees per side.
Minute opening prices and funding marks are proxies. Missing prices carry the
previous close under the `hl_gap_fill` label; collectors still receive raw
gap-bearing inputs. Unknown canonical observations remain unknown.

| Asset | Trades | Wins | Nominal net USD | Adverse net USD |
| --- | ---: | ---: | ---: | ---: |
| BTC | 3 | 2 | 6.37 | 4.10 |
| ETH | 3 | 0 | -8.39 | -8.99 |
| SOL | 5 | 2 | 3.80 | 2.76 |
| HYPE | 5 | 1 | -71.04 | -75.53 |

Nominal/adverse slippage is 2.5/5.5 bps per side. HYPE dollar values assume the
configured $2,500 notional cap; shared cap binding is not yet proven. Every
trade independently reconciles gross PnL, entry/exit fees and timestamped
funding to within $0.00000001. One ETH lifecycle touches missing minutes in
each cost case. All results, including losses, remain reported. These sixteen
conditional core trades do not constitute the seven-asset portfolio result.

## Decision, alternatives and remaining work

Accept the research extraction correction within the isolated worktree. Its
benefit is causal historical coverage, not an asserted improvement in returns.
Doing nothing retains a reproduced coverage defect; filling signal inputs to
hide gaps changes the strategy's observations. Reverting the isolated commit
remains a research rollback option if future-prefix invariance fails. Existing
immutable outputs must be preserved under their original source revisions.

The highest-value next investigation is the exact seven-asset shared cash,
funding, marked exposure and margin path, with the current three additions and
all predeclared cost cases. Source uncertainty must be measured alongside that
path, including lifecycles and prior indicator histories touching discrepancies.
No independent-PnL sum may substitute for shared sizing or drawdown validation.

Still required: joint capacity, overlapping losses/correlation/concentration,
source-sensitive decision/lifecycle effects, prospective native fills, the
isolated SPCX fix deployment decision, and the documented old-launcher reporter
ownership message on eventual shutdown. The overall goal remains active.

Approval requested: none for this report-only research correction. No live
strategy, sizing, order, restart or deployment change was made in this turn.

## Immutable evidence locations

All paths below are under the original checkout's
`data/logs/research/bidirectional_cohort/`:

- `v89_shared_verified_core_inputs_20260907_v1/manifest.json`
- `v89_shared_core_decisions_20260907_v1/manifest.json`
- `v89_shared_source_comparison_20260907_v1/report.json`
- `v89_shared_recent_native_1m_20260907_v1/manifest.json`
- `v89_shared_core_lifecycles_20260907_v1.json`
- `v89_shared_core_cashflow_validation_20260907_v1.json`
- `v89_shared_core_replay_final_tests_20260907_v1.log`

The accompanying hypothesis record pins the supporting files and successful
validation output. Raw candles, participant pages and public trade artifacts
retain the vendor request IDs and SHA-256 manifests under `data/cache/vendor/`.
