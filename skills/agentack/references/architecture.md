# Modular monolith rules

One deployable, hard internal boundaries. Every module should be independent enough to be
extracted into a service later, without paying the network cost today.

## Principles

1. **Module = bounded context.** Split by business capability (`billing`, `catalog`, `identity`),
   not by technical layer (`services/`, `controllers/`).
2. **Narrow public surface.** A module exposes only its `api` package / barrel. Importing another
   module's `domain`, `app` or `infra` is forbidden.
3. **Data ownership.** Each module owns its schema and tables. No direct queries, joins or foreign
   keys into another module's tables; use its public API or an event.
4. **Communication between modules.**
   - Synchronous: an in-process call through the other module's public interface.
   - Asynchronous: domain events with a transactional outbox. Event schemas live in `contracts/`.
   - No cycles. If one appears, turn a call into an event or move the responsibility.
5. **Minimal shared code.** `shared/` holds only generic things (logger, config, error types,
   money/date value objects). Business rules never go there.
6. **Boundaries are enforced by tools.** A rule exists when CI turns red, not when a document says so.

## Default repository layout (when the project guide says nothing else)

```
contracts/
  shared/components.yaml        # Problem (RFC 9457), pagination, common schemas
  <module>/openapi.yaml         # HTTP contract
  <module>/events.asyncapi.yaml # published events
apps/
  api-go/
    cmd/server/main.go          # composition root: wires the modules
    internal/modules/<module>/
      api/                      # public interface (interfaces + DTOs); the only importable part
      app/                      # use cases
      domain/                   # entities, value objects, domain events, rules
      infra/                    # repositories, HTTP handlers (implement the generated stub), outbox
    internal/platform/          # db, logger, config, event bus
  api-node/
    src/modules/<module>/
      index.ts                  # public barrel; nothing else is importable
      application/ domain/ infrastructure/ http/
    src/platform/
  web-next/                     # App Router; feature folders follow module names
  web-angular/                  # standalone; src/app/features/<module>/
packages/
  api-client/                   # types and clients generated from the contracts (never hand-edited)
docs/
  adr/                          # architecture decisions
  features/<slug>/              # plan.md, status.md
```

## Enforcement per stack

| Stack | Boundary check |
|---|---|
| Go | `internal/` visibility + `go-arch-lint` or `depguard` (golangci-lint): no imports of `modules/X/{app,domain,infra}` from another module |
| Node | `dependency-cruiser` or `eslint-plugin-boundaries`; with Nx, `@nx/enforce-module-boundaries` and tags |
| Next.js | no imports of a feature's internals from outside (`no-restricted-imports`); API access only through `packages/api-client` |
| Angular | Nx tags or `eslint-plugin-boundaries`; no imports between features; shared UI in `shared/ui` |

## Layer rules

- `domain` depends on no framework (Go: standard library only; Node: no Nest/Express imports).
- `app` use cases use `domain` and port interfaces; `infra` implements the ports.
- The HTTP layer is thin: validate (with types generated from the contract), call the use case,
  map the response.
- The transaction boundary is the use case; transactions never cross modules.

## When is a new module justified?

When it has its own language, its own data and its own rate of change. "The file got too big" is
not a reason. A new module always takes the Heavy path (ADR).
