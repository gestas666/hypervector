# Original collector continuation: completed source and archive qualification

The committed recovery candidate `11b1bac70277547ce118c1d7c8a19b00ce4cdf12`
passed its broader network-denied suite from working source and its exact
archive: **564 passed, 4 skipped** in **2062.55 s** and **2086.73 s**. Both
process handles returned zero. The four opt-in studies remain explicit skips;
they are not counted as passes. Earlier focused evidence and the preserved
95-second failed native-progress claim remain in revision 1.

Each run explicitly declared a 1,300-second continuation window. All five
original collectors stopped after the first committed index, reopened in fresh
processes, and issued **10, 111, 10, 111 and 18** additional requests. The
original declaration, namespace, contract, stop time and reservation version
were unchanged. Old history bytes remained a prefix. New process IDs and
request IDs were disjoint from the first phase, and every continued request
began before the original cutoff.

Both quarter-v2 collectors retained **112 reservations, 112 bindings and 112
durable HTTP begins**, with zero unbound reservations or bindings lacking a
begin. Each lifetime reservation weight was **2,350**, exactly matching the
two original process counters **21 + 2,329**. Their active in-memory windows
contained four records in the working run and five in the archive run; those
different final-time subsets do not change lifetime accounting.

An independent post-run check re-read raw/index records, observation grids and
the explicit ordered phase accounting and matched the saved verifier reports.
`resume_policy.py`, `reservation_process_verify.py` and
`quarter_reservation_verify.py` each measured 100% statements and branches in
both broader runs. That coverage claim is scoped to these modules, not the
whole repository or every possible failure.

All **11,628** file checks still matched the 5,814-file source manifest, with
zero changed or missing files. The standalone source archive still hashes to
`4228cb2f737a71bd74ab477f645b1087f97378c32ee20084be6c316c91be92c3`.
The complete checks and immutable run artifacts are under
`data/logs/research/bidirectional_cohort/v89_public_coexistence_resume_20260918_v1/`.

**High confidence within this experiment:** the repair permits explicit
continuation of the five original collectors without resetting durable
obligations, overwriting history or extending the declared window. Changed
source, failed phase accounting, duplicate requests, lost prefixes or a shifted
cutoff would falsify that claim. These are synthetic transport experiments on
the current host; no economic improvement is established.

Retain the isolated candidate. Operational migration, production overhead,
global request headroom, incomplete-request resumption and power loss remain
separate requirements. The whole-service SIGKILL qualification has a separate
experimental process-observation failure and is not implied to pass by these
graceful-interruption results. No live strategy or deployment change is proposed
by this terminal review.
