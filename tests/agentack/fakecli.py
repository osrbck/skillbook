#!/usr/bin/env python3
"""Stand-in for every agent CLI. Behavior comes from FAKE_<NAME> = ok | limit | error | edit | slow."""

import json
import os
import sys
import time

name = os.environ.get("FAKE_NAME") or os.path.basename(sys.argv[0])
key = {"claude": "CLAUDE", "codex": "CODEX", "agy": "AGY", "cursor-agent": "CURSOR", "kiro-cli": "KIRO"}[name]
mode = os.environ.get("FAKE_" + key, "ok")
args = sys.argv[1:]


def flag(f, default=None):
    return args[args.index(f) + 1] if f in args else default


if "--version" in args:
    print("%s 9.9.9 (fake)" % name)
    sys.exit(0)

if name == "kiro-cli" and args[:1] == ["whoami"]:
    if os.environ.get("FAKE_KIRO_LOGIN", "yes") == "yes":
        print("Logged in with Builder ID")
        sys.exit(0)
    sys.stderr.write("Not logged in. Run kiro-cli login\n")
    sys.exit(1)

if name == "kiro-cli" and "/usage" in args:
    spent = float(os.environ.get("FAKE_KIRO_SPENT", "5"))
    print("\x1b[1m| KIRO PRO\x1b[0m\nMonthly credits:\n\u2588\u2588\u2588 %d%% (resets on 12/01)\n"
          "(%.2f of 50 covered in plan)\nBonus credits:\n0.00/100 credits used, expires in 20 days" % (spent * 2, spent))
    sys.exit(0)

if name == "agy" and args[:1] == ["models"]:
    listing = os.environ.get("FAKE_AGY_MODELS") or ("gemini-4-argon-high,gemini-4-argon-low,gemini-3.1-pro-high,"
                                                    "gemini-3.8-flash-medium,gemini-3.8-flash-high,gemini-3.5-flash-lite")
    print(listing.replace(",", "\n"))
    sys.exit(0)

if name == "codex" and args[:1] == ["app-server"]:
    for line in sys.stdin:
        msg = json.loads(line)
        if msg.get("method") == "model/list":
            models = (os.environ.get("FAKE_CODEX_MODELS") or "gpt-6-astra,gpt-6.1-sol,gpt-6-luna,gpt-5.6-sol").split(",")
            print(json.dumps({"id": msg["id"], "result": {"data": [{"id": m, "model": m, "displayName": m.upper()}
                                                                    for m in models] +
                                                                   [{"id": "internal-x", "model": "internal-x", "hidden": True}]}}),
                  flush=True)
        elif msg.get("method") == "account/rateLimits/read":
            used = float(os.environ.get("FAKE_CODEX_USED", "10"))
            print(json.dumps({"id": msg["id"], "result": {"rateLimits": {
                "primary": {"usedPercent": used, "resetsAt": None},
                "secondary": {"usedPercent": 5, "resetsAt": None}}}}), flush=True)
        else:
            print(json.dumps({"id": msg.get("id"), "result": {}}), flush=True)
    sys.exit(0)

prompt = sys.stdin.read() if not sys.stdin.isatty() and name in ("claude", "codex", "kiro-cli") else ""
if name in ("agy", "cursor-agent"):
    prompt = flag("-p", "")
model = flag("--model", "?")

if os.environ.get("FAKE_LOG"):
    with open(os.environ["FAKE_LOG"], "a") as fh:
        fh.write(json.dumps({"cli": name, "argv": [a if len(a) < 200 else a[:60] + "…" for a in args],
                             "cwd": os.getcwd(), "prompt_has_brief": "## Task brief" in prompt,
                             "prompt_has_previous": "## Previous attempt" in prompt,
                             "prompt_read_only": "READ-ONLY run" in prompt,
                             "how": next((ln for ln in prompt.splitlines() if ln.startswith("- How to work")), ""),
                             "expand": "written for a model that is given more latitude" in prompt}) + "\n")

if model in [m for m in os.environ.get("FAKE_%s_NO_MODELS" % key, "").split(",") if m]:
    text = "The model `%s` does not exist or you do not have access to it." % model
    if name == "codex":
        text = "\u25a0 The '%s' model is not supported when using Codex with a ChatGPT account." % model
    if name == "claude":
        print(json.dumps({"result": "API Error: " + text, "is_error": True}))
    else:
        sys.stderr.write("Error: " + text + "\n")
    sys.exit(1)

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
if "Generate exactly one raster image" in prompt:
    kind = os.environ.get("FAKE_%s_IMAGE" % key, "ok")
    target = next(ln.split("Save it as: ", 1)[1].strip() for ln in prompt.splitlines() if "Save it as: " in ln)
    if kind == "ok" and name == "codex":                 # codex drops it in its own folder
        d = os.path.join(os.environ["HOME"], ".codex", "generated_images", "thread-1")
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "ig_1.png"), "wb").write(PNG)
    elif kind == "ok":
        open(target, "wb").write(PNG)
    elif kind == "jpg":
        open(target, "wb").write(b"\xff\xd8\xff\xe0" + b"0" * 32)
    elif kind == "svg":                                  # cheats: draws it as text
        open(target, "w").write("<svg/>")

if mode == "slow":
    time.sleep(60)
if mode == "edit":
    open("touched-by-%s.txt" % name, "w").write("x")

answer = "%s:%s finished the task" % (name, model)
if mode == "limit":
    text = "You've hit your usage limit. Try again in 45 minutes."
    if name == "claude":
        print(json.dumps({"result": text, "is_error": True}))
    else:
        sys.stderr.write(text + "\n")
    sys.exit(1)
if mode == "error_noise":       # a failure whose log happens to talk about some other "model"
    sys.stderr.write("running tests...\nError: User model not found in database\nboom: tests crashed the CLI\n")
    sys.exit(2)
if mode == "error":
    sys.stderr.write("boom: something unrelated broke\n")
    sys.exit(2)

if name == "claude":
    print(json.dumps({"type": "result", "result": answer, "is_error": False}))
elif name == "codex":
    open(flag("-o"), "w").write(answer)
    print("noise that is not the answer")
elif name == "agy":
    print(json.dumps({"status": "OK", "response": answer}))
elif name == "cursor-agent":
    print(json.dumps({"result": answer}))
else:
    print("\x1b[32m" + answer + "\x1b[0m")
