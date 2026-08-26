# Single Master Prompt — Final Phase 5 Corrections Before Phase 6

Repository: `https://github.com/Kedar-Joshi07/Campaign-Implementation-Tool.git`
Required starting HEAD: `eeed03d052cc75987cc8926b088d906ae0fb7ccc`

Do NOT implement Phase 6.

Phase 5 current 5M score calculation is accepted. Fix only remaining lifecycle/provenance defects.

## 1. Atomic demographic replacement

Replace live-table batch commits with staging/atomic replacement.

Invariant:

```text
success => live demographics exactly equals new source
failure => live demographics exactly equals previous source
```

Do not delete historical propensity scores. Mark import COMPLETED only after live replacement succeeds. Add forced mid-import and swap-failure tests.

## 2. Source-aware scoring lifecycle

Allow multiple historical COMPLETED score runs for the same model across different demographic sources. Remove/replace the one-COMPLETED-per-model invariant.

Current/canonical means COMPLETED + reconciled + valid model/artifact/feature provenance + demographic provenance matching CURRENT loaded source.

Stale completed runs remain history. Same model + changed source must become score-eligible again.

## 3. API semantics

Scoring-status and scoring-run detail must evaluate current source match:

```text
current => demographic_source_verified=true
stale => false
stale does not disable scoring
current blocks duplicate scoring
```

No paths, PII, individual scores, SQL, or traceback.

## 4. Regression

Prove with bounded fixture:

```text
Source A → Run A current
Source B atomic replace
Run A historical/stale
same model eligible
Run B completes/current
Run A still COMPLETED
```

Also prove failed Source B replacement leaves Source A untouched and Run A current. Run full regression and commit a sanitized evidence JSON.

## 5. Freeze

Update Phase 5 summary/tracker/acceptance/handoff. Preserve historical evidence.

Feature contract remains version 1 / SHA `a0cd5e8f95850337e239cc568b35b7d4f1d1fcca8adc364c3ee1d35c9b5a8535`.

No Audience Explorer, score bands, audience selection, campaign builder, export, or activation.

Create final correction commit. Actual final HEAD becomes Phase 6 starting SHA.

Final report: starting/final SHA, atomic replacement, canonical lifecycle, migration/index changes, historical coexistence, API semantics, tests, evidence, no Phase 6 scope creep, GO/NO-GO.

STOP.
