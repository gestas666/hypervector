# HIP-3 live episode and re-entry attribution review

## Problem restatement

The offline HIP-3 timing trial found that limiting the SPCX state recipe to one
entry per alignment episode removed four nominal and five stress development
stop losses, but validation economics were unchanged. The missing evidence was
whether routed live entries actually repeat inside one causal provider episode.

This review measures that identity from the live ledger. It does not change a
provider, profile, route, entry, exit, size, leverage, order, or running process.

## Causal contract

- Scope: the two deployed HIP-3 Swing providers only.
- Clock: each provider's recorded completed 15-minute decision.
- Episode onset: the first causally available aligned provider state after an
  observed non-aligned state, profile change, or missing decision boundary.
- Onset recipe persistence: `fresh_entry_onset_absent` alone retains an active
  alignment episode; a native component blocker ends it.
- Warmup handling: `indicator_warmup` is an explicit technical continuity
  boundary, not an inferred market state.
- Restart handling: identical profile and consecutive decision evidence may
  continue an episode across a process restart; profile changes cannot.
- Entry ordinal: chronological reflected live lifecycle count inside the exact
  episode. Hypothetical missed entries are excluded.
- Economics: resolved trades only. Open marks remain separately provisional.
- Authority: report-only with no automatic promotion or execution gate.

## Measured live prefix

The immutable v25 audit contains 810 matching provider rows and 810 unique
completed decisions. All matching rows were classifiable. Fourteen rows were
explicit `indicator_warmup` boundaries. The classified sequence contained ten
episodes and no episode crossed a process restart in this observed prefix.

Three resolved HIP-3 Swing trades were attributable:

| Provider-symbol-side | Entries | First | Repeat | Net USD | PF | Net ex largest winner |
|---|---:|---:|---:|---:|---:|---:|
| SPCX long | 2 | 2 | 0 | +$0.910830 | 2.3866 | -$0.656872 |
| GOLD long | 1 | 1 | 0 | -$0.242433 | 0.0000 | -$0.242433 |
| Total | 3 | 3 | 0 | +$0.668397 | 1.7432 | -$0.899305 |

The positive aggregate is concentrated in one SPCX winner. Removing the
largest winner makes the three-trade total negative. This is descriptive
execution evidence, not confirmation of a repeatable edge.

Two current open HIP-3 lifecycles were separately attributable as first
entries: GOLD long and SNDK short. At the audit snapshot their combined marked
net PnL was negative, but those marks are unresolved and are not included in
the resolved table or decision.

## Decision

1. Keep the current v25 timing unchanged.
2. Keep the SPCX one-entry-per-alignment-episode arm annotation-only.
3. Do not promote a cooldown from this prefix because no resolved live repeat
   entry occurred; the core live comparison is still unobserved.
4. Continue recording exact episode identity and ordinal on future audits.
5. Reassess only after both first and repeat entries have resolved, retaining
   side, profile, friction, and largest-winner sensitivity.
6. Keep the rejected one-bar confirmation and fast-EMA pullback arms rejected;
   this live prefix provides no contradictory evidence for them.

## Confidence, risks, and falsifiers

Confidence is high that the three resolved and two open reflected lifecycles
were attached to exact causal decisions in this audit: provider-row
unavailability was zero and every lifecycle matched its source run, decision,
side, and profile. Confidence is low that live repeat-entry economics are known:
the measured repeat sample is exactly zero.

The SPCX onset candidate gains support if independent future repeat entries are
after-cost losers while first entries retain better economics without relying
on one winner. It is falsified if repeat entries are profitable after costs,
capture winners unavailable to first entries, or prove to be separate provider
episodes. Any missing source decision, changed evidence byte, profile mixing,
open/closed PnL pooling, or execution authority invalidates the attribution.

The 91 all-history routing records without an `evaluations` array remain an
audit limitation. They do not create an unavailable matching HIP-3 row in this
prefix, but they prevent a claim that every historical routing cycle contained
provider telemetry.
