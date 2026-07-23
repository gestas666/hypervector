# hypervector safety policy (agents)

## Live arming ladder

```text
live-check (safe) 
  → secrets_present bool, can_start, start_gate
live-run without flags 
  → refused
live-run --enabled 
  → still refused without arm + secrets
live-run --enabled --i-accept-live-risk + secrets
  → may place on mainnet within max_notional_usd
```

**Never** suggest disabling fail-closed checks. **Never** log private keys.

## Paper honesty

- Paper path never constructs live exec client for place.
- `submitted` should be false/absent on paper/shadow fills.
- Order intents may exist with `submit_enabled=false`.

## Path isolation

| Ledger | Path |
|--------|------|
| Paper decisions | `<data-root>/paper/decisions/decisions.jsonl` |
| Live decisions | `<data-root>/live/decisions/decisions.jsonl` |

Reports and TUI must refuse cross-ledger paths.

## TUI

Read-only monitor. No arm, no place, no secret display. See design SRS_HV5_*.

## When user asks to "go live"

1. Run `live-check` and show readiness JSON (redact any accidental secrets).
2. Confirm max notional, export path, and explicit risk acceptance.
3. Only then construct `live-run` command with both arm flags.
4. Prefer small `--max-live-bars` smoke first if available.
