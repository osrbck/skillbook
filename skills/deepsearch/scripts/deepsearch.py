#!/usr/bin/env python3
"""deepsearch helper: a research team of agents, sized by a degree, reviewed by the strongest model.

  detect                              which agent CLIs are installed, and the models they list
  setup [--providers a,b] [...]       save the roster: providers, models per tier, team size per degree
  roster [--md]                       who would do what, per degree
  verify [--no-web]                   ping every model in the roster and check web search; drop what fails
  init [--set key=value]              settings of this project (.deepsearch.json): folder, language, focus
  start --degree D --topic T          open a run: a folder, the team and a plan to fill in
  advance [--run DIR]                 start the next stage, or say what is left to do
  wait [--run DIR] [--timeout 540]    block until the running agents of the stage have finished
  reflect --direction D --reason R    after a cycle: conclude, or open another one (deepen | broaden | pivot)
  check [--run DIR]                   is every source of the final document one the team cited?
  status [--run DIR] | runs           bookkeeping

Stages of a cycle: research -> review -> revise (those the review sent back) and, in the first
cycle of a degree with a second panel, panel -> revise again. After a cycle the caller reflects:
conclude and write the final document, or open another cycle with new researchers, as far as the
degree allows. The run keeps a decision log (log.md) and a copy of each plan as it was run.

Workers run through the provider CLIs with web tools only: they cannot edit files or run
commands. Everything prints JSON unless noted. Python 3.8+, standard library only.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

__version__ = "0.1.0"

SCRIPT = Path(__file__).resolve()
SKILL_DIR = SCRIPT.parent.parent
TIERS = ("fast", "deep", "top")          # weakest first
TIER_PURPOSE = {"fast": "quick research", "deep": "thorough research", "top": "review, and research at the highest degree"}
DEGREES = ("low", "medium", "hard")
DIRECTIONS = ("conclude", "deepen", "broaden", "pivot")
ROLES = ("researcher", "reviewer", "writer")
EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max")
STAGES = ("research", "review", "revise", "panel", "revise2")
TERMINAL = ("done", "error", "limit", "timeout", "no_model")
MIN_CHARS = 200                          # a shorter answer is not a piece of research
ARGV_PROMPT = 30000                      # above this a prompt goes to the CLI as a file, not an argument

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")
UNKNOWN_FLAG = re.compile(r"unknown (option|argument|flag)|unexpected argument|unrecogni[sz]ed|invalid option|"
                          r"no such option|flag provided but not defined", re.I)
LIMIT_RX = re.compile(
    r"(usage|rate|weekly|session|daily|hourly)[\s_-]*limit|limit (was |has been )?(reached|exceeded|hit)|"
    r"quota[\s_]*(exceeded|exhausted|reached)|out of (credits|quota)|insufficient (credits|quota)|"
    r"too many requests|\b429\b|resource[_ ]exhausted|credit balance is too low", re.I)
MODEL_RX = re.compile(
    r"model[^\n]{0,60}(not found|does not exist|doesn't exist|not available|unavailable|not supported|"
    r"unsupported|not allowed|no access|not have access|not enabled|unknown|invalid)|"
    r"(unknown|invalid|unsupported|unrecognized) model|model_not_found|no such model|"
    r"not supported (when using|with|on|for) [^\n]{0,60}(account|plan|subscription)", re.I)

# Default model per tier, and the keywords that find the same class of model in the CLI's own
# listing (several keyword sets = order of preference; the newest listed match wins). `None`
# means the provider has no default for that tier: the listing, or `setup --model`, names one.
PROVIDERS: Dict[str, dict] = {
    "claude": {
        "label": "Claude Code", "bins": ("claude",), "sign_in": "run `claude` and use /login",
        "tiers": {"top": {"model": "fable", "effort": "high"}, "deep": {"model": "opus"}, "fast": {"model": "sonnet"}},
        "match": {},                     # its aliases always name the current model
    },
    "codex": {
        "label": "Codex", "bins": ("codex",), "sign_in": "codex login",
        "tiers": {"top": {"model": "gpt-6-astra", "effort": "high"},
                  "deep": {"model": "gpt-6-astra", "effort": "medium"},
                  "fast": {"model": "gpt-6.1-sol", "effort": "medium"}},
        "match": {"top": (("astra",),), "deep": (("astra",), ("sol",)), "fast": (("sol",), ("terra",))},
    },
    "agy": {
        "label": "Antigravity", "bins": ("agy",), "sign_in": "run `agy` once and sign in",
        "tiers": {"top": {"model": "gemini-4-argon", "effort": "high"},
                  "deep": {"model": "gemini-4-argon", "effort": "medium"},
                  "fast": {"model": "gemini-3.8-flash", "effort": "high"}},
        "match": {"top": (("karbon",), ("carbon",), ("argon",)), "deep": (("argon",), ("3.1-pro",)),
                  "fast": (("3.1-pro",), ("flash",))},
        "never": ("lite", "orchestrator"),
    },
    "kiro": {
        "label": "Kiro", "bins": ("kiro-cli",), "sign_in": "kiro-cli login",
        "tiers": {"top": None, "deep": None, "fast": {"model": "auto"}},
        "match": {"top": (("fable",), ("mythos",), ("opus",), ("astra",), ("karbon",), ("argon",)),
                  "deep": (("opus",), ("sonnet",)), "fast": (("sonnet",), ("terra",))},
    },
}
VENDOR_WORDS = (("anthropic", ("claude", "opus", "sonnet", "haiku", "fable", "mythos")),
                ("openai", ("gpt", "astra", "sol", "terra", "luna")), ("google", ("gemini",)))

DEFAULTS: dict = {
    "version": 1,
    "order": [],                         # selected providers, in priority order
    "providers": {},                     # name -> {"bin", "tiers": {fast|deep|top: {"model","effort"}|None}, "web", "unavailable"}
    "roles": {},                         # role -> provider chain, when the user set one by hand
    "degrees": {
        # tier: the researchers' models · writer: who writes the final document (none = the caller)
        # calls: searches and page reads a researcher may spend · cycles: rounds of research a run may have
        "low": {"researchers": 2, "reviewers": 1, "panel": 0, "tier": "fast", "writer": "none", "words": 800, "calls": 8, "cycles": 1},
        "medium": {"researchers": 3, "reviewers": 1, "panel": 0, "tier": "deep", "writer": "deep", "words": 1200, "calls": 12, "cycles": 2},
        "hard": {"researchers": 3, "reviewers": 1, "panel": 1, "tier": "top", "writer": "top", "words": 1800, "calls": 16, "cycles": 3},
    },
    "timeouts": {"fast": 15, "deep": 25, "top": 40},      # minutes per agent run
    "output": "research",                # where runs are written, relative to the folder you call it from
    "language": None,                    # None = the language of the request
    "link_check": True,                  # open every cited link once, without a model, before the review
}
LIMITS = {"researchers": (1, 8), "reviewers": (1, 3), "panel": (0, 3), "words": (300, 8000), "cycles": (1, 5), "calls": (3, 40)}

# The only keys a project's .deepsearch.json may set. The file arrives with the repository, so it
# may describe the project and narrow the providers; binaries, models and team sizes come from
# the user's own config only.
PROJECT_KEYS = {"output": str, "language": str, "focus": str, "citation": str,
                "prefer_sources": list, "avoid_sources": list, "allowed_providers": list}
PROJECT_HELP = {
    "output": "folder for the runs, inside this project (default: research)",
    "language": "language of every document (default: the language of the request)",
    "focus": "what this project is about, in a sentence or two; every agent is told",
    "citation": "how sources are cited, e.g. 'APA 7' or 'numbered links'",
    "prefer_sources": "kinds of sources or sites to prefer (comma separated)",
    "avoid_sources": "kinds of sources or sites to leave out (comma separated)",
    "allowed_providers": "only these providers may be used in this project (comma separated)",
}


class Stop(Exception):
    def __init__(self, error: str, text: str, **extra):
        super().__init__(text)
        self.payload = dict(ok=False, error=error, text=text, **extra)


def emit(data, code: int = 0) -> int:
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return code


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# -- config -------------------------------------------------------------------------------------

def config_path() -> Path:
    if os.environ.get("DEEPSEARCH_CONFIG"):
        return Path(os.environ["DEEPSEARCH_CONFIG"]).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(Path.home(), ".config")
    return Path(base) / "deepsearch" / "config.json"


def read_json(path: Path) -> Optional[dict]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def _merge(base: dict, extra: dict) -> dict:
    merged = dict(base)
    for k, v in extra.items():
        merged[k] = _merge(merged[k], v) if isinstance(v, dict) and isinstance(merged.get(k), dict) else v
    return merged


def project_settings(root: Path) -> Tuple[dict, List[str]]:
    """(what .deepsearch.json may contribute, the keys in it that are ignored)."""
    raw = read_json(root / ".deepsearch.json") or {}
    kept = {}
    for key, kind in PROJECT_KEYS.items():
        value = raw.get(key)
        if isinstance(value, kind) and value:
            if kind is list:
                value = [str(x)[:120] for x in value if isinstance(x, str)][:20]
            else:
                value = value.strip()[:600]
            kept[key] = value
    folder = kept.get("output")
    if folder and (os.path.isabs(folder) or ".." in Path(folder).parts):
        kept.pop("output")               # a project may not send the runs outside itself
    return kept, sorted(k for k in raw if k not in kept)


def load_config(discover: bool = False) -> dict:
    """The saved config. With `discover`, a machine that never ran `setup` gets the default roster
    for the CLIs found on it (asking each for its models, which takes a few seconds)."""
    cfg = _merge(DEFAULTS, read_json(config_path()) or {})
    cfg["_configured"] = bool(cfg.get("order"))
    cfg["_project"], cfg["_project_ignored"] = project_settings(Path.cwd())
    if discover and not cfg["_configured"]:
        for name in PROVIDERS:
            binary = find(name, cfg)
            if binary:
                tiers, unavailable = resolve(name, binary)
                cfg["providers"][name] = {"tiers": tiers, "unavailable": unavailable}
                cfg["order"].append(name)
    return cfg


def save_config(cfg: dict) -> Path:
    path = config_path()
    write_json(path, {k: v for k, v in cfg.items() if not k.startswith("_")})
    return path


# -- providers ----------------------------------------------------------------------------------

def find(name: str, cfg: dict) -> Optional[str]:
    custom = ((cfg.get("providers") or {}).get(name) or {}).get("bin")
    for cand in ([custom] if custom else []) + list(PROVIDERS[name]["bins"]):
        path = shutil.which(os.path.expanduser(cand))
        if path:
            return path
    return None


def child_env() -> dict:
    # a nested Claude Code would otherwise think it runs inside the caller's session
    return {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}


def _quick(argv: List[str], timeout: int = 20) -> Tuple[int, str]:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           encoding="utf-8", errors="replace", env=child_env(), cwd=tempfile.gettempdir())
        return p.returncode, p.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def _codex_models(binary: str) -> List[dict]:
    """Models the Codex app-server lists for this login (one JSON-RPC call over stdio)."""
    try:
        proc = subprocess.Popen([binary, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, env=child_env())
    except OSError:
        return []
    found: List[dict] = []

    def reader():
        for line in proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") == 2 and isinstance(msg.get("result"), dict):
                for value in msg["result"].values():
                    for item in value if isinstance(value, list) else []:
                        mid = isinstance(item, dict) and not item.get("hidden") and (item.get("model") or item.get("id"))
                        if isinstance(mid, str):
                            found.append({"id": mid})
                return

    try:
        for i, (method, params) in enumerate((("initialize", {"clientInfo": {"name": "deepsearch", "version": __version__}}),
                                               ("model/list", {})), 1):
            proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) + "\n")
            proc.stdin.flush()
        t = threading.Thread(target=reader, daemon=True)
        t.start()
        t.join(8)
    except (OSError, ValueError):
        pass
    finally:
        proc.kill()
    return found


def list_models(name: str, binary: str) -> List[dict]:
    """[{"id", "preview"?}] as the provider's own CLI lists them; [] when it cannot say."""
    if name == "codex":
        return _codex_models(binary)
    if name == "agy":
        code, stdout = _quick([binary, "models"])
        words = [ln.split()[0] for ln in ANSI.sub("", stdout).splitlines() if ln.split()]
        return [{"id": w} for w in words if re.match(r"^[a-z][a-z0-9.]*-[a-z0-9.\-]*\d[a-z0-9.\-]*$", w)] if code == 0 else []
    if name == "kiro":
        code, stdout = _quick([binary, "chat", "--list-models", "-f", "json"], 30)
        try:
            data = json.loads(stdout[stdout.index("{"):]) if code == 0 else {}
        except ValueError:
            return []
        rows = []
        for m in data.get("models") or []:
            mid = isinstance(m, dict) and (m.get("model_id") or m.get("model_name") or m.get("id"))
            if isinstance(mid, str):
                rows.append({"id": mid, "preview": bool(re.search(r"experimental|preview", str(m.get("description", "")), re.I))})
        return rows
    return []


def _version(model_id: str) -> Tuple:
    m = re.search(r"\d+(?:\.\d+)*", model_id)
    return tuple(int(x) for x in m.group(0).split(".")) if m else ()


def pick_model(name: str, tier: str, models: List[dict]) -> Optional[str]:
    """The newest listed model of the class this tier asks for, at the tier's effort where the
    slug carries one."""
    prov = PROVIDERS[name]
    effort = (prov["tiers"].get(tier) or {}).get("effort")
    ids = [m["id"] for m in models if not m.get("preview")
           and not any(n in m["id"].lower() for n in prov.get("never", ()))]
    for words in prov["match"].get(tier, ()):
        hits = [i for i in ids if all(w in i.lower() for w in words)]
        if hits:
            newest = max(_version(i) for i in hits)
            hits = [i for i in hits if _version(i) == newest]
            wanted = [i for i in hits if effort and i.lower().endswith("-" + effort)]
            return sorted(wanted or hits)[-1]
    return None


def resolve(name: str, binary: Optional[str]) -> Tuple[dict, dict]:
    """(tiers, unavailable): the defaults, refined against the CLI's own model listing. A default
    the listing does not have is dropped; another provider covers that tier."""
    prov = PROVIDERS[name]
    tiers = {t: (dict(prov["tiers"][t]) if prov["tiers"].get(t) else None) for t in TIERS}
    unavailable: Dict[str, str] = {}
    models = list_models(name, binary) if binary else []
    ids = [m["id"] for m in models]
    if not ids:
        return tiers, unavailable
    for tier in TIERS:
        default = tiers[tier]
        best = pick_model(name, tier, models)
        if best:
            spec = {**(default or {}), "model": best}
            if any(best.lower().endswith("-" + e) for e in EFFORTS):
                spec.pop("effort", None)                  # the slug already says it
            if name == "codex" and tier == "deep" and "astra" not in best.lower():
                spec["effort"] = "high"                   # a smaller model standing in: give it full effort
            tiers[tier] = spec
        elif default and default["model"] not in ids and default["model"] != "auto":
            unavailable[tier] = default["model"]
            tiers[tier] = None
    return tiers, unavailable


def vendor(provider: str, model: str) -> str:
    """Whose model this is, for the rule that a reviewer should not share a vendor with the
    researchers where there is a choice. Kiro and others resell models, so the slug decides."""
    low = (model or "").lower()
    for name, words in VENDOR_WORDS:
        if any(w in low for w in words):
            return name
    return provider


def commands(name: str, binary: str, spec: dict, prompt: str, cwd: str, out_file: str) -> List[Tuple[List[str], Optional[str]]]:
    """Ways to ask this CLI one question with web tools and nothing else, newest flags first.
    The next one is tried only when the CLI says it does not know a flag."""
    model, effort = spec["model"], spec.get("effort")
    in_slug = any(model.lower().endswith("-" + e) for e in EFFORTS)
    eff = effort if effort and not in_slug and model != "auto" else None
    if name == "claude":
        head = [binary, "-p", "--model", model, "--output-format", "json"]
        web = ["--tools", "WebSearch,WebFetch", "--allowedTools", "WebSearch,WebFetch"]
        old = ["--allowedTools", "WebSearch,WebFetch", "--disallowedTools", "Bash,Edit,Write,MultiEdit,NotebookEdit"]
        e = ["--effort", eff] if eff else []
        tries = [head + e + web, head + web, head + old]
        return [(a, prompt) for a in tries]
    if name == "codex":
        e = ["-c", 'model_reasoning_effort="%s"' % eff] if eff else []
        tail = ["--model", model] + e + ["--sandbox", "read-only", "--skip-git-repo-check", "-C", cwd, "-o", out_file, "-"]
        return [([binary, "--search", "exec"] + tail, prompt),
                ([binary, "exec", "-c", "tools.web_search=true"] + tail, prompt),
                ([binary, "exec"] + tail, prompt)]
    if name == "agy":
        text = prompt
        if len(prompt) > ARGV_PROMPT:                     # too long for an argument: hand it over as a file
            Path(cwd, "PROMPT.md").write_text(prompt, encoding="utf-8")
            text = "Read the file PROMPT.md in the current folder and do exactly what it says. Your answer is the document it asks for."
        head = [binary, "-p", text, "--model", model, "--output-format", "json"]
        return [(head + ["--effort", eff], None), (head, None)] if eff else [(head, None)]
    if name == "kiro":
        head = [binary, "chat", "--no-interactive", "--model", model]
        e = ["--effort", eff] if eff else []
        return [(head + e + ["--trust-tools=*web*,web_search,web_fetch"], prompt),
                (head + ["--trust-tools=web_search,web_fetch"], prompt)]
    raise Stop("unknown-provider", "unknown provider: %s" % name)


def _last_json(text: str) -> Optional[dict]:
    text = (text or "").strip()
    for line in [text] + list(reversed(text.splitlines())):
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    return data
            except ValueError:
                continue
    return None


def final(name: str, stdout: str, out_file: str) -> Tuple[str, bool]:
    """(the CLI's final message, it reported an error)."""
    if name == "codex":
        try:
            return Path(out_file).read_text(encoding="utf-8", errors="replace").strip(), False
        except OSError:
            return "", False
    if name == "kiro":
        text = ANSI.sub("", stdout or "").strip()
        return re.sub(r"^>\s+", "", text), False
    data = _last_json(stdout)
    if data is None:
        return ANSI.sub("", stdout or "").strip(), False
    if name == "claude":
        return str(data.get("result") or "").strip(), bool(data.get("is_error"))
    failed = str(data.get("status", "")).upper() == "ERROR"
    text = data.get("response") or data.get("result")
    if failed and not text:
        text = data.get("error") or data.get("message") or json.dumps(data, ensure_ascii=False)
    return str(text or "").strip(), failed


def _run(argv: List[str], stdin: Optional[str], cwd: str, timeout: int) -> Tuple[int, str, str, bool]:
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, text=True,
                                encoding="utf-8", errors="replace", start_new_session=True, env=child_env())
    except OSError as e:
        return 127, "", str(e), False
    try:
        stdout, stderr = proc.communicate(stdin, timeout=timeout)
        return proc.returncode, stdout or "", stderr or "", False
    except subprocess.TimeoutExpired:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, sig)
                proc.wait(10)
                break
            except (OSError, subprocess.TimeoutExpired):
                continue
        return 124, "", "", True


def strip_fence(text: str) -> str:
    """A model sometimes wraps the whole document in one code fence, or says a sentence before
    it ("Research done, writing the notes now"); the file should hold the document only."""
    m = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", text.strip(), re.S)
    text = (m.group(1) if m else text).strip()
    title = re.search(r"^# \S", text, re.M)
    if title and 0 < title.start() < 600 and "\n#" not in text[:title.start()]:
        text = text[title.start():]
    return text.strip()


def ask(name: str, binary: str, spec: dict, prompt: str, cwd: str, timeout: int, log: Optional[Path] = None) -> dict:
    """One question to one model. {"outcome": done|limit|model|timeout|error, "text", "error"}."""
    out_file = os.path.join(cwd, "last-message.txt")
    code, stdout, stderr, timed_out = 1, "", "", False
    for argv, stdin in commands(name, binary, spec, prompt, cwd, out_file):
        code, stdout, stderr, timed_out = _run(argv, stdin, cwd, timeout)
        if log:
            log.write_text("$ %s\n\n-- stdout --\n%s\n-- stderr --\n%s\n" % (
                " ".join(a if len(a) < 200 else a[:80] + "…" for a in argv), stdout[-20000:], stderr[-8000:]),
                encoding="utf-8")
        if timed_out or code == 0 or not UNKNOWN_FLAG.search(stderr + stdout[-2000:]):
            break
    if timed_out:
        return {"outcome": "timeout", "error": "no answer within %d minutes" % (timeout // 60)}
    text, reported = final(name, stdout, out_file)
    if code == 0 and not reported and text.strip():
        return {"outcome": "done", "text": strip_fence(text)}
    evidence = "\n".join([stderr[-3000:], stdout[-3000:], text[:2000]])
    m = LIMIT_RX.search(evidence)
    if m:
        return {"outcome": "limit", "error": next((ln for ln in evidence.splitlines() if m.group(0) in ln), m.group(0)).strip()[:300]}
    for line in reversed(evidence.splitlines()[-200:]):
        low = line.lower()
        if MODEL_RX.search(line) and (spec["model"].lower() in low or re.search(r"account|plan|subscription|access", low)):
            return {"outcome": "model", "error": line.strip()[:300]}
    tail = " ".join((ANSI.sub("", stderr).strip() or text or stdout.strip() or "no output").split())[-400:]
    return {"outcome": "error", "error": "%s exited with code %s: %s" % (PROVIDERS[name]["label"], code, tail)}


# -- the team -----------------------------------------------------------------------------------

def usable(cfg: dict, role: str) -> List[str]:
    """Providers this role may run on, best first: the user's order (or the chain set for the
    role), with those that cannot search the web at the back."""
    provs = cfg.get("providers") or {}
    allowed = (cfg.get("_project") or {}).get("allowed_providers")
    order = [p for p in (cfg.get("roles") or {}).get(role) or cfg.get("order") or []
             if p in PROVIDERS and p in provs and (not allowed or p in allowed)]
    return sorted(order, key=lambda p: provs[p].get("web") is False)


def candidates(cfg: dict, role: str, tier: str) -> List[dict]:
    """Every (provider, model) this role may run on: its own tier on each provider first, then
    the nearest tier that exists (weaker before stronger, so a missing model never costs more)."""
    idx = TIERS.index(tier)
    order = [tier] + [TIERS[i] for i in range(idx - 1, -1, -1)] + list(TIERS[idx + 1:])
    found, seen = [], set()
    for t in order:
        for p in usable(cfg, role):
            spec = ((cfg["providers"][p].get("tiers") or {}).get(t)) or None
            if not spec or not spec.get("model"):
                continue
            key = (p, spec["model"], spec.get("effort"))
            if key in seen:
                continue
            seen.add(key)
            found.append({"provider": p, "tier": t, "model": spec["model"], "effort": spec.get("effort"),
                          "vendor": vendor(p, spec["model"]), **({"wanted": tier} if t != tier else {})})
    return found


def team(cfg: dict, degree: str, researchers: Optional[int] = None) -> List[dict]:
    """Who does what at this degree. Researchers are spread over the providers that have the
    degree's tier. Reviewers always run on the strongest tier: the first on the user's first
    provider that has such a model, each further one on a vendor no earlier reviewer used, where
    there is a choice. The writer, where the degree has one, comes last and belongs to no cycle."""
    d = cfg["degrees"][degree]
    agents: List[dict] = []

    def seat(agent: str, role: str, chain: List[dict], first: int, cycle: int = 1) -> None:
        if not chain:
            agents.append({"agent": agent, "role": role, "cycle": cycle, "chain": []})
            return
        pool = [c for c in chain if c["tier"] == chain[0]["tier"]]
        lead = pool[first % len(pool)]
        agents.append({"agent": agent, "role": role, "cycle": cycle, "chain": [lead] + [c for c in chain if c is not lead]})

    chain = candidates(cfg, "researcher", d["tier"])
    for i in range(researchers or d["researchers"]):
        seat("researcher-%d" % (i + 1), "researcher", chain, i)
    chain = candidates(cfg, "reviewer", "top")
    pool = [c for c in chain if c["tier"] == chain[0]["tier"]] if chain else []
    seats = [("reviewer-%d" % (i + 1)) for i in range(d["reviewers"])] + [("panel-%d" % (i + 1)) for i in range(d["panel"])]
    vendors: List[str] = []
    taken: List[int] = []
    for i, agent in enumerate(seats):
        fresh = [n for n in range(len(pool)) if pool[n]["vendor"] not in vendors] or \
                [n for n in range(len(pool)) if n not in taken]
        first = fresh[0] if fresh else i
        if pool:
            taken.append(first % len(pool))
            vendors.append(pool[first % len(pool)]["vendor"])
        seat(agent, "reviewer", chain, first)
    if d.get("writer") in TIERS:
        seat("writer-1", "writer", candidates(cfg, "writer", d["writer"]), 0, cycle=0)
    return agents


def describe(agent: dict) -> dict:
    if not agent["chain"]:
        return {"agent": agent["agent"], "runs": "you (no provider CLI is usable for it)"}
    c = agent["chain"][0]
    row = {"agent": agent["agent"], "provider": c["provider"],
           "model": c["model"] + ("@" + c["effort"] if c.get("effort") else ""), "tier": c["tier"]}
    if c.get("wanted"):
        row["note"] = "no %s model on your accounts; runs on %s" % (c["wanted"], c["tier"])
    return row


# -- a run --------------------------------------------------------------------------------------

def slugify(text: str) -> str:
    text = text.replace("ı", "i").replace("İ", "I").replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48].strip("-") or "research"


def output_base(cfg: dict) -> Path:
    folder = (cfg.get("_project") or {}).get("output") or cfg.get("output") or "research"
    return (Path.cwd() / Path(folder).expanduser()).resolve()


def find_run(cfg: dict, given: Optional[str]) -> Path:
    if given:
        run = Path(given).expanduser().resolve()
        if not (run / ".work" / "crew.json").is_file():
            raise Stop("no-run", "%s is not a run folder." % run)
        return run
    base = output_base(cfg)
    runs = sorted((d for d in base.glob("*") if (d / ".work" / "crew.json").is_file()),
                  key=lambda d: (d / ".work" / "crew.json").stat().st_mtime) if base.is_dir() else []
    if not runs:
        raise Stop("no-run", "No run in %s. Start one with: start --degree <low|medium|hard> --topic '<topic>'" % base)
    return runs[-1]


PLACEHOLDER = "[["
SECTION = re.compile(r"^## +((?:researcher|reviewer|panel)-\d+)\s*$", re.M)


def plan_skeleton(topic: str, agents: List[dict], language: Optional[str]) -> str:
    parts = ["# %s" % topic, "",
             "Language: %s" % (language or "[[the language of the user's request, in English: Turkish, English, …]]"), "",
             "## Question", "[[The research question in one or two precise sentences.]]", "",
             "## Scope",
             "[[What is in and what is out: period, region, field, depth; what the user will do with the answer.]]", "",
             "## Key terms", "[[Definitions the whole team must share. Delete this section when none are needed.]]", ""]
    for a in agents:
        parts += agent_section(a)
    return "\n".join(parts)


def agent_section(a: dict) -> List[str]:
    if a["role"] == "researcher":
        return ["## %s" % a["agent"],
                "Persona: [[An acclaimed master researcher of the field this angle belongs to: field, speciality, "
                "what they are known for. A role, never a real person's name.]]",
                "Angle: [[The part of the question this researcher owns, as an objective: what their notes must cover.]]",
                "Not yours: [[What the other researchers cover, so that this one leaves it alone.]]",
                "Sources: [[The kinds of source to start from: which registries, journals, filings, datasets, vendors' docs.]]",
                "Hypothesis: [[The answer you expect on this angle and why, and what evidence would refute it.]]",
                "Questions:", "- [[A concrete question to answer]]", "- [[…]]", ""]
    return ["## %s" % a["agent"],
            "Persona: [[A professor who wrote the standard book on this topic and has reviewed the field "
            "for decades: field, what they are strict about. A role, never a real person's name.]]", ""]


def read_plan(run: Path) -> Tuple[str, Dict[str, str]]:
    """(what everybody is told, the section of each agent)."""
    text = (run / "plan.md").read_text(encoding="utf-8")
    marks = list(SECTION.finditer(text))
    head = text[:marks[0].start()].strip() if marks else text.strip()
    sections = {m.group(1): text[m.end():(marks[i + 1].start() if i + 1 < len(marks) else len(text))].strip()
                for i, m in enumerate(marks)}
    return head, sections


def load_crew(run: Path) -> dict:
    return read_json(run / ".work" / "crew.json") or {}


def load_state(run: Path) -> dict:
    return {"cycle": 1, "stage": 0, "started": False, "agents": [], **(read_json(run / ".work" / "state.json") or {})}


def seats(crew: dict, kind: str, cycle: Optional[int] = None) -> List[str]:
    return [a["agent"] for a in crew["agents"] if a["agent"].startswith(kind)
            and (cycle is None or a.get("cycle", 1) == cycle)]


def logline(run: Path, text: str) -> None:
    """One line in the run's decision log: what happened and when, for whoever picks the run up later."""
    path = run / "log.md"
    if not path.exists():
        path.write_text("# Log\n\n", encoding="utf-8")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("- %s  %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M"), text))


def agent_dir(run: Path, agent: str, stage: str) -> Path:
    return run / ".work" / "runs" / ("%s.%s" % (agent, stage))


def meta_of(run: Path, agent: str, stage: str) -> dict:
    return read_json(agent_dir(run, agent, stage) / "meta.json") or {}


def out_path(run: Path, agent: str) -> Path:
    if agent.startswith("writer"):
        return run / "report.md"
    return run / ("findings" if agent.startswith("researcher") else "reviews") / (agent + ".md")


def agent_status(run: Path, agent: str, stage: str) -> dict:
    meta = meta_of(run, agent, stage)
    if meta.get("status") == "you":                       # the caller writes it; done once the file is there
        path = Path(meta["out"])
        fresh = path.is_file() and path.stat().st_mtime > meta.get("since", 0) and len(path.read_text(encoding="utf-8", errors="replace")) >= MIN_CHARS
        if fresh:
            meta["status"] = "done"
    return meta


def row(meta: dict) -> dict:
    keys = ("agent", "stage", "status", "provider", "model", "minutes", "error")
    r = {k: meta[k] for k in keys if meta.get(k) not in (None, "")}
    if len(meta.get("attempts") or []) > 1:
        r["attempts"] = meta["attempts"]
    return r


VERDICT = re.compile(r"^\W*VERDICT\W+(researcher-\d+)\W+(accept|revise)\b", re.I | re.M)


def verdicts(run: Path, reviewers: List[str], researchers: List[str]) -> Dict[str, str]:
    """accept or revise per researcher. Any reviewer asking for a revision is enough, and a
    researcher no reviewer ruled on is sent back too: silence is not approval."""
    found: Dict[str, str] = {}
    read_any = False
    for r in reviewers:
        path = out_path(run, r)
        if not path.is_file():
            continue
        read_any = True
        for who, what in VERDICT.findall(path.read_text(encoding="utf-8", errors="replace")):
            who, what = who.lower(), what.lower()
            found[who] = "revise" if "revise" in (what, found.get(who)) else "accept"
    if not read_any:
        return {}
    return {r: found.get(r, "revise") for r in researchers}


def cycle_stages(crew: dict, cycle: int) -> List[str]:
    """The second panel sits once, on the first cycle: later cycles are smaller and reviewed once."""
    return list(STAGES if crew["settings"].get("panel") and cycle == 1 else STAGES[:3])


def is_final(crew: dict, state: dict) -> bool:
    """No further cycle will follow this one: the caller concluded, or the degree's cycles are used."""
    return bool(state.get("concluded")) or int(crew["settings"].get("cycles", 1)) - state["cycle"] <= 0


def stage_plan(crew: dict, state: dict) -> List[str]:
    stages = cycle_stages(crew, state["cycle"])
    if is_final(crew, state) and seats(crew, "writer"):
        stages.append("write")
    return stages


def stage_agents(run: Path, crew: dict, stage: str, cycle: int = 1) -> List[str]:
    if stage == "research":
        return seats(crew, "researcher", cycle)
    if stage == "write":
        return seats(crew, "writer")
    if stage == "review":
        return seats(crew, "reviewer", cycle)
    if stage == "panel":
        return seats(crew, "panel", cycle)
    researchers = [n for n in seats(crew, "researcher", cycle) if out_path(run, n).is_file()]
    judges = seats(crew, "reviewer" if stage == "revise" else "panel", cycle)
    return [r for r, v in verdicts(run, judges, researchers).items() if v == "revise"]


def all_verdicts(run: Path, crew: dict) -> Dict[str, str]:
    """Where every researcher stands after the last review that ruled on them."""
    found: Dict[str, str] = {}
    for cycle in sorted({a.get("cycle", 1) for a in crew["agents"]}):
        mine = seats(crew, "researcher", cycle)
        found.update(verdicts(run, seats(crew, "panel", cycle) or seats(crew, "reviewer", cycle), mine))
    return found


def role_text(name: str) -> str:
    return (SKILL_DIR / "roles" / (name + ".md")).read_text(encoding="utf-8").strip()


URL = re.compile(r"https?://[^\s<>\]\[)\"'`]+")


def urls_in(path: Path) -> set:
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    return {u.rstrip(".,;:!?*_") for u in URL.findall(text)}


def _public(host: Optional[str]) -> bool:
    """A link check must not become a way to reach this machine or its network."""
    if not host:
        return False
    if os.environ.get("DEEPSEARCH_ALLOW_LOCAL"):          # tests only
        return True
    try:
        addrs = {i[4][0] for i in socket.getaddrinfo(host, None)}
    except OSError:
        return True                                       # does not resolve: the request will say so
    return not any(ipaddress.ip_address(a.split("%")[0]).is_private or ipaddress.ip_address(a.split("%")[0]).is_loopback
                   or ipaddress.ip_address(a.split("%")[0]).is_link_local for a in addrs)


class _NoPrivateRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _public(urllib.parse.urlparse(newurl).hostname):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def link_status(url: str, timeout: int = 8) -> str:
    """ok · dead (the page is not there) · unverified (the site would not say). No model involved."""
    if not _public(urllib.parse.urlparse(url).hostname):
        return "unverified"
    opener = urllib.request.build_opener(_NoPrivateRedirect())
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={
            "User-Agent": "Mozilla/5.0 (compatible; link-check)", "Accept": "*/*", "Range": "bytes=0-2047"})
        try:
            with opener.open(req, timeout=timeout) as resp:
                return "ok" if resp.status < 400 else "unverified"
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return "dead"
            if method == "HEAD":
                continue                                  # many sites refuse HEAD: ask properly
            return "unverified"
        except urllib.error.URLError as e:
            return "dead" if isinstance(e.reason, socket.gaierror) else "unverified"
        except (OSError, ValueError):
            return "unverified"
    return "unverified"


def check_links(run: Path, crew: dict, paths: List[Path]) -> Dict[str, str]:
    """Open every link of these documents once and remember the answer in the run."""
    store = run / ".work" / "links.json"
    known = read_json(store) or {}
    if not crew.get("link_check", True) or os.environ.get("DEEPSEARCH_OFFLINE"):
        return known
    new = sorted({u for p in paths for u in urls_in(p)} - set(known))[:400]
    if new:
        with ThreadPoolExecutor(max_workers=12) as pool:
            known.update(zip(new, pool.map(link_status, new)))
        write_json(store, known)
    return known


def dead_links(run: Path, path: Path) -> List[str]:
    known = read_json(run / ".work" / "links.json") or {}
    return sorted(u for u in urls_in(path) if known.get(u) == "dead")


HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def without_blocks(text: str, drop) -> str:
    """The document minus every section whose heading `drop` matches (with what is under it)."""
    kept, skipping = [], 0
    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            level = len(m.group(1))
            if skipping and level <= skipping:
                skipping = 0
            if not skipping and drop(m.group(2).lower()):
                skipping = level
        if not skipping:
            kept.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def write_digest(run: Path, crew: dict, cycle: int) -> Path:
    """What the caller needs to decide the next step, cut from the documents without a model:
    each researcher's takeaways, hypothesis and gaps (not the findings behind them), and each
    review without its point-by-point lists. A fraction of the full text."""
    parts = ["# Digest of cycle %d\n\nCut mechanically from the documents; the full texts are in findings/ and reviews/." % cycle]
    for n in seats(crew, "researcher", cycle):
        if out_path(run, n).is_file():
            text = out_path(run, n).read_text(encoding="utf-8", errors="replace")
            parts.append("===== %s =====\n%s" % (n, without_blocks(text, lambda h: h.startswith(("cited findings", "inferences", "changes")))))
    for n in seats(crew, "reviewer", cycle) + seats(crew, "panel", cycle):
        if out_path(run, n).is_file():
            text = out_path(run, n).read_text(encoding="utf-8", errors="replace")
            parts.append("===== %s =====\n%s" % (n, without_blocks(text, lambda h: h.startswith("researcher-"))))
    path = run / "digest.md"
    path.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    return path


def build_prompt(run: Path, crew: dict, agent: str, stage: str) -> str:
    head, sections = read_plan(run)
    cycle = next(a.get("cycle", 1) for a in crew["agents"] if a["agent"] == agent)
    settings = crew["settings"]
    words = settings["words"]
    language = crew.get("language") or (re.search(r"^Language:\s*(.+)$", head, re.M) or [None, "the language of the plan"])[1]
    proj = crew.get("project") or {}
    notes = []
    if proj.get("focus"):
        notes.append("Context of the project this research is for: %s" % proj["focus"])
    if proj.get("prefer_sources"):
        notes.append("Prefer these sources: %s" % ", ".join(proj["prefer_sources"]))
    if proj.get("avoid_sources"):
        notes.append("Leave these sources out: %s" % ", ".join(proj["avoid_sources"]))
    if proj.get("citation"):
        notes.append("Cite sources as: %s" % proj["citation"])

    def doc(title: str, path: Path) -> str:
        return "===== %s =====\n%s\n===== end of %s =====" % (title, path.read_text(encoding="utf-8", errors="replace").strip(), title)

    def docs(kind: str, every: bool = False) -> List[str]:
        return [doc(n, out_path(run, n)) for n in seats(crew, kind, None if every else cycle) if out_path(run, n).is_file()]

    def broken(kind: str) -> str:
        rows = ["- %s: %s" % (n, ", ".join(dead_links(run, out_path(run, n))))
                for n in seats(crew, kind, cycle) if dead_links(run, out_path(run, n))]
        return ("LINK CHECK (automatic, no model involved): these cited links did not open (the page does not exist)."
                "\n\n" + "\n".join(rows)) if rows else ""

    findings, first_reviews, panel_reviews = docs("researcher"), docs("reviewer"), docs("panel")
    parts: List[str] = []
    if stage == "research":
        parts += [role_text("researcher")]
    elif stage in ("revise", "revise2"):
        parts += [role_text("researcher"), role_text("revise")]
    elif stage == "write":
        parts += [role_text("writer")]
    else:
        parts += [role_text("reviewer")] + ([role_text("panel")] if stage == "panel" else [])
    parts += ["THE RESEARCH PLAN (shared by the whole team)\n\n" + head]
    if notes:
        parts += ["PROJECT NOTES\n\n" + "\n".join("- " + n for n in notes)]
    earlier = Path(crew["earlier"]) if crew.get("earlier") else None
    if earlier and earlier.is_file() and stage in ("research", "write"):
        parts += ["EARLIER RESEARCH ON THIS TOPIC (already delivered to the user: build on it, and look again only at "
                  "what the plan asks)\n\n" + earlier.read_text(encoding="utf-8", errors="replace").strip()[:24000]]
    memo = run / "notes.md"
    if memo.is_file() and (stage == "write" or (cycle > 1 and stage == "research")):
        parts += ["WHAT THE TEAM HAS ESTABLISHED SO FAR (the orchestrator's notes on the reviewed research%s)\n\n"
                  % ("" if stage == "write" else ": build on it, do not repeat it")
                  + memo.read_text(encoding="utf-8", errors="replace").strip()]
    if stage == "write":
        ran = ["- %s: %s on %s" % (r["agent"], r["stage"], r.get("model") or "the orchestrator") for r in summary(run, crew)
               if r.get("status") == "done"]
        log = run / "log.md"
        decided = [ln.strip() for ln in (log.read_text(encoding="utf-8").splitlines() if log.is_file() else []) if "reflect:" in ln]
        parts += ["THE RESEARCH (as it stands after review and revision)\n\n" + "\n\n".join(docs("researcher", True)),
                  "THE REVIEWS\n\n" + "\n\n".join(docs("reviewer", True) + docs("panel", True)),
                  "HOW THIS WAS RESEARCHED (facts for that section)\n\nDegree: %s\n%s%s" % (
                      crew.get("degree"), "\n".join(ran), ("\nDecisions:\n" + "\n".join(decided)) if decided else "")]
        parts += ["LIMITS\n\n- Write in %s.\n- As long as the answer needs, usually around %d words.\n- Your whole answer "
                  "is the document: start with its title, no greeting and no closing remark." % (language, words * 2)]
        return "\n\n---\n\n".join(parts) + "\n"
    parts += ["YOUR ASSIGNMENT: you are %s\n\n%s" % (agent, sections.get(agent, ""))]
    if stage in ("revise", "revise2"):
        own = out_path(run, agent)
        parts += ["YOUR EARLIER DOCUMENT\n\n" + doc(agent, own)]
        parts += ["THE REVIEW YOU ANSWER\n\n" + "\n\n".join(panel_reviews if stage == "revise2" else first_reviews)]
        gone = dead_links(run, own)
        if gone:
            parts += ["LINK CHECK (automatic): these links of yours did not open. Replace or drop them.\n\n" + "\n".join("- " + u for u in gone)]
    elif stage == "review":
        parts += ["THE RESEARCH TO REVIEW\n\n" + "\n\n".join(findings)] + ([broken("researcher")] if broken("researcher") else [])
    elif stage == "panel":
        parts += ["THE FIRST REVIEW\n\n" + "\n\n".join(first_reviews),
                  "THE RESEARCH AS IT STANDS AFTER THAT REVIEW\n\n" + "\n\n".join(findings)] + ([broken("researcher")] if broken("researcher") else [])
    limits = ["Write in %s; keep the section headings of the template exactly as they are, in English." % language]
    if agent.startswith("researcher"):
        limits += ["At most %d words." % words,
                   "About %d searches and page reads in all. Stop earlier when your questions are answered or nothing new "
                   "turns up; do not go past it to be thorough." % int(settings.get("calls", 12))]
    else:
        limits += ["At most %d words." % max(400, words // 2),
                   "Open about three sources per researcher, more only where a conclusion hangs on one."]
    limits += ["Your whole answer is the document: start with its first heading, no greeting and no closing remark."]
    parts += ["LIMITS\n\n" + "\n".join("- " + x for x in limits)]
    return "\n\n---\n\n".join(parts) + "\n"


def launch(run: Path, crew: dict, agent: str, stage: str, cfg: dict) -> dict:
    """Start one agent in the background, or hand its prompt to the caller when no CLI can run it."""
    seat = next(a for a in crew["agents"] if a["agent"] == agent)
    d = agent_dir(run, agent, stage)
    (d / "cwd").mkdir(parents=True, exist_ok=True)
    out = out_path(run, agent)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.is_file():                                     # a revision replaces it: keep what it replaces
        history = run / ".work" / "history"
        history.mkdir(exist_ok=True)
        shutil.copy2(out, history / ("%s.before-%s.md" % (agent, stage)))
    (d / "prompt.md").write_text(build_prompt(run, crew, agent, stage), encoding="utf-8")
    chain = [c for c in seat["chain"] if find(c["provider"], cfg)]
    tier = chain[0]["tier"] if chain else "top"
    meta = {"agent": agent, "stage": stage, "role": seat["role"], "out": str(out), "chain": chain,
            "timeout_minutes": int(crew["timeouts"].get(tier, 30)), "created": now(), "since": time.time(),
            "status": "queued" if chain else "you", "attempts": []}
    write_json(d / "meta.json", meta)
    if not chain:
        return {"agent": agent, "runs": "you", "prompt_file": str(d / "prompt.md"), "save_to": str(out)}
    with open(d / "runner.log", "w") as log:
        subprocess.Popen([sys.executable, str(SCRIPT), "_exec", str(run), agent, stage], stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, start_new_session=True, cwd=str(run))
    c = chain[0]
    return {"agent": agent, "provider": c["provider"], "model": c["model"] + ("@" + c["effort"] if c.get("effort") else ""),
            "timeout_minutes": meta["timeout_minutes"]}


def execute(run: Path, agent: str, stage: str) -> None:
    """Runs in the detached child: try the agent's providers in order until one answers."""
    d = agent_dir(run, agent, stage)
    meta = read_json(d / "meta.json") or {}
    cfg = load_config()                                   # only to find a binary the user configured
    prompt = (d / "prompt.md").read_text(encoding="utf-8")
    started = time.time()

    def finish(status: str, **extra):
        meta.update(status=status, finished=now(), minutes=round((time.time() - started) / 60, 1), **extra)
        write_json(d / "meta.json", meta)

    last = "no provider CLI is installed for this agent"
    for n, c in enumerate(meta.get("chain") or [], 1):
        binary = find(c["provider"], cfg)
        if not binary:
            continue
        meta.update(status="running", provider=c["provider"], model=c["model"], effort=c.get("effort"), tier=c["tier"])
        write_json(d / "meta.json", meta)
        res = ask(c["provider"], binary, c, prompt, str(d / "cwd"), meta["timeout_minutes"] * 60, d / ("cli.%d.log" % n))
        if res["outcome"] == "done" and len(res["text"]) < MIN_CHARS:
            res = {"outcome": "error", "error": "the answer was only %d characters" % len(res["text"])}
        meta["attempts"].append({"provider": c["provider"], "model": c["model"], "outcome": res["outcome"]})
        if res["outcome"] == "done":
            Path(meta["out"]).write_text(res["text"].strip() + "\n", encoding="utf-8")
            return finish("done")
        last = res.get("error") or res["outcome"]
        if res["outcome"] == "timeout":
            return finish("timeout", error=last)          # a second model would take as long again
    outcomes = {a["outcome"] for a in meta["attempts"]}
    finish("limit" if outcomes == {"limit"} else "no_model" if outcomes == {"model"} else "error", error=last)


# -- commands -----------------------------------------------------------------------------------

def cmd_detect(args, cfg) -> int:
    rows = []
    for name, prov in PROVIDERS.items():
        binary = find(name, cfg)
        info = {"name": name, "label": prov["label"], "installed": bool(binary), "path": binary, "sign_in": prov["sign_in"]}
        if binary:
            code, text = _quick([binary, "--version"], 10)
            info["version"] = (ANSI.sub("", text).strip().splitlines() or [None])[0]
            tiers, unavailable = resolve(name, binary)
            info["tiers"], info["unavailable"] = tiers, unavailable
        rows.append(info)
    return emit({"version": __version__, "config": str(config_path()), "configured": cfg["_configured"], "providers": rows})


def roster_payload(cfg: dict) -> dict:
    provs = []
    for name in cfg.get("order") or []:
        entry = cfg["providers"].get(name) or {}
        provs.append({"name": name, "label": PROVIDERS[name]["label"], "installed": bool(find(name, cfg)),
                      "web": entry.get("web"), "tiers": {t: (entry.get("tiers") or {}).get(t) for t in TIERS},
                      "unavailable": entry.get("unavailable") or {}})
    degrees = {}
    for degree in DEGREES:
        agents = team(cfg, degree)
        degrees[degree] = {**cfg["degrees"][degree], "agents": len(agents), "team": [describe(a) for a in agents]}
    notes = []
    if not cfg["_configured"]:
        notes.append("No setup was saved: this is the default roster for the CLIs found on this machine.")
    if not cfg.get("order"):
        notes.append("No provider CLI was found. Research still runs: the calling agent plays every role itself, "
                     "one after another, which is slower and less independent.")
    for p in provs:
        if not p["installed"]:
            notes.append("%s is in the roster but its CLI is not on PATH." % p["label"])
        if p["web"] is False:
            notes.append("%s could not search the web when it was verified; it is used last." % p["label"])
        for tier, model in sorted(p["unavailable"].items()):
            notes.append("%s: %s (%s) is not available on this account; other providers cover it." % (p["label"], model, tier))
    if cfg.get("_project_ignored"):
        notes.append("Ignored keys in .deepsearch.json: %s (a project file may set only: %s)."
                     % (", ".join(cfg["_project_ignored"]), ", ".join(PROJECT_KEYS)))
    return {"providers": provs, "degrees": degrees, "timeouts": cfg["timeouts"], "output": str(output_base(cfg)),
            "language": (cfg.get("_project") or {}).get("language") or cfg.get("language"),
            "project": cfg.get("_project") or {}, "notes": notes}


def roster_md(p: dict) -> str:
    def spec(s):
        return "–" if not s else s["model"] + ("@" + s["effort"] if s.get("effort") else "")
    lines = ["**Models**", "", "| Provider | fast | deep | top | web |", "|---|---|---|---|---|"]
    for pr in p["providers"]:
        web = {True: "yes", False: "no", None: "not checked"}[pr["web"]]
        lines.append("| %s | %s | %s | %s | %s |" % (pr["label"], spec(pr["tiers"]["fast"]), spec(pr["tiers"]["deep"]), spec(pr["tiers"]["top"]), web))
    lines += ["", "**Teams**", "", "| Degree | Agents | Researchers | Reviewers | Writer | Cycles |", "|---|---|---|---|---|---|"]
    for degree in DEGREES:
        d = p["degrees"][degree]
        res = [t for t in d["team"] if t["agent"].startswith("researcher")]
        rev = [t for t in d["team"] if t["agent"].startswith(("reviewer", "panel"))]
        wri = [t for t in d["team"] if t["agent"].startswith("writer")]
        fmt = lambda rows: ", ".join(sorted({"%s:%s" % (t["provider"], t["model"]) if t.get("provider") else "you" for t in rows}))  # noqa: E731
        lines.append("| %s | %d | %d × %s | %d × %s%s | %s | %d |" % (
            degree, d["agents"], len(res), fmt(res) or "–", len(rev), fmt(rev) or "–",
            " (%d of them a second panel)" % d["panel"] if d["panel"] else "", fmt(wri) or "you", d["cycles"]))
    if p["notes"]:
        lines += [""] + ["- " + n for n in p["notes"]]
    lines += ["", "To change who does what, ask in plain words, for example \"/deepsearch let Codex review\" or "
              "\"/deepsearch use five researchers at hard\"."]
    return "\n".join(lines)


def cmd_roster(args, cfg) -> int:
    payload = roster_payload(cfg)
    if args.md:
        print(roster_md(payload))
        return 0
    return emit(payload)


def _pairs(values: List[str], what: str) -> List[Tuple[str, str]]:
    pairs = []
    for item in values or []:
        if "=" not in item:
            raise Stop("bad-argument", "%s wants key=value, got: %s" % (what, item))
        k, v = item.split("=", 1)
        pairs.append((k.strip(), v.strip()))
    return pairs


def cmd_setup(args, cfg) -> int:
    known = cfg["_configured"]
    names = [n.strip() for n in args.providers.split(",") if n.strip()] if args.providers else list(cfg.get("order") or [])
    bad = [n for n in names if n not in PROVIDERS]
    if bad:
        raise Stop("unknown-provider", "Unknown provider: %s (known: %s)" % (", ".join(bad), ", ".join(PROVIDERS)))
    if not names:
        raise Stop("no-provider", "No provider CLI was found on PATH. Install one of: claude, codex, agy, kiro-cli. "
                   "Without one, the calling agent plays every role itself.")
    providers = {}
    for name in names:
        old = cfg["providers"].get(name) or {}
        if old.get("tiers") and not args.reset:
            providers[name] = old
            continue
        tiers, unavailable = resolve(name, find(name, cfg))
        providers[name] = {**({"bin": old["bin"]} if old.get("bin") else {}), "tiers": tiers, "unavailable": unavailable}
    for key, value in _pairs(args.model, "--model"):
        m = re.match(r"^([a-z]+):(fast|deep|top)$", key)
        if not m or m.group(1) not in providers:
            raise Stop("bad-argument", "--model wants <provider>:<fast|deep|top>=<model>[@effort], with a selected provider; got: %s" % key)
        slug, _, effort = value.partition("@")
        if effort and effort not in EFFORTS:
            raise Stop("bad-argument", "Unknown effort: %s (known: %s)" % (effort, ", ".join(EFFORTS)))
        entry = providers[m.group(1)]
        entry["tiers"][m.group(2)] = None if slug in ("", "none") else {"model": slug, **({"effort": effort} if effort else {})}
        (entry.get("unavailable") or {}).pop(m.group(2), None)
    roles = dict(cfg.get("roles") or {}) if known else {}
    for key, value in _pairs(args.role, "--role"):
        chain = [v.strip() for v in value.split(",") if v.strip()]
        if key not in ROLES or any(c not in providers for c in chain):
            raise Stop("bad-argument", "--role wants <researcher|reviewer|writer>=<provider,…> with selected providers; got: %s=%s" % (key, value))
        roles[key] = chain or None
    roles = {k: [p for p in v if p in providers] for k, v in roles.items() if v}
    degrees = json.loads(json.dumps(cfg["degrees"]))
    for item in args.degree or []:
        name, _, rest = item.partition(":")
        if name not in DEGREES or not rest:
            raise Stop("bad-argument", "--degree wants <low|medium|hard>:<key>=<value>,…; got: %s" % item)
        for key, value in _pairs(rest.split(","), "--degree"):
            if key == "tier" and value in TIERS:
                degrees[name]["tier"] = value
            elif key == "writer" and value in TIERS + ("none",):
                degrees[name]["writer"] = value
            elif key in LIMITS and value.isdigit() and LIMITS[key][0] <= int(value) <= LIMITS[key][1]:
                degrees[name][key] = int(value)
            else:
                raise Stop("bad-argument", "--degree %s: %s=%s is not valid (tier: %s; %s)" % (
                    name, key, value, "|".join(TIERS), "; ".join("%s: %d–%d" % (k, a, b) for k, (a, b) in LIMITS.items())))
    timeouts = dict(cfg["timeouts"])
    for key, value in _pairs(args.timeout, "--timeout"):
        if key not in TIERS or not value.isdigit() or not 1 <= int(value) <= 240:
            raise Stop("bad-argument", "--timeout wants <fast|deep|top>=<minutes 1–240>; got: %s=%s" % (key, value))
        timeouts[key] = int(value)
    cfg.update(order=names, providers=providers, roles=roles, degrees=degrees, timeouts=timeouts)
    if args.output:
        cfg["output"] = args.output
    if args.language:
        cfg["language"] = None if args.language == "auto" else args.language
    if args.links:
        cfg["link_check"] = args.links == "on"
    path = save_config(cfg)
    cfg["_configured"] = True
    return emit({"ok": True, "saved": str(path), **roster_payload(cfg),
                 "next": "Run `verify` once: it pings each model and checks that web search works."})


def cmd_verify(args, cfg) -> int:
    if not cfg.get("order"):
        raise Stop("no-provider", "No provider CLI was found on PATH, so there is nothing to verify.")
    report, changed = [], False
    work = Path(tempfile.mkdtemp(prefix="deepsearch-verify-"))
    try:
        for name in cfg["order"]:
            entry = cfg["providers"][name]
            binary = find(name, cfg)
            item = {"provider": name, "installed": bool(binary), "models": [], "restored": [], "dropped": []}
            report.append(item)
            if not binary:
                continue
            fresh, _ = resolve(name, binary)              # a model the account gained since is tried again
            for tier, model in list((entry.get("unavailable") or {}).items()):
                if not entry["tiers"].get(tier) and fresh.get(tier):
                    entry["tiers"][tier] = fresh[tier]
                    item["restored"].append("%s: %s" % (tier, fresh[tier]["model"]))
            seen: Dict[tuple, dict] = {}
            for tier in TIERS:
                spec = entry["tiers"].get(tier)
                if not spec:
                    continue
                key = (spec["model"], spec.get("effort"))
                if key not in seen:
                    cwd = work / ("%s-%s" % (name, tier))
                    cwd.mkdir()
                    seen[key] = ask(name, binary, spec, "Reply with the single word OK.", str(cwd), args.timeout)
                res = seen[key]
                item["models"].append({"tier": tier, "model": spec["model"], "outcome": res["outcome"],
                                       **({"error": res["error"]} if res.get("error") else {})})
                if res["outcome"] == "model":
                    entry.setdefault("unavailable", {})[tier] = spec["model"]
                    entry["tiers"][tier] = None
                    item["dropped"].append("%s: %s" % (tier, spec["model"]))
                    item["restored"] = [r for r in item["restored"] if not r.startswith(tier + ":")]
                    changed = True
                elif res["outcome"] == "done":
                    (entry.get("unavailable") or {}).pop(tier, None)
            changed = changed or bool(item["restored"])
            spec = next((entry["tiers"][t] for t in TIERS if entry["tiers"].get(t)), None)
            if spec and not args.no_web:
                cwd = work / ("%s-web" % name)
                cwd.mkdir()
                res = ask(name, binary, spec, "Use your web search tool to find the newest stable release of Python. Reply with "
                          "one line: WEB-OK <version>. If you have no working web search tool, reply exactly NO-WEB.",
                          str(cwd), max(args.timeout, 180))
                web = None if res["outcome"] != "done" else ("WEB-OK" in res["text"].upper())
                item["web"] = {True: "ok", False: "no web search", None: "not checked: " + (res.get("error") or res["outcome"])}[web]
                if web is not None and entry.get("web") != web:
                    entry["web"], changed = web, True
    finally:
        shutil.rmtree(work, ignore_errors=True)
    saved = changed or not cfg["_configured"]             # a first verify also records the roster it tested
    if saved:
        save_config(cfg)
        cfg["_configured"] = True
    return emit({"ok": True, "saved": saved, "verified": report, **roster_payload(cfg)})


def cmd_init(args, cfg) -> int:
    path = Path.cwd() / ".deepsearch.json"
    data = read_json(path) or {}
    for key, value in _pairs(args.set, "--set"):
        if key not in PROJECT_KEYS:
            raise Stop("bad-argument", "Unknown project setting: %s (known: %s)" % (key, ", ".join(PROJECT_KEYS)))
        if value in ("", "none"):
            data.pop(key, None)
        elif PROJECT_KEYS[key] is list:
            data[key] = [v.strip() for v in value.split(",") if v.strip()]
        else:
            data[key] = value
    created = not path.exists()
    if created and "output" not in data:
        data["output"] = "research"
    if created or args.set:
        write_json(path, data)
    kept, ignored = project_settings(Path.cwd())
    return emit({"ok": True, "file": str(path), "created": created, "settings": kept, "ignored": ignored,
                 "can_set": PROJECT_HELP, "runs_go_to": str((Path.cwd() / kept.get("output", cfg.get("output") or "research")).resolve())})


def cmd_start(args, cfg) -> int:
    if args.degree not in DEGREES:
        raise Stop("no-degree", "Ask the user which degree they want: low, medium or hard.", degrees={
            d: "%d agents" % len(team(cfg, d)) for d in DEGREES})
    topic = (Path(args.topic_file).read_text(encoding="utf-8") if args.topic_file else args.topic or "").strip()
    topic = " ".join(topic.split())[:200]
    if not topic:
        raise Stop("no-topic", "Give the topic: start --degree %s --topic '<a short title>'" % args.degree)
    if args.researchers is not None and not LIMITS["researchers"][0] <= args.researchers <= LIMITS["researchers"][1]:
        raise Stop("bad-argument", "--researchers wants %d to %d." % LIMITS["researchers"])
    earlier = None
    if args.builds_on:
        old = Path(args.builds_on).expanduser().resolve()
        earlier = next((p for p in (old / "report.md", old / "notes.md", old) if p.is_file()), None)
        if not earlier:
            raise Stop("no-run", "%s has no final document or notes to build on." % old)
    agents = team(cfg, args.degree, args.researchers)
    base = output_base(cfg)
    name = "%s-%s" % (datetime.now().strftime("%Y-%m-%d"), args.slug or slugify(topic))
    run, n = base / name, 1
    while run.exists():
        n += 1
        run = base / ("%s-%d" % (name, n))
    (run / ".work").mkdir(parents=True)
    language = args.lang or (cfg.get("_project") or {}).get("language") or cfg.get("language")
    crew = {"version": __version__, "topic": topic, "degree": args.degree, "settings": cfg["degrees"][args.degree],
            "language": language, "timeouts": cfg["timeouts"], "project": cfg.get("_project") or {},
            "link_check": bool(cfg.get("link_check", True)), "earlier": str(earlier) if earlier else None,
            "agents": agents, "created": now()}
    write_json(run / ".work" / "crew.json", crew)
    (run / "plan.md").write_text(plan_skeleton(topic, agents, language), encoding="utf-8")
    notes = roster_payload(cfg)["notes"]
    logline(run, "run opened: \"%s\" at degree %s, %d agents" % (topic, args.degree, len(agents)))
    return emit({"ok": True, "run": str(run), "plan": str(run / "plan.md"), "degree": args.degree, "agents": len(agents),
                 "team": [describe(a) for a in agents], "notes": notes,
                 "writes": "writer-1" if any(a["role"] == "writer" for a in agents) else "you",
                 "next": "Read references/method.md, then fill in every [[…]] of the plan and run: advance --run '%s'" % run})


def plan_gaps(run: Path, crew: dict, cycle: int) -> Optional[str]:
    head, sections = read_plan(run)
    mine = [a["agent"] for a in crew["agents"] if a.get("cycle", 1) == cycle]
    missing = [n for n in mine if not sections.get(n)]
    if PLACEHOLDER in head + "".join(sections.get(n, "") for n in mine) or missing:
        return ("The plan still has [[…]] placeholders or a missing section%s. Fill in %s first."
                % (": " + ", ".join(missing) if missing else "", run / "plan.md"))
    return None


def check_document(run: Path, crew: dict) -> dict:
    """The final document may only cite what the team cited, and its links must open."""
    doc_path = run / "report.md"
    known: set = set()
    files = [out_path(run, a["agent"]) for a in crew["agents"] if a["role"] != "writer"]
    for f in files:
        known |= urls_in(f)
    cited = urls_in(doc_path)
    unknown = sorted(cited - known)
    check_links(run, crew, [doc_path])
    dead = dead_links(run, doc_path)
    result = {"ok": not unknown and not dead, "document": str(doc_path), "sources": len(cited),
              "unknown_sources": unknown, "dead_links": dead}
    if unknown:
        result["text"] = ("%d source(s) in the document were cited by nobody on the team. Remove them, or move the "
                          "claim into a section marked as your own note, not reviewed." % len(unknown))
    if dead:
        result["text"] = (result.get("text", "") + " %d cited link(s) do not open: replace or remove them." % len(dead)).strip()
    return result


def closing(run: Path, crew: dict, state: dict, passed: List[dict]) -> dict:
    """What the caller does once the stages are through: reflect, write, or read the result."""
    left = int(crew["settings"].get("cycles", 1)) - state["cycle"]
    files = [str(out_path(run, a["agent"])) for a in crew["agents"] if a["role"] != "writer" and out_path(run, a["agent"]).is_file()]
    base = {"ok": True, "run": str(run), "cycle": state["cycle"], "passed": passed,
            "team": summary(run, crew), "last_verdicts": all_verdicts(run, crew)}
    if not is_final(crew, state):
        digest = write_digest(run, crew, state["cycle"])
        return {**base, "stage": "reflect", "cycles_left": left, "read": [str(digest)], "full": files, "notes": str(run / "notes.md"),
                "next": "Read `read` (the digest; open a file under `full` only where you need the detail), write what "
                        "is now established to `notes`, then decide: reflect --run '%s' --direction "
                        "<conclude|deepen|broaden|pivot> --reason '<one sentence>'" % run}
    if seats(crew, "writer") and (run / "report.md").is_file():
        result = check_document(run, crew)
        if result["ok"]:
            logline(run, "final document written and checked: %d sources, all cited by the team" % result["sources"])
        return {**base, "stage": "done", "document": str(run / "report.md"), "check": result,
                "next": ("Fix what `check` reports in the document, then run: check --run '%s'. " % run if not result["ok"] else "")
                        + "Read the document and give the user its answer in a few lines, with the path."}
    return {**base, "stage": "write", "read": files, "write": str(run / "report.md"),
            "next": "Read the files under `read` and write the final document to `write`. Then run: check --run '%s'" % run}


def cmd_advance(args, cfg) -> int:
    run = find_run(cfg, args.run)
    crew, state = load_crew(run), load_state(run)
    cycle = state["cycle"]
    stages = stage_plan(crew, state)
    passed = []
    while state["stage"] < len(stages):
        stage = stages[state["stage"]]
        if not state["started"]:
            if stage == "research":
                gaps = plan_gaps(run, crew, cycle)
                if gaps:
                    raise Stop("plan-not-ready", gaps)
                # the plan is fixed before anyone searches: what was asked stays on record
                shutil.copy2(run / "plan.md", run / ".work" / ("plan.cycle-%d.md" % cycle))
            agents = stage_agents(run, crew, stage, cycle)
            if not agents:
                passed.append({"stage": stage, "skipped": "nothing was sent back for revision" if stage.startswith("revise") else "no agent"})
                state.update(stage=state["stage"] + 1)
                continue
            started = [launch(run, crew, a, stage, cfg) for a in agents]
            state.update(started=True, agents=agents)
            write_json(run / ".work" / "state.json", state)
            logline(run, "cycle %d · %s started: %s" % (cycle, stage, ", ".join(
                "%s (%s)" % (x["agent"], "%s:%s" % (x["provider"], x["model"]) if x.get("provider") else "the caller") for x in started)))
            yours = [x for x in started if x.get("runs") == "you"]
            return emit({"ok": True, "run": str(run), "cycle": cycle, "stage": stage, "started": started, "passed": passed,
                         "next": _yours_text(yours) if yours and len(yours) == len(started) else
                         "Run: wait --run '%s'  (repeat until it says finished), then advance again.%s"
                         % (run, " " + _yours_text(yours) if yours else "")})
        metas = [agent_status(run, a, stage) for a in state["agents"]]
        running = [m["agent"] for m in metas if m.get("status") in ("queued", "running")]

        def mine(ms):
            return [{"agent": m["agent"], "prompt_file": str(agent_dir(run, m["agent"], stage) / "prompt.md"), "save_to": m["out"]} for m in ms]

        yours = mine([m for m in metas if m.get("status") == "you"])
        if running or yours:
            return emit({"ok": True, "run": str(run), "cycle": cycle, "stage": stage, "running": running, "yours": yours,
                         "next": (_yours_text(yours) if yours else "") + (" Run: wait --run '%s'" % run if running else "")})
        done = [m["agent"] for m in metas if m.get("status") == "done"]
        failed = [row(m) for m in metas if m.get("status") != "done"]
        if not done and stage in ("research", "review", "panel", "write"):
            # nobody answered: the caller takes these seats rather than the run stopping here
            for m in metas:
                m.update(status="you", since=time.time())
                write_json(agent_dir(run, m["agent"], stage) / "meta.json", m)
            logline(run, "cycle %d · %s: no provider answered; handed to the caller" % (cycle, stage))
            return emit({"ok": True, "run": str(run), "cycle": cycle, "stage": stage, "failed": failed, "yours": mine(metas),
                         "next": "No provider answered. " + _yours_text(mine(metas))})
        passed.append({"stage": stage, "done": done, **({"failed": failed} if failed else {})})
        text = "cycle %d · %s finished: %d done%s" % (cycle, stage, len(done), ", %d failed (%s)" % (
            len(failed), ", ".join(f["agent"] for f in failed)) if failed else "")
        if stage in ("review", "panel"):
            ruled = verdicts(run, state["agents"], [n for n in seats(crew, "researcher", cycle) if out_path(run, n).is_file()])
            text += " · verdicts: " + ", ".join("%s %s" % kv for kv in sorted(ruled.items()))
        logline(run, text)
        if stage in ("research", "revise", "revise2"):     # before anyone reviews: do the cited pages exist?
            links = check_links(run, crew, [out_path(run, a) for a in done])
            gone = sum(1 for a in done for u in urls_in(out_path(run, a)) if links.get(u) == "dead")
            if gone:
                passed[-1]["dead_links"] = gone
                logline(run, "cycle %d · link check after %s: %d cited link(s) do not open" % (cycle, stage, gone))
        state.update(stage=state["stage"] + 1, started=False, agents=[])
        write_json(run / ".work" / "state.json", state)
    write_json(run / ".work" / "state.json", state)
    return emit(closing(run, crew, state, passed))


def cmd_reflect(args, cfg) -> int:
    """After a cycle: write up, or look again. Another cycle adds researchers (and one reviewer)
    for what the first could not settle, as far as the degree allows."""
    run = find_run(cfg, args.run)
    crew, state = load_crew(run), load_state(run)
    if state["stage"] < len(cycle_stages(crew, state["cycle"])):
        raise Stop("not-yet", "The current cycle is not through. Run: advance --run '%s'" % run)
    if args.direction not in DIRECTIONS:
        raise Stop("bad-argument", "--direction wants one of: %s" % ", ".join(DIRECTIONS))
    reason = " ".join((args.reason or "").split())[:400]
    if not reason:
        raise Stop("bad-argument", "Give the reason in one sentence: --reason '…'. It goes into the log.")
    notes = run / "notes.md"
    if not notes.is_file() or len(notes.read_text(encoding="utf-8", errors="replace")) < MIN_CHARS:
        raise Stop("no-notes", "Write what is established so far to %s first (established, patterns, dead ends, "
                   "open questions). A later cycle and the final document build on it." % notes)
    left = int(crew["settings"].get("cycles", 1)) - state["cycle"]
    if args.direction != "conclude" and left <= 0:
        raise Stop("no-cycle-left", "This degree allows %d cycle(s) and they are used. Conclude: reflect --direction conclude --reason '…'"
                   % crew["settings"].get("cycles", 1))
    logline(run, "cycle %d · reflect: %s — %s" % (state["cycle"], args.direction, reason))
    if args.direction == "conclude":
        state["concluded"] = True
        write_json(run / ".work" / "state.json", state)
        if seats(crew, "writer"):
            return emit({"ok": True, "run": str(run), "stage": "write", "writes": "writer-1",
                         "next": "Run: advance --run '%s'  (it starts the writer), then wait and advance again." % run})
        return emit(closing(run, crew, state, []))
    cycle = state["cycle"] + 1
    count = max(1, min(args.researchers or 2, crew["settings"]["researchers"]))
    cfg = load_config(True)
    chain = candidates(cfg, "researcher", crew["settings"]["tier"])
    pool = [c for c in chain if c["tier"] == chain[0]["tier"]] if chain else []
    known = len(seats(crew, "researcher"))
    added = []
    for i in range(count):
        lead = pool[(known + i) % len(pool)] if pool else None
        added.append({"agent": "researcher-%d" % (known + i + 1), "role": "researcher", "cycle": cycle,
                      "chain": ([lead] + [c for c in chain if c is not lead]) if lead else []})
    top = candidates(cfg, "reviewer", "top")
    added.append({"agent": "reviewer-%d" % (len(seats(crew, "reviewer")) + 1), "role": "reviewer", "cycle": cycle, "chain": top})
    crew["agents"] += added
    write_json(run / ".work" / "crew.json", crew)
    with open(run / "plan.md", "a", encoding="utf-8") as fh:
        fh.write("\n" + "\n".join(line for a in added for line in agent_section(a)))
    state.update(cycle=cycle, stage=0, started=False, agents=[])
    write_json(run / ".work" / "state.json", state)
    return emit({"ok": True, "run": str(run), "cycle": cycle, "direction": args.direction, "cycles_left": left - 1,
                 "added": [describe(a) for a in added], "plan": str(run / "plan.md"),
                 "next": "Fill in the new sections at the end of the plan%s, then run: advance --run '%s'"
                         % (" and rewrite its Question and Scope for the new direction" if args.direction == "pivot" else "", run)})


def cmd_check(args, cfg) -> int:
    run = find_run(cfg, args.run)
    crew = load_crew(run)
    if not (run / "report.md").is_file():
        raise Stop("no-document", "There is no final document yet: %s" % (run / "report.md"))
    result = check_document(run, crew)
    if result["ok"]:
        logline(run, "final document checked: %d sources, all cited by the team" % result["sources"])
    return emit(result, 0 if result["ok"] else 1)


def _yours_text(yours: List[dict]) -> str:
    if not yours:
        return ""
    return ("No provider CLI can run %s. Do each yourself, one at a time and without looking at the others' prompts: "
            "follow its prompt_file as if it were your whole task (run it as a subagent if you have one) and save the "
            "document to save_to. Then advance again." % ", ".join(y["agent"] for y in yours))


def summary(run: Path, crew: dict) -> List[dict]:
    rows = []
    for a in crew["agents"]:
        for stage in STAGES:
            meta = meta_of(run, a["agent"], stage)
            if meta:
                rows.append(row(agent_status(run, a["agent"], stage)))
    return rows


def cmd_wait(args, cfg) -> int:
    run = find_run(cfg, args.run)
    crew = load_crew(run)
    deadline = time.time() + args.timeout
    while True:
        state = load_state(run)
        stages = stage_plan(crew, state)
        stage = stages[state["stage"]] if state["stage"] < len(stages) else None
        metas = [agent_status(run, a, stage) for a in state.get("agents") or []] if stage and state["started"] else []
        running = [m["agent"] for m in metas if m.get("status") in ("queued", "running")]
        if not running or time.time() >= deadline:
            return emit({"ok": True, "run": str(run), "stage": stage, "finished": not running, "running": running,
                         "agents": [row(m) for m in metas],
                         "next": "Run wait again." if running else "Run: advance --run '%s'" % run})
        time.sleep(2)


def cmd_status(args, cfg) -> int:
    run = find_run(cfg, args.run)
    crew, state = load_crew(run), load_state(run)
    stages = stage_plan(crew, state)
    after = "reflect" if not is_final(crew, state) else "done" if (run / "report.md").is_file() else "write"
    return emit({"ok": True, "run": str(run), "topic": crew.get("topic"), "degree": crew.get("degree"),
                 "cycle": state["cycle"], "log": str(run / "log.md"),
                 "stage": stages[state["stage"]] if state["stage"] < len(stages) else after,
                 "document": str(run / "report.md") if (run / "report.md").is_file() else None,
                 "agents": summary(run, crew)})


def cmd_runs(args, cfg) -> int:
    base = output_base(cfg)
    rows = []
    for d in sorted(base.glob("*")) if base.is_dir() else []:
        crew = read_json(d / ".work" / "crew.json")
        if crew:
            rows.append({"run": str(d), "topic": crew.get("topic"), "degree": crew.get("degree"),
                         "written": (d / "report.md").is_file()})
    return emit({"ok": True, "folder": str(base), "runs": rows})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="deepsearch", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version="deepsearch " + __version__)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("detect")
    s = sub.add_parser("setup")
    s.add_argument("--providers", help="comma separated, in order of preference: claude,codex,agy,kiro")
    s.add_argument("--model", action="append", help="<provider>:<fast|deep|top>=<model>[@effort]  (model `none` empties the tier)")
    s.add_argument("--role", action="append", help="<researcher|reviewer|writer>=<provider,…>")
    s.add_argument("--degree", action="append", help="<low|medium|hard>:researchers=N,reviewers=N,panel=N,cycles=N,calls=N,words=N,tier=fast|deep|top,writer=none|fast|deep|top")
    s.add_argument("--timeout", action="append", help="<fast|deep|top>=<minutes>")
    s.add_argument("--output", help="folder for the runs (default: research, under the folder you call it from)")
    s.add_argument("--language", help="language of every document; `auto` = the language of the request")
    s.add_argument("--links", choices=("on", "off"), help="open every cited link once before the review (default on)")
    s.add_argument("--reset", action="store_true", help="read the models from the CLIs again instead of keeping the saved ones")
    s = sub.add_parser("roster")
    s.add_argument("--md", action="store_true")
    s = sub.add_parser("verify")
    s.add_argument("--no-web", action="store_true")
    s.add_argument("--timeout", type=int, default=120, help="seconds per ping")
    s = sub.add_parser("init")
    s.add_argument("--set", action="append", help="key=value (see `init` for the keys); `none` removes one")
    s = sub.add_parser("start")
    s.add_argument("--degree", default="")
    s.add_argument("--topic")
    s.add_argument("--topic-file")
    s.add_argument("--slug")
    s.add_argument("--researchers", type=int, help="how many researchers this question needs (default: the degree's)")
    s.add_argument("--builds-on", help="an earlier run's folder: its final document is given to the team as background")
    s.add_argument("--lang")
    for name in ("advance", "status", "check"):
        s = sub.add_parser(name)
        s.add_argument("--run")
    s = sub.add_parser("reflect")
    s.add_argument("--run")
    s.add_argument("--direction", default="")
    s.add_argument("--reason")
    s.add_argument("--researchers", type=int, help="how many researchers the next cycle gets (default 2)")
    s = sub.add_parser("wait")
    s.add_argument("--run")
    s.add_argument("--timeout", type=int, default=540)
    sub.add_parser("runs")
    s = sub.add_parser("_exec")
    s.add_argument("run")
    s.add_argument("agent")
    s.add_argument("stage")
    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 0
    if args.cmd == "_exec":
        execute(Path(args.run), args.agent, args.stage)
        return 0
    try:
        discover = args.cmd in ("setup", "roster", "verify", "start")
        return globals()["cmd_" + args.cmd](args, load_config(discover))
    except Stop as e:
        return emit(e.payload, 2)


if __name__ == "__main__":
    sys.exit(main())
