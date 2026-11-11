# Brief · <role>

<!-- Style: structured. For build-class models (Sonnet and peers). Name the files, give the steps
     and the boundaries; details inside them are the worker's call. -->

**Task:** <one sentence>
**Feature:** docs/features/<slug>/plan.md → task #<n>   (omit on the Fast path)

## Files
- Change: `<path>`, `<path>`
- Read for reference: `<path>`
- Off limits: other modules or services, contract files (if one needs to change, STOP and report), generated code

## Steps
1. <step>
2. <step>
3. Write or update the unit tests for the new behavior

## Contract
- `<contract file>` → operation: `<...>` · generated types: `<path>`

## Acceptance criteria
- [ ] <behavior 1>
- [ ] <behavior 2>

## Verification commands
```
<lint>
<typecheck>
<test>
```

## Output
Your role's return format: changed files, check results, decisions, open questions.
