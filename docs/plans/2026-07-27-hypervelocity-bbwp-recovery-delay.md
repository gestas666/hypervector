# Hypervelocity 1m BBWP Recovery-Delay Plan

**Goal:** Test whether the hard-5m-range candidate fails because entries occur
too soon after 1m compression, while preserving the continuous 5m regime label
and avoiding a 15m hard veto.

**Evidence:** In the hard-range event replay, resolved entries 0-5 causal bars
after 1m BBWP compression completed 68 targets and 18 liquidations (79.1% target
rate). Entries at 6-30 bars completed 185/18 (91.1%), and 31+ completed 117/10
(92.1%). This is post-hoc evidence from the same 90-day window, so confidence is
limited until replay and fresh shadow data agree.

**Architecture:** Apply one report-only timing transformation after the existing
causal classifier. When a 1m BBWP percentile below 25 has been observed, suppress
`entry_direction` for the first six completed 1m bars while preserving
`primary_regime`, `state_5m`, and `structural_direction`. Existing open positions
remain TP-only. No 15m veto, pressure gate, model gate, or runtime change.

## Frozen Comparison

- Control: 5m hard-BBWP RANGE at 25, 300-second re-entry cooldown.
- Challenger: same decisions plus minimum 1m compression recovery age of 6 bars.
- Preserve one position, 70% allocation, 40x isolated leverage, fixed 8% target,
  maker costs, and ML observe-only behavior.
- Report source direction recall, cadence, target/liquidation counts, equity, and
  drawdown. No implicit performance abort.

## Tasks

1. Test a pure causal recovery-delay transformation, missing-history semantics,
   and non-mutation of the control frame.
2. Run serial comparison on the complete 90-day venue candle window.
3. If directionally useful, retain and run complete checksum-verified public
   trade-through replay even if a report-only metric is unfavorable.
4. Attribute event outcomes and require a new venue-matched shadow window before
   any runtime promotion, because the six-bar cutoff was selected post hoc.

## Falsifiers and Risks

- If event equity does not improve over $191.20, the apparent outcome slice did
  not survive path-dependent replay.
- If original direction recall materially worsens, the timing rule diverges from
  source behavior.
- Waiting can miss valid immediate continuations and may lower maker fill rate.
- Historical funding and private queue position remain unavailable; fresh shadow
  evidence is required even after a positive archive result.

## Verification

```bash
uv run pytest tests/test_hypervelocity_bbwp_precedence.py -q
uv run ruff check src/hypervector/research/hypervelocity_bbwp_precedence.py \
  tests/test_hypervelocity_bbwp_precedence.py
```
