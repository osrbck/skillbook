# Modular monolith

One deployable, hard internal boundaries. Every module could be extracted into a service later,
without paying the network cost today.

## Signals
A backend with a modules folder (`internal/modules`, `src/modules`, `Modules/` …), one contract
folder per module, boundary tooling (Spring Modulith, ArchUnit, dependency-cruiser, Nx tags,
go-arch-lint, NetArchTest, import-linter, packwerk, deptrac).

## Boundaries
- **Module = bounded context**, split by business capability (`billing`, `catalog`), not by layer.
- **Narrow public surface:** a module exposes one public package / barrel / API project. Another
  module's internals (domain, application, infrastructure) are never imported.
- **Data ownership:** each module owns its schema and tables. No joins, queries or foreign keys
  into another module's tables.
- **Between modules:** an in-process call through the public interface, or a domain event through
  a transactional outbox. No cycles.
- **Shared code** holds only generic things (logging, config, error types, money/date values).
  Business rules never go there.

## Rules for builders
- Stay inside the module the brief names. Another module is reached only through its public
  interface (its `api` package, `index` barrel or contracts project), never its internals.
- Query only this module's own tables. Need another module's data? Call its public interface or
  react to its event; never join across modules.
- Keep the domain free of framework imports; use cases depend on interfaces that the
  infrastructure layer implements. The transaction boundary is the use case and never spans modules.
- Events another module consumes are written to the outbox in the same transaction.
- Run the project's boundary check when it has one; a boundary violation is a failed build.

## Planning
- Start from the modules involved and their public interfaces. A change that needs a new
  dependency between modules says which direction it goes and why there is no cycle.
- A new module needs its own language, data and rate of change; "the file got too big" is not a
  reason. New modules and moved boundaries take the Heavy path with an ADR.
- Contracts are per module; an event another module consumes is a contract too.

## Review checks
- Imports into another module's internals; queries or foreign keys on another module's tables.
- Business rules that drifted into shared code; new cycles between modules.
- Events published outside the transaction (no outbox) where the project uses one.
- Run the boundary checker and report its result.

## Testing
- Unit tests per module; integration tests for calls and events across modules against a real
  database; contract tests for the HTTP surface.

## Contracts and the gate
Contracts live per module (`contracts/<module>/…` or next to the module). Code is generated from
them. The contract gate runs when a contract file changed: lint, breaking-change check, codegen,
build of the consumers.

## Sizing
- One module, one layer: Fast. Two modules or a public interface change: Standard.
- New module, moved boundary, data moving between modules: Heavy.
