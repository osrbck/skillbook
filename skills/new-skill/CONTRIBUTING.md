# Contributing

Three parts, each with one job. `SKILL.md` is the flow: find what the skill is, ask, write,
check, install, report. `references/writing.md` is what a good skill looks like; change it when
a provider changes how skills behave, and say which provider and version you saw it in.
`scripts/newskill.py` holds what must be true every time: a valid name, a description within
the limits, no missing file, no secret, no silent overwrite. Those have tests.

The order of priorities is **task, context, tokens**. Do not add a question to the four unless
most skills need the answer; every question costs the user a decision.

## Changing the helper

- Standard library only, Python 3.8+. No network request.
- A new provider goes in `PROVIDERS`, `LABELS`, `provider_homes` and the root `install.sh`
  together.
- A new `check` rule that is an `error` blocks install, so it needs a low false-positive rate;
  when in doubt make it a `warning`.
- Nothing is deleted without a backup, and nothing outside the drafts folder, the backups
  folder and the chosen skills folders is written.

## Tests

```bash
python3 -m unittest discover -s tests/new-skill -v   # from the skillbook root
```

Token-shaped fixtures are built at run time, never written as a literal.

## Pull requests

Say which agent you tried the flow in. Update `skills/new-skill/CHANGELOG.md` under
"Unreleased".
