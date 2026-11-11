# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
