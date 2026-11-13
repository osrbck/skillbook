# new-skill

**Turn a task, or the session you just had, into a skill you can call again.** `/new-skill`
works out what the skill should be, asks you how to build it, writes it, checks it and installs
it in the agents you use.

> 🇹🇷 Türkçe: [README.tr.md](README.tr.md)

```
/new-skill a search skill that does deep searches
```

```
/new-skill
```

Works in **Claude Code, Codex, Antigravity and Kiro**, whichever one you call it from.

## What it does

- **From a task.** Say what the skill should do after `/new-skill`. Whatever the session already
  holds about it (decisions, commands that worked, corrections you gave) goes into the skill.
- **From the session.** Called with nothing, it goes over the conversation, offers up to three
  things worth turning into a skill and asks which one.
- **It asks before it writes.** Every time, in one message:

  | Question | Choices |
  |---|---|
  | Name | two or three suggestions that are not taken |
  | Model power | `light` (a script does the work, cheapest), `standard` (the session's model follows the steps), `strong` (plans, checks its own result, may use other agents) |
  | Breadth | `small` (one `SKILL.md`), `medium` (plus a script or a reference file), `large` (a helper with commands, references, settings) |
  | Where | this provider, every provider found on the machine, or a folder you name |

- **It checks what it wrote.** Name and description within the limits the agents share, every
  file `SKILL.md` names is there, scripts compile, nothing left to fill in, no key or token, no
  path into one person's home folder.
- **It installs.** Into the skills folder of the providers you chose. A skill that is already
  there is never overwritten without your yes, and the old one is kept as a backup.

## Install

```bash
./install.sh new-skill --all
```

## How it works

`SKILL.md` tells the agent what to find out, what to ask and in which order. The writing rules
(what makes a skill work in four providers, what each power and breadth means in files) are in
[references/writing.md](references/writing.md), read once per skill. The helper does the parts
that should not depend on a model:

```
newskill.py where [--name N]        providers found here, their skills, whether a name is free
newskill.py draft --name N --description D [--invoke auto]
newskill.py check N|DIR
newskill.py install N|DIR --in P [--also a,b | --all] [--dest DIR] [--replace]
newskill.py drafts · drop N
```

Drafts live in `~/.local/state/new-skill/drafts/` until they are installed. The helper needs
Python 3.8+ and nothing else, and makes no network request.

## What it does not do

- It cannot change the model a skill runs on: a skill runs on the model of the session that
  calls it. "Model power" decides how the work is split between a script, the session's model
  and, where it pays, a call to another model through the provider's CLI.
- It does not publish the skill anywhere. `--dest` can put it in a repository of yours; the
  rest is up to you.

## Status

`0.1.0`. The helper is covered by tests. The flow was written for all four providers; how well
each one asks the questions depends on its own question tool.
