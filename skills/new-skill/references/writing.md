# Writing the skill

Priorities, in this order: **task, context, tokens**. The skill must do its job right; the agent
must have what it needs to do so; only then cut words.

## The description

It is the only part an agent sees before the skill is opened. One line, at most 1024 characters:
what the skill does, then when to use it ("Use when the user runs /name or asks …"). Name the
things a user would say. No line breaks, no `|` or `>` block.

## SKILL.md

Written to the agent, in the imperative, in English (the report to the user is in the user's
language; say so in the skill). Put first what is done first.

- Open with one or two sentences: what the skill does and what the result looks like.
- Steps in order. A command the agent must run is given in full, in a code block.
- Give the reason with a rule when the reason lets the agent handle a case you did not foresee.
- A table for a mapping (what the user says → which flag). An example of the output when its
  shape matters.
- End with rules: what must never happen, what to do when a step fails.
- Leave out what any capable agent already does. Leave out the history of how the skill came
  about.
- Past about 300 lines, move detail to `references/<topic>.md` and say in `SKILL.md` when to
  read it. The agent reads a reference only when told to.

## Working in all four providers

- A skill folder is installed under a different path in each provider. Refer to bundled files as
  `<this skill's directory>/scripts/x.py`, never by an absolute path.
- Scripts: Python 3.8+, standard library only, or plain shell. No package to install.
- Say "ask the user" and "your question tool if you have one", not one provider's tool name.
  The same for subagents, web search and file tools: name the ability, not the tool.
- Kiro refuses terminal commands that look like starting a server. Keep the words `host`,
  `port` and `serve` out of the flags and commands you make the agent type.
- `/name` is how the user calls it in all four. `disable-model-invocation: true` in the
  frontmatter keeps the agent from starting it on its own; providers that do not know the line
  ignore it.
- When the skill needs to know which provider it runs in, make the agent pass it as a flag
  (`--in claude|codex|agy|kiro`); a script cannot tell reliably.

## Model power

A skill cannot change the model of the session it runs in. Power is how the work is divided.

| Power | What you write |
|---|---|
| `light` | A script does everything that can be decided without judgement and prints a short report. `SKILL.md` is a few lines: run this, print that, add nothing. Works on the smallest models and costs the least. |
| `standard` | `SKILL.md` carries the method; the session's model does the thinking. A script only for what must be exact (parsing, counting, file layout, checks). |
| `strong` | `SKILL.md` makes the agent plan before acting, state what done means, and check its result against that in a second pass. Where the provider has subagents, independent parts and the check go to them; where it has none, the agent does them in turn. Tell the user it costs more. |

A step can run on another model only through that provider's CLI, called from a script, with a
fallback for when the CLI is missing. The forms that work without a terminal:

```
claude -p --model <model>                      prompt on stdin
codex exec --model <model> -                   prompt on stdin
agy -p '<prompt>' --model <model>
kiro-cli chat --no-interactive --model <model> '<prompt>'
```

Use this only when it pays for itself: a cheap model for bulk work under a strong session, or a
strong one for a single review. Find the model from what the CLI lists instead of fixing a
name that will age.

## Breadth

| Breadth | Files |
|---|---|
| `small` | `SKILL.md`. One job, no options to speak of. |
| `medium` | `SKILL.md` and either `scripts/<name>.py` or one or two `references/*.md`. A few flags taken from what the user writes after `/name`. |
| `large` | `SKILL.md` as the map, `scripts/<name>.py` with subcommands, `references/` for method, settings the user can change (kept under `~/.config/<name>/`, never in the skill folder, which is replaced on reinstall), and a command that checks the setup. |

Build the breadth that was asked for. A small skill that works beats a large one that was not
tried.

## Scripts

- One file with subcommands rather than many files. `--help` works. Output is short and meant
  for the agent: a report to print, or JSON to read.
- An expected failure is one line that says what to do next, and a non-zero exit code.
- Read-only by default. Anything that deletes, overwrites, sends or pushes is a separate
  command the skill tells the agent to confirm with the user first.
- No network unless the skill is about the network; say in `SKILL.md` where it connects.

## From a session to a skill

Carry over what was learned, not what happened: the command that worked (not the three that did
not), the user's corrections as rules, the agreed output shape as an example. Replace the
session's specifics (this repository, these file names, this account) with what the user passes
in or the script finds. Anything secret or personal stays out.
