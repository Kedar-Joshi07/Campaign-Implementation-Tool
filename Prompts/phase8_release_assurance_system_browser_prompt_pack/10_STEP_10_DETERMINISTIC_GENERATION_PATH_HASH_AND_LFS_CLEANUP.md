# Step 10 — Deterministic GZIP, Portable Paths, Hashes & LFS

Close reproducibility/documentation drift without changing synthetic business content.

## Deterministic GZIP
Inspect canonical generators and make compressed output byte-deterministic where feasible:
- fixed gzip mtime
- deterministic embedded filename behavior
- fixed compression level
- stable encoding/newline behavior

Same code + seed + dependency lock should produce the same decompressed content and ideally identical compressed bytes/LFS object.

Regenerate into a temporary validation location first.

Compare:
- row counts
- decompressed canonical-content SHA
- raw GZIP SHA

Unexpected decompressed-content drift = NO-GO.

## Portable paths
Remove absolute developer-machine paths from canonical summary JSON/manifests. Use repository-relative paths or logical source names.

Environment-specific paths may remain only in clearly marked runtime evidence and should be sanitized where practical.

## Documentation/hash refresh
After equivalence is proven, update:
- root/data documentation
- evidence registry
- raw compressed SHA references
- LFS object references
- distinction between raw SHA and source/content provenance checksum

## LFS
Run:
- git lfs status
- git lfs ls-files

Verify no duplicate nested full datasets or large non-LFS copies.

Create `docs/evidence/phase8/10_REPRODUCIBILITY_AND_LFS_REPORT.md`.

STOP.
