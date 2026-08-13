# SOL HT-Breakout Historical/Live Provider Parity

Status: exact-route rejection strengthened  
Execution authority: none  
Runtime strategy changed: false

## Problem and result

The existing research rejects unchanged SOL HT-Breakout for a future profile,
but that conclusion is useful only if the historical reconstruction still
matches the provider currently generating live decisions. This audit ran the
current historical and live provider paths on identical venue-matched SOL bars
and compared decision timestamp, side, and reference price.

All three predeclared windows matched exactly:

| Window | Historical entries | Live entries | Exact matches | Mismatches |
|---|---:|---:|---:|---:|
| Development early | 43 | 43 | 43 | 0 |
| Development late | 28 | 28 | 28 | 0 |
| Opened final, descriptive | 33 | 33 | 33 | 0 |
| Total | 104 | 104 | 104 | 0 |

There were no entries missing from live, no extra live entries, no side
differences, and no reference-price differences. The negative historical SOL
transfer therefore applies to the decision mechanism currently deployed under
the legacy `hype_breakout_onset_bidirectional_v1` identity.

## Validation contract

Each window used fourteen complete days of one-minute Hyperliquid SOL bars:
seven warmup days matching the v25 lookback behavior and seven audited days.
The current live provider and current historical builder independently derived:

- a transition into completed five-minute `BREAKOUT`;
- the completed one-hour SMA10/SMA30 structural entry side;
- decision time at source-bar close plus one minute;
- reference price at the completed source-bar close.

The early and late development windows were used for the parity decision. The
previously opened final window was descriptive only. Source evidence binds the
current v25 config, venue bars and funding, live collector, completed-decision
builder, and historical market builder by SHA-256.

## Relationship to economic evidence

Parity does not create edge. It removes one potential explanation for the
negative route economics.

The existing source-backed rejection reports:

- unchanged 365-day development: 854 trades, PF 0.834, -8,948.62 bps;
- post-hoc tuned development: 502 trades, PF 1.017, +618.28 bps;
- the same tuned rule in the opened final block: 90 trades, PF 0.671,
  -2,056.33 bps;
- prior L2-aligned forward challenger: six resolved, PF 0.151,
  -97.28 bps total.

The new route-priority interaction independently reconstructed the current
extended-hold route and found negative development and final economics on both
long and short sides. Because provider parity is exact in the sampled current
windows, that result cannot be dismissed as an obvious signal-clock or side
mapping mismatch.

## Recommendation

1. Keep exact SOL HT-Breakout rejected from a newly generated successor
   profile.
2. Do not run another parameter sweep over the same mechanism. The prior tuned
   development winner failed its opened final block, and the simple
   breakout-direction challenger was also negative.
3. Do not increase leverage, notional, stop distance, or hold duration to
   compensate for negative expectancy.
4. Preserve the currently running v25 lifecycle and venue stop. This research
   has no authority to close, resize, suppress, or reroute an open position.
5. Continue exact provider/side attribution in the live journal. Reopen the
   exact-route hypothesis only under the existing prospective falsifier: at
   least 20 independently spaced live closes across at least 30 days, PF above
   1.0 after actual costs, positive net, and less than half of gross profit from
   one trade.
6. Move successor work to a different causal mechanism rather than another SOL
   HT-Breakout variation. The next queued route is SPCX Swing canonical-pivot
   and entry-episode attribution; canonical SOL Range Onset remains the sparse
   SOL challenger.

## Confidence, falsifiers, and limitations

High confidence: the current historical and live entry generators match in the
three tested windows. This is directly supported by 104 exact timestamp, side,
and reference-price identities across two development periods and one
descriptive final period.

Medium-high confidence: the exact SOL HT-Breakout rejection remains the correct
future-profile decision. It is supported by parity plus negative development,
failed tuned final, and adverse L2-forward evidence. Confidence is not high
because simulated fills cannot reproduce every live IOC and stop outcome.

The parity claim is falsified by a changed source hash, a missing or extra
provider decision, a side mismatch, or a reference-price mismatch in a newly
audited window. The economic rejection updates only when its prospective
after-cost live falsifier is satisfied or when a genuinely new predeclared
mechanism receives a new identity and independent evidence.

The three finite windows cannot prove parity for every historical bar. The
audit does not reproduce queue position, realized slippage, stop gaps, or
funding settlement latency. The final window was already opened. No live
process, configuration, signal, order, position, stop, target, size, leverage,
allocation, route, priority, or protection changed.

## Evidence

- Current parity artifact:
  `data/logs/research/sol_hype_breakout_provider_parity_20260809T155140Z.json`.
- Prior decision:
  `docs/research-journal/sol-ht-breakout-transfer-v2.json`.
- Current route interaction:
  `data/logs/research/sol_route_priority_interaction_20260809T152921Z.json`.
