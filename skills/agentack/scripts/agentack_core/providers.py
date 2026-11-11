"""Provider adapters: how to find each agent CLI, run it headless and read its answer.

A provider is a *harness* (a CLI that can read files, edit and run commands) plus the models it
exposes. Each one declares a default model per tier:

    S4 decision   S3 plan & review   S2 build   S1 mechanical

`None` means the provider has no sensible default for that tier; the user can name one in setup.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import ssl
import subprocess
import threading
import time
import urllib.request
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

TIERS = ("S1", "S2", "S3", "S4")

# What each provider is good at, by kind of work, on a 1–5 scale:
#   5 leads the field · 4 strong · 3 adequate or not yet rated · 2 weak: last resort · 1 do not use
# Ratings describe the provider's model for that work *as run headless through its CLI*, which is
# how workers run. Evidence and dates are in references/strengths.md; override with
# `setup --rate provider:skill=N`.
SKILLS = ("decide", "plan", "review", "visual", "backend", "frontend", "test", "mechanical")
RATINGS_REVIEWED = "2026-11-11"
WEAK = 2

# How a model wants to be briefed. Order matters: each style needs more spelled out than the one
# before it ("peer" stands apart: it is how the strongest model is consulted).
STYLES = ("goal", "structured", "explicit", "rules")
TIER_STYLE = {"S4": "peer", "S3": "goal", "S2": "structured", "S1": "rules"}
STYLE_GUIDE = {
    "goal": {
        "for": "plan-and-review class models (Opus and peers)",
        "write": ["the goal, the context it cannot cheaply find, the constraints, what done looks like",
                  "no step list: the approach is the worker's call"],
        "work": "You have latitude. The brief gives the goal, context, constraints and what done looks "
                "like; choose the approach yourself and say in a line why.",
    },
    "structured": {
        "for": "build class models (Sonnet and peers)",
        "write": ["named files, numbered steps, the output shape and the boundaries",
                  "leave the details inside those to the worker"],
        "work": "Follow the brief's named files, steps and boundaries. Decide the details inside them "
                "yourself; do not widen the scope.",
    },
    "explicit": {
        "for": "models that follow instructions literally (GPT-6.1 Sol, Auto routers)",
        "write": ["every step in order, each with its file and its visible result",
                  "nothing implicit: no 'as usual', no 'like the other one'; name the file to imitate",
                  "exact commands and their expected result; the exact output sections"],
        "work": "Work through the brief step by step, in order. Nothing is implied: where a step, file "
                "or expected result is not spelled out, do not guess. State the assumption you need, "
                "and stop at that step if it would change the result.",
    },
    "rules": {
        "for": "mechanical class models (Haiku, GPT-6 Luna, Gemini 3.8 Flash)",
        "write": ["an exact rule set, with a real input/output example and a look-alike that must not change",
                  "a small batch: about 10 files or 25 items per brief; split bigger jobs",
                  "an output shape you can spot-check; then check roughly 1 item in 5 yourself"],
        "work": "Apply the rules in the brief exactly as written, one item at a time, using the examples "
                "as the pattern. Do not interpret, extend or skip a rule. An item that fits no rule "
                "stays unchanged and goes in your Skipped list.",
    },
    "peer": {
        "for": "the strongest model (Fable, GPT-6 Astra, Gemini 4 Argon)",
        "write": ["the open question and why it is hard to reverse",
                  "the evidence, gathered beforehand by cheaper roles, each fact with its source",
                  "the options so far and what is still unknown; no steps and no exploration chores"],
        "work": "You are consulted as a peer. The brief holds the open question and the evidence already "
                "gathered. Reason from it; open the code only to settle a specific doubt, and name the "
                "evidence that is missing rather than exploring broadly.",
    },
}
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")
LIMIT_RX = re.compile(
    r"(usage|rate|weekly|session|daily|hourly)[\s_-]*limit|limit (was |has been )?(reached|exceeded|hit)|"
    r"quota[\s_]*(exceeded|exhausted|reached)|out of (credits|quota)|insufficient (credits|quota)|"
    r"too many requests|\b429\b|resource[_ ]exhausted|credit balance is too low", re.I)
# the account or plan does not have this model (as opposed to having used it up)
MODEL_RX = re.compile(
    r"model[^\n]{0,60}(not found|does not exist|doesn't exist|not available|unavailable|not supported|"
    r"unsupported|not allowed|no access|not have access|not enabled|unknown|invalid)|"
    r"(unknown|invalid|unsupported|unrecognized) model|model_not_found|no such model|"
    r"not supported (when using|with|on|for) [^\n]{0,60}(account|plan|subscription)|"
    r"(requires|need) [^\n]{0,40}(plan|subscription|api key) [^\n]{0,40}model", re.I)


def model_refusal(evidence: str, model: str) -> Optional[str]:
    """The line in which a CLI says this account cannot use `model`, or None.

    A CLI's stderr can also carry a worker's own command output ("User model not found"), so a
    line only counts when it names the model or talks about the account, plan or access."""
    needle = (model or "").lower()
    for line in reversed((evidence or "").splitlines()[-200:]):
        if MODEL_RX.search(line):
            low = line.lower()
            if (needle and needle in low) or re.search(r"account|plan|subscription|access|entitle", low):
                return line.strip()[:300]
    return None


def _run(argv: List[str], timeout: int = 8, cwd: Optional[str] = None) -> Tuple[int, str]:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=cwd,
                           stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def _last_json(text: str) -> Optional[dict]:
    """Parse the whole text as JSON, else the last line that is a JSON object."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue
    return None


def _app_server(binary: str, method: str, params: Optional[dict] = None, timeout: float = 6) -> dict:
    """One JSON-RPC call to `codex app-server` over stdio. Returns the result, or {}."""
    try:
        proc = subprocess.Popen([binary, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True)
    except OSError:
        return {}
    found: dict = {}

    def reader():
        for line in proc.stdout:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == 2 and isinstance(msg.get("result"), dict):
                found.update(msg["result"])
                return

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    try:
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "agentack", "version": "2"}}}) + "\n")
        proc.stdin.flush()
        time.sleep(0.6)
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": method,
                                     "params": params or {}}) + "\n")
        proc.stdin.flush()
        t.join(timeout)
    except (OSError, ValueError):
        pass
    finally:
        proc.kill()
    return found


def _group_pids(leader: int) -> List[int]:
    code, out = _run(["ps", "-A", "-o", "pid=,pgid="], timeout=5)
    pids = [int(a) for a, b in (ln.split()[:2] for ln in out.splitlines() if len(ln.split()) >= 2)
            if a.isdigit() and b == str(leader)]
    return pids or [leader]


def _listening_ports(pids: List[int]) -> List[int]:
    ports = set()
    for pid in pids:
        code, out = _run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", str(pid)], timeout=5)
        ports |= {int(p) for p in re.findall(r":(\d+) \(LISTEN\)", out)}
    if not ports:
        code, out = _run(["ss", "-ltnpH"], timeout=5)
        for line in out.splitlines():
            if any("pid=%d," % p in line for p in pids):
                m = re.search(r":(\d+)\s", line)
                if m:
                    ports.add(int(m.group(1)))
    return sorted(ports)


def _local_rpc(port: int, path: str, body: dict, timeout: float = 3) -> Optional[dict]:
    """POST JSON to a CLI's own server on 127.0.0.1 (never leaves the machine, no proxy)."""
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))   # self-signed loopback cert
    for scheme in ("https", "http"):
        req = urllib.request.Request("%s://127.0.0.1:%d/%s" % (scheme, port, path),
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "Connect-Protocol-Version": "1"})
        try:
            with opener.open(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
                if isinstance(data, dict):
                    return data
        except Exception:
            continue
    return None


def parse_quota_summary(data: dict, prefer: str = "gemini") -> dict:
    """Antigravity quota groups -> {"5h": {"used": 40.0}, "7d": {...}} (worst bucket per window)."""
    groups = data.get("groups") or (data.get("response") or {}).get("groups") or []
    chosen = [g for g in groups if prefer in str(g.get("displayName", "")).lower()] or groups
    windows: Dict[str, dict] = {}
    for g in chosen:
        for b in g.get("buckets") or []:
            frac = (b.get("remaining") or {}).get("remainingFraction")
            if frac is None:
                continue
            name = (str(b.get("displayName", "")) + " " + str(b.get("bucketId", ""))).lower()
            label = "5h" if re.search(r"five|5[ -]?h", name) else "7d" if "week" in name else \
                (b.get("displayName") or b.get("bucketId") or "quota")
            used = round((1 - float(frac)) * 100, 1)
            if label not in windows or used > windows[label]["used"]:
                windows[label] = {"used": used, "resets_at": None, "note": b.get("description")}
    return windows


class Provider:
    name = ""
    label = ""
    vendor = ""                    # model family, used for the reviewer-independence rule
    bins: Tuple[str, ...] = ()
    conductor = False              # can host the conductor session in this release
    tiers: Dict[str, Optional[dict]] = {}
    match: Dict[str, Tuple[str, ...]] = {}   # tier -> keywords to pick a slug from a model listing
    conductor_keywords: Tuple[str, ...] = ()
    read_only_enforced = False     # the CLI itself can be prevented from editing
    styles: Dict[str, str] = {}    # tier -> briefing style, where it differs from TIER_STYLE
    ratings: Dict[str, int] = {}   # skill -> 1..5 (see SKILLS); missing = 3, not yet rated
    stand_ins: Dict[str, str] = {}  # tier -> model to try when the tier's own model is refused
    image = False                  # its CLI can produce raster images headlessly (experimental)

    def image_command(self, binary: str, spec: dict, prompt: str, cwd: str, out_file: str):
        """argv + stdin for a run whose only job is to generate one image."""
        return self.command(binary, spec, "write", prompt, cwd, out_file)

    def image_dirs(self) -> List[Path]:
        """Places outside the working directory where this CLI drops generated images."""
        return []
    never: Tuple[str, ...] = ()    # words that rule a listed model out (too weak to be worth using)
    probe_minutes = 5              # how often limit_probe may run
    sign_in = ""                   # what the user runs to sign in
    docs = ""                      # where to get the CLI
    notes = ""

    # -- discovery ---------------------------------------------------------------------------
    def find(self, cfg: dict) -> Optional[str]:
        custom = ((cfg.get("providers") or {}).get(self.name) or {}).get("bin")
        for cand in ([custom] if custom else []) + list(self.bins):
            path = shutil.which(os.path.expanduser(cand))
            if path and self.accept_binary(path):
                return path
        return None

    def accept_binary(self, path: str) -> bool:
        return True

    def style(self, tier: str, spec: Optional[dict]) -> str:
        """Briefing style for one of this provider's models (overridable per tier in the config)."""
        if spec and spec.get("style") in STYLE_GUIDE:
            return spec["style"]
        if spec and str(spec.get("model", "")).lower() == "auto":
            return "explicit"          # an unknown model behind a router: leave nothing implicit
        return self.styles.get(tier) or TIER_STYLE[tier]

    def auth(self, binary: Optional[str] = None) -> str:
        """A cheap sign-in hint: "ok", "not signed in" or "not checked". Never proof either way;
        `doctor --ping` is the real test."""
        return "not checked"

    def list_models(self, binary: str) -> List[str]:
        return []

    def trusted_models(self, binary: Optional[str]) -> List[str]:
        """The CLI's model listing, or [] when it is empty or does not look like one we understand
        (none of our known names in it). Only a trusted listing may remove models from a roster."""
        models = self.list_models(binary) if binary else []
        known = [spec["model"] for spec in self.tiers.values() if spec]
        looks_right = any(m in models for m in known) or any(
            self.pick_model(tier, models) for tier in self.match)
        return models if looks_right else []

    def pick_model(self, tier: str, models: List[str], exclude=()) -> Optional[str]:
        """Best listed model for a tier: `match[tier]` is one keyword set, or several in order of
        preference (the first that the account lists wins)."""
        wanted = self.match.get(tier) or ()
        alternatives = wanted if wanted and isinstance(wanted[0], tuple) else (wanted,) if wanted else ()
        effort = (self.tiers.get(tier) or {}).get("effort")
        for words in alternatives:
            hits = [m for m in models if all(w in m.lower() for w in words) and m not in exclude
                    and not any(n in m.lower() for n in self.never)]
            if hits:
                preferred = [m for m in hits if effort and m.lower().endswith(effort)]
                return sorted(preferred or hits)[-1]
        return None

    def detect(self, cfg: dict) -> dict:
        binary = self.find(cfg)
        info = {"name": self.name, "label": self.label, "installed": bool(binary), "path": binary,
                "can_conduct": self.conductor, "tiers": {t: self.tiers.get(t) for t in TIERS},
                "missing_tiers": [t for t in TIERS if not self.tiers.get(t)], "notes": self.notes,
                "sign_in": self.sign_in, "docs": self.docs}
        if binary:
            code, out = _run([binary, "--version"])
            info["version"] = ANSI.sub("", out).strip().splitlines()[0][:80] if out.strip() else None
            info["auth"] = self.auth(binary)
        return info

    def adjust(self, tier: str, spec: dict) -> dict:
        """Last word on a tier's spec once its model is known (e.g. effort for a stand-in model)."""
        return spec

    def resolve_tiers(self, binary: Optional[str]):
        """(tiers, unavailable): default tiers refined against the CLI's own model listing.

        A tier whose model is not in the listing is dropped: this account does not have it, and
        the role will run on another provider's model of that tier instead."""
        tiers = {t: (dict(self.tiers[t]) if self.tiers.get(t) else None) for t in TIERS}
        unavailable: Dict[str, str] = {}
        models = self.trusted_models(binary)
        if not models:
            return tiers, unavailable
        for tier in self.match:
            default = tiers.get(tier)
            best = self.pick_model(tier, models)
            if best:
                spec = {**(default or {}), "model": best}
                if re.search(r"-(minimal|low|medium|high|xhigh|max)$", best.lower()):
                    spec.pop("effort", None)          # the slug already encodes the effort
                tiers[tier] = self.adjust(tier, spec)
            elif default and default["model"] in models:
                continue
            elif default:
                unavailable[tier] = default["model"]
                tiers[tier] = None
        return tiers, unavailable

    # -- execution ---------------------------------------------------------------------------
    def command(self, binary: str, spec: dict, mode: str, prompt: str, cwd: str,
                out_file: str) -> Tuple[List[str], Optional[str]]:
        raise NotImplementedError

    def final(self, stdout: str, out_file: str) -> Tuple[str, bool]:
        """Return (final message, provider reported an error)."""
        return ANSI.sub("", stdout or "").strip(), False

    def limit_probe(self, binary: str) -> Optional[dict]:
        """Return {"windows": {"5h": {"used": 42.0, "resets_at": ...}, ...}} when measurable."""
        return None


class Claude(Provider):
    name, label, vendor = "claude", "Claude Code", "anthropic"
    bins = ("claude",)
    conductor = True
    tiers = {"S4": {"model": "fable"}, "S3": {"model": "opus"},
             "S2": {"model": "sonnet"}, "S1": {"model": "haiku"}}
    conductor_keywords = ("opus", "fable", "mythos")
    ratings = {"decide": 5, "plan": 5, "review": 5, "visual": 4, "backend": 5, "frontend": 4,
               "test": 5, "mechanical": 4}
    sign_in = "run `claude` and use /login"
    docs = "https://docs.claude.com/en/docs/claude-code/overview"
    read_only_enforced = True
    notes = "Usage can be measured through the optional status line hook (`hook install`)."

    def auth(self, binary=None):
        if os.environ.get("ANTHROPIC_API_KEY") or (Path.home() / ".claude" / ".credentials.json").exists():
            return "ok"
        return "not checked"

    def command(self, binary, spec, mode, prompt, cwd, out_file):
        argv = [binary, "-p", "--model", spec["model"], "--output-format", "json"]
        if spec.get("effort"):
            argv += ["--effort", spec["effort"]]
        if mode == "write":
            argv += ["--permission-mode", "acceptEdits",
                     "--allowedTools", "Bash,Read,Edit,Write,MultiEdit,NotebookEdit,Glob,Grep"]
        else:
            argv += ["--allowedTools", "Bash,Read,Glob,Grep",
                     "--disallowedTools", "Edit,Write,MultiEdit,NotebookEdit"]
        return argv, prompt

    def final(self, stdout, out_file):
        data = _last_json(stdout)
        if data is None:
            return (stdout or "").strip(), False
        return str(data.get("result") or "").strip(), bool(data.get("is_error"))


class Codex(Provider):
    name, label, vendor = "codex", "Codex", "openai"
    bins = ("codex",)
    conductor = True
    tiers = {"S4": {"model": "gpt-6-astra", "effort": "high"},
             "S3": {"model": "gpt-6-astra", "effort": "medium"},
             "S2": {"model": "gpt-6.1-sol", "effort": "medium"},
             "S1": {"model": "gpt-6-luna", "effort": "low"}}
    stand_ins = {"S3": "gpt-6.1-sol"}
    conductor_keywords = ("astra",)   # Sol counts only where it is the account's S3 (no Astra)
    ratings = {"decide": 5, "plan": 4, "review": 4, "visual": 4, "backend": 4, "frontend": 4,
               "test": 4, "mechanical": 3}
    styles = {"S2": "explicit"}                        # Sol wants every step spelled out

    def style(self, tier, spec):
        if spec and spec.get("style") not in STYLE_GUIDE and "sol" in str(spec.get("model", "")).lower():
            return "explicit"                          # also when Sol stands in for Astra at S3
        return super().style(tier, spec)

    def adjust(self, tier, spec):
        if tier == "S3" and "sol" in spec["model"].lower():
            spec = dict(spec, effort="high")           # Sol standing in for Astra: give it full effort
        return spec
    sign_in = "codex login"
    read_only_enforced = True
    notes = ("Write runs use the workspace-write sandbox (no network by default); add extra_args in the "
             "config if your tests need more. Some models need an API key login rather than a ChatGPT "
             "account; `verify` finds and drops those.")

    def auth(self, binary=None):
        if os.environ.get("OPENAI_API_KEY") or (Path.home() / ".codex" / "auth.json").exists():
            return "ok"
        return "not checked"

    def command(self, binary, spec, mode, prompt, cwd, out_file):
        argv = [binary, "exec", "--model", spec["model"]]
        if spec.get("effort"):
            argv += ["-c", 'model_reasoning_effort="%s"' % spec["effort"]]
        argv += ["--sandbox", "workspace-write" if mode == "write" else "read-only",
                 "--skip-git-repo-check", "-C", cwd, "-o", out_file, "-"]
        return argv, prompt

    image = True                   # built-in image_gen tool

    def image_command(self, binary, spec, prompt, cwd, out_file):
        argv = [binary, "exec", "--enable", "image_generation", "--model", spec["model"],
                "--sandbox", "workspace-write", "--skip-git-repo-check", "-C", cwd, "-o", out_file, "-"]
        return argv, prompt

    def image_dirs(self):
        home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        return [home / "generated_images"]

    def final(self, stdout, out_file):
        try:
            text = Path(out_file).read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            text = ""
        return text, False

    match = {"S4": (("astra",),), "S3": (("astra",), ("sol",)), "S2": (("sol",),), "S1": (("luna",),)}

    def list_models(self, binary):
        """Models the app-server lists for this login. A listed model can still be refused for the
        account type (ChatGPT login vs API key), which `verify` finds by pinging."""
        result = _app_server(binary, "model/list")
        out = []
        for value in result.values():
            for item in value if isinstance(value, list) else []:
                if isinstance(item, dict) and not item.get("hidden"):
                    mid = item.get("model") or item.get("id")
                    if isinstance(mid, str):
                        out.append(mid)
        return sorted(set(out))

    def limit_probe(self, binary):
        found = _app_server(binary, "account/rateLimits/read")
        limits = found.get("rateLimits") or found.get("rate_limits") or {}
        windows = {}
        for key, label in (("primary", "5h"), ("secondary", "7d")):
            w = limits.get(key) or {}
            used = w.get("usedPercent", w.get("used_percent"))
            if used is not None:
                windows[label] = {"used": float(used), "resets_at": w.get("resetsAt", w.get("resets_at"))}
        return {"windows": windows} if windows else None


class Antigravity(Provider):
    name, label, vendor = "agy", "Antigravity", "google"
    bins = ("agy",)
    conductor = True               # as a skill in the Antigravity app, IDE or CLI
    image = True                   # Gemini image models through the agent
    conductor_keywords = ("karbon", "carbon", "argon", "3.1-pro", "gemini-pro")
    # Gemini is used where it is strong: analysis, review, long context and anything visual run on
    # Argon (Karbon where the plan has it). It trails on headless coding loops, so its build and
    # mechanical tiers are one model up from the menu's suggestion and rated as a last resort.
    # Flash-Lite class models are never used.
    tiers = {"S4": {"model": "gemini-4-argon", "effort": "high"},
             "S3": {"model": "gemini-4-argon", "effort": "high"},
             "S2": {"model": "gemini-3.1-pro", "effort": "high"},
             "S1": {"model": "gemini-3.8-flash", "effort": "medium"}}
    match = {"S4": (("karbon",), ("carbon",), ("argon",)), "S3": (("argon",), ("3.1-pro",)),
             "S2": (("3.1-pro",), ("argon",), ("3.8-flash",)), "S1": (("3.8-flash",), ("flash",))}
    never = ("lite",)
    ratings = {"decide": 4, "plan": 4, "review": 4, "visual": 5, "backend": 2, "frontend": 2,
               "test": 2, "mechanical": 2}
    notes = ("Uses your existing `agy` login. Model slugs are read from `agy models`; usage is read "
             "from the CLI's local quota endpoint (experimental).")

    def auth(self, binary=None):
        # a working model listing is a good sign that the CLI can reach the account
        return "ok" if binary and self.list_models(binary) else "not checked"

    def list_models(self, binary):
        code, out = _run([binary, "models"], timeout=15)
        if code != 0:
            return []
        return sorted(set(re.findall(r"\b(gemini-[a-z0-9.\-]+)", ANSI.sub("", out).lower())))

    probe_minutes = 15
    sign_in = "run `agy` once and sign in"
    docs = "https://antigravity.google/docs/cli"
    RPC = "exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary"
    META = {"ideName": "antigravity", "extensionName": "antigravity", "locale": "en", "ideVersion": "1.0.0"}

    def limit_probe(self, binary):
        """Start `agy` briefly in a pseudo-terminal and ask its own local server for the quota
        summary (5-hour and weekly buckets per model group). Nothing is typed into the session."""
        import pty
        master, slave = pty.openpty()
        try:
            proc = subprocess.Popen([binary], stdin=slave, stdout=slave, stderr=slave,
                                    start_new_session=True, close_fds=True)
        except OSError:
            os.close(master)
            os.close(slave)
            return None
        os.close(slave)
        os.set_blocking(master, False)
        windows: dict = {}
        deadline = time.time() + 12
        try:
            while time.time() < deadline and proc.poll() is None and not windows:
                time.sleep(0.8)
                try:
                    while os.read(master, 65536):     # keep the TUI from blocking on a full pipe
                        pass
                except OSError:
                    pass
                for port in _listening_ports(_group_pids(proc.pid)):
                    for body in ({"metadata": self.META}, self.META):
                        data = _local_rpc(port, self.RPC, body)
                        windows = parse_quota_summary(data) if data else {}
                        if windows:
                            break
                    if windows:
                        break
        finally:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(proc.pid, sig)
                    proc.wait(2)
                    break
                except (OSError, subprocess.TimeoutExpired):
                    continue
            os.close(master)
        return {"windows": windows} if windows else None

    def command(self, binary, spec, mode, prompt, cwd, out_file):
        argv = [binary, "-p", prompt, "--model", spec["model"], "--output-format", "json",
                "--dangerously-skip-permissions"]
        if spec.get("effort") and not re.search(r"-(minimal|low|medium|high|xhigh|max)$", spec["model"]):
            argv += ["--effort", spec["effort"]]
        return argv, None

    def final(self, stdout, out_file):
        data = _last_json(stdout)
        if data is None:
            return ANSI.sub("", stdout or "").strip(), False
        failed = str(data.get("status", "")).upper() == "ERROR"
        text = data.get("response") or data.get("result")
        if failed and not text:      # keep the CLI's own error text so it can be classified
            text = data.get("error") or data.get("message") or json.dumps(data, ensure_ascii=False)
        return str(text or "").strip(), failed


class Cursor(Provider):
    name, label, vendor = "cursor", "Cursor", "cursor"
    bins = ("cursor-agent", "agent")
    tiers = {"S4": None, "S3": None,
             "S2": {"model": "cursor-composer-2-5"}, "S1": {"model": "auto"}}
    read_only_enforced = True      # without --force the CLI only proposes changes
    ratings = {"backend": 3, "frontend": 3, "test": 3, "mechanical": 3}       # not yet rated
    sign_in = "cursor-agent login (or set CURSOR_API_KEY)"
    notes = ("Composer and Auto cover build and mechanical work. For S3/S4 name a frontier model "
             "your plan includes (setup: --model cursor:S3=<slug>). Uses CURSOR_API_KEY or your login.")

    def accept_binary(self, path):
        if os.path.basename(path) != "agent":
            return True   # `agent` is a generic name: require a sign that it is Cursor's
        return "cursor" in os.path.realpath(path).lower() or (Path.home() / ".cursor").exists()

    def auth(self, binary=None):
        return "ok" if os.environ.get("CURSOR_API_KEY") else "not checked"

    def command(self, binary, spec, mode, prompt, cwd, out_file):
        argv = [binary, "-p", prompt, "--model", spec["model"], "--output-format", "json"]
        if mode == "write":
            argv.append("--force")
        return argv, None

    def final(self, stdout, out_file):
        data = _last_json(stdout)
        if data is None:
            return ANSI.sub("", stdout or "").strip(), False
        return str(data.get("result") or data.get("response") or "").strip(), bool(data.get("is_error"))


class Kiro(Provider):
    name, label, vendor = "kiro", "Kiro", "kiro"
    bins = ("kiro-cli",)
    tiers = {"S4": None, "S3": None, "S2": {"model": "auto"}, "S1": {"model": "auto"}}
    notes = ("Uses your `kiro-cli login` session, or KIRO_API_KEY where set. Monthly credit usage is "
             "read with `/usage`. Auto covers build and mechanical work.")

    def auth(self, binary=None):
        if os.environ.get("KIRO_API_KEY"):
            return "ok"
        if binary:
            code, out = _run([binary, "whoami"], timeout=10)
            low = ANSI.sub("", out).lower()
            if code == 0 and "not logged in" not in low and low.strip():
                return "ok"
            if "not logged in" in low or "login" in low:
                return "not signed in"
        return "not checked"

    probe_minutes = 15
    sign_in = "kiro-cli login"
    docs = "https://kiro.dev/docs/cli/"

    def limit_probe(self, binary):
        """`/usage` in a non-interactive chat prints the monthly credit report."""
        text = ""
        for extra in (["--v2"], []):
            code, out = _run([binary, "chat", "--no-interactive", "/usage"] + extra, timeout=20)
            text = ANSI.sub("", out)
            if extra and re.search(r"unexpected argument|unrecognized|unknown (option|argument)", text, re.I):
                continue
            break
        return parse_kiro_usage(text)

    def command(self, binary, spec, mode, prompt, cwd, out_file):
        return [binary, "chat", "--v3", "--no-interactive", "--trust-all-tools",
                "--model", spec["model"]], prompt


def parse_kiro_usage(text: str, today: Optional[date] = None) -> Optional[dict]:
    """Monthly credits from Kiro's /usage report: '(12.50 of 50 covered in plan)', or the bar's N%."""
    used = None
    m = re.search(r"\(\s*([\d.,]+)\s+of\s+([\d.,]+)\s+covered in plan", text, re.I)
    if m:
        spent, total = (float(x.replace(",", "")) for x in m.groups())
        used = round(spent / total * 100, 1) if total > 0 else None
    if used is None:
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", text[text.lower().find("monthly credits"):] if
                      "monthly credits" in text.lower() else "")
        used = float(m.group(1)) if m else None
    if used is None:
        return None
    resets = None
    m = re.search(r"resets on (\d{1,2})/(\d{1,2})", text, re.I)
    if m:
        today = today or date.today()
        month, day = int(m.group(1)), int(m.group(2))
        try:
            when = date(today.year, month, day)
            if when < today:
                when = date(today.year + 1, month, day)
            resets = when.isoformat() + "T00:00:00+00:00"
        except ValueError:
            pass
    return {"windows": {"month": {"used": used, "resets_at": resets}}}


PROVIDERS: Dict[str, Provider] = {p.name: p for p in (Claude(), Codex(), Antigravity(), Cursor(), Kiro())}


def is_auto(spec: Optional[dict]) -> bool:
    return bool(spec) and str(spec.get("model", "")).lower() == "auto"
