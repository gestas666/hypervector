# Hypervelocity source/canonical overlap review — 2026-07-29

## Problem restatement

Determine whether the current Hypervector backend can causally recognize the
profitable source-follow short candidate. Success means the canonical engine
has the same executable direction on the last completed 1m bar when each
pinned Hypertrader 5m event becomes available. This is a report-only audit; it
does not change execution authority, runtime configuration, or ML authority.

## Inputs and causal contract

- 525,600 Hyperliquid-native 1m bars from 2025-07-28 through 2026-07-27.
- 277 pinned-current Hypertrader `TREND_DOWN` onsets in the 06:00-15:00 UTC
  window with source confidence at least 0.70.
- Current faithful Hypervector 1m/5m/15m regime configuration.
- Each source decision at time `t` is matched only to the completed canonical
  1m bar at `t - 1 minute`. Missing exact bars fail visibly rather than using
  nearest or future values.

## Directional overlap result

| Measurement | Result |
|---|---:|
| Source events | 277 |
| Exact canonical rows available | 277 |
| Canonical short entry direction | 277 |
| Canonical opposite direction | 0 |
| Canonical no-entry direction | 0 |
| Exact directional overlap | 100.0% |

The canonical primary regime at those events was `TREND_DOWN` for 263,
`BREAKOUT` for 7, and `RANGE` for 7. The seven non-trend primary rows still
carried a canonical short structural entry direction. This is not evidence
that RANGE should become tradable; it shows that `primary_regime` and
`entry_direction` are distinct telemetry fields.

## Timing result

The source onsets generally occur inside an already-active canonical short
run rather than at its beginning:

| Canonical short-run age at source event | Events |
|---|---:|
| 0-5 minutes | 43 |
| 0-15 minutes | 98 |
| 0-30 minutes | 142 |
| 0-60 minutes | 183 |
| Median | 30 minutes |
| 90th percentile | 262 minutes |

Therefore the remaining mismatch is event timing, not trade direction. A
canonical trend-onset rule is not equivalent to the source classifier event.

## Replay-outcome attribution by canonical run age

The 163 source events covered by the twelve gap-free execution blocks were
joined to their serialized order lifecycle outcomes. This is diagnostic and
was not a predeclared parameter search.

| Run age | Events | Filled | Targets | Liquidations | Net PnL |
|---|---:|---:|---:|---:|---:|
| 0-5m | 24 | 9 | 9 | 0 | +$4,769.37 |
| 6-15m | 37 | 14 | 13 | 1 | +$3,270.89 |
| 16-30m | 21 | 6 | 6 | 0 | +$3,126.93 |
| 31-60m | 27 | 8 | 6 | 1 | -$923.80 |
| 61-120m | 17 | 8 | 7 | 1 | +$1,277.47 |
| 121-240m | 17 | 7 | 7 | 0 | +$3,518.28 |
| 241m+ | 20 | 7 | 7 | 0 | +$3,594.96 |

Older canonical runs still produced targets, including all seven filled
events older than four hours. This falsifies using canonical run freshness as
an entry gate on the current archive. The three liquidation observations are
too sparse to infer a stable age relationship.

## Engineering decision

1. Keep the current canonical detector as the directional confirmation and
   operational regime telemetry.
2. Do not replace source event timing with canonical trend freshness.
3. Evaluate the pinned source onset as a report-only forward trigger on new
   recorded Hyperliquid tape before granting it execution authority.
4. Do not add an age gate; it would remove profitable mature-run fills and is
   unsupported by these outcomes.
5. Keep ML in observe mode and leave the active shadow runtime unchanged.

## Confidence, risks, and falsifiers

- **High confidence in causal directional overlap**: every exact timestamp was
  available and all 277 directions matched. This would be falsified by a
  reproduced audit with a different decision identity or by discovering an
  availability-time error.
- **Medium confidence that source timing is the missing operational feature**:
  canonical run ages are broadly distributed and only 43 events occur within
  five minutes of canonical onset. This would be updated if a canonical-only
  timing rule reproduces the same event timestamps without source labels.
- **Low-to-medium confidence in live profitability**: the replay candidate is
  post-selected, only 58 positions resolved, and three liquidations drive
  material tail risk. At least 50 new resolved forward positions and ten
  complete observer activations remain the frozen acceptance evidence.
- Queue rank is unobserved, session selection may be data-mined, and a
  one-sided short candidate is not yet a complete two-sided Hypervelocity
  strategy.

## Evidence

- Immutable overlap report SHA-256:
  `3b24c5ee7c87e9dec912b93345bdac352beb35bc8134849fd84366baaaf229ac`
- Canonical decision identity SHA-256:
  `c3f8fc379700c5358cfe8d330dd7c2496b322af973700699341f56b6756dc103`
- Bar input SHA-256:
  `b0742553ebeaa7cb4af6fabfd496f5462354cb541705fd0ca5ec222dc21e15d8`
- Source-label input SHA-256:
  `de6beef5eed4caf29f595e0c04cb9d26b33b063b05847c7a1b66b0cba3138653`
