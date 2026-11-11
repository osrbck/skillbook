# Sizing and routing

The aim is the smallest crew that finishes the work correctly. The order is **task, context,
tokens**: the task is finished correctly, so gates are never traded for speed; every agent gets
the context it needs and no more, so briefs are narrow and the project profile is sliced per
role; and only then the token cost, so no role is called without its trigger.

## 1. Measure before you classify

A wrong size costs more than five lookups. Before tagging the task, find out:

- **Where** it lands: which unit, which module, service or feature, which files (roughly).
- **How wide** it is: one layer or several, one boundary or more (module, service, feature).
- **Whether a contract moves:** a new or changed endpoint, event, RPC, schema or shared type.
- **Whether risk is present:** auth, payments, deletion, migration, security, boundaries.

What counts as a boundary depends on the architecture: read its `## Sizing` notes in
`architecture/<kind>.md`. Budget: about five cheap lookups by the conductor (git status, one or
two greps, the project profile). Still unknown → that is `scout`'s trigger, with a question as narrow as
"where is X handled and what calls it".

## 2. Paths

| Path | All of these hold | Crew | Typical cost |
|---|---|---|---|
| **Direct** | ≤ 2 files · ≈ 40 changed lines or fewer · location known · no contract/schema/auth/security impact · an existing command verifies it | conductor alone | no worker |
| **Fast** | one module · one layer · contract `none` · risk `normal` | 1 builder → reviewer | 2 workers |
| **Standard** | M · or contract `additive` · or > 5 files · or unclear root cause | architect → contract gate → builders → reviewer (+ qa) | 4–6 workers |
| **Heavy** | L · or risk `high` · or contract `breaking` | decider (+ second opinion) → Standard crew + qa | 6+ workers |

Take the lowest path whose conditions all hold. When in doubt between two, measure once more
rather than guessing up or down.

## 3. Triggers

| Trigger | Path | First role |
|---|---|---|
| "Where is X", "how does Y work" | — | answer yourself, or `scout` |
| Typo, copy change, config value, one-line fix with a test | Direct | — |
| Rename, format, lint fix, import cleanup across files | Fast (mechanical) | `scout` in write mode, review by diff |
| Schema change on live data · concurrency-sensitive rules · multi-step writes across boundaries | Standard or Heavy | `architect`, then `backend-architect` |
| New screen or flow unlike any existing one; visual redesign | Standard | `architect`, then `designer` |
| UI change that does not touch the contract | Fast | the frontend unit's builder (`fe-<stack>`) |
| Single-module bug with a clear repro | Fast | the layer's builder |
| New endpoint, or an optional field on an existing one | Standard | `architect` |
| New screen plus new endpoint | Standard | `architect` |
| Change across 2+ modules | Standard | `architect` |
| Refactor touching more than 5 files | Standard | `architect` |
| Intermittent bug, no repro, performance problem | Standard | `architect` (diagnosis), then a builder |
| DB schema change, migration | Heavy | `decider` if data can be lost, else `architect` |
| New module; splitting, merging or moving a boundary | Heavy | `decider` |
| Auth, authorization, payments, personal data, encryption | Heavy | `decider` |
| Breaking contract change | Heavy + user approval | `decider` |
| Technology or library choice (ORM, state, queue) | Heavy | `decider` |

## 4. Role by role: call or skip

- **scout** — call when the location is unknown or the edit is mechanical. Skip when the user
  named the files or your lookups found them.
- **architect** — call when a contract changes, two modules meet, or the cause is unknown. Skip on
  Direct and Fast: a builder with a clear brief does not need a plan document.
- **backend-architect** — call when the backend must be designed before it is coded: a schema
  change on existing data, invariants that must survive concurrency (money, stock, quotas), a
  write across modules or services, a new external integration, a hot query path. Skip when the
  change follows a pattern already in the module. It designs the inside of the backend; the
  architect still owns contracts and the task split, the decider the hard-to-reverse choices.
- **designer** — call for a new screen or flow that has no existing screen to model it on, for a
  broad visual change, or when the user gave a mockup or reference to match. Skip for changes
  inside existing screens: the builder follows what is there. It designs; it never writes
  application code.
- **contract-guard** — only when a contract file changed. If the project has one command that lints,
  checks breaking changes and regenerates, run that command yourself; the gate is the command's
  result, not the agent.
- **builders** — one per unit that actually changes, named after its stack (`be-go`, `fe-angular`,
  `be-csharp` …). A backend-only fix starts no frontend builder. A change on both sides of a full
  stack unit (`fs-next`, `fs-ruby` …) is one builder, not two. In microservices, one builder per
  service that changes.
- **qa** — call when behavior crosses an API or module boundary, when acceptance criteria need
  integration or e2e proof, and always on the Heavy path. Skip when the builders' unit tests cover
  the change.
- **reviewer** — every path except Direct. Scale the scope, not the gate: give it only the diff
  range and the files that matter.
- **decider** — only for hard-to-reverse decisions and escalations. A second opinion only when
  reversal would be expensive.

## 5. Keeping workers cheap without cutting corners

- A brief names the paths a worker may touch and the commands that prove it is done. Vague briefs
  are the main cause of wasted effort.
- Brief each model in its own style (`new-brief` picks the template): latitude for the models
  that plan, every step spelled out for the literal ones, rules and examples for the mechanical
  ones. See "Briefing styles" in `providers.md`.
- Mechanical work goes out in small batches with a spot check after each, so one wrong rule costs
  ten items, not two hundred.
- The strongest model is spent only on decisions: cheaper roles gather its evidence beforehand
  and carry out its decision afterwards.
- Give workers file paths, not pasted file contents.
- Ask for the return format in the role file; do not ask for explanations you will not use.
- Disjoint writers run in the same tree in parallel. Worktrees only for overlapping paths.
- Do not run `qa` and `reviewer` to re-check what the other already proved.

## 6. Re-sizing

Move up a path as soon as one of these appears: a contract has to change, a second module is
involved, a migration is needed, a risk area is touched, or the diff grows past the path's limits.
Tell the user in one line when you do. Never move down after a gate has started, and never drop a
gate because the work "turned out simple".

## 7. Parallelism

- After the contract gate passes, frontend and backend builders run in parallel.
- Never give two builders the same module, service or feature at once.
- `scout` exploration and the contract gate are sequential: the others depend on them.

## 8. Examples

- *"Fix the typo in the invoice empty state."* → Direct. One file, one string, lint proves it.
- *"The cart total rounds wrong for 3 decimal currencies."* (Go API) → Fast: `be-go` with the
  repro as an acceptance test → `reviewer`. No architect, no qa.
- *"Add an invoice list endpoint and a list page."* (modular monolith, Java + Angular) → Standard:
  `architect` (contract + plan) → contract gate → `be-java` ∥ `fe-angular` → `reviewer`. `qa` only
  if the criteria ask for an e2e flow.
- *"Add a favourites page with its own table."* (Next.js full stack) → Standard: `architect`
  (schema + plan) → `fs-next` (one builder, both sides) → `reviewer`.
- *"Orders must reserve stock in the inventory service."* (microservices) → Standard: `architect`
  (new RPC or event, deploy order) → contract gate (`buf breaking`) → `be-csharp` (inventory) ∥
  `be-go` (orders) → `qa` (contract tests between them) → `reviewer`.
- *"Let users transfer credits to each other."* → Standard: `architect` (contract) →
  `backend-architect` (ledger tables, no-negative-balance invariant, row locking, idempotency
  key, must-have tests) → `be-java` → `qa` → `reviewer` with `backend.md`.
- *"Add an onboarding flow with three steps and an illustration per step."* → Standard:
  `architect` → `designer` (design note, mockup, three asset prompts) → images generated by the
  conductor → `fe-angular` → `reviewer` with screenshots and `--skill visual`.
- *"Move payments into their own module and add refunds."* → Heavy: `decider` (boundary and data
  ownership, second opinion) → `architect` → gate → builders → `qa` → `reviewer`.
