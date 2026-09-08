# V89 quarter-hour entry comparison implementation plan

**Goal:** Measure one faster-entry challenger for SNDK and BRENTOIL against
their existing hourly Donchian routes, with unchanged exits and sizing.

**Architecture:** Add a research-only signal builder using existing completed
hour resampling, ATR, lifecycle simulation and shared-account replay. Keep the
live configuration and execution processes unchanged. Preserve all results,
including negative cases, in immutable source-backed artifacts.

**Tech stack:** Python, pandas, pytest, existing Hypervector research modules,
local native Hyperliquid candles/funding and recorded core lifecycle evidence.

## Frozen experiment, before viewing results

- Only SNDK 20/10 and BRENTOIL 8/4 channel lengths are tested. Both directions
  remain available. No threshold, channel-length or allocation search.
- At each completed 15-minute close, compare price with the preceding N complete
  hours before that quarter's containing hour. The channel stays fixed within
  the hour, including its final quarter, matching the hourly baseline's channel.
- A fresh false-to-true quarter-hour breakout can enter at the following open.
  Continuous breakout states do not repeatedly emit entries. Gaps reset onset
  continuity; incomplete current-hour prefixes cannot create an entry.
- ATR20 uses only hours completed by that decision. Intermediate quarters use
  the prior completed hour's ATR; the final quarter may use its now-completed
  hour. Structural stops retain 2 ATR and existing 20–250 bps clamps.
- Preserve both baseline hourly exit columns exactly, including opposite-side
  hourly entry exits. No new quarter-hour reversal or exit instruction.
- Preserve the existing $500 notional cap, 2% margin fraction, 10x leverage,
  24-hour maximum hold and current fee/funding accounting. No live deployment.
- Reuse July 19–September 7 frozen native 15-minute OHLC and hourly funding.
  July 19–21 is warmup. Report July 21–August 18, August 18–September 7 and the
  continuous July 21–September 7 interval. All have been inspected previously;
  none is an untouched holdout or a forecast.
- Three per-side costs: nominal 2.5 bps slippage + 0.9 bps fee; adverse 5.5 +
  0.9; full-fee sensitivity 5.5 + 9.0. No favorable live-fill cost adjustment.
- Retain 36 asset/variant/cost/window cells. Report signals, executed trades,
  cadence, net win rate/payoffs, fees/funding, drawdown, side results, censoring,
  same-bar ambiguity and removal of the largest one and three winners.
- Propagate continuous cases through the existing exact seven-asset shared
  account with other routes fixed. Retain both recorded-native core revisions
  and both declared intrabar exit clocks; report attribution and overlap.

## Task 1: Test timing and source isolation

Create `tests/test_quarter_hour_donchian_entries.py`. Use hand-computable long
and short paths, an early breakout that reverses before the hourly close,
continuous states, a missing quarter, invalid grids/configs, all input prefixes
and a deliberately extreme future hourly high. Assert existing hourly exits
remain byte-equivalent and a modeled entry occurs at the next open.

Run with the original `.venv/bin/python -m pytest` and `PYTHONPATH=src`;
observe the missing-builder failure before implementation.

## Task 2: Implement and validate the research builder

Create `src/hypervector/research/quarter_hour_donchian_entries.py`. Reuse public
completed-bar primitives and the baseline builder. Derive channels from rolling
completed-hour highs/lows within contiguous segments, then join each quarter to
its explicit prior-hour identity. Test the new module and existing hourly and
four-hour builders, then run Ruff and coverage. Keep functions under 50 lines.

## Task 3: Run and reconcile the frozen comparison

Create `scripts/v89_quarter_entry_comparison.py`, reusing the current cost,
window, activity and shared-marking machinery. Validate exact source hashes and
baseline reproduction before interpreting differences. Write signals, complete
trade records, summaries and all provenance without rounding detailed floats.
Add focused tests for runner selection/identity and integration invariants.

## Task 4: Review and journal

Record results and recommendation in
`docs/reviews/2026-09-08-v89-quarter-entry-comparison.md` and an immutable
research-journal revision. Verify evidence hashes and append sequentially to
the local research database. Commit only this experiment. The next untouched
prospective block is required before any apparent development improvement can
be treated as confirmation. Define its frozen start/end after this exploratory
comparison, without inspecting that block first.

## Limits, falsifiers and rollback

Conditional candle execution lacks native latency, depth and intrabar ordering.
Historical fee modes and first-publication candle identity remain uncertain.
More trades may increase losses and costs. Prefix instability, changed baseline
exits, missing source coverage or unreconciled accounting invalidates the
experiment. Economic failure is a retained result, not a technical abort.

Confidence starts low for economic benefit. Successful technical validation is
causal reproducibility and complete attribution, not positive PnL. Rollback is
discarding the isolated candidate code while retaining its immutable evidence;
there is no runtime state to roll back. Prior goal turn: progress. Goal active.
