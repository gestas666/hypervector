# V89 SPCX short at 18:00 UTC: signal and protection receipts

High confidence within the retained evidence: the September 16 SPCX short
matches the completed hourly band re-entry condition, configured 10x isolated
leverage and a covering venue stop. This establishes a technically consistent
entry, not profitable expectancy or the eventual outcome. No live source,
strategy setting or financial process was changed during this investigation.

The live backend remains process 67727, run `bidirectional-live-1789569979897`.
The approved restart had already succeeded. Its new SPCX entry was detected
while checking that approval, so this investigation took priority over the
planned independent native-minute collector. That collector has not been
implemented or started.

The audit retained complete, contiguous current-run ledger ranges: 3,620 cohort
records / 36,990,351 bytes and 3,256 asset records / 4,729,951 bytes. Compressed
copies reproduce the original bytes and their SHA256 digests. The initial
asset-capture assertion correctly rejected the checkpoint's compatible-history
offset, which includes earlier runs. The existing current-run snapshot reader
then selected the correct boundary. The failed assertion and its correction
are retained; no original evidence was overwritten.

The actual September 16 pre-start manifest and five relevant implementation
and configuration files were authenticated against their compressed backups.
Their current bytes match that backup. This pins the inspected mechanism to
the running generation without reinstalling it.

| Check | Observation and validation |
| --- | --- |
| Input window | 1,260 completed native minutes, September 15 21:00 through September 16 17:59 UTC, form 21 complete hours. Startup input and later cohort publications had no conflicting overlapping OHLCV values in this window. |
| Previous hour | Close 151.81 exceeded its upper band 151.40250357463742. No fresh entry was recorded at 17:00. |
| Current hour | Close 150.97 returned below upper band 152.1676677208123 while remaining above mean 145.6985, satisfying the short re-entry condition. |
| Independent arithmetic | Decimal population-variance calculations and NumPy calculations agree with all six recorded band metrics within 1e−10; largest Decimal-to-record difference is about 4.52e−14. Both calculations share the selected input records. |
| ATR recurrence | `(19 × 1.1671127313962324 + 2.23) / 20 = 1.22025709482642078`; recorded ATR differs by 5.8e−16. This checks one update from recorded prior state, not the original seed. |
| Stop anchor | `150.97 + 2 × 1.2202570948264202 = 153.4105141896528404`, matching the execution plan within 1e−10. Recorded venue trigger: 153.41. |
| Causality | Latest required candle publication was at 18:00:08.203… UTC, before the asset decision at 18:00:08.204615. The later intent-routing report at 18:00:22.000855 is not used as the input-availability cutoff. |
| Entry | Order 546992644531 filled short 3.31 at 150.92: $499.5452 against the configured $500 notional cap; fee $0.04316. Dispatch age 8,206 ms was within the configured 30,000 ms deadline. |
| Protection | Order 546992931088 was accepted resting. All 84 subsequent captured reconciliations show a 3.31-unit reduce-only buy Stop Market at 153.41. All 84 nonflat position records report −3.31 units and 10x isolated leverage, through 18:20:47.169865 UTC. |

The entry's 1m regime was TREND_DOWN while 5m and 15m were TREND_UP. The recorded
alignment was −2/3, labelled directionally opposed. This countertrend context
does not contradict the approved mean-reversion entry rule. It remains a
descriptive observation and does not justify inventing a new veto from one
trade.

Protection timing deserves the next bounded investigation. The venue fill was
timestamped 18:00:09.455 UTC, the local entry acknowledgement 10.828766, the
PROTECTING transition 14.713926, the stop intent 14.714617 and the local resting
acknowledgement 17.603999. Fill to local stop acknowledgement was 8.148999
seconds; entry acknowledgement to PROTECTING was 3.885160 seconds. These are
different clock domains for the first interval. The venue's actual stop
activation timestamp and request-level timing within the middle interval are
unavailable. This is an observed latency investigation, not yet a demonstrated
defect or an assertion that the position lacked protection for that exact time.

Recommendation: preserve the current approved settings on this evidence and
trace the intervening reconciliation calls before proposing a latency change.
The simpler alternative is to continue observing subsequent entries; that
avoids implementation work but leaves this interval unexplained. Changing entry
rules or leverage has no demonstrated advantage from this one observation.
Any eventual execution change requires a separate concrete, validated proposal.
No approval is requested for this read-only work.

Falsifiers include changed source bytes, a missing or future required candle,
different band arithmetic, a noncovering stop, unexpected leverage or duplicate
entry identity. Complete ATR-seed reproduction, independent input-reader
reproduction, venue stop-activation timing and the final trade outcome remain
outside this result. No sealed prospective performance study was opened.

Evidence directory:
`data/logs/research/bidirectional_cohort/v89_captured_provider_assembly_20260916_v1/spcx_short_entry_1800_20260916_v1/`.

The immutable `capture.json`, `completed_entry_inputs.json`,
`signal_validation.json` and `execution_validation.json` contain the byte
identities, numerical comparisons and observation counts.
