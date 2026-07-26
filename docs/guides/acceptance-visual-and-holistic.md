# Hypervelocity TUI visual and backend-parity acceptance

## Scope and success criteria

The TUI is a read-only projection of the Python shadow backend. Acceptance
requires all three screens to show the same run, portfolio, regime, execution,
cost, and L2 facts found in the active backend ledger. The TUI must not create
orders, trades, labels, probabilities, distributions, or fallback market data.

Automated acceptance:

```bash
uv run pytest tests/ -q -m "not network"
cargo fmt --check
cargo clippy -p hypervector-tui --all-targets -- -D warnings
cargo test -p hypervector-tui
```

Human acceptance uses a terminal at least 120 columns wide. Any mismatch with
the ledger is a failure even when the display looks plausible.

## Launch

Use the supervised command so one lifecycle owns the backend and foreground
TUI:

```bash
uv run python -m hypervector \
  --data-root data \
  hypervelocity-tui \
  --config configs/hypervelocity_faithful.toml
```

Normal quit preserves the durable shadow portfolio and journal. Do not use a
reset merely to restart the display. A deliberately fresh observation window
uses the recoverable command shown on screen 3:

```bash
uv run python -m hypervector \
  --data-root data \
  hypervelocity-shadow-reset --yes
```

## Screen 1: Dashboard

Verify the following against the latest run in
`data/paper/decisions/decisions.jsonl`:

- Run ID, strategy ID, shadow mode, model mode, and model probability match.
- One BTC position maximum is shown; pending maker orders are not positions.
- Entry, mark, size, 40x leverage, unrealized PnL, paid entry fee, funding, and
  estimated exit fee match backend rows.
- Initial capital, equity, realized/unrealized/net PnL, closed trade count, and
  win/loss counts persist across normal quit and restart.
- Five bid and five ask levels are visible when the backend publishes them.
- The journal is selectable. Details include Eastern entry/exit times, entry
  and exit 1m/5m/15m states, entry/exit fees, funding, gross PnL, and net PnL.
- Flat readiness shows backend entry direction, canonical state, maker status,
  retry/cooldown state, funding, L2 age, and structure score.

## Screen 2: Regime Detection

The exact backend vocabulary is
`TREND_UP`, `TREND_DOWN`, `BREAKOUT`, `RANGE`, `TRANSITION`, and `UNKNOWN`.

- `Canonical Primary` says `5m authoritative`.
- `Context Only` is immediately below it and shows 15m non-veto context.
- 1m is execution telemetry and breakout confirmation; no text may advertise
  a 1m directional fallback over 5m.
- A 5m breakout is direction-eligible only after matching 1m confirmation.
- `Structure Strength` is separate from `Model p`; it is an EMA-gap percentile
  diagnostic and is not an execution gate.
- The distribution uses observed backend history, includes `UNKNOWN`, and is
  not a current-state-shaped constant profile.
- The transition audit uses backend timestamps and reasons.
- Missing L2, funding, or playback features say `not available` or
  `not reported`; zero must not be presented as a measured neutral value.

## Screen 3: Effective configuration

Rows are selectable and read-only. Verify these identity fields:

| Field | Expected faithful value |
|---|---|
| Position mode / max per symbol | `one_way` / `1` |
| Margin allocation / leverage | `70%` / `40x` |
| Target | `8%` margin return, strategy-target only |
| Order | post-only limit, event-driven public L2/trade evidence |
| Execution / primary / context timeframe | `1m` / `5m` / `15m` |
| Allowed states | `TREND_UP`, `TREND_DOWN`, `BREAKOUT` |
| Blocked states | `RANGE`, `TRANSITION`, `UNKNOWN` |
| Breakout direction required | `true` |
| Context hard gate / strength-score gate | `false` / `false` |
| Metalabel mode | `off` or `observe`, never a hidden filter |

The displayed reset command must quote and reuse the backend-reported active
data root.

## Persistence and honesty protocol

1. Record the current run ID, equity, journal count, and open/pending state.
2. Quit with `q` and verify the shell returns normally.
3. Relaunch the same supervised command.
4. Confirm the same durable run and portfolio resume unless a new backend run
   identity is explicitly required by an incompatible execution fingerprint.
5. Confirm shadow mode never writes a live decision or constructs a live venue
   execution client.
6. Inspect regime rows and assert no `submit_entry` occurs when `state_5m` is
   `RANGE`, `TRANSITION`, or `UNKNOWN`.

## File-playback parity

```bash
uv run python -m hypervector \
  --data-root data \
  regime-export --symbol BTC --timeframe 1m --bars 1500

cargo run -p hypervector-tui --bin tui-regime-detector -- \
  --symbol BTC --timeframe 1m \
  --file data/exports/regime_snapshots.json
```

Playback states, reasons, timeframe labels, and structure scores must match
`classify_multitimeframe(..., faithful_regime_config())` for the same rows.
Incomplete snapshots are rejected instead of backfilled with synthetic values.

## Sign-off record

```text
Date:
Commit:
Terminal and dimensions:
Backend run ID:
Screen 1 dashboard parity: PASS | FAIL
Screen 2 regime parity: PASS | FAIL
Screen 3 config parity: PASS | FAIL
Quit/restart persistence: PASS | FAIL
No-submit shadow honesty: PASS | FAIL
Reviewer notes:
```

Automated green tests increase confidence in parsing and rendering. They do not
replace human visual inspection or a fresh venue-matched shadow/real comparison.
