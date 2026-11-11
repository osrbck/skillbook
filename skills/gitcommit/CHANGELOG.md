# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
