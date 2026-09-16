# Passive prospective collector health watch

The two frozen public-source collectors stopped for about 49 hours without an
active health observer. Preserve those sources, manifests, timing evidence and
outcome seals. Add a separate read-only observer; it has no restart, financial,
credential, network or economic-evaluation authority.

1. Pin each capture manifest and collector PID/birth/command. Authenticate its
   declared source files and protocol on every observation.
2. Validate health schema, identity, heartbeat, schedule and lifecycle against
   the frozen study window. Require a live matching process and occupied writer
   lock during collection. Recognize only an evidenced final completed window.
3. Use a 120-second heartbeat alert threshold and 15-second observer interval.
   Waiting heartbeats are 30 seconds; queries have three 10-second transport
   timeouts, 1/2-second retry delays and, for seven assets, bounded budget waits.
   This is an operational threshold, not a hard network-duration guarantee.
4. Retain immutable start/result observations and atomic observer heartbeat.
   Read again at the finite deadline. Stop with an alert on invalid inputs;
   never repair sources or restart jobs automatically.
5. Offline regression tests cover absent/reused PID, lock mismatch, stopped,
   stale/future/malformed heartbeat, manifest/source drift, valid completion,
   and faults arising during the final sleep. Real validation reads both live
   collectors without signalling them. Test source modifications only in copies.
6. Install only new observer files after tests, preserve implementation evidence,
   launch an agent-owned finite observer and verify its live handle. Journal
   limitations: observer death itself needs another supervisor; this is not an
   independent operating-system notification service or proof of timely coverage.

Also inspect the scheduled 01:00 UTC funding recovery using timing/identity
fields only. Backfill remains late; original study coverage stays incomplete.
