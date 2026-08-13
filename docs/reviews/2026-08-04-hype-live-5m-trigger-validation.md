# HYPE Live 5m Trigger Validation

**Observed:** 2026-08-04 EDT  
**Lifecycle:** `HYPE:509645894962`  
**Entry decision:** 2026-08-04 07:30:00 UTC  
**Authority:** report-only; no routing, sizing, exit, or order authority

## Problem restatement

The open HYPE long's entry inspector showed one-minute attribution values of
approximately 0.94x breakout volume and -0.18 bps 20-minute clearance. Those
values appeared inconsistent with a real breakout. The executable provider,
however, is specified to trigger from a completed five-minute breakout onset,
while the one-minute fields are retrospective annotation.

## Independent reconstruction

Hyperliquid's public `candleSnapshot` feed returned 2,880 one-minute HYPE bars.
They were aggregated with the runtime's left-closed five-minute convention and
classified with the current regime contract.

The completed five-minute bar ending at 07:29 UTC was:

- Open: 54.447
- High: 54.665
- Low: 54.447
- Close: 54.649
- Volume: 33,138.19

Its prior 60-bar range high was 54.585. The close cleared that boundary by
11.7248 bps against the configured 8-bps minimum. Volume was 5.2392x its prior
20-bar average of 6,325.075 against the configured 2.5x minimum. The classifier
returned `BREAKOUT`, `BK_UPWARD`, and `confirmed_prior_range_break`.

## Assessment

High confidence: this entry was a valid completed-five-minute breakout under
the current deterministic classifier. The independent public-candle result
matches the backend's recorded reference price, state, volume ratio, direction,
and reason.

The one-minute 0.94x volume and -0.18-bps clearance values are not contradictory
because they answer a different question: what the final one-minute bar looked
like at entry, not whether the completed five-minute trigger qualified. They
remain useful as outcome-attribution features but do not authorize execution.

The TUI label now explicitly says `HYPE 1M ATTRIBUTION`, `REPORT ONLY`, and
`NOT EXECUTION TRIGGER`. This is a display clarification only; the running
backend and protected position were not changed or restarted.

This assessment would be falsified by a mismatch between the venue candle
payload and the backend's original input, a different runtime resampling
boundary, or a runtime classifier/configuration fingerprint that differs from
the current recorded profile.

