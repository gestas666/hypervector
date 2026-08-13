# Cohort runtime risk-utilization review — 2026-08-04

## Problem and success criteria

The effective cohort position sizing was not directly visible. The backend
profile reported a `3%` margin fraction and a `$25` maximum notional, while the
operator needed to know which term actually controlled entries. Success
requires a read-only, backend-derived projection that:

1. distinguishes configured from effective margin;
2. identifies a binding notional cap without calling it a strategy gate;
3. uses no performance, balance, or promotion threshold;
4. cannot alter sizing or execution; and
5. remains unavailable rather than inventing missing evidence.

## Authoritative inputs and calculation

The checkpoint reads the selected run's latest `configuration_identity` and
`cohort_snapshot`. For each configured asset it applies the same entry-plan
shape as the live adapter:

```text
uncapped notional = account value * margin fraction * leverage
planned notional  = min(uncapped notional, configured maximum notional)
planned margin    = planned notional / leverage
```

At the 2026-08-04 00:58 EDT checkpoint, account value was `$504.32520149`.
BTC, ETH, SOL, and HYPE each configured `3%`, `5x`, and `$25`, yielding:

| Measure | Per asset | Four-position envelope |
|---|---:|---:|
| Uncapped requested notional | `$75.6488` | `$302.5951` |
| Planned entry notional | `$25.00` | `$100.00` |
| Planned entry margin | `$5.00` | `$20.00` |
| Effective margin fraction | `0.9914%` | `3.9657%` |

The four-position figure is a configured maximum envelope, not current margin
usage or a strategy recommendation. Actual marked notional can differ after
quantity rounding and price movement; the open HYPE position was about
`$25.08` at visual inspection.

## Authority and failure behavior

The evidence contract is fixed to:

- `report_only=true`
- `execution_authority=none`
- `performance_gate=false`
- `automatic_sizing_change=false`

Python rejects missing run identity/snapshot data, invalid numeric values,
invalid position capacity, and duplicate asset symbols. Rust independently
validates the contract, every arithmetic identity, asset counts, binding-cap
counts, and the simultaneous-margin summary. Invalid evidence makes the
checkpoint unavailable; the TUI does not calculate a fallback.

The approximate funded balance is an input to arithmetic only. It is not a
hard gate, promotion requirement, or eligibility threshold. The explicit
`$25` notional limit is a separate configuration field.

## Validation evidence

- Six focused Python risk-utilization tests passed, including duplicate and
  invalid-value rejection.
- Checkpoint integration tests passed for all four configured assets.
- Eleven Rust checkpoint tests passed, including rejection of evidence that
  claims performance-gate authority.
- TUI tests passed for selected-asset sizing and dashboard capacity.
- A real 165x50 monitor rendered the backend-authored values on Screens 1 and
  9.
- The full non-network Python suite passed `3,193` tests with four intentional
  deselections; the complete Rust/TUI suite and strict Clippy passed.
- Monitor exit preserved live backend PIDs `24037/24038` and HYPE venue stop
  OID `509351056418`.

## Confidence, limitations, and falsifiers

**High confidence** that the display accurately projects the current runtime
formula and profile because the Python calculation, independent Rust
validation, rendered TUI, and live checkpoint values agree.

This does not prove that the current sizing is economically optimal. It also
does not predict exact filled notional after venue size rounding, price
movement, fees, funding, or partial fills.

The projection would be falsified by any of the following:

- a future entry plan produced by the same runtime profile does not use the
  displayed `$25` cap before venue rounding;
- the TUI differs from the checkpoint JSON for the same generation;
- a missing or malformed checkpoint produces a numeric sizing value;
- the evidence filters, pauses, promotes, resizes, or otherwise changes a
  strategy; or
- any `$500`-style balance threshold appears in strategy eligibility.

The next sizing decision should be provider-specific and evidence-backed. A
global increase would scale providers with materially different live and
historical evidence, so this review changes visibility only.

## Provider-specific next-run staging

The provider-symbol control surface is now implemented and the disk profile
stages one isolated allocation experiment:

| Provider-symbol | Margin fraction | Notional cap | Planned notional at $504.30 | Planned margin | Effective margin |
|---|---:|---:|---:|---:|---:|
| Hulk/SOL | 3% | $25 | $25 | $5 | 0.99% |
| Range-Onset/SOL | 10% | $75 | $75 | $15 | 2.97% |

The SOL asset adapter ceiling is `$75`, but Hulk/SOL has an explicit `$25`
provider override. This prevents the adapter-ceiling increase from silently
scaling Hulk. Other assets and providers retain their prior `$25` plan.

This is a sizing experiment, not a strategy gate. Both directions and all ten
configured provider-symbol execution mappings remain enabled. The rationale is
medium-confidence historical evidence for the exact Range-Onset/SOL mapping;
it does not prove forward profitability. A stopped-run audit showing worse
after-cost SOL outcomes at the larger size, materially worse slippage, or
unacceptable shared-account interaction would falsify the staged allocation.

The running backend still carries the older profile and remains untouched while
HYPE is open. Configuration-generation telemetry reports the disk overrides
separately with no restart or execution authority. Activation requires a later
verified flat/no-orders restart; it is not triggered by account balance.

Fresh verification after staging passed `3,202` non-network Python tests with
four intentional deselections, the complete Rust/TUI suite, strict Clippy,
Ruff, Rustfmt, and whitespace checks. A real 165x50 monitor selected
Range-Onset/SOL and displayed its running `$25` plan separately from the
next-run `10%/$75` override with `RESTART REQUIRED`. Monitor exit left backend
PIDs `24037/24038` and venue stop OID `509351056418` unchanged.

## First live activation-boundary observation

At `2026-08-04T05:45:12.230Z`, the protected HYPE long crossed its configured
eight-hour soft deadline. The running backend did not restart or apply the
staged sizing profile. It retained the position under its persisted
`extend_while_regime_supported` contract because the latest completed-bar
structure support score was `0.9167` in the position direction. Exact venue
stop OID `509351056418` remained present, reduce-only, and matched the full
`0.46` position. The unconditional hard deadline remains 24 hours after entry.

This event confirms that profile activation is governed by the lifecycle-safe
flat/no-orders boundary rather than account value. It does not establish that
the extension policy has positive expectancy. The only prior resolved
same-context challenger is one HYPE trade, positive at each measured
5/15/30/60-minute horizon; that sample is too small for a stable conclusion.
The current lifecycle's eventual exact exit, incremental path after the soft
deadline, fee, funding, and slippage evidence will update that assessment.
