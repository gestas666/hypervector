# Release SQLite readers after recovery inspection

The offline `committed_index` helper left each SQLite connection open until garbage
collection. Its `with sqlite3.connect(...)` managed transactions, not connection
ownership. Explicit `contextlib.closing` now releases the connection on both a
successful read and an SQL exception. This changes only the research inspection
helper, not live strategy, orders, original collector scheduling or index data.
Confidence is high for the reproduced resource-lifetime defect.

Source `b2c7436d88ee202a867db3c9723798b05c02fc89` is committed and pushed on
`research/v89-recovery-reader-cleanup-20260918`, based on `24babd9`.
Evidence root:
`data/logs/research/bidirectional_cohort/v89_public_recovery_reader_cleanup_20260918_v1`.

The predecessor probe produced three warnings from three calls, with allocation
tracebacks pointing to `process.py:86`. Its initial diagnostic assertion inspected
only the first traceback frame; the corrected probe retains the complete stack.
Seven regression tests failed against the predecessor and passed after the fix.
They keep real connections referenced, then require queries to fail because each
connection is closed. Both index filenames, empty/populated tables, SQL failure
after partial inspection, exact byte preservation and 256 repeated reads are covered.

The candidate and independent archive each passed **234 tests, one skipped**, in
137.90 and 137.84 seconds. Resource and unraisable-exception warnings were promoted
to errors. Each run's main log and 85 child stderr logs contain no ResourceWarning.
Fresh tests include ten original runtime scenarios, five original crash cases and
two whole-owner-loss cases. Both versions independently revalidated the retained
five-collector continuation from the predecessor. The optional new 300-second
continuation was skipped; this small reader change does not claim a new such run.

All measured statements in the changed reader function were exercised. Its module
has 39/41 statements and 4/6 branches covered; the uncovered paths concern unrelated
spawn overrides and cleanup of a still-running process. The two failure-validator
modules retain 84/84 statements and 32/32 branches covered. Ruff, formatting,
diff, file/function-size and annotation checks passed.

All 5,837 tracked files match in source and archive (11,674 matches, zero changed
or missing). Archive: 33,895,667 bytes, SHA-256
`9d75b05c21f6af1f1f910279710d3774d58c83d4b06eb795e964242b6dd75cf5`.
Candidate tests preceded the commit; subsequent source-manifest checks verify the
tested implementation bytes and the independent archive repeats the same suite.

Disk headroom was restored by replacing the completed predecessor extraction with
independent APFS clones of its byte-identical source. Its compressed backup,
5,814 files and absence of open handles were verified first; all files matched
afterward. Observed free space rose from 8,800,960,512 to 9,030,590,464 bytes.
Archive paths, raw study evidence and running workloads were preserved.

The next investigation measures study-scale telemetry and full bridge recovery.
This repair does not establish network headroom, power-loss safety, profitable
strategies or operational deployment readiness. A renewed connection leak or
changed read results would falsify the repair's claim. Preserve the prior source
and archive for comparison; any live adoption remains subject to explicit approval.
