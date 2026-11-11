#!/usr/bin/env python3
"""Stand-in for the four agent CLIs (claude, codex, agy, kiro-cli) as `gitcommit run` calls them.

It answers a plan prompt with one commit for every path under CHANGES, unless FAKE_ANSWERS names
a file with answers to give in turn (separated by a line of `---`). Every call is logged to
FAKE_LOG. FAKE_<NAME>=fail makes the CLI fail; FAKE_OLD=1 makes it reject newer flags."""

import json
import os
import re
import sys

name = os.environ.get("FAKE_NAME") or os.path.basename(sys.argv[0])
key = {"claude": "CLAUDE", "codex": "CODEX", "agy": "AGY", "kiro-cli": "KIRO"}[name]
args = sys.argv[1:]


def flag(f, default=None):
    return args[args.index(f) + 1] if f in args else default


def log(**entry):
    if os.environ.get("FAKE_LOG"):
        with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"cli": name, "argv": [a if len(a) < 300 else a[:80] + "…" for a in args],
                                 "cwd": os.getcwd(), **entry}) + "\n")


# -- model listings --
if name == "codex" and args[:1] == ["app-server"]:
    for line in sys.stdin:
        msg = json.loads(line)
        if msg.get("method") == "model/list":
            models = [m for m in os.environ.get("FAKE_CODEX_MODELS", "gpt-5.6-luna,gpt-5.6-terra,gpt-6-luna").split(",") if m]
            print(json.dumps({"id": msg["id"], "result": {"data": [{"id": m, "model": m} for m in models]
                                                           + [{"id": "internal-luna-9", "model": "internal-luna-9", "hidden": True}]}}),
                  flush=True)
        else:
            print(json.dumps({"id": msg.get("id"), "result": {}}), flush=True)
    sys.exit(0)
if name == "agy" and args[:1] == ["models"]:
    print("Fetching available models...")
    for m in os.environ.get("FAKE_AGY_MODELS", "gemini-4-argon-high,gemini-3.8-flash-high,gemini-3.8-flash-low").split(","):
        print("%s\t%s" % (m, m.replace("-", " ").title()))
    sys.exit(0)
if name == "kiro-cli" and "--list-models" in args:
    rows = [{"model_name": "auto", "model_id": "auto", "description": "Models chosen by task", "rate_multiplier": 1.0}]
    for item in os.environ.get("FAKE_KIRO_MODELS", "claude-opus-5.5=2.0,claude-haiku-5.5=0.06,claude-haiku-4.5=0.4,qwen3-coder-next=0.05!").split(","):
        if item:
            mid, rate = item.split("=")
            rows.append({"model_name": mid, "model_id": mid, "rate_multiplier": float(rate.rstrip("!")),
                         "description": "Experimental preview" if rate.endswith("!") else "A model"})
    print(json.dumps({"models": rows, "default_model": "auto"}))
    sys.exit(0)

# -- one question, one answer --
if os.environ.get("FAKE_OLD") and any(a in args for a in ("--no-session-persistence", "--ephemeral", "--trust-tools=", "--effort")):
    sys.stderr.write("error: unknown option '%s'\n" % next(a for a in args if a.startswith("--")))
    sys.exit(1)
prompt = flag("-p", "") if name == "agy" else sys.stdin.read()
log(model=flag("--model"), prompt=prompt)
if os.environ.get("FAKE_" + key) == "fail":
    sys.stderr.write("boom: the provider is having a bad day\n")
    sys.exit(1)

answer = None
script = os.environ.get("FAKE_ANSWERS")
if script:
    answers = open(script, encoding="utf-8").read().split("\n---\n")
    count_file = script + ".n"
    n = int(open(count_file).read()) if os.path.exists(count_file) else 0
    open(count_file, "w").write(str(n + 1))
    answer = answers[min(n, len(answers) - 1)]
if answer is None:
    section = prompt.split("\nCHANGES\n", 1)[1].split("\nDIFF\n", 1)[0] if "\nCHANGES\n" in prompt else ""
    paths = [re.sub(r"  \((new|changed|deleted|renamed|copied)[^)]*\)$", "", ln) for ln in section.splitlines() if ln.strip()]
    answer = json.dumps({"commits": [{"subject": os.environ.get("FAKE_SUBJECT", "feat: update the project"),
                                      "body": [], "paths": paths}]})

if name == "claude":
    print(json.dumps({"type": "result", "result": answer, "is_error": False}))
elif name == "codex":
    open(flag("-o"), "w", encoding="utf-8").write(answer)
    print("tokens used: 123")
elif name == "agy":
    print(json.dumps({"status": "SUCCESS", "response": answer + "\n"}))
else:
    print("\x1b[32m> Here is the plan:\x1b[0m\n```json\n" + answer + "\n```")
