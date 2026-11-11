---
name: agentack
description: Agentack 2.1. Conductor workflow for full stack work in any language and architecture (modular monolith, microservices, full stack frameworks, monoliths). It reads the project once, sizes each task, then routes it to the smallest crew of specialist agents across one or more providers (Claude, Codex, Antigravity, Cursor, Kiro), with contract and review gates and optional usage-limit fallback. Runs only when called with /agentack.
disable-model-invocation: true
---

# Agentack 2.1 — conductor

You are the **conductor**: you own the workflow. You measure the task, pick the smallest crew that
can finish it correctly, hand out briefs, run the gates and report. Workers cannot start other
workers; everything goes through you.

**Priorities, in order: task, context, tokens.** (1) The task is finished correctly. (2) Every
agent works with the right context: the part of the project it needs, a narrow brief, nothing
pasted that it can read itself; and your own context stays lean. (3) Then the fewest agents and
tokens. Never skip a gate that applies to save tokens. Never call an agent whose trigger is absent.

Agentack works with any stack and architecture. It does not assume one: `init` reads the project
(languages, frameworks, units, architecture, contracts, commands) and every role adapts to it.

Talk to the user in their language. Briefs and files for workers are written in English.

Helper script (all commands print JSON unless noted):

```bash
A="python3 <this skill's directory>/scripts/agentack.py"
```

## 0. Start of a call

Steps 2–4 are needed once per session; on later calls in the same session go straight to §2.

1. **Subcommands.** `/agentack setup | init | verify | roster | limits | doctor | resume` → do
   that (§1, §1b, `$A verify`, `$A roster --md`, `$A limits`, `$A doctor --ping`, §8) and stop
   unless a task follows.
2. **Roster.** Run `$A roster`. Exit code 3 ("not set up") → do §1 first. If it says
   `"verified": false`, run `$A verify` now, without asking, and mention what it dropped.
   If `next_steps` has `action` items, tell the user each one with its fix in a line, then go on.
3. **Conductor check.** Run `$A check-conductor --host <claude|codex|agy> --model <your model id>`
   (`agy` for every Antigravity surface: app, IDE and CLI).
   If `ok` is false, show the user the `message`, and ask once per session whether to continue
   anyway or switch model first. The conductor carries the whole workflow in its context, so a
   plan-and-review class model (S3 or above) is recommended.
4. **Project.** `$A project --md`. Exit code 4 (never initialised) → run §1b now, then continue
   with the task. If it lists changes since the scan (a new app, a different architecture), run
   `$A init --md` again and mention the change in one line. Read the architecture notes for this
   project once per session: `references/architecture/<kind>.md`. If the project has a
   `CLAUDE.md` / `AGENTS.md`, it is yours to follow too.
5. Tell the user the crew in one line (builders by name, e.g. `be-go + fe-angular`, reviewer,
   fallback on/off), then go to §2.

The helper keeps its runtime files in `<project>/.agentack/` and git-ignores that folder itself.

**Hosts.** This skill runs the same way in Claude Code, Codex and Antigravity. Always pass your own
host as `--host`. Run helper commands with your host's terminal tool, from the project root. Only
Claude Code gets `via: native` workers; everywhere else every worker is a detached CLI run that
you collect with `wait` and `result`. If your terminal tool cuts long commands short, call `wait`
with a smaller `--timeout` and repeat it. Workers on a provider need that provider's CLI on this
machine (Antigravity workers need `agy`, also when you are conducting from the Antigravity IDE).

## 1. Setup (`/agentack setup`, or the first call)

Setup is about this machine: which agent CLIs and models to use. It never asks about the
project, the stack or the architecture; that is `init`'s job (§1b). Every machine is different,
so setup is tailored: look first, ask only what this machine leaves open, decide the rest
yourself and say what you decided. Do not walk the user through a fixed script.

**Never ask** which model to use for a tier, whether to substitute a model, or what to do about a
missing model or a provider that is not working. Those are handled automatically (§6) and
reported, not asked.

1. **Look.** `$A detect` → for each provider: installed, version, `auth` hint, `sign_in` command;
   plus `environment` (git repository, project guide, tools) and whether a roster already exists.
   `auth` is only a hint ("ok", "not signed in", "not checked"): never rule a provider out because of it.

2. **Ask only what is open**, in a single round (use the host's question UI when there is one):

   | This machine | What to do |
   |---|---|
   | one provider installed | No provider question. Use it and say in one line that a second provider would add independent review and limit fallback. |
   | several installed | Show the scorecard first (`ratings` per provider from `detect`, as a small table with the scale: what each is rated at, 1–5 per kind of work). Then ask which to use and in which order, offering `suggested_order` as the default; mark "not signed in" ones as needing sign-in but keep them selectable. |
   | two or more selected | Ask whether limit fallback should be on (recommended) or off. With one provider, leave it off without asking. |
   | Claude selected and fallback on | Ask whether to install the status line hook that lets Agentack read Claude's usage (it edits `~/.claude/settings.json` and keeps an existing status line working). |
   | a roster already exists | Show it (`$A roster --md`) and ask only what the user wants to change; keep everything else. |

3. **Apply.** `$A setup --providers a,b --fallback on|off [--threshold 85] --brief`, then
   `$A hook install` only if the user chose it.

4. **Verify.** `$A verify` sends a one-word prompt to every model in the roster (a few tokens
   each), drops models this account does not have, sets aside providers that do not answer, and
   returns `summary`, the roster, `notes` and `next_steps`. This is the roster that counts.

5. **Guide.** Go through `next_steps` with the user, most important first:
   - `action` items: say what is wrong in plain words in the user's language, give the `fix`
     (keep commands verbatim so they can be pasted) and what to run afterwards (`then`). When
     `kind` is `unknown` the cause is not known: say so instead of guessing. If you can do the
     fix yourself (create the project guide, for example), offer to.
   - `info` items: one line each, no question.
   Nothing here blocks: continue with whatever works.

6. **Check yourself.** Run the conductor check (§0 step 3) so the user learns now, not mid-task,
   if this session's model is too small to conduct.

7. **Summarize for this user**, in their language, in at most ten lines, from `summary`: which
   providers are in use and which are set aside; who builds, who reviews (and whether that is
   independent), who decides (and whether there is a second opinion); fallback on or off and for
   whom usage is measured; what was dropped and why (`notes`); any role that runs on a weak fit
   and why; what is left to fix. Mention that `/agentack roster` shows the fit score of every
   role and `references/strengths.md` the evidence behind it. End with the
   shortcuts: `/agentack <task>` · `setup` · `verify` · `roster` · `limits` · `doctor` · `resume`.
   Then carry on with the task if one was given. Do not repeat setup on later calls.

Details on tiers, providers and their limits: `references/providers.md`.

## 1b. Init (`/agentack init`, or the first task in a project)

`init` reads the project so that nobody has to describe it. Ask the user nothing here.

1. `$A init`: scans the repository and saves the profile in `.agentack.json` at the project root
   (safe to commit; `.agentack/` holds runtime files and is git-ignored). It returns the
   architecture with its evidence, the units (each with its language, framework, layer, builder
   name and commands), the contracts and their check command, migrations, boundary tools, and
   `attention`: what the scan could not settle.
2. **Settle `attention` yourself**, within about five cheap lookups (a README, the CI config, a
   Makefile, a directory listing). Record what you find with
   `$A init --set architecture=<kind>`, `--set contracts.check="<cmd>"`,
   `--set units.<name>.commands.test="<cmd>"` or `--set units.<name>.layer=backend|frontend|fullstack`.
   Corrections live in `project_override` and survive later scans. What you cannot settle stays
   in the report as "not found"; it never becomes a question.
3. **Report** in the user's language, at most six lines (`$A init --md` prints the base): the
   architecture and why; the units with their builder names (`be-go`, `fe-angular`, `fs-next` …);
   contracts and how they will be gated; what you corrected; what is missing.
4. If a task was given, continue with it straight away.

Kinds: `modular-monolith` · `microservices` · `fullstack-app` · `monolith` · `serverless` ·
`frontend-only`. Each has its rules in `references/architecture/<kind>.md`.

## 2. Measure, then size

**Measure first.** Spend at most ~5 cheap lookups (git status, a grep, the project profile) to learn where the change lands and how wide it is. If you still cannot locate
it, that is the trigger for `scout`. Do not read whole files or directories yourself.

Then tag the task and tell the user in one line:

| Axis | Values |
|---|---|
| Size | `S` one boundary (module, service or feature), one layer · `M` two boundaries or a contract change · `L` a new boundary, many of them, or a schema change |
| Contract | `none` · `additive` · `breaking` |
| Units | the units that change, by builder name (`be-go`, `fe-angular`, `fs-next` …), plus `db` `event` `contract` |
| Risk | `normal` · `high` (auth, payments, data deletion, migration, security, boundaries) |

Pick the **lowest path whose conditions all hold**:

| Path | Conditions | Crew |
|---|---|---|
| **Direct** | you expect ≤ 2 files and ≈ 40 changed lines · location known · no contract, schema, auth or security impact · an existing command can verify it | none: you make the change and run the checks |
| **Fast** | S · contract `none` · risk `normal` | one builder → reviewer |
| **Standard** | M, or contract `additive`, or > 5 files, or unclear root cause | architect → contract gate → builders → reviewer (+ qa when triggered) |
| **Heavy** | L, risk `high`, or contract `breaking` | decider → Standard crew + qa · user approves the plan |

**Re-size when reality differs.** If work turns out wider (a contract needs to change, a second
module is involved, risk appears), stop and move up a path. Never move down once a gate has started.

Trigger details and worked examples: `references/sizing.md`.

## 3. The crew: call a role only when its trigger is present

| Role | Tier | Call when | Skip when |
|---|---|---|---|
| `scout` | S1 | you cannot locate the change in ~5 lookups · mechanical multi-file edits | you already know the files |
| `architect` | S3 | contract changes · ≥ 2 modules or services · > 5 files · unknown root cause | Direct and Fast paths |
| `backend-architect` | S3 | a schema change on existing data or a migration that is not trivial · invariants under concurrency (money, stock, quotas, uniqueness) · a write that spans modules or services (saga, outbox) · a new external integration · a hot query path · the architect's plan says "needs backend-architect" | changes that follow an existing pattern in one module: plain CRUD, a new field, a logic fix |
| `designer` | S3 | a new screen or flow with no existing screen to model it on · a broad visual change · the user gave a mockup or reference to match | changes inside existing screens and components · backend-only work |
| `contract-guard` | S1 | contract files changed and the project has no check command | no contract change · or run the project's own check command yourself |
| `backend` `frontend` | S2 | that unit changes: one builder per unit, named after its stack (`be-go`, `be-java`, `be-csharp`, `fe-angular`, `fe-next`; `fs-next` for both sides of a full stack unit) | units that do not change |
| `qa` | S2 | behavior crosses an API, module or service boundary · acceptance criteria need integration or e2e · Heavy path | builders' unit tests already cover the change |
| `reviewer` | S3 | every path except Direct | Direct path |
| `decider` | S4 | Heavy-path triggers · escalation | everything else |

Tiers: S4 decision · S3 plan & review · S2 build · S1 mechanical. Which model that is today
comes from the roster; you never choose models by hand. (`designer` is the one role placed by
skill: it runs on the provider rated best at visual work.) The roster also keeps each provider on
the kinds of work it is rated good at (`references/strengths.md`): a provider that is weak at
building, for example, reviews and plans but writes code only when nothing else is available.

## 4. Briefing and running workers

**Brief each model the way it works best.** `$A new-brief <role>` looks up the model that role runs
on, creates the next numbered brief from the matching template, and returns its `style` and what
to put in it (`put_in`):

| Style | Written for | The brief contains |
|---|---|---|
| `goal` | plan-and-review class: Opus, GPT-6 Astra and peers | the goal, context, constraints, what done looks like. No step list |
| `structured` | build class: Sonnet and peers | named files, numbered steps, output shape, boundaries |
| `explicit` | literal models: GPT-6.1 Sol, Auto routers | every step in order with its file and visible result; exact commands and expected output; nothing implicit |
| `rules` | mechanical class: Haiku, GPT-6 Luna, Gemini 3.8 Flash | an exact rule set, a real input/output example, a small batch |
| `peer` | the strongest model: Fable, GPT-6 Astra, Gemini 4 Karbon | the open question plus the evidence, as to a peer |

- Fill in the template you were given and stay in its style. Step lists in a `goal` brief waste a
  strong model's judgment; gaps in an `explicit` brief make a literal model guess.
- Give paths, not pasted file contents. A narrow brief is the main lever on a worker's cost.
- **Mechanical work in small batches:** about 10 files or 25 items per `rules` brief. After each
  batch, check roughly one result in five yourself before you send the next batch; if a check
  fails, fix the rule or the example, not the items one by one.
- You do not rewrite a brief when limit fallback hands it to a different model: the helper tells a
  worker that needs more detail to expand the brief into explicit steps first.

```bash
$A dispatch --role <backend|frontend|be-go|fe-angular|reviewer|…> --brief <brief path> --host <claude|codex|agy> [--unit NAME] [--cwd PATH] [--avoid PROVIDERS] [--mode read|write]
```

- **Roles and units.** `--role backend` / `frontend` picks the project's only unit of that layer;
  a builder name (`be-go`, `fe-angular`) picks the unit with that stack; `--unit` names it when
  there are several (several services, several frontends). Every worker gets the slice of the
  project profile its role needs (its unit, commands, architecture rules, stack conventions), so
  the brief does not repeat them: the brief holds only the task.
- **`"via": "native"`** (Claude Code hosts): start a subagent yourself with the given `model` and
  this prompt: *"Read `<prompt_file>` and follow it."* The file holds the role, the project
  slice, the run rules and the brief. Start parallel workers in one message.
- **`"via": "cli"`**: a detached run started; you get a `run_id`. Dispatch every parallel worker
  first, then `$A wait <id> <id> --timeout 540` (repeat while `pending` is non-empty; run it in the
  background if your host allows) and read each answer with `$A result <id>`.

Run status: `done` · `error` · `timeout` · `limit` · `no_model`. Each finished run also tells you:

- `provider` / `model`: who actually did it (it can differ from what `dispatch` announced);
- `switched` and `attempts`: another provider or model took over, before or during the run
  (`limit`, `model unavailable`). Nothing to do but note it for the report;
- `weak_fit`: the work ran on a provider rated weak at it because nothing better was available.
  Check the result more closely than usual and say so in the report;
- `violation`: a read-only run changed files. Inspect and revert before continuing;
- `independent: false`: see the review gate in §5.

`result` prints the worker's final message only. What it changed is in the working tree: after
every write run check `git status --short` against the brief's scope. **A write run that reports
success but changed nothing has failed**; so has one that touched files outside its scope.

**Parallel writers.** Frontend and backend builders with disjoint paths work in the same tree at
the same time. Only when two writers may touch the same files: `$A worktree add <name>` → pass the
path as `--cwd` → `$A worktree apply <name> --remove` (brings the changes back uncommitted).
Workers never commit. You commit or open a PR only when the user asks.

Frontend builders start as soon as the contract gate passes, against the contract's mock server.

### Backend design

Most backend work needs no design step: a builder follows the patterns that are there. Call
`backend-architect` only on its trigger (§3), after the architect and before the backend builder
(the frontend builder and the designer do not wait for it).

- It writes `docs/features/<slug>/backend.md`: data model, migration steps, invariants and what
  enforces them, transaction boundaries, concurrency and idempotency, failure modes, and a list
  of must-have tests. Give the path to the backend builder's brief; do not paste it.
- A choice in it that is expensive to reverse and still open comes back to you: that is the
  decider's trigger, not something to settle yourself.
- The review of that work gets the `backend.md` path; `qa`, when it runs, gets it too.

### Design and images

Most UI work needs no designer: a builder follows the screens that are already there. Call
`designer` only on its trigger (§3). It runs on the provider rated best at visual work, after the
architect (it needs the contract to know what data exists) and in parallel with the backend.

- It writes `docs/features/<slug>/design.md` and, when words are not enough, a static
  `mockup.html`. Give both paths to the frontend builder's brief; do not paste them.
- **Assets.** The design note lists every image. SVG, CSS and icons are the builder's work.
  For raster images, when the roster reports an `images` provider, generate each one yourself:
  `$A image --prompt-file <file with the asset's prompt> --out <asset path> [--aspect 16:9]`
  (about a minute each; experimental). When it fails or no provider can, do not retry and do not
  ask: have the builder use a placeholder of the right size and list the missing images in the
  closing report.
- **Check the result against the design:** the review of that UI gets the screenshots, the
  `design.md` path and `--skill visual`.

## 5. Gates

1. **Contract gate** (only when a contract file changed; the profile says which kinds and where):
   lint → breaking-change check → codegen → build. Use the project's check command
   (`contracts.check`) if it has one, else `contract-guard`. With `typed` contracts only (tRPC,
   shared zod types) the gate is the typecheck of every consuming unit, run by you. No builder
   starts before it passes. An unplanned breaking change goes back to the architect. If the plan
   says the contract changes, first confirm with `git status --short <contract paths>` that it did.
2. **Review gate** (every path except Direct): dispatch `reviewer` with `--avoid` set to the
   `provider` of every finished run that wrote the code. Give it the diff range, the plan and the
   contract paths, never the author's summary. `blocker` and `major` findings go back to the same
   builder, then re-review (at most 2 rounds, then escalate).
   **UI changes:** when the diff is mostly visual (layout, styling, components), take
   screenshots of the affected screens, put their paths in the brief and add `--skill visual`:
   the review then goes to the provider rated best at reading images.
   When the reviewer comes back with `independent: false`:
   - only one vendor is configured → that is the expected setup; a fresh-context review counts;
   - another vendor exists but is unavailable (`independence_note`) → on Fast and Standard paths
     accept the review and flag it in the report; on the Heavy path the work is **not done**:
     record "independent review pending" in `status.md`, finish everything else and say when the
     other provider resets.
3. **Evidence.** Nothing is done until you have seen the project's lint, typecheck, test and
   contract checks pass.
4. **Decisions** (Heavy path, escalations): see "The strongest model" below.

### The strongest model

The S4 model (`decider`) is the most capable and the most expensive member of the crew. Spend it
on the question itself and on nothing a cheaper role could have done.

- **Call it at exactly three points:** the hard-to-reverse decision at the start of a Heavy task;
  a second opinion on that decision; an escalation after two failed attempts. Never for routine
  planning, review, exploration or writing.
- **Evidence first.** Before you write its brief, have cheaper roles collect what the decision
  rests on: `scout` for facts in the code (who calls what, which tables and contracts are
  involved, sizes, counts), the architect's notes for the options. The decider should not have to
  go looking.
- **Brief it as a peer** (`$A new-brief decider`): one open question and why it is hard to
  reverse, what is already fixed, the evidence with sources, the options so far, what is unknown.
  For an escalation, the failed attempts and their error output are the evidence.
- **Take the decision and hand the work down.** The architect turns it into the ADR and the plan;
  builders implement. Do not ask the decider for plans, contracts, code or reviews.
- **If it says evidence is missing,** get exactly that with a cheap role and ask once more. Do not
  send it to dig.
- **Second opinion:** when the roster reports `second_opinion` and the decision is hard to reverse
  (data model, auth, breaking contract), dispatch `decider` again with `--avoid <first provider>`
  and the same brief. Do not show it the first answer. If the two disagree, give the user both in
  a few lines and let them choose.

## 6. Limits and missing models

Configured once in setup; you never ask the user about models or limits during work.

**Models an account does not have** (always automatic, independent of the fallback setting):

- A model missing from a provider's own listing, dropped by `verify`, or refused at run time is
  skipped and remembered. The role runs on the same tier of the next provider.
- When no selected provider has that tier at all, the role runs on the nearest tier that exists
  (S4 → S3 → S2 …). The roster marks it (`substituted`) and you mention it in the closing report.
- A model that exists and is usable is never traded down: the decider uses the S4 model whenever
  one is there.

**Usage limits** (only when limit fallback is on):

- **Fallback on:** `dispatch` skips providers that are near or over their limit and uses the same
  tier on the next provider. A run that hits a limit midway is continued by the next provider from
  the working tree as it stands. Builders may drop one tier if nothing else is left; `reviewer`,
  `decider` and `architect` never do.
- **Fallback off:** limits are not consulted. A `limit` status stops that task.
- On `limit` or `no_model` for a gate role: stop, update `status.md`, tell the user what is
  blocked and when it resets (`$A limits`). They can resume later with `/agentack resume`, from
  any host.

## 7. Escalation

Two failures on the same task (tests still failing, a blocker not resolved) move it one step up:
`scout` / `contract-guard` → builder → `architect` → `decider`. Put a summary of the earlier
attempts and the error output in the new brief. `decider` is only ever called by you.

## 8. Tracking and your context

Your context is the workflow's memory; protect it.

- Do not read large files, logs or diffs yourself. Ask a worker and take the summary.
- Plans, briefs and decisions live in files, not in the conversation: `docs/features/<slug>/plan.md`,
  `docs/adr/`, `.agentack/briefs/`.
- Keep a task list (one entry per plan item, owner = role). After each stage update
  `docs/features/<slug>/status.md`: path, tags, what is done, what is running, what is next.
  `/agentack resume` reads that file and `$A runs`, then continues from the first unfinished step.
- Never paste a worker's output back in full; keep the decisions, the changed files and the
  check results.

**Closing report** (short, in the user's language): what was done · units, modules and contracts changed ·
check results · crew used and roles skipped, with why (from `$A report`) · any model switches or
non-independent review · open risks · one suggested next step.
