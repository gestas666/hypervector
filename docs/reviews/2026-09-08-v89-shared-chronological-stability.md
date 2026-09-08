# V89 shared portfolio: chronological stability

The later 20 historical days lose money in every retained source and cost case.
With recorded-native candle substitutions and adverse slippage, the earlier
28 days earn **$183.56**, the later 20 days lose **$87.44**, and the full 48 days
earn **$96.12**. HYPE contributes **−$71.47** to the later loss. These are modeled
shared-account results, not realized live returns.

Confidence is high in the bounded arithmetic: daily contributions reconcile to
the previously saved marked equity, and the frozen source replay reproduces the
report exactly. Confidence is low in a causal regime-change interpretation:
both partitions have already been explored, the sample is short, and execution
and historical-source limitations remain.

## Question and frozen comparison

This study attributes the existing seven-asset paths over the original
noncrypto screening split. It does not rerun a parameter search or reset the
portfolio at the split:

- Development: July 21 through August 18, 2026, 28 complete UTC days.
- Extension: August 18 through September 7, 2026, 20 complete UTC days.
- Initial marked equity: $4,857.58724349; existing cash, positions, configured
  size caps, funding, fees, marks and event order are carried across August 18.
- Sources: archive, first recorded candle version and latest recorded version.
- Costs: nominal, adverse slippage and full HIP-3 fee stress.
- Exit clocks: recorded bar clock and late intrabar exit, retained separately.

The 18 source/cost/clock combinations are sensitivity controls, not independent
samples. First and latest recorded-source period statistics agree exactly.
The full-fee case is a historical stress assumption; current fee metadata does
not establish which fee applied throughout the past window.

## Results

Recorded-bar-clock net PnL in USD; both exit-clock cases remain in the machine
report. First/latest recorded-source columns are identical.

| Cost | Archive: first 28 days | Archive: later 20 days | Recorded: first 28 days | Recorded: later 20 days |
|---|---:|---:|---:|---:|
| Nominal | +215.26 | −42.65 | +215.30 | −17.89 |
| Adverse slippage | +183.51 | −63.66 | +183.56 | −87.44 |
| Full HIP-3 fee stress | +104.05 | −113.50 | +104.09 | −137.28 |

The recorded/adverse development period opens at $4,857.59 and closes at
$5,041.15. The extension carries that $5,041.15 forward and closes at $4,953.71.
Its return is −1.73%; its maximum close-mark drawdown is $198.69, or 3.91%,
including interior event rows. This drawdown is not a liquidation stress test.

| Recorded/adverse contribution | First 28 days | Later 20 days |
|---|---:|---:|
| BTC | +11.35 | −7.25 |
| ETH | −5.26 | −3.73 |
| HYPE | −27.79 | −71.47 |
| SOL | +6.32 | −3.56 |
| Brent | +26.09 | +6.77 |
| SNDK | +147.44 | −26.59 |
| SPCX | +25.40 | +18.39 |
| Four crypto assets | −15.38 | −86.00 |
| Three noncrypto assets | +198.94 | −1.43 |

The extension has ten positive and ten negative marked days. Ten of its
20 days have at least two losing assets. Maximum marked concurrency is four
positions; maximum reserved margin is $333.33 in that partition and $400.00
over the full path. These observations do not justify increasing live size.

Across all 48 days, subtracting the three largest positive marked-day
contributions changes recorded/adverse net from +$96.12 to **−$77.62**.
This is concentration arithmetic, not removal of trades from a new simulation.
The earlier source study's separate largest-three-trades subtraction is
−$132.11; the two quantities have different definitions.

## Evidence and verification

Inputs are registered against a frozen read-only DuckDB inventory of the two
existing September 7 shared studies. Both original journal records match their
database-registered bytes and SHA-256. Every report, daily attribution and marked
path used by this study matches its prior journal and declared report checksum.

The analysis preserves duplicate event timestamps when measuring drawdown and
uses cumulative equity differences at UTC boundaries. Ending marks/events use
the period convention `(start, end]`. All 48 daily boundaries reconcile; maximum
absolute residual is **9.094947017729282e−13 USD**, below the declared 1e−8 USD
numerical tolerance. The initial and final numerical reports also agree exactly.

Source revision: `634a33ee5cdd6aeee60f14d27e51e0faee830031`, isolated in
`/Users/gestas/Prototypes/hypervector-v89-storage-spcx-20260908`.

**54 tests pass** in both the working source and extracted archive with network
access denied. Tests plus real replay cover 186/188 statements and 60/62
branches, 98.4% combined. The pure attribution module covers 77/77 statements
and 26/26 branches. The wrapper's two uncovered lines are its existing-output
guard and module-entry guard. The initial CLI separately exercised the latter.
Ruff, formatting, source size/function limits, annotations and docstrings pass.

The **5,036 archive members** are verified; 5,035 tracked files match the source
commit, with one additional offline verification harness. The archive replay
reproduces the final report exactly.

Evidence is under the main repository's
`data/logs/research/bidirectional_cohort/v89_chronological_stability_20260908_v1/`:
`validation_final/replay/report.json`, `validation_archive/`,
`archive_replay_result.json`, `source_commit_parity.json`, `source_manifest.json`
and `source.tar.gz`. The immutable journal pins inputs and verification outputs.

## Correction to the preceding research plan

The HYPE compression audit's proposed follow-up incorrectly said a seven-asset
shared-account comparison was missing. The older annual cache does end July 27,
but newer 48-day inputs and completed shared studies already existed in another
worktree and DuckDB. Their 61 and 139 evidence references were rechecked without
changed or missing files. Eight corresponding review/journal documents are now
copied byte-for-byte into the main and current research worktrees.

The duplicate proposal `v89_seven_asset_common_window_joint_marking_v1` is
withdrawn. This chronological attribution addresses a remaining question in
the existing study. Revision 2 of the HYPE journal corrects only its follow-up;
the measured 907-publication input parity result remains unchanged.

## Disposition and next investigation

Retain the descriptive result. No live change follows from this study.
Historical gaps, hybrid native histories, candle revisions, modeled fills,
funding-mark proxies and the absence of client-time executable quote evidence
limit any profitability conclusion. A changed input checksum, boundary error,
failed equity reconciliation or independently reproduced different result would
falsify the bounded calculation. An untouched future sample is needed to assess
whether the observed deterioration persists.

The highest-value next investigation is
`v89_hype_aug26_executable_price_reconstruction_v1`: examine historical book and
trade evidence around the first 02:25:21 UTC publication on August 26 for the
already identified source-sensitive HYPE long. Compare observable ask-side depth
at the frozen modeled size against nominal/adverse entry prices and the later
stop-switch sensitivity. Inventory existing evidence first; acquire a bounded
unsigned archive window only if needed. Do not infer an actual missed live order
or fabricate local receipt times. Quotes alone cannot prove achievable fills or
client latency. No sealed prospective outcomes are required.

| Research option | Value and trade-off | Disposition |
|---|---|---|
| Leave the source-sensitive entry unqualified | No work; retains a known execution-price assumption | Lower priority |
| Reconstruct historical executable prices | Tests the largest identified cost-sensitive event; latency remains uncertain | Next investigation |
| Tune or remove HYPE from these losses | Changes the strategy after observing a short sample | No proposal on this evidence |

See the [current V89 research index](../research-journal/v89-current-index.md)
before choosing another experiment. No new human clarification is required to
continue the research-only investigation.
