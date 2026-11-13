# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-13

### Added
- A research method after the `autoresearch` skill of Orchestra Research's AI-Research-SKILLs,
  adapted to research on the web: a survey before the plan; a hypothesis per researcher, fixed
  before the search (the plan is copied as it was run); `notes.md` as the run's memory; `log.md`
  as its decision record; and `reflect` after each cycle: conclude, or open another cycle to
  deepen, broaden or pivot, as far as the degree allows (`low` 1, `medium` 2, `hard` 3)
- A team design after Anthropic's multi-agent research system and its `deep-research` skill:
  the question sets the number of researchers (`start --researchers N`, 1 to 8); each gets an
  objective, a boundary ("Not yours") and source guidance; researchers return dense notes (one
  fact per bullet with its link, takeaway and gaps per question) within a budget of searches; a
  writer agent in a clean context writes the final document at `medium` and `hard`;
  `start --builds-on <run>` gives a follow-up run the earlier document as background
- Checks that use no model: every cited link is opened before the review and the dead ones are
  given to the reviewer; `digest.md` gives the orchestrator the takeaways, gaps and verdicts
  without the full documents; `check` lists every source in the final document that nobody on
  the team cited and every link that does not open. The link check never contacts private or
  local addresses; `setup --links off` turns it off
- `/deepsearch <low|medium|hard> <topic>`: the called session orchestrates a team of researchers
  and reviewers and writes one cited document from research that has been reviewed
- Degrees: `low` (2 researchers on fast models), `medium` (3 on thorough models), `hard` (4 on
  the strongest models, plus a second review panel); with no degree it asks
- The reviewer always runs on the strongest model of the first provider, and the second panel on
  another vendor where there is one; the verdict per researcher decides who revises
- Researchers run in parallel through the provider CLIs (Claude Code, Codex, Antigravity, Kiro)
  with web tools only: no shell, no file edits, no permission bypass
- A provider that fails, hits a usage limit or lacks a model is replaced by the next one; with no
  CLI at all the calling session plays every role itself
- `setup`, `verify`, `roster`, `init`, `status`: choose providers, models per tier (`fast`,
  `deep`, `top`), who reviews, the team size per degree, timeouts, output folder and language;
  `verify` pings every model, checks web search and drops what the account does not have
- `.deepsearch.json` for a project: output folder, language, focus, citation style, preferred
  and avoided sources, allowed providers. It cannot change binaries, models or team sizes
