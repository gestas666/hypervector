# HYPE profit-retention audit

**Decision timestamp:** 2026-08-05 12:57 EDT  
**Strategy:** `hype_breakout_onset_bidirectional_v1`  
**Execution authority:** report-only; no order, position, stop, staged profile,
or running strategy was changed

## Problem and evidence identity

Separate two materially different exit hypotheses:

1. activate a profit floor/trailing stop before the configured eight-hour soft
   boundary; and
2. begin a trailing exit only after the active policy has extended beyond that
   boundary.

The live checkpoint generated at `2026-08-05T16:56:26.687188+00:00` bound its
cohort evidence to the first `382602786` bytes of
`data/live/bidirectional_cohort/decisions.jsonl`, SHA-256
`7ee9d0fc81c1aafabc9e8ab121d0e1a439392877d400b97136b72b05dc022ffa`.
It independently bound the first `61330379` bytes of the HYPE asset ledger to
SHA-256
`32d7f2169d7cf68fc008bd43be4799b0c8242f4af6ab7cb0e40819e13dabc5eb`.
Both prefix hashes were reproduced directly before this decision was written.

Historical mechanism evidence comes from
`data/logs/research/hype_breakout_profit_protection_development_v2_20260803.json`,
SHA-256
`98cc915687fe4c7f17476514ad45689cdc4b9d86274874175cdc711dfe08545c`.

## Pre-eight-hour profit locks

All six reconciled canonical HYPE closes were eligible for the same three
frozen profit-lock policies. Actual net PnL was `$2.099489`.

| Policy | Activation / floor / trail | Triggered | Estimated net | Delta vs actual | PF |
|---|---|---:|---:|---:|---:|
| `a25_floor15_trail10` | 25 / 15 / 10 bps | 5/6 | `$0.137787` | `-$1.961702` | `1.6154` |
| `a40_floor15_trail20` | 40 / 15 / 20 bps | 5/6 | `$0.134087` | `-$1.965402` | `1.5988` |
| `a60_floor15_trail30` | 60 / 15 / 30 bps | 5/6 | `$0.417465` | `-$1.682024` | `2.8644` |

The independent development replay agrees on mechanism direction. Against the
generic eight-hour control (`1011` trades, PF `0.8911`, `-7625.83` bps), the
three profit-lock shapes produced PF `0.5255`, `0.6237`, and `0.7265` and net
results of `-18815.22`, `-18482.62`, and `-15603.10` bps. The matched-entry
diagnostic also left every challenger below the same control. The control being
negative does not validate the entry strategy; it only makes the relative
failure of these exit mechanisms explicit.

### Decision

Reject these three pre-soft profit-lock policies for canonical HYPE. They cut
the current live winners materially and failed to improve the broader
development control. This rejection is policy-specific: it does not establish
that every possible profit-protection rule is harmful.

**Confidence: medium.** The live result is sparse, but all three mechanisms
lose substantial value in the live sample and the direction is corroborated by
the much larger development replay. A prospectively frozen policy that improves
after-cost results across multiple non-adjacent live windows without increasing
loss concentration would update this decision.

## Post-eight-hour trails

Only two canonical HYPE lifecycles extended beyond the soft boundary, both
long. Their actual extended exits totaled `$0.961388`; the estimated fixed
eight-hour exits totaled `$1.249790`.

| Post-soft giveback | Triggered | Estimated net | Delta vs actual | Delta vs fixed 8h |
|---|---:|---:|---:|---:|
| 20 bps | 2/2 | `$1.413389` | `+$0.452001` | `+$0.163599` |
| 30 bps | 2/2 | `$1.363808` | `+$0.402420` | `+$0.114018` |
| 40 bps | 2/2 | `$1.312744` | `+$0.351356` | `+$0.062954` |

The 20-bps trail beat the actual extended exit in both lifecycles, but it beat
the fixed eight-hour estimate in only one. All estimates use prior completed
one-minute extrema, reuse each actual exit's fill/reference ratio and fee rate,
and cannot reconstruct intraminute ordering.

### Decision

Keep the 20/30/40-bps post-soft trails as report-only observers. Do not promote
one to an executable candidate from two long-side counterfactuals. A post-soft
trail and the staged fixed-eight-hour profile are mutually exclusive: a fixed
exit ends the lifecycle before a post-soft trail can operate.

**Confidence: low.** The aggregate ordering favors 20 bps, but `N=2`, one side,
and counterfactual fills are too weak for execution authority. Repeated
profile-matched long and short extensions where one frozen trail beats the
fixed boundary per lifecycle after costs would increase confidence. Failure to
beat fixed eight hours across new extensions would reject it.

## Current open lifecycle and non-interference

At the evidence boundary, `HYPE:510653043774` was an open protected long before
its soft deadline. It had approximately `214.90` bps completed-bar MFE,
`66.10` bps peak giveback, and estimated exit-now net PnL of `$0.349303`.
Its venue stop remained `56.131328` under OID `510653123467`; estimated net at
that stop was `-$0.220107`. The open post-soft observers correctly remained
`pending_soft_deadline`.

This provisional path exposes profit-giveback risk but is not a resolved
counterfactual and does not authorize a hot stop change. The backend remained
on active profile fingerprint
`c992cb2f958ed607d25d6be76a52a37070278061c0e8c186723dc574e6938f6b`,
while the separately staged fixed-eight-hour profile retained SHA-256
`5015b0b55e0737dfcd1b8d19c443a7d7d70ea82b88ae588401dc63b8feab7158`.

## Validation and failure modes

- Continue exact live measurement of actual exits, fees, funding, slippage,
  MFE, MAE, and all frozen counterfactuals.
- Do not combine an entry, allocation, and exit change in one causal claim.
- Treat live process windows as operational provenance, not independent market
  samples.
- Refuse any live transition without venue-flat state, zero owned orders, an
  independently verified prestart bundle, and explicit live authority.
- Rebuild this audit if either cited ledger prefix fails its recorded hash.
