# Isolated ETH/SOL native decision reuse

Purpose: reduce duplicated provider/canonical computation without changing any
native strategy, regime, source-timing or account result. This is authorized
research implementation. Financial runtime deployment is outside this plan.

1. Create an isolated checkout from the qualified research source. Preserve the
   current two full source experiments and downstream account waiter. Record the
   baseline source, dependency lock and existing native evidence hashes.
2. Use the existing `DirectionalRangeOnsetCollector.source_collector`, range
   decision-builder and canonical decision-builder injection interfaces. Keep
   live default construction unchanged. A research-only adapter may share one
   builder between the exact ETH/SOL provider and canonical call.
3. Start with failing behavioral controls: identical detached frames and identical
   observed/after clocks compute once; changed values, order, dtype, index,
   metadata, observed time, after time or source revision compute independently.
   HYPE's different cutoffs must not share a result. Preserve empty and malformed
   input behavior. Errors must propagate and must not populate the reuse state.
4. Limit reuse to one source window and collector instance. Verify separate
   instances and nested consumers cannot mutate each other's retained data;
   control cache lifetime and retained memory explicitly. Avoid a process-global
   patch or unbounded cache. Reuse the existing native implementation rather
   than reconstructing strategy logic in the adapter.
5. Compare every field of actual native outputs against the frozen baseline for
   all seven assets and both variants, including the three sampled dates and
   changed-receipt/late-entry controls. Preserve exact bytes; a numeric tolerance
   or removal of provenance fields is not accepted. Test meaningful entry, exit,
   withheld and canonical outcomes, not only empty publications.
6. Measure repeated, paired, uninstrumented native calls with the same input
   artifacts and environment. Retain per-asset/source timings, all output hashes,
   memory evidence and ordering. Report variability; do not use profiler times
   as the speedup baseline.
7. Freeze and reproduce the candidate with its focused and adjacent tests in a
   separate archive. Keep failed controls and exact source manifests. Register
   any complete-window comparison as a separate experiment; do not restart or
   overwrite the current baselines. A bounded probe does not qualify full-period
   equivalence or improve the ETA of already-running processes.
8. Append the hypothesis journal with measured results, remaining scope and a
   retain/reject decision. Rollback means retaining the prior isolated research
   implementation; no financial process control is involved.

Success requires exact unchanged outputs and errors, bounded isolated memory,
fewer demonstrated identical computations and a measured uninstrumented benefit.
Any semantic difference, cross-window reuse, mutable leak or slower paired result
updates or rejects the proposal. Confidence is high in observed ETH/SOL duplication
at the first fabricated decision; generality and performance benefit are unproven.
