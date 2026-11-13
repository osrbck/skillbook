---
name: new-skill
description: Builds a new agent skill and installs it, from a task given in the call or from what was done in this session. Asks the user for the name, the model power, the breadth and where to install before writing anything, then drafts, checks and installs the skill for Claude Code, Codex, Antigravity and Kiro. Use when the user runs /new-skill or asks to turn something into a skill.
disable-model-invocation: true
---

# new-skill

Turn a task, or the work of this session, into a skill the user can call again. You decide what
the skill is and write it; the helper names the folder, checks the result and installs it.

```bash
python3 <this skill's directory>/scripts/newskill.py <command>
```

## 1. Find what the skill is

- **A task came with the call** (`/new-skill a search skill that does deep searches`): that is
  the skill. Add what this session already holds about it: decisions the user made, commands
  that worked, mistakes that were corrected, files and formats that were agreed on.
- **No task**: go over this session, from what is in your context (do not read transcript
  files). Look for work worth repeating: a procedure done more than once, a sequence of commands
  that had to be found out, a correction the user gave that should hold next time, a report in a
  fixed shape. Offer up to three candidates, one line each (what it would do, what it is built
  from), the strongest first, and ask which one. If the session holds nothing to build from, ask
  what the skill should do. Do not go on without an answer.

## 2. Ask how to build it

Run `newskill.py where` first: it lists the providers on this machine and the skills they
already have, so that your suggestions are real. Then ask these four in **one** message, with
your question tool if you have one, each with a recommended choice first. Ask them in both
cases above, also when the task looks complete. Skip one only if the user already answered it
in the call.

| Question | Choices |
|---|---|
| **Name** | two or three suggestions: short, lowercase, hyphens, not taken in `where` |
| **Model power** | `light`: a script does the work, the model only runs it and prints, cheapest · `standard`: the session's model follows the steps · `strong`: plans first, checks its own result, may hand parts to other agents, costs the most |
| **Breadth** | `small`: one `SKILL.md`, one job · `medium`: `SKILL.md` and a script or a reference file, a few options · `large`: a helper with commands, reference files, its own settings |
| **Where** | this provider only · every provider found here · a folder the user names |

Add a fifth question only when something else truly decides the design (for example which
service it talks to). Everything else you settle yourself and report at the end.

## 3. Write it

Read `references/writing.md` once before you write; it holds what makes a skill work in all four
providers and what each power and breadth means in files.

```bash
python3 <dir>/scripts/newskill.py draft --name <name> --description '<what it does and when to use it>'
```

It prints the draft folder with a `SKILL.md` to fill in. `--invoke auto` lets the agent pick the
skill up on its own; without it the skill runs only when the user calls `/<name>` (the default,
keep it unless the user asked otherwise). Write `SKILL.md` and whatever files the breadth calls
for into that folder. If the skill has a script, run it once against a real or made-up case
before you go on: a skill whose script was never run is not finished.

## 4. Check and install

```bash
python3 <dir>/scripts/newskill.py check <name>
python3 <dir>/scripts/newskill.py install <name> --in <claude|codex|agy|kiro>
```

`--in` is the provider you are running in. For every provider found add `--all`; for some,
`--also codex,kiro`; for a folder, `--dest <folder>`. Fix every `error:` that `check` prints and
weigh every `warning:`. If `install` says a skill of that name is already there, ask the user
before you pass `--replace` (the old one is kept as a backup and the command says where).

## 5. Report

In the user's language, a few lines: the name and how to call it, where it was installed, the
power and breadth it was built with, what you decided on your own, and what was not tried. Say
that a new session picks it up.

## Rules

- Never write a password, token, key, personal data or a path into the user's home folder into
  a skill. Take them out of what you carry over from the session.
- The skill must work in Claude Code, Codex, Antigravity and Kiro unless the user limits it.
  Do not name a tool only one of them has without saying what the others do.
- Do not overwrite an installed skill, and do not install outside the folders above, without
  the user's yes.
- If the user stops before install, the draft stays: `newskill.py drafts` lists it and
  `newskill.py drop <name>` removes it.
