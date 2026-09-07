# V89 TUI repair and operator launch verification

The earlier preview acceptance checked route counts before the first completed
checkpoint. It did not establish populated regime/research panes. This review
supersedes that part of the earlier installation handoff.

Installed fixes at source commit `3086d2a`:
- Setup, fill, closed-trade and research inspectors share bounded wrapped scrolling.
- Regime Page Up/Page Down exposes label history, open-position context,
  closed-trade reflection and routing arbitration at the 100x28 minimum size.
- The navigation bar keeps all nine tab labels visible at that minimum width.
- Hourly providers publish 15m source / completed-1h signal clocks, ATR and both
  sides of their channel levels or the three band levels.
- Explicitly configured hourly routes receive independent canonical regime
  telemetry. Session gaps discard pre-gap history; partial bars are excluded.
  Unavailable warmup moving averages serialize as null, rather than invalid NaN.
  No extra entry/exit action is emitted by this telemetry collector. V89 has one
  strategy owner per new asset; same-symbol multi-provider conflicts are absent.

Validation: 150 focused Python tests passed; the full Rust suite passed 497 tests;
final view regression tests passed 99 tests; formatting and strict Clippy passed.
The rebuilt release was exercised in an actual terminal at 100x28, 120x36 and
190x52, covering all nine screens, seven setup inspectors and extra regime pages.
Run `bidirectional-observe-1788792706940` completed seven successful polling cycles
with no degraded cycles and two canonical observations for each of seven assets.
The technical audit passed and normal quit returned zero. V88's original live
checkpoint hash remained unchanged. The final release also passed 26 additional screen captures against genuine
observer and stopped-live snapshots, including every visible navigation label.
The first snapshot harness waited for a setup-only label on the portfolio page;
it was interrupted without modifying the ledger. The corrected v2 harness passed.

Read-only preflight at 2026-09-07T14:49:59Z found all seven assets technically ready,
zero open positions/orders and reconciled ledgers. Exact approval and the historical
V88 stopped/flat archive validated. Pure command resolution verified the supplied
flags and existing credential presence without starting a backend. Fresh state
can change; operator startup still rechecks the venue and creates its backup.
No real-money backend was started or restarted during this repair.

Run in the main checkout:

```bash
cd /Users/gestas/Prototypes/hypervector
.venv/bin/python scripts/multi_asset_bidirectional_canary_tui.py \
  --config configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml \
  --backtest-lab-root /Users/gestas/Prototypes/backtest-lab/backtest_lab \
  --mode live --enabled --i-accept-live-risk
```

This command requests real execution and owns its backend; quitting this TUI
stops that backend. Startup performs its verified backup before the cockpit opens.
Inspectors use arrows, Page Up/Page Down and Home/End. Screen 8 uses Page Up/Page
Down for its three pages and Left/Right to select each asset.

High confidence in the tested display/data corrections, limited to the recorded
sizes and input evidence. Missing fields specific to an unconfigured model,
non-emitting provider or absent completed trade remain explicit N/A/awaiting
states. The new hourly providers do not classify regimes inside their own entry
rows; independent current regime context is on screen 8. Observer previews do
not have live account/fill outcomes. Actual V89 private execution and profitability
have not been established by these checks. New false labels, inaccessible content,
or altered entry/exit streams would invalidate this acceptance.

Evidence is under `data/logs/research/bidirectional_cohort/`, prefixed
`v89_tui_repair_`, plus `v89_live_read_only_preflight_20260907_v1.json`.
The immutable [research review](2026-09-07-frequency-and-noncrypto-expansion.md)
and [exact live package](2026-09-07-v89-operator-live-launch.md) retain the economic
limitations and unchanged V88 rollback contract.
