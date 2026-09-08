# V89 completed process storage capture

High confidence in the bounded observations: the diagnostic completed all 181
samples from 04:17:44 to 04:32:44 UTC and exited successfully. Its completed
checksum, source dependencies and 19 retained open-file captures all verified.
The original live processes and public market collector were not controlled by
this diagnostic.

| Measurement | Result |
| --- | ---: |
| Minimum free space | 9,873,084,416 bytes |
| Maximum free space | 15,297,503,232 bytes |
| Observed free-space range | 5,424,418,816 bytes |
| Samples below the importer's 8 GiB requirement | 0 |
| Reporter attributed writes | 3,632,705,536 bytes |
| Docker allocated-block range | 4,448,256 bytes |
| Largest five-second free-space fall | 3,404,550,144 bytes |
| Comparable process writes during that interval | 1,146,880 bytes |
| Maximum diagnostic sample duration | 0.128 seconds |

The reporter repeatedly creates temporary ledger copies, as shown by its open
file ownership and the source copy path. That overhead is measurable and worth
testing independently. The larger free-space changes remain unexplained:
attributed disk writes and net filesystem allocation are different measurements,
and privileged or short-lived activity is incompletely observed. The evidence
does not justify blaming Docker, deleting its data or weakening the importer's
capacity check.

The highest-value next experiment is a bounded snapshot reader that avoids the
repeated copies while preserving exact rows, checksums, complete-line boundaries,
sequence validation and causal cutoffs. Compare disk writes, peak memory and
elapsed time on identical frozen inputs. Any changed output or weaker integrity
check rejects the replacement. This experiment has not yet produced a deployable
change. A broader allocation trace during another event is the minimum additional
evidence needed for whole-system attribution; repeating this same counter sample
would not close its permission and sampling gaps.

The immutable acceptance is
`data/logs/research/bidirectional_cohort/v89_process_storage_acceptance_20260908_v1.json`.
Its standalone executed source and log are beside it. The earlier journal keeps
the qualified running-prefix observation; the next revision records this actual
completion and its limits. No trading strategy or execution change is proposed.
