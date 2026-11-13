# Contributing

The split is deliberate. `SKILL.md` tells the orchestrator what only it can do: frame the
question, cut the angles, cast the personas, reflect, write the final document;
`references/method.md` holds how. `roles/` holds what each agent is told. Everything mechanical (who runs on which model, which stage comes next, who was
sent back, what an agent is allowed to touch) is code in `scripts/deepsearch.py` and has a test.

## Changing the helper

- Standard library only, Python 3.8+, JSON on stdout. Expected failures are a `Stop` with a short
  `error` code and a `text` a person can act on.
- **Agents get web tools and nothing else.** A new provider command must not give a shell or
  write access, and must never pass a flag that skips permission checks. The test
  `test_agents_get_web_tools_and_nothing_else` guards this; extend it for a new provider.
- A new CLI flag needs a fallback for CLIs that do not know it yet (the list `commands` returns
  is tried in order) and a test with `FAKE_OLD`.
- The link check opens addresses that came out of a model: it must keep refusing private, loopback
  and link-local hosts (`_public`), also after a redirect. Tests run with `DEEPSEARCH_OFFLINE=1`.
- The project file is not trusted with the machine: a new key goes into `PROJECT_KEYS` only if a
  stranger's repository could set it without harm.
- Model names are defaults and keywords, not truth: the CLI's own listing decides, and `setup
  --model` overrides both. When a provider renames its models, change `PROVIDERS`.

## Changing what agents are told

`roles/*.md` are prompts. Keep them short, say why a rule exists, and do not add a rule the
helper could enforce. The reviewer's `VERDICT` lines are parsed by the helper: change their form
in `roles/reviewer.md` and in `VERDICT` together.

## Tests

`tests/deepsearch/test_deepsearch.py` drives whole runs against `tests/deepsearch/fakecli.py`,
which stands in for the four CLIs.

```bash
python3 -m unittest discover -s tests/deepsearch -v   # from the skillbook root
```

## Pull requests

Say which agent, which CLI versions and which degree you tested with. Update
`skills/deepsearch/CHANGELOG.md` under "Unreleased".
