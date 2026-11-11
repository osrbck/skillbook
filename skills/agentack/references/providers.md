# Providers, tiers and limits

A **provider** is an agent CLI: a harness that can read files, edit and run commands, plus the
models it offers. Roles are bound to **tiers**; the roster maps each tier to a model on each
selected provider.

## Tiers

| Tier | Purpose | Roles |
|---|---|---|
| **S4** | decisions that are expensive to reverse | decider |
| **S3** | planning, design and review | conductor (your session), architect, backend-architect, designer, reviewer |
| **S2** | building | backend, frontend (as be-/fe-/fs-<stack> for the project), qa |
| **S1** | mechanical work | scout, contract-guard |

## Default models

| Provider | S4 | S3 | S2 | S1 | Can conduct |
|---|---|---|---|---|---|
| `claude` Claude Code | fable | opus | sonnet | haiku | yes |
| `codex` Codex | gpt-6-astra (high) | gpt-6-astra (medium), else gpt-6.1-sol (high) | gpt-6.1-sol (medium) | gpt-6-luna (low) | yes |
| `agy` Antigravity | Gemini 4 Karbon, else Argon | Gemini 4 Argon, else 3.1 Pro | Gemini 3.1 Pro | Gemini 3.8 Flash | yes (app, IDE, CLI) |
| `cursor` Cursor | — name one | — name one | Composer | Auto | no |
| `kiro` Kiro | — name one | — name one | Auto | Auto | planned |

- On Codex, Astra is the plan-and-review model as well as the decider: it is the model on a par
  with Opus. Decisions use high reasoning effort, planning and review medium. Sol builds. On an
  account without Astra (a ChatGPT login, for example) Sol at high effort stands in at S3 and is
  briefed step by step.
- Antigravity is placed where Gemini is strong: Argon plans, reviews and reads anything visual,
  and Karbon decides where an account has it (otherwise Argon does). Its build and mechanical
  tiers sit one model higher than its menu suggests (3.1 Pro and 3.8 Flash), Flash-Lite class
  models are never used, and both tiers are rated a last resort: see `strengths.md`. Slugs are
  read from `agy models` during setup and matched by name.
- Tiers are only half of the routing. Each provider is also rated per kind of work, and a
  provider that is weak at a kind of work is used for it only when nothing better is available.
- Model names change. Override any cell: `setup --model codex:S2=gpt-6.1-sol@low`. A default that
  could not be checked against the CLI's own model list is marked `unverified` in the config.

## Briefing styles

Models differ in how much they want spelled out. Each tier of each provider has a briefing style;
`new-brief` creates the matching template, and every worker is told how to treat its brief.

| Style | The brief contains | Used for |
|---|---|---|
| `goal` | goal, context, constraints, what done looks like | S3 on Claude (Opus), Antigravity (Argon, 3.1 Pro) |
| `structured` | named files, steps, output shape, boundaries | S2 on Claude (Sonnet), Antigravity (3.1 Pro), Cursor Composer |
| `explicit` | every step in order, nothing implicit | GPT-6.1 Sol on Codex (S2, and S3 where it stands in for Astra), any Auto router |
| `rules` | exact rule set with input/output examples, small batches, spot checks | S1 everywhere (Haiku, GPT-6 Luna, Gemini 3.8 Flash) |
| `peer` | the open question plus the evidence | S4 everywhere (Fable, GPT-6 Astra, Gemini 4 Karbon) |

- The Claude and OpenAI rows follow what those models are known to respond to best. The Gemini,
  Cursor and Kiro assignments are by analogy with their tier; change any of them with
  `setup --style <provider>:<tier>=<style>`.
- The decider's brief is always a `peer` brief, also when an S3 model stands in for a missing S4.
- When limit fallback hands a brief to a model that needs more detail than it was written for
  (an Opus `goal` brief landing on Sol), the worker is told to expand it into explicit steps
  first. Briefs are not rewritten.

### When your account does not have a model

Nobody is asked anything; the roster adapts.

- **At setup:** a tier whose model is not in the provider's own listing (`agy models`, Codex
  `model/list`) is dropped for that provider. `verify` then pings every remaining model and drops
  the ones the account refuses, for example
  *"The 'gpt-6-astra' model is not supported when using Codex with a ChatGPT account."*
- A roster that was never verified is verified on the next call, without questions.
- **At run time:** a "model not found / no access" error marks that model as missing for a week
  and the run continues on the next candidate. This works whether limit fallback is on or off.
- **Where the work goes:** the same tier on the next provider. If no selected provider has the
  tier, the nearest tier that exists stands in (the decider runs on S3 when there is no S4
  anywhere, and so on). The roster and the closing report say so.
- A model that is there is always used: nothing is traded down while its tier is available.

`roster` lists what was dropped under `notes`. `setup --reset` restores the defaults and
`setup --model <provider>:<tier>=<model>` names a model yourself.

### Cursor, Kiro and "Auto"

These are harnesses with a small or routed model menu.

- **Auto** modes pick a model you cannot see, so they are meant for S1 and S2 work.
  `reviewer`, `decider` and `architect` prefer any named model, on any tier and any provider.
- Only when nothing but Auto is available (a setup that uses just Cursor or just Kiro) do those
  roles run on Auto, and the roster says so. To avoid that, name a model your plan includes
  (`setup --model cursor:S3=<slug>`) or add a second provider.

## One provider or several

One provider runs the whole workflow: every role maps to that provider's tiers, and the reviewer
is the same vendor in a fresh context.

With two or three:

- **Builders** follow your priority order.
- **Reviewer** starts on a different provider than the builders, and `dispatch --avoid` keeps it
  off the vendor that wrote the code. When that is impossible the run reports `independent: false`.
- **Decider** can get a second opinion from another vendor's S4.
- Per role chains are yours to change: `setup --role reviewer=codex,claude`.

A project can restrict providers with `.agentack.json` at its root:
`{"allowed_providers": ["claude"]}`.

## How each CLI is run

| Provider | Headless command | Read-only runs | Sign-in |
|---|---|---|---|
| claude | `claude -p --model M --output-format json` (prompt on stdin) | edit tools disallowed | existing login or `ANTHROPIC_API_KEY` |
| codex | `codex exec --model M -c model_reasoning_effort=E --sandbox … -o FILE -` | `--sandbox read-only` | existing login or `OPENAI_API_KEY` |
| agy | `agy -p PROMPT --model SLUG --output-format json --dangerously-skip-permissions` | checked after the run | your existing `agy` login |
| cursor | `agent -p PROMPT --model M --output-format json [--force]` | no `--force` | `CURSOR_API_KEY` or login |
| kiro | `kiro-cli chat --v3 --no-interactive --trust-all-tools --model M` (prompt on stdin) | checked after the run | your `kiro-cli login` session, or `KIRO_API_KEY` |

- Every read-only run is also verified: if `git status` differs afterwards, the run carries a
  `violation` with the changed files.
- Codex write runs use the `workspace-write` sandbox: no network by default and no writes to
  `.git`. Workers therefore never commit; add `extra_args` for a provider in the config if your
  tests need more.
- `detect` shows an `auth` hint per provider, read from files, environment variables or a status
  command (`kiro-cli whoami`). It is a hint, not a test.
- `doctor --ping` is the test: it sends a one-word prompt through each selected provider exactly
  the way a worker would be started, and reports the answer or the error. It spends a few tokens
  per provider.

In Claude Code, workers on the `claude` provider run as the host's own subagents (`via: native`)
instead of a child process: they start faster and show up in the UI. Turn this off with
`setup --native off`.

## Images

Agentack has no image model of its own. `image` asks a selected provider's CLI to generate one
raster image and save it; it is **experimental**, because it relies on each CLI's own image tool.

| Provider | How | Notes |
|---|---|---|
| Codex | `codex exec --enable image_generation …` (the built-in `image_gen` tool) | the file is picked up from the run folder or `~/.codex/generated_images/`; older Codex versions need `image_generation` enabled in `~/.codex/config.toml` |
| Antigravity | a normal `agy -p` run that is told to generate and save one image | needs an account with image generation; about a minute per image |
| Claude Code, Cursor, Kiro | no built-in image generation | SVG, CSS and icons are written as code by the frontend builder |

- Providers are tried in your order. A run counts only if it leaves a real PNG, JPEG, WebP or
  GIF behind (the file's bytes are checked, so an SVG or a text file renamed `.png` is rejected).
- The file gets the extension of its real format, and the result says so (`renamed`).
- When nothing can produce the image, the command says so and the conductor continues with a
  placeholder. Nothing is asked.
- Each image is a provider run and counts against that provider's usage.

## Usage limits

`limit_fallback` is set in setup. **Off:** nothing is measured or consulted. **On:** each
dispatch walks the role's chain and takes the first provider that is available.

A provider is unavailable when:

1. its CLI returned a usage-limit error. It stays unavailable until the reset time in the message,
   or for `cooldown_minutes` (60) when none is given;
2. measured usage is at or above `switch_at_percent` (85):

   | Provider | Read from | Windows |
   |---|---|---|
   | Codex | `codex app-server` (`account/rateLimits/read`) | 5-hour, weekly |
   | Claude Code | status line data, if you installed the hook (`hook install`) | 5-hour, weekly |
   | Kiro | `kiro-cli chat --no-interactive "/usage"` | monthly credits |
   | Antigravity | the quota summary of `agy`'s own local server; `agy` is started for a few seconds in a pseudo-terminal, nothing is typed into it (experimental) | 5-hour, weekly (Gemini group) |
   | Cursor | not readable headlessly today: rule 1 only | — |

   Probes run at most every 5 minutes (Codex) or 15 minutes (Kiro, Antigravity). When a probe
   returns nothing, that provider simply falls back to rule 1.

Rules when switching:

- Same tier first, on the next provider in the role's chain.
- Builders, `qa` and `scout` may drop one tier when nothing else is left
  (`builders_may_drop_one_tier`). `reviewer`, `decider` and `architect` never drop: the run ends
  with `limit` / `no_model` and the conductor stops and reports.
- A run interrupted by a limit is continued by the next provider from the same working tree, with
  a note about the earlier attempt.
- Every switch is logged (`report`) and appears in the closing report.

Limits are tracked per provider, not per model. `limits` shows the current state,
`limits --refresh` probes now, `limits --clear <provider>` forgets a recorded limit.

The conductor's own session cannot be switched. If its provider runs out, resume from another
host with `/agentack resume`; progress is in `docs/features/<slug>/status.md`.

## Conductor hosts

| Host | Skill location | Called with | Workers |
|---|---|---|---|
| Claude Code | `~/.claude/skills/agentack` | `/agentack` | Claude workers as native subagents, others as CLI runs |
| Codex | `~/.codex/skills/agentack` | `/agentack` | CLI runs |
| Antigravity (app, IDE, CLI) | `~/.gemini/config/skills/agentack` | `/agentack` | CLI runs; Gemini workers need the `agy` CLI |

The conductor should be on its host's S3 model or above: Opus, GPT-6 Astra, Gemini 4 Argon
(3.1 Pro is accepted).
Antigravity loads skills by their description, so the description says the skill is for explicit
`/agentack` calls only.

## Files

| Path | What |
|---|---|
| `~/.config/agentack/config.json` | providers, models per tier, role chains, limit settings |
| `~/.local/state/agentack/limits.json` | recorded limits and usage |
| `<project>/.agentack/` | briefs, runs, logs, worktrees (git-ignored automatically) |
| `<project>/.agentack.json` | optional project overrides, safe to commit |
