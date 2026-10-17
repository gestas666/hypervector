# Agent notes — hypervector

## Skills (load these)

| Skill | When | Path |
|-------|------|------|
| **`hypervector-cli`** | Any CLI / backtesting / autotune / paper / live / research ops | `skills/hypervector-cli/SKILL.md` |
| **`hypervector-regime-detector`** | Canonical regime engine, accuracy evaluation and JSON telemetry | `skills/hypervector-regime-detector/SKILL.md` |

Paths (project-scoped):
- `skills/hypervector-cli/SKILL.md` (or `.grok/skills/hypervector-cli/SKILL.md`)
- `skills/hypervector-regime-detector/SKILL.md` (or `.grok/skills/hypervector-regime-detector/SKILL.md`)

## Guides

| Guide | Path |
|-------|------|
| Visual + holistic acceptance | `docs/guides/acceptance-visual-and-holistic.md` |
| Data layout (I2) | `docs/infra-data-layout.md` |
| Phase status | `HANDOFF.md` |

## Safety defaults

- Paper/shadow: never place.
- Live: fail-closed; arm only on explicit user request.
- Never print wallet/API secret values.
- Mainnet only. No neural-trader.
- The TUI is retired; use the unified CLI and headless acceptance guide.
- In an armed live checkout, use its existing `.venv/bin/python`; do not run
  `uv run` or `uv sync`. Develop execution changes in an isolated checkout with
  its own venv. Merge/restart only at an explicitly approved transition boundary.

## Project Charter

| Principle | Spec Identifier | Core Rule & Enforcement |
|-----------|-----------------|-------------------------|
| **Ungated Execution** | `SRS_HV1_NO_GATES` | Only **technical failure** aborts a trial. No implicit strategy, drawdown, or risk rejection gates unless explicitly configured by the user. Performance, drawdown, trade count, regime confidence, and model scores remain reported trial results rather than implicit abort conditions. |
| **Fail-Closed Safety** | `SRS_HV1_HONESTY` | Paper/shadow mode **never** constructs live execution clients or places live orders. Live mode is strictly fail-closed and arms **only** on explicit `--enabled --i-accept-live-risk` flags. Wallet/API secrets are **never** printed. |
| **Regime Telemetry** | `SRS_HV1_REGIME` | Multi-timeframe trend & volatility classification (1m execution, 15m HTF regime lock) with dynamic ML conviction scaling and continuous rolling window transition logging. |
| **Venue Precision** | `SRS_HV1_VENUE_SPEC` | Strict adherence to Hyperliquid per-asset venue leverage specifications (BTC 40x max, ETH 25x max, SOL 20x max, Altcoins 10x-15x max). |

## Quick verify

```bash
.venv/bin/python -m pytest tests/ -q -n 4 --dist loadfile
.venv/bin/python -m hypervector status
```
