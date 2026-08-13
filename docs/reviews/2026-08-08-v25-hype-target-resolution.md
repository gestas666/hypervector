# V25 HYPE target resolution and journal revision

## Problem restatement

The live v25 prefix gained one resolved lifecycle after the prior 20:23:37 UTC
audit. The required systems task was to isolate that economic change, reconcile
its venue costs and exit identity, distinguish it from provisional path
evidence, update the append-only research journal, and leave the armed runtime
unchanged.

## Evidence and identity

- Run: `bidirectional-live-1786182011216`.
- Profile: `multi_asset_bidirectional_complete_portfolio_canary_v25`.
- Immutable prefix:
  `data/logs/research/bidirectional_cohort/v25_live_prefix_20260808T210508Z.json`,
  SHA-256 `cd5048959139198be21d526539c288f430a279f3648b7be69849c4241122b320`.
- Immutable same-run delta:
  `data/logs/research/bidirectional_cohort/v25_live_prefix_delta_20260808T202339Z_20260808T210508Z.json`,
  SHA-256 `34c10eb42a054c68264ca87bad437d73c4909e4d1bc52aa95ece7b4bede4dc33`.
- Delta: 302 new cohort rows, one fill, one close, one win, +$0.552777
  net PnL, $0.042981 fees, and +$0.000078 signed funding.
- The 30 additional metric-value gaps are the known old-process HIP-3 pressure
  telemetry limitation. No technical-gap identity was added or removed.

## Resolved lifecycle

The new close is `HYPE:512893816278`, owned and exited by
`hulk_expansion_bidirectional_tuned_v2`:

| Field | Measured value |
|---|---:|
| Side | Long |
| Entry / exit | 54.760 / 55.198 |
| Exit | Venue target, OID `512893839186` |
| Hold | 5,510,079 ms, about 1.53 hours |
| Price return | +0.799854% |
| Net PnL | +$0.552777 |
| Net / entry margin | +3.719329% |
| Fees / funding | $0.042981 / +$0.000078 |
| Completed-path MFE / MAE | +79.9854 / 7.1220 bps |
| Peak giveback at exit | 0 bps |
| Gross MFE capture | 100% |

Post-exit completed-candle returns in the original long direction were
`-8.3336`, `-1.0870`, and `-15.0368 bps` at 5, 15, and 30 minutes. This is
consistent with the target capturing the measured favorable path before a
short-horizon reversal. It does not prove that every Hulk target is optimal.

The compatible-profile v25 history is now five closed lifecycles, four wins,
one loss, +$2.170721 net, 80% win rate, and profit factor 4.3046. These five
trades span two backend process windows and are explicitly not statistically
independent.

## Journal decision

The delta correctly recommended an economic revision because a lifecycle
resolved. Revision 2 of `hulk-eth-hype-native-transfer` was appended as
`59e35f9bf2deef1bda8077fcd0be3157682f181cd9402dfeb015b805a27fa682`.
The report verifies eleven matching evidence references, zero changed, and zero
missing.

The decision remains `reject` for a durable ETH/HYPE transfer edge. One exact
HYPE long winner contradicts the historical result, but it represents one side,
1.53 hours, and 100% of this route's live gross profit. It does not overturn 97
historical HYPE trades at PF 0.4639 and 100 historical ETH trades at PF 0.5919.
The falsifier requires 20 independently resolved live lifecycles per asset, 30
calendar days, both sides represented, positive after-cost PnL, combined PF
above 1.0, and no single trade above half of gross profit.

## Cockpit and validation

The closed-trade inspector now renders backend-authored completed-path MFE,
MAE, and peak giveback beside ignored-provider-exit evidence. It displays
`PATH EXCURSION UNAVAILABLE` when the backend lacks those values; it never
derives them locally.

- The exact red test failed because the line was absent, then passed after the
  projection was added.
- The complete cohort view suite passed 77 tests.
- The full `hypervector-tui` crate passed with zero failures.
- `cargo fmt --check --all` passed.
- The full non-network Python suite passed 4,131 tests, with four deselected
  network cases and 27 known warnings.
- Strict Clippy remains unclean because of two pre-existing unrelated warnings:
  one needless struct update in `backend_cohort_checkpoint.rs` and one
  collapsible conditional in `backend_cohort_opportunity_capture.rs`. Those
  user-owned paths were not changed in this increment.

## Uncertainties, failure modes, and next experiment

Confidence is high for the venue fill, costs, lifecycle identity, target exit,
audit hashes, and journal chain. Confidence that Hulk transfers durably to HYPE
remains low because the exact live sample is one long winner.

The assessment would be updated or falsified by a source hash mismatch,
unreconciled fee/funding arithmetic, a different provider identity, a later
audit removing or changing the resolved lifecycle, repeated exact-route live
outcomes satisfying the declared falsifier, or runtime/protection drift.

The next useful experiment is prospective, not a hot change: accumulate the
same exact Hulk/HYPE route on both sides and compare its realized target capture,
fees, funding, and post-exit reversal distribution. The still-open SPCX
Swing/HA lifecycle remains the separate provider-specific profit-protection
hypothesis. Neither observation authorizes a pooled exit change.

