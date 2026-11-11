# Contributing to skillbook

Thanks for helping. You can improve an existing skill or add a new one.

## Improving a skill

Each skill has its own contributing notes, for example
[skills/agentack/CONTRIBUTING.md](skills/agentack/CONTRIBUTING.md),
[skills/gitcommit/CONTRIBUTING.md](skills/gitcommit/CONTRIBUTING.md) and
[skills/worklog/CONTRIBUTING.md](skills/worklog/CONTRIBUTING.md). Note your change under
"Unreleased" in that skill's `CHANGELOG.md`.

## Adding a skill

1. Copy the template: `cp -R template skills/<your-skill>`. The folder name is the skill name:
   lowercase letters, digits and hyphens.
2. Fill in `SKILL.md`. The frontmatter needs:
   - `name`: the same as the folder name
   - `description`: what the skill does **and when to use it**, in one paragraph. Agents decide
     whether to load a skill from this line alone, so make it specific.
3. Keep `SKILL.md` focused. Put long reference material in `references/` and helper code in
   `scripts/`, and tell the agent in `SKILL.md` when to read or run them.
4. Write `README.md` for people (what it does, how to use it, an example). A Turkish
   `README.tr.md` is welcome.
5. Add tests in `tests/<your-skill>/` if the skill has scripts.
6. If the skill needs a step after installing (a check, a migration), add `install.hook.sh` with a
   `post_install` and/or `post_uninstall` function. It is sourced by `install.sh` and not copied
   into the agent's skills folder.
7. Add a row to the skills table in both root READMEs.
8. Run the checks:

   ```bash
   python3 scripts/validate.py
   python3 -m unittest discover -s tests/<your-skill> -v
   ./install.sh <your-skill> && ls ~/.claude/skills/<your-skill>
   ```

## Guidelines

- **Agent-neutral.** Write for any agent that reads `SKILL.md`. Note tool-specific parts clearly.
- **Standard library only** for helper scripts, and no network calls unless that is the skill's
  purpose and the README says so.
- **Safe by default.** A skill must not delete, push or send anything without the user asking.
- **No personal data in fixtures.** Use synthetic data; never commit real transcripts or secrets.
- One skill per pull request, with a short description of what you tested and on which agent.
