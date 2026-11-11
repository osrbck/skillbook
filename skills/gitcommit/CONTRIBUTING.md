# Contributing

The split is deliberate. `SKILL.md` is a few lines for the agent the user is working with: run
one command, print its report. How to group changes and word a subject is written once, in the
prompt the helper builds for the provider's small model (`build_prompt`). Anything that must hold
every time (whose name is on a commit, what a message may contain, what is never pushed, what a
model is never shown) is code in `scripts/gitcommit.py` and has a test.

The order of priorities is **task, context, tokens**: the commits must be right, the small model
must see enough of the diff to name them truthfully, and only then do we save tokens. Do not cut
context to save tokens, and do not add words to `SKILL.md` that the helper could enforce.

## Changing the helper

- Standard library only, Python 3.8+, JSON on stdout. Expected failures are a `Stop` with a
  short `error` code and a `text` a person can act on.
- It must stay safe to call: no force, no `--no-verify`, no history rewriting, no change to git
  configuration or remotes, no network request except `git push`.
- A new rule for messages goes in `message_problems`, so that `commit` and `check` agree.
- A new kind of flag needs a low false-positive rate. A file left out by mistake is reported and
  can be included; a secret that got pushed cannot be taken back. Name and size rules apply only
  to files git does not track yet.
- Never print a secret: flags carry the kind and the line, not the value.

## Tests

`tests/gitcommit/test_gitcommit.py` drives the helper against throwaway repositories and bare
remotes; `tests/gitcommit/fakecli.py` stands in for the four provider CLIs. A new provider flag
needs a fallback for CLIs that do not know it yet (see `ask_model`) and a test with `FAKE_OLD`. Build token-shaped fixtures at run time (`"ghp_" + "a" * 36`), never as a literal, so
that no scanner trips over the test file.

```bash
python3 -m unittest discover -s tests/gitcommit -v   # from the skillbook root
```

## Pull requests

Say which agent and which git version you tested with. Update
`skills/gitcommit/CHANGELOG.md` under "Unreleased". And yes: commit it with `/gitcommit`.
