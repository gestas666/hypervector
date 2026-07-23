# HANDOFF — hypervector

**Saved:** 2026-07-23 — Acceptance guide + agent skills shipped. **Next: run visual + holistic gates.**  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `main` (tracks `origin/main`)  
**Remote:** `https://github.com/gestas666/hypervector.git`  
**HEAD:** check `git log -1`

**Prefer this HANDOFF over agentmemory for phase status.**

---

## Status (read this first)

| Layer | State |
|-------|--------|
| Phase 1–4c + Phase 5 TUI code | **Done** (on `main`, pushed) |
| Automated QA | **Green** (last: TUI 28, pytest offline 279) |
| **Acceptance guide (visual + holistic)** | **Written** → `docs/guides/acceptance-visual-and-holistic.md` |
| **Agent CLI skill** | **Written** → `.grok/skills/hypervector-cli/` |
| **Agent acceptance skill** | **Written** → `.grok/skills/hypervector-acceptance/` |
| Visual pass (tickrs bar) | **NEXT — Albert** |
| Holistic CLI ↔ TUI | **NEXT — Albert + agent assist** |
| 1-page GUI | **Deferred** until both acceptance gates PASS |
| neural-trader | **Rejected** |

---

## NEXT ACTION ITEMS (highest priority)

### 1. Visual pass — tickrs / density bar

- **Guide:** `docs/guides/acceptance-visual-and-holistic.md` §2  
- **Skill:** `/hypervector-acceptance`  
- **IDs:** V1–V16  
- **Owner:** Albert (human eyes required for PASS)  
- **Launch:** `./target/release/hypervector-tui --data-root data`

### 2. Holistic CLI ↔ TUI acceptance

- **Guide:** same doc §3  
- **Skill:** `/hypervector-acceptance` + `/hypervector-cli`  
- **IDs:** C1–C7, S1–S5  
- **Owner:** Albert + agent (agent runs CLI parity; human confirms screen)

### 3. After both PASS

- Record sign-off in `docs/superpowers/notes/YYYY-MM-DD-phase5-acceptance.md`  
- Update this HANDOFF: Phase 5 **accepted**  
- Only then reopen GUI design  

---

## Guides & skills (new)

| Artifact | Path |
|----------|------|
| Visual + holistic user guide | `docs/guides/acceptance-visual-and-holistic.md` |
| Guides index | `docs/guides/README.md` |
| Agent entrypoint | `AGENTS.md` |
| CLI skill | `.grok/skills/hypervector-cli/SKILL.md` |
| CLI refs | `.grok/skills/hypervector-cli/references/{command-matrix,safety}.md` |
| Acceptance skill | `.grok/skills/hypervector-acceptance/SKILL.md` |

**Slash:** `/hypervector-cli` · `/hypervector-acceptance`

---

## Phase 5 TUI — what shipped

```bash
cargo run -p hypervector-tui -- --data-root data
./target/release/hypervector-tui --data-root data
```

| Flag | Default |
|------|---------|
| `--data-root` | `data` |
| `--refresh-ms` | `1000` |
| `--tape` | `auto` (`paper`\|`live`\|`auto`) |

**Views:** Ops Floor + Card Focus only.  
**Keys:** `?` · `Tab` · `Enter` · `Esc` · `r` · `R` · `p`/`l`/`a` · `q`  
**Safety:** read-only CLI allowlist; no secrets; paper/live path refuse; terminal restore on quit.

### Automated verification (baseline)

```text
cargo test -p hypervector-tui     → 28 passed
cargo build -p hypervector-tui --release → ok
uv run pytest tests/ -q -m "not network" → 279 passed, 4 deselected
uv run python -m hypervector status → ok
```

---

## Pipeline

```text
1–4c + 5 TUI code     DONE
Acceptance guide+skills DONE
Visual gate            NEXT  ← Albert
Holistic gate          NEXT  ← Albert + agent
GUI                    DEFERRED
```

---

## Ops commands (quick)

| Area | Command |
|------|---------|
| Status | `uv run python -m hypervector status` |
| Paper | `paper-check` · `paper-run` · `paper-report` |
| Live | `live-check` · `live-run` (armed) · `live-report` |
| Regime | `hypervector regime` |
| TUI | `hypervector-tui` |
| Agent CLI | load **hypervector-cli** skill |

Full matrix: `.grok/skills/hypervector-cli/references/command-matrix.md`

---

## Locked decisions

| Topic | Choice |
|-------|--------|
| TUI name | `hypervector-tui` |
| Control plane | Read-only v1 |
| Views | Floor + Focus only |
| Network | Mainnet only |
| GUI | Deferred post acceptance |
| neural-trader | Rejected |

---

## Outgoing summary

**Code + GitHub ready. Acceptance guide and agent skills now exist.**  

**Next human step:** open `docs/guides/acceptance-visual-and-holistic.md` and run the visual (V*) + holistic (C*/S*) checklists — or tell an agent `/hypervector-acceptance` to drive the assist protocol.
