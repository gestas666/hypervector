# Native funding/source qualification without prospective account outcomes

Continue after provider/source qualification `38e1d6a` and journal revision 9.
The existing native funding prototype has 36 preliminary synthetic checks.
Neither live execution nor either running collector may change. Neither sealed
study's strategy signals, positions, trades, cash flows or returns may be
computed. Real-data work here is source-only; account cash-flow checks remain
explicitly synthetic.

Use the already registered complete-source snapshot and receipt tape from
`v89_complete_source_view_20260909_v1`, not a more favorable later capture.
Authenticate the tape through journal revision 8 and its exact recorded hash;
authenticate its historical manifest and immutable raw/index sources as before.

At the tape's final request cutoff, bind all seven assets, both first/latest
variants and each captured hourly identity from bootstrap through the last hour
whose opening candle is complete. The fixed snapshot spans September 7 through
September 9 00:32 UTC: 49 hourly identities per asset/variant, or 686 requests.
Preserve every absent input and all lateness results; missing funding is not zero.

Additionally find, from first receipts only, when each asset's study-opening
funding and opening-price candle are first jointly known. Query one millisecond
before and at that exact time for both variants: 28 boundary requests. Schedule
all 714 queries in increasing knowledge time to respect the source view's
forward-only contract. A candle that has not completed cannot enter the source
query. At a missing-input boundary, retain the missing identities and create no
accounting observation.

The native settlement S remains the raw funding timestamp, including its
millisecond offset. Knowledge K is separate. The declared funding price proxy
is the settlement-hour candle's open; its completed-bar availability and actual
receipt remain explicit. A price proxy learned after S does not become a claim
that it was observed at S. First funding timeliness uses first receipt minus
first native settlement, independently of selected revision clocks. Late rates
remain observed rates, with a reported lateness result.

Validate missing and contradictory identities, both rate payloads, malformed
clocks, revision order, actual first/latest source use, positive/negative/zero
rates, missing-versus-zero behavior, premature/future price receipts and native
offset preservation. Independently reconstruct selections from authenticated
raw responses without importing the source view or funding implementation.
Compare complete identities, values, clocks, missing states and declared scope.
Use the existing incremental account only for synthetic signed arithmetic.

Pin source, preserve the initial failures and corrections, reproduce from its
full archive and append/read back the journal. High confidence requires exact
independent source agreement and archive reproduction; any mismatch, hidden
missing source, fabricated timing, changed settlement or altered price proxy
invalidates the affected acceptance. Full cost/trigger, metadata and 24-cell
account orchestration remain separate requirements, as does future profitability.
