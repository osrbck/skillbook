# Monolith

One backend without explicit module boundaries, often with a separate frontend (client-server),
organized by layers (controllers, services, repositories) or by feature folders.

## Signals
One backend unit, no modules folder, no per-module contracts; optionally one or more frontend units.

## Boundaries
- The layers are the boundaries: the HTTP layer is thin, logic lives in services or use cases,
  data access in repositories or models.
- The API between the backend and its frontends is the contract, written down or not.
- Where feature folders exist, treat them as soft modules and keep them apart.

## Rules for builders
- Follow the existing layering: no queries in controllers or views, no HTTP concerns in services.
- Put new code next to the code it belongs with, in the style already used there.
- Changing a response shape the frontend uses is a contract change: say so and update both sides
  in the same task, or stop and report.
- Schema changes go through the project's migration tool and stay reversible.

## Planning
- Group work by feature. When a change spreads across many layers and files, note whether a
  clearer internal boundary would help, but do not restructure the project unless asked.

## Review checks
- Logic in the wrong layer; duplicated logic that already exists elsewhere.
- Response shapes changed without the frontend side; authorization gaps; N+1 queries.

## Testing
- Unit tests for services, API tests for endpoints, e2e for the critical flows.

## Contracts and the gate
When the API has a spec (OpenAPI, GraphQL schema), gate changes to it as described in
`contracts.md`. Without one, the typecheck and API tests are the gate.

## Sizing
- One endpoint or screen: Fast. A change on both backend and frontend: Standard.
- Auth, payments, schema changes with data migration: Heavy.
