# Source-follow observe-only portfolio candidate

## Decision

Confidence: medium.

Preserve HYPE breakout and Hulk Smash as bidirectional execution providers in a
separate inactive candidate, preserve source-follow as a fully measured
bidirectional observer, and remove only source-follow's BTC order authority.
Range-onset remains observe-only. This is a next-flat candidate, not a live
change or an automatic performance gate.

Candidate:
`configs/multi_asset_bidirectional_source_observe_hype_fixed8_candidate.toml`

- Profile fingerprint:
  `3fee4878a5c30c5f67f2526dcfec9461ba0915280b83720e7ecdfffb1896ab47`
- File SHA-256:
  `c03c7b59bbbf49e6256696534f76b1d616b56bd95854238491203241e8d67d73`
- Executable pairs: Hulk Smash on BTC/ETH/SOL/HYPE and HYPE breakout on HYPE.
  Every executable pair retains both long and short authority.

An exposure-only aggressive variant is also preserved at
`configs/multi_asset_bidirectional_hype_core75_source_observe_fixed8_candidate.toml`.
It changes the HYPE asset ceiling from `$25` to `$75` while pinning Hulk HYPE
at `$25`, so only HYPE breakout inherits the larger ceiling.

- Profile fingerprint:
  `e5506e63e76fd99c1d73c3ea6b35e7ee428e6a15b07505fa12cf2435c33b240b`
- File SHA-256:
  `fdff218893885cae0afb25b3fd5612a68810b801425971d67ddebc1a6f2ae679`

An evidence-routed variant is preserved at
`configs/multi_asset_bidirectional_evidence_routed_hype75_fixed8_candidate.toml`.
It keeps every provider-symbol mapping observable but limits order authority to
HYPE breakout/HYPE at `$75` and Hulk Smash/BTC at `$25`, both bidirectional.

- Profile fingerprint:
  `697f30b2bb4eb430c5f514c8b82cdbe994a5decf100459da243c53660b5177b6`
- File SHA-256:
  `936ec127645c4e07f1fde77f8571f60b8daae720746471fc966d2a97008048fd`
- Complete entry, routing, risk, and exit contract:
  `docs/reviews/2026-08-05-hype-breakout-strategy-contract.md`

## Live evidence

The 2026-08-05 10:23 EDT checkpoint contained 14 reconciled closed
lifecycles across three profile fingerprints and six trade-bearing backend
process runs. Process runs are descriptive restart windows, not independent
trials.

| Provider | Closed | W/L | Net USD | PF | Mean PnL/trade on margin |
|---|---:|---:|---:|---:|---:|
| HYPE breakout / HYPE | 6 | 5/1 | +2.099489 | 10.3762 | +7.0633% |
| Hulk Smash / BTC | 2 | 2/0 | +0.343915 | no loss | +3.4708% |
| Source-follow / BTC | 5 | 3/2 | -0.104597 | 0.6951 | -0.4249% |
| Range-onset / ETH | 1 | 0/1 | -0.174380 | 0.0000 | -3.4986% |

HYPE breakout closed positive in four of five trade-bearing process windows.
Its long side closed positive in three of four windows; its single short window
was positive. The current runtime profile contributed two HYPE closes, both
wins, for `+$1.094830`. The open HYPE long was protected and marked
`+$0.244780` at the audit point, but that provisional mark is excluded from the
closed-performance decision.

Source-follow closed positive in one of three trade-bearing process windows.
Its long side remains negative in both trade-bearing windows and totaled
`-$0.239760` over four closes. The current runtime profile's three resolved
source-follow trades were 2W/1L, `-$0.115626`, PF `0.4717`. The latest BTC
source-follow long hit its target for `+$0.051270` net while this review was in
progress. That improves the sample but does not reverse its after-cost total.

The separate one-year venue study also found the deployed source-follow shape
negative after modeled costs on both sides: 365 long trades with PF `0.5707`
and 417 short trades with PF `0.6667`. That study does not reproduce private
live fills, so it is corroboration rather than a substitute for live evidence.

## Aggressive HYPE allocation evidence

At approximately `$505.69` account value, the current `$25` HYPE notional uses
`$5` margin, or `0.99%` of account value. The `$75` variant uses `$15` margin,
or `2.97%`, at the same 5x isolated leverage. The checkpoint's portfolio
envelope increases from `5.93%` to `7.91%` maximum simultaneous effective
margin.

The latest 240 public HYPE book snapshots had complete visible depth for the
`$75` size. Measured p95 visible sweep impact was `0.15 bps` for a long and
`0.40 bps` for a short; maximum observed impact remained below `1.05 bps`.
This supports venue capacity only. Public depth can cancel before the IOC
arrives, and it does not establish signal profitability.

## Why observe instead of delete

An empty source-follow `execution_symbols` list causes every fresh source event
to remain evaluated and journaled as `provider_symbol_observe_only`. It removes
order authority without erasing signal cadence, blockers, regime context, or
forward paths. This preserves the evidence needed to falsify the retirement
while preventing the current negative shape from consuming BTC capacity.

## Risks and trade-offs

- Four source-follow closes and six HYPE closes are sparse. Profit factor can
  move sharply after one additional loss.
- HYPE history spans multiple profile fingerprints and exit policies. The
  fixed-eight-hour exit still needs direct live evidence after a safe profile
  transition.
- Removing source-follow execution reduces portfolio trade frequency. The
  appropriate response is to qualify new bidirectional challengers, not to
  treat a negative provider as profitable for activity's sake.
- Hulk Smash has no resolved live evidence outside BTC in this checkpoint.
- A threefold HYPE notional increase approximately triples both wins and losses;
  it does not improve the underlying signal or exit policy.

## Falsifiers and next evidence

Reconsider source-follow order authority if a profile-matched observe window
produces at least 20 resolved, venue-friction-equivalent trades with PF above
one, positive net PnL, and positive results across multiple non-adjacent
windows. Reconsider HYPE's core status if 20–30 profile-matched closes fall to
PF at or below one or negative after-cost net PnL. Reconsider the fixed-eight-
hour exit if direct live lifecycles repeatedly retain more after-cost profit
beyond that boundary than they give back.

No running process, position, order, stop, target, staged profile, or signing
authority was changed during this review.
