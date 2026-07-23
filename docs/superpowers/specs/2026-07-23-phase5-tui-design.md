# Design: Phase 5 — hypervector-tui (condensed financial ops terminal)

**Date:** 2026-07-23  
**Status:** **Approved by Albert 2026-07-23** — implement via plan below; no GUI until TUI holistic acceptance  
**Plan:** `docs/superpowers/plans/2026-07-23-phase5-tui.md`  
**Process:** engineering-software (Hyde) + superpowers brainstorming + Ratatui ecosystem research  
**Research pass:** [Terminal Trove](https://terminaltrove.com/) monitoring/financial catalog + second pass [Awesome Ratatui](https://github.com/ratatui/awesome-ratatui) widgets/utilities  
**Depends on:** Phase 4c CLI completeness (`2026-07-23-phase4c-cli-completeness-design.md`); Phase 3 UX note (`2026-07-22-phase3-paper-live-feed-design.md`)  
**Binary / crate name:** `hypervector-tui`  
**GUI:** **Deferred** until TUI is built and overall functionality across all surfaces is completed, reviewed, and tested holistically  
**Visual bar (locked):** [tickrs](https://github.com/tarkah/tickrs) for market-density data display craft

---

## 1. Intent

Ship a **best-in-class terminal monitoring surface** for hypervector: a condensed financial ops terminal with multi-card density, elite visual polish, and zero second strategy brain.

**One-sentence lock:**  
`hypervector-tui` is a **read-only projection** of CLI + ledger truth — mode, readiness, KPIs, decision tape, and **regime detection** — rendered as a high-density financial terminal with at most **two views**.

“GOAT” in prior notes meant quality bar only; **product name is `hypervector-tui`**, not GOAT.

---

## 2. Session decisions (locked)

| Topic | Choice |
|-------|--------|
| Control plane v1 | **Read-only** monitor (no start/stop/arm/kill from TUI) |
| Ship order | **TUI first and complete**; GUI only after holistic review |
| TUI stack | **[Ratatui](https://ratatui.rs/)** (Rust) + crossterm backend |
| Binary / crate | **`hypervector-tui`** |
| Views | **Ops floor + card focus** (max 2 screens) |
| Regime | **Visible** on floor + focus-drillable |
| Data model | Same ledgers/CLI as 4c: `data/paper/`, `data/live/`; no parallel truth DB |
| Brain | **No second strategy** — UI does not re-run alpha |
| Mode visibility | `execution_mode` (shadow / paper / live) always obvious |
| Network | Mainnet only; no testnet path |
| CLI | Remains scriptable; TUI does not replace CLI |
| neural-trader | Rejected |
| Critical actions | Deferred post-monitor acceptance; any future live control still requires arm + confirm |

---

## 3. Non-goals (Phase 5 TUI)

- GUI / web dashboard (post-holistic-acceptance only)  
- Start/stop daemons, live arm, venue submit, secret entry or display  
- Multi-tab navigation forests, research-ladder browser, sweep UIs  
- Reimplementing strategy / metalabel / fill models inside the TUI  
- Postgres / Redis / k8s  
- Naming the product “GOAT”

---

## 4. Actors & use cases (context)

| Actor | Goal |
|-------|------|
| Albert (ops) | At a glance: mode, gates, exposure/KPIs, last decisions, regime mix |
| Albert (debug) | Focus one card (tape or regime) without leaving the terminal |
| Agent / CLI | Still drives run lifecycle; TUI observes only |

**Primary use case:** open TUI while paper/shadow/live daemon runs elsewhere; continuous monitoring.

---

## 5. Requirements (testable)

Format: black-box *shall* / *must*. Tags for RTM-lite.

| Tag | Requirement |
|-----|-------------|
| SRS_HV5_NAME | Product binary **shall** be named `hypervector-tui` (crate may match). |
| SRS_HV5_READ_ONLY | TUI v1 **must not** start/stop daemons, arm live, place orders, or mutate policy/secrets. |
| SRS_HV5_CLI_PARITY | Displayed status/gates/report counters **shall** match the corresponding CLI JSON fields (`status`, `paper-check`, `live-check`, `paper-report`, `live-report`) within one refresh cycle of a successful read. |
| SRS_HV5_NO_SECRETS | TUI **must never** print or render secret values (wallet, API keys); only presence booleans if shown. |
| SRS_HV5_MODE_BANNER | Floor **shall** show `execution_mode` (shadow / paper / live) in a full-width banner that remains visible without scroll on a ≥24-row terminal. |
| SRS_HV5_TWO_VIEWS | Navigation **shall** provide at most two screens: Ops Floor and Card Focus; Esc returns from focus to floor. |
| SRS_HV5_CARDS | Floor **shall** include at least: Mode banner, Identity/gates, KPI strip, Regime, Decision tape, Honesty/health footer. |
| SRS_HV5_REGIME_VIEW | Regime card **shall** show label mix (up/down/range) and metrics consistent with `regime_detection_metrics` / `hypervector regime` output; **must not** invent a second detector algorithm. |
| SRS_HV5_TAPE | Decision tape **shall** bind to paper or live `decisions.jsonl` under data-root (mode-selected path); refuse cross-ledger paths. |
| SRS_HV5_LEDGER_ROOT | TUI **shall** honor `--data-root` (default project `data/`) matching CLI layout I2. |
| SRS_HV5_REFRESH | Floor **shall** auto-refresh on a configurable interval (default ≤2s for file-backed hot path; regime compute may be slower/on-demand). |
| SRS_HV5_EMPTY | Empty/cold states **shall** render designed empty cards (not blank panels or panics). |
| SRS_HV5_VISUAL_THEME | TUI **shall** use a documented truecolor semantic theme (mode colors, signed PnL, muted chrome); degrade gracefully on limited terminals. |
| SRS_HV5_QUIT | `q` or Ctrl+C **shall** restore terminal (raw mode / alt screen) via proper teardown (`color-eyre` / ratatui restore pattern). |

### Design goals (not hard requirements)

| Tag | Goal |
|-----|------|
| DG_HV5_BIG_KPI | Primary KPIs as large pixel text (`tui-big-text`) when space allows |
| DG_HV5_GARNISH | Card chrome via `ratatui-garnish` (padding/border/shadow) for btop-grade craft |
| DG_HV5_FX | Sparse tachyonfx transitions on mode change / focus enter only |
| DG_HV5_SKELETON | Skeleton/shimmer while first load or regime compute in flight |
| DG_HV5_TOAST | Lightweight toast on refresh error (no secrets in message) |
| DG_HV5_TERMPROFILE | Capability-aware colors via `termprofile` (truecolor when available) |
| DG_HV5_STACKED_REGIME | Regime history as stacked bar when label series present |
| DG_HV5_OPALINE | Optional token theme engine if custom theme.toml proves heavy |
| DG_HV5_PY_SHIM | Optional later: `hypervector tui` launches the binary |

---

## 6. Visual research summary (dopamine stack)

**Sources (final pass):**

- [Ratatui](https://ratatui.rs/) v0.30+, [built-in widgets](https://ratatui.rs/showcase/widgets/), [third-party widgets](https://ratatui.rs/showcase/third-party-widgets/)
- [Awesome Ratatui](https://github.com/ratatui/awesome-ratatui) (widgets + utilities, second full pass)
- [Terminal Trove](https://terminaltrove.com/) — especially [Monitoring](https://terminaltrove.com/categories/monitoring/) + financial tools
- [tachyonfx](https://github.com/ratatui/tachyonfx); btop-class design systems

### 6.1 What “high dopamine” means here (ops, not carnival)

Priority order:

1. **Clarity under stress** — mode + kill-relevant gates first  
2. **Dense but readable** — Bloomberg/btop density, not sparse form UIs  
3. **Semantic color that moves** — PnL sign, regime, live danger  
4. **Motion only when it informs** — refresh throb, mode flash, skeleton load  
5. **Craft details** — rounded/garnished cards, aligned numbers, big KPIs, empty states  

Anti-patterns (reject): default grey boxes with unstyled dumps; menu shells wrapping CLI; rainbow gradients without meaning; full-screen rain/particles; multi-tab research mazes; dependency bloat without pixel payoff.

### 6.2 Terminal Trove — peer tools (visual / product bar)

Catalog scan of [terminaltrove.com](https://terminaltrove.com/) monitoring + stock/crypto tools. These are **UX references**, not dependencies (many are Go/C++).

#### Canonical peer (locked)

| Tool | Role |
|------|------|
| **[tickrs](https://terminaltrove.com/tickrs/)** ([GitHub](https://github.com/tarkah/tickrs), Rust) | **Primary visual standard for market-density data display.** Albert lock: no better reference found for this class of terminal market UI. Steal: multi-series charts, summary collapse (big change/bid/ask/range readouts), volume pane, smart timeframes, adjustable cadence, dense but legible sparklines/candles — **without** becoming a Yahoo watchlist clone. Our data is ops/ledger/regime truth; the *display craft* targets tickrs. |

#### Secondary peers

| Tool | TT page | Steal for hypervector-tui |
|------|---------|---------------------------|
| **[btop](https://terminaltrove.com/btop/)** | Monitoring | Card density, notched titles, braille graphs, semantic gradients, right-aligned metrics |
| **[bottom](https://terminaltrove.com/bottom/)** | Monitoring | Clean multi-panel layout, restrained chrome, resize behavior |
| **[ticker](https://terminaltrove.com/ticker/)** (Go/Charm) | Financial | Holdings/snapshot glance, themes, refresh — secondary to tickrs |
| **[cointop](https://terminaltrove.com/cointop/)** | Crypto | Sortable table density + theme depth — tape layout secondary |
| **[mop](https://terminaltrove.com/mop/)** | Stock | Minimal hacker tracker — **anti-bloat** reminder |
| **[k9s](https://terminaltrove.com/k9s/)** | Ops | Mode/context always visible; keyboard-first |
| **[zenith](https://terminaltrove.com/zenith/)** / **[gping](https://terminaltrove.com/gping/)** | Graphs | Continuous sparkline/graph feel for live series |
| **[sampler](https://terminaltrove.com/sampler/)** / **[ttyplot](https://terminaltrove.com/ttyplot/)** | Plotting | “Any metric as graph” — KPI sparklines from decision counters |
| **[wtf](https://terminaltrove.com/wtf/)** | Dashboard | **Do not copy** module soup; fixed card set only |
| **[otel-tui](https://terminaltrove.com/otel-tui/)** | Telemetry | Health/freshness footer inspiration |

**TT takeaway:** **tickrs** is the bar for how series + KPIs + density should *look*. **btop/k9s** inform ops mode banners and card packing. We are not a watchlist product — same craft, hypervector truth.

### 6.3 Awesome Ratatui — second-pass crate decisions

Beyond the first shortlist, these crates earned upgrades after re-reading Awesome Ratatui:

| Crate | Why it matters | Decision |
|-------|----------------|----------|
| **[ratatui-garnish](https://crates.io/crates/ratatui-garnish)** | Decorate any widget: multi-border, padding, shadow, title placement; serde-able garnish sets for themes | **Adopt for card chrome** — highest ROI craft vs hand-rolled Block nesting |
| **[termprofile](https://github.com/aschey/termprofile)** | Detect truecolor / capability; degrade styles safely | **Adopt** — required for “works great on Ghostty/Kitty, still ok on basic” |
| **[tui-popup](https://github.com/joshka/tui-popup)** (tui-widgets suite) | Centered error/help overlay without reinventing | **Adopt** for help (`?`) and non-secret errors |
| **[tui-overlay](https://crates.io/crates/tui-overlay)** | Drawers/toasts/popovers from one primitive | **Optional** — prefer popup + toaster if both not needed |
| **[ratatui-stacked-bar](https://github.com/zeqianli/ratatui-stacked-bar)** | Stacked area over time | **Adopt for regime history** (up/down/range composition over bars) when series present |
| **[opaline](https://crates.io/crates/opaline)** | Token theme engine, gradients, 20 builtins, theme picker | **Optional (DG)** — ship custom semantic theme first; opaline if theme expansion wanted |
| **[ggsci-ratatui](https://crates.io/crates/ggsci-ratatui)** | Sci-fi / scientific palettes | **Optional** accent only |
| **[rat-focus](https://docs.rs/rat-focus) / [rat-event](https://docs.rs/rat-event)** (rat-salsa family) | Production focus + event traits | **Evaluate in 5a** — use if focus across cards is cleaner than hand-rolled; not a full rat-widget rewrite |
| **[ratatui-interact](https://github.com/Brainwires/ratatui-interact)** | Focus + mouse | **Optional** mouse later; keyboard first |
| **[ratatui-comfy-toaster](https://crates.io/crates/ratatui-comfy-toaster)** / **ratatui-toaster** | Toast engine | **Adopt one** for refresh/regime failures (no secrets) |
| **[tui-shimmer](https://github.com/vinhnx/tui-shimmer)** | Shimmer text | **Optional** alongside skeleton |
| **[color-to-tui](https://crates.io/crates/color-to-tui)** | Hex → Color | **Adopt** if theme.toml uses hex |
| **hyperrat** (OSC 8 links) | Clickable paths | **Optional** — link data-root path in footer |
| **tui-nodes / wireframe / globe / rain** | Novelty graphs | **Reject** for v1 |
| **Full rat-widget / rat-salsa app shell** | Heavy input-centric suite | **Reject as app framework** — too much surface; cherry-pick focus/event only if needed |

### 6.4 Built-in Ratatui widgets — role map

| Widget | Use in hypervector-tui |
|--------|------------------------|
| **Block** + `border::ROUNDED` (+ garnish) | Card chrome; focused card stronger border/title color |
| **Sparkline** | Decision rate / notional / regime path mini-history |
| **Gauge / LineGauge** | Max notional utilization; readiness continuum |
| **BarChart** | Action mix fallback for regime mix |
| **Chart** | Focus: PnL/path if ledger series cheap |
| **Table** (+ state) | Decision tape; focus scroll/select |
| **Paragraph / Line / Span** | Labels, badges, honesty footer |
| **Scrollbar** | Long tape / focus lists |
| **Clear** | Underlays for popup |
| **Canvas** | Only if braille graph needs more than Sparkline |
| **Tabs** | **Avoid** as primary nav (two-view lock) |

### 6.5 Locked dependency tiers

| Tier | Crates |
|------|--------|
| **Required** | `ratatui` + `crossterm`, `color-eyre`, `tui-big-text`, `palette` (or truecolor styles), `tachyonfx` (sparse), `throbber-widgets-tui`, `termprofile` |
| **Adopt (v1 polish)** | `ratatui-garnish`, `tui-piechart` and/or `ratatui-stacked-bar` (regime), `tui-skeleton`, `tui-popup`, one toaster, `tui-scrollview` if focus overflows, `color-to-tui` if hex themes |
| **Optional (DG)** | `opaline`, `ggsci-ratatui`, `tui-logger` (focus only), `tui-overlay`, `rat-focus`/`rat-event`, mouse via `ratatui-interact`, OSC8 links |
| **Reject v1** | `ratatui-image` splash, `tui-rain`/confetti, textarea/menus/forms, `tui-realm`/`ratatui-kit` as frameworks, novelty 3D widgets |

### 6.6 Dopamine moments (designed, not accidental)

| Moment | Technique |
|--------|-----------|
| App open | Skeleton cards → tachyonfx coalesce into live data |
| Mode = LIVE | Banner high-contrast + single pulse; steady LIVE after |
| Fresh decision | Tape row highlight fade (short) |
| Regime composition | Pie **or** stacked-bar of up/down/range; history stack if series |
| Stale data | Health footer warning; age seconds bold |
| Focus enter | Short fade/slide (≤200–300ms); Esc reverse |
| Refresh / regime compute | Corner throbber only |
| Soft failure | Toast / popup — never secret material |

---

## 7. Architecture

### 7.1 Context (IEEE 1016 Context viewpoint — HV5_SDD_001)

```text
                    ┌─────────────────────┐
  CLI processes ───►│ hypervector CLI JSON │── status / checks / reports / regime
                    └──────────┬──────────┘
                               │ subprocess or documented JSON contract
                               ▼
  data/paper|live ──► ReadModel (Rust) ──► Theme + Cards ──► ratatui Frame
  decisions.jsonl              │                    │
  layout mtimes                │                    └─ tachyonfx (sparse)
                               │
                        no strategy, no orders, no secrets
```

### 7.2 Hybrid read model (recommended)

| Path | Source | Cadence |
|------|--------|---------|
| Hot | Rust parse `decisions.jsonl`, mtimes, path existence | ≤1–2s |
| Snapshot | CLI `status`, `paper-check`, `live-check`, report summaries | 2–5s or on `r` |
| Regime | Prefer export/`regime` artifact if fresh; else on-demand `hypervector regime` (or last metrics cache) | On open + `R` / slower timer |
| Forbidden | Silent reimplementation of EMA detector with different params | — |

### 7.3 Logical structure (HV5_SDD_002)

```text
crates/hypervector-tui/
  src/
    main.rs          # terminal setup, color-eyre, run loop
    app.rs           # App state, view enum (Floor | Focus)
    theme.rs         # semantic colors, borders
    model/           # snapshots: Status, Gates, Tape, Regime, Health
    read/            # file readers + CLI adapters
    ui/
      floor.rs       # card layout
      focus.rs       # single-card expand
      cards/         # mode, gates, kpi, regime, tape, health
    effects.rs       # tachyonfx orchestration (optional feature)
```

### 7.4 Views

**View 1 — Ops Floor**

```text
┌──────────────────────────────── MODE: SHADOW | PAPER | LIVE ─ mainnet ─┐
│ IDENTITY / GATES          │  KPI STRIP (big text)                      │
│ data-root · can_start     │  decisions · submitted · notional gauge    │
│ enabled/armed (bools)     │  sparklines                                │
├───────────────────────────┴────────────────────────────────────────────┤
│ REGIME (pie/bars + pct up/down/range + age)  │ DECISION TAPE (table)   │
│                                              │ … last N rows           │
├──────────────────────────────────────────────┴─────────────────────────┤
│ honesty · paper no_submit · live fail-closed · refresh age · keys      │
└────────────────────────────────────────────────────────────────────────┘
```

**View 2 — Card Focus**  
Enter on focused card → full-height Regime metrics **or** Decision tape (scroll/filter) **or** Gates checklist. Esc → Floor.

Keys (v1): `Tab`/arrows focus card · `Enter` focus view · `Esc` back · `r` refresh · `p`/`l` paper vs live tape root · `q` quit. Footer shows only active hints.

### 7.5 Regime binding

- Detector remains Python: `detect_regime_ema` + `regime_detection_metrics` (labels up/down/range; **not a trade gate**).  
- TUI displays: `pct_up`, `pct_down`, `pct_range`, `flip_rate`, `mean_duration`, `n_bars`, sample counts, params (fast/slow), provenance age.  
- Floor: compact pie/bar + dominant label badge.  
- Focus: full metrics table + optional sparkline of recent labels if series available.

---

## 8. Safety model

| Rule | Enforcement |
|------|-------------|
| Read-only | No process spawn of `paper-run` / `live-run`; no writes under data roots except optional local UI cache (not truth) |
| Secrets | Never read key material into UI state; only env-presence flags via check JSON |
| Live danger | LIVE banner always high contrast; still cannot arm from TUI |
| Cross-ledger | Paper tape path refuses live/; live path refuses paper/ |

---

## 9. Success bar

1. Offline automated tests: model parsers + golden JSON fixtures from CLI shapes; UI unit tests for mode banner presence; no network required.  
2. Manual: `hypervector-tui` on cold data-root shows designed empties; with paper decisions file, tape updates; regime card shows metrics after compute/cache.  
3. Visual review (Albert): density and theme meet **tickrs** bar for series/KPI display craft and **btop/k9s** for ops card packing/mode visibility — not “default ratatui demo skin.”  
4. Terminal always restored on panic/quit; truecolor path exercised on a modern emulator.  
5. HANDOFF updated; GUI remains deferred until holistic acceptance of TUI + CLI surfaces.

---

## 10. RTM-lite

| Requirement | Design view | Verify |
|-------------|-------------|--------|
| SRS_HV5_* | HV5_SDD_001 Context + HV5_SDD_002 Logical + Interaction floor/focus | unit + manual |
| SRS_HV5_CLI_PARITY | Read adapters | fixture parity tests |
| SRS_HV5_REGIME_VIEW | Regime card | fixture from regime JSON |
| SRS_HV5_VISUAL_THEME | theme.rs | screenshot / VHS optional later |

---

## 11. Implementation staging (plan outline; formal plan after spec approve)

| Stage | Deliverable |
|-------|-------------|
| **5a** | Crate scaffold, theme, floor chrome, status/gates bindings |
| **5b** | Decision tape + KPI big-text + sparklines |
| **5c** | Regime card + focus view |
| **5d** | Effects/skeleton/throbber polish + empty states + tests |
| **Gate** | Holistic review: CLI + TUI parity, visual sign-off |
| **Later** | GUI (separate design); optional critical control plane |

---

## 12. Open items (none blocking design)

| Item | Default if unset |
|------|------------------|
| Launch via `cargo run -p hypervector-tui` only vs later `hypervector tui` shim | Binary first; shim optional |
| Default tape mode when both paper and live have data | Prefer last-written mtime; override with `p`/`l` |
| Regime auto-compute on open | Yes if cache missing and network/cache allows; else empty + hint |

---

## 13. Approval

**Approved by Albert:** 2026-07-23.  
**Plan:** `docs/superpowers/plans/2026-07-23-phase5-tui.md` — execute next session.  
**HANDOFF:** updated for implementation (GUI still deferred).
