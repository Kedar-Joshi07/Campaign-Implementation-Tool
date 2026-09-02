# Section 2 Phase 7 Acceptance Matrix

Schema:
- [ ] v11 additive
- [ ] campaigns
- [ ] campaign_export_events
- [ ] no campaign_members
- [ ] no PII columns in campaign tables

Campaign:
- [ ] DRAFT
- [ ] FINALIZED
- [ ] finalized immutable
- [ ] current saved audience required
- [ ] stale blocks finalize/export

Resolution:
- [ ] exact Filter/Rank/Selection v1
- [ ] propensity DESC/person_id ASC
- [ ] ALL_MATCHING exact
- [ ] TOP_N exact
- [ ] keyset, no OFFSET
- [ ] no 5M Python list/member table

PII/export:
- [ ] EMAIL_CONTACT_V1 exact
- [ ] DIRECT_MAIL_CONTACT_V1 exact
- [ ] no phone v1
- [ ] prohibited sensitive fields excluded
- [ ] no historical customer_id
- [ ] deliverability explicit
- [ ] selected=deliverable+undeliverable
- [ ] exported rows=deliverable
- [ ] CSV injection protected
- [ ] no PII logs
- [ ] no persistent server CSV
- [ ] aggregate export audit only

UI:
- [ ] backend wired
- [ ] stale campaign read-only
- [ ] PII acknowledgement required
- [ ] streaming download
- [ ] safe export history
- [ ] no activation/send

Quality:
- [ ] no sampling
- [ ] no approximation
- [ ] no truncation
- [ ] provenance retained
- [ ] 60–180 sec exact heavy work allowed when justified

Regression:
- [ ] Phase 1–6 intact
- [ ] pytest/pip/compileall/diff/validate_data pass
- [ ] browser E2E
- [ ] no regeneration/retrain/rescore
- [ ] no real activation
