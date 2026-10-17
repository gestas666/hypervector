# Unified current checkout implementation plan

**Goal:** Finish the focused application cleanup, verify retained workflows and
make the original checkout's main branch the maintained unified CLI version.

**Architecture:** Preserve existing external APIs while separating paper
lifecycle, session concerns and autotuning orchestration into focused services.
Keep provenance-bound historical research as archival/support code. The current
CLI and tests must distinguish software failures from unavailable historical
operator evidence. No trading process is started by validation or merging.

**Tech stack:** Python 3.13, existing package/venv, pytest, VectorBT/Rust/TA-Lib,
Nautilus, Hyperliquid, 0xArchive, Git.

1. Back up the eleven pre-existing local files with hashes, patch, tar and a
   named Git stash; retain a pre-merge main branch. Integrate compatible local
   supervisor and accounting work, resolve current docs, preserve STOP state.
2. Run offline units, external integration/evidence selections in an isolated
   environment, and record exact missing/stale prerequisites. Acquire no orders
   or live execution clients. Use read-only copies of local vendor evidence.
3. Decompose active paper/session/autotuning orchestration by responsibility;
   preserve existing import/monkeypatch contracts and replay outputs. Add
   regression/contract tests before fixes and rerun affected tests after each
   extraction. Remove obsolete current TUI docs and packaged script coupling.
4. Close the artifact-validation contract: unit-test negative and positive
   paths with controlled inputs; replay real available vendor data separately;
   identify historical hash mismatches without rewriting historical approvals.
5. Build/install a fresh wheel and verify all public command parsing plus
   actual retained engines, TA-Lib indicators, optimizer, shadow and archive
   normalization. Repeat runtime/memory observations and full offline tests.
6. Commit verified changes; fast-forward or merge main in the original checkout.
   Update its stopped environment with the locked dependency set, test there,
   and verify clean Git status, preserved local work and unchanged STOP/service
   state. Retain recoverable backup references; do not push to a remote unless
   required by the user's requested repository workflow.

Acceptance: retained workflow tests pass; no default test reaches a venue;
installed CLI works outside the source tree; core recovery memory is bounded;
original main contains the verified commit; new current docs have no TUI
instructions. Historical evidence remains immutable and is not misrepresented
as current deployment approval. The user authorized this merge explicitly.
