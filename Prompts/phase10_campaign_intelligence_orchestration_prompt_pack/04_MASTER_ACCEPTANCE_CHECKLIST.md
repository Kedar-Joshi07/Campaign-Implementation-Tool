# Phase 10 Master Acceptance Checklist

## Identity
- [ ] versioned Modeling Context
- [ ] order-insensitive canonical hashes
- [ ] delivery channel excluded
- [ ] campaign details excluded
- [ ] targeting preferences excluded
- [ ] product/type/category/offer/historical-channel included
- [ ] policy versions included

## Historical
- [ ] campaign_categories supported backward-compatibly
- [ ] offer_types supported backward-compatibly
- [ ] old saved analyses still work
- [ ] full canonical date range persisted
- [ ] contacted-only + attributed-purchase policy
- [ ] multi-product ANY-positive proven
- [ ] insufficient history blocks, never broadens

## Compatibility/reuse
- [ ] no latest-run fallback
- [ ] exact historical compatibility
- [ ] exact model compatibility
- [ ] exact scoring compatibility
- [ ] exact rank/analytics readiness
- [ ] READY full reuse
- [ ] rank-only rebuild
- [ ] score-only rebuild
- [ ] model+score rebuild
- [ ] full build
- [ ] delivery channel reuse
- [ ] target-filter reuse

## Orchestration
- [ ] durable persistence
- [ ] idempotent Prepare
- [ ] one active exact build
- [ ] no nested executor deadlock
- [ ] refresh/navigation resume
- [ ] restart reconciliation
- [ ] retry from highest verified stage
- [ ] child lineage persisted

## UI
- [ ] analyst not required in normal business path
- [ ] automatic preparation on preview transition
- [ ] business-friendly progress
- [ ] insufficient-history state
- [ ] retry state
- [ ] technical details hidden by default
- [ ] Phase 9 targeting/preview semantics unchanged
- [ ] no PII

## Lifecycle
- [ ] generation registry
- [ ] protected references
- [ ] non-destructive retirement eligibility
- [ ] no automatic score deletion

## Certification
- [ ] comprehensive tests
- [ ] Phase 1–9 regression
- [ ] bounded clean-room
- [ ] real Chrome/Edge certification
- [ ] clean-head full 5M Phase 10 certification
- [ ] exact-SHA CI
- [ ] Phase 10 GO
