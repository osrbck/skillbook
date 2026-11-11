# Stack conventions

A builder receives only the one section that matches its unit (framework first, then stack, then
language). These are defaults: the project's own patterns always win. Keep each section short;
it is sent with every builder run.

## go
- `ctx context.Context` is the first parameter of every function that does I/O.
- Errors are values: wrap with `fmt.Errorf("…: %w", err)`, compare with `errors.Is/As`; no `panic`
  for expected failures.
- Small interfaces defined where they are used; the domain package uses the standard library only.
- Table-driven tests; `-race` where the project runs it; `gofmt`/`goimports` clean.
- Generated code (oapi-codegen, sqlc, protoc) is never edited.

## node
- TypeScript `strict`, no `any` (use `unknown` and narrow); public functions declare return types.
- Validate input at the edge with the project's validator (zod, class-validator, typebox).
- Thin controllers/routes; logic in services or use cases; the domain imports no framework.
- One central place maps errors to HTTP responses; async errors are never left unhandled.
- Tests with the project's runner (Vitest/Jest); HTTP tests with supertest or the framework's injector.

## nest
- Modules, providers and controllers as Nest intends; inject through constructors.
- DTOs validated with the project's pipes; no business logic in controllers or guards.
- Feature modules export only what others need.
- Tests with `Test.createTestingModule`, real providers replaced only at the edges.

## csharp
- Nullable reference types on; async all the way down with `CancellationToken` passed through.
- Dependency injection through constructors; options pattern for configuration.
- Minimal APIs or controllers as the project uses them; validation with the project's library
  (FluentValidation, data annotations); errors as ProblemDetails.
- EF Core: migrations through `dotnet ef`, no lazy loading surprises, `AsNoTracking` for reads.
- Tests with the project's framework (xUnit/NUnit); `dotnet format` clean.

## java
- Constructor injection; immutable DTOs (records) at the edges.
- Validation with Bean Validation on request objects; one `@ControllerAdvice` (or equivalent)
  maps errors to responses.
- Transactions at the service layer; no lazy-loading outside a transaction.
- Flyway or Liquibase for schema changes, as the project already uses.
- JUnit 5 tests; Testcontainers for repositories where the project uses it.

## kotlin
- Immutable data classes, null safety without `!!`, coroutines with structured concurrency.
- Follow the framework the unit uses (Spring, Ktor) as in the Java section where it applies.
- Tests with JUnit 5 or Kotest as the project does.

## python
- Type hints on public functions; the project's checker (mypy/pyright) stays clean.
- Validate input with the framework's tools (Pydantic, serializers, forms).
- Keep I/O at the edges; pure functions for logic; no mutable default arguments.
- pytest with fixtures; `ruff` clean where the project uses it.

## django
- Fat models or a services module as the project does; thin views.
- Every model change gets a migration (`makemigrations`); check it is reversible.
- Querysets: `select_related`/`prefetch_related` against N+1; permissions on every view.
- DRF: serializers validate input; viewsets or APIViews as the project uses.

## fastapi
- Pydantic models for every request and response; dependencies for auth and sessions.
- `async` endpoints only with async drivers; never block the event loop.
- Errors through `HTTPException` or the project's handlers; Alembic for migrations.

## ruby
- Rails conventions: skinny controllers, logic in models or service objects as the project does.
- Strong parameters for input; authorization (Pundit, CanCanCan …) on every action.
- Reversible migrations; avoid N+1 with `includes`.
- RSpec or Minitest as the project uses; RuboCop clean.

## php
- Laravel/Symfony conventions: form requests or validators for input, policies or voters for
  authorization, services for logic.
- Eloquent/Doctrine migrations reversible; eager loading against N+1.
- Typed properties and return types; PHPStan and Pint clean where configured.

## elixir
- Contexts are the boundaries; Ecto changesets validate every input.
- Pattern match on `{:ok, _}` / `{:error, _}`; let processes crash only where a supervisor expects it.
- LiveView: keep socket assigns small; ExUnit tests; `mix format` clean.

## rust
- `Result` and `?` for errors with a project error type (thiserror/anyhow as used); no `unwrap`
  in production paths.
- Async with the project's runtime; never block inside async code.
- `cargo clippy -D warnings` and `cargo fmt` clean; tests next to the code.

## next
- App Router: Server Components by default; `"use client"` only for interaction, state or
  browser APIs, as low in the tree as possible.
- Read data on the server; mutate with server actions or the project's client (React Query …);
  state the cache and revalidation strategy.
- Server-only code (database, secrets) never reaches a client component (`server-only`).
- Every data screen has `loading`/`error` states; forms validate on the server too.
- Component tests with Testing Library; e2e with the project's tool.

## nuxt
- Composition API with `<script setup>`; `useFetch`/`useAsyncData` for data; server routes in `server/`.
- Server-only logic and secrets stay in `server/` and runtime config, never in client bundles.
- Pinia for shared state where the project uses it.

## sveltekit
- Load data in `+page.server.ts`/`+layout.server.ts`; mutate with form actions.
- Server-only modules in `$lib/server`; validate every action's input on the server.

## remix
- Loaders read, actions write; validate action input on the server; progressive enhancement
  with `<Form>`. Server-only code in `.server` modules.

## angular
- Standalone components, `signal`/`computed`/`input()`/`output()`, built-in control flow
  (`@if`, `@for` with `track`), `inject()`. No new NgModules; `OnPush` by default.
- Component state in signals; feature state in a service with signals (or the store the project uses).
- RxJS for HTTP and streams, cleaned up with `takeUntilDestroyed` or `toSignal`.
- Lazy feature routes (`loadComponent`/`loadChildren`); functional guards; no imports between features.
- API access only through the generated or shared client; no hand-written URLs for a contracted API.

## react
- Function components and hooks; derive state instead of syncing it with effects.
- Server data through the project's data library (React Query, SWR, RTK Query); no fetching in
  `useEffect` when one is in place.
- Components small and typed; lists keyed by stable ids.
- Testing Library tests that query by role and label.

## vue
- Composition API with `<script setup>` and TypeScript; props and emits typed.
- Pinia for shared state where the project uses it; composables for reusable logic.
- Vitest + Vue Test Utils for components.

## svelte
- Runes (`$state`, `$derived`, `$effect`) in Svelte 5 projects, stores in older ones, as the project does.
- Keep components small; typed props.

## react-native
- Platform differences handled explicitly; no web-only APIs.
- Lists virtualised (`FlatList`/`FlashList`); images sized; navigation as the project sets it up.
- Test with the project's runner and React Native Testing Library.

## flutter
- Widgets small and `const` where possible; state with the project's approach (Riverpod, Bloc,
  Provider), not a new one.
- `flutter analyze` clean; widget tests for interactions.

## blazor
- Components small; parameters typed; services injected; `async` with cancellation.
- Validation with the project's approach (DataAnnotations, FluentValidation).

## android
- Kotlin, Jetpack Compose or views as the project does; ViewModel + state flows.
- Never block the main thread; lifecycle-aware collection.
