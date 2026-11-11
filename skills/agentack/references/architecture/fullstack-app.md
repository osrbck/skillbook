# Full stack app

One framework serves both the pages and the data: Next.js with route handlers or server
actions, Nuxt, SvelteKit, Remix, Rails, Laravel, Django with templates, Phoenix LiveView.

## Signals
A single application unit whose framework renders UI and also has server routes, server
actions, an ORM or migrations.

## Boundaries
- The line that matters is server versus client: secrets, database access and authorization
  stay on the server; the client gets only what it may see.
- Features are folders or routes; one feature does not reach into another's internals.
- Data access goes through one layer (ORM models, a `server/` or `lib/server` folder, services),
  not scattered through components or views.
- The types or schemas shared between server and client (tRPC routers, zod schemas, serializers,
  form requests) are the contract.

## Rules for builders
- One builder covers both sides of a change in this unit; stay within the feature or route
  folders the brief names.
- Database access, secrets and authorization checks live in server-only code. Never import
  server-only modules into client code, and never send fields the user may not see.
- Validate every input on the server (with the shared schema where the project has one), even
  when the client validates too.
- Use the framework's data patterns the project already follows (server components and actions,
  loaders/actions, controllers and form objects); do not introduce a second one.
- Schema changes go through the project's migration tool and stay reversible.

## Planning
- Split by feature or route, not by server/client: a feature is one task for one builder unless
  it is large.
- Authorization rules and data model changes are the decisions that are hard to reverse.

## Review checks
- Server-only code or secrets reachable from the client; missing authorization on server actions,
  route handlers or controllers.
- Over-fetching: whole records sent to the client when a few fields are shown.
- Input trusted because the client validated it; N+1 queries; missing cache invalidation.

## Testing
- Unit tests for server logic, component tests for interactions, e2e for the flows in the
  acceptance criteria.

## Contracts and the gate
Usually there are no contract files: the typechecker is the gate. Run the project's typecheck
and build; where the project has an OpenAPI or GraphQL surface for outside clients, gate it as
in a monolith.

## Sizing
- One feature: Fast. Several features or a shared schema change: Standard.
- Auth, payments, data model changes with migrations: Heavy.
