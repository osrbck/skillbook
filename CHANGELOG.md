# Changelog

Changes to the repository itself (installer, layout, tooling). Each skill keeps its own changelog
in `skills/<skill>/CHANGELOG.md`.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `gitcommit` 0.2.0: clean commits under your own name, written by the provider's smallest
  current model and pushed to any git server (see `skills/gitcommit/CHANGELOG.md`)
- Kiro as a fourth install target: `install.sh --kiro` (`~/.kiro/skills`); `--all` now means
  Claude Code, Codex, Antigravity and Kiro, and every skill is written for all four
- `worklog` 0.2.0 reads Antigravity sessions; `agentack` can be conducted from Kiro

### Changed
- `agentack` updated to 2.1.0 (see `skills/agentack/CHANGELOG.md`)

## 2026-11-11

### Added
- skillbook: one repository for all skills
- `agentack` 2.0.0, moved from github.com/osrbck/agentack
- `worklog` 0.1.0, moved from github.com/osrbck/worklog
- One installer for every skill (`install.sh <skill>... [--codex|--agy|--all|--uninstall]`), with
  optional per-skill `install.hook.sh`
- `template/` for new skills, `scripts/validate.py` and a GitHub Actions workflow that validates
  every skill and runs its tests
