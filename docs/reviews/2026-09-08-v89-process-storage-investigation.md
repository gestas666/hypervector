# V89 process attribution for recurring storage pressure

The bounded storage experiment now records process I/O counters and open writable
file metadata alongside filesystem capacity. This supplies a discriminating
observation that was absent from the earlier file-only samples. Confidence is
high in the controlled counter test and sampled process ownership, but the
multi-gigabyte free-space changes remain unattributed.

## Instrument qualification

The read-only C probe uses the installed Darwin SDK declarations for
`proc_pid_rusage` and `rusage_info_v2`. Its source and compiled binary are hashed.
A controlled, synced 16 MiB file write produced exactly 16 MiB of additional
attributed process writes. This validates that counter in this environment; it
does not equate cumulative disk I/O with net filesystem allocation. The API
fields are also present in
[Apple's published source](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/resource.h).

Nine offline tests passed, covering interval attribution, PID reuse, new and
exited processes, permission failures, counter reversal and lsof ownership
boundaries. The first launch failed before writing any samples because the
minimal environment omitted `/usr/sbin` from PATH. Its source, manifest and
failure log remain preserved. The corrected source uses verified absolute paths
for `ps` and `lsof`, passed the same tests and started a separate output version.
No live process was restarted.

## Bounded observation and remaining uncertainty

The corrected capture is PID 86437, started 2026-09-08 04:17:43 UTC. It is
scheduled to take 181 samples at five-second intervals and terminate after
fifteen minutes. A frozen 97-sample prefix records the process alive; completion
must be established from its actual terminal status and completed artifact.

The sample caught multi-gigabyte space changes without corresponding writes in
the accessible process counters. Docker allocated blocks stayed approximately
constant and a separate system check reported no swap usage. Unprivileged
`fs_usage` required root; a noninteractive privileged attempt required a
password. No password was requested or security setting changed. A full lsof
inventory yielded 2,632 writable file observations; 59 later metadata reads were
explicitly unavailable due to permissions. These gaps prevent whole-system
attribution.

The reporter's own I/O and temporary files are observable. It repeatedly writes
approximately 134 MiB of ledger copies. The sampled open-file ownership points
to `_loaded_suffix_snapshot` in `live_ledger_snapshot.py`, which copies source
suffixes into named temporary files before projection and hashing. This is a
confirmed reporting cost; it is not proven to explain the larger space drops.

The next improvement experiment should compare a bounded read-only snapshot
reader with the current copy path, requiring identical selected rows, source
checksums, sequence bounds, partial-tail handling and causal cutoff behavior.
Measure disk writes, peak memory and latency on the same frozen inputs. A
changed output or weaker corruption detection rejects the replacement. No
reporting replacement or live configuration change has been deployed.

Artifacts under `data/logs/research/bidirectional_cohort/` retain the native probe,
positive control, both launch versions, test logs, full open-file observations
and `v89_process_storage_midpoint_20260908_v1/`. The running capture's mutable
sample file is not treated as immutable completed evidence.
