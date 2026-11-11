#!/usr/bin/env python3
"""gitcommit helper: read a working tree, make clean commits under your own name, push them.

  inspect                       what changed, how this repository writes commits, what blocks a commit
  init                          turn the current folder into a git repository (no commit is made)
  commit --subject S -- PATH…   stage exactly these paths and commit them
  commit --subject S --staged   commit what is staged, as it is
  check [--since REV]           verify the commits made since REV (author, message, attribution)
  push [--since REV]            check, then push the current branch to its remote (never forced)

Everything prints JSON. The helper never rewrites history, never forces a push, never skips git
hooks and never changes git configuration. Python 3.8+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

__version__ = "0.1.0"

SUBJECT_MAX = 72            # hard limit; the skill aims for 50
BODY_MAX_LINES = 5
BODY_LINE_MAX = 100         # lines holding a URL are exempt
LARGE_BYTES = 5 * 1024 * 1024
MAX_CHANGES = 400           # entries listed by `inspect`
MAX_FLAGS = 60
HISTORY = 50                # commits read to learn the repository's style

CONVENTIONAL = re.compile(r"^(?P<type>[a-z]+)(\((?P<scope>[^()\s]+)\))?(?P<bang>!)?: (?P<desc>\S.*)$")
CONVENTIONAL_TYPES = {"feat", "fix", "docs", "style", "refactor", "perf", "test", "build", "ci", "chore", "revert"}
GITMOJI = re.compile(r"^(:[a-z0-9_+-]+:|[☀-➿\U0001f000-\U0001faff])")
TICKET = re.compile(r"^\[?(?P<key>[A-Z][A-Z0-9]{1,9}-\d+|#\d+)\]?[:\s]")
BRANCH_KEY = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]{1,9}-\d+)(?![A-Za-z0-9])")

# Lines that credit anyone or anything but the committer. A commit made by this skill never has one.
ATTRIBUTION = [
    (re.compile(r"^\s*co-authored-by\s*:", re.I), "a Co-authored-by trailer"),
    (re.compile(r"\b(generated|created|written|authored|made|produced)\s+(with|by|using)\b.{0,40}"
                r"\b(claude|codex|copilot|cursor|gemini|chatgpt|gpt|anthropic|openai|kiro|antigravity|"
                r"aider|windsurf|devin|ai|llm|an? (ai|agent|assistant))\b", re.I), "an AI attribution line"),
    (re.compile(r"noreply@anthropic\.com|\U0001f916"), "an AI attribution line"),
]
SIGNOFF = re.compile(r"^\s*signed-off-by\s*:\s*(.*)$", re.I)

SECRETS = [
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}")),
    ("GitLab token", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}")),
    ("Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9\-]{10,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("API key", re.compile(r"\bsk-(ant-|proj-|live-)?[A-Za-z0-9_\-]{24,}")),
    ("Stripe live key", re.compile(r"\b[sr]k_live_[A-Za-z0-9]{20,}")),
    ("npm token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
]
CONFLICT_MARKER = re.compile(r"^(<{7}|>{7}) \S")
SENSITIVE_NAME = re.compile(
    r"^(\.env(\.(?!example$|sample$|template$|dist$|defaults$)[^.]+)*|id_(rsa|dsa|ecdsa|ed25519)|\.netrc|\.htpasswd|"
    r"credentials(\.json)?|service[-_]?account.*\.json|secrets?\.(json|ya?ml|toml|env)|"
    r".*\.(pem|key|p12|pfx|jks|keystore|kdbx))$", re.I)
JUNK_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
JUNK_SUFFIXES = (".pyc", ".pyo", ".swp", ".swo", ".orig", ".rej", ".log", "~")
JUNK_DIRS = {"node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv",
             ".next", ".nuxt", ".turbo", ".gradle", ".terraform", ".idea", "coverage", ".parcel-cache"}


class Stop(Exception):
    """An expected failure: printed as JSON and returned as exit code 2."""

    def __init__(self, code: str, text: str, **extra):
        super().__init__(text)
        self.payload = {"ok": False, "error": code, "text": text, **extra}


# -- git -------------------------------------------------------------------------------------

def _env(english: bool = False) -> Dict[str, str]:
    """The environment git runs in. Identity variables set by a host or a CI are removed, so the
    author and the committer always come from the user's own git configuration."""
    env = {k: v for k, v in os.environ.items()
           if not re.match(r"GIT_(AUTHOR|COMMITTER)_(NAME|EMAIL|DATE)$", k)}
    env["GIT_TERMINAL_PROMPT"] = "0"          # fail instead of waiting for a password nobody can type
    env.setdefault("GIT_EDITOR", "true")
    if english:
        env["LANGUAGE"] = "en"                # messages we have to read
    return env


def git(cwd: Path, *args: str, timeout: int = 60, english: bool = False,
        stdin: Optional[str] = None, extra_env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
                           env={**_env(english), **(extra_env or {})}, input=stdin, encoding="utf-8",
                           errors="replace",
                           **({} if stdin is not None else {"stdin": subprocess.DEVNULL}))
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timed out after %d seconds" % timeout
    except OSError as e:
        return 127, "", str(e)


def out(cwd: Path, *args: str) -> Optional[str]:
    code, stdout, _ = git(cwd, *args)
    return stdout.strip() if code == 0 and stdout.strip() else None


def find_repo(start: Path) -> Optional[Path]:
    top = out(start, "rev-parse", "--show-toplevel")
    return Path(top) if top else None


def need_repo(start: Path) -> Path:
    repo = find_repo(start)
    if repo is None:
        if out(start, "rev-parse", "--is-bare-repository") == "true":
            raise Stop("bare-repository", "this is a bare repository: there is no working tree to commit")
        raise Stop("not-a-repository", "this folder is not a git repository", fix="run `init` first")
    return repo


def identity(repo: Path) -> Optional[Dict[str, str]]:
    name, email = out(repo, "config", "user.name"), out(repo, "config", "user.email")
    return {"name": name, "email": email} if name and email else None


def in_progress(repo: Path) -> Optional[str]:
    gitdir = out(repo, "rev-parse", "--absolute-git-dir")
    if not gitdir:
        return None
    d = Path(gitdir)
    for marker, what in (("MERGE_HEAD", "merge"), ("rebase-merge", "rebase"), ("rebase-apply", "rebase"),
                         ("CHERRY_PICK_HEAD", "cherry-pick"), ("REVERT_HEAD", "revert"), ("BISECT_LOG", "bisect")):
        if (d / marker).exists():
            return what
    return None


def remote_info(repo: Path, branch: Optional[str]) -> dict:
    """Where this branch pushes: its upstream when it has one, else `origin` or the only remote."""
    remotes = (out(repo, "remote") or "").split()
    upstream = out(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}") if branch else None
    remote = out(repo, "config", "branch.%s.remote" % branch) if branch and upstream else None
    if not remote or remote == ".":
        remote = "origin" if "origin" in remotes else remotes[0] if len(remotes) == 1 else None
    url = out(repo, "remote", "get-url", "--push", remote) if remote else None
    info = {"remotes": remotes, "remote": remote, "upstream": upstream,
            "url": re.sub(r"(?<=://)[^/@\s]+@", "", url) if url else None, "ahead": 0, "behind": 0}
    head = out(repo, "rev-parse", "-q", "--verify", "HEAD")
    if upstream:
        counts = (out(repo, "rev-list", "--left-right", "--count", "%s...HEAD" % upstream) or "0\t0").split()
        info["behind"], info["ahead"] = int(counts[0]), int(counts[1])
    elif head:
        info["ahead"] = int(out(repo, "rev-list", "--count", "HEAD", "--not", "--remotes") or 0)
    return info


# -- changes ---------------------------------------------------------------------------------

def _status(repo: Path) -> List[dict]:
    code, raw, err = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=normal")
    if code != 0:
        raise Stop("git-failed", "git status failed", output=err.strip()[-500:])
    parts = raw.split("\0")
    entries, i = [], 0
    while i < len(parts):
        item = parts[i]
        i += 1
        if len(item) < 4:
            continue
        x, y, path = item[0], item[1], item[3:]
        entry = {"path": path, "staged": x not in " ?", "unstaged": y not in " ?"}
        if x in "RC":                                  # the original path follows as its own field
            entry["from"] = parts[i] if i < len(parts) else None
            i += 1
        if x == "?" and y == "?":
            entry["change"] = "untracked"
        elif x + y in ("DD", "AU", "UD", "UA", "DU", "AA", "UU"):
            entry["change"] = "conflict"
        elif "D" in (x, y):
            entry["change"] = "deleted"
        elif x == "R":
            entry["change"] = "renamed"
        elif x == "A":
            entry["change"] = "added"
        else:
            entry["change"] = "modified"
        entries.append(entry)
    return entries


def _numstat(repo: Path, has_head: bool) -> Dict[str, Tuple[Optional[int], Optional[int]]]:
    args = ["diff", "--numstat", "-z", "--no-renames"] + (["HEAD"] if has_head else ["--cached"])
    code, raw, _ = git(repo, *args)
    stats = {}
    for item in raw.split("\0") if code == 0 else []:
        cols = item.split("\t", 2)
        if len(cols) == 3:
            binary = cols[0] == "-"
            stats[cols[2]] = (None, None) if binary else (int(cols[0]), int(cols[1]))
    return stats


def _walk(base: Path, limit: int = 2000) -> List[Path]:
    """Files under an untracked directory, bounded; directories that are never source are not entered."""
    found, stack = [], [base]
    while stack and len(found) < limit:
        d = stack.pop()
        try:
            children = sorted(d.iterdir())
        except OSError:
            continue
        for c in children:
            if c.is_symlink():
                continue
            if c.is_dir():
                if c.name not in JUNK_DIRS and c.name != ".git":
                    stack.append(c)
            elif len(found) < limit:
                found.append(c)
    return found


def _is_junk(path: str) -> bool:
    parts = Path(path).parts
    name = parts[-1] if parts else ""
    return bool(set(parts) & JUNK_DIRS) or name in JUNK_NAMES or name.endswith(JUNK_SUFFIXES)


def _scan_text(text: str) -> Optional[str]:
    for kind, rx in SECRETS:
        if rx.search(text):
            return kind
    return None


DIFF = ("-c", "core.quotePath=false", "diff", "-U0", "--no-color", "--no-ext-diff", "--no-renames",
        "--src-prefix=a/", "--dst-prefix=b/")


def _scan_diff(diff: str) -> List[dict]:
    """Secrets and conflict markers on the added lines of a unified diff (-U0)."""
    flags, path, line = [], None, 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = raw[6:] if raw.startswith("+++ b/") else None
            continue
        if raw.startswith("@@"):
            m = re.match(r"@@ -\S+ \+(\d+)", raw)
            line = int(m.group(1)) if m else 0
            continue
        if not path or not raw.startswith("+") or raw.startswith("+++"):
            continue
        text = raw[1:20001]
        kind = _scan_text(text)
        if kind:
            flags.append({"path": path, "kind": "secret", "detail": kind, "line": line})
        elif CONFLICT_MARKER.match(text):
            flags.append({"path": path, "kind": "conflict-marker", "detail": "unresolved merge marker", "line": line})
        line += 1
    return flags


def _scan_file(repo: Path, path: str) -> List[dict]:
    """Checks for a file git does not know yet: its name, its size, its content."""
    flags = []
    full = repo / path
    name = Path(path).name
    if _is_junk(path):
        return [{"path": path, "kind": "junk", "detail": "editor, cache or dependency file that belongs in .gitignore"}]
    if SENSITIVE_NAME.match(name):
        flags.append({"path": path, "kind": "sensitive-file", "detail": "file name suggests credentials"})
    try:
        size = full.stat().st_size
    except OSError:
        return flags
    if size > LARGE_BYTES:
        flags.append({"path": path, "kind": "large", "detail": "%.1f MB" % (size / 1048576)})
        return flags
    try:
        with open(full, "rb") as fh:
            data = fh.read(1024 * 1024)
    except OSError:
        return flags
    if b"\0" in data[:8000]:
        return flags                                   # binary
    for n, text in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
        kind = _scan_text(text[:20000])
        if kind:
            flags.append({"path": path, "kind": "secret", "detail": kind, "line": n})
            break
    return flags


def _dedupe(flags: List[dict]) -> List[dict]:
    seen, result = set(), []
    for f in flags:
        key = (f["path"], f["kind"])
        if key not in seen:
            seen.add(key)
            result.append(f)
    return result[:MAX_FLAGS]


def changes(repo: Path, has_head: bool) -> Tuple[List[dict], List[dict]]:
    """(entries, flags) for everything that differs from the last commit."""
    entries = _status(repo)
    stats = _numstat(repo, has_head)
    flags: List[dict] = []
    for e in entries:
        path = e["path"]
        if e["change"] == "untracked":
            if path.endswith("/"):
                files = _walk(repo / path)
                e["files"] = len(files)
                if _is_junk(path.rstrip("/")):
                    flags.append({"path": path, "kind": "junk",
                                  "detail": "cache or dependency folder that belongs in .gitignore"})
                    continue
                for f in files:
                    flags += _scan_file(repo, f.relative_to(repo).as_posix())
            else:
                found = _scan_file(repo, path)
                flags += found
                if not any(f["kind"] in ("junk", "large") for f in found):
                    try:
                        with open(repo / path, "rb") as fh:
                            data = fh.read(1024 * 1024)
                        e["binary"] = b"\0" in data[:8000]
                        if not e["binary"]:
                            e["added"], e["deleted"] = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0), 0
                    except OSError:
                        pass
            continue
        added, deleted = stats.get(path, (0, 0))
        if added is None:
            e["binary"] = True
        else:
            e["added"], e["deleted"] = added, deleted
        if e["change"] in ("added", "renamed") and SENSITIVE_NAME.match(Path(path).name):
            flags.append({"path": path, "kind": "sensitive-file", "detail": "file name suggests credentials"})
        if e["change"] in ("added", "renamed"):       # a new file that was staged by hand
            try:
                size = (repo / path).stat().st_size
                if size > LARGE_BYTES:
                    flags.append({"path": path, "kind": "large", "detail": "%.1f MB" % (size / 1048576)})
            except OSError:
                pass
    code, diff, _ = git(repo, *DIFF, *(["HEAD"] if has_head else ["--cached"]), timeout=120)
    if code == 0:
        flags += _scan_diff(diff)
    return entries, _dedupe(flags)


# -- style -----------------------------------------------------------------------------------

def style(repo: Path, branch: Optional[str]) -> dict:
    """How this repository writes commit messages, learned from its recent history."""
    code, raw, _ = git(repo, "log", "-n", str(HISTORY), "--no-merges", "--format=%s%x1f%b%x1e")
    commits = [c.strip("\n").split("\x1f", 1) for c in raw.split("\x1e") if c.strip()] if code == 0 else []
    subjects = [c[0].strip() for c in commits if c[0].strip()]
    n = len(subjects)
    # the newest subjects, verbatim: the agent reads the format and the language from them
    result = {"commits_read": n, "convention": "none", "examples": [s[:100] for s in subjects[:10]]}
    key = BRANCH_KEY.search(branch or "")
    if key:
        result["branch_issue_key"] = key.group(1)
    if n < 3:
        result["note"] = "too little history to follow: use Conventional Commits"
        return result
    conv = [m for m in (CONVENTIONAL.match(s) for s in subjects) if m and m.group("type") in CONVENTIONAL_TYPES]
    emoji = sum(1 for s in subjects if GITMOJI.match(s))
    ticket = sum(1 for s in subjects if TICKET.match(s))
    if len(conv) / n >= 0.6:
        result["convention"] = "conventional"
        result["types"] = [t for t, _ in Counter(m.group("type") for m in conv).most_common()]
        scopes = Counter(m.group("scope") for m in conv if m.group("scope"))
        result["scopes"] = [s for s, _ in scopes.most_common(10)]
        result["scope_share"] = round(sum(scopes.values()) / len(conv), 2)
        starts = [m.group("desc")[0] for m in conv]
    elif emoji / n >= 0.6:
        result["convention"] = "gitmoji"
        starts = []
    elif ticket / n >= 0.6:
        result["convention"] = "ticket-prefix"
        starts = []
    else:
        result["convention"] = "plain"
        starts = [s[0] for s in subjects]
    letters = [c for c in starts if c.isalpha()]
    if letters:
        result["first_letter"] = "upper" if sum(c.isupper() for c in letters) * 2 > len(letters) else "lower"
    lengths = sorted(len(s) for s in subjects)
    result["median_subject_length"] = lengths[n // 2]
    result["ticket_share"] = round(ticket / n, 2)
    result["body_share"] = round(sum(1 for c in commits if len(c) > 1 and _prose(c[1])) / n, 2)
    result["signoff"] = sum(1 for c in commits
                            if any(SIGNOFF.match(ln) for ln in (c[1] if len(c) > 1 else "").splitlines())) / n >= 0.5
    return result


def recent(repo: Path, count: int = 8) -> List[dict]:
    """The last commits on this branch with the files they touched, newest first: what the new
    commits continue, and what is already recorded. `pushed` is false for commits no remote has."""
    code, raw, _ = git(repo, "-c", "core.quotePath=false", "log", "-n", str(count), "--no-renames",
                       "--name-only", "--format=%x1e%H%x1f%s%x1f%cI")
    if code != 0:
        return []
    local = set((out(repo, "rev-list", "-n", "200", "HEAD", "--not", "--remotes") or "").split())
    rows = []
    for chunk in raw.split("\x1e"):
        head, _, rest = chunk.partition("\n")
        f = head.split("\x1f")
        if len(f) != 3:
            continue
        files = [ln for ln in rest.splitlines() if ln.strip()]
        rows.append({"sha": f[0][:8], "subject": f[1][:100], "date": f[2][:10], "pushed": f[0] not in local,
                     "files": files[:8], **({"files_omitted": len(files) - 8} if len(files) > 8 else {})})
    return rows


def _prose(body: str) -> bool:
    """True when a commit body has text of its own, not only trailers."""
    return any(ln.strip() and not re.match(r"^[A-Za-z-]+: \S", ln) for ln in (body or "").splitlines())


def tooling(repo: Path) -> dict:
    """Things that run or judge a commit in this repository. Informational: nothing is bypassed."""
    names = ("commitlint.config.js", "commitlint.config.cjs", "commitlint.config.mjs", "commitlint.config.ts",
             ".commitlintrc", ".commitlintrc.json", ".commitlintrc.yml", ".commitlintrc.yaml", ".commitlintrc.js",
             ".commitlintrc.cjs")
    lint = next((n for n in names if (repo / n).is_file()), None)
    if not lint and (repo / "package.json").is_file():
        try:
            if "commitlint" in json.loads((repo / "package.json").read_text(encoding="utf-8")):
                lint = "package.json"
        except (OSError, ValueError):
            pass
    hooks_dir = out(repo, "rev-parse", "--git-path", "hooks")
    hooks = []
    if hooks_dir:
        d = (repo / hooks_dir) if not os.path.isabs(hooks_dir) else Path(hooks_dir)
        hooks = [h for h in ("pre-commit", "prepare-commit-msg", "commit-msg", "pre-push")
                 if (d / h).is_file() and os.access(d / h, os.X_OK)]
    managers = [n for n, marker in (("husky", ".husky"), ("pre-commit", ".pre-commit-config.yaml"),
                                    ("lefthook", "lefthook.yml"), ("lefthook", ".lefthook.yml"))
                if (repo / marker).exists()]
    return {"commitlint": lint, "hooks": hooks, "hook_managers": sorted(set(managers)),
            "gitignore": (repo / ".gitignore").is_file()}


# -- messages --------------------------------------------------------------------------------

def message_problems(subject: str, body: str, who: Optional[Dict[str, str]]) -> List[str]:
    problems = []
    subject = subject or ""
    if not subject.strip():
        problems.append("the subject is empty")
    if "\n" in subject.strip():
        problems.append("the subject has more than one line")
    if len(subject) > SUBJECT_MAX:
        problems.append("the subject is %d characters (limit %d, aim for 50)" % (len(subject), SUBJECT_MAX))
    if subject.rstrip().endswith("."):
        problems.append("the subject ends with a period")
    lines = [ln for ln in (body or "").splitlines() if ln.strip()]
    if len(lines) > BODY_MAX_LINES:
        problems.append("the body is %d lines (limit %d): say only what the subject cannot" % (len(lines), BODY_MAX_LINES))
    for ln in lines:
        if len(ln) > BODY_LINE_MAX and "://" not in ln:
            problems.append("a body line is %d characters (limit %d)" % (len(ln), BODY_LINE_MAX))
            break
    for ln in [subject] + lines:
        rules = ATTRIBUTION if ln is not subject else ATTRIBUTION[:1] + ATTRIBUTION[2:]
        hit = next((what for rx, what in rules if rx.search(ln)), None)
        if hit:
            problems.append("the message has %s: %s" % (hit, ln.strip()[:80]))
            continue
        m = SIGNOFF.match(ln)
        if m and who and who["email"].lower() not in m.group(1).lower():
            problems.append("the message is signed off by someone else: %s" % m.group(1).strip()[:80])
    return problems


def commit_problems(c: dict, who: Optional[Dict[str, str]]) -> List[str]:
    problems = message_problems(c["subject"], c["body"], who)
    if who:
        for role in ("author", "committer"):
            if (c[role + "_name"], c[role + "_email"].lower()) != (who["name"], who["email"].lower()):
                problems.append("the %s is %s <%s>, not %s <%s>" % (role, c[role + "_name"], c[role + "_email"],
                                                                     who["name"], who["email"]))
    return problems


def read_commits(repo: Path, revs: List[str]) -> List[dict]:
    code, raw, err = git(repo, "log", "--format=%H%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%s%x1f%b%x1e", *revs)
    if code != 0:
        raise Stop("bad-revision", "cannot read commits: %s" % (err.strip().splitlines() or ["?"])[-1])
    commits = []
    for chunk in raw.split("\x1e"):
        f = chunk.strip("\n").split("\x1f")
        if len(f) == 7:
            commits.append({"sha": f[0], "author_name": f[1], "author_email": f[2], "committer_name": f[3],
                            "committer_email": f[4], "subject": f[5], "body": f[6].strip()})
    return commits


def run_check(repo: Path, since: Optional[str]) -> dict:
    """Problems in the commits made since `since` (a commit, or "root" for a repository that had none)."""
    if not out(repo, "rev-parse", "-q", "--verify", "HEAD"):
        return {"ok": True, "range": None, "commits": []}
    if since in (None, "", "root", "none", "null"):
        revs, label = ["HEAD"], "every commit on this branch"
    else:
        revs, label = ["%s..HEAD" % since], "%s..HEAD" % since[:12]
    who = identity(repo)
    rows = []
    for c in read_commits(repo, revs):
        rows.append({"sha": c["sha"][:8], "subject": c["subject"], "problems": commit_problems(c, who)})
    return {"ok": not any(r["problems"] for r in rows), "range": label, "commits": rows}


# -- commands --------------------------------------------------------------------------------

def cmd_inspect(args) -> dict:
    start = Path(args.repo or os.getcwd()).resolve()
    repo = find_repo(start)
    if repo is None:
        bare = out(start, "rev-parse", "--is-bare-repository") == "true"
        return {"version": __version__, "repository": None, "folder": str(start),
                "blockers": [{"code": "bare-repository", "text": "this is a bare repository: nothing to commit here"}
                             if bare else
                             {"code": "not-a-repository", "text": "this folder is not a git repository",
                              "fix": "run `init`, then `inspect` again"}]}
    head = out(repo, "rev-parse", "-q", "--verify", "HEAD")
    branch = out(repo, "symbolic-ref", "-q", "--short", "HEAD")
    who = identity(repo)
    entries, flags = changes(repo, bool(head))
    blockers = []
    if not who:
        blockers.append({"code": "no-identity", "text": "git does not know who you are (user.name / user.email)",
                         "fix": 'git config --global user.name "Your Name" && git config --global user.email you@example.com'})
    op = in_progress(repo)
    if op:
        blockers.append({"code": "in-progress", "text": "a %s is in progress" % op,
                         "fix": "finish or abort the %s first" % op})
    if any(e["change"] == "conflict" for e in entries):
        blockers.append({"code": "conflicts", "text": "there are unresolved merge conflicts",
                         "fix": "resolve them: " + ", ".join(e["path"] for e in entries if e["change"] == "conflict")[:300]})
    if head and not branch and not op:
        blockers.append({"code": "detached-head", "text": "HEAD is detached: commits made here belong to no branch",
                         "fix": "git switch <branch>, or git switch -c <new-branch>"})
    remote = remote_info(repo, branch)
    flagged = {f["path"] for f in flags}
    return {
        "version": __version__, "repository": str(repo), "branch": branch, "head": head or "root",
        "first_commit": not head, "identity": who, **remote,
        "can_push": bool(remote["remote"] and branch),
        "nothing_to_commit": not entries,
        "staged": sum(1 for e in entries if e["staged"]),
        "totals": {"paths": len(entries), "added": sum(e.get("added") or 0 for e in entries),
                   "deleted": sum(e.get("deleted") or 0 for e in entries),
                   "flagged": len(flagged)},
        "changes": entries[:MAX_CHANGES], "changes_omitted": max(0, len(entries) - MAX_CHANGES),
        "flags": flags, "style": style(repo, branch), "recent": recent(repo) if head else [],
        "tooling": tooling(repo), "blockers": blockers,
    }


def cmd_init(args) -> dict:
    start = Path(args.repo or os.getcwd()).resolve()
    if find_repo(start) is not None:
        raise Stop("already-a-repository", "this folder is already inside a git repository: %s" % find_repo(start))
    if not start.is_dir():
        raise Stop("no-folder", "no such folder: %s" % start)
    if start == Path.home() or start.parent == start:
        raise Stop("refused", "refusing to turn %s into a repository: run this inside a project folder" % start)
    extra = [] if out(start, "config", "init.defaultBranch") else ["-b", "main"]
    code, _, err = git(start, "init", "-q", *extra)
    if code != 0 and extra:                            # git older than 2.28 has no -b
        code, _, err = git(start, "init", "-q")
    if code != 0:
        raise Stop("git-failed", "git init failed", output=err.strip()[-500:])
    return {"ok": True, "repository": str(start), "branch": out(start, "symbolic-ref", "-q", "--short", "HEAD"),
            "gitignore": (start / ".gitignore").is_file(), "next": "run `inspect`"}


def _remaining(repo: Path) -> int:
    return len(_status(repo))


def cmd_commit(args) -> dict:
    repo = need_repo(Path(args.repo or os.getcwd()).resolve())
    who = identity(repo)
    if not who:
        raise Stop("no-identity", "git does not know who you are (user.name / user.email)")
    op = in_progress(repo)
    if op:
        raise Stop("in-progress", "a %s is in progress: finish or abort it first" % op)
    head = out(repo, "rev-parse", "-q", "--verify", "HEAD")
    if head and not out(repo, "symbolic-ref", "-q", "--short", "HEAD"):
        raise Stop("detached-head", "HEAD is detached: switch to a branch first")
    subject = (args.subject or "").strip()
    body = "\n".join(line.rstrip() for part in (args.body or []) for line in part.splitlines()).strip()
    problems = message_problems(subject, body, who)
    if problems:
        raise Stop("bad-message", "the commit message does not meet the rules; nothing was committed",
                   problems=problems)
    if args.staged and args.paths:
        raise Stop("usage", "give either --staged or paths, not both")
    if not args.staged:
        if not args.paths:
            raise Stop("usage", "name the paths this commit holds after `--`, or pass --staged")
        git(repo, "reset", "-q")                       # the index holds this commit and nothing else
        code, _, err = git(repo, "add", "-A", "--", *args.paths)
        if code != 0:
            raise Stop("bad-path", "git could not stage these paths", output=err.strip()[-500:])
    staged = [p for p in (out(repo, "diff", "--cached", "--name-only", "--no-renames", "-z") or "").split("\0") if p]
    if not staged:
        raise Stop("nothing-staged", "nothing to commit for these paths: they have no changes")
    if not args.include_flagged:
        code, diff, _ = git(repo, *DIFF, "--cached", timeout=120)
        flags = _scan_diff(diff) if code == 0 else []
        new = [p for p in (out(repo, "diff", "--cached", "--name-only", "--no-renames", "-z", "--diff-filter=A") or "").split("\0") if p]
        for p in new:                                  # name and size rules: new files only
            if _is_junk(p):
                flags.append({"path": p, "kind": "junk", "detail": "belongs in .gitignore"})
            elif SENSITIVE_NAME.match(Path(p).name):
                flags.append({"path": p, "kind": "sensitive-file", "detail": "file name suggests credentials"})
            try:
                if (repo / p).is_file() and (repo / p).stat().st_size > LARGE_BYTES:
                    flags.append({"path": p, "kind": "large", "detail": "%.1f MB" % ((repo / p).stat().st_size / 1048576)})
            except OSError:
                pass
        flags = _dedupe(flags)
        if flags:
            if not args.staged:
                git(repo, "reset", "-q")
            raise Stop("flagged", "these paths hold something that should not be committed; nothing was committed",
                       flags=flags, fix="leave them out, or pass --include-flagged when the user said to include them")
    cmd = ["commit", "-q", "-m", subject] + (["-m", body] if body else []) + (["--signoff"] if args.signoff else [])
    code, stdout, stderr = git(repo, *cmd, timeout=300)
    if code != 0:
        tail = "\n".join(x for x in (stdout.strip(), stderr.strip()) if x)[-1500:]
        raise Stop("commit-failed", "git commit failed (a hook, a signing problem or a commit-msg rule); "
                                    "nothing was bypassed", output=tail, staged=len(staged))
    made = read_commits(repo, ["-1", "HEAD"])[0]
    result = {"ok": True, "sha": made["sha"][:8], "subject": made["subject"], "files": len(staged),
              "author": "%s <%s>" % (made["author_name"], made["author_email"]), "remaining": _remaining(repo)}
    after = commit_problems(made, who)
    if after:
        result["problems"] = after                    # a hook rewrote the message or the identity
    return result


def cmd_check(args) -> dict:
    repo = need_repo(Path(args.repo or os.getcwd()).resolve())
    return run_check(repo, args.since)


# -- signing in ------------------------------------------------------------------------------

def _transport(url: Optional[str]) -> Tuple[str, Optional[str], Optional[str]]:
    """(transport, host, path) of a remote URL: https://host/owner/repo.git, git@host:owner/repo.git …"""
    url = url or ""
    m = re.match(r"^(https?)://(?:[^/@]+@)?([^/:]+)(?::\d+)?/(.+?)/?$", url)
    if m:
        return m.group(1), m.group(2), m.group(3)
    m = re.match(r"^ssh://(?:[^/@]+@)?([^/:]+)(?::\d+)?/(.+?)/?$", url) or re.match(r"^(?:[^/@]+@)?([^/:]+):(?!//)(.+?)/?$", url)
    if m and "://" not in url.replace("ssh://", "", 1):
        return "ssh", m.group(1), m.group(2)
    return ("file" if url.startswith(("/", ".", "file://")) else "other"), None, None


def prompt_guard(repo: Path, ask: bool) -> Tuple[Dict[str, str], Optional[str]]:
    """(environment for the push, the password program git would have fallen back to).

    A push must never open a password dialog nobody asked for. Whatever was set up for git on
    purpose is left alone: credential helpers, GIT_ASKPASS, core.askPass, SSH keys and the SSH
    agent. What is switched off is the accident: with nothing else to ask, git borrows the
    desktop's SSH passphrase program (SSH_ASKPASS) and a username and password window appears in
    the middle of an agent run. `ask` lets it appear, because then the user asked for it."""
    explicit = os.environ.get("GIT_ASKPASS") or out(repo, "config", "core.askPass")
    borrowed = None if explicit else os.environ.get("SSH_ASKPASS") or None
    if ask:
        return {}, borrowed
    env = {"GCM_INTERACTIVE": "never"}                 # Git Credential Manager: no browser, no window
    silent = shutil.which("true")
    if not explicit and silent:
        env["GIT_ASKPASS"] = silent                    # answers nothing, so the push fails cleanly
    return env, borrowed


def _ssh_accepted(host: str) -> Optional[bool]:
    """Does this machine already hold an SSH key that `host` accepts? None when it cannot be told."""
    if not shutil.which("ssh") or host in ("localhost", "::1") or re.match(r"^(127\.|\[)", host):
        return None
    try:
        p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6", "-T", "git@" + host],
                           capture_output=True, text=True, timeout=12, stdin=subprocess.DEVNULL,
                           encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    text = (p.stdout + p.stderr).lower()
    if re.search(r"successfully authenticated|welcome to gitlab|authenticated via|logged in as|hi there", text):
        return True
    return False if re.search(r"permission denied|publickey", text) else None


def sign_in_help(repo: Path, remote: str, url: Optional[str], borrowed: Optional[str], asked: bool) -> dict:
    """Why the server said no, as far as this machine shows it, and what the user can do about it."""
    transport, host, path = _transport(url)
    helpers = sorted(set(filter(None, (out(repo, "config", "--get-all", "credential.helper") or "").splitlines()
                                + [out(repo, "config", "--get-urlmatch", "credential.helper", url or "") or ""])))
    facts = {"transport": transport, "host": host, "credential_helpers": helpers,
             "password_program": os.path.basename(borrowed) if borrowed else None, "asked": asked}
    options = []
    where = host or "the server"
    if transport in ("http", "https"):
        facts["why"] = ("git has no saved sign-in for %s here: no credential helper is configured" % where
                        if not helpers else
                        "the credential helper (%s) had nothing the server accepts for %s" % (", ".join(helpers), where))
        accepted = _ssh_accepted(host) if host else None
        facts["ssh_key_accepted"] = accepted
        if accepted and path:
            options.append({"what": "use the SSH key this machine already has for %s" % where,
                            "run": "git remote set-url %s git@%s:%s" % (remote, host, path),
                            "then": "call the skill again"})
        cli = "gh" if host and "github" in host else "glab" if host and "gitlab" in host else None
        if cli and shutil.which(cli):
            options.append({"what": "sign git in through the %s CLI" % cli,
                            "run": "%s auth login" % cli if cli == "glab" else "gh auth login && gh auth setup-git",
                            "then": "call the skill again"})
        if borrowed and not asked:
            options.append({"what": "let your desktop's password window (%s) ask you, and remember the answer"
                                    % os.path.basename(borrowed),
                            "run": "call the skill again with `ask`",
                            "then": "enter your user name and a personal access token, not your account password"})
        options.append({"what": "save a sign-in for git yourself" if not helpers else "refresh the saved sign-in",
                        "run": "run `git push` once in your own terminal"
                               + ("" if helpers else " after setting up a credential helper (git help credentials)"),
                        "then": "call the skill again"})
    elif transport == "ssh":
        facts["why"] = "%s did not accept an SSH key from this machine" % where
        options.append({"what": "load your key into the SSH agent, or add its public key to your account on %s" % where,
                        "run": "ssh-add" + ("  &&  ssh -T git@%s" % host if host else ""), "then": "call the skill again"})
    else:
        facts["why"] = "the remote refused the push"
    return {"sign_in": facts, "options": options}


def _classify(text: str) -> Tuple[str, str]:
    low = text.lower()
    if re.search(r"fetch first|non-fast-forward|tip of your current branch is behind|updates were rejected because the remote", low):
        return "rejected", ("the remote has commits you do not have; nothing was pushed and nothing was forced. "
                            "Bring them in (git pull --rebase), then call the skill again")
    if re.search(r"protected branch|gh006|pre-receive hook declined|you are not allowed to push|remote rejected", low):
        return "refused", "the server refused the push (protected branch or a server rule); push a branch and open a request"
    if re.search(r"authentication failed|could not read username|could not read password|permission denied|"
                 r"terminal prompts disabled|invalid username or (token|password)|access denied|not authorized|"
                 r"\b40[13]\b|repository not found", low):
        return "auth", "the server did not accept a sign-in from this machine"
    if re.search(r"could not resolve host|unable to access|connection (timed out|refused|reset)|network is unreachable|"
                 r"timed out|failed to connect|could not read from remote", low):
        return "offline", "the server could not be reached; the commits are safe locally, push again when you are online"
    return "error", "git push failed"


def cmd_push(args) -> dict:
    repo = need_repo(Path(args.repo or os.getcwd()).resolve())
    branch = out(repo, "symbolic-ref", "-q", "--short", "HEAD")
    if not out(repo, "rev-parse", "-q", "--verify", "HEAD"):
        raise Stop("no-commits", "there is nothing to push: this repository has no commits yet")
    if not branch:
        raise Stop("detached-head", "HEAD is detached: switch to a branch first")
    info = remote_info(repo, branch)
    remaining = _remaining(repo)
    remote = args.remote or info["remote"]
    if not remote:
        text = ("this repository has no remote; the commits stay local" if not info["remotes"] else
                "this repository has several remotes and none is called origin: say which one to use (--remote)")
        return {"ok": True, "status": "which-remote" if info["remotes"] else "no-remote", "pushed": False,
                "text": text, "branch": branch, "remotes": info["remotes"], "remaining": remaining,
                "fix": "push --remote <name>" if info["remotes"] else
                       "git remote add origin <url>, then call the skill again"}
    if remote not in info["remotes"]:
        raise Stop("no-such-remote", "no remote named %s (remotes: %s)" % (remote, ", ".join(info["remotes"])))
    if args.since is not None:
        checked = run_check(repo, args.since)
        if not checked["ok"]:
            raise Stop("check-failed", "nothing was pushed: the new commits do not meet the rules",
                       commits=[c for c in checked["commits"] if c["problems"]])
    elsewhere = bool(args.remote) and args.remote != info["remote"]
    if elsewhere:
        url = out(repo, "remote", "get-url", "--push", remote)
        info["url"] = re.sub(r"(?<=://)[^/@\s]+@", "", url) if url else None
    if info["upstream"] and not elsewhere:
        count = info["ahead"]
        if count == 0:
            return {"ok": True, "status": "up-to-date", "pushed": False, "branch": branch, "remote": remote,
                    "upstream": info["upstream"], "url": info["url"], "remaining": remaining}
        cmd = ["push", "--porcelain"]
    else:
        count = int(out(repo, "rev-list", "--count", "HEAD", "--not", "--remotes=%s" % remote) or 0)
        cmd = ["push", "--porcelain"] + ([] if info["upstream"] else ["--set-upstream"]) + [remote, branch]
    guard, borrowed = prompt_guard(repo, args.ask)
    code, stdout, stderr = git(repo, *cmd, timeout=args.timeout, english=True, extra_env=guard)
    text = "\n".join(x for x in (stdout.strip(), stderr.strip()) if x)
    if code != 0:
        status, hint = _classify(text) if code != 124 else ("offline", "the push timed out; the commits are safe locally")
        failed = {"ok": False, "status": status, "pushed": False, "text": hint, "branch": branch, "remote": remote,
                  "url": info["url"], "unpushed": count, "output": text[-1200:], "remaining": remaining}
        if status == "auth":
            failed.update(sign_in_help(repo, remote, info["url"], borrowed, args.ask))
            failed["text"] = "%s; nothing was pushed and the commits are safe locally" % failed["sign_in"]["why"]
        return failed
    now = remote_info(repo, branch)
    links = re.findall(r"https?://\S+", "\n".join(ln for ln in stderr.splitlines() if ln.startswith("remote:")))
    return {"ok": True, "status": "pushed", "pushed": True, "branch": branch, "remote": remote,
            "upstream": now["upstream"], "url": info["url"], "commits": count,
            "set_upstream": not info["upstream"], "remaining": remaining,
            **({"link": links[0]} if links else {})}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="gitcommit", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version="gitcommit " + __version__)
    ap.add_argument("--repo", help="folder to work in (default: the current directory)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("inspect").set_defaults(fn=cmd_inspect)
    sub.add_parser("init").set_defaults(fn=cmd_init)

    s = sub.add_parser("commit")
    s.add_argument("--subject", required=True, help="one line, at most %d characters, no period" % SUBJECT_MAX)
    s.add_argument("--body", action="append", help="one short body line (repeatable); most commits need none")
    s.add_argument("--staged", action="store_true", help="commit what is staged instead of naming paths")
    s.add_argument("--signoff", action="store_true", help="add your own Signed-off-by (for repositories that use it)")
    s.add_argument("--include-flagged", action="store_true",
                   help="commit paths that were flagged (secret, large, junk); only when the user said so")
    s.add_argument("paths", nargs="*", help="the paths of this commit, after `--`")
    s.set_defaults(fn=cmd_commit)

    s = sub.add_parser("check")
    s.add_argument("--since", help="the `head` that `inspect` reported before the run (or `root`)")
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("push")
    s.add_argument("--since", help="check the commits made since this revision before pushing")
    s.add_argument("--remote", help="push to this remote instead of the branch's own")
    s.add_argument("--ask", action="store_true",
                   help="let git open the system's password window; only when the user asked for it")
    s.add_argument("--timeout", type=int, default=180, help="seconds (default 180)")
    s.set_defaults(fn=cmd_push)

    args = ap.parse_args(argv)
    try:                                               # commit subjects are not always ASCII
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if not _have_git():
        data, code = {"ok": False, "error": "no-git", "text": "git is not installed or not on PATH"}, 2
    else:
        try:
            data = args.fn(args)
            code = 0 if data.get("ok", True) else 1
        except Stop as e:
            data, code = e.payload, 2
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return code


def _have_git() -> bool:
    try:
        return subprocess.run(["git", "--version"], capture_output=True).returncode == 0
    except OSError:
        return False


if __name__ == "__main__":
    sys.exit(main())
