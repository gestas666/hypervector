# v25 durable research sync and checkpoint-log integrity

## Problem restatement

The portfolio improvement loop requires live execution evidence to survive
process boundaries and remain attributable by asset, provider, entry run, and
exit run. The checkpoint sidecar must import this evidence without delaying or
mutating the execution backend, and its operator log must preserve one
parseable event per line when launchd merges stdout and stderr.

## Observed durable research path

The running `com.hypervector.v25.checkpoint` sidecar uses a short-lived,
execution-incapable worker every 600 seconds to incrementally import all ten
cohort JSONL ledgers into `data/research/market.duckdb`. The persistent process
does not open the large database itself. A fill-identity hash avoids rebuilding
the all-time portfolio archive when execution fills are unchanged.

The HYPE target close advanced the database fill identity from 67 to 68 and
changed `archive_status` to `rebuilt_after_fill_identity_change`. Subsequent
syncs reused that exact identity. At the verification boundary DuckDB reported:

- ten cohort source files;
- 672,411 imported events;
- 68 venue fills and 34 close fills;
- 68 attributed fills and 31 reconstructed close orders;
- no missing or truncated source ledgers.

The database was approximately 92 KB behind the actively growing files during
the read. This is expected inside the ten-minute import interval and is
explicitly labeled `pending_import`, not synchronized. A missing or truncated
source would instead be a source-integrity error.

## Current-run reconciliation

An independent read-only DuckDB query found three close orders whose entry or
exit run is `bidirectional-live-1786182011216`:

| Asset | Provider | Entry run | Exit run | Exit | Net after lifecycle costs |
|---|---|---|---|---|---:|
| ETH | precompression pullback | prior process | current | maximum hold | +$0.010815 |
| SOL | HT-Breakout | prior process | current | maximum hold | +$1.582877 |
| HYPE | Hulk expansion v2 | current | current | target | +$0.552777 |

The sum is +$2.146469. The compatible-profile audit total is +$2.170721; its
$0.024252 difference is the two compatible closes inherited from the earlier
process prefix. The scopes therefore reconcile rather than conflict. This
query validates durable provenance, not profitability or repeatability.

## Logging defect and staged repair

The launchd job directs checkpoint stdout and stderr to one file. The current
loaded process writes JSON sync events to buffered stdout and historical
refresh messages to stderr. One observed line concatenated both messages,
making that boundary unsuitable for line-oriented event parsing.

The staged source now writes both routine events as flushed JSON to stderr:

- `cohort_research_sync`;
- `cohort_historical_projection_refreshed`.

Every row retains `execution_authority=none`. The change affects observability
only and cannot place, cancel, close, resize, route, or promote a trade.

The loaded v25 sidecar has not been restarted and therefore does not yet contain
this repair. It should be loaded only at a safe process boundary. Acceptance
requires newly emitted lines from the restarted process to decode independently
as JSON without concatenation.

## Validation

- Both logging tests failed before implementation for the expected reasons:
  sync used stdout and refresh output was plain text.
- Both tests passed after implementation.
- The broader checkpoint-script set passed 20 tests.
- Ruff lint and format checks passed.
- Production is 496 lines and the new test module is 70 lines.
- The full non-network Python suite passed: 4,133 tests, four deselected, and
  27 known dependency/deprecation warnings.
- The live execution owner remained PID 37897, launch count one, never exited,
  live-armed, healthy, and fault-free with three protected open positions.

## Confidence, risks, and falsification

Confidence is high that the current ledger-to-DuckDB path persisted the HYPE
close and retained entry/exit-run provenance. Confidence is high that the
staged stream/flush change prevents the reproduced mixed-stream ordering class
under unit conditions. Live acceptance remains unproven because the running
sidecar has not loaded it.

The durable-path assessment is falsified by a changed imported prefix, missing
or truncated source, fill-count disagreement, or reconstructed close economics
that differ from the venue ledger. The logging repair is falsified by any
post-restart routine event that is concatenated, not independently JSON
decodable, or omits the report-only authority contract.
