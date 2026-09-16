# Confirmed-entry protection during a reconciliation outage

The baseline failure injection reproduces an acknowledged fill followed by a
terminal reconciliation read error with no stop attempt. The actual SPCX trade
received its stop; its 3.885160-second interval motivated this failure test.

Build and qualify an isolated candidate; preserve root live source and processes.

1. Preserve the baseline failure, entry receipts and actual source identities.
2. Preserve ordinary reconciliation-before-protection. On a known venue read
   failure, attempt protection only from a direct accepted IOC fill with an
   exact order identity, finite positive executed quantity and average price.
   Do not substitute requested size, balance defaults, resting/canceled status
   or recovered acknowledgements with unqualified fill provenance.
3. Journal a distinct failure event with exception class and evidence source,
   without exception text or a fabricated venue snapshot. Bind the existing
   plan and logical entry time. Reuse durable stop submission and full post-stop
   verification. A further read error propagates, retaining PROTECTING state
   and any stop receipt; it must not claim OPEN or FLAT without evidence.
4. Extract existing entry helpers only to respect the module size limit.
   Test unchanged ordinary/deadline/no-fill behavior, both directions, anchors,
   invalid/ambiguous acknowledgements, persistent/recovering outages, rejection,
   failure before entry and restart adoption. Deny network access in tests.
5. Verify an archived candidate and rollback; commit and push; present a
   concrete installation proposal before any live change.

Success is a durable stop attempt using acknowledged executed exposure during
the tested read outage, with no invented venue truth or weaker final checks.
It does not promise placement during a total venue outage or solve ambiguous
fills without sufficient evidence. Ordinary-path latency remains unchanged.

Falsifiers: duplicate orders, wrong size/side/anchor, lost restart ownership,
secret disclosure, changed normal traces, unsupported successful reconciliation
or a retry policy change outside scope.
