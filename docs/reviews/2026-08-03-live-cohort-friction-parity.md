# Live cohort modeled-versus-runtime friction parity

Date: 2026-08-03

## 1. Problem restatement

The shared live cohort combines four signal providers behind one execution and
position manager. A live fill is useful strategy evidence only when the live
entry and exit mechanics are explicitly compared with the mechanics used by
the cited research result. This audit adds that comparison without changing
signals, routing, sizing, exits, orders, or the open BTC and HYPE positions.

Success means every configured provider-symbol mapping has a typed research
contract, a typed runtime contract, exact difference labels, and owned-fill
cost observations when available. The report remains descriptive: parity does
not establish profitability, and mismatch does not automatically block a
trial under `SRS_HV1_NO_GATES`.

## 2. Current evidence

The checkpoint generated at `2026-08-03T18:18:34.390321+00:00` covered all ten
configured provider-symbol mappings:

| Provider | Symbols | Runtime shape | Exact differences |
|---|---:|---|---|
| HYPE breakout onset | HYPE | mismatch | fixed 8h research hold versus live extension while regime-supported, hard-capped at 24h |
| BTC Source Follow | BTC | mismatch | maker versus taker entry; research has no stop versus the live 80-bps safety overlay |
| Range Onset | BTC/ETH/SOL/HYPE | aligned | none: 60-bps stop, 48h hold, no target |
| Hulk Expansion | BTC/ETH/SOL/HYPE | aligned | none: structural 20-75-bps stop, 24h hold, 3R maker target |

The shared live adapter submits market IOC entries for every provider. The
observed entry sample remains small:

| Provider | Entry fills | Mean fee | Mean slippage | Mean acknowledgement |
|---|---:|---:|---:|---:|
| HYPE breakout onset | 3 | 4.3198 bps | 0.7044 bps | 1267.7 ms |
| BTC Source Follow | 2 | 4.3198 bps | -0.5386 bps | 1218.5 ms |

For HYPE, the research contract modeled 4.5-bps fees and 2-bps slippage per
side, so these three entries are within that nominal cost shape. That does not
validate the signal edge. For Source Follow, the modeled entry was post-only
maker at 1.5 bps and zero fixed slippage; the two live entries instead averaged
about 4.32 bps and -0.54 bps signed slippage. Its 26.6667-bps maker target and
24h hold are present in the current provider contract, but the entry liquidity
and added venue-native safety stop remain different from the cited replay.

## 3. Implementation and visibility

- `cohort_friction_contracts.py` resolves typed research mechanics and each
  provider's configured execution plan. `cohort_friction_parity.py` compares
  those shapes and groups owned entry fills by exact provider and symbol.
- The rolling live checkpoint publishes the result under
  `audit.execution.friction_parity` with report-only, no-gate, no-retune, and
  no-execution authority.
- TUI Screen 6 shows aggregate aligned/mismatched counts and an `EXEC` column.
  Selecting a row and pressing Enter shows model/live entry liquidity, fees,
  slippage, acknowledgement latency, stop, hold, target, mismatch labels, and
  evidence source.
- Older checkpoints without the new section remain readable and render parity
  as unavailable rather than inferred.

The bounded read-only checkpoint was regenerated on the new code. The order
backend was not restarted. At verification, one BTC long remained open and
venue-stop protected, with zero backend faults.

## 4. Recommendation and trade-offs

Do not pool these fills into one claim that the historical strategies were
validated live. Eight provider-symbol runtime shapes match their cited
research, but most have no live fills and none has enough live outcomes to
establish edge. Source Follow and HYPE remain explicit mechanical challengers.

Before the next flat restart, choose one explicit correction per provider:

1. Reproduce the cited provider mechanics in the shared runtime, retaining a
   separately justified live safety invariant where required; or
2. freeze the current shared runtime contract and run one bounded, exact
   replay so its signal evidence is evaluated under the mechanics actually
   being traded.

The first option maximizes fidelity to earlier research but may conflict with
the venue-stop safety invariant. The second preserves the present live engine,
but prior performance numbers must not be cited as matched evidence for the two
remaining mismatches. Doing nothing preserves ongoing data collection while
keeping those differences visible.

Confidence is high in the current configured contract comparison because it is
derived from typed research configurations and the provider execution payload.
Confidence is low in the observed cost distribution because only five
attributed entries exist. A bound plan on a historical lifecycle that predates
the current profile, a different adapter, or additional fills materially
changing the cost distribution would update the assessment.

## 5. Verification

- 3,066 non-network Python tests passed; four were intentionally deselected.
- All 141 Rust/TUI tests passed.
- Strict Clippy, Rust formatting, Ruff, and focused parity tests passed.
- The regenerated checkpoint rendered `8/10 ALIGNED`, `2 MISMATCH`, with exact
  provider-plan provenance on all ten rows.
