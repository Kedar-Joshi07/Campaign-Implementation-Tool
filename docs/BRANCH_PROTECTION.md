# Branch Protection for main

This repository cannot be programmatically configured from local CI scripts, so apply the settings in GitHub UI.

## Current verification status

Verified through the public GitHub API on 2026-09-21:

- repository: `Kedar-Joshi07/Campaign-Implementation-Tool`;
- default branch: `main`;
- remote `main` SHA: `9009e23b750000d3f3d29e09204281f3d301e640`;
- branch metadata: `protected=false`;
- authenticated protection-detail endpoint: unavailable (`401 Requires authentication`);
- GitHub CLI/admin credentials: not available in the certification environment.

Branch protection is therefore **not currently enabled or verified as enabled**. The settings below remain an explicit repository-governance follow-up. This does not invalidate the certified runtime behavior, but protection must be applied and re-read through an authenticated administrator account before claiming the repository-governance gate complete.

The latest remote-main CI run at the time of this check was run `#23` (`35514589328`) for the exact remote SHA above. Repository Hygiene, Python Validation, Tests, Clean-Room Phase1-7, and Frontend Contract all completed successfully. This green run does not substitute for branch protection and does not certify later local/uncommitted changes.

## Required status checks

Set these exact checks as required on branch main:

- Repository Hygiene
- Python Validation
- Tests
- Clean-Room Phase1-7
- Frontend Contract

## UI steps

1. Open repository Settings.
2. Open Branches.
3. Under Branch protection rules, click Add rule.
4. Branch name pattern: main.
5. Enable Require a pull request before merging.
6. Enable Require approvals and set the review count to your team standard.
7. Enable Require status checks to pass before merging.
8. Select the exact required checks listed above.
9. Enable Require branches to be up to date before merging.
10. Enable Do not allow bypassing the above settings.
11. Save changes.

## Notes

- Keep direct pushes to main disabled after this rule is active.
- Full Validation (Manual) is intentionally not a required check because it is workflow_dispatch only.
