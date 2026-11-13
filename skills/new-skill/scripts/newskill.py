#!/usr/bin/env python3
"""new-skill: draft, check and install an agent skill for Claude Code, Codex, Antigravity, Kiro.

  newskill.py where [--name N]                 providers found here, and whether a name is free
  newskill.py draft --name N --description D   start a draft folder with SKILL.md in it
  newskill.py check N|DIR                      is the draft a well-formed skill?
  newskill.py install N|DIR --in P [--also a,b | --all] [--dest DIR] [--replace]
  newskill.py drafts                           drafts that were never installed
  newskill.py drop N                           delete a draft

Standard library only, Python 3.8+. Nothing leaves the machine.
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

__version__ = "0.1.0"

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_NAME = 64
MAX_DESCRIPTION = 1024
LONG_BODY = 300
PROVIDERS = ("claude", "codex", "agy", "kiro")
LABELS = {"claude": "Claude Code", "codex": "Codex", "agy": "Antigravity", "kiro": "Kiro"}
MARK = "TODO(" + "new-skill)"   # split so that this file passes its own check
PART_RE = re.compile(r"\b((?:scripts|references|roles|assets)/[A-Za-z0-9_][A-Za-z0-9_./-]*\.[A-Za-z0-9]+)")
SECRETS = (
    ("an API key", re.compile(r"\b(sk-ant-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{32,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16})\b")),
    ("a private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)
HOME_RE = re.compile(r"(/home/[A-Za-z0-9._-]+/|/Users/[A-Za-z0-9._-]+/|[A-Z]:\\Users\\)")
TEXT_SUFFIXES = {".md", ".py", ".sh", ".json", ".txt", ".yaml", ".yml", ".toml"}


class Stop(Exception):
    pass


def home():
    return Path(os.environ.get("HOME") or Path.home())


def provider_homes():
    h = home()
    return {
        "claude": Path(os.environ.get("CLAUDE_CONFIG_DIR") or h / ".claude"),
        "codex": Path(os.environ.get("CODEX_HOME") or h / ".codex"),
        "agy": h / ".gemini" / "config",
        "kiro": Path(os.environ.get("KIRO_HOME") or h / ".kiro"),
    }


def skills_dir(provider):
    return provider_homes()[provider] / "skills"


def found(provider):
    base = provider_homes()[provider]
    return (base.parent if provider == "agy" else base).is_dir()


def state_dir():
    env = os.environ.get("NEWSKILL_HOME")
    if env:
        return Path(env)
    return Path(os.environ.get("XDG_STATE_HOME") or home() / ".local" / "state") / "new-skill"


def drafts_dir():
    return state_dir() / "drafts"


def check_name(name):
    if not NAME_RE.match(name or ""):
        raise Stop("the name must be lowercase letters, digits and single hyphens: %r" % name)
    if len(name) > MAX_NAME:
        raise Stop("the name is %d characters (max %d)" % (len(name), MAX_NAME))


def locate(ref):
    """A draft name or a folder path -> the skill folder."""
    p = Path(ref).expanduser()
    if p.is_dir() and (os.sep in ref or ref.startswith(".")):
        return p.resolve()
    d = drafts_dir() / ref
    if NAME_RE.match(ref) and d.is_dir():
        return d
    if p.is_dir():
        return p.resolve()
    raise Stop("no draft or folder called %r (see: newskill.py drafts)" % ref)


def frontmatter(text):
    """(fields, body, problems). Reads the plain `key: value` lines the four agents share."""
    if not text.startswith("---\n"):
        return None, text, []
    end = text.find("\n---", 4)
    if end == -1:
        return None, text, []
    fields, problems = {}, []
    for line in text[4:end].splitlines():
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            value = m.group(2).strip()
            if value in ("|", ">", "|-", ">-", "|+", ">+"):
                problems.append("%s must be written on one line (no | or > block)" % m.group(1))
            if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1].replace('\\"', '"')
            fields[m.group(1)] = value
        elif line.strip() and not line.startswith("#"):
            problems.append("frontmatter line is not `key: value`: %r" % line[:60])
    body = text[end + 4:]
    return fields, body.lstrip("\n"), problems


def yaml_value(text):
    text = " ".join(text.split())
    if re.search(r"(: |#|^[\[\]{}&*!|>'\"%@`-])", text):
        return '"%s"' % text.replace("\\", "\\\\").replace('"', '\\"')
    return text


def inspect(folder):
    """(errors, warnings) for a skill folder."""
    errors, warnings = [], []
    name = folder.name
    if not NAME_RE.match(name):
        errors.append("folder name must be lowercase letters, digits and hyphens: %r" % name)
    skill_md = folder / "SKILL.md"
    if not skill_md.is_file():
        return errors + ["SKILL.md is missing"], warnings
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    fields, body, problems = frontmatter(text)
    if fields is None:
        return errors + ["SKILL.md has no frontmatter (--- ... ---) at the top"], warnings
    errors += problems
    if fields.get("name") != name:
        errors.append("frontmatter name %r does not match the folder %r" % (fields.get("name"), name))
    desc = fields.get("description", "")
    if not desc:
        errors.append("frontmatter description is empty")
    elif len(desc) > MAX_DESCRIPTION:
        errors.append("description is %d characters (max %d)" % (len(desc), MAX_DESCRIPTION))
    else:
        if len(desc) < 60:
            warnings.append("description is short: say what the skill does and when to use it")
        if not re.search(r"\b(use|when|run[s]?|asks?)\b", desc, re.I):
            warnings.append("description does not say when to use the skill")
    if not body.strip():
        errors.append("SKILL.md has no instructions under the frontmatter")
    lines = body.count("\n") + 1
    if lines > LONG_BODY:
        warnings.append("SKILL.md is %d lines: move detail into references/ and name the file" % lines)
    for part in sorted(set(PART_RE.findall(body))):
        if not (folder / part).is_file():
            errors.append("SKILL.md names %s, which is not in the skill" % part)
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(folder).as_posix()
        if path.is_symlink():
            errors.append("%s is a link: a skill carries its own files" % rel)
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        if MARK in content:
            errors.append("%s still has %s lines to fill in" % (rel, MARK))
        for label, rx in SECRETS:
            if rx.search(content):
                errors.append("%s holds what looks like %s" % (rel, label))
        if HOME_RE.search(content):
            warnings.append("%s has a path into one user's home folder: it will not work elsewhere" % rel)
        if path.suffix == ".py":
            try:
                compile(content, rel, "exec")
            except SyntaxError as exc:
                errors.append("%s does not compile: line %s, %s" % (rel, exc.lineno, exc.msg))
    return errors, warnings


def taken(name):
    return [p for p in PROVIDERS if (skills_dir(p) / name).exists()]


def cmd_where(args):
    out = {"providers": {}, "drafts": str(drafts_dir())}
    for p in PROVIDERS:
        d = skills_dir(p)
        skills = sorted(x.name for x in d.iterdir() if (x / "SKILL.md").is_file()) if d.is_dir() else []
        out["providers"][p] = {"label": LABELS[p], "found": found(p), "skills_dir": str(d), "skills": skills}
    if args.name:
        ok = bool(NAME_RE.match(args.name)) and len(args.name) <= MAX_NAME
        out["name"] = {"name": args.name, "valid": ok, "installed_in": taken(args.name) if ok else [],
                       "draft_exists": ok and (drafts_dir() / args.name).exists()}
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


SKELETON = """---
name: {name}
description: {description}
{invoke}---

# {name}

{mark} One or two sentences: what this skill does and what the result looks like.

## Steps

{mark} The steps, in the order they are done.

## Rules

{mark} What must never happen, and what to do when a step fails.
"""


def cmd_draft(args):
    check_name(args.name)
    desc = " ".join(args.description.split())
    if not desc:
        raise Stop("the description is empty")
    if len(desc) > MAX_DESCRIPTION:
        raise Stop("the description is %d characters (max %d)" % (len(desc), MAX_DESCRIPTION))
    folder = drafts_dir() / args.name
    if folder.exists():
        if not args.replace:
            raise Stop("a draft called %r is already there: %s\nContinue it, or pass --replace to start over" % (args.name, folder))
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    invoke = "disable-model-invocation: true\n" if args.invoke == "command" else ""
    (folder / "SKILL.md").write_text(
        SKELETON.format(name=args.name, description=yaml_value(desc), invoke=invoke, mark=MARK), encoding="utf-8")
    print("draft: %s" % folder)
    where = taken(args.name)
    if where:
        print("note: %r is already installed in %s; install needs --replace" % (args.name, ", ".join(where)))
    print("Write the skill into that folder, then: newskill.py check %s" % args.name)
    return 0


def cmd_check(args):
    folder = locate(args.skill)
    errors, warnings = inspect(folder)
    for e in errors:
        print("error: %s" % e)
    for w in warnings:
        print("warning: %s" % w)
    files = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts)
    print("%s: %s (%d file%s)" % ("FAILED" if errors else "ok", folder, len(files), "" if len(files) == 1 else "s"))
    return 1 if errors else 0


def copy_skill(src, dest):
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git", ".DS_Store"))
    scripts = dest / "scripts"
    if scripts.is_dir():
        for f in scripts.iterdir():
            if f.is_file() and f.suffix in (".py", ".sh"):
                f.chmod(f.stat().st_mode | 0o755)


def cmd_install(args):
    src = locate(args.skill)
    name = src.name
    errors, _ = inspect(src)
    if errors:
        raise Stop("not installed, the skill has errors:\n" + "\n".join("  - " + e for e in errors))
    targets = []
    if args.dest:
        targets.append(("folder", Path(args.dest).expanduser().resolve()))
    providers = []
    if args.provider:
        providers.append(args.provider)
    if args.all:
        providers += [p for p in PROVIDERS if found(p)]
    for p in (args.also or "").split(","):
        if p.strip():
            if p.strip() not in PROVIDERS:
                raise Stop("unknown provider %r (one of: %s)" % (p.strip(), ", ".join(PROVIDERS)))
            providers.append(p.strip())
    for p in dict.fromkeys(providers):
        targets.append((p, skills_dir(p)))
    if not targets:
        raise Stop("say where: --in <%s>, --also, --all or --dest DIR" % "|".join(PROVIDERS))
    busy = [str(base / name) for _, base in targets if (base / name).exists()]
    if busy and not args.replace:
        raise Stop("already there, nothing was changed:\n%s\nPass --replace to put the new one in its place "
                   "(the old one is kept as a backup)" % "\n".join("  " + b for b in busy))
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for label, base in targets:
        dest = base / name
        if dest.resolve() == src.resolve():
            print("in place: %s" % dest)
            continue
        base.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            backup = state_dir() / "backups" / ("%s-%s-%s" % (name, label, stamp))
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dest), str(backup))
            print("backup: %s" % backup)
        copy_skill(src, dest)
        print("installed: %s" % dest)
    draft = drafts_dir() / name
    if src == draft and not args.keep_draft:
        shutil.rmtree(draft)
    print("Run it as /%s after restarting the agent (a new session is enough in most)." % name)
    return 0


def cmd_drafts(args):
    d = drafts_dir()
    names = sorted(x.name for x in d.iterdir() if x.is_dir()) if d.is_dir() else []
    for n in names:
        print("%s  %s" % (n, d / n))
    if not names:
        print("no drafts")
    return 0


def cmd_drop(args):
    check_name(args.name)
    d = drafts_dir() / args.name
    if not d.is_dir():
        raise Stop("no draft called %r" % args.name)
    shutil.rmtree(d)
    print("dropped: %s" % d)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="newskill.py", description="Draft, check and install an agent skill.")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("where", help="providers found here and their skills")
    s.add_argument("--name")
    s.set_defaults(fn=cmd_where)
    s = sub.add_parser("draft", help="start a draft")
    s.add_argument("--name", required=True)
    s.add_argument("--description", required=True)
    s.add_argument("--invoke", choices=("command", "auto"), default="command",
                   help="command: only when the user calls it; auto: the agent may also pick it up")
    s.add_argument("--replace", action="store_true")
    s.set_defaults(fn=cmd_draft)
    s = sub.add_parser("check", help="check a draft or a skill folder")
    s.add_argument("skill")
    s.set_defaults(fn=cmd_check)
    s = sub.add_parser("install", help="copy a checked skill into the agents' skills folders")
    s.add_argument("skill")
    s.add_argument("--in", dest="provider", choices=PROVIDERS)
    s.add_argument("--also", help="more providers, comma separated")
    s.add_argument("--all", action="store_true", help="every provider found on this machine")
    s.add_argument("--dest", help="another skills folder, for example a project's or a repository's")
    s.add_argument("--replace", action="store_true")
    s.add_argument("--keep-draft", action="store_true")
    s.set_defaults(fn=cmd_install)
    s = sub.add_parser("drafts", help="list drafts")
    s.set_defaults(fn=cmd_drafts)
    s = sub.add_parser("drop", help="delete a draft")
    s.add_argument("name")
    s.set_defaults(fn=cmd_drop)
    args = ap.parse_args(argv)
    if not getattr(args, "fn", None):
        ap.print_help()
        return 2
    try:
        return args.fn(args)
    except Stop as exc:
        print("Blocked: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
