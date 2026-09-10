# Phase 9 Step 2 — Business UX and Terminology Report

## Scope and outcome

Phase 9 Step 2 defines the business-first information architecture and language contract without removing or changing the behavior of the existing Phase 1–8 technical workflows.

Implemented in this step:

- the existing Home/Overview and Campaigns entry points are grouped under **Business Workspace**;
- Data Status, Historical Analysis, model management/scoring, and Audience Explorer remain reachable under **Advanced**;
- the combined model/scoring navigation entry is described as **Targeting Intelligence / Model Management** with **Scoring / Targeting Results** as its secondary label;
- the default Home/Overview removes visible `PU` terminology;
- the independent demographic population is described as **Potential Customers** and explicitly as independent people available for targeting;
- the target page map, default campaign flow, terminology matrix, explainer copy, and progressive-disclosure rules are fixed below for the later Phase 9 implementation steps.

No API, schema, database, model, scoring, audience-selection, campaign, export, or lineage behavior changed.

## Information architecture

### Default business navigation target

| Order | Business page | Purpose | Step 2 disposition |
|---:|---|---|---|
| 1 | Home / Overview | Readiness, recent business activity, and direct entry to campaign planning | Existing Overview relabeled and retained |
| 2 | Create Campaign | Guided campaign-to-target-group workflow | Route and wizard owned by Step 4; defined here, not prematurely stubbed |
| 3 | Saved Target Groups | Find and reopen immutable target-group definitions | Business surface completed with the save workflow in Step 10 |
| 4 | Campaigns | Review drafts, finalized campaigns, and exports | Existing Campaigns entry retained in Business Workspace |
| 5 | Insights | Business summaries learned from past campaigns | Business surface to wrap governed historical insight capabilities |

Only working business destinations are exposed in the live navigation at this step. Future destinations are not presented as dead or misleading controls.

### Advanced navigation

| Advanced page | Existing capability preserved | Default/business relationship |
|---|---|---|
| Data Status | Import, source, reconciliation, and schema status | Support and diagnostic workspace |
| Historical Analysis | Existing Phase 2 analysis workflow | Technical source for Past Campaign Insights |
| Targeting Intelligence / Model Management | Existing training, validation, selection, and artifact workflow | Technical management behind Targeting Intelligence |
| Scoring / Targeting Results | Existing scoring workflow, currently combined with model management | Technical provenance behind business targeting results |
| Audience Explorer | Existing Phase 6 filters, rankings, profiles, saves, and reopen behavior | Technical workspace behind Find Target Customers / Target Group |

The Advanced grouping is a navigation boundary, not an authorization or data-contract boundary. Existing routes and view identifiers remain unchanged.

## Default business flow

```text
Create Campaign
  -> Campaign Details
  -> Campaign Context
  -> Targeting Preferences
  -> Target Group Preview
  -> Review
  -> Save Target Group
  -> Create Campaign Draft
```

Flow rules:

1. The business user begins with campaign intent, not data science operations.
2. Campaign Details captures the campaign identity and delivery basics.
3. Campaign Context captures the successful historical outcome and explicit intelligence source context.
4. Targeting Preferences captures business criteria and targeting strength.
5. Target Group Preview explains the estimated group and why people match before any save.
6. Review presents the business choices, estimate, freshness, and optional technical traceability.
7. Save Target Group creates an immutable saved definition under the existing governed audience contracts.
8. Create Campaign Draft links that saved target group to a new governed campaign draft.

## Business terminology matrix

| Technical/internal term | Default business UI | Visibility rule |
|---|---|---|
| Historical Analysis | Learn from Past Campaigns / Past Campaign Insights | Business label; technical label remains under Advanced |
| Positive population | Customers with the selected successful outcome | Business context copy |
| Unlabeled population | Not shown | Hidden from default business UI |
| PU learning | Not shown | Hidden from default business UI |
| Model | Targeting Intelligence | Business label |
| Model Training | Build / Refresh Targeting Intelligence | Business action label |
| Prospect | Potential Customer | Business label; never implies identity linkage |
| Prospect Scoring | Find Similar People / Evaluate Potential Customers | Business action label |
| Propensity Score | Targeting Match Score | Business result label plus mandatory disclaimer |
| Scoring Run | Targeting Results | Business result label |
| Audience Explorer | Find Target Customers / Target Group | Business page/section label |
| Saved Audience | Saved Target Group | Business label; internal names and contracts remain unchanged |
| Rank Band | Match Strength | Business label |
| Percentile | Top Matching % | Business label |
| Algorithm | Algorithm | Advanced details only |
| Artifact SHA | Artifact SHA | Audit details only |
| Feature Contract | Feature Contract | Audit details only |
| Rank Contract | Rank Contract | Audit details only |
| Current | Up to date | Business freshness state |
| Stale | Needs refresh | Business freshness state |
| Calibration | Calibration | Advanced details only |
| Candidate model | Candidate model | Advanced details only |

Default business screens must not require the user to understand `PU`, `P/U`, algorithm, model artifact, scoring run, feature contract, rank contract, SHA, calibration, or candidate model.

## Approved explainer copy

| Term/control | Plain-language help |
|---|---|
| Targeting Match Score | Shows how strongly a Potential Customer matches the patterns in the validated Targeting Intelligence. Use it to compare and rank people, not as a promise that they will buy. |
| Targeting Strength | Controls how narrowly the target group focuses on the strongest matches. A stronger setting selects a smaller, more concentrated group. |
| Potential Customer | A person in the independent population available for targeting. This record is not claimed to be the same person as any historical customer. |
| Saved Target Group | An immutable, reusable definition of who was selected, with the criteria and governed source lineage used at save time. |
| Up to date | The saved result still matches the currently approved source inputs and can be used in the normal workflow. |
| Needs refresh | One or more approved source inputs changed. Review and create a refreshed result before using it in a new campaign. |
| Why these people? | Explains the selected business criteria, targeting strength, match distribution, and approved source context that shaped the target group. It does not claim causation or guarantee an outcome. |

Required score disclaimer, to be shown wherever the business result presents Targeting Match Score:

> Targeting Match Score measures similarity/ranking against the validated targeting intelligence. It is not a guaranteed purchase probability.

## Progressive disclosure and traceability

Every business result must offer an optional **View technical details** control. It is collapsed by default and must not interrupt or dominate the primary task.

Depending on the result, the disclosed details may include:

- analysis run, model, scoring run, saved audience/target-group, campaign, and export identifiers;
- source import identifiers and source fingerprints;
- model artifact path and SHA;
- feature, role-policy, evaluation, rank, filter, selection, analytics, campaign, member-resolution, and export contract versions;
- algorithm, calibration, validation, and currentness diagnostics.

The business summary and the technical detail must describe the same governed result. Progressive disclosure changes presentation only; it must not introduce an alternate calculation or lineage path.

## Data and lineage language boundary

- Historical customer/campaign records and the independent demographic population remain separate source populations.
- **Potential Customer** is the required business term for a person in the independent demographic population.
- UI copy must not say or imply that a Potential Customer is a historically identified customer.
- Similarity/ranking is not identity resolution, a causal claim, or a purchase probability.
- The internal `saved_audiences` naming and immutable provenance contracts remain authoritative underneath the **Saved Target Group** business label.

## Safe UI changes made

| Surface | Before | After | Reason |
|---|---|---|---|
| Primary navigation group | Data Foundation / Audience Intelligence / Campaign Execution | Business Workspace / Advanced | Separates normal business entry points from technical workspaces without deleting any page |
| Overview navigation label | Overview | Home / Overview | Aligns the first business destination with the page map |
| Model/scoring navigation label | Model Training & Prospect Scoring | Targeting Intelligence / Model Management; Scoring / Targeting Results | Preserves the technical destination while introducing the governed business term |
| Overview population metric | Prospect universe | Potential Customers | Applies the terminology contract on the default screen |
| Overview population description | Independent demographic records | Independent people available for targeting | Makes the non-linkage boundary explicit in plain language |
| Overview outcome metric | PU-positive observations | Customers with a successful outcome | Removes required data-science jargon from the default screen |

Existing technical page content was deliberately not bulk-renamed. Those workspaces remain Advanced, and broad copy changes there would risk changing established Phase 1–8 test and operator contracts without improving the default business path.

## Verification

Executed the bounded frontend regression suite after the UI changes:

```text
.venv\Scripts\python.exe -m pytest tests\test_frontend.py tests\test_phase3_hardening.py -q
35 passed in 33.45s
```

New regression coverage verifies that the default Overview uses **Potential Customers**, makes the independent-population boundary explicit, describes the successful-outcome population without `PU`, and no longer exposes the previous `PU-positive` or `Prospect universe` metric labels.

## Step boundary

Step 2 is complete. Schema and API additions, the campaign wizard shell, campaign context capture, targeting controls, intelligence resolution, target-group results, saving, and campaign-draft creation are intentionally deferred to their ordered Phase 9 steps.
