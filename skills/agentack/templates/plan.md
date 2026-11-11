# Feature: <title>

**Slug:** <slug> · **Path:** Fast/Standard/Heavy · **Size:** S/M/L · **Contract:** none/additive/breaking · **Risk:** normal/high

## Goal
<What changes for the user, 2–3 sentences>

## Units and modules affected
| Unit / module | Change | Contract |
|---|---|---|

## Contract changes
- `<contract file>`: <add/change, additive or breaking>

## Tasks
| # | Task | Role | Depends on | Paths |
|---|---|---|---|---|
| 1 | Contract draft | architect | — | <contract path> |
| 2 | Contract gate | contract-guard | 1 | <generated paths> |
| 3 | ... | be-<stack> | 2 | <backend unit>/<module> |
| 4 | ... | fe-<stack> | 2 | <frontend unit>/<feature> |
| 5 | Review | reviewer | 3,4 | — |

## Roles not needed
<e.g. qa: builders' unit tests cover it · decider: no hard-to-reverse decision>

## Acceptance criteria
- [ ]

## Risks and open questions
-
