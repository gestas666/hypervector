# V88 runtime routing correction after operator startup refusal

The operator launched the approved V88 command on September 6. Backend PID 88405
created and verified the fresh prestart bundle, then stopped with
`enabled symbols require both long and short capability: ['BTC']`. Its log was
last written at `2026-09-06T14:13:25.113451+00:00`. Both the launcher and backend
were subsequently absent from the process table; no V88 live checkpoint appeared.

Correction to the earlier readiness assessment: configuration, unsigned observer,
and prior full-suite success did not exercise construction of the real V88 runtime
router. A separate validator still required every symbol to have both directions.
That condition contradicted the approved BTC long-only provider. The previous
technical checks were valid within their recorded scope, but insufficient to
establish live startup readiness.

The repair makes the router accept the nonempty directions each provider actually
declares. It preserves canonical symbol order and rejects intents whose direction
is absent from that provider's declaration. Existing duplicate-provider, symbol,
position-capacity, and position-snapshot checks remain. Bidirectional providers
continue to support both directions. The approved strategy TOML, executable sides,
sizing, leverage, exits, and asset universe are unchanged. This is a corrective
technical repair under the original preapproved defect-fix mandate; it does not
introduce a strategy proposal or request approval again.

Four regression cases failed with the observed exception before the repair. The
focused suite then passed 43 tests, including real V88 router and runtime-controller
assembly with inert dependencies and no execution clients. The broader Python
suite and final source checks are recorded in
`data/logs/research/bidirectional_cohort/overhaul_v88_runtime_router_correction_acceptance_20260906_v1.json`.
Rust source and the TUI binary are unchanged by this repair.

Final full-suite result: 8,001 passed, four network tests deselected, 27 warnings,
405.13 seconds. Ruff and whitespace checks passed. These results support the
correction within the tested scope; the next live startup remains unverified.

An additional 50 routing, execution-isolation, and runner checks passed under
coverage instrumentation. Router statement coverage was 88.37%; both branches of
the new undeclared-direction check executed. Overall router branch coverage in
that focused run was 69.74%, so this is not a claim of exhaustive legacy coverage.
Module-name coverage instrumentation encountered a NumPy import error; using the
source directory for instrumentation completed without changing dependencies.

A public-wallet-only check at `2026-09-06T14:17:55.915280+00:00` found zero positions,
zero orders, reconciled ledgers, and no transition blockers. That timestamped
observation does not substitute for the next launcher's fresh reconciliation.
The failed startup's verified backup is
`data/backups/bidirectional_cohort/prestart_20260906T140555.030103Z_06e90a0c59b4`,
manifest SHA-256
`f487cc65c5276d1359e0d35beba7838bfafaeaa7ab38a55876381f7b41a149a9`.
It preserves the pre-repair source for inspection and rollback without overwriting
current ledgers. Git branch `backup/v88-pre-router-repair-20260906` also preserves
pre-repair commit `64c41b0`. The incident artifact retains the exact new log segment.

The startup backup covered 7,432,991,142 source bytes; the largest file was the
4,074,541,641-byte cohort ledger. A read-only process sample observed JSON parsing,
and an open-file inspection found the HYPE ledger. This supports historical ledger
processing as a contributor to startup duration, but is not a complete performance
profile. The backup announcement used buffered stdout, so a missing log line did
not prove that backup verification was still pending. No history was removed and
no timeout or validation was bypassed.

High confidence in the reproduced cause and focused correction. Rejection of the
same profile during real router/runtime assembly, acceptance of an undeclared
direction, or failure of the next startup would update that assessment. Future
profitability and native fill/protection/exit fidelity remain unverified.

The agent has not restarted trading. The operator can retry the same command from
the [deployment handoff](2026-09-06-v88-approved-deployment-handoff.md). After a
fresh, consistent V88 checkpoint exists, perform read-only post-start acceptance,
capture the actual nine TUI screens, and bind the four prospective lifecycle
investigations before evaluating future outcomes. Their preparation scripts were
not executed against the old V86 checkpoint. Retain the original frozen proposal
and approval records as history; this correction supersedes the prior startup
readiness assessment.
