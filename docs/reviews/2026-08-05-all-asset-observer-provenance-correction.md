# All-asset observer provenance correction

**Corrected:** 2026-08-05 15:31 EDT  
**Execution authority:** none  
**Runtime strategy changed:** no

Research-journal revision 1 was appended before the final formatting check.
Ruff then reformatted `multi_asset_strategy_evidence.py`, changing its file hash
from `2b6b189234935056dc794834e302899e1f52c348e811b5c76699d1039dc89822`
to `de7cda1ef1b5fa38ff48910f0ec068430fa0b107ea2984615df1678e601d3742`
and its byte count from 14,454 to 14,432.

This correction does not rewrite or delete revision 1. Its changed evidence hash
remains visible. Revision 2 binds the formatted implementation and supersedes
revision 1 as the current research decision.

Post-format verification passed 25 focused evidence and telemetry tests, Ruff
check, and Ruff format check. The observer was already restarted after the
evidence-state correction and retained the same profile fingerprint, empty
execution scope, four observed provider-symbol mappings, and report-only
contract. The armed live backend was not restarted or changed.

Confidence is high that the formatting operation did not intentionally change
the observer contract or evidence values because the same focused behavioral
tests passed before and after formatting. A payload difference for the same
input, an executable provider-symbol mapping, or a changed profile fingerprint
would falsify that assessment.

