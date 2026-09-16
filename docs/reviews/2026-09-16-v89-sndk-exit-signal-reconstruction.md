# SNDK exit signal reconstruction and retained restart gaps

The September 16 07:00 UTC SNDK short exit matches an independently reconstructed
Donchian predicate: the completed-hour close **1544.8** exceeded the prior
ten-hour high **1544.6**. The prior low was **1516.4**. All 660 constituent
one-minute candles were retained in the current native run before the owned
exit decision. High confidence applies to this retained signal evidence;
it does not establish strategy expectancy or continuous exit management during
the preceding restart gap.

The preceding eleven complete hourly windows, September 15 20:00 through
September 16 06:00 UTC, also match their reported channels and exit sides.
None triggered a short exit. This resolves the original-channel limitation
for the final exit in the [earlier accounting review](2026-09-16-v89-sndk-hourly-exit-reconciliation.md).
That review's reconciled net loss remains **$4.445448**; no new economic result
or hypothetical earlier fill is substituted.

## Coverage and correction

There are 53 recorded evaluations among 60 scheduled quarter-hour decisions
after entry through exit. Seven are absent: September 15 **16:45, 17:00,
17:15, 17:30, 17:45, 18:00 and 18:15 UTC**. The 18:30 evaluation was observed
at **18:42:16.640321** and explicitly labeled `pre_activation_readiness_seed`;
it is not evidence of an active exit check at 18:30. Thus 52 retained
evaluations are outside that startup seed category.

Correction to the earlier progress estimate: the prior run's last cohort
record is a running heartbeat at **16:41:26.485234 UTC**, sequence 605438.
The next run's first retained cohort record is **18:41:51.993041 UTC**,
sequence 605439. The observation gap is **2 hours 25.507807 seconds**.
The roughly 18:30 process start is a different clock and does not shorten
this recorded gap. These adjacent native sequence numbers establish the
retained ledger interval, not the exact process stop time or venue protection
throughout it.

At 19:00, 43 earlier minutes are unavailable, so the exact channel remains
unqualified. Available prior highs already reach **1580.2**, while the close
is **1516.8**. Since adding missing highs cannot lower a maximum, those
retained inputs rule out a short-exit breakout at that hour. The opposite-side
exit and exact full channel are not independently qualified by this bound.

The result explicitly retains `complete_hold_validation=false` and
`continuous_local_exit_handling_qualified=false`. Original ATR initialization,
entry-signal validation, missing 17:00/18:00 decisions and real prospective
study outcomes remain outside the qualified findings.

## Validation and provenance

Two adjacent frozen native prefixes contain **17,577 original records**.
The prior prefix is bytes 4,336,519,850–4,356,500,152; its 2,125 records join
the existing 15,452-record current prefix without a sequence or byte-range
gap. Each selected record is matched to its original line, offset, byte count
and SHA-256 using the previously qualified SPCX authenticator.

There are **478 prior-run** and **1,219 current-run** SNDK candles. All
**240 overlapping candles** agree exactly in OHLCV. The independent exit
calculation uses the previous ten completed hours, excluding the current
completed hour, and strict `close > high` / `close < low` comparisons.
Every complete window requires its full 660-minute grid and causally available
inputs. At the final exit, the latest input is sequence **618730**, observed
**07:00:11.795452 UTC**, preceding owned exit sequence **618732**, observed
**07:00:11.796699 UTC**. Numeric comparison tolerance was fixed at `1e-10`;
the reported final extrema and close match exactly.

**25 offline tests passed.** Negative controls reject changed prices/channels,
wrong sides or identities, missing/duplicated/late candles and evaluations,
altered cadence/scope, cross-run OHLCV disagreement, and contradictions of
partial-history bounds. A separate control changes current-hour highs/lows
and verifies that they cannot move the prior channel. The first additional
partial-history controls exposed two omissions in this offline validator;
both checks were added before final qualification. These were audit defects,
not diagnosed live strategy defects. Failed receipts are retained.

Coverage measured **180/187 statements and 39/40 branches**. The remaining
lines cover CLI result publication, exercised separately by actual sandboxed
runs. Two audits with network and credential-file access denied produced
byte-identical **10,606-byte** results, SHA-256
`d34ac2fbbf1ea672b79393bd1b5fc09aa70d2cbf8c5316a32755fc97d1efdecf`.

Artifacts are in
`data/logs/research/bidirectional_cohort/v89_captured_provider_assembly_20260916_v1/sndk_exit_signal_v1/`.
`verification.json` pins the final implementation, tests and result files.
Journal revision 2 appends this evidence without changing the pinned cash
reconciliation or earlier revision.

## Decision and next investigation

**Recommendation / why now:** retain the verified exit calculation and the
restart gaps as separate findings. This loss alone does not justify changing
the exit channel. The new reconstruction removes one technical uncertainty
while preserving the unobserved interval.

**Applicable regime:** this is a price-channel rule audit for one recorded
short lifecycle, without a regime-specific profitability conclusion.

| Alternative | Benefit | Limitation |
| --- | --- | --- |
| Keep only the prior cash audit | No further work | Leaves the exit predicate unverified |
| Preserve this reconstruction and investigate continuity | Resolves signal arithmetic and identifies exact evidence gaps | Cannot infer missing decisions or private fills |
| Retune the exit from this loss | Changes responsiveness | No validated portfolio or out-of-sample justification |

**Proposed live change:** none. **Expected upside:** better diagnosis and
traceable separation of configured behavior from missing operational evidence.
**Main risks:** incomplete native history, receipt-clock interpretation and
mistaking one lifecycle for evidence of a repeatable edge.

**Validation still required / highest-value next investigation:** correlate
the seven missing evaluations with retained shutdown, startup and inherited
position/protection evidence to bound local exit-management continuity.
The already running full native-source and account comparisons continue;
real prospective study seals remain unchanged.

**Success metrics:** matching authenticated inputs and exact reconstructed
exit predicates, with every unavailable interval reported. **Falsifiers /
rollback triggers:** changed source bytes, inconsistent overlap, later-received
inputs, a different channel or an earlier qualifying verified short exit
reopen this finding. Prior journal revisions provide the preserved audit
history; no trading rollback is implicated.

**Confidence:** high for the specified reconstructed windows and ledger gaps;
unverified for continuous local management, original ATR seed and economic
counterfactuals. **Approval:** no live change is proposed or requested here.
