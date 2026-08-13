# Source same-side re-entry raw-reset audit

Date: 2026-07-31

## Problem and success criterion

Test whether creator same-direction re-entry is associated with a causal raw
5m regime reset-and-return that the pinned Hypertrader state machine hides
inside an unchanged confirmed trend. The hypothesis is useful only if such a
hidden event occurs materially before observed creator re-entries; merely
reproducing a normal confirmed regime reset does not repair onset-only fidelity.

## Inputs and assumptions

- Creator evidence: 37 raw position records from July 9 through July 24.
- Current reconciliation removes one duplicate record and collapses two true
  split positions, yielding 34 logical positions: 15 long and 19 short.
- Twenty consecutive logical pairs are same-side, non-overlapping re-entries
  with a visible prior close.
- Labels are the pinned current Hypertrader 5m revision and are joined by their
  causal `available_at` timestamps, never by future bar timestamps.
- A raw reset-and-return requires at least one non-aligned raw label after the
  prior close followed by a side-aligned raw label before the next open.

The creator close timestamps include tracker-derived records and are not a
complete authenticated private-order ledger. This limits causal inference but
does not change the deterministic calculation over the retained sample.

## Result

| Measure | Count |
|---|---:|
| Logical positions | 34 |
| Same-side non-overlapping re-entry windows | 20 |
| Raw reset-and-return windows | 6 |
| Hidden raw resets with no confirmed reset | 0 |
| Raw side aligned at next entry | 11 |
| Confirmed side aligned at next entry | 12 |

Every raw reset-and-return was already accompanied by a confirmed reset. The
raw classifier therefore contributes no additional selective re-entry event
in this source sample. Nine of twenty next entries were not even aligned with
the raw source side at the displayed open timestamp.

Immutable artifact:
`data/logs/research/hypervelocity_source_reentry_raw_reset_20260731T215250Z.json`

Artifact SHA-256:
`e78641f864deaab51d514071d19fd604b10dc626db697467deee0661ddaeff75`

## Decision, risks, and falsifier

Do not implement raw-reset re-entry authority. Retain raw/confirmed diagnostic
telemetry because it makes live regime behavior auditable, but keep it outside
entry eligibility. Runtime strategy behavior and the armed process remain
unchanged.

Confidence is high for rejecting this exact mechanism on the current 20-window
sample. Confidence is medium outside the sample because creator submissions
can precede displayed maker fills and losing/no-entry records are incomplete.
The conclusion would be falsified by a larger timestamped creator ledger in
which hidden raw reset-and-return events recur before same-side entries and are
rare in matched no-entry windows.
