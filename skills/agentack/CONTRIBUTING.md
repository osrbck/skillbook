# Contributing to Agentack

Thanks for helping. The most useful contributions right now:

1. **Verified command lines.** Run `/agentack doctor` (it pings each provider) and open an issue
   or PR with what worked and what did not: CLI version, the model ids your account accepts, the
   exact wording of a usage-limit error.
2. **New providers** (see below).
3. **Sizing rules** backed by real use: a task that got too much or too little crew, and why.
4. **Conductor hosts:** Kiro and Antigravity.

## Adding a provider

Add a class to `skills/agentack/scripts/agentack_core/providers.py` and register it in `PROVIDERS`.

```python
class MyTool(Provider):
    name, label, vendor = "mytool", "My Tool", "vendorname"
    bins = ("mytool",)                       # executable names to look for
    tiers = {"S4": None, "S3": {...}, "S2": {"model": "...", "effort": "medium"}, "S1": {...}}

    def command(self, binary, spec, mode, prompt, cwd, out_file):
        """Return (argv, stdin_text_or_None) for one headless run. mode is "read" or "write"."""

    def final(self, stdout, out_file):
        """Return (final_message, provider_reported_error)."""
```

Optional: `list_models()` + `match` to resolve model slugs from the CLI's own listing,
`limit_probe()` to measure usage, `auth()` for a sign-in hint.

Rules:

- **Headless and non-interactive.** A run must never wait for input.
- **Read-only when asked.** Use the CLI's own switch if it has one and set
  `read_only_enforced = True`; every read-only run is checked with `git status` either way.
- **`vendor` is the model family** used for the reviewer-independence rule.
- **No "auto" in gate roles.** If the only model is a router, leave S3/S4 as `None`.
- Add the provider to `tests/agentack/fakecli.py` and cover: a normal run, a usage-limit error, read-only mode.

## Guidelines

- **Correctness first, then effort, then tokens.** Changes that let builders start before the
  contract gate, or weaken the review gate, need a strong reason.
- **Keep the skill generic.** Project-specific rules belong in the project guide.
- **Prefer measurable rules** ("more than 5 files") over vague ones ("complex tasks").
- The helper stays standard-library-only and makes no network calls.
- Update `skills/agentack/CHANGELOG.md` under "Unreleased".

```bash
python3 -m unittest discover -s tests/agentack -v   # from the skillbook root
```
