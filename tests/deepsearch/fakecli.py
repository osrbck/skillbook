#!/usr/bin/env python3
"""Stand-in for the four agent CLIs (claude, codex, agy, kiro-cli) as the deepsearch helper calls them.

It answers a research prompt with a short document, a review prompt with a review that ends in
VERDICT lines, and the two `verify` prompts with OK / WEB-OK. Every call is logged to FAKE_LOG.

  FAKE_<NAME>=fail|limit|nomodel   make that CLI fail in that way (NAME: CLAUDE, CODEX, AGY, KIRO)
  FAKE_<NAME>_WEB=no               that CLI has no web search
  FAKE_NOMODEL=<slug,…>            these models are refused by every CLI
  FAKE_OLD=1                       the CLIs reject the newer flags
  FAKE_REVISE=researcher-1,…       who the first review sends back (default: researcher-1)
  FAKE_PANEL_REVISE=…              who the second panel sends back (default: nobody)
  FAKE_SHORT=1                     answers are too short to count
"""

import json
import os
import re
import sys

name = os.environ.get("FAKE_NAME") or os.path.basename(sys.argv[0])
key = {"claude": "CLAUDE", "codex": "CODEX", "agy": "AGY", "kiro-cli": "KIRO"}[name]
args = sys.argv[1:]
env = os.environ


def flag(f, default=None):
    return args[args.index(f) + 1] if f in args else default


def log(**entry):
    if env.get("FAKE_LOG"):
        with open(env["FAKE_LOG"], "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"cli": name, "argv": [a if len(a) < 300 else a[:80] + "…" for a in args],
                                 "cwd": os.getcwd(), **entry}) + "\n")


if args[:1] == ["--version"]:
    print("%s 9.9.9 (fake)" % name)
    sys.exit(0)

# -- model listings --
if name == "codex" and args[:1] == ["app-server"]:
    for line in sys.stdin:
        msg = json.loads(line)
        if msg.get("method") == "model/list":
            models = [m for m in env.get("FAKE_CODEX_MODELS", "gpt-6-astra,gpt-6.1-sol,gpt-6-luna").split(",") if m]
            print(json.dumps({"id": msg["id"], "result": {"data": [{"id": m, "model": m} for m in models]}}), flush=True)
        else:
            print(json.dumps({"id": msg.get("id"), "result": {}}), flush=True)
    sys.exit(0)
if name == "agy" and args[:1] == ["models"]:
    for m in env.get("FAKE_AGY_MODELS", "gemini-4-argon-medium,gemini-4-argon-high,gemini-3.8-flash-high,gemini-3.8-flash-low,gemini-3.5-flash-lite").split(","):
        print("%s\t%s" % (m, m.replace("-", " ").title()))
    sys.exit(0)
if name == "kiro-cli" and "--list-models" in args:
    rows = [{"model_name": "auto", "model_id": "auto", "description": "Models chosen by task"}]
    for mid in env.get("FAKE_KIRO_MODELS", "claude-opus-5.5,claude-opus-5,claude-opus-4.8,claude-sonnet-5.5,claude-haiku-5.5,qwen3-next!").split(","):
        if mid:
            rows.append({"model_name": mid.rstrip("!"), "model_id": mid.rstrip("!"),
                         "description": "Experimental preview" if mid.endswith("!") else "A model"})
    print(json.dumps({"models": rows, "default_model": "auto"}))
    sys.exit(0)

# -- one question, one answer --
NEW = ("--tools", "--search", "--effort", "--trust-tools=*web*,web_search,web_fetch")
if env.get("FAKE_OLD") and any(a in args for a in NEW):
    sys.stderr.write("error: unknown option '%s'\n" % next(a for a in args if a in NEW))
    sys.exit(2)
prompt = flag("-p", "") if name == "agy" else sys.stdin.read()
from_file = False
if name == "agy" and "PROMPT.md" in prompt and os.path.exists("PROMPT.md"):
    prompt, from_file = open("PROMPT.md", encoding="utf-8").read(), True
model = flag("--model")
agent = (re.search(r"YOUR ASSIGNMENT: you are (\S+)", prompt) or [None, None])[1]
if prompt.startswith("# Writer"):
    agent = "writer-1"
log(model=model, agent=agent, from_file=from_file, chars=len(prompt),
    stage="write" if agent == "writer-1" else "panel" if "# Second panel" in prompt else "review" if "# Reviewer" in prompt
    else "revise" if "# Revision" in prompt else "research" if agent else "ping")

mode = env.get("FAKE_" + key)
if mode == "fail":
    sys.stderr.write("boom: the provider is having a bad day\n")
    sys.exit(1)
if mode == "limit":
    sys.stderr.write("You have hit your usage limit. Try again later.\n")
    sys.exit(1)
if mode == "nomodel" or (model and model in env.get("FAKE_NOMODEL", "").split(",")):
    sys.stderr.write("The model `%s` does not exist or you do not have access to it.\n" % model)
    sys.exit(1)

if "single word OK" in prompt:
    answer = "OK"
elif "WEB-OK" in prompt:
    answer = "NO-WEB" if env.get("FAKE_%s_WEB" % key) == "no" else "WEB-OK 3.14.2"
elif agent == "writer-1":
    answer = "# Cells last longer than expected\n\nWritten on %s. %s ([Example](https://example.org))%s\n\n## How this was researched\nBy a team.\n" % (
        model, "The answer first. " * 12, " ([Invented](https://invented.example.com/x))" if env.get("FAKE_WRITER_INVENTS") else "")
elif "# Reviewer" in prompt:
    panel = "# Second panel" in prompt
    shown = sorted(set(re.findall(r"^===== (researcher-\d+) =====$", prompt, re.M)))
    back = env.get("FAKE_PANEL_REVISE", "") if panel else env.get("FAKE_REVISE", "researcher-1")
    answer = "# Review\n\n## Overall\nBy %s on %s. %s\n\n" % (agent, model, "The team has covered the question. " * 6)
    answer += "".join("## %s\nSolid: the sources.\nProblems:\n1. [must] \"a claim\" → unsupported → cite it\n\n" % r
                      for r in shown if r in back.split(","))
    answer += "## Verdicts\n" + "\n".join("VERDICT %s: %s" % (r, "revise" if r in back.split(",") else "accept") for r in shown)
else:
    revised = "# Revision" in prompt
    answer = ("# Findings of %s\n\n## Hypothesis\nSupported: written on %s by %s.%s\n\n## Question one\n\n### Takeaway\nTAKEAWAY-OF-%s. %s\n\n"
              "### Cited findings\n- CITED-FINDING %s — [Example, 2026](https://example.org)%s\n\n### Inferences\n- INFERENCE\n\n### Gaps\n- GAP-OF-%s\n" % (
                  agent, model, name, " REVISED." if revised else "", agent, "It holds. " * 12, "with detail " * 8,
                  "\n- another — [Gone](%s)" % env["FAKE_DEAD_LINK"] if env.get("FAKE_DEAD_LINK") else "", agent))
    if revised:
        answer += "\n## Changes\n- a claim → cited\n"
if env.get("FAKE_SHORT") and agent:
    answer = "Too short."

if name == "claude":
    print(json.dumps({"type": "result", "result": answer, "is_error": False}))
elif name == "codex":
    open(flag("-o"), "w", encoding="utf-8").write(answer)
    print("tokens used: 123")
elif name == "agy":
    print(json.dumps({"status": "SUCCESS", "response": answer + "\n"}))
else:
    print("\x1b[32m> \x1b[0m" + answer)
