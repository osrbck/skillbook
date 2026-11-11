#!/usr/bin/env python3
"""Agentack 2.1 helper: detect agent CLIs, read the project, keep the roster, dispatch roles, track limits.

  detect                          which agent CLIs are installed (JSON)
  setup --providers a,b [...]     save the roster for the chosen providers
  init [--set key=value]          scan this project (stack, units, architecture, contracts, commands)
  project [--md]                  the saved project profile, and whether the repository moved on since
  roster [--md]                   who does what (configured, ignoring live limits)
  strengths [--md]                what each provider is rated at, per kind of work
  check-conductor --host H --model M
  new-brief ROLE                  create the next brief, in the style of the model that role runs on
  dispatch --role R --brief FILE  start a worker (prints a run id, or a native-subagent instruction)
  wait ID... [--timeout 540]      block until runs finish
  result ID [--full]              a run's final message (bounded)
  runs | report | limits          bookkeeping
  verify                          ping every model in the roster; drop the ones your account lacks
  doctor [--ping]                 show the setup (ping spends a few tokens per provider)
  image --prompt TEXT --out FILE  generate one raster image through a provider that can (experimental)
  worktree add|apply|remove NAME  isolated working copies for overlapping writers
  hook install|remove             optional Claude Code status line hook that records usage

Everything prints JSON unless noted. Python 3.8+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agentack_core import __version__, config, limits, roster, runs  # noqa: E402
from agentack_core import project as projectmod  # noqa: E402
from agentack_core.providers import PROVIDERS, RATINGS_REVIEWED, SKILLS, TIERS, model_refusal  # noqa: E402


def out(data, code: int = 0) -> int:
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return code


def fail(message: str, code: int = 2, **extra) -> int:
    return out({"error": message, **extra}, code)


def detect_host() -> str:
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude"
    if any(k.startswith("CODEX_") for k in os.environ if k != "CODEX_HOME"):
        return "codex"
    if any(k.startswith("ANTIGRAVITY_") for k in os.environ):
        return "agy"
    return "unknown"


def need_config(cfg: dict):
    if not cfg.get("_configured"):
        return fail("Agentack is not set up yet", next="run `detect`, ask the user which providers to "
                    "use, then `setup --providers ...`", code=3)
    return None


# -- commands --------------------------------------------------------------------------------

def environment(project: Path) -> dict:
    return {"python": "%d.%d" % sys.version_info[:2], "git": bool(shutil.which("git")),
            "git_repo": (project / ".git").exists(), "project": str(project),
            "port_tools": bool(shutil.which("lsof") or shutil.which("ss")),
            "project_guide": next((n for n in ("CLAUDE.md", "AGENTS.md") if (project / n).is_file()), None),
            "project_initialised": bool((config.read_json(projectmod.project_file(project)) or {}).get("project"))}


def next_steps(cfg: dict, project: Path) -> list:
    """What this user should know or fix, most important first. `action` items have a `fix`."""
    steps = []
    provs = cfg.get("providers") or {}
    order = cfg.get("order") or []
    active = [p for p in order if not (provs.get(p) or {}).get("disabled")]
    for p in order:
        reason = (provs.get(p) or {}).get("disabled")
        if reason:
            prov = PROVIDERS[p]
            kind = (provs.get(p) or {}).get("disabled_kind") or "unknown"
            if kind == "not installed":
                fix = "install it (%s)" % (prov.docs or prov.label)
            elif kind == "sign-in":
                fix = prov.sign_in
            else:
                fix = ("run `%s` once by hand to see what it reports; if it asks you to sign in: %s"
                       % (prov.bins[0], prov.sign_in))
            steps.append({"level": "action", "provider": p, "kind": kind,
                          "text": "%s is set aside: %s" % (prov.label, reason),
                          "fix": fix, "then": "/agentack verify"})
    if not active:
        steps.append({"level": "action", "text": "no provider is usable right now",
                      "fix": "sign in to at least one agent CLI", "then": "/agentack verify"})
    env = environment(project)
    if not env["git"] or not env["git_repo"]:
        steps.append({"level": "action", "text": "this folder is not a git repository",
                      "fix": "run /agentack inside your project's repository (git init if it is new)"})
    elif not env["project_initialised"]:
        steps.append({"level": "info", "text": "this project has not been scanned yet; it happens by itself "
                      "on the first task, or now with /agentack init"})
    fb = cfg["limit_fallback"]
    for row in roster.table(cfg):
        if row["fit"] and row["fit"] <= 2:
            steps.append({"level": "info", "text": "%s runs on %s, which is rated weak at %s work (%d/5). "
                          "Adding a provider that is strong at it would move this role there."
                          % (row["role"], row["primary"], row["skill"], row["fit"])})
            break
    try:
        import datetime as _dt
        age = (_dt.date.today() - _dt.date.fromisoformat(RATINGS_REVIEWED)).days
        if age > 90:
            steps.append({"level": "info", "text": "the provider ratings are %d days old; models move fast, "
                          "so update Agentack (git pull && ./install.sh)" % age})
    except ValueError:
        pass
    vendors = {PROVIDERS[p].vendor for p in active}
    if len(vendors) == 1:
        steps.append({"level": "info", "text": "one provider in use: review runs on the same vendor in a fresh "
                      "context, and there is nothing to fall back to on a usage limit. Add a second provider "
                      "any time with /agentack setup."})
    if fb["enabled"]:
        if "claude" in active and "agentack.py statusline" not in str(
                ((config.read_json(_claude_settings()) or {}).get("statusLine") or {}).get("command")):
            steps.append({"level": "info", "text": "Claude usage is not measured (no status line hook), so a "
                          "switch away from Claude happens only after it reports a limit.",
                          "fix": "/agentack setup can install the hook"})
        if "agy" in active and not env["port_tools"]:
            steps.append({"level": "info", "text": "Antigravity usage cannot be measured without `lsof` or `ss`.",
                          "fix": "install lsof"})
        if "cursor" in active:
            steps.append({"level": "info", "text": "Cursor usage cannot be measured; it is switched away from "
                          "only after it reports a limit."})
    return steps


def crew_summary(cfg: dict) -> dict:
    """The roster in the few facts a person wants: who builds, reviews and decides."""
    rows = {r["role"]: r for r in roster.table(cfg)}
    provs = cfg.get("providers") or {}
    active = [p for p in cfg.get("order") or [] if not (provs.get(p) or {}).get("disabled")]
    builder = (rows["backend"]["primary"] or "").split(":")[0]
    reviewer = (rows["reviewer"]["primary"] or "").split(":")[0]
    deciders = roster.candidates("decider", cfg)
    second = next((c for c in deciders[1:] if c["vendor"] != deciders[0]["vendor"]), None) if deciders else None
    fb = cfg["limit_fallback"]
    measured = [p for p in active if p in ("codex", "kiro", "agy")]
    if "claude" in active and "agentack.py statusline" in str(
            ((config.read_json(_claude_settings()) or {}).get("statusLine") or {}).get("command")):
        measured.append("claude")
    return {
        "in_use": active,
        "set_aside": [p for p in cfg.get("order") or [] if p not in active],
        "builds": rows["backend"]["primary"], "mechanical": rows["scout"]["primary"],
        "plans": rows["architect"]["primary"], "reviews": rows["reviewer"]["primary"],
        "designs": rows["designer"]["primary"],
        "images": (runs.image_providers_cfg(cfg) or [None])[0],
        "review_is_independent": bool(builder and reviewer and
                                      PROVIDERS[builder].vendor != PROVIDERS[reviewer].vendor),
        "decides": rows["decider"]["primary"],
        "second_opinion": ("%s:%s" % (second["provider"], second["model"]))
        if second and cfg.get("second_opinion") else None,
        "limit_fallback": ("on, switch at %d%%" % fb["switch_at_percent"]) if fb["enabled"] else "off",
        "usage_measured_for": measured if fb["enabled"] else [],
    }


def cmd_detect(args, cfg, project):
    found = [p.detect(cfg) for p in PROVIDERS.values()]
    installed = [p["name"] for p in found if p["installed"]]
    for p in found:
        p["ratings"] = {k: roster.rating(cfg, p["name"], k) for k in SKILLS}
        p["can_generate_images"] = PROVIDERS[p["name"]].image
    by_fit = sorted(installed, key=lambda n: -sum(roster.rating(cfg, n, k) for k in SKILLS))
    return out({"version": __version__, "configured": cfg.get("_configured", False),
                "selected": cfg.get("order"), "host": detect_host(), "environment": environment(project),
                "suggested_order": by_fit, "ratings_reviewed": RATINGS_REVIEWED,
                "note": "`auth` is only a hint read from files, env vars or a status command. "
                        "`doctor --ping` sends a real one-word prompt and is the actual test.",
                "config": str(config.config_path()), "providers": found})


def _roster_payload(cfg: dict) -> dict:
    fb = cfg["limit_fallback"]
    return {"order": cfg["order"], "summary": crew_summary(cfg),
            "strengths": scorecard(cfg, cfg["order"]),
            "roster": roster.table(cfg), "notes": roster.notes(cfg),
            "limit_fallback": {"enabled": fb["enabled"], "switch_at_percent": fb["switch_at_percent"],
                               "builders_may_drop_one_tier": fb["builders_may_drop_one_tier"]},
            "second_opinion": bool(cfg.get("second_opinion")) and
            len({c["vendor"] for c in roster.candidates("decider", cfg)}) > 1,
            "single_provider": len(cfg["order"]) == 1, "verified": bool(cfg.get("verified_at"))}


def cmd_setup(args, cfg, project):
    cfg = {k: v for k, v in config.load(None).items() if not k.startswith("_")}   # user level only
    if args.providers:
        order = [p.strip() for p in args.providers.split(",") if p.strip()]
        unknown = [p for p in order if p not in PROVIDERS]
        if unknown:
            return fail("unknown provider(s): %s" % ", ".join(unknown), known=list(PROVIDERS))
        missing = [p for p in order if not PROVIDERS[p].find(cfg)]
        if missing and not args.force:
            return fail("not installed: %s (use --force to configure anyway)" % ", ".join(missing))
        old = cfg.get("providers") or {}
        cfg["providers"] = {}
        for p in order:
            if p in old and not args.reset:
                cfg["providers"][p] = old[p]
                stale = [t for t, spec in (old[p].get("tiers") or {}).items() if spec and spec.get("unverified")]
                if stale:   # defaults an older version could not confirm: resolve them again
                    tiers, unavailable = PROVIDERS[p].resolve_tiers(PROVIDERS[p].find(cfg))
                    for t in stale:
                        old[p]["tiers"][t] = tiers.get(t)
                        if t in unavailable:
                            old[p].setdefault("unavailable", {})[t] = unavailable[t]
            else:
                tiers, unavailable = PROVIDERS[p].resolve_tiers(PROVIDERS[p].find(cfg))
                cfg["providers"][p] = {"bin": (old.get(p) or {}).get("bin"), "tiers": tiers,
                                       "unavailable": unavailable,
                                       "extra_args": (old.get(p) or {}).get("extra_args", [])}
        limits.clear_missing(order)
        cfg["verified_at"] = None
        if order != cfg.get("order") or args.reset:
            cfg["roles"] = {}            # chains follow the order and the ratings unless set by hand
        cfg["order"] = order
    if not cfg.get("order"):
        return fail("no providers selected: pass --providers")

    for item in args.model or []:        # provider:TIER=model[@effort]
        try:
            left, model = item.split("=", 1)
            prov, tier = left.split(":", 1)
            tier = tier.upper()
            assert prov in cfg["providers"] and tier in TIERS and model
        except (ValueError, AssertionError):
            return fail("bad --model %r; expected provider:S3=model[@effort]" % item)
        model, _, effort = model.partition("@")
        spec = {"model": model}
        if effort:
            spec["effort"] = effort
        cfg["providers"][prov].setdefault("tiers", {})[tier] = spec
        (cfg["providers"][prov].get("unavailable") or {}).pop(tier, None)
    for item in args.style or []:        # provider:TIER=style
        try:
            left, style = item.split("=", 1)
            prov, tier = left.split(":", 1)
            tier = tier.upper()
            assert style in ("goal", "structured", "explicit", "rules", "peer")
            cfg["providers"][prov]["tiers"][tier]["style"] = style
        except (ValueError, AssertionError, KeyError, TypeError):
            return fail("bad --style %r; expected provider:S2=goal|structured|explicit|rules|peer "
                        "for a tier that has a model" % item)
    for item in args.rate or []:         # provider:skill=1..5
        try:
            left, score = item.split("=", 1)
            prov, skill = left.split(":", 1)
            assert prov in PROVIDERS and skill in SKILLS and 1 <= int(score) <= 5
            cfg.setdefault("ratings", {})["%s:%s" % (prov, skill)] = int(score)
        except (ValueError, AssertionError):
            return fail("bad --rate %r; expected provider:skill=1..5" % item, skills=list(SKILLS))
    for item in args.role or []:         # role=p1,p2
        try:
            role, chain = item.split("=", 1)
            role = roster.canonical(role)[0]
            chain = [c for c in chain.split(",") if c]
            assert role in roster.ROLES and chain and all(c in cfg["providers"] for c in chain)
        except (ValueError, AssertionError):
            return fail("bad --role %r; expected role=provider[,provider]" % item, roles=list(roster.ROLES))
        cfg.setdefault("roles", {})[role] = chain

    fb = dict(cfg["limit_fallback"])
    if args.fallback:
        fb["enabled"] = args.fallback == "on"
    if args.threshold is not None:
        fb["switch_at_percent"] = max(1, min(100, args.threshold))
    if args.drop_tier:
        fb["builders_may_drop_one_tier"] = args.drop_tier == "on"
    cfg["limit_fallback"] = fb
    if args.second_opinion:
        cfg["second_opinion"] = args.second_opinion == "on"
    if args.native:
        cfg["native_subagents"] = args.native == "on"
    path = config.save(cfg)
    if args.brief:
        return out({"saved": str(path), "order": cfg["order"], "limit_fallback": cfg["limit_fallback"]["enabled"],
                    "next": "run `verify`: it tests every model and returns the roster"})
    return out({"saved": str(path), **_roster_payload(cfg)})


def cmd_roster(args, cfg, project):
    err = need_config(cfg)
    if err is not None:
        return err
    data = _roster_payload(cfg)
    data["next_steps"] = next_steps(cfg, project)
    prof = projectmod.effective(cfg)
    names = {"backend": [], "frontend": []}
    for u in (prof or {}).get("units") or []:
        for layer in ("backend", "frontend"):
            if u["layer"] in (layer, "fullstack"):
                names[layer].append(projectmod.label(layer, u))
    data["builders"] = {k: sorted(set(v)) for k, v in names.items()} if prof else None
    if not args.md:
        return out(data)
    fb = data["limit_fallback"]
    lines = ["| Role | Tier | Model | Fit | Brief style | Fallbacks |", "|---|---|---|---|---|---|"]
    for r in data["roster"]:
        model = r["primary"] or "— none"
        if r["substituted"]:
            model += " (%s)" % r["runs_on"]
        role = r["role"]
        if data["builders"] and data["builders"].get(role):
            role += " (%s)" % ", ".join(data["builders"][role])
        lines.append("| %s | %s %s | %s | %s | %s | %s |" % (
            role, r["tier"], roster.TIER_PURPOSE[r["tier"]], model,
            ("%d/5 %s" % (r["fit"], r["skill"])) if r["fit"] else "—", r["style"] or "—",
            ", ".join(r["fallbacks"]) or "—"))
    lines.append("")
    lines.append("Limit fallback: %s" % ("on (switch at %d%%)" % fb["switch_at_percent"]
                                         if fb["enabled"] else "off"))
    for p in data["notes"]:
        lines.append("ℹ " + p)
    for step in data["next_steps"]:
        if step["level"] == "action":
            lines.append("→ %s. Fix: %s" % (step["text"], step["fix"]))
    print("\n".join(lines))
    return 0


def scorecard(cfg: dict, names) -> dict:
    return {"reviewed": RATINGS_REVIEWED,
            "scale": "5 leads the field · 4 strong · 3 adequate or not yet rated · 2 weak, last resort · 1 do not use",
            "providers": {n: {k: roster.rating(cfg, n, k) for k in SKILLS} for n in names}}


def cmd_strengths(args, cfg, project):
    """What each provider is rated at (1–5 per kind of work). Evidence: references/strengths.md."""
    names = cfg.get("order") or [n for n, p in PROVIDERS.items() if p.find(cfg)]
    card = scorecard(cfg, names)
    if not args.md:
        return out(card)
    lines = ["| Provider | " + " | ".join(SKILLS) + " |", "|---|" + "---|" * len(SKILLS)]
    for n, row in card["providers"].items():
        lines.append("| %s | %s |" % (n, " | ".join(str(row[k]) for k in SKILLS)))
    lines += ["", card["scale"], "Ratings reviewed: %s" % card["reviewed"]]
    print("\n".join(lines))
    return 0


def _attention(prof: dict) -> list:
    """What the conductor should confirm by looking at the code. Never questions for the user."""
    items = []
    a = prof["architecture"]
    if a.get("confidence") == "low":
        items.append("architecture is a guess (%s): look at the layout and correct it with "
                     "`init --set architecture=<kind>` if needed" % "; ".join(a.get("why") or []))
    if not prof["units"]:
        items.append("no application was recognised: find the entry points and add them with "
                     "`init --set units.<name>.path=<dir> --set units.<name>.layer=backend|frontend|fullstack "
                     "--set units.<name>.stack=<language or framework>`")
    for x in prof.get("unclaimed") or []:
        items.append("%d %s files (mostly in %s) belong to no unit: the scan missed an application. Find its "
                     "root and add it with `init --set units.<name>.path=<dir> --set units.<name>.layer=backend "
                     "--set units.<name>.stack=%s`" % (x["files"], x["language"], x["mostly_in"], x["language"]))
    for u in prof["units"]:
        if not u.get("commands", {}).get("test"):
            items.append("%s has no test command: find it (README, CI, Makefile) and set "
                         "`units.%s.commands.test`" % (u["name"], u["name"]))
    c = prof.get("contracts") or {}
    if c.get("kinds") and not c.get("check") and set(c["kinds"]) - {"typed"}:
        items.append("contracts (%s) have no single check command: the contract gate will use "
                     "contract-guard with the default tools, unless CI has one (`contracts.check`)"
                     % ", ".join(c["kinds"]))
    if prof.get("guide"):
        items.append("read %s once: where it names other commands or rules, record them with `init --set`"
                     % " / ".join(prof["guide"]))
    return items


def _init_md(payload: dict) -> str:
    prof = payload["profile"]
    lines = ["**Project profile** (%s)" % ("saved to .agentack.json" if payload.get("written") else
                                          "unchanged" if payload.get("unchanged") else "not saved")]
    lines.append(projectmod.describe(prof))
    if payload.get("changes"):
        lines.append("- Changed since last scan: " + "; ".join(payload["changes"]))
    lines.append("- Builders for this project: " + ", ".join(payload["builders"]) if payload["builders"]
                 else "- Builders: none (no application found)")
    for item in payload["attention"]:
        lines.append("- To check: " + item)
    return "\n".join(lines)


def cmd_init(args, cfg, project):
    if args.set and not args.dry_run:
        try:
            projectmod.set_override(project, args.set)
        except ValueError as e:
            return fail(str(e))
    old = (config.read_json(projectmod.project_file(project)) or {}).get("project")
    scanned = projectmod.scan(project)
    changed, path = (False, None) if args.dry_run else projectmod.save(project, scanned)
    if not args.dry_run:
        runs.work_dir(project)                       # makes sure .agentack/ is ignored by git
    prof = projectmod.effective(config.load(project)) if not args.dry_run else scanned
    builders = [a for u in prof["units"] for a in u["agents"]]
    payload = {"written": str(path) if changed else None, "unchanged": bool(path) and not changed,
               "first_time": old is None, "changes": projectmod.changes(old, scanned),
               "builders": builders, "attention": _attention(prof), "profile": prof,
               "summary": projectmod.describe(prof)}
    if args.md:
        print(_init_md(payload))
        return 0
    return out(payload)


def cmd_project(args, cfg, project):
    prof = projectmod.effective(cfg)
    if not prof:
        return fail("this project has not been initialised", code=4, next="run `init`")
    saved = (config.read_json(projectmod.project_file(project)) or {}).get("project")
    moved = projectmod.changes(saved, projectmod.scan(project))
    if args.md:
        print(projectmod.describe(prof) + ("\n- Changed since the scan: " + "; ".join(moved) +
                                          " (run `init` again)" if moved else ""))
        return 0
    return out({"profile": prof, "summary": projectmod.describe(prof), "stale": moved,
                "builders": [a for u in prof["units"] for a in u["agents"]]})


def cmd_image(args, cfg, project):
    err = need_config(cfg)
    if err is not None:
        return err
    text = args.prompt or ""
    if args.prompt_file:
        try:
            text = Path(args.prompt_file).read_text(encoding="utf-8")
        except OSError as e:
            return fail("cannot read the prompt file: %s" % e)
    if not text.strip():
        return fail("give the image description with --prompt or --prompt-file")
    limits.refresh(cfg)
    try:
        return out(runs.image(project, cfg, text, Path(args.out).resolve(), args.aspect, args.timeout))
    except roster.NoModel as e:
        return fail(str(e), code=3, next="use an SVG, an icon from the project's set or a placeholder, "
                                         "and list the missing image in the closing report")


def cmd_check_conductor(args, cfg, project):
    return out(roster.check_conductor(args.host, args.model, cfg))


def cmd_dispatch(args, cfg, project):
    err = need_config(cfg)
    if err is not None:
        return err
    brief = Path(args.brief).resolve()
    if not brief.is_file():
        return fail("brief not found: %s" % brief)
    cwd = Path(args.cwd).resolve() if args.cwd else Path.cwd()
    avoid = [a for a in (args.avoid or "").split(",") if a]
    host = args.host or detect_host()
    try:
        return out(runs.dispatch(project, args.role, brief, cwd, args.mode, avoid, host, args.timeout, cfg,
                                 args.skill, args.unit))
    except runs.Unclear as e:
        return fail(str(e), code=2, role=args.role)
    except roster.NoModel as e:
        return fail(str(e), code=3, role=args.role)


def cmd_resolve(args, cfg, project):
    err = need_config(cfg)
    if err is not None:
        return err
    limits.refresh(cfg)
    try:
        return out(roster.pick(roster.canonical(args.role)[0], cfg, avoid=[a for a in (args.avoid or "").split(",") if a],
                               skill=args.skill))
    except roster.NoModel as e:
        return fail(str(e), code=3, role=args.role)


def cmd_new_brief(args, cfg, project):
    if roster.canonical(args.role)[0] not in roster.ROLES:
        return fail("unknown role: %s" % args.role, roles=list(roster.ROLES))
    return out(runs.new_brief(project, args.role, cfg, args.style))


def cmd_wait(args, cfg, project):
    try:
        return out(runs.wait(project, args.ids, args.timeout))
    except FileNotFoundError as e:
        return fail(str(e))


def cmd_result(args, cfg, project):
    try:
        print(runs.result(project, args.id, args.full, cfg))
        return 0
    except FileNotFoundError as e:
        return fail(str(e))


def cmd_runs(args, cfg, project):
    return out(runs.list_runs(project))


def cmd_report(args, cfg, project):
    return out(runs.report(project))


def cmd_limits(args, cfg, project):
    err = need_config(cfg)
    if err is not None:
        return err
    if args.clear:
        limits.clear(args.clear)
    limits.refresh(cfg, force=args.refresh)
    return out({"limit_fallback": cfg["limit_fallback"], "providers": limits.summary(cfg)})


def _ping(prov, binary: str, spec: dict, timeout: int) -> dict:
    """Send a one-word prompt exactly the way a worker would be started."""
    res = {"ok": False, "model": spec["model"]}
    with tempfile.TemporaryDirectory() as tmp:
        argv, stdin = prov.command(binary, spec, "read", "Reply with exactly: OK", tmp,
                                   os.path.join(tmp, "last.txt"))
        io = {"input": stdin} if stdin is not None else {"stdin": subprocess.DEVNULL}
        try:
            p = subprocess.run(argv, capture_output=True, text=True, cwd=tmp, timeout=timeout, **io)
        except (OSError, subprocess.SubprocessError) as e:
            res["error"] = str(e)[:300]
            return res
        text, bad = prov.final(p.stdout, os.path.join(tmp, "last.txt"))
        res["ok"] = p.returncode == 0 and not bad and bool(text.strip())
        res["answer"] = text.strip()[:80]
        if not res["ok"]:
            evidence = "\n".join(x for x in ((p.stderr or "").strip()[-3000:], text.strip()[:1500] if bad else "",
                                             (p.stdout or "").strip()[-3000:] if not text.strip() else "") if x)
            refusal = model_refusal(evidence, spec["model"])
            if refusal:
                res["model_unavailable"] = True
                res["error"] = refusal
            else:
                res["error"] = evidence[-400:]
                if re.search(r"log ?in|sign ?in|auth|credential|api[ _-]?key|unauthori", res["error"], re.I):
                    res["hint"] = "looks like a sign-in problem: " + (prov.notes or "")
    return res


def cmd_verify(args, cfg, project):
    """Ping every distinct model of the selected providers; drop the ones the account lacks."""
    cfg = {k: v for k, v in config.load(None).items() if not k.startswith("_")}
    if not cfg.get("order"):
        return fail("Agentack is not set up yet", code=3)
    limits.clear_missing(cfg["order"])
    results, removed = [], []
    for name in cfg["order"]:
        prov, entry = PROVIDERS[name], cfg["providers"][name]
        entry.pop("disabled", None)
        entry.pop("disabled_kind", None)
        binary = prov.find(cfg)
        if not binary:
            results.append({"provider": name, "ok": False, "error": "not installed"})
            entry["disabled"] = entry["disabled_kind"] = "not installed"
            continue
        seen = {}
        listed = prov.trusted_models(binary)
        for tier in reversed(TIERS):                       # S4 first
            spec = (entry.get("tiers") or {}).get(tier)
            if not spec:
                continue
            if listed and spec["model"] not in listed and spec["model"] != "auto":
                seen[spec["model"]] = {"ok": False, "model": spec["model"], "model_unavailable": True,
                                       "error": "not in the provider's model list"}
                results.append({"provider": name, **seen[spec["model"]]})
            if spec["model"] not in seen:
                seen[spec["model"]] = _ping(prov, binary, spec, args.ping_timeout)
                results.append({"provider": name, **seen[spec["model"]]})
            res = seen[spec["model"]]
            while res.get("model_unavailable"):
                removed.append("%s:%s (%s)" % (name, spec["model"], tier))
                bad = [m for m, r in seen.items() if r.get("model_unavailable")]
                nxt = prov.pick_model(tier, listed, exclude=bad)
                if not nxt and prov.stand_ins.get(tier) not in [None] + bad + [spec["model"]]:
                    nxt = prov.stand_ins[tier]              # no listing to choose from: the known stand-in
                if not nxt:
                    entry.setdefault("unavailable", {})[tier] = spec["model"]
                    entry["tiers"][tier] = None
                    break
                spec = prov.adjust(tier, dict(spec, model=nxt))   # the next best model this provider lists
                if spec.get("effort") and nxt.lower().endswith("-" + spec["effort"]):
                    spec.pop("effort")
                entry["tiers"][tier] = spec
                if nxt not in seen:
                    seen[nxt] = _ping(prov, binary, spec, args.ping_timeout)
                    results.append({"provider": name, **seen[nxt]})
                res = seen[nxt]
            if not entry["tiers"].get(tier):
                continue
            if not res["ok"] and not res.get("model_unavailable"):
                # sign-in or CLI problem: more pings would fail the same way. Set the provider
                # aside so no work is routed to it until a later verify passes.
                entry["disabled"] = " ".join((res.get("error") or "the test prompt got no answer").split())[:200]
                entry["disabled_kind"] = "sign-in" if (res.get("hint") or prov.auth(binary) == "not signed in") \
                    else "unknown"
                break
    cfg["verified_at"] = __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds")
    config.save(cfg)
    return out({"checked": results, "removed": removed, **_roster_payload(cfg),
                "next_steps": next_steps(config.load(None), project)})


def cmd_doctor(args, cfg, project):
    report = {"version": __version__, "config": str(config.config_path()),
              "configured": cfg.get("_configured", False), "host": detect_host(), "providers": []}
    if not args.ping:
        report["note"] = "nothing was sent to the providers; run with --ping for a real test"
    names = cfg.get("order") or list(PROVIDERS)
    for name in names:
        prov = PROVIDERS[name]
        info = prov.detect(cfg)
        entry = {k: info.get(k) for k in ("name", "installed", "version", "auth", "notes")}
        if args.ping and info["installed"]:
            tiers = ((cfg.get("providers") or {}).get(name) or {}).get("tiers") or prov.tiers
            spec = next((tiers[t] for t in TIERS if tiers.get(t)), None)
            if spec:
                entry["ping"] = _ping(prov, info["path"], spec, args.ping_timeout)
                if entry["ping"]["ok"]:
                    entry["auth"] = "ok"
        report["providers"].append(entry)
    report["environment"] = environment(project)
    prof = projectmod.effective(cfg)
    report["project"] = projectmod.describe(prof, short=True) if prof else "not initialised (/agentack init)"
    if cfg.get("_configured"):
        report["notes"] = roster.notes(cfg)
        report["next_steps"] = next_steps(cfg, project)
    return out(report)


def cmd_worktree(args, cfg, project):
    if args.action == "add":
        return out(runs.worktree_add(project, args.name))
    if args.action == "apply":
        return out(runs.worktree_apply(project, args.name, args.remove))
    return out(runs.worktree_remove(project, args.name))


def _claude_settings() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(Path.home(), ".claude")
    return Path(base) / "settings.json"


def cmd_hook(args, cfg, project):
    """Opt-in: let Claude Code's status line feed its rate-limit numbers to agentack."""
    path = _claude_settings()
    settings = config.read_json(path) or {}
    ours = "%s %s statusline" % (sys.executable or "python3", runs.SCRIPT)
    current = (settings.get("statusLine") or {}).get("command")
    cfg = {k: v for k, v in config.load(None).items() if not k.startswith("_")}
    if args.action == "install":
        if current and "agentack.py statusline" not in current:
            cfg["statusline_passthrough"] = current      # keep the user's own status line working
        settings["statusLine"] = {"type": "command", "command": ours}
    else:
        if current and "agentack.py statusline" in current:
            if cfg.get("statusline_passthrough"):
                settings["statusLine"] = {"type": "command", "command": cfg["statusline_passthrough"]}
            else:
                settings.pop("statusLine", None)
        cfg["statusline_passthrough"] = None
    config.write_json(path, settings)
    config.save(cfg)
    return out({"ok": True, "settings": str(path), "statusLine": settings.get("statusLine")})


def cmd_statusline(args, cfg, project):
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    windows = None
    try:
        windows = limits.from_statusline(payload)
    except Exception:
        pass
    if cfg.get("statusline_passthrough"):
        try:
            p = subprocess.run(cfg["statusline_passthrough"], shell=True, input=raw, capture_output=True,
                               text=True, timeout=5)
            sys.stdout.write(p.stdout)
            return 0
        except (OSError, subprocess.SubprocessError):
            pass
    model = ((payload.get("model") or {}).get("display_name")) or ""
    usage = " · ".join("%s %d%%" % (k, round(v["used"])) for k, v in (windows or {}).items())
    print(" · ".join(x for x in (model, usage) if x))
    return 0


def cmd_exec(args, cfg, project):
    runs.execute(Path(args.run_dir))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="agentack", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version="agentack " + __version__)
    ap.add_argument("--project", help="project root (default: the git repository of the current directory)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("detect").set_defaults(fn=cmd_detect)

    s = sub.add_parser("setup")
    s.add_argument("--providers", help="comma separated, in priority order: " + ",".join(PROVIDERS))
    s.add_argument("--model", action="append", help="provider:S3=model[@effort] (repeatable)")
    s.add_argument("--role", action="append", help="role=provider[,provider] (repeatable)")
    s.add_argument("--style", action="append", help="provider:S2=explicit — briefing style (repeatable)")
    s.add_argument("--rate", action="append", help="provider:skill=1..5 — your own rating (repeatable)")
    s.add_argument("--fallback", choices=["on", "off"], help="switch models automatically on usage limits")
    s.add_argument("--threshold", type=int, help="usage percent that triggers a switch (default 85)")
    s.add_argument("--drop-tier", choices=["on", "off"], help="builders may drop one tier when needed")
    s.add_argument("--second-opinion", choices=["on", "off"])
    s.add_argument("--native", choices=["on", "off"], help="use Claude Code's own subagents when possible")
    s.add_argument("--reset", action="store_true", help="discard customized models and role chains")
    s.add_argument("--brief", action="store_true", help="print a short confirmation instead of the roster")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_setup)

    s = sub.add_parser("init")
    s.add_argument("--set", action="append", metavar="KEY=VALUE",
                   help="correct the scan: architecture=microservices, contracts.check=CMD, "
                        "units.NAME.commands.test=CMD, units.NAME.layer=backend (repeatable; empty value clears)")
    s.add_argument("--dry-run", action="store_true", help="scan and print, write nothing")
    s.add_argument("--md", action="store_true", help="print a short report instead of JSON")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("project")
    s.add_argument("--md", action="store_true")
    s.set_defaults(fn=cmd_project)

    s = sub.add_parser("roster")
    s.add_argument("--md", action="store_true", help="print a Markdown table")
    s.set_defaults(fn=cmd_roster)

    s = sub.add_parser("check-conductor")
    s.add_argument("--host", required=True, choices=["claude", "codex", "agy"])
    s.add_argument("--model", required=True)
    s.set_defaults(fn=cmd_check_conductor)

    for name, fn in (("dispatch", cmd_dispatch), ("resolve", cmd_resolve)):
        s = sub.add_parser(name)
        s.add_argument("--role", required=True)
        s.add_argument("--avoid", help="provider(s) that wrote the work, for an independent reviewer")
        s.add_argument("--skill", choices=list(SKILLS),
                       help="send this run to the provider rated best at a specialty (e.g. visual)")
        if name == "dispatch":
            s.add_argument("--brief", required=True, help="path to the task brief (Markdown)")
            s.add_argument("--cwd", help="working directory for the worker (default: current directory)")
            s.add_argument("--mode", choices=["read", "write"], help="default depends on the role")
            s.add_argument("--host", choices=["claude", "codex", "agy"], help="the conductor's own CLI")
            s.add_argument("--timeout", type=float, help="minutes")
            s.add_argument("--unit", help="which unit of the project (see `project`); needed only when "
                                          "the project has several of that layer")
        s.set_defaults(fn=fn)

    s = sub.add_parser("new-brief")
    s.add_argument("role")
    s.add_argument("--style", choices=["goal", "structured", "explicit", "rules", "peer"],
                   help="default: the style of the model this role runs on")
    s.set_defaults(fn=cmd_new_brief)

    s = sub.add_parser("wait")
    s.add_argument("ids", nargs="+")
    s.add_argument("--timeout", type=int, default=540, help="seconds (default 540)")
    s.set_defaults(fn=cmd_wait)

    s = sub.add_parser("result")
    s.add_argument("id")
    s.add_argument("--full", action="store_true")
    s.set_defaults(fn=cmd_result)

    s = sub.add_parser("strengths")
    s.add_argument("--md", action="store_true")
    s.set_defaults(fn=cmd_strengths)

    sub.add_parser("runs").set_defaults(fn=cmd_runs)
    sub.add_parser("report").set_defaults(fn=cmd_report)

    s = sub.add_parser("limits")
    s.add_argument("--refresh", action="store_true", help="probe providers now")
    s.add_argument("--clear", metavar="PROVIDER", help="forget a recorded limit")
    s.set_defaults(fn=cmd_limits)

    s = sub.add_parser("doctor")
    s.add_argument("--ping", action="store_true", help="send a one-word prompt through each provider")
    s.add_argument("--ping-timeout", type=int, default=120)
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("verify")
    s.add_argument("--ping-timeout", type=int, default=120)
    s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("image")
    s.add_argument("--prompt", help="what the image shows")
    s.add_argument("--prompt-file", help="a file with the description, instead of --prompt")
    s.add_argument("--out", required=True, help="where to save it; the extension follows the real format")
    s.add_argument("--aspect", help="aspect ratio, e.g. 16:9, 1:1, 4:5")
    s.add_argument("--timeout", type=int, default=300, help="seconds per provider (default 300)")
    s.set_defaults(fn=cmd_image)

    s = sub.add_parser("worktree")
    s.add_argument("action", choices=["add", "apply", "remove"])
    s.add_argument("name")
    s.add_argument("--remove", action="store_true", help="with apply: remove the worktree afterwards")
    s.set_defaults(fn=cmd_worktree)

    s = sub.add_parser("hook")
    s.add_argument("action", choices=["install", "remove"])
    s.set_defaults(fn=cmd_hook)

    sub.add_parser("statusline").set_defaults(fn=cmd_statusline)
    s = sub.add_parser("_exec")
    s.add_argument("run_dir")
    s.set_defaults(fn=cmd_exec)

    args = ap.parse_args(argv)
    project = Path(args.project).resolve() if args.project else config.project_root()
    cfg = config.load(project)
    return args.fn(args, cfg, project)


if __name__ == "__main__":
    sys.exit(main())
