# Configuration-staging correction: isolated and ready for review

**Recommendation:** apply the narrowly scoped source correction
`a676db5c884ae3c9a69e3d41be7da26ef5744c6c` to main after explicit approval.
It changes `cohort_profile_stage.py` and adds its regression test file. It does
not write an active profile or start/restart any process. The source remains
isolated; it has not been deployed to main.

## Reproduced defect and resulting behavior

The original serializer, SHA-256
`14a6a769dbaeef19a56405dae12d4bf515f50b540c4bebe081659a5337508ca7`,
writes BTC provider sides as long/short even when V89 configures long-only.
The resulting unchanged-V89 file fails the observe loader's exact route
validation. It also drops all seven explicit 0.002 entry-slippage caps; repairing
direction alone would expose the existing 0.01 market-cap fallback. It omits
the position policy needed by an existing flat-entry-only provider too.

The correction serializes configured provider/asset sides, optional explicit
entry caps and provider position policy. A staged identity explicitly clears
the previous profile's transition approval, matching the prior generated-file
omission without carrying stale authorization in the candidate object. The
asset-envelope requirement to support both long and short is preserved; valid
one-way execution remains a provider setting.

Before publication, the generated temporary file is loaded in observe mode and
its full profile fingerprint must equal the intended staged candidate. Invalid
or semantically changed bytes fail before replacing an existing staged file.
Validation and operating-system publication failures propagate; temporary files
are removed and the previous staged output is retained. The correction does not
modify current trading route semantics or automatically apply staged settings.

Confidence is **high in the reproduced staging defect and corrected tested
behavior**. This is not evidence that the defect caused previous trading losses
or the current process shutdown. A source mismatch, failing round trip, widened
direction/position policy, changed effective slippage or failed preservation of
the previous output would falsify the corrective acceptance.

## Verification

The exact V89 round trip, explicit and legacy entry caps, provider overrides,
flat-entry-only behavior, invalid asset-envelope rejection, malformed output,
loadable semantic corruption and publication failure are tested offline.
**41 focused tests pass** across staging, operator settings and the inactive
allocation generator. All modified staging executable lines and decision
branches are covered. The full existing staging module has 88.50% statement /
83.33% branch coverage (87.10% combined); uncovered older helper paths are not
claimed as tested. The new inactive generator has 97.46% statement / 94.23%
branch coverage (96.47% combined).

The first regression run had five failures and one pass. A proposed narrow
asset-envelope fixture was corrected after inspecting the existing validation
rule; its rejection now remains an explicit regression. An initial named-package
coverage invocation failed during NumPy import. Coverage collection using file
paths, and then `coverage run` without that package pre-import, succeeded. No
dependency or environment changes were made to mask the failure.

The exact inactive control/equal profiles preserve all other typed fields.
A separate checker with no Hypervector implementation imports verifies the full
raw TOML against an explicit independent allowlist, including known legacy
defaults, and recalculates budgets/cap-binding equity with Decimal. A tampered
entry cap is detected by that independent check. Main's existing observe loader
also accepts both generated files without live flags.

All **5,161 Git source blobs** match the frozen full source archive
`1e720d5ea8ab18e6f871bdd08a684b05f9c6716e`. Archive execution reproduces both TOML
files and the comparison JSON byte-for-byte, reproduces the independent audit
byte-for-byte, and passes all 41 tests. Ruff and changed/new-file structural
checks pass. The isolated two-file patch passes `git apply --check` against main.

## Deployment decision

| Required proposal field | Reviewable decision |
|---|---|
| Why now / observed problem | The reproduced serializer corrupts a staged V89 contract. Correct generation is needed before a trustworthy inactive or later staged proposal can be produced. |
| Applicable market regime | Independent of market regime; the defect is deterministic configuration serialization. |
| Alternatives considered | Keep the defective staging path and avoid using it; hand-edit each candidate; or repair the shared serializer with pre-publication parity. The correction reuses the existing path and reduces repeated manual validation. |
| Proposed live/deployment change | Apply only commit `a676db5` to main source. No active config, route, sizing, leverage, execution flags, backend/reporter/TUI process or order changes accompany it. |
| Expected upside | Future staged files preserve configured behavior and cannot report successful publication after serializer drift. No direct profit improvement is asserted. |
| Main risks | Stricter round-trip checking may expose an older unsupported serialization path. That produces an explicit error and preserves the previous output. Filesystem failures and other profiles remain subject to the documented validation scope. |
| Validation completed | Reproductions and regressions above; exact semantic checks; independent arithmetic/raw TOML; full-source archive; main patch applicability. |
| Validation still required | After approval, verify main's unchanged base, apply only the two-file commit and run the focused staging/operator suite there. No trading restart is required for this source change. |
| Success metrics | V89 and supported flat-entry profiles load with identical intended fingerprints; entry caps and scopes persist; malformed or changed output leaves the prior staged file intact. |
| Failure / rollback | If main-source or focused checks disagree, retain the prior main version. After an approved application, a new scoped revert of this commit can restore the serializer; do not reset unrelated work or alter trading state. |
| Confidence | High for this deterministic correction and tested cases. Broader production effects are unverified until approved source application and main verification. |
| Explicit approval requested | Apply only the staging correction commit to main. The active goal's **Human control** instruction reserves deployment changes for explicit human approval; research preparation was already authorized. |

The allocation proposal is separate:
`docs/proposals/v89-equal-cap-20260908/recommendation.md`. Its prospective window
is frozen at September 9–23, but its collector/replay implementation remains
unqualified and it is not running. No live allocation approval is requested.

Evidence root:
`data/logs/research/bidirectional_cohort/v89_equal_cap_inactive_proposal_20260908_v1/`.
It contains the original failing bytes/source, correction patch, regression logs,
coverage, independent checks, source archive, replay comparison and prospective
preregistration. No existing sealed outcome was inspected or reconstructed.
