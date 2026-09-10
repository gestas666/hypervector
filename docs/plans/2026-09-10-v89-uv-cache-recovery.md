# Recover inactive package-cache capacity

Research is at 44/48 cases with about 3.05 GB free. Preserve the original
coordinator, reporting handoff, source identities, reservations and account data.
All project compiler-cache directories were already removed with verified backups.

Back up the eight PyTorch uv wheel archives, their wheel metadata/symlinks and
the PyPI simple-index record listed in scope.json. Check uv 0.9.5 removal scope
against its versioned source, including alternate/source/flat-index records.
Verify every archive member, mode, logical file hash and symlink, then repeat
the source inventory. The backup retains macOS AppleDouble metadata. Abort before
cleanup if the backup exceeds 1 GiB or leaves less than 2 GiB free.

Use only uv's supported package-specific `uv cache clean torch --offline`
command, without --force and without manual cache deletion. First retain a
nonmutating cleanup assessment, check active open files, and prove the project
environment has no torch installation or cache-linked imports. Preserve installed
environments and original backups. A cache rebuild/download may be needed later;
this changes no installed dependency or live execution setting.

After cleanup, verify the predicted cache entries removed, retained archive hash,
unchanged runtime/profile/binary identities and original research processes.
Measure actual free capacity; hardlinks/APFS sharing can make nominal cache size
overstate recovery. Do not claim an ETA from nominal bytes. Restore only from the
verified archive into a separate directory under exclusive cache ownership if
needed; do not blindly overwrite an actively used uv cache.
