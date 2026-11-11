# Contracts

A contract is whatever one part of the system promises another: an HTTP API, an event, an RPC
service, a GraphQL schema, or the shared types of a full stack app. `init` records which kinds the
project has and where. The rules below apply to all of them; the tables give the default tools
when the project has no command of its own.

## Rules for every kind

- **The contract comes first.** It changes before the code that implements or consumes it, and
  ships in the same change.
- **Generated code is never edited by hand.** Regenerate instead; CI should fail on a diff.
- **Implementations are checked by the compiler:** a server implements the generated interface, a
  client uses the generated types, so a mismatch fails the build rather than production.
- **Additive changes** (a new optional field, a new endpoint or RPC, a new event) are allowed in the
  same version. Consumers tolerate unknown fields and enum values.
- **Breaking changes** (remove or rename, change a type, make something required, reshape a
  response) get a new version and a deprecation period, take the Heavy path, and need the user's
  approval. Detect them against the main branch with the kind's breaking-change tool.
- **Errors** have one documented shape per project (for HTTP, RFC 9457 Problem Details unless the
  project already uses another).

## Default tools per kind

| Kind | Lint | Breaking check | Codegen (examples) |
|---|---|---|---|
| OpenAPI | `redocly lint` · `spectral lint` | `oasdiff breaking <base> <head>` | Go `oapi-codegen` · TS `openapi-typescript`, `orval`, `@hey-api/openapi-ts` · C# NSwag, Kiota · Java/Kotlin `openapi-generator` · Python `datamodel-code-generator` |
| AsyncAPI | `asyncapi validate` | compare with `asyncapi diff` | `asyncapi generate` · Modelina |
| protobuf / gRPC | `buf lint` | `buf breaking --against '.git#branch=main'` | `buf generate` |
| GraphQL | `graphql-schema-linter` or the project's ESLint plugin | `graphql-inspector diff` | `graphql-codegen` · gqlgen · Strawberry · Hot Chocolate |
| JSON Schema | `ajv compile` | review by hand, or a schema-diff tool | `quicktype` · `json-schema-to-typescript` |
| typed (tRPC, ts-rest, shared zod) | the typecheck | the typecheck of every consumer | none: the types are shared |

Contract tests where the project wants proof at run time: `schemathesis` (OpenAPI), Pact
(consumer-driven, between services), the framework's own API tests elsewhere.

## Writing defaults (when the project has no conventions of its own)

**HTTP (OpenAPI 3.1)**
- A unique `operationId` per operation: `<module>.<verb><Noun>` (`billing.createInvoice`).
- Every operation declares its 4xx/5xx responses; errors are `application/problem+json`.
- Fields `camelCase`, IDs as strings (UUID/ULID), times `date-time` in UTC.
- `required` listed explicitly; request bodies set `additionalProperties: false`.
- Lists use cursor pagination (`limit`, `cursor`, `nextCursor`).

**Events (AsyncAPI 3 or the project's schema)**
- Names in the past tense (`invoice.paid`); payloads carry `eventId`, `occurredAt`, `version`.

**protobuf**
- One package per service and version (`orders.v1`); never reuse or renumber a field tag;
  `reserved` for removed fields.

**GraphQL**
- Nullable by default, non-null only when guaranteed; deprecate with `@deprecated(reason:)`
  before removing.

## Where contracts live

The project decides. Common layouts the scan recognises: one folder per module
(`contracts/<module>/`) in a modular monolith; a shared `proto/` or `contracts/` folder, or one
spec per service, in microservices; none at all in a full stack app, where shared types are the
contract.
