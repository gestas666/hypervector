# Source-follow paired live-tape review — 2026-07-30

## Problem restatement and success criteria

The experiment asks whether the development-selected `TD_WEAK_CHOPPY`
half-sizing rule improves a source-authoritative Hypervelocity portfolio on
fresh Hyperliquid evidence. Both arms must receive identical source decisions,
L2, trades, mark/oracle observations, funding, fees, latency, queue state, and
exit rules. Only signal-level allocation may differ. The active shadow backend
must remain unchanged and no order may be placed.

## Known facts and assumptions

- Source: pinned Hypertrader revision
  `ad15f2bdc949619be495a5f516babd08f7f52a90`.
- Signal: completed-5m `TREND_DOWN` onset, confidence at least 0.70,
  completed-bar range 12-100 bps, short, 24/7.
- Portfolio: $15,000, 50% isolated margin, 30x, one BTC position.
- Exit: 8% gross-margin target, no fixed stop, 24-hour maximum hold.
- Execution: public displayed queue, 50 ms submit/cancel latency, maker/taker
  fees, authentic hourly funding, isolated liquidation, and recorded receive
  timestamps.
- ML remains observe-only and has no filtering, sizing, or execution authority.
- Window: 2026-07-29 17:00 UTC through 2026-07-30 08:30 UTC.

## Technical validation

The prior 26,850-label prefix was compared against the extension. Primary and
secondary labels, confirmed and raw confidence, and availability timestamps
were identical. Of the diagnostic `volume_ratio` values, 19,329 differed only
below `8e-14`. The old terminal 05:25 bar differed by 0.0138 because its live
trade volume had not fully arrived when the earlier artifact was generated;
its classification and confidence did not change. The new terminal 08:25 bar
was imported after more than four minutes of recorder buffer.

Live replay coverage contained 10,389 L2 snapshots, 260,377 public trades,
54,598 mark/oracle observations, and 15 funding settlements. Maximum L2 and
context gaps were 14.266 and 13.219 seconds. Six recorded reconnect gaps were
present; the largest was 13.661 seconds. Context rows sharing one exchange
millisecond were deterministically resolved by latest receive timestamp after
a regression test reproduced the prior duplicate rejection.

Recorded receipt lag exposed clock skew that the earlier exchange-time proxy
hid. There were 8,548 trades with negative lag, 14 trades above six seconds,
and one book above six seconds. The production matcher therefore emitted
29,926 fail-closed uncertainty cycles. The two selected lifecycles were
unchanged, but this uncertainty is retained rather than smoothed away.

## Paired result

| Metric | Uniform | `TD_WEAK_CHOPPY` half | Scaled minus uniform |
|---|---:|---:|---:|
| Initial equity | $15,000.00 | $15,000.00 | $0.00 |
| Final equity | $15,737.63 | $15,466.76 | -$270.87 |
| Signals / targets | 2 / 2 | 2 / 2 | 0 / 0 |
| Liquidations / time exits | 0 / 0 | 0 / 0 | 0 / 0 |
| Maximum marked drawdown | -8.59% | -8.59% | 0.00 pp |
| Maker fees | $92.89 | $58.75 | -$34.15 |
| Funding cashflow | +$1.15 | +$0.71 | -$0.43 |

The first signal was `TD_EXHAUSTION` and stayed full-sized in both arms. The
second was `TD_WEAK_CHOPPY`; half-sizing reduced its net target profit from
$541.30 to $270.43. It completed earlier because the smaller target quantity
consumed less public trade flow. Both arms ended flat.

No additional qualified source onset occurred after 20:20 UTC. In particular,
the candidate remained flat at 01:00 UTC when the old faithful backend entered
the still-open adverse short. The source completed 00:55 bar was `RANGE` at
0.35 confidence. This is one forward avoided-entry observation, not proof that
all such exclusions are profitable.

## Uncertainties, risks, and falsifiers

- Strategy-confidence is low: two completed trades cannot estimate stable PF,
  loss tails, or daily income.
- Regime-boundary confidence is low-to-medium: two targets plus one avoided
  adverse entry agree with the candidate hypothesis, but one later losing
  source-qualified trade would materially change the sample.
- Half-sizing confidence is low and mixed. It improved development PF/drawdown,
  but reduced profit without drawdown benefit in this forward window.
- Implementation confidence is medium-to-high for report-only replay: focused
  tests cover receive timestamps, duplicate context resolution, causal signal
  selection, and UTC boundaries. Clock skew remains unresolved operationally.
- Private cancellations and exact private queue rank remain unobservable.

The source candidate is weakened if unchanged forward collection reaches PF at
or below 1 after friction, its excluded faithful entries outperform included
source entries, or ledger/TUI state disagrees with replayed execution. The
half-sizing rule is weakened if additional `TD_WEAK_CHOPPY` trades remain
profitable without materially larger loss tails at full size. NTP-synchronized
recording with no negative receipt lag would update the clock-skew assessment.

## Recommendation and trade-offs

| Option | Evidence value | Risk | Recommendation |
|---|---|---|---|
| Keep old faithful indefinitely | Preserves current lifecycle | Known source/backend regime mismatch | No |
| Interrupt the open faithful short | Starts candidate sooner | Contaminates lifecycle evidence | No |
| Flat-only source-authoritative uniform shadow | Tests the strongest fresh signal | Still statistically sparse | Recommended after flat |
| Promote half-sizing to runtime | Tests lower historical drawdown | Fresh winner was unnecessarily reduced | Keep paired observer only |
| Enable live capital or ML authority | Tests operational execution | Edge sample remains insufficient | No |

The next good-enough gate is an explicit flat-only source-authoritative shadow
cutover with uniform sizing, while continuing half-sizing as a report-only
paired challenger. Promotion requires materially more resolved forward trades,
clean accounting parity, and no worsening of liquidation or drawdown tails.

## 09:05 UTC extension

An exact incremental checkpoint extended the recorder-backed window by 35
minutes without reclassifying the 90-day prefix. The source stayed confirmed
`RANGE`; its last two raw bars were `TRANSITION`. No new qualified onset was
created, so both paired portfolio results remain unchanged.

The incremental reproduction was checked separately over 05:30-08:30. All
decision-driving fields and all 80 recipe events matched the full-history run
exactly. Extension volume ratios differed by at most 1.6e-15. One preserved
05:25 value differed because that older checkpoint captured incomplete
terminal-bar volume; its regime, subtype, confidence, and event decisions were
unchanged.

The 09:05 paired artifact is
`data/logs/research/hypervelocity_source_live_pair_20260729T1700_20260730T0905_20260730.json`
(SHA-256
`edf01f0ab173d055574139190990f893d83d7c3af51c94b65c52d2a56847ce13`).

## Allocation-only robustness update

The allocation hypothesis was isolated after validating the frozen 24/7
artifact identity. A session-limited 109-signal artifact was rejected; the
accepted continuous control contains the same 285 source signals in every arm.
Signal logic, leverage, target, queue matcher, fees, funding, and liquidation
model were unchanged.

| Margin | Continuous final | PF | Max DD | Targets | Full / partial liquidations |
|---:|---:|---:|---:|---:|---:|
| 25% | $32,237.73 | 1.830 | -27.64% | 108 | 7 / 21 |
| 35% | $39,946.62 | 1.817 | -34.22% | 105 | 10 / 31 |
| 40% | $40,139.28 | 1.679 | -37.70% | 103 | 11 / 37 |
| 50% | $36,408.76 | 1.428 | -51.14% | 100 | 12 / 43 |

The untouched April 18-28 slice was positive at every allocation but contained
only four fills: final equity was $15,872.60 / $16,103.05 / $16,218.90 /
$16,451.84 at 25% / 35% / 40% / 50%, with 4/4 targets and no liquidation.

The recorder-backed pair was rerun at the same four allocations. Every arm
completed 2/2 targets with no liquidation. Final equity was $15,466.76 /
$15,575.02 / $15,629.22 / $15,737.63. Maximum marked drawdown stayed -8.59%
because public trade capacity capped the adverse first lifecycle at the exact
same 1.28782 BTC fill in every arm; this tape therefore cannot estimate how
allocation changes that lifecycle's downside.

Thirty-five percent is the provisional shadow recommendation. Forty percent
earned only $192.66 more over the continuous period while worsening PF,
drawdown, targets, and both liquidation counts. Twenty-five percent is the
safer frontier but retained less return. The distinct inactive configuration is
`configs/hypervelocity_source_follow_minrange12_alloc35_shadow.toml`. It keeps
30x isolated leverage, the 8% target, source-only entry authority, one position,
and ML observe-only. No running process was changed.

Confidence is medium for the historical allocation ordering and low for fresh
performance. Forward PF at or below one, clustered liquidations, poorer real
fill conversion, or backend/TUI accounting disagreement would overturn the
recommendation.

## Immutable evidence

- Paired replay:
  `data/logs/research/hypervelocity_source_live_pair_20260729T1700_20260730T0830_20260730.json`
  (SHA-256
  `028fb9ff4efeef25fef54cc6fdf41bbb053b05766a3314009f669a2d9a944566`).
- Source labels:
  `data/logs/research/hypertrader_current_ad15_btc_5m_labels_through_20260730T0830.parquet`
  (SHA-256
  `256904b351cc3b6bb2a093e6a266803874e3cfc5f5497d0aa4188b4217240b0a`).
- Source metadata:
  `data/logs/research/hypertrader_current_ad15_btc_5m_labels_through_20260730T0830.json`
  (SHA-256
  `b21068e754ef37c1bfcf8d4c47b2e66d8ac38082ad7b96b1de07caf8fb51cbbf`).
