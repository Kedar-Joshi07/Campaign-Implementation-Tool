# Stage 14B_04 resumable scoring, attestation, and reuse

Recorded 2026-10-06 from `main` at starting/current HEAD
`336875c30fc32b00323d916ecc45b232016168a1`. The candidate remains
`UNCOMMITTED`. Stage 14B_03 was the preceding GO. This stage did not commit,
push, migrate the operator database, change canonical inputs, run five-million
row scoring, or execute Stage 14B_05.

## Implemented contract

V3 scoring has its own repository and service path. A generation is identified
by the immutable published profile and artifact, current demographic import and
checksum, `BUYER_PROFILE_DISTANCE_V1`, and scorer contract 1. Threshold,
audience-filter, and export choices are absent from that identity and therefore
cannot cause a rescore. The existing v1/v2 probability and calibration paths
are not consulted or changed.

Before work starts, the estimator reports profiles already reusable, profiles
requiring builds, exact score-row work, feature-distance terms, approximate
peak persistent bytes, and whether multiple new products warrant explicit
operator confirmation. The 50-profile request limit is only an input bound; it
does not eagerly build every catalog product.

The worker streams demographics in stable `person_id` order using bounded
keyset chunks. Every source person produces exactly one staged row: either a
finite `[0,1]` similarity score with valid coverage and prototype key, or an
explicit invalid row with no score/prototype and a bounded reason. IDs and
contact fields are never model features and are not copied into analytical
metadata. Queue time is a separate stage; scoring progress and heartbeats are
written transactionally with each actual chunk and checkpoint.

Same-token recovery resumes after the committed checkpoint. A stale-lease
reclaim deliberately clears the old incomplete stage and restarts from zero,
which is cheaper and easier to verify than accepting mixed-token stage rows.
The generation identity remains the same, but the new token fences every
write; an old token cannot append, cancel, verify, or publish. Cancellation and
source replacement remove incomplete stage rows and end in `FAILED` or `STALE`
without published scores.

Deep verification runs once before first publication. It independently checks
the current profile artifact checksum, latest demographic import/checksum and
live population, exact row count, distinct population equality, no missing or
extra people, valid plus invalid accounting, finite score/coverage bounds,
valid/invalid reason consistency, allowed prototype keys, and completed
checkpoint. Its facts and failure codes are persisted in an immutable
generation attestation. Only a verified stage is copied into published scores,
the stage is removed, and the generation is marked `PUBLISHED` in one
transaction. Failed verification publishes nothing.

Normal reuse checks the latest authoritative customer, sales, and demographic
import metadata plus the small profile artifact checksum and stored
attestation. It does not rescan the score population. Multi-product composition
accepts only current attested generations, deduplicates by person, selects the
maximum valid similarity, and resolves an exact score tie by ascending
`product_id` (then generation ID).

## Verification

- Focused Stage 14B_04 test matrix: 13 tests passed as part of the final
  affected run, covering chunked publication and
  reuse, chunk-size independence, checkpoint resume, concurrent claim,
  stale-lease restart and fencing, missing/extra/duplicate populations, source
  replacement, corrupt artifact, two-product max/dedup/exact tie, cancellation,
  resource estimation, subminimum valid-coverage rejection, and v2-calibration
  independence.
- Affected Stage 14B_01 through 14B_04, legacy selection, and Phase 10
  compatibility regression: 95 tests passed in 169.89s.
- `python scripts/validation/audit_14b_04_scoring_attestation.py` passed against
  a 1,000-person canonical sample. The source database was opened SQLite
  `mode=ro`; all writes and artifacts were confined to a removed temporary
  directory.
- The bounded audit published 1,000 exact unique rows in chunks of 137, recorded
  1,000 valid and zero invalid rows, removed staging after publication, verified
  currentness, and reused the generation without another deep scan.
- Targeted compilation and evidence JSON parsing passed. Ruff is not installed
  in the repository virtual environment, so no Ruff result is claimed.

## Decision and boundary

Decision: **GO** for the bounded Stage 14B_04 scoring and attestation contract.
The score remains a descriptive buyer-similarity index, not probability,
confidence, predictive validation, or campaign effectiveness evidence.

The canonical five-million-person database was not scored. Full-scale runtime,
performance, disk, recovery, and clean-machine proof belongs to Stage 14B_16.
API/UI selection, result materialization, exports, and the next integration
surface belong to later sequential stages. No remote CI or release claim is
made.
