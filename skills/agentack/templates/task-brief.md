# Task brief

**Task:** <one sentence>
**Feature:** docs/features/<slug>/plan.md → task #<n>   (omit on the Fast path)
**Role:** <be-go | be-node | fe-next | fe-angular | qa | scout | ...>

## Scope
- You may touch: `<path>`, `<path>`
- You may not touch: other modules, `contracts/` (if a change is needed, STOP and report), generated code

## Contract
- `contracts/<module>/openapi.yaml` → operationId: `<...>`
- Generated types: `<path>`

## Acceptance criteria
- [ ] <behavior 1>
- [ ] <behavior 2>
- [ ] Unit tests written and passing

## Verification commands
```
<lint>
<typecheck>
<test>
```

## Previous attempts (filled in on escalation)
<summary + error output>
