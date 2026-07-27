# HANDOFF — hypervector

**Saved:** 2026-07-27 — Hyperliquid-native 90-day archive, trade-aware maker replay, and faithful shadow continuity.
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `main`
**Prefer this HANDOFF over agentmemory for phase status.**

---

## Status (read this first)

| Layer | State |
|-------|--------|
| Phase 1–4c CLI pipeline | **Done** |
| Phase 5 thin projector TUI | **Superseded** by Shadow Ops Floor |
| Probe Python resolution | **Fixed** (`.venv` / `HYPERVECTOR_PYTHON` / `uv run`) |
| Shadow Ops Floor (readiness + charts + regime auto + tape craft) | **Implemented** — agent PTY evidence green |
| Automated QA | **Changed surface green**; Rust 8/8, Python 400/400 excluding one pre-existing Ray worker termination |
| Visual PASS (human) | **NEXT — Albert** |
| Holistic CLI↔TUI | **Agent assist PASS**; human on-screen confirm |
| GUI | **Deferred** until Shadow Ops visual PASS |
| Hypervelocity execution authority | **Python backend only**; TUI consumes ledger telemetry |
| Hypervelocity execution contract | **One-way bidirectional BTC 1m, 70% margin, 40x, one 8% margin target, post-only** |
| Hypervelocity shadow execution | **`nautilus_event_v1` active in faithful config; public L2/trade evidence only** |
| Hypervelocity entry states | **Trend up/down or direction-confirmed breakout only; no range entries** |
| Hypervelocity model | **Observe-only enforced**; older directional candidates remain selected, while the 90-day archive assessment was insufficient for retraining |
| Hypervelocity 180d autotune | **Completed**; best long/short candle trials remained materially negative after costs |
| L2 replay archive | **Operational**; 4,219 paired BTC trades and 32,209 L2-derived 1m bars |
| Range 1m impulse research | **Autotuned from 681 L2 replay trades** (339 long, 342 short) |
| Range 1m impulse LightGBM | **Runtime-compatible candidate trained**; not auto-installed |
| 0xArchive venue evidence | **90-day BTC audit and full replay PASS**; 2,160 hourly L2/trade pairs (4,320 individual evidence bundles) |

### 2026-07-27 Hyperliquid-native archive and replay update

- A resumable, bounded 0xArchive importer now stores immutable gzip evidence,
  manifest identity, request IDs, byte counts, and SHA-256 checksums for native
  Hyperliquid L2 books and public trades. Participant-side fills are preserved
  raw and normalized to one public match per venue `trade_id` using the
  `crossed=true` taker row.
- The exact 90-day BTC window is `2026-04-28T00:00:00Z` through
  `2026-07-27T00:00:00Z`: 4,320/4,320 expected hourly bundles, 12,013,542 L2
  snapshots, 36,591,780 public trades from 73,289,898 participant fills, and
  9,465,157,545 declared evidence bytes. The durable audit is
  `data/logs/research/oxa_btc_90d_archive_audit.json`.
- Every declared evidence checksum passed. A streaming cross-hour check found
  zero timestamp regressions, zero conflicting repeated identities, and ten
  exact trade-ID repeats at inclusive hourly boundaries; replay validation
  deduplicates those exact repeats and rejects conflicts.
- Twenty-one book hours are complete vendor responses with zero L2 rows; all
  21 independently reproduced as zero with new request IDs. Trade coverage is
  nonzero for every hour. These remain explicit vendor coverage gaps and are
  not synthetically filled.
- The strict Hyperliquid 1m research cache contains 129,600 exact-cadence bars:
  129,532 native venue bars plus 68 explicit zero-volume `hl_gap_fill` bars.
  Raw vendor candles remain unchanged.
- Maker replay can now compare touch, one-tick book-through, and cumulative
  public-trade-through fills. Trade-through is report-only and causal, but
  queue rank and cancellations remain unknowable from public historical data.
- A July 26 measured comparison produced five touch/through submissions and
  six trade-through submissions; both completed three trades, left one open,
  and ended at `$11,496.77`. This is one sample, not proof of general edge.
- The full-window streaming replay completed across all 2,160 hourly pairs and
  exactly 12,013,542 L2 snapshots. Public-trade-through consumed 36,591,762
  deduplicated prints; the 18-row difference from the archive audit is exact
  inclusive-boundary duplicate removal, not missing evidence. The report and
  conservative labels are `hypervelocity_oxa_90d_fill_comparison.json` and
  `hypervelocity_oxa_90d_labels.parquet` under `data/logs/research/`.
- Touch, one-tick-through, and trade-through produced 46/53/67 submissions,
  39/50/40 completed targets, and one right-censored open long each. Their
  path-dependent entry identities diverged: only 2 of 125 nominal signals had
  resolved outcomes under all three assumptions; 123 were disagreements. The
  two labels were one long negative and one short positive, so each directional
  training lane was one-class. Structured `insufficient_resolved_labels`
  assessments were written under
  `data/models/metalabel/candidates/hypervelocity-oxa-90d-runtime-{long,short}-20260727/`.
- No new model was fabricated or installed. The historical maker comparator
  does not model funding, liquidation, authentic queue rank, cancellations, or
  local receipt latency. Each fill path eventually held a 40x long that never
  reached its target, preventing later entries; therefore its compounded final
  equity is a fill-assumption bound, not a credible portfolio forecast. The
  live event-shadow path separately models funding, isolated liquidation,
  partial fills, queue-ahead, latency, and backstop behavior.
- `execution_evidence_uncertain` telemetry now derives marked equity and
  unrealized PnL from the same event-account snapshot. The regression case of
  a long marked below entry previously emitted zero unrealized PnL.
- Final readiness verification passed 746 offline Python tests (4 network
  tests deselected) and all 27 Rust TUI integration tests. A real unified
  `hypervelocity-tui` smoke created one backend run (`bb6d6f9276de`), populated
  live 5m/15m regime and five-level L2 telemetry, and recorded zero venue submit
  or place attempts. Normal `q` exit reaped the TUI and backend with exit zero.
- The pre-readiness ledger/log are recoverable under
  `data/backups/shadow_reset_20260727T060828Z`. The bounded smoke is recoverable
  under `data/backups/shadow_reset_20260727T060946Z`. Active decisions and log
  files are zero bytes, so the next unified launch starts a new `$10,000`
  shadow portfolio; archive-audit and strict-candle-cache hashes are unchanged.

### 2026-07-25 implementation status

- TUI projection now recognizes canonical `TREND_UP`/`TREND_DOWN`/`BREAKOUT`/`TRANSITION` labels and uses live backend `regime_observation` history for the distribution bar. It falls back to session identity for 40x leverage and reports net trade PnL—including entry/exit fees and funding—as a percentage of actual allocated margin.
- Normal TUI/backend quit no longer resets shadow state. The backend resumes the latest filled Hypervelocity run from its ledger, including initial cash, realized PnL, open position, and last exit cooldown; only the explicit backed-up reset command starts a fresh portfolio.
- Closed journal trades are selectable and expose Eastern entry/exit times, entry/exit 1m/5m/15m regime context, entry/exit fees, funding, gross PnL, and net PnL. The active-position box reports paid entry fee, accrued funding, and estimated maker exit fee.
- The dashboard now allocates enough height to display five backend-published bid levels and five ask levels. Labels match the implemented composite: authoritative 5m primary, direction-confirmed 1m+5m breakouts, and 15m non-veto context. A 1m trend cannot override 5m `RANGE`, `TRANSITION`, or `UNKNOWN`.
- `hypervelocity-shadow-reset` is dry-run by default. `--yes` obtains the backend singleton lock, creates a timestamped audit backup, and clears only shadow decisions and the backend text log; cache, regime snapshots, models, and configuration remain intact.
- `hypervelocity-tui` is the single operator entry point: Python supervises the no-submit backend, waits for fresh ledger telemetry, runs the Rust TUI in the foreground, and terminates/reaps the backend child when the TUI exits. Backend logs are isolated from the terminal screen under `<data-root>/paper/hypervelocity-shadow.log`.
- A per-data-root advisory lock refuses a second Hypervelocity backend, preventing two independent BTC positions or competing latest-run telemetry.
- `hypervelocity-shadow-run --config configs/hypervelocity_faithful.toml` starts one bidirectional backend. It permits one signed BTC position, cannot reverse while open, and may switch sides only after the 8% margin target closes the prior trade.
- Startup validates current public Hyperliquid BTC metadata. On 2026-07-25 the live response reported `szDecimals=5`, `maxLeverage=40`, and hourly funding `0.0000125`.
- Tier-0 fees are explicit: maker `0.00015`, taker `0.00045`. Qualified post-only fills use maker fees and no invented slippage; funding refreshes every 60 seconds and applies only at hourly settlement boundaries while a position is open.
- Hyperliquid price ticks are calculated from venue precision rules rather than a permanently fixed `$1` assumption. At the observed BTC price near `$64k`, the effective tick is `$1`.
- Verification: 439 offline Python tests passed, 20 Rust TUI integration tests passed, targeted Ruff passed, the TUI binary built, TOML parsed, and the prior real PTY launch/quit smoke wrote unified no-submit telemetry and reaped the backend child.
- The unified shadow state was reset on 2026-07-25 after the first observation window. The prior decisions and backend log are recoverable under `data/ops/hypervelocity_visual/backups/shadow_reset_20260725T141543Z`; active decisions/log files were verified at zero bytes while cache and regime-snapshot checksums remained unchanged.

- `paper-run --metalabel-mode observe` records model probability and bundle identity without changing conviction or entry eligibility.
- Every backend run stamps its run/export/strategy/execution/model identity and effective strategy, exit, risk, and cost configuration in `session_start`.
- The TUI reads `data/paper/decisions/decisions.jsonl`, follows the persistent filled Hypervelocity run across supervised restarts, and projects only backend-confirmed trades, position, PnL, equity, and model annotations.
- Missing or invalid telemetry is shown as disconnected/stale/error; the TUI does not synthesize replacement trades.
- Research, sweep, backtest, autotune, and model-training CLI commands remain separate from both the backend daemon and TUI process.
- Candidate bundles are retained under `data/models/metalabel/candidates/`; neither 2026-07-25 Hypervelocity candidate was installed because chronological OOS log loss did not beat the constant-probability baseline.
- Paper cost resolution now accepts the canonical exported `funding_rate_1h` when the legacy `funding_rate_8h` field is null; this was validated with the real Hypervelocity export.

### 2026-07-26 restart-fidelity update

- The canonical unified launch/reset root is now `data`. Screen 3 projects the
  resolved root from backend `session_start` telemetry and renders the complete
  shell-quoted same-root reset command.
- Shadow resume now validates the portfolio equity identity and a canonical
  fingerprint of execution-affecting strategy, risk, exit, order, and position
  policy. An incompatible open position or pending entry fails closed; a flat
  portfolio may adopt the new profile and records the prior fingerprint.
- An unmatched `submit_entry` is durable before the first fill. Restart restores
  its side, quantity, exact limit, submission time/TTL, conviction, and model
  annotations; a later cancel or fill remains authoritative.
- If active state spans downtime, only completed `source=hl` candles after the
  persisted state timestamp may reconcile it. Replay can manage that existing
  maker order or fixed target but cannot synthesize a new entry. Hourly funding
  uses public `fundingHistory` observations and fails before replay when a
  required settlement row is absent.
- `strict_hl_only` now bypasses and refreshes an incompatible mixed-venue cache
  rather than silently returning it.
- Verification on 2026-07-26: 457 offline Python tests and all 20 Rust TUI
  integration tests passed; targeted Ruff and formatting checks passed; the
  `tui-regime-detector` binary built successfully.
- A read-only audit of the current `data` ledger selected run `7e3887db6340` as
  the durable portfolio: flat, no pending maker entry, `$10,000` equity, state
  timestamp `2026-07-26T02:13:00Z`, and compatible with the faithful profile.

### 2026-07-26 event-shadow friction review

- The faithful backend now opens a bounded public Hyperliquid mainnet WebSocket
  feed for L2 and trades, archives normalized events before consumption, and
  routes them through the pure Hypervelocity coordinator and no-submit shadow
  port. Candle data still drives regime decisions but has no fill authority.
- The event port models submit/cancel latency, ALO rejection, displayed
  queue-ahead, partial fills, proportional reduce-only targets, maker fees,
  hourly funding, isolated maintenance margin, and explicit stream gaps.
- Restart restores partial entry and target orders, costs, order IDs, and
  episode/cooldown state. Because historical queue priority is unknowable,
  restarted orders are explicitly requeued behind current displayed liquidity.
- Liquidation now charges configured taker commission, records zero separate
  clearance fee, and is identified as a venue-enforced market close. Funding is
  applied before the boundary mark check.
- The next no-submit friction batch now consumes and archives continuous
  `activeAssetCtx` mark/oracle/funding observations, walks fresh displayed L2
  for liquidations, applies the documented >$100,000 20% partial path and
  30-second cooldown, and models isolated backstop transfer below two-thirds of
  maintenance after insufficient market depth. Every component is stamped in
  the session identity and faithful TOML; no live order client is constructed.
- Batch-2 verification: 592 offline Python tests passed with 4 network tests
  deselected; all 23 Rust TUI tests passed; changed-file Ruff/format, Cargo
  format, CLI status, TOML/profile validation, Python compilation, diff checks,
  and a bounded public-mainnet L2/trades/`activeAssetCtx` smoke passed.
- Full batch-2 review:
  `docs/reviews/2026-07-26-hypervelocity-friction-batch2-review.md`.
- Verification: 579 offline Python tests passed with 4 network tests deselected;
  all 23 Rust TUI integration tests passed; CLI status, TOML/profile parsing,
  targeted Ruff/format, Python compilation, Cargo formatting, and diff checks
  passed. Coverage instrumentation remains unverified because its Python 3.13
  run caused a NumPy double-load error despite normal pytest passing.
- Full review: `docs/reviews/2026-07-26-hypervelocity-event-shadow-review.md`.

### 2026-07-25 faithful-contract validation

The recorded strategy facts supplied by Albert supersede the speculative
32%-risk, ATR-stop, and split-exit hypotheses in `docs/external`. The backend
now enforces the observed baseline:

- BTC 1m only, with separate long and short strategy IDs.
- Entries only during canonical `TREND_UP`, `TREND_DOWN`, or a direction-confirmed real breakout.
- `RANGE`, `TRANSITION`, `UNKNOWN`, and directionless breakout create no entry.
- 70% of current equity is margin at 40x (28x-equity notional).
- One 8% return-on-margin target (0.2% BTC price move), with no invented stop or split exit.
- Post-only entry and target orders. Streaming paper execution retains pending orders and requires one-tick-through evidence; missing L2 falls back to a causal next-completed-bar through test.
- LightGBM and temporal/logistic candidates are annotations only. CLI requests to scale or filter Hypervelocity are converted to `observe`, and the effective policy is stamped in the backend ledger.
- TUI trade, position, PnL, equity, risk, exit, model, and order-execution fields come from the backend ledger. Display fallback values are fixed-contract labels only and never execute trades.

Corrected causal regime evaluation (candle-open timestamps become available one
minute later) used 35 unique recorded entry decisions:

| Candidate | Train exact | Holdout exact | Total exact | RANGE/no-entry at logged entries |
|-----------|------------:|--------------:|------------:|---------------------------------:|
| Scalar-score winner (trial 91) | 21/24 | 9/11 | 30/35 (85.7%) | 1 |
| Selected zero-false-range candidate (trial 248) | 19/24 | 10/11 | 29/35 (82.9%) | 0 |

Confidence is high for those counts on the evaluated cache and medium for
general range accuracy: the manual log contains positive entries, not labeled
negative/range intervals, and 11.9% of the evaluated candles came from
Hyperliquid while the remainder came from Binance rather than the original
recording venue. A point-in-time venue-matched labeled range set would update
this conclusion.

The bounded order-book replay used 32,609 BTC L2 snapshots and produced 8
filled entries, 7 completed trades, one open position, and one expired entry
from a $71.23 flat-start account; final equity was about $98.64 after 1.5 bp
maker fees. Touch and one-tick-through bounds agreed on those fills, but queue
position, cancellations, partial fills, and the already-open real position at
the beginning of coverage remain unknown. Therefore exact timestamp-for-
timestamp strategy replication is not yet proven.

The faithful replay annotation comparison used 4,219 overlapping rows and four
purged/embargoed chronological folds:

| Model | OOS log loss | OOS Brier | Decision |
|-------|-------------:|----------:|----------|
| Constant past-only baseline | 0.13747 | — | Reference |
| LightGBM | 0.28282 | 0.07958 | Retain only; did not beat baseline |
| Current-row logistic | 0.68939 | 0.24199 | Retain only; did not beat baseline |
| Three-event lag logistic | 0.70004 | 0.23935 | Retain only; did not beat baseline |

A TCN remains a future research option, not a missing runtime dependency:
PyTorch/TensorFlow are absent and the effective independent sample count is
materially lower than 4,219 because windows overlap. It should be tested only
after venue-matched labels and replay fidelity are stronger.

Verification evidence:

- `cargo test -p hypervector-tui`: 8 passed.
- `uv run pytest tests/ -q -m "not network" -k "not ray_adapter_executes_through_vectorbt"`: 400 passed, 5 deselected.
- The excluded pre-existing VectorBT/Ray adapter test terminated its worker process before producing a result in this host environment; it is unverified, not counted as passed.
- All changed Python files pass targeted Ruff. Repository-wide Ruff still reports 37 pre-existing issues in unrelated modules.
- `status` and `paper-check` passed: shadow is no-submit, live remains unarmed/fail-closed, and no secret values were printed.
- Both TOML profiles parse successfully.
- A bounded 500-bar shadow run on cached BTC 1m data produced two pending entries, two causal maker entry fills, one fixed-target close, and zero submit attempts. Its ledger stamped 70% margin, 28x notional, 40x/8%, no stop, post-only, and one-tick-through execution.

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

### 2026-07-25 venue-matched shadow reconciliation pilot

The backend now supports a report-only
`hypervelocity-shadow-compare` command. It selects explicit shadow run IDs,
defines the evidence window from live `regime_observation` rows, matches
same-side entries one-to-one within a reported tolerance, and reports timing,
direction, RANGE-at-real-entry, maker submit-to-fill, exit, and price
discrepancies. A non-overlapping real log fails explicitly instead of
returning a misleading zero-match result.

Live daemon warm-up is now observation-only: historical bars seed the rolling
indicator buffer but cannot create historical shadow orders or alter starting
equity. Offline replay behavior remains unchanged. Capped real REST sessions
also wait for completed bars; only injected test/replay feeds use the
three-empty-poll exhaustion rule.

First isolated pilot root:
`data/experiments/shadow_20260725T1324Z`.

- Warm history: 5,193 BTC 1m bars, 100% Hyperliquid provenance, zero detected
  gaps, ending 2026-07-25 13:24 UTC.
- Long run `3904919d8b03` and short run `e2f4043b6594`: five live observations
  each from 13:26 through 13:30 UTC, zero fills, zero venue submit/place
  attempts, clean `max_live_bars` stop.
- All ten observations were `TREND_UP`; long eligibility was 5/5 and short
  eligibility was 0/5. The long lane created one post-only `submit_entry`, but
  no one-tick-through fill occurred before the window ended.
- L2 recorder captured 71 Hyperliquid snapshots from 13:24:42 through
  13:27:54 UTC, then stopped on HTTP 429. Maker evidence is therefore partial,
  not a complete-window validation.
- The available manual real-strategy log ends at 2026-07-24 15:06 UTC. The new
  comparator correctly refused it because it does not overlap the July 25
  shadow window. A same-window real log remains required for a match score.

For the next paired collection, use a slower REST cadence (for example 10
seconds for the two shadow daemons and 5 seconds for L2 recording) to reduce
HTTP 429 risk. Rate limits, zero trades, performance, and mismatch counts remain
reported observations rather than implicit gates.

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

1. Export a complete real-strategy log covering a new paired shadow UTC window; rerun collection at the documented lower request cadence.
2. Run `hypervelocity-shadow-compare` with both explicit run IDs and retain the JSON report. Use mismatches to tune detector unknowns, never the fixed 70%/40x/8% facts.
3. Visually confirm the same backend run IDs, pending-order, fill, target, equity, and model telemetry in the TUI.
4. Add a per-strategy model map before testing multiple annotation candidates in one backend process.
5. Consider a TCN only after the faithful label set beats simple past-only baselines and has enough independent events.
