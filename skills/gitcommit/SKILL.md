---
name: gitcommit
description: Turns the changes in the working tree into a few clean, professional commits and pushes them, in one command and with very few tokens. A helper script scans everything that changed (whoever made it and whenever), lets the smallest current model of the provider in use (Claude, Codex, Antigravity or Kiro) write the commit plan, commits under the user's own name with no co-author or AI attribution, in the repository's own convention and language, and pushes to whatever remote the project has. Called together with a task, the task is done first and committed at the end. Runs only when called with /gitcommit.
disable-model-invocation: true
---

# gitcommit

One command does the whole job. The helper scans the working tree, asks the smallest current
model of the provider you are running in for the commit plan, makes the commits under the
user's own name, pushes them and prints a short report. **You do not read diffs, plan commits
or write messages yourself, and you add no words of your own.**

```bash
python3 <this skill's directory>/scripts/gitcommit.py run --in <claude|codex|agy|kiro> [flags]
```

Run it from the project folder. `--in` is the provider you are running in right now:
Claude Code → `claude`, Codex → `codex`, Antigravity → `agy`, Kiro → `kiro`.

## Flags

Take them from what the user wrote after `/gitcommit` (any language):

| The user says | Flag |
|---|---|
| nothing | none: everything that changed → commits → push |
| `no push`, `local`, `pushlama` | `--no-push` |
| `staged` | `--staged` (only what is staged, as one commit) |
| `single`, `one commit`, `tek commit` | `--single` |
| `plan`, `dry run` | `--dry-run` (shows the plan, changes nothing) |
| `include <path>` | `--include <path>` (a path that was left out as flagged) |
| a language (`in English`, `türkçe`) | `--lang <language>` |
| `ask`, `sor` | `--ask` (a password window may open on the user's screen: say so first) |
| words about work that is already in the tree | `--hint '<those words>'` |
| a task: work that is not done yet | see below |

## Called with a task

When the call carries work that the tree does not show yet ("add coupon support to checkout"),
do the task first, the way you would without this skill, with the project's own tests and
checks. When it is finished, run the command with `--hint '<the task in a few words>'`. If the
task could not be finished, or its checks fail and you cannot fix them, do not run the command:
say where the work stands. Unfinished work is not pushed.

## Output

Print the report the command printed, in the user's language, and stop. Keep commit lines,
paths and commands exactly as they are. No introduction, no account of what you ran, no summary
of the code, no advice, no closing sentence.

- **`NEED-PLAN`** (exit code 3): the small model could not be used. Read the file the message
  names (it holds the rules, the history and the changes), write the JSON plan it asks for to a
  file, and run the same command with `apply --plan <file>` in place of `run --in …`. Then
  print that report.
- **`push stopped`** with numbered options: the commits are made and safe, only the push is
  missing. Print the options as they are; the first is the recommended one. If the user answers
  with one of them, run exactly that command and then `run` again.
- **`Blocked:`**: print it. Nothing was changed.

## Rules

- Never commit or push by hand, and never add a co-author, a tool name or a "generated with"
  line anywhere. The helper refuses them.
- Never ask for, type or store a password or token. Never change a remote, a git setting or the
  history, never force a push, never skip a hook.
- Outside a task given in the call, do not fix or improve the code that is being committed.
