# V89 strategy and regime monitor

The installed monitor covers BTC, ETH, SOL, HYPE, xyz:SPCX, xyz:SNDK and
xyz:BRENTOIL. It displays the backend's strategy evidence and portfolio state.
Use a terminal at least 120 columns by 36 rows; 100 by 28 is the compact floor.

```bash
cd /Users/gestas/Prototypes/hypervector
.venv/bin/python -m hypervector cohort-tui --mode monitor --independent-monitor \
  --config configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml \
  --tui-bin target/release/tui-regime-detector-v89-monitor-20260915-exits \
  --tui-bin-sha256 52df3fbb38a0a91f8e4577bebb7884da537dc8c3c8fd35411751684d7866bc84
```

Run this in another terminal and leave the original combined session open.
This independent mode owns only its reporter and TUI; quitting it preserves the
financial backend. It requires fresh same-run shared reporting and does not
load credentials, submit operator commands, make network requests or write the
research database. A stale or mismatched source fails explicitly.

The monitor labels provider exits by their recorded target side (`EXIT SHORT`,
for example), separately from entry eligibility and actual execution receipts.
Missing exit-side evidence remains `EXIT SIDE N/A`. See the
[exit-side validation](../reviews/2026-09-15-v89-provider-exit-side-display.md).

The separate binary path preserves the executable pinned by the existing user
startup. `LEV C/V` means configured/venue leverage: `20x/-` is a flat asset
configured for 20x; `10x/10x` records both configured and observed leverage.
An open position with missing venue leverage shows `N/A`. The rolling strip uses
`PROFILE` for compatible historical results and `RUN` only for explicit current-run
results. See [September 15 installed validation](../reviews/2026-09-15-v89-independent-monitor-and-leverage.md).


| Task | Controls | Evidence to inspect |
| --- | --- | --- |
| Inspect a strategy setup | `2`, up/down, `Enter`, `PgUp/PgDn` | Exact provider and asset, recorded indicators, readiness prerequisites, blockers, entry/exit plan and configured sizing. |
| Relate indicators to regime | Continue through the setup inspector | Canonical 1m/5m/15m context at the recorded strategy decision, separately from the latest recorded context; each has its own time and age. |
| Inspect the strategy chart | `3`, left/right to select asset, `Enter` | Reported signal timeframe and configured source timeframe. Hourly strategies show completed hourly candles; missing or incomplete evidence is explicit. |
| Monitor regime changes | `8`, left/right, `PgUp/PgDn` | All assets, three regime pages, trend/compression diagnostics, transitions, open lifecycle context and outcome/arbitration evidence. |
| Plan configuration changes | `9`, up/down, `PgUp/PgDn` | Effective settings beside the local next-run draft. Editing a draft does not make it effective. |
| Inspect portfolio and exposure | `1`; open-lifecycle page on `8` | Recorded positions, costs, stop/target evidence and bound hold-clock origin. |

`Esc` closes an inspector. `q` quits the monitor. The existing nine screens
remain available through keys `1`–`9`.

Read `DATA AGE` before treating an indicator as current. `ARRIVAL LAG` measures
the difference between decision and observation time. A newly generated
checkpoint can still contain old strategy evidence. When the backend is
stopped, the monitor may refresh its report-only checkpoint but cannot produce
new strategy decisions. `STOPPED SNAPSHOT`, `IF STILL OPEN` and `LOCAL EXITS OFF`
describe dated position evidence and absent local exit management.

Readiness measures prerequisite completion; regime strength is a diagnostic.
Neither is a win probability. Provider entry rules remain separate from
canonical context. Missing data should remain unavailable rather than become
zero, neutral or a fabricated current reading.

High confidence in installed display/source parity comes from the authenticated
installation, Rust regression tests and native terminal captures described in
[the current installation review](../reviews/2026-09-14-v89-partial-protection-tui-installed.md).
That confidence is limited to the observed inputs and terminal sizes. A wrong
provider, timestamp or timeframe, omitted indicator, clipped required panel,
changed binary hash or failed launcher would require revalidation. Display
acceptance does not establish strategy profitability or fresh venue state.

## Start the backend and TUI together

Use the installed supervised launcher:

```bash
cd /Users/gestas/Prototypes/hypervector
.venv/bin/python -m hypervector cohort-tui \
  --mode live --enabled --i-accept-live-risk \
  --config configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml \
  --tui-bin target/release/tui-regime-detector-v89-monitor-20260915-exits \
  --tui-bin-sha256 52df3fbb38a0a91f8e4577bebb7884da537dc8c3c8fd35411751684d7866bc84 \
  --startup-timeout-seconds 1800
```

It opens the TUI after a fresh backend configuration identity appears and binds the checkpoint writer to that run. Historical initialization can take several minutes. The explicit timeout permits up to 30 minutes; it does not predict startup time. Quitting this combined TUI stops its owned backend. The detached monitor command at the top of this guide leaves a separately started backend running. The [September 15 startup memory update](../reviews/2026-09-15-v89-startup-history-and-memory.md) is installed.
