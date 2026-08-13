# V25 GOLD maximum-hold resolution

## Problem restatement

The immutable v25 prefix gained one resolved `xyz:GOLD` lifecycle after the
22:30 UTC audit. The systems task is to reconcile its venue costs, entry and
exit ownership, completed path, ignored recipe-exit evidence, and known
telemetry limitations without changing the armed portfolio.

## Evidence and identity

- Active run: `bidirectional-live-1786182011216`.
- Profile: `multi_asset_bidirectional_complete_portfolio_canary_v25`.
- Lifecycle: `xyz:GOLD:512544506543`.
- Entry originated in compatible predecessor run
  `bidirectional-live-1786137154835`; v25 adopted and closed it under the same
  profile fingerprint
  `ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc`.
- Immutable prefix:
  `data/logs/research/bidirectional_cohort/v25_live_prefix_post_checkpoint_repair_20260808T2307Z.json`,
  SHA-256 `5d9b2e3b53c793df07b296ce6e60a24c140e93a04654a5ed7b4edb82dddc620f`.
- Immutable same-run delta:
  `data/logs/research/bidirectional_cohort/v25_live_delta_2230_to_2307_20260808T2307Z.json`,
  SHA-256 `e7462e14cce7be93e8235b1f82856f0e1d2a11349d0576a4c3216bf664b45a3d`.
- Delta: 261 new cohort rows, two GOLD fills, one close, one loss,
  `-$0.242433` net PnL, `$0.129325` fees, and `-$0.008188` funding.
- The 20 additional metric-value gaps are the known loaded-process HIP-3
  pressure-clock limitation. No technical-gap identity was added or removed.

## Resolved lifecycle

The long entry was owned by
`hip3_swing_ha_sndk_gold_brent_bidirectional_v1`; the close was owned by
`cohort_maximum_hold`.

| Field | Measured value |
|---|---:|
| Side | Long |
| Entry / exit | 4354.3 / 4348.2 |
| Entry / exit OID | `512544506543` / `512949596449` |
| Exit reason | `maximum_hold_seconds` |
| Hold | 86,411,114 ms, about 24.00 hours |
| Price return | -0.140091% |
| Net PnL | -$0.242433 |
| Net / entry margin | -1.625793% |
| Fees / funding | $0.129325 / -$0.008188 |
| Completed-path MFE / MAE | +7.8084 / 38.8122 bps |
| Peak giveback | 21.8175 bps |
| Protective stop | 4319.4656; not crossed |

The entry never cleared a round-trip friction threshold: maximum favorable
excursion was only 7.8 bps before fees, funding, and exit slippage. The path was
already -25.0 bps after four hours and -22.5 bps after twelve hours. This is
evidence of weak entry follow-through, not a liquidation or stop-placement
failure.

## Ignored recipe-exit evidence

The first ignored `hip3_swing_ha_flip` close-long signal occurred around twelve
hours after entry at reference price 4344.7, approximately -22.05 bps gross.
The actual maximum-hold exit recovered 8.06 gross bps from that reference and
closed at -14.01 gross bps. Therefore this one lifecycle does not support
promoting the earlier recipe exit: it would have crystallized a worse gross
price before unmeasured counterfactual costs. It also does not establish that a
24-hour hold is desirable; the final result remained negative after costs.

Canonical regime context is unavailable for this HIP-3 asset in the resolved
record. Consequently the evidence cannot determine whether a regime-alignment
filter would have rejected the entry. That missing classification is a
specific analysis limitation rather than permission to infer a regime cause.

## Portfolio interpretation

Compatible-profile history at this boundary is six closed lifecycles, four
wins, two losses, `+$1.928288` net, `$0.314712` fees, `-$0.029060` funding,
and profit factor `3.144198`. Maximum drawdown is `0.301368%`. Six closes are
too sparse and provider-concentrated to establish a durable portfolio edge.

The GOLD result weakens the Swing/HA onset entry hypothesis because favorable
follow-through never exceeded costs. It does not justify disabling GOLD,
changing exits, shrinking risk, or altering the live profile from a single
long lifecycle.

## Validation and failure modes

Confidence is high for fill identity, costs, maximum-hold ownership, path
arithmetic, stop non-crossing, and immutable artifact hashes. Confidence in an
economic remedy is low because there is one resolved GOLD long, no resolved
short, and no canonical regime classification.

The assessment would be updated or falsified by changed artifact bytes,
different venue fills or costs, evidence that the stop crossed before exit,
reconstructed canonical regime data with causal provenance, or independent
both-side GOLD/SNDK/BRENTOIL lifecycles that repeatedly clear live friction.

The next report-only experiment should measure whether exact Swing/HA entries
that also have finite order pressure and causally available multi-timeframe
context improve post-entry MFE and after-cost outcomes. It must preserve the
ungated live result as the control and must not gain execution authority from
this review.

No process, route, order, position, stop, target, size, allocation, exit policy,
or runtime strategy changed during this analysis.
