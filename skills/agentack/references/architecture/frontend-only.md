# Frontend only

One or more frontend applications in this repository; the backend lives elsewhere.

## Signals
Frontend units only, often with a generated client or API types for a remote backend.

## Boundaries
- The remote API is a contract you consume and cannot change from here. Its types come from its
  spec or a generated client.
- Features stay apart; shared UI lives in the shared components folder or design system.

## Rules for builders
- Do not change generated API types or clients by hand; if the remote API does not offer what the
  task needs, stop and report.
- Handle loading, empty and error states, and slow or failing calls, for every remote call.
- Never put secrets in client code; anything in the bundle is public.

## Planning
- Split by feature or screen. Note every assumption about the remote API.

## Review checks
- Hand-written types for a remote API that has a spec; secrets in the bundle.
- Missing error and loading states; accessibility; bundle size of new dependencies.

## Testing
- Component tests for interactions; e2e against a mock of the remote API.

## Contracts and the gate
The remote API spec, when vendored, is regenerated into the client; the typecheck is the gate.

## Sizing
- One screen: Fast. A cross-cutting UI or state change: Standard. Auth flows: Heavy.
