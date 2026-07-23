# Agent notes — hypervector

## Skills (load these)

| Skill | When |
|-------|------|
| **`hypervector-cli`** | Any CLI / paper / live / research / TUI ops |
| **`hypervector-acceptance`** | Visual tickrs pass, holistic CLI↔TUI sign-off |

Paths (project-scoped):

- `.grok/skills/hypervector-cli/SKILL.md`
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
