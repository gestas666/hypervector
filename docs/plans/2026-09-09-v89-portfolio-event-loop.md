# Connect funding, accepted exposure and intrabar risk to the chronological account loop

Continue from holding/pending source `b32374d` and journal revision 12. Work only
in the isolated research worktree. Preserve both prospective outcome seals,
registered economics, the fifteen pinned collector files and live state.

The account currently processes funding, ordinary exits, entries and immediate
exits in one atomic timestamp batch. Intrabar liquidation needs the accepted
quantity, margin, entry fee and funding balance after those preceding actions.
Do not obtain that state by committing half a timestamp or settling funding
twice. Introduce an immutable account preview that uses the same transition
implementation as commit, leaves the original account unchanged, and exposes
the resulting accepted positions, dispositions, closes and snapshot.

Verify preview/commit parity for simultaneous funding, ordinary exits, ordered
entries, rejected entries and immediate exits; repeated previews; failed previews;
terminal preview; and a failed final batch. Existing account and legacy controls
must remain unchanged. No alternative sizing or cash arithmetic is introduced.

Bind each risk calculation to the matching current/projected accepted position.
Only accumulated funding may differ from the lifecycle's original opening
record. Shared liquidation uses the existing isolated-margin helper and the
frozen per-asset maintenance assumption, with accepted rounded quantity, margin,
entry fee and signed cumulative funding. Check independent long/short arithmetic
and funding-before-risk ordering. HYPE's absent historical liquidation trigger
stays explicit; do not borrow a shared model. Nonpositive/undefined boundaries
must remain explicit model limitations rather than fabricated positive prices.

Preserve the two registered exit clocks. The historical `timed_trades` mapping
adds `bar_minutes * 60_000 - 1` to the recorded exit timestamp for stop, target,
liquidation and protective-stop reasons in the late variant. This includes an
opening HYPE protective stop. Do not silently replace that formula with bar end,
clip an explicit recorded opening offset, or apply it to ordinary pending/hold
exits. Native funding settlement S, modeled execution T and source knowledge K
remain distinct. Funding later than an event's modeled clock cannot alter its
liquidation boundary; same-time funding precedes risk and entry sizing.

Then implement the stateful chronological coordinator. Persist per-lifecycle
pending decisions, process open actions before intrabar risk, preserve HYPE and
shared priority differences, and apply close-known decisions only to surviving
positions. Build the proposed route-state update before committing its account
batch; publish both only after all validation succeeds. Reject skipped/repeated
bar phases, stale ownership, duplicate closes, and source events delivered in
the wrong order. Retain every rejected/zero-trade result. Final positions remain
marked, including a pending close with no next study-period opening.

Qualify metadata/source joins and complete provider/regime behavior before
running all 24 registered cells after the seal. Synthetic fixtures may exercise
the entire coordinator now without inspecting prospective outcomes. Compare
event traces and cash to independent references, exercise all seven routes,
archive/reproduce the final implementation, and record remaining limitations.

High confidence requires identical preview/commit arithmetic, exact event and
position attribution, independent risk/clock checks and unchanged legacy controls.
Double funding, changed sizing, premature liquidation, lost pending state,
unregistered clock clipping or failed atomicity falsifies the affected acceptance.
Component success does not establish attainable fills or profitable live trading.
