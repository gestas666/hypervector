# Native HYPE holding in the conditional research account

The research account now uses the unchanged native HYPE holding policy with
independent provider and canonical evidence. Previously, the older research
support calculation duplicated provider state into canonical fields and rejected
UNKNOWN. That older calculation remains an explicit baseline; native account
routing uses the native policy. Confidence is high in the reproduced synthetic
compatibility result and low in any unmeasured financial benefit.

The complete 48-day historical account experiment remains unfinished. This
correction does not establish better historical returns, achievable fills or a
profitable live change.

## Verified behavior

- Observed UNKNOWN fields contribute no observed weight to the native support
  score. All-UNKNOWN evidence produces the ordinary eight-hour expiry; remaining
  known evidence can support an extension. Provider and canonical observations
  retain their distinct payloads and clocks.
- Native timer precedence is preserved before recipe decisions. The configured
  protective stop retains precedence at an opening gap even when the timer and
  an opposite signal also fire.
- The original accepted entry timestamp governs the eight-hour soft and
  twenty-four-hour hard boundaries. Missing, stale and future evidence retain
  their distinct native reason payloads beside the existing modeled exit-cost
  category. Terminal observations do not invent an opening or forced close.
- Pending closes are recomputed against their exact retained source completion.
  Edited reasons, evidence, decision/knowledge clocks, trade IDs and sides are
  rejected before acceptance. Existing account publication remains atomic.

The independent Fraction oracle covers all 69,984 combinations of five regime
fields and separate provider/canonical breakout directions for the configured
long HYPE route. It reports zero differences: 8,630 extensions and 61,354 exits;
41,859 cases contain at least one UNKNOWN field. These are synthetic policy
cases, not trades or win-rate observations. The oracle checks every exit score
and every exit/extension outcome; extending cases do not return a pending-exit
payload to compare.

## Reproduction and limits

Source `5fcb533cda4f692c59677af3b899cd00c55177ed` passes 363 account/routing
regressions plus five oracle tests in the worktree, and the combined 368 tests
in its archive. The measured six modules cover 549/559 statements (98%); both
new holding modules have 100% statement coverage. These coverage figures do not
claim complete branch or complete system coverage.

All 5,499 archived Git blobs, file kinds and executable bits match the commit.
The 33,494,934-byte source archive has SHA-256
`ed240b4df3256e84a3cb04422f9bc4ba47285651f4785c7dcdbb5a2ed4b93247`.
Both probe manifests and reports agree exactly. Their complete compressed
comparison files are byte-identical: 331,212 bytes, SHA-256
`31baba77f5bc70b92a7f46320d34f6d95a5b7065385618d598fae27edc7a965d`.
Evidence is retained under
`data/logs/research/bidirectional_cohort/v89_native_hold_qualification_20260909_v1/`.
The earlier failed tests remain evidence; one intermediate failure was an
incorrect generic-stop assertion, corrected to the configured protective stop.

The native live holding implementation, live configuration, deployment and
process lifecycle were not changed. Both prospective outcome seals remain
intact. Source or clock substitutions, unexplained native-policy differences,
failed archive reproduction or account mutation after a rejected step would
invalidate the affected qualification.

Next complete the [original historical account experiment](../plans/2026-09-09-v89-gap-market-account-followup.md):
connect authenticated market tables and native entry sizing, retain explicitly
assumed venue precision, supply complete independent canonical history and
reconcile every original source/cost/clock/allocation case. The canonical export
remains running in exec session 32156 and must not be restarted. The new venue
and historical entry bindings are separate work in progress, outside this frozen
HYPE qualification.
