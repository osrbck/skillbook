# Feature: <title>

**Slug:** <slug> · **Path:** Fast/Standard/Heavy · **Size:** S/M/L · **Contract:** none/additive/breaking · **Risk:** normal/high

## Goal
<What changes for the user, 2–3 sentences>

## Modules affected
| Module | Change | Contract |
|---|---|---|

## Contract changes
- `contracts/<module>/openapi.yaml`: <add/change>
- `contracts/<module>/events.asyncapi.yaml`: <...>

## Tasks
| # | Task | Role | Depends on | Paths |
|---|---|---|---|---|
| 1 | Contract draft | architect | — | contracts/<module> |
| 2 | Contract gate | contract-guard | 1 | packages/api-client, gen/ |
| 3 | ... | be-go | 2 | apps/api-go/internal/modules/<module> |
| 4 | ... | fe-next | 2 | apps/web-next/... |
| 5 | Review | reviewer | 3,4 | — |

## Roles not needed
<e.g. qa: builders' unit tests cover it · decider: no hard-to-reverse decision>

## Acceptance criteria
- [ ]

## Risks and open questions
-
