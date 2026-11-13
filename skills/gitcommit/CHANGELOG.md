# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- The provider is now named with `--in` (`run --in kiro`). Kiro's terminal guard takes a command
  that contains `--host` for one that starts a server and refuses it, which cost the calling
  agent several extra turns. `--host` still works

## [0.2.0] - 2026-11-11

The whole job is now one command, and the model that writes the commit messages is the smallest
current model of the provider you are running in.

### Added
- `run`: scans the tree, asks the provider's small model for the commit plan in a single call,
  commits, pushes and prints a report of a few lines; `apply --plan` does the same with a plan
  that was handed in
- The small model is found, not hardcoded: Claude Code uses the `haiku` alias; Codex, Antigravity
  and Kiro are asked for their own model list and the newest model of their small family is
  taken (Luna, Flash-Lite or Flash at its lightest effort, Haiku or the lowest-rate model);
  `--model` or `GITCOMMIT_MODEL` overrides it
- The model is called through the provider's own CLI with no tools, no permissions and an empty
  folder: it sees the history, the list of changes and a bounded diff, and answers with JSON
- Its answer is checked before anything is written (every path exactly once, message rules,
  one commit when one was asked for) and sent back once when it is wrong
- Fallback: when the CLI is missing or fails, the calling agent gets the same brief and writes
  the plan itself, so the work is always finished
- Kiro support: `install.sh --kiro` (`~/.kiro/skills`), `--host kiro`

### Changed
- `SKILL.md` went from about 16 KB to under 4 KB: the calling agent runs one command and prints
  its report, with no commentary. The rules moved into the helper
- Flagged paths (secrets, credential files, junk) are removed before the model sees anything
- A rename is planned as one unit; the user's index is left as it was while planning

## [0.1.0] - 2026-11-11

### Added
- `/gitcommit` skill for Claude Code, Codex and Antigravity: groups the working tree into
  commits by purpose, writes short messages and pushes; runs only when called
- The whole working tree is in scope, whichever session, agent or person changed it; recent
  history (`inspect` → `recent`) guides how the changes are split and named
- Called with a task (`/gitcommit add coupon support`), it does the task and commits and pushes
  it as the last step; unfinished or failing work is not pushed
- Helper with `inspect`, `init`, `commit`, `check` and `push`
- Commit style learned from the repository's history: Conventional Commits, gitmoji, ticket
  prefix or plain sentences; Conventional Commits in a new repository
- Messages in the language of the repository's history (Turkish history, Turkish commits),
  with the history's verb form; English in a new repository; a language named in the call wins
- Message rules enforced before a commit is written: subject of at most 72 characters without a
  period, a body of at most five lines, no `Co-authored-by` trailer, no AI attribution line, no
  sign-off by anyone else
- Author and committer always taken from the user's git configuration; identity variables set
  by the host are ignored
- Flags for what must stay out: secrets on added lines, new credential files, conflict markers,
  new files over 5 MB, junk files and folders
- Push to the remote the project already has, on any host; a new branch is published with the
  same name; never forced. Without a remote the commits stay local, and a folder without git
  gets `git init`
- A push never opens a password window on its own: git's fallback to the desktop's SSH
  passphrase program (`SSH_ASKPASS`) and Git Credential Manager's interactive mode are switched
  off unless the call says `ask`; helpers, `GIT_ASKPASS`, `core.askPass` and SSH are used as set up
- A refused sign-in is explained (`sign_in`: transport, host, helpers, whether the server accepts
  an SSH key this machine has) with the options to fix it, easiest first
- Arguments: `no push`, `staged`, `single`, `plan`, `include <path>`, `ask`, a language
