# Native reconstruction profile and repeated decision computation

High confidence in the sampled computation: ETH and SOL each rebuild the same
completed-bar decisions for provider and canonical reporting. Exact input frames,
scalar arguments and outputs match in both source variants at the first fabricated
decision. This is an opportunity to reduce research runtime, not an observed
strategy or order-execution fault. No computation has yet been reused.

The separate profile invoked 42 unchanged native collectors: seven assets, both
source variants and three dates in the registered fabricated fourteen-day window.
The authenticated source archive is commit `38bdf78c5ef5ee2c777e90dfac2ce478a26af554`.
The original full collection, regeneration and account waiter were preserved.
Public prospective outcomes remain sealed.

The measured native calls total 44.537 instrumented seconds. Approximately 26.829
seconds are cumulative time inside `build_completed_live_decisions`; 6.840 seconds
are inside its rolling-trend component. These nested times overlap and must not
be added. Source-frame construction costs approximately 6.922 seconds across 63
new windows despite the already-installed per-window frame cache. Profiling
overhead and fresh collectors prevent extrapolating these figures into a full-run
completion time or claiming a speedup.

All 42 call records and the profiler output completed. The original final summary
write then failed because the generic JSON writer could not encode a typed
evidence reference. The retained finalizer authenticated those artifacts and
published the summary using the existing canonical serializer. It did not repeat
or replace the computation. The failed log and original driver are retained.

A separate trace observed fourteen unchanged native calls, covering every asset
and both variants at the first fabricated decision. It copied the builder's input
frames at entry, compared values and metadata with exact Pandas frame equality,
and compared exact serialized returned values. Both diagnostics reproduce all
fourteen prior first-decision native record hashes from the earlier probe.

| Asset | Builder calls per native publication | Finding |
| --- | --- | --- |
| ETH, SOL | 2 each | Exact arguments and outputs match; four duplicate pairs across both variants. |
| HYPE | 2 | Scalar cutoff arguments differ; no equivalent-call reuse established. |
| BTC | 1 | No duplicate call in this path. |
| SPCX, SNDK, Brent | 0 | These collectors do not use this builder in the sampled path. |

Recommendation: develop an isolated, bounded reuse candidate for the two exact
ETH/SOL calls, using the existing collector injection interfaces. Preserve every
native publication field, validation, cutoff, source revision and error. Cache
scope must not cross a source window or a collector instance, and consumers must
receive detached nested values. HYPE's different arguments must remain distinct.
This remains a candidate investigation; no runtime installation or new approval
is requested.

Keeping duplicate computation is the lowest-complexity alternative. Altering
rolling formulas or retaining only selected output fields would complicate exact
parity and is not supported by this evidence. The expected benefit is faster
validated research; its magnitude remains unmeasured. Main failure modes are
stale inputs, hidden argument differences, mutable output leaks, cached failures
and false equality across source revisions.

Next: write behavioral controls, implement the candidate in an isolated checkout,
then compare full native records and measure uninstrumented paired runs. Sample
parity is insufficient for replacing the ongoing full-window experiments. Any
changed native value, lost exception or inadequate isolation rejects the candidate.
The [implementation plan](../plans/2026-09-16-v89-native-decision-reuse.md) records
the requirements. Evidence remains under
`data/logs/research/bidirectional_cohort/v89_captured_provider_assembly_20260916_v1/native_decision_profile_v1/`.
