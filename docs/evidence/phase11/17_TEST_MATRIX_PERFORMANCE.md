# Phase 11 Step 17 — Comprehensive Test Matrix and Performance Gates

Date: 2026-09-17

## Outcome

Step 17 is complete. The bounded functional, UI-contract, privacy, compatibility,
and performance gates passed before the later clean-room, installed-system-browser,
and real-5M certifications in Steps 18–20.

This step did not import canonical data, train a model, score the 5M population,
create an atomic-segment index, or run outbound activation. Performance numbers
below are measured local-fixture observations, not production SLA claims.

## Comprehensive matrix

| Area | Result | Executed proof |
| --- | --- | --- |
| A. Navigation/UI | PASS | The three business tabs, canonical/direct routes, hidden-but-retained legacy views, redirects, history behavior, and immutable view contract passed in `test_phase11_business_navigation.py`. |
| B. Multi-select | PASS | Search, select/deselect, filtered select-all, clear, chips, keyboard navigation, Escape/Tab/outside focus, ARIA, native value round-trip, reset/destroy, duplicate prevention, all 16 adapters, error recovery, and 48/51/500-option behavior passed in `test_phase11_multi_select_dropdown.py`. |
| C. Search-run persistence | PASS | Each intentional submit creates a distinct immutable run; exact hashes, statuses, transitions, reload/reopen, restart visibility, and safe retained failure history passed across the registry, search-form, smart-reuse, and API suites. |
| D. Exact-result cache | PASS | Exact current reuse, criteria/selection/contract drift misses, missing/corrupt/checksum/count rejection, stale-generation rejection, deterministic repair, and artifact validation passed in `test_phase11_smart_reuse_engine.py` and `test_phase11_result_snapshot_materialization.py`. |
| E. Intelligence reuse | PASS | Delivery-profile-only changes and changed age/gender/state/income targeting reuse the same Phase 10 intelligence without new model/scoring rows, while producing the correct distinct exact membership identity. |
| F. New build | PASS | Incompatible/not-ready Phase 10 state is durably handed to the existing Phase 10 orchestration boundary, resumes once, records `NEW_INTELLIGENCE_BUILD`, and does not duplicate orchestration. No real training/scoring was launched in this bounded step. |
| G. Result snapshot | PASS | Exact row count/checksum, five-field no-contact-PII schema, deterministic gzip bytes and manifest, atomic publication, rollback/orphan recovery, immutable identity, zero rows, repair, and shared snapshot reuse passed. |
| H. Profiles | PASS | EMAIL, DIRECT_MAIL, SMS, WHATSAPP, TELEMARKETING, PAID_SOCIAL, and PAID_SEARCH validators, field allowlists, identifier validity, consent/contactability, exact counts, and checksums passed. MOBILE_PUSH, DISPLAY, and WEBSITE_ONSITE gated-source availability behavior also passed. |
| I. Paid media | PASS | Email/phone normalization and SHA-256 hashes are deterministic; paid-media files contain hashes instead of raw identifiers; the contract and UI describe the output as pseudonymous, not anonymous. |
| J. Contactability source | PASS | Deterministic generation, chunk-size independence, import provenance, impossible-state validation, migration preservation, and the unchanged frozen model feature contract passed. |
| K. Results UI | PASS | Newest-first history, active-only refresh, blocked/failed/completed states, pagination, responsive detail, progressive disclosure, safe download visibility, and no contact PII passed. |
| L. Privacy | PASS | Default business JSON APIs were recursively checked for contact values, raw paths, SQL, and stack traces. Registry/snapshot schemas reject nested contact or membership metadata. Contact PII appears only in an authorized governed download stream. |
| M. Phase 1–10 regression | PASS | The bounded retained regression completed with 655 passed; browser, clean-room, explicit performance, and full-5M markers were intentionally left to their owning certification steps. |

## Performance methodology

`tests/test_phase11_performance_gates.py` uses isolated temporary schema-18
databases, real Phase 11 API/service/repository/materialization/export code, and
a deterministic 20,000-member analytical fixture. It opens no canonical database.

- Home, options, history, snapshot reads, and exact reuse use five repetitions.
- Each export profile uses three complete streamed downloads.
- Snapshot publication is measured once because every publication must use a new
  immutable identity.
- No absolute response-time threshold is asserted.
- The one required relative gate is exact reuse versus re-filter/materialize.
  Exact reuse must be at least 1.25 times faster for the same fixture.
- The exact-hit run injects a membership source that raises if invoked. It was
  called zero times, proving that the cache path did not filter or scan score
  membership.

Machine-readable samples are retained in
`docs/evidence/phase11/17_performance_metrics.json`.

## Measured performance

| Operation | Repetitions | Median seconds | Notes |
| --- | ---: | ---: | --- |
| Home load | 5 | 0.059934 | Metadata-only `/api/business/overview` |
| Options load | 5 | 0.564070 | Backend-owned search options |
| Exact cache hit | 5 | 0.599704 | Zero membership-source calls; no propensity-score population scan |
| Intelligence-reuse filter/materialize | 5 | 1.543939 | 20,000 analytical membership rows per snapshot |
| Snapshot write | 1 | 1.369815 | Atomic gzip + manifest + registry publication, 20,000 rows |
| Snapshot read/validation | 5 | 0.154087 | Full immutable artifact/manifest validation |
| Result history | 5 | 0.150355 | Business results API, bounded to 20 |

The refreshed exact-cache speedup was **2.575×**, so the required material
advantage passed. Exact and intelligence-reuse runs shared the same Phase 10
generation; only the exact targeting/membership key changed.

### Export profile medians

| Profile | Median seconds | Stream bytes |
| --- | ---: | ---: |
| EMAIL_CONTACT_V1 | 0.507480 | 152 |
| DIRECT_MAIL_CONTACT_V1 | 0.539510 | 300 |
| SMS_CONTACT_V1 | 0.550907 | 154 |
| WHATSAPP_CONTACT_V1 | 0.557891 | 206 |
| TELEMARKETING_CONTACT_V1 | 0.498830 | 154 |
| PAID_SOCIAL_AUDIENCE_V1 | 0.638233 | 409 |
| PAID_SEARCH_AUDIENCE_V1 | 0.499300 | 409 |
| MOBILE_PUSH_CONTACT_V1 | 0.556281 | 126 |
| DISPLAY_AUDIENCE_V1 | 0.547198 | 189 |
| WEBSITE_AUDIENCE_V1 | 0.547652 | 187 |

The export fixture contains governed deterministic identifiers for gated
profiles so their streaming path can be measured. Separate availability tests
prove those profiles remain blocked when their required source fields are not
present; identifiers are never invented at export time.

## Optional atomic-segment comparison

No additional candidate was implemented, so a candidate before/after comparison
is not applicable. After Step 20 created current generation 1/scoring run 3,
Step 10 reran all seven required shapes against the current schema-18 5M source.
All repeated results were stable; p50-like medians ranged from 1.612901 seconds
to 10.889234 seconds. The evidence-backed decision retained the existing indexed
Audience Engine because no additional atomic structure demonstrated a net
runtime/storage benefit without adding generation-specific build, invalidation,
and recovery cost. Exact-result reuse remains the zero-rescan optimization.

Current machine evidence is in `10_atomic_segment_benchmark.json`; the earlier
schema-15 file remains historical reference only.

## Test execution

Bounded Phase 11 service/repository/API matrix:

```text
python -m pytest tests -k phase11 \
  -m "not browser and not performance and not full5m and not cleanroom" -q

200 passed, 763 deselected in 293.08s
```

Headless browser UI-contract matrix:

```text
python -m pytest tests -k phase11 \
  -m "browser and not full5m and not cleanroom" -q

61 passed, 899 deselected in 204.68s
```

Bounded performance gate:

```text
PHASE11_STEP17_METRICS=docs/evidence/phase11/17_performance_metrics.json \
python -m pytest tests/test_phase11_performance_gates.py -q

1 passed in 66.77s
```

Retained Phase 1–10 bounded regression:

```text
python -m pytest tests -k "not phase11" \
  -m "not browser and not cleanroom and not full5m and not performance" -q

655 passed, 305 deselected in 1496.52s
```

Aggregate non-overlapping result: **917 passed**.

## Corrected regression assertion

The first permitted browser run exposed one stale test selector. The Results
card has intentionally used a semantic `<h3>` campaign heading since Step 12,
but one Step 8 integration assertion still looked for the removed `<strong>`
element. The assertion was corrected to the current accessible heading contract.
The focused case then passed, followed by all 61 browser cases.

The original sandboxed browser attempt also produced Windows named-pipe access
errors before test setup. The identical suite was rerun with the required local
browser-process permission; those setup errors were environmental and are not
counted as product results.

## Guardrail confirmation

- No canonical data import or regeneration ran.
- No production model training, scoring, ranking, or Phase 10 build ran.
- No 5M score scan ran.
- No atomic-segment index was added.
- No activation/send integration ran.
- No clean-room or installed-system-browser certification was claimed.
- No files were staged, committed, or pushed.
