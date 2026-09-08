# Causal source receipt reconstruction

The prior turn qualified registered historical account compatibility, journal
revision 5. Full prospective replay remains unqualified. This step implements
and validates market-source selection at an explicit knowledge timestamp.
It changes no frozen economics, live deployment or running collector source.

The collector index stores the first and last occurrence of each distinct value.
That is sufficient for its registered first/latest summary, but not for arbitrary
intermediate knowledge timestamps. For example A, B, A, B, A retains only the
first/last A and first/last B; it loses the middle A occurrence from the summary.
All raw responses remain authoritative. Prove the ambiguity on synthetic inputs
before implementing the reader; do not classify the collector as losing raw data.

Build a separate immutable research receipt tape from an authenticated capture
snapshot. Open source SQLite read-only, bind its bytes and manifest identity,
verify each indexed raw envelope and response body, and retain every normalized
receipt with native event, availability and receipt timestamps, request identity,
value hash and values. Preserve HTTP failures and partial coverage explicitly.
A corrupt/missing raw file, changed source identity, duplicate observation or
inconsistent request/index status fails publication. No mutable collector file
is edited or migrated; use a new output directory and atomic publication.

Store individual receipts in the new tape, with query indexes, so repeated value
reversions cannot erase an intermediate state. This also avoids requiring the
full fourteen-day repeated response history as Python objects in memory.
Queries for first and latest receipts must apply the explicit as-of timestamp
before version selection. Neither native availability nor a pre-request clock
can replace the actual receipt clock. Equal timestamp ordering retains the
collector's documented request-filename tie break and identifies it explicitly.
An unavailable observation remains unavailable; missing prices and funding are
not imputed. Native funding offsets remain distinct from their hour identity.
Metadata selection must retain its actual receipt and not claim publication lag.

These generic causal queries are not yet the complete 24-cell replay adapter.
The fixed route entry deadlines and recorded-bar versus modeled-fill clocks still
need to be connected and qualified against providers. Do not silently relabel a
bar-price model as an attainable receipt-time fill or apply end-of-window revised
values to earlier decisions. No strategy outcomes are computed by this component.

Validation: known A/B/reversion and equal-clock fixtures; late receipts; future
availability; first/latest differences; native funding offsets; metadata updates;
missing/partial/failed requests; tampered manifest/index/raw/body; read-only source
preservation; atomic output failure; query bounds; explicit unavailable results.
Independently reconstruct query answers from raw request sequences without using
tape query code. Verify every real query on the existing pinned source-qualification
snapshot, reporting only hashes, counts and timestamps. Pin source, reproduce from
archive and journal the qualified scope and remaining integration work.

A source hash mismatch, receipt later than the query clock, missing revision,
wrong native funding time, independent selection mismatch or mutation of either
running collector invalidates this component's qualification. High confidence
requires those checks to pass; no future performance inference follows from them.
