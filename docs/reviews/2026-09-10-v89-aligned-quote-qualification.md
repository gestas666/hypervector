# Aligned-quote fee eligibility remains unresolved

Public metadata captured September 10, 2026, **15:09:13–15:09:15 UTC** maps all
seven configured markets to collateral token **0**, identified by `spotMeta`
as **USDC**. The formerly documented `alignedQuoteTokenInfo` request for token
0 returned **HTTP 422**, with a request-deserialization error. That response
establishes neither aligned nor unaligned eligibility.

High confidence applies to the observed collateral mapping, response status
and dated documentation. Actual aligned-discount eligibility remains unverified.
The current information-endpoint documentation no longer lists this older query.
The [current aligned-asset specification](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/aligned-quote-assets)
distinguishes AQAv1, which offers trading-fee benefits, from AQAv2, which offers
none. A generic alignment label alone would therefore be insufficient evidence
for applying a discount without resolving its protocol meaning.

Retain the existing explicit no-aligned-discount assumption. The earlier
0.864 bps HIP-3 and 4.32 bps core projections remain conditional estimates from
their dated fee snapshot. This probe changes no rate, historical case, live
configuration, reporting source or prospective outcome seal. The existing V2
report already preserves this uncertainty and does not require another revision.

The research operator sent four unsigned public-information requests: core and
XYZ metadata, token metadata, and the legacy alignment probe. It uses no wallet
identity, signing key, account endpoint, order client or execution request.
Receipts retain request type, clock, HTTP status and response-body hash;
allowlisted metadata retains exact configured identities. The error is preserved,
not replaced by a false eligibility flag. The operator passes Ruff and uses
explicit typed functions. This is an observed API probe, not a new trading feature
or a claim of broad protocol compatibility.

Evidence is retained under
`data/logs/research/bidirectional_cohort/v89_aligned_quote_qualification_20260910_v1/`:
the plan and capture source, current documentation snapshots, request receipts,
selected market/token metadata and `alignment_0.json`.

A current documented replacement API, a version-specific native eligibility
field, or appropriately available actual fill-fee evidence could resolve the
remaining question. Do not repeat the rejected legacy request without new
contract evidence. No extra discount or historical substitution is proposed.
The highest-value remaining task is the original complete account report and
its final deployment review. Future profitability remains unproven.
