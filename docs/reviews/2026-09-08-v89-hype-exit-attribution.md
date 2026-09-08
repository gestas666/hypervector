# HYPE: chronological losses by exit mechanism

The recorded-source HYPE sample contains **six modeled longs in 48 days**.
Under nominal costs, four protective stops lose $92.11 while two maximum-hold
exits earn $45.88, leaving **−$46.23 net**. Its price PnL is already **−$31.66
before fees and funding**. Fees therefore do not explain the whole loss.

Confidence is high in this reconciled description and low in a causal regime
shift or future win-rate interpretation. Six trades are a small, already
explored sample. These are simulated outcomes under the current contract,
not six new live trades. No current-strategy PnL or live setting is changed.

## Scope and provenance

This study joins the exact HYPE entries in the existing seven-asset shared-account
replay to their modeled lifecycle reports. It retains all 18 combinations of
archive/first/last source, nominal/adverse/full-HIP-3-fee cost, and recorded/late
intrabar exit clock. These combinations reuse the same events and are not
independent statistical observations.

Entry time, side, entry and exit price, quantity economics, fees, funding, exit
reason and the declared clock transformation must agree. A late intrabar stop
adds 59,999 ms to the recorded stop-bar clock; maximum-hold clocks are retained.
Every HYPE period total reconciles to the earlier shared marked-account study.
No HYPE lifecycle crosses the August 18 partition, so complete-trade attribution
does not misassign carried exposure here. Such a crossing causes an explicit
failure in the implementation.

The window is July 21 through September 7, 2026: first 28 days ending August 18,
then 20 later days. The profile fingerprint is
`39e334fc97f3cbe21bac30e53e91524d6a4cf9727370a0f69bc2d51039667f7a`.
The source reports retain their original fees, funding proxies, candle histories
and fill assumptions. Nothing is refitted or newly backtested.

## Recorded-source results

First and latest recorded-source results agree. USD below; the two exit-clock
variants have identical aggregate HYPE economics in this evidence.

| Cost and period | Trades / wins | Protective stops: count / net | Maximum hold: count / net | Total net |
|---|---:|---:|---:|---:|
| Nominal, first 28 days | 3 / 1 | 2 / −45.91 | 1 / +21.12 | −24.79 |
| Nominal, later 20 days | 3 / 1 | 2 / −46.20 | 1 / +24.76 | −21.44 |
| Adverse, first 28 days | 3 / 1 | 2 / −47.39 | 1 / +19.60 | −27.79 |
| Adverse, later 20 days | 3 / 0 | 3 / −71.47 | 0 / 0.00 | −71.47 |

There are no modeled opposite-signal exits in any retained HYPE case. That
does not establish equivalence between honoring and ignoring provider exits in
other paths. Each nominal partition has the same two-stop/one-maximum-hold mix;
the adverse later-period mix changes because of the August 26 case.

| Full recorded window | Nominal | Adverse |
|---|---:|---:|
| Price PnL before fees/funding | −31.661190 | −84.712486 |
| Fees | −13.485752 | −13.461879 |
| Funding | −1.085273 | −1.081988 |
| Net | **−46.232216** | **−99.256353** |

The full-HIP-3-fee stress leaves HYPE's own costs unchanged and matches the
adverse HYPE result. The archive-source history has five HYPE trades because it
omits the August 26 entry. Its full net is −$71.04 nominal and −$75.53 adverse.
Gross HYPE PnL is negative in every retained scenario.

## Source-sensitive stop and remaining losses

The nominal-to-adverse full-window difference is **−$53.024137**. The August 26
lifecycle accounts for **−$48.536712**, or **91.54%**, of that scenario difference.
Its modeled exit switches from maximum hold to protective stop. This is paired
scenario arithmetic, not a measured deterioration in actual execution.

The [preceding mark study](2026-09-08-v89-hype-mark-trigger.md) leaves that
alternate current-contract trigger unresolved. Its actual V61 profit is not
substituted into the V89 model. Removing the disputed trade as a sensitivity
calculation still leaves the other two later-period adverse HYPE trades at
**−$47.689772**. This subtraction is not a resimulated portfolio.

Recorded candle excursions remain available per trade, with their original
limitations. They do not establish executable peak exits or authorize a
profit-lock change. The evidence supports neither increasing size nor promising
large winners merely because entries are infrequent.

## Validation

Source revision: `aef8172ab53869d595fbf8231987d87165e9dd24`, isolated in
`hypervector-v89-storage-spcx-20260908`.

**22 offline tests pass**; the pure attribution module covers 64/64 statements
and 26/26 branches. Controls reject missing/duplicate joins, conflicting prices,
unsupported costs/clocks/reasons, invalid quantities, inconsistent economics and
cross-boundary lifecycles. An independent Decimal calculation checks 204
trade-period arithmetic instances and all 54 period totals. Initial and final
reports match. All 5,066 source-archive members match committed Git blob identities,
and archive replay reproduces the final report exactly. File/function limits,
annotations, public docstrings, Ruff and formatting pass.

Evidence: `data/logs/research/bidirectional_cohort/v89_hype_exit_attribution_20260908_v1/`.
Different input hashes, wrong joins, a failed marked-total reconciliation or
contrary independent replay would falsify the corresponding result. Denser
historical venue trigger evidence could update the August 26 interpretation;
an untouched future sample is needed for a prospective performance assessment.

## Separate storage observation

The live reporter's research import was observed deferred below its 8 GiB free
space requirement, then resumed automatically. A bounded 180-sample observation
at approximately one-second intervals ran from 13:43:31 through 13:46:35 UTC.
Free space ranged from **12,585,840,640 to 13,032,529,920 bytes**; no sample was
below 8 GiB. The observation captured a successful import at 13:45:03 UTC and
no DuckDB spill files. It did not reproduce the earlier shortage.

Matching `live-ledger-*` temporary files occupied 486,858,752–785,031,168 bytes.
Their ownership is not exhaustively established, and sampling can miss shorter
peaks. The mapped-reader proposal measures physical-write reduction, not net
filesystem allocation. It is not established as a cure for these capacity
swings. Permanent cause remains unresolved; no threshold, reporter or backend
was changed. Evidence is in `v89_disk_pressure_observation_20260908T1344Z/`.

## Disposition and next investigation

| Research option | Evidence and trade-off | Disposition |
|---|---|---|
| Blame fees alone | Price PnL is already negative in every HYPE case | Reject explanation |
| Treat the August 26 modeled stop as verified venue execution | Continuous trigger history is absent | Remains unresolved |
| Fit a new HYPE exit from six explored trades | High selection risk; prior profit-lock studies must be respected | No proposal from this study |
| Audit the two new noncrypto live stop exits | New current-contract execution evidence | Next investigation |

Next: `v89_noncrypto_opening_stop_execution_20260908_v1`. Reconcile the SNDK
short stopped at 13:30:27.920 UTC and SPCX long stopped at 13:32:33.954 UTC on
September 8 against their exact native stop orders, fills, costs and bounded
public trade/book evidence. Separate loss at the configured barrier from
additional stop-fill slippage and fees. Inventory existing evidence before any
unsigned acquisition; do not change execution or inspect sealed prospective
experiment outcomes.
