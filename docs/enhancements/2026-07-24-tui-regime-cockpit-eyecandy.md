# Enhancement Spec: Visual Feedback & Eye Candy for `tui-regime-detector`

**Date:** 2026-07-24
**Status:** Proposed (spec for review, not implemented)
**Target:** `crates/hypervector-tui` (bin `tui-regime-detector`)
**Scope:** Rendering/UX only. Zero changes to the regime engine, snapshot schema producers, or policy logic. Regime output remains pure research telemetry (SRS_HV1_REGIME, SRS_HV1_REGIME_NO_GATE); the TUI displays, never gates.

---

## 1. Current state (audited)

- ratatui `0.29` (`all-widgets`), crossterm `0.28`; screens: [1] Regime Detection, [2] Strategy Policy; header/footer bars; event log table; event modal; help overlay.
- Visuals today: one `Gauge` (OPI), two `Sparkline`s (price, BBWP), hand-rolled ASCII `█░` bars (conviction, leverage, long/short weights, scrub), styled text everywhere else.
- **Three eye-candy dependencies are already declared in `Cargo.toml` but entirely unused:** `tui-big-text 0.7`, `throbber-widgets-tui 0.8`, `palette 0.7`. This spec puts all three to work; **no new dependencies required.**
- `App.theme_mode: usize` exists but is not wired to anything; `CockpitTheme` has a single hardcoded palette.
- `App.tick_count` exists and increments per tick, usable for animation without new state plumbing.
- **Visual defect found:** `sparkline_price_data()` feeds absolute `(price * 10.0) as u64` into `Sparkline`, which scales `0..max`. At BTC price scale the bar heights differ by <0.1%, so the price sparkline renders as a nearly flat full block. Window min-max normalization is required for any visible dynamics (S1 below).

## 2. Non-goals

- No engine/classifier changes, no new snapshot fields required from Python side.
- No GUI work (AGENTS.md: GUI deferred until acceptance gates B+C PASS; this is the existing TUI surface).
- No mouse support, no config files, no persistence of UI state.
- No per-frame heap-heavy work: all new rendering must be O(visible window).

## 3. Requirements (testable, tagged)

Phase A — high impact, low risk:

- **SRS_TUI_EC1 Regime timeline ribbon.** A 1-row strip (between header and screen body) rendering the trailing N snapshots (N = inner width) as colored `█` cells, one per snapshot, colored by that snapshot's `RegimeState` (theme colors: bull/bear/coiling/carry/chop), with the playhead cell inverted (`REVERSED` modifier). Scrubbing/playback moves the playhead; the ribbon is the at-a-glance persistence/flip-flop view and doubles as a visual scrubber. Pure function `ribbon_cells(snapshots, current_index, width) -> Vec<(RegimeState, bool)>` unit-tested for window clamping and playhead position.
- **SRS_TUI_EC2 Sparkline normalization fix.** Price and BBWP sparkline data min-max normalized over the visible window to `0..=100` before casting to `u64`; flat windows render mid-scale instead of panicking or flat-lining at max. Unit test: strictly increasing price window yields strictly increasing u64s; constant window yields constant 50s.
- **SRS_TUI_EC3 Transition flash.** When `current_snapshot().state` differs from the previous rendered snapshot's state, the banner border and ribbon playhead flash (alternate `border_active` / state style every tick) for 6 ticks, and a transient `⚡ REGIME SHIFT: <FROM> → <TO>` badge renders in the header's right corner. Implemented via `flash_until_tick: u64` on `App` compared against `tick_count`; decays automatically. Unit test on the pure decay helper.
- **SRS_TUI_EC4 Live throbber.** In `--live` mode the header renders a `throbber-widgets-tui` spinner (BrailleSix) next to `REAL-TIME LIVE`, advancing with `tick_count`; static glyph when paused. (First use of the already-declared dep.)
- **SRS_TUI_EC5 LineGauge unification.** Replace hand-rolled `█░` string bars (conviction, dynamic leverage, long/short weights, footer scrub) with ratatui `LineGauge` (thick line set), styled: conviction = confidence-gradient (EC10), leverage = gold, long = bull, short = bear, scrub = cyan. Removes 5 bespoke bar constructions.

Phase B — instrument-grade telemetry:

- **SRS_TUI_EC6 Braille price chart with regime coloring.** Replace the price `Sparkline` with a ratatui `Chart` (Braille marker): dataset 1 = price line over trailing window; datasets 2..6 = per-regime scatter overlays (window points bucketed by state, drawn in state color) so trend segments are visibly regime-colored; vertical transition markers at event timestamps within the window; Y-axis labeled with window min/mid/max price, X-axis with window start/end timestamps.
- **SRS_TUI_EC7 Bipolar meters.** Funding z-score and OPI rendered as center-zero bipolar meters: `[----|----]` custom span meter with colored fill left (bear) or right (bull) of center, threshold tick glyphs `▎` at ±1.8 z (funding) and ±0.20 (OPI), value readout colored by breach. Replaces the current single-direction OPI `Gauge` percent mapping (`(opi+1)/2` hides polarity at a glance). Pure helper `bipolar_cells(value, max_abs, width, threshold)` unit-tested at 0, ±threshold, ±max, and asymmetric widths.
- **SRS_TUI_EC8 Regime distribution bar.** One-row horizontally stacked distribution strip in the Regime screen: share of loaded snapshots per state, rendered as contiguous colored blocks with `pct%` labels when segment width >= 7 cells. Pure helper unit-tested for rounding-to-width (segments sum exactly to width).
- **SRS_TUI_EC9 Event log scrollbar + polish.** ratatui `Scrollbar` attached to the audit log; selected-row `▶` marker glyph; from→to states rendered as compact colored chips (`primary_label()` instead of full display names) freeing ~50 columns for the trigger diagnostic.

Phase C — polish & identity:

- **SRS_TUI_EC10 Confidence gradient.** Conviction gauge/readout colored via `palette` Lch lerp red → gold → green over confidence 0..1 (perceptually uniform, no muddy midpoints). Helper `gradient_color(t: f64) -> Color` unit-tested at t = 0.0/0.5/1.0.
- **SRS_TUI_EC11 Big-text regime label.** When the banner box is >= 96 cols and >= 12 rows, render the primary label (`TREND_UP`, `RANGE`, ...) via `tui-big-text` (half-height font) in the state color inside the banner; fall back to current single-line label below that size. (First use of the already-declared dep.)
- **SRS_TUI_EC12 Theme cycling.** Wire the existing `theme_mode` field: `[c]` cycles 3 built-in themes — `Neon` (current default), `Matrix` (green monochrome ramp), `Paper` (light, high-contrast); footer shows active theme name. All themes define the full `CockpitTheme` struct; no partial styling.
- **SRS_TUI_EC13 MTF alignment pulse.** On full 3-TF alignment, the `FULL 3-TF ALIGNMENT` line pulses (BOLD ↔ DIM every 2 ticks) in the aligned direction's color; partial alignment renders static. Per-TF rows get `●` state dots (bull/bear/chop colored) before the labels.
- **SRS_TUI_EC14 Price delta ticker.** Banner mark price gains `▲/▼` vs previous snapshot plus signed bps delta, colored bull/bear; flat renders `·` muted.

Cross-cutting:

- **SRS_TUI_EC15 Graceful degradation.** All new widgets clamp/hide at small sizes; hard floor 80x24 renders every panel without panic (existing tests must keep passing; add a 80x24 `TestBackend` render smoke test).
- **SRS_TUI_EC16 No perf regression.** Frame render stays under the 250ms live refresh budget with 50k loaded snapshots; ribbon/chart/distribution helpers operate on at most `visible_width` or one O(n) pass cached per `current_index` change, never per-cell scans of the full vector inside the draw loop.

## 4. Design notes

- **File layout:** split the 28KB `ui/mod.rs`: keep `draw()` orchestration in `ui/mod.rs`, add `ui/widgets.rs` (ribbon, bipolar meter, distribution bar, gradient, big-label) and `ui/anim.rs` (flash decay, pulse phase, throbber state). Pure helpers take plain data, return spans/cells; no `Frame` access, so they unit-test without a terminal.
- **App additions:** `flash_until_tick: u64`, `prev_rendered_state: Option<RegimeState>`, theme cycling in `theme_mode` (already present) + `[c]` in the key handler (`main.rs`), and cached window aggregates recomputed only when `current_index` changes.
- **Keybindings delta:** `[c]` Cycle Theme (added to footer + help overlay). No changes to existing bindings.
- **Charter note:** every element here visualizes already-computed research outputs (`RegimeSnapshot` fields). Nothing feeds back into classification, trials, or execution.

## 5. Test & acceptance plan

1. Unit tests (`cargo test -p hypervector-tui`): ribbon mapping, sparkline normalization, bipolar meter cells, distribution rounding, gradient endpoints, flash/pulse decay, 80x24 + 200x60 `TestBackend` render smoke tests for both screens and both overlays across all 3 themes.
2. `uv run pytest tests/ -q -m "not network"` unaffected (no Python changes) — run once to confirm.
3. Visual pass per `docs/guides/acceptance-visual-and-holistic.md` (hypervector-acceptance skill): playback a real parquet (`--file data/cache/aligned/BTC_1m_aligned_book.parquet`), verify ribbon/flash/chart against the audit log events, plus `--live` throbber check.
4. Estimated effort: Phase A ~0.5 day, Phase B ~1 day, Phase C ~0.5 day. Each phase ships independently green.

## 6. Risks

- Braille `Chart` (EC6) is the only item with meaningful layout complexity; if axis labels crowd small terminals, fall back to the normalized sparkline (EC2 keeps that path healthy).
- `tui-big-text` glyph widths vary by font; gate strictly on measured `Rect`, never assume.
- Emoji width quirks in some terminals already exist in the current UI (🔥/🛡️); new elements use box-drawing and Braille glyphs only, avoiding new emoji dependence.
