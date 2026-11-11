# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [2.1.0] - 2026-11-11

Agentack no longer assumes a stack or an architecture: it reads the project and the crew takes
its shape. Scout, architect, contract-guard, qa, reviewer, decider, the two gates and independent
review are unchanged.

### Added
- `init`: scans the repository once (units, languages, frameworks, layers, architecture,
  contracts, migrations, boundary tools, commands) and saves the profile to `.agentack.json`;
  `init --set` records corrections that survive later scans. The first task in a project runs
  it by itself and reports before it starts; nobody is asked to describe the project
- `project`: the saved profile, and what changed in the repository since the scan
- Architecture notes per kind (`references/architecture/`): modular monolith, microservices,
  full stack app, monolith, serverless, frontend only. Each role receives only its section
  (rules for builders, planning, review checks, testing)
- Stack conventions (`references/stacks.md`) for Go, Node/Nest, C#, Java, Kotlin, Python/Django/
  FastAPI, Ruby, PHP, Elixir, Rust, Next.js, Nuxt, SvelteKit, Remix, Angular, React, Vue, Svelte,
  React Native, Flutter, Blazor and Android; a builder gets only its unit's section
- `dispatch --unit` for projects with several backends or frontends; builder names per project
  (`be-java`, `fe-angular`, `fs-next` for both sides of a full stack unit)
- Native Claude Code workers get one prompt file with the role, the project slice and the brief
- `backend-architect` role (S3): for backend changes that must be designed before they are coded
  (schema changes on live data, invariants under concurrency, writes across boundaries) it fixes
  the data model, migration, transactions, idempotency, failure modes and must-have tests in
  `backend.md`; the builder implements it, the reviewer and qa check against it
- `designer` role (S3, placed on the provider rated best at visual work): for a new screen or a
  visual redesign it writes a design note with every state, an optional static mockup and an
  asset list before the frontend builder starts; review can compare screenshots with it
- `image` (experimental): generates a raster image from the design's asset list through Codex or
  Antigravity; the file's real format is checked, and a placeholder is used when nothing can
- Contract rules and default tools for OpenAPI, AsyncAPI, protobuf, GraphQL, JSON Schema and
  shared types (tRPC, ts-rest)

### Changed
- The four stack-specific builders (`be-go`, `be-node`, `fe-next`, `fe-angular`) became two
  project-aware roles, `backend` and `frontend`; with the new `backend-architect` and `designer` the crew
  stays at ten roles. The old names still
  work as aliases
- Priorities are now task, context, tokens: the right context per agent ranks above token cost
- Setup is only about the machine; the project is `init`'s job
- The contract gate follows the project's contract kinds and check command instead of a fixed
  `contracts/` folder; with shared types only, the typecheck is the gate

- Codex: GPT-6 Astra is now the plan-and-review model as well as the decider (high effort for
  decisions, medium for planning and review); Sol builds, and stands in at S3 at high effort
  only on accounts without Astra
- A backend and a frontend in the same folder (`go.mod` next to `package.json`) are two units;
  source code that no unit accounts for is reported by `init`

- The workflow diagram reads left to right, one column per stage, with a badge and icon per role
  and the version in the corner

### Removed
- `references/architecture.md` (now `references/architecture/modular-monolith.md`) and
  `templates/project-guide.md` (the profile replaces it; an existing `CLAUDE.md`/`AGENTS.md` is
  still read)

## [2.0.0] - 2026-11-11

Agentack 2.0 replaces the Claude-only 0.1 under the same name. The workflow and its two gates are
the same; who does the work is no longer tied to one vendor.

### Changed
- The manager is now the **conductor**, and can run in Claude Code, Codex or Antigravity
- Roles are bound to tiers (S1–S4) instead of fixed Claude models
- Role prompts moved from global subagents (`~/.claude/agents/`) into the skill (`roles/`);
  `install.sh` backs up and removes the 0.1 agents
- The conductor may make very small changes itself (Direct path) instead of always delegating
- Workers no longer commit; worktrees are used only when writers overlap, and their changes come
  back uncommitted
- Skill, roles and references are written in English; `routing.md` became `sizing.md`,
  `project-CLAUDE.md` became `project-guide.md`

### Added
- Multi-provider crews: Claude Code, Codex, Antigravity, Cursor and Kiro as workers; one provider
  is enough, two or three add an independent reviewer and fallback
- Tiers S1–S4: roles are bound to tiers, each provider maps tiers to its models
- Conductor on Claude Code, Codex or Antigravity (app, IDE, CLI), with a check that the session runs on a plan-and-review class model
- Right-sizing: measure first, then one of four paths (Direct, Fast, Standard, Heavy); each role
  has an explicit call/skip trigger
- Provider strengths: a dated, sourced 1–5 rating per kind of work keeps each provider on what
  it does well; weak fits are a last resort, specialties (`--skill visual`) go to the best rated,
  and setup shows the scorecard
- Antigravity is routed by its strengths: Argon plans, reviews and reads visuals; build and
  mechanical tiers use 3.1 Pro and 3.8 Flash; Flash-Lite class models are never used
- Briefing styles per model (goal, structured, explicit, rules, peer): `new-brief` creates the
  matching template, workers are told how to treat it, and a looser brief is expanded when
  fallback hands it to a more literal model
- The strongest model is called at three points only and briefed with the open question plus
  evidence gathered beforehand by cheaper roles
- Usage-limit fallback (optional): automatic same-tier switch across providers, mid-task
  continuation, gate roles never downgraded
- Models an account does not have are skipped automatically (listing, `verify`, or a run-time
  refusal): same tier on another provider, else the nearest tier. No questions asked
- Usage measurement for Codex (`app-server`), Kiro (`/usage`), Antigravity (local quota endpoint,
  experimental) and Claude Code (opt-in status line hook)
- Setup tailored to the machine: asks only what is open, verifies every model with a one-word
  prompt, sets aside providers that do not answer and gives an exact fix for each gap
- `agentack.py`: detect, setup, verify, roster, dispatch, wait, result, limits, doctor, report, worktree
- Read-only runs verified with `git status`; worktree changes applied back without commits
- Project allowlist of providers (`.agentack.json`)
- Role prompts and references in English; test suite with fake agent CLIs

## [0.1.0] - 2026-11-06

### Added
- `/agentack` manager skill with task classification, fast/standard/heavy paths, contract and review gates, escalation
- Subagents: scout, architect, contract-guard, be-go, be-node, fe-next, fe-angular, qa, reviewer, decider
- References: modular monolith architecture, contract conventions, routing table
- Templates: feature plan, ADR, task brief, project CLAUDE.md
- `install.sh` with backup, update and `--uninstall`
