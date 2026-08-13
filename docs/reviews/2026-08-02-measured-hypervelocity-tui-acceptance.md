# Measured Hypervelocity TUI acceptance

## Scope and evidence

- Candidate: `hypervelocity_source_follow_bidirectional_minrange12_alloc10_lev5_shadow_v1`.
- Working tree base: `761ddf21223b1f49f9397a09bfea7150fbcec144` with uncommitted shared work preserved.
- Deterministic backend fixture run: `measured`.
- Terminal sizes: 120x36 and 180x52.
- Evidence artifact SHA-256: `25f8b7c1aa1490ee6766e4f7d1e06089e54c9f833d4c617f64c7e8dad947220f`.

## Eight-screen cohort cockpit completion

The current shared BTC/ETH/SOL/HYPE operator interface supersedes the earlier
four-screen cohort layout. Portfolio, Setups, Chart, Depth, Trades, Journal,
Control, and Config all project the same backend run. Setup and fill rows are
selectable, the four charts use completed backend OHLCV, and Depth uses only
the five real bid/ask levels recorded in `market_books` events.

Control does not make Rust an execution engine. A confirmed action creates an
expiring, run/profile-bound local request; only the explicitly armed Python
backend can claim, revalidate, execute, and journal it. Observer mode disables
entry and close. Config writes a validated restart-only staged profile while
disarmed and cannot hot-mutate or arm the backend. No credentials are rendered
or written to either request format.

Manual entry and close are one-off overrides rather than a manual portfolio
mode. The automatic strategies remain active; after a manual close, only the
same polling cycle is protected from immediate re-entry and the next cycle
resumes ordinary automatic decisions. A Python regression test pins this
behavior without constructing a live client.

Current observer run `bidirectional-observe-1785682136700` was inspected against
the real ledger and rolling checkpoint. At the recorded acceptance point it had
74 public-data polls, 113 evaluations, all 10 expected provider-symbol pairs,
zero duplicate evaluations, zero technical gaps, zero intents/actions, and only
`live_armed=false` / `execution_authority=none`. The cockpit launch command was
also re-executed in monitor mode; a deliberately undersized 80x24 PTY produced
the required resize diagnostic and exited cleanly without stopping the observer.

Fresh verification passed all 129 Rust/TUI tests, strict all-target Clippy,
Rust formatting, task-scoped Ruff, and whitespace checks. The latest full
non-network Python regression passed 2,782 tests with four intended
deselections and 27 existing dependency/Pandas warnings.

Confidence is high for the exercised projection, navigation, L2, request
serialization, staging, and disarmed fail-closed paths. Real manual entry/close
venue outcomes remain unverified until a separately authorized armed canary.
An observer order attempt, request replay/cross-run acceptance, fabricated book,
hot-applied draft, missing protective stop, or ledger/display mismatch would
falsify this acceptance.

## Acceptance result

| Check | Result | Evidence |
|---|---|---|
| Screen 1 dashboard parity | PASS | Exact 10% margin, 5x, 0.50x notional, target, no-stop, development status, and gap count asserted. |
| Screen 2 regime parity | PASS | 5m authority, bidirectional sides, lifecycle-safe `SIGNAL OBSERVED`/`ENTRY PENDING` readiness, honest unavailable L2, and no irrelevant BBWP asserted. |
| Screen 3 chart parity | PASS | Backend OHLC candlesticks, volume, regime tape, source signal, target, and missing-value behavior asserted. |
| Screen 4 config parity | PASS | Backend-only selectable rows, evidence provenance, scrolling, and full selected value asserted. |
| Compact operator state | PASS | 120x36 retains `5m/60s`, `EXEC SHADOW`, `FEED LIVE`, and `CONNECTED`. |
| Open-position parity | PASS | Latest mark, margin, notional, target, fees, liquidation price, and liquidation distance asserted. |
| Shadow no-submit contract | PASS | Profile validation requires paper submit false, live false, shadow-only execution, and model observation with no authority. No live client was invoked. |
| Quit/restart persistence | NOT EXECUTED | Requires a real supervised shadow launch; deterministic rendering cannot validate process persistence. |

## Shared cohort observer addendum

The measured BTC bidirectional source-follow signal and the HYPE breakout-onset
challenger are declared as the third and fourth providers in
`multi_asset_bidirectional_canary_v2`. They reuse the cohort's completed
Hyperliquid one-minute feed and now have explicit provider-symbol execution
scope together with Hulk and range-onset. This scope change does not arm the
observer and is not presented as evidence of edge.

### Provider evidence qualification

New backend configuration identities bind one report-only research record to
every configured provider-symbol mapping. The record includes its research
state, confidence, measured cadence, concise basis, and source. It does not
change configured execution scope, router priority, position limits, sizing, or
live authority.

The Setup inspector shows the exact selected mapping's evidence beside its live
readiness and blockers. Config shows the same research state beside effective
and next-run scope. Older immutable runs without the field remain readable and
show `RESEARCH STATE NOT REPORTED BY THIS RUN`; the TUI does not fabricate a
qualification.

The rolling observer checkpoint now also combines that immutable historical
qualification with the run's fired-signal paths in a ten-mapping strategy
scorecard. The contract is explicitly report-only: it cannot gate performance,
pause, retune, filter, size, or execute. Journal rows show the forward
assessment, while Enter retains the raw signal/readiness horizons and adds the
historical cadence, confidence, basis, and source. Older checkpoints without
the additive scorecard remain readable and display `NOT REPORTED BY THIS RUN`.

A one-shot checkpoint of still-running run
`bidirectional-observe-1785682136700` at 2026-08-02 20:28 UTC reported nine
mappings with no eligible forward signal evidence. The HYPE breakout-onset
mapping had one eligible short path, resolved at 5/15/30/60 minutes with mean
directional returns of -49.60/-35.18/-13.84/-34.61 bps. This is one adverse
counterfactual candle path, not a fill or an edge estimate. Repeated independent
signals with materially different paths would update the assessment; one path
cannot support either rejection or promotion.

| Check | Result | Evidence |
|---|---|---|
| Causal source evaluation | PASS | Completed one-minute bars form five-minute decisions available only after the bar closes; startup history seeds readiness without emitting retroactive intents. |
| Authority parity | PASS | Python and Rust accept only each provider's declared symbols; all ten v2 mappings are canary-eligible while observe mode remains execution-incapable. |
| Router visibility | PASS | `HV SOURCE 5M` has its own readiness row, human blocker labels, side, confidence, range, and primary-onset telemetry. |
| Compact capacity | PASS | All ten provider/asset evaluations render at 120x36 without clipping the tenth row. |
| Configuration provenance | PASS | Screen 4 shows all four aliases, exact backend strategy IDs, the full pinned profile path, timeframes, priorities, and complete execution-scope role labels. |
| Strategy scorecard boundary | PASS | Exact ten-mapping coverage and report-only authority are validated; hidden performance gates and incomplete coverage fail closed. |
| Controlled observer restart | PASS WITH DISCLOSED GAP | The prior disarmed run was immutably audited before the new four-provider fingerprint started; its one rejected-signal direction conflict is explicitly excluded and reported. No hot mutation or execution authority was used. |

### Forward observer activation

The prior two-provider run was subsequently stopped cleanly and published as
`multi_asset_observer_audit_bidirectional-observe-1785656878593.json`. It
covered 4.40 hours and 1,056 poll cycles with complete technical coverage,
zero routed actions, and zero strategy intents.

The updated run `bidirectional-observe-1785672774457` started under profile
fingerprint `61148acd9ad3de517a90255f489149cc0c6b848d39a72b3d731a1418c3716502`.
Its first cycle produced all nine declared provider-symbol evaluations and all
four market-candle streams while remaining `live_armed=false` with
`execution_authority=none`. The measured BTC source row was visible as a
non-eligible `TRANSITION` with its confidence, completed-bar range, and exact
blockers.

Observe mode now has a supervised bounded checkpoint sidecar. Deterministic
120x36 runtime inspection showed:

`FRESH | FORWARD OBSERVER | COVERAGE COMPLETE | FWD EVAL 122 | FIRE 0 | 5M PATH 95/23 INDEP | NO FILLS/PNL`

The observer checkpoint contains no closed-trade or net-PnL fields. Its causal
forward paths exclude nine startup seeds, separate eligible signals from
readiness annotations, and expose independent counts so overlapping one-minute
observations cannot masquerade as 95 independent samples. Quitting the
standalone read-only TUI did not stop either the backend observer or its
checkpoint sidecar.

Observer timing diagnostics separate the initial completed-decision seed age
from post-start decision arrival lag. This prevents a deliberately seeded 30m
Hulk decision from being mislabeled as live feed latency.

### Four-provider rollover and visual parity

The nine-pair run `bidirectional-observe-1785672774457` ended with 515 rows,
228 poll cycles, zero eligible evaluations, zero strategy intents, and zero
routed actions. Its immutable audit is
`multi_asset_observer_audit_bidirectional-observe-1785672774457_20260802T131023Z.json`.
The audit reports complete market and metric data plus one
`provider_direction_telemetry_conflict`: a rejected HYPE Hulk row copied a
stale long candidate while indicator readiness was short. The row never had
execution authority. It is excluded from directional outcomes rather than
silently assigned a side; an eligible conflict remains a hard failure.

Fresh run `bidirectional-observe-1785676597907` started under profile
fingerprint `efe5222e9df75939c10fc0e6532b1822b07405dcc215a62da97fb2c6e689fdd7`.
Its initial cycle contained exactly ten evaluations, four candle streams, zero
actions, `live_armed=false`, and `execution_authority=none`. The rolling
checkpoint reported ten expected/initial/observed provider-symbol pairs, zero
duplicates, zero future decisions, zero direction conflicts, and complete
technical coverage.

An interactive 120x36 monitor pass inspected all four backend-driven screens
for the superseded v1 authority profile.
Screen 2 showed all ten readiness rows and exact blockers; Screen 3 showed four
native OHLCV candlestick panes; Screen 4 showed the full untruncated labels
`OBSERVE ONLY | 30M EXPANSION`, `CANARY SOL | HOURLY CROSS + 5M REGIME`,
`OBSERVE ONLY | COMPLETED 5M PRIMARY`, and
`OBSERVE ONLY | FRESH 5M BREAKOUT`. Quitting the monitor left the observer and
checkpoint sidecar running.

### Ungated v2 execution scope and observer journal

The prior single-SOL `execution_symbols` profile was an operator-policy
bottleneck, not a transport limitation. It was replaced by
`multi_asset_bidirectional_canary_v2`, which declares all ten existing
provider-symbol mappings execution-eligible. This applies no performance,
trade-count, model-score, or profitability promotion gate. The existing router
still resolves simultaneous same-coin intents by configured provider priority,
enforces one venue position per coin, and caps the shared portfolio at four
positions. The per-coin envelope remains 5x isolated, 3% margin fraction,
$25 maximum notional, 80-bps venue-native stop, and eight-hour maximum hold.

Observer Screen 1 now projects the backend checkpoint directly as a ten-row
setup journal and a 5/15/30/60-minute causal path journal. An interactive
120x36 pass against run `bidirectional-observe-1785676597907` showed complete
technical coverage, all ten provider rows, 165 forward evaluations, zero
eligible signals, and `132/32` resolved/non-overlapping 5m annotations. The
screen explicitly labels these as annotations rather than fills or PnL. The
monitor exited without stopping the observer or its checkpoint sidecar.

The completed Journal screen now preserves the checkpoint's two evidence
classes rather than pooling them. `SIGNAL` columns contain eligible fired
evaluations only; `SETUP` columns contain readiness annotations only. Selecting
a row and pressing Enter exposes all four horizons with resolved,
non-overlapping, censored, and missing counts. The current run has zero fired
signal evidence, so setup paths are explicitly prohibited from standing in for
signal, fill, fee, funding, or PnL evidence.

## Verification record

- `cargo fmt --all -- --check`: PASS.
- `cargo test -p hypervector-tui`: PASS, 131 tests.
- `cargo clippy -p hypervector-tui --all-targets -- -D warnings`: PASS.
- Measured profile/replay Python tests: PASS, 29 tests.
- `uv run pytest tests/ -q -m "not network"`: PASS, 2,774 passed, 4 deselected,
  and 27 dependency/deprecation warnings.
- Ruff format and lint checks for the seven touched Python checkpoint/launcher
  paths: PASS. Repo-wide Ruff is not a clean baseline: 33 unrelated existing
  lint findings remain, and 294 legacy files are outside current formatter
  conformance; this acceptance does not claim otherwise or rewrite them.
- `git diff --check`: PASS.

## Confidence and falsifiers

- High confidence that the deterministic TUI projection matches the serialized backend contract at the two acceptance sizes. A real ledger field rendered differently, a missing value shown as zero, or any TUI-derived execution state would falsify this.
- High confidence in the four-screen observer usability at 120x36 because an
  interactive live-ledger monitor pass covered every screen and monitor quit
  preserved the two backend processes. A stale checkpoint, clipped critical
  field, or backend/TUI value mismatch would lower confidence.
- Medium-low confidence in the strategy's positive edge remains unchanged. This acceptance validates telemetry quality, not profitability or live promotion.
- High confidence that v2 scope is faithfully represented and remains dormant
  in observe mode. An undeclared provider-symbol action, a startup seed becoming
  an intent, more than one action per coin, or TUI-derived execution state would
  falsify this.

## Remaining runtime check

Run the disarmed shadow profile, inspect all four screens, quit, and restart the same command. Confirm the run ID, equity, journal, and open/pending state resume from the backend ledger before considering visual acceptance complete in a real process.

The rolling observer remains useful for setup cadence and blocker attribution,
but it is no longer a permission gate. A later explicitly armed v2 canary is
the source of venue-authoritative execution evidence; the observer alone cannot
identify fills, execution quality, or profitability.
