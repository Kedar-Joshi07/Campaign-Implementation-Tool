# Branch Protection for main

This repository cannot be programmatically configured from local CI scripts, so apply the settings in GitHub UI.

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
