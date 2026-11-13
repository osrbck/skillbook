# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-13

### Added
- `/new-skill <task>` builds a skill from the task and from what the session holds about it;
  `/new-skill` alone goes over the session, offers up to three candidates and asks which one
- Four questions before anything is written: name, model power (`light`, `standard`, `strong`),
  breadth (`small`, `medium`, `large`) and where to install
- `newskill.py`: `where`, `draft`, `check`, `install`, `drafts`, `drop`. Installs into Claude
  Code, Codex, Antigravity and Kiro, or a folder; an installed skill is replaced only with
  `--replace`, and the old one is kept as a backup
- `check` refuses a skill with a missing file, a script that does not compile, unfilled lines,
  a key or token, or a description outside the shared limits
- `references/writing.md`: how to write a skill that works in all four providers
