# Agentack 2.0 — agentic stack

**A conductor-led, multi-provider agent workflow for contract-first modular monoliths.**

Call `/agentack` in Claude Code, Codex or Antigravity and your session becomes a *conductor*: it measures the
task, picks the smallest crew that can finish it correctly, and routes each role to the right
model on the agent CLIs you already use: Claude Code, Codex, Antigravity, Cursor, Kiro.

Stacks covered out of the box: **Next.js · Angular · Node.js (TypeScript) · Go**.

> 🇹🇷 Türkçe: [README.tr.md](README.tr.md) · Coming from 0.1? See [Upgrading](#upgrading-from-01).

<p align="center">
  <img src="../../docs/agentack/agentack-flow.svg" alt="Agentack 2.0 crew: the conductor branches into specialist roles, each bound to a tier S1–S4" width="100%">
</p>

## Highlights

- **One provider or several.** Roles are bound to tiers, not models. A single provider can run
  the whole workflow; two or three add an independent reviewer and fallback.
- **Right-sized crews.** Ten roles exist, most tasks need two, a typo fix needs none. The
  conductor measures first and calls a role only when its trigger is present.
- **Independent review.** With more than one provider, review runs on a different vendor than
  the one that wrote the code.
- **Each model is briefed its own way.** Latitude for the models that plan, every step spelled
  out for the literal ones, rules and examples for the mechanical ones. The strongest model gets
  only the open question and the evidence, gathered for it by cheaper roles.
- **It adapts instead of asking.** A model your account does not have is skipped: the role runs
  on the same tier of another provider, or one tier down when nobody has it. A model you do have
  is never traded down.
- **Usage-limit fallback** (optional). When a provider nears or hits its limit, the same tier on
  the next provider takes over, mid-task if needed.
- **Priorities, in order:** finish the work correctly, with the least effort, at the lowest token cost.

## Quick start

```bash
git clone https://github.com/osrbck/skillbook.git ~/skillbook
~/skillbook/install.sh agentack --all   # Claude Code, Codex and Antigravity; or one of: (no flag) --codex --agy
```

Restart your agent, then:

```
/agentack setup
```

Setup looks at what is installed and signed in on *your* machine, asks only what that leaves
open, verifies every model with a one-word prompt, and tells you exactly what to fix if something
is missing. There is no fixed script, because no two machines are set up the same way.

## Commands

| Command | What it does |
|---|---|
| `/agentack <task>` | Size the task, run the crew it needs, report |
| `/agentack setup` | Choose providers and options for this machine; re-run any time |
| `/agentack verify` | Re-test every model and provider; brings back a provider you fixed |
| `/agentack roster` | Who does what: role, tier, model, fit score, fallbacks |
| `/agentack limits` | Usage per provider and anything currently skipped |
| `/agentack doctor` | Health check: CLIs, sign-in, environment, next steps |
| `/agentack resume` | Continue an unfinished task, also from another host |

```
/agentack Add an invoice list endpoint to billing and a list page in the Next.js app
/agentack fix the typo in the invoice empty state
```

In a new project, start with `/agentack Scan this repo and create the project guide`. The guide
(`CLAUDE.md` / `AGENTS.md`) holds your apps, modules and commands and overrides the skill's
defaults. The conductor commits or opens a PR only when you ask.

## Tiers

| Tier | Purpose | Roles | Claude | Codex | Antigravity |
|---|---|---|---|---|---|
| **S4** | hard-to-reverse decisions | decider | Fable | GPT-6 Astra | Gemini 4 Karbon, else Argon |
| **S3** | plan & review | conductor, architect, reviewer | Opus | GPT-6.1 Sol (high) | Gemini 4 Argon, else 3.1 Pro |
| **S2** | build | be-go, be-node, fe-next, fe-angular, qa | Sonnet | GPT-6.1 Sol (medium) | Gemini 3.1 Pro |
| **S1** | mechanical | scout, contract-guard | Haiku | GPT-6 Luna | Gemini 3.8 Flash |

Cursor (Composer, Auto) and Kiro (Auto) cover S1 and S2; review and decision roles prefer a named
model on any provider. These are defaults: what your roster really contains depends on your
accounts and is shown by `/agentack roster`. Details: [`providers.md`](skills/agentack/references/providers.md).

## Strengths

Tiers say how capable a model is; strengths say what a provider is good at. Each provider is
rated 1–5 per kind of work, and the roster keeps it on what it does well.

| Provider | decide | plan | review | visual | backend | frontend | test | mechanical |
|---|---|---|---|---|---|---|---|---|
| Claude Code | 5 | 5 | 5 | 4 | 5 | 4 | 5 | 4 |
| Codex | 5 | 4 | 4 | 4 | 4 | 4 | 4 | 3 |
| Antigravity | 4 | 4 | 4 | 5 | 2 | 2 | 2 | 2 |

Your provider order decides, with two corrections: a provider rated weak (2 or lower) at a kind
of work does it only as a last resort, and a specialty such as visual review goes to the best
rated. So Gemini plans, reviews and checks UI, but writes code only when nothing else is
available. Setup shows this scorecard before you choose; `--rate` changes any number. Ratings are
dated and sourced in [`strengths.md`](skills/agentack/references/strengths.md).

## Briefing styles

| Models | The brief contains |
|---|---|
| Opus and peers (S3) | goal, context, constraints, what done looks like |
| Sonnet and peers (S2) | named files, steps, output shape, boundaries |
| GPT-6.1 Sol, Auto routers | every step in order, nothing left implicit |
| Fable, GPT-6 Astra, Gemini 4 Karbon (S4) | the open question plus the evidence, as to a peer |
| Haiku, GPT-6 Luna, Gemini 3.8 Flash (S1) | exact rules with input/output examples, small batches, spot checks |

The conductor gets the right template for whichever model a role runs on. The strongest model is
called at three points only: a hard-to-reverse decision, a second opinion on it, and an
escalation after two failed attempts.

## Paths

| Path | When | Crew |
|---|---|---|
| **Direct** | ≤ 2 files, location known, no contract/schema/auth impact, a command can verify it | the conductor alone |
| **Fast** | one module, one layer, no contract change | one builder → reviewer |
| **Standard** | a contract changes, 2 modules, > 5 files, or unclear cause | architect → contract gate → builders → reviewer (+ qa when needed) |
| **Heavy** | new module, schema change, auth/payments, breaking contract | decider (+ second opinion) → Standard crew + qa |

Two gates never move: **no build before the contract check passes**, and **nothing is done before
an independent review** (every path except Direct). When a task turns out wider than measured,
the conductor moves it up a path. Details: [`sizing.md`](skills/agentack/references/sizing.md).

## Models and limits

**Missing models** are handled automatically, always: a model that is not on your account
(not listed, refused by `verify`, or refused during a run) is skipped and remembered.

**Usage limits** are handled when fallback is on:

- A provider is skipped after it reports a limit (until the reset time) or when measured usage
  passes your threshold (default 85%). Usage is measured for Codex, Kiro, Antigravity
  (experimental) and, with the optional status line hook, Claude Code.
- Same tier first. Builders may drop one tier as a last resort. Reviewer, decider and architect
  are never downgraded for a limit: the work stops and tells you when it resets.
- A run cut off by a limit is continued by the next provider from the same working tree.
- Nothing is asked during work. Every switch appears in the closing report.

## How it runs

```
/agentack → conductor (your Claude Code, Codex or Antigravity session)
               │  measure → size → path → gates
               ▼
            agentack.py dispatch ── role → tier → provider + model
               ├─ claude -p · codex exec · agy -p · agent -p · kiro-cli chat --no-interactive
               └─ in Claude Code, Claude workers run as native subagents
```

- Workers run headless in your repository with a narrow brief, and never commit.
- Read-only roles are enforced by the CLI where possible and verified with `git status` after every run.
- Runs, logs and briefs live in `<project>/.agentack/` (git-ignored automatically).
- The helper is plain Python with no dependencies. It talks only to the agent CLIs on your machine.
- A project can restrict providers by committing `.agentack.json`: `{"allowed_providers": ["claude"]}`.

Agentack assumes, and helps enforce, a **contract-first modular monolith**: modules own their data
and expose a narrow public surface; contracts (OpenAPI 3.1, AsyncAPI 3, RFC 9457 errors) live in
`contracts/<module>/` and code is generated from them. See
[`architecture.md`](skills/agentack/references/architecture.md) and
[`contracts.md`](skills/agentack/references/contracts.md).

## Requirements

- **Conductor:** Claude Code, Codex or Antigravity (app, IDE or CLI), on a plan-and-review class
  model (Opus, GPT-6.1 Sol, Gemini 4 Argon or above). On a smaller model Agentack warns and asks
  before continuing. Kiro is planned as a host; today it works as a provider.
- **Providers:** at least one of Claude Code, Codex, Antigravity (`agy`), Cursor CLI, Kiro CLI.
- Python 3.8+ and git, on macOS, Linux or WSL. Your project in a git repository.

Update with `cd ~/skillbook && git pull && ./install.sh agentack --all`; remove with `./install.sh agentack --uninstall`.

### Upgrading from 0.1

2.0 replaces the Claude-only 0.1 under the same name and command. `install.sh agentack` installs the new
skill over the old one and moves the ten global subagents that 0.1 put in `~/.claude/agents/`
into `~/.claude/backups/` (2.0 keeps its role prompts inside the skill, so nothing global is
needed). Then run `/agentack setup` once. Project guides written for 0.1 keep working.

## Status

| Provider | State |
|---|---|
| Claude Code | tested against the real CLI |
| Codex, Antigravity, Cursor, Kiro | written from each CLI's documentation and covered by simulated tests |

Model names and CLI flags change often. `/agentack verify` proves what works on your machine,
and reports of what you see there are very welcome.

## Repository

Agentack lives in [skillbook](../../README.md):

```
skillbook/
├── install.sh                # ./install.sh agentack [--codex|--agy|--all]
├── skills/agentack/
│   ├── SKILL.md              # the conductor
│   ├── roles/                # 10 provider-neutral role prompts
│   ├── references/           # sizing, providers, architecture, contracts
│   ├── templates/            # plan, ADR, task brief, project guide
│   ├── scripts/              # agentack.py + agentack_core
│   └── install.hook.sh       # 0.1 / preview migration, CLI detection
├── docs/agentack/            # diagrams
└── tests/agentack/           # end-to-end tests against fake agent CLIs
```

```bash
python3 -m unittest discover -s tests/agentack -v   # from the skillbook root
```

Contributions are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under [MIT](../../LICENSE).

Agentack is a community project and is not affiliated with Anthropic, OpenAI, Google, Cursor or AWS.
