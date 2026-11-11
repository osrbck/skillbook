# Serverless

Functions deployed separately (AWS Lambda, Cloud Functions, Cloudflare Workers, Netlify or
Vercel functions), wired together by the platform: queues, buckets, API gateways.

## Signals
`serverless.yml`, SST, SAM `template.yaml`, `wrangler.toml`, `firebase.json`, functions folders.

## Boundaries
- Each function does one thing and owns its trigger. Shared code is plumbing, not business rules.
- Infrastructure is code: permissions, queues and routes change in the same commit as the
  function that needs them.

## Rules for builders
- Keep handlers small and stateless; everything that must survive goes to the store the project uses.
- Give each function only the permissions it needs; never widen a role to make an error go away.
- Every event handler is idempotent: the platform may deliver an event more than once.
- Mind cold starts and time limits: no heavy work at import time, no unbounded loops.
- Configuration and secrets come from the platform's settings, never from code.

## Planning
- Name every function, trigger and permission the change touches, and the deploy order.

## Review checks
- Over-broad IAM or platform permissions; non-idempotent handlers; missing dead-letter handling.
- Secrets in code or logs; timeouts and memory left at defaults for heavy work.

## Testing
- Unit tests for handlers with events as fixtures; integration tests against the platform's
  local emulator or a test stage where the project has one.

## Contracts and the gate
Event payloads and HTTP routes are the contracts. Gate them like any other contract when they
are written down; otherwise the typecheck and handler tests are the gate.

## Sizing
- One function: Fast. Several functions or a new trigger: Standard. Permissions or data model
  changes: Heavy.
