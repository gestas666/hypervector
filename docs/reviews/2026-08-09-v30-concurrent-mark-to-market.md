# v30 Concurrent Mark-to-Market Review

## Decision

Keep the proposed v30 composition and its 1.00x fixed sizing as the next
flat-boundary candidate. Do not increase leverage or notional from the opened
sensitivity surface. Do not activate, restart, drain, or mutate live v25 from
this report.

Confidence in the accounting result is high: all 169 accepted lifecycle
cashflows reconcile, terminal equity matches the prior realized ledger, all
required mark paths are present, and the focused tests pass. Confidence that
the candidate will retain a positive live edge is medium-low because the source
windows are opened, asynchronous, and selection-contaminated.

## Fixed candidate

| Route | Symbol | Notional | Leverage | Sides |
|---|---:|---:|---:|---|
| Range Onset | SOL | $75 | 5x | long + short |
| Dual-MTF Range Onset | ETH | $25 | 5x | long + short |
| Swing/HA | xyz:SPCX | $75 | 5x | long + short |

The shared account remains $500, one position per symbol, three positions
maximum. The test changed no signal, route, priority, stop, live order, or live
profile.

## Results

### Proposed 1.00x sizing

| Window | Trades | Net | PF | Close-mark DD | Adverse intrabar DD |
|---|---:|---:|---:|---:|---:|
| Full opened source union | 169 | +$65.75 | 2.27 | -2.37% | -2.40% |
| Opened final common, 2026-07-06 to 2026-07-21 UTC | 29 | +$5.09 | 1.45 | -1.83% | -1.86% |

The full union contained 37 wins and 132 losses. Its positive result therefore
depends on asymmetric winner size rather than a high win rate. The prior lean
comparison reported +$50.34 after removing the single largest winner, so one
trade did not create the entire result.

### Fixed sizing sensitivity

| Multiplier | Full net | Full adverse DD | Final-common net | Final-common adverse DD |
|---:|---:|---:|---:|---:|
| 0.50x | +$32.89 | -1.27% | +$2.56 | -0.94% |
| 0.75x | +$49.33 | -1.85% | +$3.83 | -1.40% |
| 1.00x | +$65.75 | -2.40% | +$5.09 | -1.86% |
| 1.25x | +$82.17 | -2.92% | +$6.34 | -2.32% |
| 1.50x | +$98.58 | -3.41% | +$7.59 | -2.78% |
| 2.00x | +$131.37 | -4.32% | +$10.06 | -3.69% |

These rows are mechanical exposure sensitivity, not independent strategy
evidence. Returns and drawdown rising together does not validate 2.00x. The
recent common window has only 29 trades and no sealed holdout, so the extra
notional would amplify selection error as readily as edge.

## Coverage and reconciliation

- 157 full-window lifecycles contain completed intratrade marks.
- 12 full-window lifecycles are exact immediate same-bar exits normalized to a
  one-millisecond causal duration. Their exact realized stop losses are included.
- 27 of 29 final-common lifecycles contain completed intratrade marks; the other
  two are the same immediate-exit class.
- Zero non-instant lifecycles are missing required marks.
- Maximum simultaneous positions is three.
- The 1.00x terminal equity is $565.752716, matching the accepted realized
  ledger within substantially less than one cent.

## Defect correction and provenance

The first immutable attempt at `20260809T170500Z` used a separate, lower peak
for the adverse series. That could make adverse drawdown appear less severe
than close-mark drawdown and is invalid for decision use. The
`20260809T172000Z` revision corrected the peak and completed-exit-bar ordering.
The decision artifact `20260809T173000Z` additionally distinguishes immediate
same-bar exits from genuinely missing marks. Earlier artifacts remain
immutable and are explicitly superseded rather than overwritten.

## Failure modes and uncertainty

- SPCX uses verified 0xarchive L2 midpoint OHLC. It is a useful price-path
  proxy, not proof of executable trade prices or private queue position.
- Funding is linearly accrued between entry and exit for the path calculation;
  terminal funding cashflow is exact, but intratrade settlement timing is an
  approximation.
- Bar extremes do not establish sub-bar event order. Stop gaps and live IOC
  friction may exceed the modeled path.
- The full source union mixes different route start dates. Only the final-common
  comparison places all three routes in the same 15-day interval.
- Every route was selected using opened evidence. Positive results may be
  selection bias rather than durable edge.

The sizing assessment would be falsified or reduced by live stop gaps outside
the source lifecycle assumptions, unreconciled venue fees or funding, a live
adverse excursion materially beyond the 1.00x path, or a prospective block
showing that the recent PF advantage does not repeat. Those observations remain
reported trial outcomes under `SRS_HV1_NO_GATES`; they are not hidden execution
abort gates.

## Recommended next actions

1. Preserve v25 until the account is flat and order-free.
2. At that boundary, prepare a byte-identified v30 profile containing only the
   three fixed routes above. Activation still requires explicit live authority.
3. Start v30 at 1.00x: SOL $75, ETH $25, SPCX $75, all at 5x. Do not promote a
   larger multiplier from this opened surface.
4. Reconcile every live close, fee, funding settlement, stop, and maximum
   adverse excursion. Review after each five closes or 72 hours, whichever
   occurs first; treat the review as measurement, not an implicit gate.
5. Derive the next cadence challenger from reconciled missed-opportunity and
   route journals. Do not revive the rejected one-minute shock family or buy
   another venue dataset merely to retune that failed contract.

## Evidence

- Decision artifact:
  `data/logs/research/lean_successor_concurrent_mtm_20260809T173000Z.json`
  (`3757b8874dc6a17cbc34f801632502a72f5510b0878145bb62adb7a0b0abf5c1`)
- Baseline path sidecar:
  `data/logs/research/lean_successor_concurrent_mtm_20260809T173000Z.parquet`
  (`e5468bc673f7508e7ca421adf9910538876bdb0dd14f83d8b5901739c133930b`)
- Predeclared plan:
  `docs/plans/2026-08-09-v30-concurrent-mark-to-market.md`
- Realized-ledger comparison:
  `data/logs/research/lean_successor_portfolio_comparison_20260809T161609Z.json`
