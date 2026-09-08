# V89 quarter-hour entry comparison

Do not promote the faster-entry proposal. In the explored 48-day window it
increased shared-account trades from 177 to 200, while reducing net PnL under
all three cost assumptions and increasing drawdown. Confidence is high for
this reproduced conditional comparison, but low for extrapolating either
strategy's future profitability. The live configuration remains unchanged.

## Hypothesis and fixed comparison

The predeclared hypothesis was that completed 15-minute entries against the
existing completed-hour channels might capture useful moves earlier. SNDK
retained its 20/10 channels; Brent retained 8/4. Both retained ATR20, two-ATR
structural stops, the 20–250 bps stop clamps, hourly exits, 24-hour maximum hold,
10x leverage and $500 notional cap. The other five portfolio routes stayed fixed.
The exact protocol was committed before viewing results as `c7569f4`.

Channels stay fixed throughout each hour and exclude that hour. ATR uses only
hours completed by the entry decision. A signal can fill at the following
quarter's open; a current quarter's close cannot fill earlier in that same bar.
The candidate retains the baseline's complete hourly exit columns, including
hourly opposite-entry exits. It does not introduce quarter-hour reversals.

Inputs are the previously frozen native 15-minute candles and hourly funding.
July 19–21 supplies warmup; July 21–September 7 is the continuous evaluation.
July 21–August 18 and August 18–September 7 are separate descriptive slices.
These periods have been examined previously and are not untouched holdouts.
All 36 asset/variant/cost/window cases were retained.

## Results after costs

Per-side costs are 2.5 bps slippage plus 0.9 bps fee for nominal, 5.5 plus 0.9
for adverse, and 5.5 plus 9.0 for the historical full-fee sensitivity. Current
growth-mode fee observations were not substituted throughout past history.

| Shared account, 48 days | Hourly baseline | Quarter-entry candidate |
| --- | ---: | ---: |
| Trades | 177 | 200 |
| Trades per calendar day | 3.6875 | 4.1667 |
| Nominal net | $197.42 | $167.57 |
| Adverse net | $96.12 | $59.91 |
| Full-fee sensitivity net | -$33.18 | -$87.40 |
| Adverse close-mark drawdown magnitude | 3.91% | 5.02% |
| Adverse win rate | 40.68% | 36.00% |
| Adverse net excluding largest winner | $4.77 | -$48.72 |
| Adverse net excluding three largest winners | -$132.11 | -$216.47 |

Both recorded-native core source revisions and both declared intrabar exit
clocks were retained: 12 candidate shared scenarios compared with the 12
existing baselines. Their aggregate net comparisons agree; detailed source
and timing differences remain in the artifacts. Shared capacity stayed within
the frozen sizes: maximum concurrent positions four, maximum reserved margin
$400, no notional mismatches and positive unreserved cash at every marked point.
This validates the fixed-size accounting assumption on these paths, not an
unconditional claim about future account capacity.

| Adverse cost, continuous | Baseline trades / net | Candidate trades / net |
| --- | ---: | ---: |
| SNDK | 47 / $120.85 | 53 / $172.57 |
| Brent | 61 / $32.86 | 78 / -$55.07 |

The favorable SNDK aggregate is insufficient to select it. In the later 20-day
slice, SNDK worsened from -$24.93 to -$77.16; Brent worsened from $6.25 to
-$11.52. The candidate loses after removing its three largest winners on each
asset's continuous adverse case: SNDK -$103.81, Brent -$126.67. SNDK's candidate
adverse win rate was 28.30%, versus 31.91% for baseline; Brent's was 25.64%,
versus 32.79%. Higher trade frequency did not produce a higher win rate.

The SNDK candidate adds 109 and removes 55 exact timestamp/side signals, retaining
34. Brent adds 198, removes 97 and retains 33. These are signal identities, not
independent filled opportunities. Position occupancy and lifecycle exits limit
the actual increase to six SNDK trades and seventeen Brent trades.

## Validation and evidence corrections

- All six previously published continuous asset/cost baselines reproduced exactly.
- Thirty-seven focused tests pass. The new signal module has 100% statement and
  branch coverage. Ruff and whitespace checks pass.
- Twenty-two real-input prefix comparisons preserve every value exactly. All
  19,200 hourly exit field values match the baseline across the two asset grids.
- Ninety-eight declared source references match their hashes. There are zero
  source or capacity mismatches.
- All 1,434 modeled trade records across the overlapping 36 cases reconcile
  gross PnL, fees and funding to net PnL and enter at the next quarter's open.
  These repeated records are not 1,434 independent trades.
- Independent daily attribution reconciles all twelve shared scenarios; the
  largest absolute residual is approximately $1.27e-12.

The first comparison attempt rejected equal Python tuples and persisted JSON
arrays. The verifier now compares their JSON values without rounding numbers;
a regression test still rejects a 1e-12 numerical change. This was a verifier
representation error, not a changed baseline trade.

The first signal export used the existing index-free Parquet writer and omitted
the full timestamp index. That export cannot establish inactive-row identities.
The separate v3 export reconstructs the same signals, writes timestamps as an
explicit column, and proves every old value remains exactly equal after the
same serialization. The old economic reports and generators remain immutable.
Arrow's string dtype conversion is normalized only for the prefix comparator's
two text fields; numeric, boolean and timestamp comparisons remain exact.

Research source commit: `1dc57ec`, isolated in
`/Users/gestas/Prototypes/hypervector-v89-quarter-entry-20260908`.
Reproduction from that checkout uses `PYTHONPATH=src:scripts` and the original
workspace's `.venv/bin/python`, in this order:

1. `scripts/v89_quarter_entry_comparison.py --output-dir <unused directory>`
2. `scripts/v89_quarter_entry_shared.py --output-dir <unused directory>`
3. `scripts/v89_quarter_entry_signal_export.py`
4. `scripts/v89_quarter_entry_acceptance.py`

The last three scripts bind the documented immutable input/output names. For a
fresh end-to-end rerun, use an isolated source copy with new matching artifact
names rather than overwriting the original evidence. The timestamp repair is
an explicit required follow-on export; the frozen original generator is retained
for provenance. These are research scripts, not installed live provider code.

Authoritative artifacts under the original workspace's
`data/logs/research/bidirectional_cohort/` are:

- `v89_quarter_entry_comparison_20260908_v2/report.json`
- `v89_quarter_entry_shared_20260908_v1/report.json`
- `v89_quarter_entry_signal_exports_20260908_v3/manifest.json`
- `v89_quarter_entry_acceptance_20260908_v1.json`
- `v89_quarter_final_tests_20260908_v1.log`

## Runtime observation and next decision

A frozen 02:22:33 UTC checkpoint records two open live longs, no closes and zero
faults: SNDK 0.276 at 1803.4, and SPCX 3.34 at 149.7. SPCX filled at
02:00:22.492 UTC, with stop 538846363686 accepted and later present in the
checkpoint. SNDK's first funding settlement is recorded. The bounded SPCX
ledger bytes and selected entry events are preserved in
`v89_quarter_runtime_20260908_v1`. These remain provisional open lifecycles;
their final exit, total costs and net returns are not yet known.

| Alternative | Evidence and trade-off | Decision |
| --- | --- | --- |
| Keep current hourly entries | Preserves the measured baseline; sparse live evidence remains | Current runtime |
| Change both routes to quarter entries | More trades, lower net and larger drawdown in every cost scenario | Reject this proposal |
| Select SNDK from the favorable full-period result | Later-period deterioration and winner concentration remain | No live recommendation |
| Freeze a prospective comparison | Collects new causal evidence with fixed rules, requiring elapsed market time | Next research step |

The single highest-value independent next action is implementing read-only
capture for the frozen prospective block before its start, as specified in
`docs/research/v89-quarter-entry-prospective-20260908.md`. Actual live lifecycle
reconciliation remains event-driven when a position closes.

Conditional candle fills, mark proxies, historical fee regimes, intrabar order
and publication-time uncertainty limit economic confidence. A changed source
hash, prefix instability or accounting mismatch invalidates this technical
comparison. New fixed-rule prospective evidence can update the economic
rejection; another fit on the same history cannot supply independent confirmation.

No live change is recommended and no approval is requested. No execution
process, route, leverage, sizing or TUI binary changed in this experiment.
Rollback means using the unchanged baseline; research evidence is retained.
This goal turn made progress. The broader objective remains active.
