# Phase 9 End-to-End Test Matrix

## Campaign details
- valid create
- blank name
- date preservation
- Back/Next persistence

## Campaign context
- one product
- multiple products
- multiple campaign types
- category
- offer
- channel
- invalid option
- canonical order/deduplication

## Targeting
- each Match Strength
- multi-gender
- each age bucket
- multiple age buckets
- state multi-select
- income multi-select
- advanced demographic
- TOP_N
- clear one
- clear all
- invalid combination
- zero-result combination

## Targeting source
- READY
- STALE
- NOT_AVAILABLE
- INCOMPATIBLE_CONTEXT
- no silent latest-run fallback

## Preview
- exact counts
- distribution
- demographics
- pagination
- deterministic order
- no PII
- Why these people?
- technical details

## Recommendation
- Very Strong usable
- Strong recommended
- Strong too small → Good
- all too small
- disclaimer

## Save / campaign
- save target group
- immutable saved audience
- create campaign draft
- reopen
- criteria changed after save → new target group
- stale target group handling

## UI quality
- keyboard
- focus
- mobile/tablet/desktop
- loading/error/empty
- console/network clean

## Regression
- legacy technical pages
- legacy Audience Explorer
- legacy Campaign Builder
- exports
- currentness
