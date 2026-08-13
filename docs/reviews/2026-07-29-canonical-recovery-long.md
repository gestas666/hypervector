# Canonical Recovery-Long Review

Date: 2026-07-29

## Problem restatement

The source-follow short candidate survives authentic Hyperliquid replay, but it
does not explain the creator's long entries. This experiment tests one finite,
causal long hypothesis already present in the alignment code: enter long on a
fresh 1m `TREND_UP` onset while the canonical 5m state remains `TREND_DOWN`,
during the Recipe C 07:00-16:00 UTC session.

The success criteria are positive chronological equity across touch,
book-through, and public-trade-through fills; tolerable drawdown; stability
outside one selected slice; and timestamp agreement with creator evidence.
The experiment is report-only and has no execution authority.

## Known facts and contract

- Candles are strict Hyperliquid 1m bars. The 90-day research cache contains
  129,532 native rows plus 68 explicit zero-volume `hl_gap_fill` rows.
- L2 and public trades come from the checksum-verified research database.
- Mark/oracle prices and hourly funding are authentic backward-known venue
  context.
- Portfolio assumptions remain $10,000 initial equity, one BTC position, 70%
  isolated margin, 40x leverage, 8% gross-margin target, no stop, and a
  24-hour maximum hold.
- Maker entry eligibility is five minutes. Same-direction re-entry requires a
  new episode after a 60-second minimum cooldown.
- ML remains observe-only and cannot filter, size, route, or exit trades.

## Full development result

The unconditional recovery-long hypothesis fails the 2026-04-28 through
2026-07-26 development window under every fill model.

| Fill model | Fills | Targets | Liquidations | Final equity | Max drawdown | Fees | Net funding |
|---|---:|---:|---:|---:|---:|---:|---:|
| Touch | 121 | 103 | 18 | $144.95 | -99.61% | $1,108.77 | -$43.87 |
| One-tick through | 120 | 102 | 18 | $138.37 | -99.63% | $1,096.16 | -$43.50 |
| Public trade-through | 117 | 100 | 17 | $207.52 | -99.45% | $1,322.66 | -$76.17 |

A high target rate does not rescue the economics. At 40x, each isolated
liquidation dominates multiple 8%-margin targets. The full-window result
falsifies this event as an unconditional standalone long strategy.

## Recent-window sensitivity

The strict full-window chronology concentrated 16 of 17 liquidations before
July. A new $10,000 portfolio was therefore started at 2026-07-01 as an
exploratory, retrospectively selected sensitivity—not as a clean holdout.

| Candidate / fill | Fills | Targets | Liquidations | Final equity | Max drawdown |
|---|---:|---:|---:|---:|---:|
| Recovery long / touch | 35 | 34 | 1 | $29,896.13 | -42.08% |
| Recovery long / through | 35 | 34 | 1 | $29,896.13 | -42.08% |
| Recovery long / trade-through | 27 | 26 | 1 | $20,370.28 | -48.66% |
| Source-follow short / touch | 13 | 12 | 1 | $11,048.11 | -57.54% |
| Source-follow short / through | 11 | 11 | 0 | $16,869.42 | -32.46% |
| Source-follow short / trade-through | 5 | 5 | 0 | $12,753.12 | -32.46% |

The recovery long has stronger July return and weaker strict drawdown than the
short arm. The short remains the stronger cross-regime candidate because it is
profitable across the full 90 days and its strict path has no liquidation.

This start-date sensitivity is size-aware. The July 6 $63,120 limit filled in
9 seconds in the nearly depleted 90-day portfolio because the order was only
0.0406 BTC. The fresh-July portfolio required 5.5820 BTC of cumulative
trade-through volume, filled after 66 seconds, and later liquidated. This is
expected capacity behavior, not replay nondeterminism.

## Forward observations

The two later windows are supportive but sparse:

- July 27: three recovery events, one fill, one target, no liquidation under
  every fill model. Strict final equity was $10,475.92 with -0.89% drawdown.
- July 28 00:00-22:00 UTC: three events, one fill, one target, no liquidation
  under every fill model. Strict final equity was $10,475.92 with -1.92%
  drawdown.

Two 1/1 forward fills cannot estimate a liquidation tail. They increase
confidence that the July effect is not solely one historical day, but do not
overcome the selected-window and regime-drift risks.

## Creator alignment and attribution

The candidate does not recover the six newer creator timestamps under the
evidence-backed UTC-5 conversion:

- recovery-long strict winner: 13:38 UTC;
- source-follow short strict winner: 14:55 UTC;
- creator longs: 14:40, 16:25, 16:38, and 17:28 UTC;
- creator shorts: 20:01 and 23:10 UTC.

The UTC-5 mapping is inferred from an earlier screenshot row whose displayed
time, entry price, and tracker timestamp agree. Treating the displayed clock
as UTC would create attractive near-matches, but contradicts that prior
evidence and is not accepted.

Simple canonical features do not cleanly separate the 100 strict targets from
17 liquidations. Median confidence was 0.508 for targets versus 0.417 for
liquidations; BBWP was 82.50 versus 77.08; completed-structure width was 76.64
bps versus 81.35 bps. The distributions overlap, and both groups are dominated
by 15m `TREND_DOWN` context. These are attribution differences, not justified
execution thresholds.

## Recommendation and trade-offs

| Option | Evidence | Benefit | Risk | Decision |
|---|---|---|---|---|
| Promote recovery long | July profit plus two forward targets | Adds a long arm | Full 90-day collapse; no creator timestamp match | Reject |
| Retain as annotation | Same measured evidence | Collects forward outcomes without gating | Slow validation | Accept |
| Add a July/date gate | Retrospective month split | Reproduces selected result | Non-causal calendar overfit | Reject |
| Retain source-follow short leader | Full-window and two forward targets | Best cross-regime evidence | Sparse and short-only | Accept as research leader |
| Combine arms now | Both profitable in July | Higher recent cadence | Conflict arbitration is untested | Defer |

Confidence is high in the accounting and the conclusion that unconditional
recovery-long fails. Confidence is medium that a recent July-specific effect
exists. Confidence is low that this is the creator's long trigger or a durable
future edge.

The recent-effect hypothesis would be falsified by a frozen sequence producing
a liquidation, negative aggregate forward equity, or fill-model disagreement.
The source-fidelity conclusion would be updated by authoritative creator order
timestamps, losing trades, or a documented long-entry rule.

## Immutable evidence

Development:

- touch: `13ed8fdc5d111982f80a6e24497e3c7f2b92d85ca81e76ee1977eb60c6bacefb`;
- through: `122bd5613803355141b6a313a554f22294a2bb6ee2b87f77bce0acefc7bcdc6a`;
- trade-through: `2558b2679d30cbd052b6b4d9dac19f5e3cf84c5148fa1e909a5578acbd30db36`.

July 1-27 recovery long:

- touch: `ca8b36a56ea49ff6429cb94f2c51d872f62d8e6f628b4ec58b0314ed389a1dff`;
- through: `8bed35185ec6180d6c1be4f3ba38e5eb25a343b2c03d527af091e4aa2b7a2022`;
- trade-through: `af096d3351dd71375ae55d349948353fd74e74362f04b94796c9d646e483a003`.

July 27 recovery long:

- touch: `06c78425d0bca89792aebaecaecaf82f12ee9347c142d8e9e561c93c0660fd72`;
- through: `aae55e9bfcbf594768ae033fe1a115ffa2bcd0ed2051736266acd2df0d7b4a2d`;
- trade-through: `d46bb2729a0aedafaff271223377d619428ba184d30abcca4a22a3a898e28f08`.

July 28 recovery long:

- touch: `7ac7517b40e1694578ec7dcf33457acb216448992b1fcc0ce56755ec65fce3df`;
- through: `ba422ed3a50ccee1dfee4a159c3323fa62cf87d6c761ca28df7d629a001f8176`;
- trade-through: `cadd68e46f7462406ddfd0202597be7edb906c8d06645c21b487e4b63c1636d1`.

Same-window source-follow short:

- touch: `56b8ecf91fe3ac331fba1b8d4b47546d99b463f7124260cf63f19c8437f4b054`;
- through: `a57c87bff42678b4167ffe6a73310f1e7a0deba3cab8046e41b291ee26b91587`;
- trade-through: `4eae1d285bcc340ef2454dae73edb1ac7101751b8619fb50cac616f8c002e55e`.
