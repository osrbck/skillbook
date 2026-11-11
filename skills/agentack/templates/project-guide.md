# <Project name>

Save this as `CLAUDE.md` (Claude Code) and/or `AGENTS.md` (Codex and others). This project is run
with Agentack 2.0; the values here override the skill's defaults.

## Apps
| App | Path | Stack |
|---|---|---|
| web | apps/web-next | Next.js <version>, App Router |
| admin | apps/web-angular | Angular <version>, standalone + signals |
| api | apps/api-go | Go <version>, chi/echo/stdlib |
| api-node | apps/api-node | Node <version>, NestJS/Fastify |

## Modules
| Module | Owning app | Contract |
|---|---|---|
| identity | api-go | contracts/identity |

## Commands
| Purpose | Command |
|---|---|
| Install | `pnpm install` |
| Lint (all) | `pnpm lint` |
| Typecheck | `pnpm typecheck` |
| Test (all) | `pnpm test` |
| Go test | `cd apps/api-go && go test ./...` |
| Go lint | `cd apps/api-go && golangci-lint run` |
| Contract check (lint + breaking + codegen) | `pnpm contracts:check` |
| Mock API | `pnpm contracts:mock` |
| Boundary check | `pnpm boundaries` |
| E2E | `pnpm e2e` |
| Full verification | `pnpm verify` |
| Local environment | `docker compose up -d` |

## Project rules
- Main branch: `main`. Branch names: `feat/<slug>`, `fix/<slug>`.
- Database: <PostgreSQL>, one schema per module (`identity.*`, `billing.*`).
- Migration tool: <goose / atlas / prisma migrate>.

## Agentack (optional, in `.agentack.json` at the repo root)
```json
{ "allowed_providers": ["claude", "codex"] }
```
