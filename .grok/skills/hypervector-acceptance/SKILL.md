---
name: hypervector-acceptance
description: >
  Run Phase 5 visual (tickrs bar) assist and holistic CLI↔TUI acceptance protocol
  for hypervector. Use when the user asks for visual pass, tickrs bar review,
  holistic acceptance, TUI acceptance, CLI parity check, sign-off, or Phase 5 gate.
  Slash: /hypervector-acceptance. Follow docs/guides/acceptance-visual-and-holistic.md exactly.
---

# hypervector-acceptance

Drive **Gate B (visual assist)** and **Gate C (holistic CLI↔TUI)** using the canonical guide.

## Canonical doc (source of truth)

Read and follow:

`docs/guides/acceptance-visual-and-holistic.md`

Do not invent alternate checklists. Use IDs **V1–V16**, **C1–C7**, **S1–S5**.

## Agent authority limits

| Task | Agent may | Agent must not |
|------|-----------|----------------|
| Gate A automated | Run full suite; report evidence | Skip failures |
| Gate B visual | Prep environment, launch TUI, fill V# template | Mark overall VISUAL **PASS** without Albert |
| Gate C holistic | Run CLI captures, parity tables, S1–S5 | Arm live or place |
| GUI | Remind deferred | Start GUI design before B+C PASS |

## Workflow

### 1. Pre-flight (Gate A)

```bash
uv run pytest tests/ -q -m "not network"
cargo test -p hypervector-tui
cargo build -p hypervector-tui --release
uv run python -m hypervector --data-root data status
```

Record pass/fail with exit evidence. If A fails, stop — fix before B/C.

### 2. Prep demo data if needed

```bash
mkdir -p data/paper/decisions
# only if empty:
cp crates/hypervector-tui/tests/fixtures/decisions_paper.jsonl \
   data/paper/decisions/decisions.jsonl
```

### 3. Holistic CLI captures (C1–C5)

```bash
uv run python -m hypervector --data-root data status | tee /tmp/hv-status.json
uv run python -m hypervector --data-root data paper-check | tee /tmp/hv-paper-check.json
uv run python -m hypervector --data-root data live-check | tee /tmp/hv-live-check.json
uv run python -m hypervector --data-root data paper-report --last 5 | tee /tmp/hv-paper-report.json
# regime may need network/cache:
uv run python -m hypervector --data-root data regime 2>/dev/null | tee /tmp/hv-regime.json || true
```

Build parity tables from guide §3.2. Flag mismatches as **FAIL** with field path + expected vs actual.

### 4. Safety S1–S5

- S1: `cargo test -p hypervector-tui --test read_only_guard`
- S2: instruct user to confirm no secret glyphs; agent greps TUI code for allowlist
- S3: document tape path footer for `p` vs `l`
- S4: status honesty flags true
- S5: user confirms quit restores terminal

### 5. Visual assist (B)

Launch:

```bash
./target/release/hypervector-tui --data-root data
```

Present the **V1–V16** checklist to Albert. Fill what agent can observe from design/code; leave subjective density (V5–V10) for human.

### 6. Sign-off artifacts

If Albert says PASS:

1. Write `docs/superpowers/notes/YYYY-MM-DD-phase5-acceptance.md` with both sign-off blocks completed.
2. Update `HANDOFF.md`: Visual PASS, Holistic PASS, Phase 5 accepted; GUI still needs explicit reopen.
3. Commit docs only if user wants commit.

If FAIL: list blocker IDs, proposed fix owner (code vs config), no GUI.

## Quality bar

- Every claim cites a command output or checklist ID.
- No “looks good” without IDs.
- Prefer `hypervector-cli` skill for any CLI invocation details.
- Truecolor terminal ≥120×32 recommended for visual session.

## Related

- `.grok/skills/hypervector-cli/SKILL.md`
- `docs/superpowers/specs/2026-07-23-phase5-tui-design.md` SRS_HV5_*
- `HANDOFF.md`
