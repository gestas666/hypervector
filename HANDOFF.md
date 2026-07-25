# HANDOFF — hypervector

**Saved:** 2026-07-25 — Full L2 replay recovered, four lanes autotuned, and replay ML candidates trained.
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `feat/hypervelocity-backend-telemetry`
**Prefer this HANDOFF over agentmemory for phase status.**

---

## Status (read this first)

| Layer | State |
|-------|--------|
| Phase 1–4c CLI pipeline | **Done** |
| Phase 5 thin projector TUI | **Superseded** by Shadow Ops Floor |
| Probe Python resolution | **Fixed** (`.venv` / `HYPERVECTOR_PYTHON` / `uv run`) |
| Shadow Ops Floor (readiness + charts + regime auto + tape craft) | **Implemented** — agent PTY evidence green |
| Automated QA | **Green** (TUI 7 tests; pytest offline 333 on 2026-07-25) |
| Visual PASS (human) | **NEXT — Albert** |
| Holistic CLI↔TUI | **Agent assist PASS**; human on-screen confirm |
| GUI | **Deferred** until Shadow Ops visual PASS |
| Hypervelocity execution authority | **Python backend only**; TUI consumes ledger telemetry |
| Hypervelocity LightGBM | **Observe-only mode implemented**; candle and L2-replay candidates retained with metrics |
| Hypervelocity 180d autotune | **Completed**; best long/short candle trials remained materially negative after costs |
| L2 replay archive | **Operational**; 4,219 paired BTC trades and 32,209 L2-derived 1m bars |
| Range 1m impulse research | **Autotuned from 681 L2 replay trades** (339 long, 342 short) |
| Range 1m impulse LightGBM | **Runtime-compatible candidate trained**; not auto-installed |

### 2026-07-25 implementation status

- `paper-run --metalabel-mode observe` records model probability and bundle identity without changing conviction or entry eligibility.
- Every backend run stamps its run/export/strategy/execution/model identity and effective strategy, exit, risk, and cost configuration in `session_start`.
- The TUI reads `data/paper/decisions/decisions.jsonl`, isolates the latest run, and reconstructs only backend-confirmed trades, position, PnL, equity, and model annotations.
- Missing or invalid telemetry is shown as disconnected/stale/error; the TUI does not synthesize replacement trades.
- Research, sweep, backtest, autotune, and model-training CLI commands remain separate from both the backend daemon and TUI process.
- Candidate bundles are retained under `data/models/metalabel/candidates/`; neither 2026-07-25 Hypervelocity candidate was installed because chronological OOS log loss did not beat the constant-probability baseline.
- Paper cost resolution now accepts the canonical exported `funding_rate_1h` when the legacy `funding_rate_8h` field is null; this was validated with the real Hypervelocity export.

Candidate evidence:

| Side | Labels | WF folds | OOS log loss | Baseline | OOS AUC | Decision |
|------|-------:|---------:|-------------:|---------:|--------:|----------|
| Long | 11,193 | 9 | 0.6574 | 0.6344 | 0.5311 | Retain, do not promote |
| Short | 12,928 | 9 | 0.6457 | 0.6297 | 0.5237 | Retain, do not promote |

The current label builder samples true entry bars and applies the export's generic barrier exits. It is not yet empirically proven to match every native backend trade lifecycle; that audit is required before model promotion.

### 2026-07-25 L2 replay correction

The initial 2-long / 5-short range result below is a candle-only experiment and
does not represent the intended Hypervelocity order-book archive. The actual
source was found at
`/Users/gestas/Prototypes/orderbook-data/impulse_calibration_snapshot.sqlite.zst`:

- 3,226,438 BTC L2 feature snapshots.
- 4,219 causally paired BTC simulated trades.
- 32,209 reconstructed 1m L2-mid bars from 2026-05-05 through 2026-06-17.
- 590 uptrend-long, 1,200 downtrend-short, 339 range-long, and 342 range-short trades.

All four replay lanes received 100 trials under `SRS_HV1_NO_GATES`; negative
performance and low trade counts remained reported trial results. Valid boards:

- `data/logs/research/autotune_l2_replay_uptrend_long_20260725T081034Z.json`
- `data/logs/research/autotune_l2_replay_downtrend_short_20260725T081034Z.json`
- `data/logs/research/autotune_l2_replay_range_long_20260725T081034Z.json`
- `data/logs/research/autotune_l2_replay_range_short_20260725T081034Z.json`

Three standard 17-feature LightGBM bundles were trained from the L2-derived 1m
bars and recorded replay outcomes. They load through the existing backend
`Metalabeler` and are compatible with annotation-only inference:

| Lane | Samples | CV log loss | Baseline | AUC |
|------|--------:|------------:|---------:|----:|
| Uptrend long | 590 | 0.1175 | 0.1185 | 0.6733 |
| Downtrend short | 1,200 | 0.1357 | 0.1376 | 0.6147 |
| Range combined | 681 | 0.1082 | 0.1058 | 0.5773 |

Candidate timestamp: `20260725T081458Z` under
`data/models/metalabel/candidates/`. No candidate was automatically copied into
the shared installed-model root because each backend run must explicitly select
the model matching its strategy lane. This is configuration isolation, not a
performance gate. The range candidate was manually loaded through
`MetalabelConvictionProvider(mode="observe")`; it returned a probability while
preserving conviction 0.5 and `allow_entry=true`.

A second research-only comparison used the original sub-second recorder feature
contract. LightGBM outperformed the regularized temporal logistic alternative,
but neither beat its past-only constant baseline. Those candidates remain saved
and are not runtime-compatible until the backend emits the same sub-second
features.

### 2026-07-25 autotune evidence

All four final boards contain 100 successful trials and strict export bundles. Optuna
was unavailable, so the requested hybrid runs used the deterministic
`karpathy_random_adaptive` fallback.

| Strategy | Best return | Sharpe | Trades | Decision |
|----------|------------:|-------:|-------:|----------|
| Hypervelocity long | -87.06% | -19.98 | 2,193 | Do not promote |
| Hypervelocity short | -100.03% | -0.67 | 529 | Do not promote |
| Range impulse long | +0.13% | 1.04 | 2 | Candle-only diagnostic; superseded by L2 replay |
| Range impulse short | -0.12% | -0.64 | 5 | Candle-only diagnostic; superseded by L2 replay |

Valid final boards:

- `data/logs/research/autotune_hypervelocity_1m_scalper_long_1m_20260725T074341Z.json`
- `data/logs/research/autotune_hypervelocity_1m_scalper_short_1m_20260725T074334Z.json`
- `data/logs/research/autotune_impulse_1m_range_long_1m_20260725T074639Z.json`
- `data/logs/research/autotune_impulse_1m_range_short_1m_20260725T074641Z.json`

Do not use the earlier diagnostic boards ending in `T074042Z` (long) or
`T074035Z` (short). They predate fixes for native parameter types, venue leverage
clamping, and strict export wiring. The final boards above enforce BTC's 40x
strategy leverage cap and preserve boolean/integer parameter types.

The earlier candle-only LightGBM attempt stopped at 2 long / 5 short labels. That
technical failure is superseded by the replay pipeline and its 681-sample range
candidate; retain it only as diagnostic history.

---

## Acceptance bar (Albert — non-negotiable)

At a glance on ≥120×32:

- MODE + **DRY-RUN READY** / **LIVE REFUSED** / live danger
- Regime mix populated (not stuck on probe errors)
- Charts: price · activity · derived equity sparklines
- Ops-grade tape (time/mode/act/side/sub/qty/mark/fill)
- Read-only; no secrets; quit restores terminal

Guide: `docs/guides/acceptance-visual-and-holistic.md`  
Launch: `./target/release/hypervector-tui --data-root data`

---

## What shipped (Shadow Ops)

- `crates/hypervector-tui/src/read/cli_probe.rs` — launcher resolution
- `model/readiness.rs`, `model/series.rs` — dry-run chip + chart series
- Banner / gates / KPI charts / tape / regime empty states upgraded
- Demo tape: `data/paper/decisions/decisions.jsonl` (48 shadow rows) + fixture `decisions_shadow_demo.jsonl`

### Verify

```bash
cargo test -p hypervector-tui
cargo build -p hypervector-tui --release
uv run pytest tests/ -q -m "not network"
./target/release/hypervector-tui --data-root data
```

Last agent PTY markers: SHADOW OPS, DRY-RUN READY, LIVE REFUSED, regime dominant RANGE, tape n=48, no module-not-found.

---

## Locked decisions

| Topic | Choice |
|-------|--------|
| TUI role | Read-only Shadow Ops projection of authoritative backend telemetry |
| Control plane | Still read-only (no paper-run/live-run spawn) |
| Live | Fail-closed; never arm from TUI |
| GUI | Deferred post visual PASS |
| neural-trader | Rejected |

---

## NEXT

1. Run a bounded Hypervelocity shadow session with `--metalabel-mode observe` and visually confirm ledger/TUI parity.
2. Run each lane in bounded shadow/observe mode with its explicitly selected `20260725T081458Z` replay candidate and verify probability telemetry.
3. Add an explicit per-strategy model map if multiple lanes must run in one backend process; do not rely on one shared model root for different feature/outcome populations.
4. Continue time-series experiments with a small GRU or temporal CNN only as additional reported research; preserve purged/embargoed walk-forward evidence.
5. Albert visual walk (V* against Shadow Ops bar), then sign off before reopening the GUI epic.
