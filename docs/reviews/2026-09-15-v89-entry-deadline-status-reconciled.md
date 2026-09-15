# Entry-deadline candidate reconciled with installed successor

High confidence from authenticated source comparisons: the September 8 candidate
is incorporated into the September 14 qualified release and the current run's
September 15 prestart bundle. Its journal status was stale. This reconciliation
changes the research record only; it makes no new live execution change.

Candidate `3d204863af40536187df96f161f4874d9fa42166` changed 19 source files.
Qualified successor `d01abba1deb2c54141ef88a9b8dce2a6ff95335f` was installed
through the separately documented native-account release. All 19 prestart files
match that qualified successor exactly. Eleven also match the original candidate
byte-for-byte; eight have later qualified changes. The central
`entry_submission_deadline.py` guard still matches the original candidate hash
`04ed3818b53c47fc54f5d2dbe0291839c78fbaf22eee24c8924fc90a5a436437`.

The authenticated bundle is
`data/backups/bidirectional_cohort/prestart_20260915T183016.143980Z_39e334fc97f3`.
Its manifest SHA256 is
`9f20a7a850c2625c977c59ba7d292a9d9c1a09e56b5f71e73d7759445ae76029`.
The comparison and extracted source bytes are retained alongside the band audit
under `v89_band_history_install_20260915_v1/prestart_source_comparison.json`
and `prestart_sources/`. A twentieth comparison concerns the separate band bug;
it must not be counted as one of the 19 deadline candidate files.

The operational source subsequently changed two of these files for the
separately qualified startup-candle evidence capture. Their current bytes are
reported separately. The prestart source is the relevant historical evidence
for the existing backend; source on disk alone cannot prove active imports.

Revision 3 of `v89-entry-deadline-engine-gap-20260908` therefore records `retain`
and supersedes revision 2's pending-candidate status. Historical revisions,
454-test qualification, 16 mutation controls and four flat-recovery cases remain
preserved. Those counts describe the September 8 experiment and are not claimed
as fresh tests in this reconciliation.

No new live expired-entry case was deliberately exercised. Local deadline
checks still do not guarantee venue receipt within the configured interval:
signing, scheduling, transmission and venue processing follow the final local
check. No reduction in financial loss is measured. A changed archive hash,
missing final guard, resurrection of a documented unsent intent or contradictory
native execution evidence would reopen this conclusion. Further source changes
are unnecessary without such new evidence.
