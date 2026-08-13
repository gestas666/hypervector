# Source-follow live-tape checkpoint — 2026-07-30

## Problem restatement and success criteria

This checkpoint asks whether the frozen source-follow lead can classify and
execute the first newly recorded Hyperliquid window more faithfully than the
still-running canonical shadow backend. A useful result must use only
decision-time source labels, native live L2/public trades, live mark/oracle and
funding observations, the exact shadow execution contract, and no ML authority.
It must also preserve every unfavorable outcome and leave the active backend
untouched.

## Known facts and fixed assumptions

- Candidate: pinned Hypertrader revision
  `ad15f2bdc949619be495a5f516babd08f7f52a90`, completed-5m TREND_DOWN onset,
  confidence at least 0.70, completed-bar range 12-100 bps, short only, 24/7.
- Portfolio: $15,000, 50% isolated margin, 30x, one BTC position.
- Execution: 60-second post-only entry, displayed queue ahead, public-trade
  consumption, partial fills, 50 ms submit/cancel latency, 6-second event-age
  limit, maker/taker fees, authentic funding, and isolated liquidation.
- Exit: 8% gross-margin target, no fixed stop, 24-hour maximum hold.
- ML: observe-only. It cannot filter, resize, or place an order.
- Window: 2026-07-29 17:00 UTC through 2026-07-30 04:00 UTC.
- This is report-only replay. It did not restart, reset, or mutate the active
  faithful shadow backend.

## Fresh live-tape result

The pinned source produced two qualified decisions. Both entered through the
production queue matcher, completed their targets, and ended flat.

| Metric | Result |
|---|---:|
| Initial / final equity | $15,000.00 / $15,737.63 |
| Net PnL | +$737.63 |
| Signals / submitted entries | 2 / 2 |
| Targets / time exits / liquidations | 2 / 0 / 0 |
| Maker / taker fees | $92.89 / $0.00 |
| Funding cashflow | +$1.15 |
| Maximum marked drawdown | -8.59% |
| Execution-uncertainty annotations | 0 |
| Missing / stale funding-oracle settlements | 0 / 0 |

The first signal entered at 2026-07-29 17:05:01.534 UTC and completed at
19:47:31.377 UTC for +$196.33 after filling 1.28782 BTC. The second entered at
20:20:16.759 UTC and completed at 21:04:57.933 UTC for +$541.30 after filling
3.58330 BTC. The different quantities are consequences of public queue and
partial-fill evidence, not an extra sizing rule.

Evidence coverage was 7,373 L2 snapshots, 228,320 public trades, 38,735
mark/oracle observations, and ten hourly funding settlements. Maximum L2 gap
was 7.103 seconds; four explicitly recorded reconnect gaps were present, with
a 2.607-second maximum. The 6-second execution freshness contract produced no
actionable uncertainty annotations.

## Regime-alignment evidence

The still-running faithful backend entered a short at 2026-07-30 01:00 UTC.
The pinned source's completed 00:55 bar was RANGE / RG_NORMAL_VOL at 0.35
confidence. The candidate therefore would not have entered that position. This
is direct forward evidence that source-authoritative entry removes a concrete
canonical/source mismatch; it does not prove every excluded canonical trade
would lose.

Across 373 completed shadow bars through 03:55 UTC, strict source labels and
canonical backend labels disagreed on 221 bars. The two detectors are
materially different. The candidate resolves this at the execution boundary by
making the pinned source state authoritative rather than blending contradictory
entry states.

## Replay-parity correction

The research replay helper used a 3-second default event-age limit while the
actual inherited shadow profile is pinned to 6 seconds. A failing regression
test reproduced the mismatch. The shared source-follow constant and both
portfolio/lifecycle replay paths now use 6 seconds; focused tests passed.

The full continuous development replay was rerun with the corrected contract:

| Metric | Prior 3s helper | Runtime-parity 6s |
|---|---:|---:|
| Final equity | $36,243.91 | $36,408.76 |
| Net PnL | +$21,243.91 | +$21,408.76 |
| Completed trades | 114 | 114 |
| Targets / time exits / liquidations | 100 / 2 / 12 | 100 / 2 / 12 |
| Partial liquidations | 43 | 43 |
| Profit factor | 1.427616 | 1.427555 |
| Maximum drawdown | -51.03% | -51.14% |
| Maker / taker fees | $9,771.99 / $1,317.11 | $9,844.58 / $1,326.85 |
| Funding cashflow | +$730.96 | +$737.16 |

Thirty-nine lifecycles changed quantity, funding, PnL, or one of three exit
timestamps after the compounded path first diverged. Every trade status stayed
the same. The +$164.86 equity change is therefore economically near-neutral:
PF is effectively unchanged and drawdown is 0.11 percentage point worse. This
fix raises implementation confidence, not strategy-confidence by itself.

## Uncertainties, risks, and failure modes

- Statistical confidence in the fresh result is low: two trades cannot
  estimate a stationary win rate, PF, loss tail, or daily-income distribution.
- Historical edge confidence is medium: the corrected continuous development
  path remains profitable after friction, but the 12-bps floor was selected on
  development evidence and drawdown remains about -51%.
- Implementation confidence is high for the local replayed path: native event
  coverage passed, funding/oracle counters are clean, the runtime freshness
  contract is now shared, and focused tests pass.
- Public L2 cannot expose private cancellations or exact private queue rank.
- The old faithful backend currently has an open position. Restarting it now
  would interrupt that lifecycle and contaminate the preserved comparison.

The lead is weakened or rejected if a fresh unchanged source-follow shadow
sample reaches PF at or below 1 after friction, produces liquidation/drawdown
outside its historical envelope, shows materially worse real fill timing than
the live-tape replay, drifts from the pinned source labels, or disagrees with
its ledger/TUI accounting.

## Recommendation and trade-offs

| Option | Evidence value | Main cost | Recommendation |
|---|---|---|---|
| Keep old faithful backend | Preserves current lifecycle only | Continues known canonical/source mismatch | Only until flat |
| Cut over while old position is open | Starts candidate sooner | Breaks lifecycle continuity and comparison | Reject |
| Flat-only source-follow shadow cutover | Collects independent candidate evidence | Requires more time/trades | Recommended next action |
| Enable live capital | Tests private execution directly | Current sample is statistically insufficient | Reject now |
| Grant ML authority | Could alter selection | No validated incremental edge | Keep observe-only |

Good enough for the next phase means an explicit flat-only restart into the
unchanged source-follow lead, correct backend/TUI identity, no-submit honesty,
and continued immutable collection. It does not mean the requested income is
proven.

## Immutable evidence and verification

- Fresh live-tape replay:
  `data/logs/research/hypervelocity_source_minrange12_live_tape_20260729T1700_20260730T0400_20260730.json`
  (SHA-256
  `35fe7190b61d438b38f964e217b295744779488dbb8083b925babc057ef10ef6`).
- Corrected continuous replay:
  `data/logs/research/hypervelocity_source_production_minrange12_continuous_runtime6s_20250728_20260418_20260730.json`
  (SHA-256
  `db223085f8c0ff747373376b2a3d40869d56a2a1dd7cfa7a9ade426041d436e9`).
- Pinned labels through 04:00 UTC:
  `data/logs/research/hypertrader_current_ad15_btc_5m_labels_through_20260730T0400.parquet`
  (SHA-256
  `b4950e30d009319eb971797144ceaad3e0dfc90e77b2ad836483e976da9e7416`).
- Repository non-network Python verification: 1,450 passed, 4 deselected.
- Rust/TUI verification: 34 passed.
- Focused Ruff and changed-file whitespace verification: passed with no
  findings.
