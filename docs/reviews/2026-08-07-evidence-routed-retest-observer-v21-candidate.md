# Evidence-routed retest-observer v21 candidate

**Prepared:** 2026-08-07 EDT  
**Runtime effect:** none; inactive candidate  
**Active runtime:** `multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14`

## Problem restatement

The next portfolio generation needs cleaner executable attribution than v14
without losing the ability to learn from the bounded breakout-retest hypothesis.
Success means preserving v18's three explicit execution routes while recording
the v2 challenger prospectively on BTC, ETH, SOL, and HYPE. Observation must not
silently become execution authority.

## Known facts

- **High confidence:** v21 has exactly four portfolio slots and each of its four
  assets permits one position. This is enforced by configuration validation and
  the focused contract test.
- **High confidence:** the only executable mappings are Hulk/BTC,
  ETH-pullback/ETH, and v1 breakout/HYPE. Retest v2 has an empty execution scope
  on all four assets.
- **High confidence:** the real poller constructs the v2 collector, so a future
  v21 run can record arms, confirmations, expirations, and withheld routing from
  the live completed-bar stream.
- **High confidence:** live start still requires both explicit arming flags.
- **Low confidence:** any of the three executable mappings has positive forward
  expectancy. Their current evidence is sparse, contradictory, or negative.
- **Low confidence:** retest v2 improves economic outcomes. In the current v14
  replay it confirmed 3/7 onsets, but the confirmed short reference prices were
  worse by 7.92 bps on average; one confirmed HYPE lifecycle lost and two remain
  unresolved.

## Candidate contract

| Asset | Executable provider | Sides | Maximum notional | Retest v2 |
|---|---|---|---:|---|
| BTC | Hulk expansion | long + short | $25 | observe only |
| ETH | precompression pullback | long + short | $25 | observe only |
| SOL | none | observed both ways | $75 ceiling | observe only |
| HYPE | breakout onset v1 | long + short | $75 | observe only |

All assets use isolated 5x. The candidate fingerprint is
`0b0d4a841241f60814eef68fb52adcf93fb323744978f7427ec8372a819518a0`.

## Failure modes and validation

| Failure mode | Detection | Response |
|---|---|---|
| Retest gains execution authority | Exact route assertion and startup fingerprint | Refuse the generation |
| A coin gains multiple position slots | Config invariant and TUI identity validation | Fail configuration load |
| Retest state is reconstructed incorrectly | v1/retest change monitor and immutable replay identity | Classify as technical fault |
| Confirmation only delays to a worse fill | Record decision reference, venue fill, slippage, and missed v1 path | Report after-friction delta |
| Candidate inherits v14 exposure | Flat/no-owned-order transition reconciliation | Do not start v21 |
| Sparse positive result is mistaken for edge | Route-, side-, and cluster-aware journal | Retain provisional confidence |

## Recommendation

Prefer v21 over v18 for the next verified-flat experiment because it adds
prospective challenger telemetry without changing v18's execution scope. Do not
activate it while v14 owns BTC, ETH, or SOL positions. At the flat boundary,
publish the final v14 audit, verify no owned orders, create a fresh backup, and
request explicit approval for the exact v21 fingerprint.

**Overall confidence: low-to-medium.** Mechanical isolation is strongly tested;
economic value is not established. A larger non-overlapping bidirectional sample
where confirmed retests improve attainable after-friction outcomes would raise
confidence. Continued negative route outcomes, observer/runtime mismatches, or
expired v1 paths outperforming confirmations would lower it.
