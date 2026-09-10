# Combined technical candidate: offline integration accepted

Candidate `71fbf0541fd1360e726f49b7de89ae905912020c` combines the three existing
technical proposals in an isolated checkout based on main `b3df618`. It changes
26 implementation files and 14 test files, plus its qualification plan. Main's
live source and profiles remain unchanged. High confidence applies to the
measured offline integration; live acceptance and profitability remain unproven.

| Existing correction | Exact preserved scope |
| --- | --- |
| Entry deadline, `3d204863` | All 19 candidate source hashes match the prior qualified proposal |
| Mapped reporting reader, `7a30d04` | All six source and two test files match its complete deployment bundle |
| Staging serializer, `a676db5` | Its source file and regression test match the exact two-file commit |

The reader's final commit alone is insufficient: its complete reviewed bundle
also includes the preceding stream-support changes. The deadline deployment
patch contains implementation files; its 11 changed test/helper files were
therefore taken from the exact qualified commit before testing. These were
packaging requirements, not changes to the proposed technical behavior.

All **602 tests across 56 modules pass** in the candidate and again from its
retained source archive. The exact test identities match between runs. The
suite includes all 43 modules in the original 454-test deadline qualification,
plus direct reporting and staging consumers. Python socket connections,
resolution and datagram sends are denied by an audit hook whose synthetic
probe is checked before pytest; no unexpected socket events were recorded.
This is focused integration, not a claim that the entire repository suite ran.

All 5,144 candidate Git blobs and 530 retained external provider Python files
were verified before and after the archived tests. The external provider is a
namespace package and must also occupy the expected adjacent
`backtest-lab/backtest_lab` layout. The first archive check incorrectly assumed
an `__init__.py`; the next run had 601 passes and one failure because that
adjacent directory was absent. Correcting only the retained layout produced
602 passes. Failed operators and logs remain available. Candidate source did
not change during these packaging corrections.

The exact source archive, patch, candidate manifest, test list, operators,
logs, JUnit results and `acceptance.json` are under
`data/logs/research/bidirectional_cohort/v89_technical_release_integration_20260910_v1/`.
Use `archive_final.log`, `archive_final_junit.xml` and `archive_final_exit.json`.
The prior installed TUI hash remains
`95f87cdcd49e5aa0068b7ebf8d4bef2b18d5f3efa7692291fc9aeabc83623d8f`.
Copies of the observed live profile and binary are retained under
`observed_inputs/`; the acceptance records their original paths and hashes.

Why now: the existing fixes address a reproduced dispatch-deadline gap,
reporting write load and staging-contract corruption. Their separate test
results did not establish integration against the current baseline. This
qualification prepares one coherent technical candidate while the economic
matrix continues. Applicability is independent of market regime.

Expected upside is restoration of the existing timing and configuration
contracts and reduced reporting snapshot writes. No increase in trade count,
win probability or return is established. Keeping the current source is the
simpler alternative but retains the diagnosed defects; deploying the fixes
separately requires repeated integration and transition validation.

Remaining validation: finish the original economic comparison, select the
concrete deployment scope, obtain explicit approval under Human control,
refresh source/configuration and venue-ownership evidence, retain the normal
prestart backup, then perform supervised startup and fresh TUI/checkpoint
acceptance. The old deployment documents' PID snapshots are stale and cannot
be reused as current ownership evidence. No order is required just to create
an acceptance trade.

Success requires preserved route/configuration identity, correct deadline and
unsent-intent recovery, owned position/protection state, and fresh consistent
reporting. Source drift, failed recovery, duplicate dispatch, missing protection,
wrong profile or reporting discrepancy invalidates acceptance. The deadline
proposal's compatibility rule still applies to rollback: retain its corrected
`sol_order_restart.py` after new unsent-entry markers exist. Do not restore old
ledgers over post-deployment history. Open-position rollback remains outside
the previously established flat recovery evidence.

No new deployment approval is requested at this qualification step. Existing
pending approvals are not expanded by this record. No live strategy, allocation,
execution, deployment, process or TUI installation changed. Both prospective
outcome seals and the full 48-case research scope remain intact.
