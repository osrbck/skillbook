# Contract rules

The contract is the single source of truth. Code is generated from contracts, never the reverse.

## Formats

- **HTTP:** OpenAPI 3.1, one file per module: `contracts/<module>/openapi.yaml`.
- **Events:** AsyncAPI 3: `contracts/<module>/events.asyncapi.yaml`. Payloads are JSON Schema.
- **Shared:** `contracts/shared/components.yaml` (Problem Details error model, cursor pagination,
  Money, timestamp format). Modules reference it with `$ref`; they do not copy it.

## Writing rules

- `operationId` is required and unique: `<module>.<verb><Noun>` (e.g. `billing.createInvoice`).
- Errors are `application/problem+json` (RFC 9457). Every endpoint declares its 4xx/5xx responses.
- Fields are `camelCase`; IDs are strings (UUID/ULID); times are `date-time` (UTC, RFC 3339).
- Every schema lists `required` explicitly; request bodies set `additionalProperties: false`.
- List endpoints use cursor pagination (`limit`, `cursor`, `nextCursor`).
- Every field has a `description`, and an `example` where it helps.
- Event names are past tense (`invoice.paid`, `user.registered`); payloads carry `eventId`,
  `occurredAt`, `version`.

## Versioning

- **Additive** (optional field, new endpoint, new enum value that clients tolerate): allowed
  within the same major version.
- **Breaking** (removing or renaming a field, changing a type, making an optional field required,
  reshaping a response): a new version (`/v2/...` or a new event `version`), with the old one
  marked `deprecated: true` for at least one release. Needs the user's approval.
- Breaking changes are detected against the main branch with `oasdiff breaking`.

## Default toolchain (unless the project guide names others)

| Step | Tool |
|---|---|
| Lint | `@redocly/cli lint` or `spectral lint` |
| Breaking change | `oasdiff breaking <base> <head>` |
| Mock server | `@stoplight/prism-cli mock` |
| Go codegen | `oapi-codegen` (strict server + types), output under `infra/http/gen` |
| Node codegen | `openapi-typescript` (types) + `zod` schemas for validation (`openapi-zod-client` or `orval`) |
| Next.js client | `orval` (fetch + React Query) or `openapi-fetch`, output in `packages/api-client` |
| Angular client | `orval` angular target or `ng-openapi-gen`, output in `packages/api-client/angular` |
| Contract tests | `schemathesis` against the running backend |

## Rules

- Generated code is never edited by hand. It starts with "GENERATED - DO NOT EDIT", and CI re-runs
  codegen and checks for a diff.
- A contract change and the code that uses it ship together, contract first.
- Backend handlers must implement the generated interface, so the compiler or typechecker catches
  a contract mismatch.
