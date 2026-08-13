# Hypervelocity 30x Shadow Promotion Review

Date: 2026-07-29

## Correction: sizing evidence does not validate the canonical runtime stream

The allocation/leverage surface in this review uses the selective
`source-follow-session-06-15-confidence-70` short entry stream. The faithful
runtime uses a distinct 24/7 bidirectional canonical 5m regime stream. My
earlier treatment of the source-follow 70%/30x result as sufficient evidence
for a clean canonical-runtime shadow promotion was incorrect. Matching sizing,
target, and execution mechanics do not make different entry streams equivalent.

A new one-year causal bar screen tested the actual canonical entry stream with
one shared $15,000 BTC portfolio and the same maker fee/funding contract:

| Canonical profile | Completed | Liquidations | PF | Final equity | Max DD |
|---|---:|---:|---:|---:|---:|
| 50% / 30x | 1,568 | 188 | 0.933 | approximately $0 | -100% |
| 70% / 30x | 1,568 | 188 | 0.931 | approximately $0 | -100% |
| 70% / 40x control | 2,186 | 307 | 0.675 | approximately $0 | -100% |

The screen is not executable L2 evidence and includes 160 explicitly marked
gap-fill minutes, so it cannot establish maker fill probability. It is still a
strong falsifier of the claim that changing only canonical sizing to 30x
creates positive economics. The active 40x shadow run independently produced
six completed lifecycles, three targets, one verified liquidation, two
unverified legacy liquidation labels, and -$1,924.03 net after costs.

Within the shared 70%/30x screen, long trades attributed PF 1.178 and
+$14,721.14, while shorts attributed PF 0.782 and -$29,721.14. Those figures
are path-dependent attribution from a bidirectional portfolio, not standalone
long/short strategies. They justify a bounded direction-isolation experiment;
they do not justify promotion.

Revised confidence: high that the current canonical bidirectional entry stream
is not validated by the profitable source-follow risk surface; medium that
direction isolation is the next useful challenger. A causal L2 direction split
that contradicts the bar attribution would update the latter assessment.

## Problem restatement

The operational question was whether the 70%-margin, 40x isolated BTC
Hypervelocity contract should remain the shadow baseline or be replaced by a
configuration that better preserves the source-follow maker edge after fees,
funding, capacity, and liquidation. The required output is one coherent
backend/TUI contract suitable for a fresh continuous shadow falsification.

The economic floor is +$50,000 net from a $15,000 starting portfolio over a
trailing-year sensitivity. +$100,000 net remains the preferred objective.
Reset-block products are reported as sensitivities, not as a claim that a
continuous portfolio achieved either objective.

## Frozen experiment

- BTC Hyperliquid public L2 and trade-through maker evidence.
- Twelve independently reset gap-free blocks from 2025-07-28 through
  2026-04-18; archive gaps are excluded rather than interpolated.
- Untouched holdout from 2026-04-18 through 2026-04-28.
- Initial equity: $15,000 per block.
- Source-follow 06:00-15:00 UTC, confidence at least 70%.
- Post-only maker entries, 60-second eligibility, one position per symbol,
  isolated margin, authentic funding and mark context, and an 8% gross-margin
  target.
- Allocation surface: 50%, 70%, and 100%; leverage surface: 10x, 20x, 30x,
  and 40x.

Public trade-through proves that public volume crossed the displayed price; it
does not reveal private queue rank. Every block resets equity because the
archive does not contain a continuous gap-free annual tape.

## Selected development results

| Candidate | Fills | Targets | Liquidations | Positive blocks | PF | Worst DD | Reset-block PnL | Product ending |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 70% / 40x control | 48 | 44 | 3 | 9/12 | 2.16 | -74.53% | +$16,749.72 | $24,213.93 |
| 50% / 30x | 63 | 60 | 1 | 11/12 | 5.69 | -41.37% | +$28,170.43 | $73,982.63 |
| 70% / 30x | 55 | 52 | 1 | 11/12 | 4.97 | -55.40% | +$33,602.55 | $88,098.56 |

The 70%/30x candidate is the return leader. Relative to 70%/40x, it restored
seven fills, reduced full liquidations from three to one, increased positive
blocks from nine to eleven, improved profit factor from 2.16 to 4.97, and
reduced worst drawdown by 19.14 percentage points. Its median block PnL was
+$3,217.30; its worst block was -$5,775.47.

The 50%/30x candidate is the lower-tail alternative. It produced a lower
product ending balance but improved worst drawdown to -41.37% and profit factor
to 5.69. Both 30x candidates clear the +$50,000 net floor in this sensitivity;
neither clears the +$100,000 preferred objective.

## Cross-block robustness audit

A separate immutable audit pooled completed-trade economics without stitching
portfolio state across archive gaps. The 70%/30x development population
contains 54 completed trades: 52 targets, one 24-hour time-exit loss, and one
liquidation. Gross winning PnL was $43,552.23 versus $8,755.88 of gross losses.
The observed losing-trade rate was 3.70%; the empirical break-even loss rate
given the measured average win and loss was 16.06%.

The two-sided 95% Wilson upper bound on the losing-trade rate was 12.54%, below
the measured break-even rate. This is favorable finite-sample evidence, not a
claim of stationarity: Wilson coverage assumes approximately independent,
homogeneous binary outcomes. Regime clustering, candidate selection, and
private maker-queue uncertainty can make the interval optimistic.

The result is distributed rather than one-trade dominated:

- the largest profitable trade contributed 2.85% of gross winning PnL;
- the largest profitable block contributed 27.43% of positive block PnL;
- 11 of 12 reset blocks were profitable; and
- every leave-one-block-out product remained above the $15,000 start.

The weakest leave-one-block-out ending was $51,217.39. That remains profitable
but represents only +$36,217.39, so the +$50,000 annual floor does not survive
removal of the strongest block. This is the clearest remaining economic
weakness before forward shadow evidence.

| Candidate | Completed | Wins/Losses | 95% loss-rate upper | Break-even loss rate | Bound below break-even | LOO minimum | Worst DD |
|---|---:|---:|---:|---:|---|---:|---:|
| 50% / 30x | 62 | 60 / 2 | 11.02% | 15.95% | yes | $50,084.30 | -41.37% |
| 70% / 30x | 54 | 52 / 2 | 12.54% | 16.06% | yes | $51,217.39 | -55.40% |
| 70% / 40x | 47 | 44 / 3 | 17.16% | 12.84% | no | $15,122.30 | -74.53% |

The comparison strengthens rejection of 70%/40x. It does not reverse the
shadow selection: 70%/30x remains the return candidate, while 50%/30x remains
the explicit lower-tail alternative. A fresh continuous window showing loss
frequency above 16%, persistent maker-fill conversion failure, or clustered
losses that invalidate the homogeneous-rate approximation would update this
assessment.

## Holdout

The untouched holdout contained one fill and four canceled entries. The fill
reached its target for every selected candidate:

- 70%/30x: +$740.91, -6.39% maximum drawdown;
- 50%/30x: +$529.22, -4.57% maximum drawdown; and
- 70%/40x: +$707.84, -8.52% maximum drawdown.

Including this sparse holdout raises the 70%/30x product sensitivity to
$92,450.13 and the 50%/30x sensitivity to $76,592.86. The holdout is
non-inferior but cannot establish robustness with only one trade.

## Exit-overlay result

A +7% activation / 55%-of-peak lock was replayed only on the surviving 30x
candidates. It is rejected:

- 70%/30x product ending fell from $88,098.56 to $71,920.32;
- profit factor fell from 4.97 to 4.48;
- reset-block PnL fell by $4,316.87;
- worst drawdown and liquidation count did not improve; and
- all six peak exits reduced their block result or left it unchanged.

The report-only peak observer may remain enabled to collect falsification data,
but it has no execution authority. A daily profit lockout is also not promoted:
the observed liquidation was the only trade on its day, while same-day repeat
entries contributed later target winners.

## Source-follow sizing decision

Retain one source-follow sizing candidate for further comparison:

- 70% of current positive equity as isolated margin;
- $15,000 configured initial cash for a newly reset shadow ledger; a normal
  resume retains the durable ledger's original initial cash and equity;
- 30x strategy leverage, with BTC venue maximum leverage retained at 40x for
  maintenance-tier calculations;
- 21x equity notional;
- 8% gross-margin target, equal to a 0.2666667% unlevered price move before
  tick rounding;
- no execution stop or peak lock;
- regime-reset same-direction re-entry; and
- ML metalabel authority remains observe-only.

The configuration, Python contract, Nautilus defaults, sizing, portfolio
fingerprint, strategy registry, and TUI fallback/title currently share that
30x contract. This implementation coherence is not evidence of canonical
profitability. Do not activate it as a validated edge until the entry-stream
mismatch is resolved. The existing 40x backend process remains unchanged in
memory.

## Validation and falsification

Focused promotion tests passed 52 Python checks. The broader affected suite
passed 768 Python tests, and the complete TUI suite passed 33 Rust integration
tests. Full repository verification remains the final pre-restart gate.

Confidence is medium. The direction and size of the 30x improvement repeat
across eleven positive blocks, but the tape is discontinuous, the source clock
window is selected, the holdout has one trade, and public data cannot establish
private queue position.

The candidate is falsified for promotion if a fresh continuous shadow window
shows materially worse fill conversion than the public trade-through replay,
profit factor below one after fees and funding, repeated liquidation behavior,
or a drawdown path inconsistent with the 30x improvement. Queue misses and
maker-order timing must be attributed explicitly rather than hidden as generic
strategy losses.

## Evidence

- Development surface:
  `data/logs/research/hypervelocity_maker_risk_surface_equity15k_gapfree_*_trade_through_20260729.json`
- Selected peak comparison:
  `data/logs/research/hypervelocity_maker_selected_peak7_equity15k_gapfree_*_trade_through_20260729.json`
- Untouched holdout:
  `data/logs/research/hypervelocity_maker_selected_peak7_equity15k_holdout_20260418_20260428_trade_through_20260729.json`
- 50%/30x robustness decision:
  `data/logs/research/hypervelocity_maker_alloc50_lev30_robustness_decision_20260729.json`
  (SHA-256 `1e1f229b305fff7c7d5fc1ed599572dcc4f0ae2c90bbc5cedcc182936ef77861`).
- 70%/30x robustness decision:
  `data/logs/research/hypervelocity_maker_alloc70_lev30_robustness_decision_20260729.json`
  (SHA-256 `1cf6796e150d29d43cd3472e3e0308a423c10cca2d8035b153564af26e75512a`).
- 70%/40x robustness decision:
  `data/logs/research/hypervelocity_maker_alloc70_lev40_control_robustness_decision_20260729.json`
  (SHA-256 `2e52747546f206319c393a1860e5aaf80960f40c6fa7baa8db35b959f8bd6fe5`).
- Canonical one-year sizing screen:
  `data/logs/research/shared_hypervelocity_continuous_20250728_20260728_1m_risk_surface_v1.json`
  (SHA-256 `efbadea1ea84e2ad7718ad2a4da5cb5b8bc453c2030120df14fa7d4536765592`).
