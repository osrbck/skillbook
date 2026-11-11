# Backend design: <title>

**Slug:** <slug> · **Unit:** <backend unit> · **Modules / services:** <list>

## Data model
| Table / collection | Column | Type | Constraints | Owner |
|---|---|---|---|---|

Indexes: <index → the query it serves>

## Migration
| # | Step | Reversible | Lock / downtime risk | Old and new code together? |
|---|---|---|---|---|

## Invariants
| Rule that must always hold | Enforced by |
|---|---|

## Transactions and consistency
- <operation>: transaction covers <…>; outside it: <…> (how it converges)

## Concurrency and idempotency
| Situation (two at once, retry, duplicate event) | What happens | Mechanism |
|---|---|---|

## Failure modes
| Step / external call | Fails or times out | Result for the caller | Recovery |
|---|---|---|---|

## Authorization
| Operation | Check | Where |
|---|---|---|

## Queries
| Access path | Expected size | Index / approach |
|---|---|---|

## Must-have tests
- [ ]

## Open questions
-
