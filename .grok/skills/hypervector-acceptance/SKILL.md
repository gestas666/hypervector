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

Product bar is **Shadow Ops Floor** (dry-run cockpit): DRY-RUN READY chip, regime auto, price/activity charts, ops tape — not a thin JSON mirror.

## Canonical doc (source of truth)

Read and follow:

`docs/guides/acceptance-visual-and-holistic.md`

Do not invent alternate checklists. Use IDs **V1–V16**, **C1–C7**, **S1–S5**.

## Project Charter Enforcement

- **`SRS_HV1_NO_GATES`**: Ungated execution — only technical failures abort a trial.
- **`SRS_HV1_HONESTY`**: Fail-closed safety & paper/shadow non-submitting guarantee.
- **`SRS_HV1_REGIME`**: 15m HTF lock + 1m execution continuous rolling window telemetry.
- **`SRS_HV1_VENUE_SPEC`**: Hyperliquid per-asset leverage specifications (BTC 40x, ETH 25x, SOL 20x).

## Agent authority limits

| Task | Agent may | Agent must not |
|------|-----------|----------------|
| Gate A automated | Run full suite; report evidence | Skip failures |
| Gate B visual | Prep environment, launch TUI, fill V# template | Mark overall VISUAL **PASS** without user sign-off |
| Gate C holistic | Run CLI captures, parity tables, S1–S5 | Arm live or place orders |
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

### 5. 4-Screen Visual assist (B)

Launch:

```bash
cargo run -p hypervector-tui --bin tui-regime-detector -- --symbol BTC --timeframe 1m
```

Verify all 4 Cockpit screens (`[1]`, `[2]`, `[3]`, `[4]`):
- **`[1]`**: Regime engine, 15m HTF lock, continuous rolling transition audit log.
- **`[2]`**: Strategy policy matrix.
- **`[3]`**: Live shadow paper trading cockpit ($10k equity, L2 orderbook stack, win/loss stats, trade journal).
- **`[4]`**: Interactive engine & risk configuration (dynamic vs static leverage, TP/SL engines, risk calculator).

Fill what agent can observe from design/code; leave subjective density (V5–V10) for human.

### 6. Sign-off artifacts

If user says PASS:

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

- `skills/hypervector-cli/SKILL.md`
- `skills/hypervector-regime-detector/SKILL.md`
- `docs/superpowers/specs/2026-07-23-phase5-tui-design.md` SRS_HV5_*
- `HANDOFF.md`
