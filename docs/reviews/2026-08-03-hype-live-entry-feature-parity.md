# HYPE live entry-feature parity — 2026-08-03

## Problem and observed evidence

The broad one-year HYPE breakout control and the current live sample disagree.
The historical control completed 1,011 development trades, produced a 0.891
profit factor, lost 7,625.83 net basis points after the declared cost model,
and had one positive chronological fold out of five. The current compatible
live history has only three closed HYPE trades, two wins, one loss, $0.908059
net PnL, and a descriptive 5.055 profit factor. The live result is encouraging
but is not enough evidence to infer a profitable regime or a repaired signal.

The live provider previously retained only the breakout onset, structural
direction, regime states, and confidence diagnostic. It did not retain the 17
causal signal-time features used by the frozen historical entry attribution.
Consequently, the journal could not determine whether the live trades came
from a materially different part of the historical setup distribution.

## Implemented evidence bridge

Fresh HYPE provider evaluations now carry the same 17 definitions used by
`hype_breakout_entry_attribution_development_v1_20260803`:

- directional SMA and EMA gaps, RSI distance, and 5/15/60-minute returns;
- current and prior-15-minute BBWP measurements;
- breakout and trailing-20-minute volume ratios;
- signal-bar range/body and 20-minute breakout clearance;
- 1-minute and 15-minute directional alignment; and
- regime movement strength.

The provider requests 60 prior completed one-minute decisions solely to build
this feature window. Missing history, a candle gap, neutral direction, or an
unavailable source produces an explicit unavailable status with null feature
values. None of those statuses changes signal eligibility.

The Setup inspector renders a compact HYPE entry-attribution block with body,
clearance, range, volume, BBWP, prior return, alignment, gap, and RSI evidence.
Older ledgers render no inferred block. The rolling research checkpoint can
consume the numeric metrics through its existing provider-metric diagnostics.

## Authority and balance contract

- `entry_feature_authority=report_only`
- no model was trained;
- no threshold was selected;
- no entry, exit, routing, size, leverage, stop, or timer changed; and
- the approximate account balance is not an eligibility or evidence gate.

The running backend was not restarted because an accepted, venue-stop-protected
HYPE lifecycle remains open. The new feature rows begin only after the next
safe backend start; no current or historical row is backfilled by inference.

## Validation

A real-bar parity probe used the final HYPE breakout event in a 10,000-minute
venue-cached window. Every one of the 17 live values matched the frozen
historical feature builder exactly; maximum absolute delta was zero. Focused
Python provider, decision-source, and poller tests passed. Rust unit coverage
binds the compact report-only inspector output. Ruff, Rustfmt, Clippy with
warnings denied, and whitespace validation passed. The full non-network Python
suite passed with 3,180 tests and four intentional deselections; the complete
Rust/TUI suite also passed.

## Confidence, failure modes, and falsifiers

Confidence is high in feature-definition parity because synthetic and real-bar
comparisons agree exactly. Confidence remains low in HYPE economic edge because
three closed live trades are not an adequate effective sample, and the broad
historical control was negative.

The implementation would be falsified by any nonzero live-versus-historical
feature delta on the same completed candles, a fresh eligible HYPE onset missing
the measured feature contract despite 60 contiguous minutes, a report-only
status changing a routed action, or the TUI displaying values absent from the
backend row. Additional live trades returning toward the historical negative
distribution would update the favorable current assessment.

The next decision is evidence-driven: accumulate fresh feature-attributed HYPE
outcomes, compare them by exact provider and side, and only then evaluate a
predeclared challenger. This is not a reason to withhold otherwise executable
signals under the ungated-execution charter.
