# HANDOFF — hypervector

**Saved:** 2026-07-21  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Status:** Install done. **Phase 1 design cycle in progress.** User process = **`engineering-software` (Hyde) + brainstorming** for the full development cycle. Load `~/.grok/skills/engineering-software` after restart. No implementation until requirements/design approved.

Agentmemory: `mem_mrv00zmt_4d9453952d47` (workflow handoff). Resume with “read HANDOFF.md” or `/handoff` / recall `hypervector`.

---

## Goal (current understanding)

Hybrid quantitative pipeline (from `pyproject.toml` / `initial-spec.md`):

1. **Phase 1 — VectorBT** research / vectorized backtests  
2. **Phase 2/3 — NautilusTrader** event-driven sim → live path (Hyperliquid in scope for install)  
3. **Backtrader** also installed as an additional classical backtest engine (user request this session)

Exact product scope beyond “install engines + docs” is **TBD — user will detail next**.

---

## Current progress

### Environment (Python 3.13 via `uv`)

| Package | Version / notes |
|---------|-----------------|
| `vectorbt[full,rust]` | `1.1.0` (existing; rust engine + full integrations) |
| `nautilus_trader` | `>=1.230.0` → installed **1.230.0** official **wheel** (cp313 macOS arm64) |
| Hyperliquid adapter | Bundled in core wheel — no pip extra; import `nautilus_trader.adapters.hyperliquid` works |
| `backtrader[plotting]` | `>=1.9.78.123` → **1.9.78.123** + matplotlib |

`pyproject.toml` + `uv.lock` updated. No secrets in repo.

### Install tests (in-repo)

| File | What it proves |
|------|----------------|
| `tests/test_install.py` | VectorBT rust + full integrations |
| `tests/test_nautilus_install.py` | Nautilus version, Hyperliquid public surface, offline config construct, factories |
| `tests/test_backtrader_install.py` | Backtrader version, plotting extra, public API, minimal offline Cerebro SMA-cross |

Run:

```bash
uv sync --all-extras
uv run pytest tests/test_install.py tests/test_nautilus_install.py tests/test_backtrader_install.py -v
```

### Reference / offline docs (all under `reference/`, **gitignored** via `/reference/`)

| Path | Contents |
|------|----------|
| `reference/nautilus_trader-develop/` | Vendored Nautilus develop tree (source + docs + examples) |
| `reference/nautilus-backtester-docs/` | Curated scrape: latest + nightly backtesting, Python API, notebook conversions — see its `README.md` |
| `reference/vectorbt-v1.1.0/` | VectorBT 1.1.0 source tree |
| `reference/backtrader/` | Clone of https://github.com/mementum/backtrader @ v1.9.78.123 |
| `reference/backtrader-docs/` | Full `/docu/` scrape (69/69 pages) + `README.md` |
| `reference/backtrader-master/`, `apex/`, `orderbook/`, `pine-scripts/` | Present; not owned by this session |

### Skills installed for agents (user request)

From `backtest-lab/backtest_lab/skills/` → copied to:

- `~/.grok/skills/{write-clean-code,think-like-a-programmer,engineering-software}`
- `~/.agents/skills/` (same three)
- `~/.claude/skills/` (same three)

Grok primary path: `~/.grok/skills/`. Claude-compat skills flag is `false` in `~/.grok/config.toml`; Grok path is what matters here.

---

## What worked

- Prefer **PyPI wheels** for Nautilus (do not source-build unless wheel missing).
- Hyperliquid is **in the core Nautilus package** — no separate extra.
- Backtrader “full” install = **`backtrader[plotting]`** (pulls matplotlib).
- Docs: `web-scrape` with Parallel engine into `reference/*-docs/`; keep README reading orders.
- Install gates = real imports + offline engine smoke (no network, no live keys).

## What to avoid / non-goals so far

- Live trading, Hyperliquid keys, builder fees, vaults (explicit non-goal of install goal).
- Committing `reference/` (gitignored on purpose — huge trees).
- Replacing VectorBT or rewriting Phase-1 beyond coexistence.
- Source-building Nautilus when wheels exist.

---

## Git state (uncommitted at handoff)

```
 M .gitignore          # /reference/
 M initial-spec.md
 M pyproject.toml      # nautilus + backtrader deps
 M tests/test_install.py
 M uv.lock
?? tests/test_backtrader_install.py
?? tests/test_nautilus_install.py
?? HANDOFF.md
```

No commit was made for this work unless user asked later.

---

## Preferred development cycle (USER MANDATE)

Load and follow after every restart:

1. **`engineering-software`** — `~/.grok/skills/engineering-software/SKILL.md` (Write Great Code Vol. 3 / Hyde)  
   Process framing for hypervector (small solo project → light iterative, not enterprise Waterfall theater):
   - **Verify** (build the product right) and **validate** (build the right product) explicitly.
   - Requirements must be **testable** — *shall* / *must*; black-box; atomic. Weak words killed.
   - Prefer **use-case narratives** for externally visible Phase 1 behaviors (what, not how).
   - Design concerns → viewpoints/views only after requirements are solid enough.
   - Traceability light-weight: tag requirements → design notes → tests (STC-style), not full IEEE doc set.
   - ~40% cost from bad requirements — **front-load Q&A**; estimate with ×2–4 on small tasks.
   - Project size: treat Phase 1 as **small/medium solo** → iterative MVP loops, not Spiral/FDD ceremony.

2. **`brainstorming`** (superpowers) — collaborative design gate  
   One question at a time → 2–3 approaches → design sections → write `docs/superpowers/specs/…-design.md` → user review → **`writing-plans` only** after approval.

3. **Hard-gate:** no product implementation until Phase 1 design/spec is approved.

4. Related book skills (installed same session, optional for tone/quality):  
   `write-clean-code`, `think-like-a-programmer` under `~/.grok/skills/`.

---

## Brainstorming log (Phase 1)

**Process:** `engineering-software` + superpowers `brainstorming`. See mandate above.

**Hard-gate:** no product code until Phase 1 design is approved.

**Known from `initial-spec.md`:**
- Phase 1 = VectorBT: features, ML matrices, multi-dim parameter sweeps on candles
- Output = filtered candidates with robust parameter bounds for Phase 2 (Nautilus)
- Integration preference = modular: export signals/weights → Nautilus ingest
- Tuning note: “Kapathy-style autotune / Optima / Both” (unresolved)

**Q&A (append each answer):**
1. **Market universe:** Hyperliquid **perps only**.
2. **Adapters:** Prefer reuse — `dev/hyper-pi`, `Prototypes/hypertrader`, `reference/apex/`, other HL tooling.
3. **Symbols:** MVP **BTC only**; design for **majors basket**.
4. **TF:** MVP **1m**; design multi-TF **5m, 15m** then maybe 30m/1h.
5. **History:** floor 30d; default 90d; promo 180d; config-driven.
6. **Rank:** primary **net PnL / total return**; secondary Sharpe, trade count, W/L, win%, DD — **no risk gates**.
7. **Strategies start:** best **uptrend**, best **downtrend**, **regime detection** (up/down/range); pine + book families; multi-export.
8. **Data:** HL-max first; **Binance then Bybit** backfill with provenance.
9. **Infra I2:** Parquet cache + SQLite runs + FS exports under `/data/` (gitignored).

**Design spec:** `docs/superpowers/specs/2026-07-21-phase1-vectorbt-design.md` — awaiting user review of written file.

---

## Next steps (for following session)

0. **On restart:** load `engineering-software` + brainstorming; read this HANDOFF + design spec.
1. User reviews/approves written design spec (or requests edits).
2. Then **writing-plans** only → implementation plan.
3. Optionally commit install/test changes if user wants.
4. Do **not** implement Phase 1 product code until plan execution begins.

---

## Quick resume commands

```bash
cd /Users/gestas/Prototypes/hypervector
uv sync --all-extras
uv run python -c "import vectorbt, nautilus_trader, backtrader; print(vectorbt.__version__, nautilus_trader.__version__, backtrader.__version__)"
# Docs indexes
open reference/nautilus-backtester-docs/README.md   # or just read in editor
open reference/backtrader-docs/README.md
```
