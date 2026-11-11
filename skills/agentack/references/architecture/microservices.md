# Microservices

Several deployables that talk over the network. Each service owns its data and its release cycle.

## Signals
Two or more backend units with their own manifests, a `services/` folder, container builds for
several services, Kubernetes or Helm manifests, protobuf/gRPC or per-service API specs.

## Boundaries
- A service is reached only through its published API (HTTP, gRPC, GraphQL) or its events.
  No shared database, no shared tables, no reading another service's storage.
- Shared libraries carry plumbing (logging, tracing, auth middleware, generated clients),
  never business rules.
- Every call across services can fail or be slow: timeouts, retries with backoff, idempotency.
- Contracts are versioned; a consumer must keep working while a producer is deployed first.

## Rules for builders
- Change only the service the brief names. Other services are reached through their generated
  clients or published events; never import their code or touch their data.
- Every outgoing call has a timeout and handles failure; retried operations are idempotent.
- Keep backward compatibility: add fields, do not rename or remove them; tolerate unknown fields
  and enum values from others.
- Configuration comes from the environment the project already uses; no hard-coded hosts.
- Log with the request or trace id the project propagates; never log secrets or personal data.

## Planning
- Name every service the change touches and the deploy order. A change that needs two services
  to deploy at the same moment is a breaking change: redesign it as expand → migrate → contract.
- A new service, a split or a merge of services, or data moving between services is Heavy.
- Prefer events for "something happened", calls for "I need an answer now".

## Review checks
- Calls without timeouts, unbounded retries, non-idempotent retried operations.
- Breaking API or message changes without a version; consumers that would break on deploy order.
- One service reading another's data store, or business logic in a shared library.
- Missing propagation of trace/correlation ids; secrets or personal data in logs.

## Testing
- Unit tests inside each service; consumer-driven contract tests (Pact or the project's
  equivalent) between services; integration tests with the real dependencies in containers.

## Contracts and the gate
Each service publishes its contracts (OpenAPI, protobuf, AsyncAPI, GraphQL schema), often in a
shared `proto/` or `contracts/` folder or a schema registry. The gate runs on every contract
change: lint, breaking-change check against the main branch (`buf breaking`, `oasdiff` …),
regenerate clients, build every service that consumes them.

## Sizing
- One service, no API change: Fast. An additive API or event change: Standard.
- A breaking change, a new service, data moving between services: Heavy.
