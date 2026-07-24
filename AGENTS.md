# Agent notes — hypervector

## Skills (load these)

| Skill | When | Path |
|-------|------|------|
| **`hypervector-cli`** | Any CLI / backtesting / autotune / paper / live / research ops | `skills/hypervector-cli/SKILL.md` |
| **`hypervector-regime-detector`** | Ultimate Regime Engine, accuracy evaluation, `tui-regime-detector` | `skills/hypervector-regime-detector/SKILL.md` |
| **`hypervector-acceptance`** | Visual tickrs pass, holistic CLI↔TUI sign-off | `.grok/skills/hypervector-acceptance/SKILL.md` |

Paths (project-scoped):
- `skills/hypervector-cli/SKILL.md` (or `.grok/skills/hypervector-cli/SKILL.md`)
- `skills/hypervector-regime-detector/SKILL.md` (or `.grok/skills/hypervector-regime-detector/SKILL.md`)
- `.grok/skills/hypervector-acceptance/SKILL.md`

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
- GUI deferred until acceptance guide gates B+C PASS.

## Quick verify

```bash
uv run pytest tests/ -q -m "not network"
cargo test -p hypervector-tui
uv run python -m hypervector status
```
