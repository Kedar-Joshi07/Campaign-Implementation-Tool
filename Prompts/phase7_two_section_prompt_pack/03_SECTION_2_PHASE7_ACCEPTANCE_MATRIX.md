# Section 2 Phase 7 Acceptance Matrix

Schema:
- [x] v12 additive
- [x] campaigns
- [x] campaign_export_events
- [x] no campaign_members
- [x] no PII columns in campaign tables

Campaign:
- [x] DRAFT
- [x] FINALIZED
- [x] finalized immutable
- [x] current saved audience required
- [x] stale blocks finalize/export

Resolution:
- [x] exact Filter/Rank/Selection v1
- [x] propensity DESC/person_id ASC
- [x] ALL_MATCHING exact
- [x] TOP_N exact
- [x] keyset, no OFFSET
- [x] no 5M Python list/member table

PII/export:
- [x] EMAIL_CONTACT_V1 exact
- [x] DIRECT_MAIL_CONTACT_V1 exact
- [x] no phone v1
- [x] prohibited sensitive fields excluded
- [x] no historical customer_id
- [x] deliverability explicit
- [x] selected=deliverable+undeliverable
- [x] exported rows=deliverable
- [x] CSV injection protected
- [x] no PII logs
- [x] no persistent server CSV
- [x] aggregate export audit only

UI:
- [x] backend wired
- [x] stale campaign read-only
- [x] PII acknowledgement required
- [x] streaming download
- [x] safe export history
- [x] no activation/send

Quality:
- [x] no sampling
- [x] no approximation
- [x] no truncation
- [x] provenance retained
- [x] 60-180 sec exact heavy work allowed when justified

Regression:
- [x] Phase 1-6 intact
- [x] pytest/pip/compileall/diff/validate_data pass
- [x] browser E2E
- [x] no regeneration/retrain/rescore
- [x] no real activation
