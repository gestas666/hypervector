---
name: hypervector-cli
description: >
  Operate the hypervector crypto trading research/ops CLI and read-only TUI correctly.
  Use when running hypervector commands, paper/shadow/live checks, reports, sweeps,
  regime, phase2, exports, data-root layout, fail-closed live policy, or when the user
  mentions hypervector, paper-run, live-run, paper-check, status inventory, or hypervector-tui.
  Slash: /hypervector-cli. Prefer this skill over inventing CLI flags.
---

# hypervector-cli

Expert operator skill for **hypervector** — HL-oriented research → historical → paper/shadow → fail-closed live.

## Hard safety (never violate)

1. **Paper/shadow never places venue orders.** Default mode is `shadow`.
2. **Live is fail-closed.** `live-run` requires `--enabled` **and** `--i-accept-live-risk` **and** secrets env. Do not arm without explicit user request.
3. **Never print secret values** (`HYPERVECTOR_HL_WALLET_ADDRESS`, `HYPERVECTOR_HL_API_PRIVATE_KEY`). Only presence booleans.
4. **Mainnet only** — no testnet path.
5. **Paper ≠ live storage.** Never write paper decisions under `data/live/` or reverse.
6. **TUI is read-only.** Do not expect TUI to start/stop/arm. CLI owns lifecycle.
7. Do **not** integrate neural-trader / `@neural-trader/*` (rejected).

## Invocation

Always from repo root with uv:

```bash
uv run python -m hypervector --data-root data <command> [flags]
```

Global: `--data-root` (default project `data/`). Layout: see `docs/infra-data-layout.md`.

TUI (separate binary):

```bash
cargo run -p hypervector-tui -- --data-root data
# or
./target/release/hypervector-tui --data-root data --tape auto --refresh-ms 1000
```

## Funnel map (pick the right layer)

```text
Research:   history → regime | sweep-up/down → report → export → export-validate
Historical: phase2-check → phase2-run
Paper ops:  paper-check → paper-run → paper-report
Live ops:   live-check → live-run (armed) → live-report
Observe:    status | hypervector-tui
```

## Command cookbook

### Inventory & gates (safe, offline)

| Intent | Command |
|--------|---------|
| Pipeline + honesty | `status` |
| Create I2 dirs | `infra-init` |
| Paper surface flags | `paper-check` |
| Live readiness (no place) | `live-check` [`--enabled`] [`--armed`] [`--max-notional-usd 50`] |
| Paper ledger summary | `paper-report` [`--path …`] [`--last 10`] |
| Live ledger summary | `live-report` [`--path …`] [`--last 10`] |

### Research

| Intent | Command |
|--------|---------|
| Cache bars | `history --symbol BTC --timeframe 1m --lookback 90` |
| Regime metrics | `regime [--fast N] [--slow N] [--export]` |
| Sweep track | `sweep-up` / `sweep-down` (see `--help` for strategy flags) |
| Rank trials | `report [--track NAME]` |
| Best export | `export --track NAME` |
| Validate export | `export-validate --path data/exports/<id> [--strict]` |

### Phase 2 historical

```bash
uv run python -m hypervector phase2-check --path data/exports/<id>
uv run python -m hypervector phase2-run --path data/exports/<id> --lookback 90
# --paper / --live on phase2-run are LEGACY flags — they do NOT switch engines
```

### Paper/shadow daemon (no venue orders)

```bash
uv run python -m hypervector paper-run \
  --path data/exports/<id> \
  --mode shadow \
  --max-live-bars 5 \
  --poll-interval 5
```

- Default `--mode shadow` (mainnet-honest intents, synthetic fills).
- Use `--max-live-bars` for smokes; `--stop-file /tmp/hv.stop` for graceful stop.
- Fill model: `--preferred-fill-model l2_walk_v1`, `--max-book-age-ms 3000`.
- Metalabel: `--metalabel` / `--no-metalabel`.

### Live daemon (dangerous — explicit only)

```bash
# Readiness only (safe):
uv run python -m hypervector live-check

# Place path — ONLY with user instruction + secrets present:
uv run python -m hypervector live-run \
  --path data/exports/<id> \
  --enabled \
  --i-accept-live-risk \
  --max-notional-usd 50
```

If any gate fails, CLI refuses (fail-closed). Do not bypass.

## Data roots

```text
data/
  cache/  runs/  exports/  logs/  nautilus/
  paper/decisions/decisions.jsonl   # paper-report, TUI tape paper
  paper/ledger/
  live/decisions/decisions.jsonl    # live-report, TUI tape live
  live/ledger/
```

`paper-report --path` must not point at live/; `live-report` must not point at paper/.

## TUI allowlist (what TUI may subprocess)

Only: `status`, `paper-check`, `live-check`, `paper-report`, `live-report`, `regime`.

Never: `paper-run`, `live-run`, control plane.

Keys: `?` help · `Tab` card · `Enter` focus · `Esc` floor · `r` refresh · `R` regime · `p`/`l`/`a` tape · `q` quit.

## JSON honesty fields (agents parse these)

- `status.honesty.paper_never_constructs_exec_client`
- `status.honesty.live_run_fail_closed`
- `status.honesty.secret_values_never_printed`
- `status.paper.no_submit`
- `status.live.submit_wired` / `can_start` / `max_notional_usd` / `network`
- `live-check.start_gate` = `ok` | `refused` (+ `start_gate_reason`)
- `paper-report` / `live-report`: counters only; no wallet/key material

## Offline verification

```bash
uv run pytest tests/ -q -m "not network"
cargo test -p hypervector-tui
cargo build -p hypervector-tui --release
```

## Decision tree for agents

```text
Need layout?           → infra-init
What's installed?      → status
Can paper run?         → paper-check
Can live start?        → live-check (never secrets values)
Summarize paper tape?  → paper-report
Summarize live tape?   → live-report
Research bars?         → history
Regime metrics?        → regime
Find alpha?            → sweep-* → report → export → export-validate
Historical BT?         → phase2-check → phase2-run
Dry-run live feed?     → paper-run --mode shadow
Real place?            → STOP → confirm user + secrets → live-run armed
Monitor only?          → hypervector-tui
Acceptance review?     → load hypervector-acceptance skill
```

## References

- `references/command-matrix.md` — full command matrix
- `references/safety.md` — live arming and secret policy
- `docs/infra-data-layout.md` — I2 layout
- `docs/guides/acceptance-visual-and-holistic.md` — visual + holistic gate
- `HANDOFF.md` — phase status

## Anti-patterns

- Inventing flags not in `--help`
- Using `phase2-run --live` as live trading
- Writing keys into commands, logs, or commits
- Mixing paper/live paths
- Claiming TUI can arm or place
- Skipping `export-validate --strict` before paper-run on untrusted export
