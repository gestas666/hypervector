# Current V89 monitor verification

The original supervising TUI, PID 8440, still maps executable inode
203867057. The installed executable is inode 204043072, SHA-256
`1036c56c9e5680e4ce4c27953e5b536bf72dcea4e9092459132fd111306bc1d3`.
New detached monitors load the installed version. Replacing a file did not
reload the existing window. Confidence is high for the observed file/process
identity and captured installed display; the user's currently viewed window
was not independently identified.

Open a new terminal, preferably at least 120 columns wide, and attach using:

```bash
cd /Users/gestas/Prototypes/hypervector
.venv/bin/python -m hypervector cohort-tui --mode monitor \
  --config configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml
```

This selects the active profile and attaches the monitor. The existing
supervising window owns a different lifecycle; leave it running while using
the new monitor. The inspection procedure did not restart or signal the live
backend, supervisor, original TUI, checkpoint reporter, or prospective collector.

## Captured evidence

The installed executable was inspected at 100x28, 120x36, and 190x52. All
nine workspaces were visited: Portfolio, Setups, Chart, Depth, Trades, Journal,
Operations, Regime, and Configuration. The 27 workspace captures retained
their original ANSI streams. Replaying each exact stream prefix through
pyte 0.8.2 reproduced every saved visible-cell buffer.

At the captured boundaries, three entry fills and one exit fill corresponded
to two open lifecycles and one closed lifecycle. Eight bounding checkpoints
agreed on four fills, one closed trade, zero faults, and the following values:

| Evidence | Observed display and source |
| --- | --- |
| SPCX | Open long; full protective stop ID 538846363686 |
| Brent oil | Open long; full protective stop ID 538999050017 |
| SNDK | Flat; closed net loss $4.280304, displayed as $4.28 |
| Brent fill inspector | Symbol xyz:BRENTOIL, order 538998955084, trade 409406508647902, price 97.884, size 5.11 |
| SNDK exit inspector | Order 538806460232, trade 923869374782070, price 1788.2, size 0.276, protective_stop |

The monitor test command omitted the operator request inbox; the Operations
screen explicitly showed `REQUEST CHANNEL UNAVAILABLE`. Navigation and detail
inspection sent no operator requests. All four owned monitor processes exited
normally on their own quit keys. The six pre-existing process lifetimes were
unchanged before and after capture.

Evidence directories, relative to the original repository:

- `data/logs/research/bidirectional_cohort/v89_current_tui_capture_20260908_v1/`
- `data/logs/research/bidirectional_cohort/v89_current_tui_detail_20260908_v1/`

`acceptance_v2.json` records the bounded acceptance and limitations.
`process_binary_identity.json` records the original executable mapping.
Three PNG reconstructions support review of cell placement; they use plain
colors and are not operating-system screenshots or color-theme acceptance.

## Limits and next action

The first verifier failed because the 100x28 selected closed-trade row clips
`PROTECTIVE STOP` to `PROTECTIVE STO`. Its fill summary also abbreviates
`xyz:BRENTOIL`. This was retained as a display limitation. Twelve additional
detail frames verified that the full names, reason, venue IDs, prices, and
cost fields remain available through Enter and scrolling. At 120 columns,
the captured table retained the full exit reason and Brent symbol.

Long headings can clip at compact sizes. Mutable marks and unrealized PnL
can change between live ledger reads and checkpoint publication; bounding
snapshots do not prove exact same-instant parity for those fields. No claim
is made that these captures replace human sign-off for every field or screen.

The wide Depth view explicitly labels the HIP-3 roster snapshot stale.
The Journal view explicitly labels HYPE L2 Ridge not configured. These are
remaining data-availability limits, not fabricated zero observations.
The stop fill inspector's 992 ms ACK is the original stop-order placement
acknowledgement, as reconciled in the native stop audit; it does not measure
trigger-to-fill latency.

No reporting code, trading settings, or installed binary changed in this turn.
The mapped-reader proposal remains prepared and its existing approval request
is pending. This turn made progress through current display evidence and
isolation of the old-window explanation. The next execution investigation is
the newly observed Brent entry's native order, protection, and cost evidence;
it must remain separate from the frozen prospective strategy comparison.

Falsifiers: a new monitor loading the old image, an incorrect full ID or
lifecycle in its inspector, a missing configured asset, or a same-boundary
source comparison contradicting a displayed value requires renewed diagnosis.
