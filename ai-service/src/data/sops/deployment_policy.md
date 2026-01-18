# Deployment Policy

## Purpose
This policy defines the rules for deploying code to production.

## General Rules

### Rule 1: Linear Issue Required

## Trigger
GitHub PR is opened or updated

## Condition
- PR body does not contain a valid Linear Issue reference (LIN-XXX)
- No linked Linear Issue in the PR description

## Action
- Block the PR with a comment requesting Linear Issue linkage
- Do not allow merge until LIN-XXX is added

---

### Rule 2: Issue State Validation

## Trigger
GitHub PR is ready for review

## Condition
- Linked Linear Issue is in BACKLOG state
- Linked Linear Issue is in CANCELLED state
- Linked Linear Issue is in DONE state

## Action
- Warn the author that the issue should be in IN_PROGRESS or REVIEW state
- Request author to update the issue state before proceeding

---

### Rule 3: Friday Deploy Restriction

## Trigger
PR is approved and ready to merge

## Condition
- Current day is Friday (weekday == 4)
- Current time is after 3 PM
- PR does not have "emergency" label

## Action
- Block the merge
- Comment explaining that Friday afternoon deploys require emergency justification
- Suggest scheduling for Monday

### Severity: block

---

### Rule 4: Test Coverage Requirement

## Trigger
CI pipeline completes

## Condition
- Test coverage drops below 80%
- No new tests added for changed files

## Action
- Fail the CI build
- Post comment with coverage report
- Request minimum 80% coverage
