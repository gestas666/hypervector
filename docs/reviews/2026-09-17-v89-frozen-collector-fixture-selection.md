# Frozen collector handoff: explicit fixture selection

Final source **ca9445af15b0a88ec3ebe4918860e99705d3d602** only adds explicit
fixture-availability markers to two test modules. All six research modules are
byte-identical to the preceding qualified **7ce7c8d** source. The original
[handoff review](2026-09-17-v89-frozen-collector-handoff.md) remains unchanged.

With `HYPERVECTOR_COLLECTOR_INVENTORY` explicitly selecting the authenticated
archived producer inventory, **24 tests pass in 18.83 seconds** from final archived
source. All nine complete cases independently verify again. Without that external
fixture selection, the six self-contained staging tests pass and eighteen
fixture-dependent tests skip with an explicit reason. Skips are not passing
capture/store qualification.

Final `source_v2.tar` contains 1477 files / 13,373,440 bytes, SHA
`1107b67f660923738518af41a83a54635fe05ed891e8c6f75f263e35fd839e2d`.
Git, candidate and extracted bytes match. The 1477 source files and 152 copied
producer files were rechecked after execution. `archive_v2_test_tmp/`,
`archive_v2_verification.json`, `archive_v2_tests.txt`, `source_manifest_v2.json`
and `final_source_verification.json` retain the final qualification evidence under
the original handoff evidence root. Earlier archives/results are preserved.

Confidence is high for this test-selection correction and the repeated bounded
contract results. The admission/lineage incompatibility, full-loop qualification,
coverage limits and deployment requirements in the original review still apply.
No live process, execution setting, source study or financial behavior changed.
