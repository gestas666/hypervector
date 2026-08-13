# ETH Breakout-Transfer Canary Qualification

## Decision

Prepare, but do not activate, profile
`multi_asset_bidirectional_evidence_routed_hype75_eth25_canary_v12` for the next
verified-flat restart boundary. It adds both-direction ETH execution at a
$25 maximum notional and 5x isolated leverage while preserving the existing
BTC/HYPE mappings, four-position shared portfolio cap, and one-position-per-coin
rule.

This is a low-confidence live research canary, not evidence of an established
edge. The active v11 backend remains unchanged while its HYPE lifecycle is open.

## Reproduction and provenance

The selected row was regenerated directly from:

- `data/cache/ETH_1m_365d.parquet`, SHA-256
  `e10e00209f1584151c23a69d39116485d7c241e00d4a8c2031f7e624a431bd84`;
- matched Hyperliquid ETH funding, SHA-256
  `8debd8c1084168e705f98b8ee2c7fb82c32f9329adf053dee09e787fe5a265d8`;
- `data/logs/research/eth_breakout_transfer_stop_hold_tuning_v1_20260805.json`,
  SHA-256
  `b41e43ed8cf81543a894780dcc4683d2cc318812bdb1e88132907e296fc5e3c6`.

The replay regenerated the market row counts, split boundaries, entry counts,
trade counts, wins/losses, fees, funding, fold returns, maximum drawdown, net
return, profit factor, and exit-reason counts without a mismatch.

## Exact candidate contract

- Signal clock: completed one-minute evaluations of a fresh canonical completed
  five-minute `BREAKOUT` onset.
- Side: completed-hour SMA10/SMA30 structural direction; both long and short are
  retained.
- Entry filters: prior 15 one-minute BBWP minimum at or below 40 and current
  directional candle body at or below zero.
- Entry: taker IOC with a 60-second maximum signal age.
- Exit: venue-protective 60-bps stop or fixed 12-hour maximum hold; no profit
  target.
- Risk: $25 maximum ETH notional, 5x isolated leverage, approximately $5 margin
  at the cap. A 60-bps stop plus the 13-bps modeled round-trip friction is about
  $0.18 at full notional before live slippage variance and funding.
- Portfolio: shared account, maximum four simultaneous positions, maximum one
  position per coin.

## Reproduced results

| Scope | Side | Trades | W/L | Net bps | PF |
|---|---|---:|---:|---:|---:|
| Development | Both | 282 | 67/215 | +1,657.98 | 1.1111 |
| Development | Long | 142 | 32/110 | +254.70 | 1.0332 |
| Development | Short | 140 | 35/105 | +1,403.28 | 1.1932 |
| Opened final 60d | Both | 56 | 18/38 | +322.33 | 1.1208 |
| Opened final 60d | Long | 26 | 10/16 | +345.18 | 1.3109 |
| Opened final 60d | Short | 30 | 8/22 | -22.85 | 0.9853 |

Development had four positive chronological folds out of five, but the fifth
fold lost 1,630.88 bps. Historical cadence was 338 completed trades across the
365-day development plus opened-final window, approximately 0.93 per day before
live occupancy and routing effects.

## Selection caveat

The original post-hoc entry-policy screen selected the same compression and
pullback rule as its least-bad challenger, but under the original 80-bps stop
and eight-hour hold it remained negative: 281 trades, -187.11 bps, PF 0.9886,
and three positive folds of five. A subsequent 20-cell stop/hold surface selected
the 60-bps/12-hour shape. The final 60-day block was then opened once and is
descriptive, not sealed evidence.

The side attribution also rotated: shorts carried development while longs
carried the opened final block. The aggregate result therefore cannot justify a
directional edge claim. Both sides remain enabled only so the bounded canary can
measure that instability prospectively rather than silently choosing the most
recent winner.

## Failure modes and falsifiers

- One-minute bars cannot reproduce intrabar path ordering, IOC latency, private
  queue state, rate-limit behavior, or realized slippage.
- The selected shape is multiple-tested and the opened final block is not a
  pristine holdout.
- Protective stops accounted for 208 of 282 development exits and 37 of 56
  opened-final exits; a small gross edge can be erased by live friction.
- Long/short leadership was unstable across time.
- A provider/runtime feature mismatch, stale onset replay, missing venue stop,
  duplicate ETH position, or any route beyond ETH invalidates implementation
  parity and requires fail-closed correction.
- After-cost prospective outcomes materially below PF 1, persistent loss on
  both sides, or live friction exceeding the thin historical surplus would
  falsify the economic hypothesis. These are reported outcomes, not implicit
  automatic shutdown gates.

## Validation boundary

Promotion beyond the $25 canary requires reconciled venue fills, fees, funding,
slippage, stop identity, maximum-hold behavior, and complete entry-feature
telemetry. Twenty resolved ETH lifecycles is a first review checkpoint, not a
claim that twenty trades proves edge. The canary profile must only replace v11
at a verified-flat transition with a prestart backup and exact fingerprint.
