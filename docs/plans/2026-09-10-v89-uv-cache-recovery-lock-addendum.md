# Passive uv wrapper lock conflict

The initial supported cleanup remained waiting and made no change. Its own
waiting process was terminated; no other service was stopped. Two uv wrapper
processes (785 and 791) have been running for fourteen days. Each has only the
cache-global .lock open; their child Python processes have no cache files open.
All ten selected PyTorch cache roots were independently checked without an open
consumer, and the original active research environment does not contain torch.

The initial no-force method is superseded for this exact package scope by uv's
supported --force option after a fresh wrapper/child/open-file and source-identity
check. This is a bounded cache operation, backed by the verified complete archive;
it does not stop services or change any installed environment. Refuse a new uv
installer, changed wrapper identity, open selected artifact, source drift or
unexpected removal scope. Do not generalize this exception to a full cache clean.

The official uv documentation permits --force when other uv processes are known
not to be reading or writing the cache. Here the surviving processes are passive
service wrappers, rather than package installers. Residual risk is a concurrent
new package operation between observation and cleanup; complete source retention
and a package-specific command bound its recovery. Retain the lock observation,
initial refusal log, exact command and measured post-clean identities.
