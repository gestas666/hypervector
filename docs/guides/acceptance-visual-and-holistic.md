# Acceptance Guide — Visual Pass (tickrs bar) + Holistic CLI ↔ TUI

**Audience:** Albert (ops owner) + agents assisting review  
**When:** After Phase 5 `hypervector-tui` implementation (Tasks 1–9 done)  
**Outcome:** Signed visual + holistic acceptance **before** any GUI work  
**Status:** Ready for use (2026-07-23)  
**Related:** `docs/superpowers/specs/2026-07-23-phase5-tui-design.md`, `docs/superpowers/specs/2026-07-23-phase4c-cli-completeness-design.md`, `HANDOFF.md`

---

## 0. What “ready” means

| Gate | Owner | Pass criteria |
|------|--------|----------------|
| **A. Automated** | CI / agent | `cargo test -p hypervector-tui` green; offline pytest green; no network required |
| **B. Visual (tickrs bar)** | Albert | Floor density, mode banner, KPI craft meet peer bar (not default ratatui demo) |
| **C. Holistic CLI ↔ TUI** | Albert (+ agent assist) | Same truth: status/gates/tape/regime match CLI JSON within one refresh; safety rules hold |
| **D. GUI reopen** | Albert | Only after B + C signed — GUI remains **deferred** until then |

This guide is the playbook for **B** and **C**. Gate A was already exercised on implementation.

---

## 1. Pre-flight (5 minutes)

```bash
cd /Users/gestas/Prototypes/hypervector   # or your clone
git checkout main && git pull
uv sync --all-extras
uv run pytest tests/ -q -m "not network"
cargo test -p hypervector-tui
cargo build -p hypervector-tui --release
uv run python -m hypervector status
```

**Expect:** offline pytest ~279+; TUI tests 28; status JSON `ok: true`, honesty flags true, no secret strings.

**Terminal:** Prefer a truecolor emulator (Ghostty, Kitty, WezTerm, modern iTerm2). Size ≥ **120×32** (absolute minimum **80×24** for banner visibility).

**Optional demo tape** (if paper decisions empty):

```bash
mkdir -p data/paper/decisions
cp crates/hypervector-tui/tests/fixtures/decisions_paper.jsonl \
   data/paper/decisions/decisions.jsonl
```

---

## 2. Visual pass — tickrs / density bar

### 2.1 Reference peers (what “good” looks like)

| Peer | Steal for hypervector-tui | Do **not** copy |
|------|---------------------------|-----------------|
| **[tickrs](https://github.com/tarkah/tickrs)** | Dense market-style numbers, readable sparklines, summary collapse, cadence feel | Full Yahoo watchlist product |
| **btop** | Card packing, notched titles, right-aligned metrics | System-monitor module soup |
| **k9s** | Mode/context always obvious; keyboard-first | Cluster admin chrome |
| **bottom** | Clean multi-panel resize | Generic status bars only |

**One-sentence bar:**  
*“At a glance I know mode (shadow/paper/live), whether I’m safe, last decisions, and regime mix — without squinting or hunting menus.”*

### 2.2 Launch surfaces

```bash
# Primary
./target/release/hypervector-tui --data-root data

# Dev
cargo run -p hypervector-tui -- --data-root data --refresh-ms 1000 --tape auto
```

Keys reminder: `?` help · `Tab` focus card · `Enter` focus view · `Esc` floor · `r` refresh · `R` regime · `p`/`l`/`a` tape · `q` quit.

### 2.3 Visual checklist (tick every row)

Score each: **PASS / FAIL / N/A**. Failures need a note (screenshot path optional).

#### Mode & stress clarity (k9s / safety)

| # | Check | PASS criteria |
|---|--------|----------------|
| V1 | Mode banner always visible | Full-width; no scroll needed on ≥24 rows; shows SHADOW / PAPER / LIVE |
| V2 | LIVE danger | LIVE uses high-contrast (e.g. white on red); still read-only |
| V3 | Network | Banner or gates show **mainnet** (no testnet path) |
| V4 | Read-only obvious | Footer or banner signals monitor-only / no arm from TUI |

#### Density & craft (tickrs / btop)

| # | Check | PASS criteria |
|---|--------|----------------|
| V5 | Card packing | Gates \| KPI mid row; Regime \| Tape lower; no large empty voids on 120×32 |
| V6 | KPI primary | Decision count large (big-text) when height allows; compact bold when short |
| V7 | Sparkline / gauge | Tape activity sparkline readable; notional/utilization gauge not raw dump |
| V8 | Tape table | Columns aligned (time, mode, action, side, sub, px); newest-first feels ops-grade |
| V9 | Theme | Semantic colors (live danger, up/down regime, muted chrome); not greyscale default boxes |
| V10 | Rounded chrome | Cards use rounded borders / clear titles; focused card border stronger |

#### Empty & error states

| # | Check | PASS criteria |
|---|--------|----------------|
| V11 | Cold empty | Empty tape shows designed copy, not panic/blank panel |
| V12 | Regime cold | “press R” / no metrics hint when regime unavailable |
| V13 | Toast | Soft CLI/probe errors toast without secrets |
| V14 | Quit restore | After `q` / Ctrl+C, shell is normal (no stuck raw mode / garbled prompt) |

#### Motion (optional design goals)

| # | Check | PASS criteria |
|---|--------|----------------|
| V15 | Sparse motion | Skeleton on first load OK; no rain/particles/carnival |
| V16 | Focus only two views | Enter → Focus; Esc → Floor; **no third screen** |

### 2.4 Visual sign-off block (copy into HANDOFF or PR)

```text
VISUAL PASS — hypervector-tui
Date:
Terminal:
Size:
Tape mode used: paper / live / auto
V1–V16: (list FAIL only)
Overall: PASS | FAIL
Reviewer:
Notes:
```

**PASS rule:** No FAIL on V1–V4, V11–V14, V16. Soft fails on V15 only if still non-carnival. Density V5–V10: at most one minor nit if still ops-usable.

---

## 3. Holistic CLI ↔ TUI acceptance

Goal: TUI is a **projection** of CLI/ledger truth — not a second brain.

### 3.1 Safety invariants (hard fail if broken)

| ID | Invariant | How to verify |
|----|-----------|---------------|
| S1 | TUI never spawns `paper-run` / `live-run` | Source allowlist + `cargo test -p hypervector-tui read_only` / static guard |
| S2 | No secret values on screen | Set dummy env names present; open TUI; only `secrets present=true/false` — never key material |
| S3 | Paper tape cannot bind live path | `p` vs `l` toggles; path footer shows correct segment |
| S4 | Live fail-closed honesty | `status` / footer: live fail-closed; paper no_submit |
| S5 | Terminal restore | Quit leaves usable shell |

### 3.2 Parity protocol (CLI truth → TUI)

Run CLI and TUI against the **same** `--data-root`.

#### Step C1 — Status / honesty

```bash
uv run python -m hypervector --data-root data status | tee /tmp/hv-status.json
```

In TUI (after `r`):

| CLI field | TUI location | Match? |
|-----------|--------------|--------|
| `live.submit_wired` | Gates card | |
| `live.can_start` | Gates card | |
| `live.max_notional_usd` | Gates / KPI gauge context | |
| `live.network` | Banner / gates | |
| `paper.no_submit` | Gates / health | |
| `honesty.*` | Health footer | |

#### Step C2 — Paper gates

```bash
uv run python -m hypervector --data-root data paper-check | tee /tmp/hv-paper-check.json
```

| CLI field | TUI | Match? |
|-----------|-----|--------|
| `paper.execution_mode` / `mode` | Mode banner default / gates | |
| `paper.book_feed`, `l2_walk_available` | Gates bools | |
| `paper.secrets_present` | Gates (bool only) | |
| `live.readiness.can_start` / nested live | Gates live section | |

#### Step C3 — Live gates

```bash
uv run python -m hypervector --data-root data live-check | tee /tmp/hv-live-check.json
```

| CLI field | TUI | Match? |
|-----------|-----|--------|
| `live.enabled`, `armed`, `can_start` | Gates | |
| `start_gate` / reason | Gates (if shown) | |
| `submit_wired` | Gates | |
| `venue_submit` must be false on check | Never shows as actively submitting | |

#### Step C4 — Decision tape

```bash
# Ensure sample or real paper decisions exist
uv run python -m hypervector --data-root data paper-report --last 5 | tee /tmp/hv-paper-report.json
```

In TUI: press `p` (paper). Confirm:

- Row count on tape ≥ min(rows, display window)  
- Actions / modes consistent with report `action` / `execution_mode` histograms  
- `submitted` column shows N/false for paper/shadow honesty  

Toggle `l` (live): path footer must use `live/decisions`; empty state if no live file.

#### Step C5 — Regime

```bash
# May hit network/cache; for offline inject fixture via --fixture-regime in advanced runs
uv run python -m hypervector --data-root data regime 2>/dev/null | tee /tmp/hv-regime.json
```

In TUI: press `R` (or wait for timer). Compare:

| CLI `metrics.*` | TUI Regime card |
|-----------------|-----------------|
| `pct_up`, `pct_down`, `pct_range` | Percent labels / bars |
| `flip_rate`, `mean_duration`, `n_bars` | Meta line / focus table |
| Dominant label | Badge matches largest share |

**Hard rule:** TUI must not invent EMA labels in Rust — only display probe/fixture metrics.

#### Step C6 — Focus navigation

1. `Tab` through cards — focus border moves  
2. `Enter` on Regime / Tape / Gates — full height content  
3. `Esc` always returns Floor  
4. Confirm enum/UI: **only two views**

#### Step C7 — Cross-surface honesty (paper vs live)

| Surface | Expect |
|---------|--------|
| Paper report | `no_submit` / submitted false or absent |
| Live report | Can show submitted when live ran; still no secrets |
| TUI health | paper_no_submit · live_fail_closed · secrets never printed |

### 3.3 Holistic sign-off block

```text
HOLISTIC CLI↔TUI ACCEPTANCE
Date:
data-root:
C1 status parity: PASS|FAIL
C2 paper-check: PASS|FAIL
C3 live-check: PASS|FAIL
C4 tape vs paper-report: PASS|FAIL
C5 regime: PASS|FAIL|SKIP (reason)
C6 two views: PASS|FAIL
C7 honesty: PASS|FAIL
S1–S5 safety: PASS|FAIL
Overall: PASS|FAIL
Reviewer:
Blockers:
```

**PASS rule:** All S1–S5 PASS; C1–C4, C6–C7 PASS; C5 PASS or SKIP only if offline/no cache with documented reason.

---

## 4. Agent assist (how agents should help)

Agents **may**:

- Run Gate A and C1–C5 CLI captures  
- Diff CLI JSON vs TUI model parsers / fixtures  
- File a structured FAIL report against V#/C#/S# IDs  
- Seed fixtures; never invent live secrets  

Agents **must not**:

- Claim visual PASS for Albert (V1–V16 needs human eyes)  
- Run `live-run --enabled --i-accept-live-risk` without explicit Albert order + secrets  
- Push GUI work before B+C signed  

Use skill: **`hypervector-cli`** for correct CLI invocation; **`hypervector-acceptance`** for this checklist workflow.

---

## 5. After both gates PASS

1. Update `HANDOFF.md`: Visual **PASS**, Holistic **PASS**, Phase 5 **accepted**.  
2. Optional: tag `phase5-tui-accepted`.  
3. **Only then** open GUI design (separate epic).  
4. Do not weaken read-only TUI control plane without a new design pass.

---

## 6. Quick reference — commands

```bash
# Inventory
uv run python -m hypervector --data-root data status

# Gates
uv run python -m hypervector --data-root data paper-check
uv run python -m hypervector --data-root data live-check

# Ledgers (read-only)
uv run python -m hypervector --data-root data paper-report --last 10
uv run python -m hypervector --data-root data live-report --last 10

# Regime (display-only metrics source)
uv run python -m hypervector --data-root data regime

# TUI
./target/release/hypervector-tui --data-root data

# Offline regression
uv run pytest tests/ -q -m "not network"
cargo test -p hypervector-tui
```

---

## 7. Anti-patterns (reject)

- “Looks fine” without V1–V16 / C1–C7 IDs  
- Accepting greyscale default ratatui skin as tickrs-grade  
- TUI re-running alpha / EMA detector with different params  
- Third navigation root (tabs forest, research browser)  
- Secret values in toast, logs, or screenshots committed to git  
- Starting GUI design while B or C is FAIL  

---

## 8. Record location

| Artifact | Path |
|----------|------|
| This guide | `docs/guides/acceptance-visual-and-holistic.md` |
| Sign-off notes (optional) | `docs/superpowers/notes/YYYY-MM-DD-phase5-acceptance.md` |
| Phase status | `HANDOFF.md` |
| Agent CLI skill | `.grok/skills/hypervector-cli/SKILL.md` |
| Agent acceptance skill | `.grok/skills/hypervector-acceptance/SKILL.md` |
