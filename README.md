# skillbook

A collection of open-source skills for AI coding agents. Each skill is a folder with a `SKILL.md`
(the open [Agent Skills](https://agentskills.io) format), so the same skill works in
**Claude Code**, **Codex**, **Antigravity** and **Kiro**. Every skill here is written for all four and
runs wherever the agent does: desktop app, IDE or CLI.

> 🇹🇷 Türkçe: [README.tr.md](README.tr.md)

## Skills

| Skill | What it does | Command |
|---|---|---|
| [**agentack**](skills/agentack/) | Conductor for full stack work in any language and architecture: reads the project once, sizes each task and routes it to the smallest crew of specialist agents across Claude, Codex, Antigravity, Cursor and Kiro, with contract and review gates. | `/agentack` |
| [**gitcommit**](skills/gitcommit/) | Turns the changes in your working tree into a few clean commits and pushes them, in one command: grouped by purpose, short messages in the repository's own convention and language, your name only (no co-author or AI attribution), secrets and junk left out. The messages are written by your provider's smallest current model, so it costs very few tokens. Works with any git server. | `/gitcommit` |
| [**new-skill**](skills/new-skill/) | Turns a task, or the session you just had, into a skill you can call again: works out what the skill should be, asks you for the name, the model power, the breadth and where to install, then writes it, checks it and installs it in the agents you use. | `/new-skill` |
| [**deepsearch**](skills/deepsearch/) | Researches a topic with a team of agents: your session frames the question and gives each researcher a persona and an angle, they work in parallel on the web through the CLIs you have, a reviewer on the strongest model checks their sources and sends back what does not hold, and what survives becomes one cited document. A degree (`low`, `medium`, `hard`) sets the size and strength of the team. | `/deepsearch` |
| [**worklog**](skills/worklog/) | Scans your local AI coding sessions (Claude Code, Codex, Antigravity, Kiro, OpenCode) for a time range and writes a report of the work done, grouped by project, with time estimates, commits and issue keys. | `/worklog` |

Each skill's folder has its own README, changelog and contributing notes.

## Install

```bash
git clone https://github.com/osrbck/skillbook.git ~/skillbook
cd ~/skillbook

./install.sh                          # list the skills
./install.sh worklog                  # one skill, for Claude Code
./install.sh worklog agentack --all   # several skills, for Claude Code, Codex, Antigravity and Kiro
./install.sh --everything --codex     # every skill, for Codex
```

| Flag | Installs to |
|---|---|
| *(none)* or `--claude` | `~/.claude/skills/<skill>` (respects `CLAUDE_CONFIG_DIR`) |
| `--codex` | `~/.codex/skills/<skill>` (respects `CODEX_HOME`) |
| `--agy` | `~/.gemini/config/skills/<skill>` (Antigravity app, IDE and CLI) |
| `--kiro` | `~/.kiro/skills/<skill>` (Kiro IDE and CLI; respects `KIRO_HOME`) |
| `--all` | all four |

Update with `git pull && ./install.sh <skill>...`, remove with `./install.sh <skill>... --uninstall`.
Only the skill itself is copied; READMEs, changelogs and install hooks stay in the repo.

**Requirements:** Python 3.8+ and bash, on macOS, Linux or WSL. The skills' helper scripts use
only the Python standard library.

## Repository layout

```
skillbook/
├── install.sh                  # one installer for every skill
├── skills/
│   └── <skill>/
│       ├── SKILL.md            # required: name + description frontmatter, then instructions
│       ├── scripts/ …          # optional helpers, references, templates
│       ├── README.md           # repo-only: docs shown on GitHub
│       ├── CHANGELOG.md        # repo-only
│       └── install.hook.sh     # repo-only, optional: post_install / post_uninstall
├── tests/<skill>/              # tests per skill
├── docs/<skill>/               # images and other docs assets
├── template/                   # starting point for a new skill
└── scripts/validate.py         # checks every skill's structure (runs in CI)
```

## Development

```bash
python3 scripts/validate.py                               # structure and frontmatter of every skill
python3 -m unittest discover -s tests/worklog -v          # one skill's tests
for d in tests/*/; do python3 -m unittest discover -s "$d"; done   # all of them
```

Want to add a skill? See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE). skillbook is a community project and is not affiliated with Anthropic, OpenAI,
Google, Cursor or AWS.
