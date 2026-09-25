# VTAB Square — Development to Production release policy

**Source of truth:** GitHub. Google Drive Development/Production folders hold artifacts and evidence, not competing copies of active source code.

## Branches
- `feature/<ticket>-<description>`: implement and test a change; open PR to `develop`.
- `develop`: integration branch; deploy only to an isolated DEV environment after that application's DEV configuration is ready.
- Existing default branch (`main` or `master`): production source; promote only through reviewed PR from `develop` and tag the approved commit `vMAJOR.MINOR.PATCH`.
- Hotfix: branch from production release, test, promote, then merge back to `develop`.

## Promotion checklist
- [ ] Review code and identify the exact commit, app, hosting target, and dependencies.
- [ ] Run build/tests and DEV smoke tests using sanitized test data.
- [ ] Verify login, core workflow, Contact for Demo CTA/product attribution, and test email where relevant.
- [ ] Review database migration and rollback steps; back up PROD if needed.
- [ ] Record release version, approver, test evidence, and previous production tag.
- [ ] Merge approved PR to production branch; tag and deploy that exact commit.
- [ ] Check client URL, core workflow, logs, and demo enquiry; rollback if checks fail.

**Safety:** Do not point DEV at production databases, storage, credentials, or live lead-email destinations. Do not change existing client-demo deployment branches until an isolated DEV service and its credentials are verified. Branch protection, required reviews/checks, and deployment approval must be configured by a GitHub administrator; this file alone does not enforce them.
