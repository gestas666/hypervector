# Combined deployment packet and compatible rollback rehearsed

The [exact technical deployment proposal](../proposals/v89-technical-release-20260910/recommendation.md)
is prepared for source candidate `f00b6b8d22cf59285a313b7de1166cccecbe52ca`.
It packages 33 implementation files, 19 tests/fixtures and the qualified TUI
binary. Nineteen paths are newly introduced; prior absence is recorded. It
changes no configuration file, strategy selection, allocation or leverage.
Main source and installed TUI remain unchanged, and live activation is pending.

Confidence is high in the measured source/binary composition and static rollback.
The existing 602 Python and 544 Rust test qualifications remain applicable:
Python source matches 71fbf05, Rust runtime/Cargo source matches b73b112, and
the stronger f00 test set was already reproduced from its source archive. No
accepted suite was repeated simply to package identical bytes. This does not
establish fresh live behavior, order acceptance or financial improvement.

The install patch passes a non-mutating applicability check against current
main, whose code/config/test scope matches baseline b3df618. In detached
rehearsal checkout `hypervector-v89-release-rehearsal-20260910`, application
produced exact candidate bytes and Git modes for all 52 paths. Comparing the
entire code/config/test scope against f00 found no additional difference.
Replacing the rehearsal TUI produced the accepted SHA256
`604307380b4b047453e0492a349760e737c58da3a917f37305feb39072af3ea3`.
Neither TUI executable nor a backend, signer or order client was run by the rehearsal.

Compatible rollback restored every prior path and the original binary, retaining
only candidate `src/hypervector/live/sol_order_restart.py`. Complete scoped Git
comparison found that one remaining difference. This reader matches the original
qualified deadline correction, and the baseline Python/config/test source is
identical to the prior four-probe flat-recovery source. Eight intervening Rust
changes are outside that Python recovery scope and remain in the rollback's
current TUI baseline. The prior executable restores SHA256
`95f87cdcd49e5aa0068b7ebf8d4bef2b18d5f3efa7692291fc9aeabc83623d8f`.

The corrected restart reader must remain once new unsent-entry markers exist;
it is retained unconditionally in this rollback patch. Blind restoration of the
older reader is not the qualified fallback. No old ledger is restored over newer
history. Static composition plus the existing fake-venue flat recovery does not
qualify open-position rollback or authorize a restart.

All 530 pinned external-provider Python files still match. The first unfiltered
filesystem inventory also included hidden development environments/tool trees;
the scoped result records these separately, with no additional nonhidden Python
source and no changed/missing pinned file. All ten installed SDK source files
match the current venue qualification. These checks read source only.

The packet archive independently restores **104 files** with identical contents
and modes, including candidate/prior source and both executables. It is
7,665,950 bytes, SHA256
`2efd00abed2180946c753715b8bd7b413bb789f4751ff6b2d98e71de1ec34b42`.
The two preparation/rehearsal operators pass Ruff and their function/file-size,
annotation and public-docstring checks. The detached checkout is intentionally
left in the compatible rollback state; it is not a deployment or launch directory.

The proposal documents exact scope, alternatives, expected benefit, uncertainties,
approval boundary, static verification commands, fresh prestart evidence,
post-start acceptance and rollback. It distinguishes the monitor's optional
reporter ownership from the live TUI supervisor's backend ownership. All nine
views and actual route evidence still need fresh presentation acceptance; old
constructed screen buffers do not substitute for that observation.

At September 10 08:32:01 UTC, the original historical matrix has **26/48** complete
receipts, four active workers and the qualified reporting handoff waiting on its
original coordinator. Both job handles were polled live. Free disk is 10.04 GB;
no local live backend or TUI matched. This process observation does not refresh
venue positions or orders. Both prospective outcome seals remain intact.

Next complete the original matrix and full report, then finalize the deployment
decision using this concrete packet and fresh ownership/native-state evidence.
No new deployment approval is requested during this preparation. Existing
pending authorizations are not expanded. Changed bytes/modes/dependencies,
unexplained scope differences or failed recovery invalidate the packaging claim;
unfavorable economic results remain reported evidence rather than trial aborts.

Evidence root:
`data/logs/research/bidirectional_cohort/v89_combined_deployment_review_20260910_v1/`.
Key files: `release_manifest.json`, `install.patch`, `rollback_compatible.patch`,
`rehearsal_acceptance.json`, `prior_qualification_applicability.json`,
`provider_identity_scoped.json`, `current_sdk_identity.json`,
`archive_manifest.json`, `archive_acceptance.json`, and `release_packet.tar.gz`.
