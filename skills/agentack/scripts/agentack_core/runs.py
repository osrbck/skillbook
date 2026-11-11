"""Dispatch a role to a provider's headless CLI, detached, and collect a bounded result."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from . import config, limits, roster
from . import project as projectmod
from .providers import LIMIT_RX, PROVIDERS, STYLE_GUIDE, STYLES, model_refusal

TERMINAL = {"done", "error", "limit", "timeout", "no_model"}
SKILL_DIR = Path(__file__).resolve().parents[2]
SCRIPT = SKILL_DIR / "scripts" / "agentack.py"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def work_dir(project: Path) -> Path:
    d = project / ".agentack"
    d.mkdir(exist_ok=True)
    ignore = d / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")   # runtime data never reaches the repo
    return d


def log(project: Path, **event) -> None:
    with open(work_dir(project) / "log.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"time": _now(), **event}, ensure_ascii=False) + "\n")


def role_file(role: str) -> Path:
    return SKILL_DIR / "roles" / (role + ".md")


def _meta(run_dir: Path) -> dict:
    return config.read_json(run_dir / "meta.json") or {}


def _save(run_dir: Path, meta: dict) -> None:
    config.write_json(run_dir / "meta.json", meta)


def find_run(project: Path, run_id: str) -> Path:
    base = work_dir(project) / "runs"
    exact = base / run_id
    if exact.is_dir():
        return exact
    hits = [d for d in base.glob("*") if d.is_dir() and run_id in d.name] if base.is_dir() else []
    if len(hits) != 1:
        raise FileNotFoundError("run not found: %s" % run_id)
    return hits[0]


# -- dispatch ------------------------------------------------------------------------------

class Unclear(ValueError):
    """The project does not say which unit a run is for; the message lists the choices."""


def project_context(role: str, prof: dict, unit: Optional[dict]) -> str:
    """The slice of the project profile this role needs, and nothing more."""
    arch = prof["architecture"]["kind"]
    ref = SKILL_DIR / "references" / "architecture" / (arch + ".md")
    c = prof.get("contracts") or {}
    contracts = ("- Contracts: %s in %s%s. Generated code is never edited by hand." % (
        ", ".join(c["kinds"]), c.get("root") or ", ".join(c.get("roots") or []) or "the code (tRPC / ts-rest types)",
        " · check: `%s`" % c["check"] if c.get("check") else "")) if c.get("kinds") else \
        "- Contracts: none as files; the types and signatures shared between units are the contract."
    out = ["## Project"]
    if role in roster.BUILDERS and unit:
        out += ["- Architecture: %s" % arch, projectmod.describe_unit(unit), contracts]
        if role == "backend" and (prof.get("data") or {}).get("migrations"):
            out.append("- Migrations: " + ", ".join(prof["data"]["migrations"]))
        rules = projectmod.section(ref, "Rules for builders")
        if rules:
            out += ["", "## Architecture rules (%s)" % arch, rules]
        stacks = SKILL_DIR / "references" / "stacks.md"
        for key in (unit.get("framework"), unit.get("stack"), unit.get("language")):
            conv = projectmod.section(stacks, key) if key else ""
            if conv:
                out += ["", "## %s conventions" % key, conv]
                break
        out += ["", "The project's own code wins over every rule above: before you write, read one or two "
                    "neighbouring files and follow their patterns."]
    elif role in ("reviewer", "architect", "qa"):
        out.append(projectmod.describe(prof))
        if unit:
            out.append("- Focus on unit `%s` (%s)" % (unit["name"], unit["path"]))
        head = {"reviewer": "Review checks", "architect": "Planning", "qa": "Testing"}[role]
        text = projectmod.section(ref, head)
        if text:
            out += ["", "## %s (%s)" % (head, arch), text]
        if role == "architect":
            out.append("\nFull architecture notes: `%s` · contract rules: `%s`"
                       % (ref, SKILL_DIR / "references" / "contracts.md"))
    elif role == "backend-architect":
        out.append(projectmod.describe(prof, short=True))
        if unit:
            out += [projectmod.describe_unit(unit), contracts]
        if (prof.get("data") or {}).get("migrations"):
            out.append("- Migrations: " + ", ".join(prof["data"]["migrations"]))
        if prof.get("boundaries"):
            out.append("- Boundary checks: " + ", ".join(prof["boundaries"]))
        for head in ("Boundaries", "Rules for builders"):
            text = projectmod.section(ref, head)
            if text:
                out += ["", "## %s (%s)" % (head, arch), text]
    elif role == "designer":
        out.append(projectmod.describe(prof, short=True))
        if unit:
            out += [projectmod.describe_unit(unit),
                    "- Design for this unit's framework and the components it already has."]
        out.append("- Images: %s" % ("the conductor can generate raster images from the prompts in your "
                                     "asset list" if image_providers_cfg(prof.get("_cfg")) else
                                     "no provider here generates raster images; plan for SVG, CSS, icons "
                                     "from the project's icon set, or placeholders the user replaces"))
    elif role == "contract-guard":
        out += [contracts, "- Tools found in the repository: %s" % (", ".join(c.get("tools") or []) or "none"),
                "- Default tools per contract kind: `%s`" % (SKILL_DIR / "references" / "contracts.md")]
    else:                                                       # scout, decider: the map, not the rules
        out.append(projectmod.describe(prof, short=role == "scout"))
    return "\n".join(out)


def dispatch(project: Path, role: str, brief: Path, cwd: Path, mode: Optional[str], avoid: List[str],
             host: Optional[str], timeout: Optional[int], cfg: dict, skill: Optional[str] = None,
             unit: Optional[str] = None) -> dict:
    role, stack = roster.canonical(role)
    if role not in roster.ROLE_TIER or not role_file(role).is_file():
        raise roster.NoModel("unknown role: %s" % role)
    prof, saved = projectmod.load(project, cfg)
    target = None
    try:
        if role in roster.BUILDERS:
            target = projectmod.pick_unit(prof, role, unit, stack)
        elif unit:
            target = projectmod.pick_unit(prof, "", unit)
        elif role in ("designer", "backend-architect"):
            try:
                target = projectmod.pick_unit(prof, "frontend" if role == "designer" else "backend")
            except ValueError:
                target = None                                   # several frontends: the brief names it
    except ValueError as e:
        raise Unclear(str(e))
    prof = dict(prof, _cfg=cfg)
    label = projectmod.label(role, target)
    limits.refresh(cfg)
    choice = roster.pick(role, cfg, avoid=avoid, skill=skill)
    mode = mode or roster.default_mode(role)
    context = project_context(role, prof, target)
    extra = {"label": label, "unit": target["name"] if target else None}
    if not saved:
        extra["project_note"] = "project not initialised; used a fresh scan (run `init` to save it)"

    if host == "claude" and choice["provider"] == "claude" and cfg.get("native_subagents", True):
        # The host can run this itself as a subagent: cheaper to start and visible to the user.
        log(project, event="dispatch", via="native", role=role, label=label,
            skipped=[x.get("provider") for x in choice["skipped"]], **_brief_choice(choice))
        pdir = work_dir(project) / "prompts"
        pdir.mkdir(exist_ok=True)
        pfile = pdir / ("%s-%s.md" % (datetime.now().strftime("%m%d-%H%M%S"), label))
        pfile.write_text(_prompt({"role": role, "label": label, "mode": mode, "cwd": str(cwd),
                                  "brief": str(brief), "context": context}, choice), encoding="utf-8")
        return {"via": "native", "role": role, "mode": mode, "model": choice["model"],
                "style": choice.get("style"), "prompt_file": str(pfile), "cwd": str(cwd),
                "tier": choice["tier"], "switched": choice["switched"], "skipped": choice["skipped"],
                "independent": choice["independent"], "independence_note": choice.get("independence_note"),
                **extra}

    run_id = "%s-%s-%s" % (datetime.now().strftime("%m%d-%H%M%S"), label, uuid.uuid4().hex[:4])
    run_dir = work_dir(project) / "runs" / run_id
    run_dir.mkdir(parents=True)
    tier_timeout = timeout or cfg["timeouts"].get(roster.ROLE_TIER[role], 30)
    _save(run_dir, {"id": run_id, "role": role, "label": label, "unit": extra["unit"], "mode": mode,
                    "cwd": str(cwd), "brief": str(brief), "context": context,
                    "avoid": avoid, "skill": skill, "project": str(project), "timeout_minutes": tier_timeout,
                    "status": "queued", "created": _now(), "attempts": []})
    with open(run_dir / "runner.log", "w") as out:
        subprocess.Popen([sys.executable, str(SCRIPT), "_exec", str(run_dir)], stdin=subprocess.DEVNULL,
                         stdout=out, stderr=out, start_new_session=True, cwd=str(project))
    return {"via": "cli", "run_id": run_id, "role": role, **extra, "mode": mode, "provider": choice["provider"],
            "style": choice.get("style"),
            "model": choice["model"], "effort": choice.get("effort"), "tier": choice["tier"],
            "switched": choice["switched"], "skipped": choice["skipped"],
            "independent": choice["independent"], "independence_note": choice.get("independence_note"),
            "timeout_minutes": tier_timeout}


def _brief_choice(c: dict) -> dict:
    return {k: c.get(k) for k in ("provider", "model", "effort", "tier", "style", "fit", "weak_fit",
                                  "switched", "independent", "substituted", "dropped")
            if c.get(k) is not None}


BRIEF_STYLE = re.compile(r"<!--\s*Style:\s*([a-z]+)")


def brief_style(text: str) -> Optional[str]:
    m = BRIEF_STYLE.search(text or "")
    return m.group(1) if m and m.group(1) in STYLE_GUIDE else None


def _needs_more_detail(written_for: Optional[str], actual: Optional[str]) -> bool:
    """True when the brief was written for a model that needs less spelled out than this one."""
    return (written_for in STYLES and actual in STYLES
            and STYLES.index(actual) > STYLES.index(written_for))


def _prompt(meta: dict, choice: dict) -> str:
    role_text = role_file(meta["role"]).read_text(encoding="utf-8")
    brief = Path(meta["brief"]).read_text(encoding="utf-8")
    rules = ["- Role: %s · Tier: %s · Working directory: %s" % (meta.get("label") or meta["role"], choice["tier"],
                                                                 meta["cwd"])]
    if meta["mode"] == "read":
        rules.append("- READ-ONLY run: do not create, modify or delete any file. Commands that only "
                     "read or verify (git diff, tests, linters) are fine.")
    else:
        rules.append("- Work only inside the scope the brief gives you. Do not run git commit, push, "
                     "checkout, reset or stash: leave your changes in the working tree.")
    style = choice.get("style")
    if style in STYLE_GUIDE:
        rules.append("- How to work: " + STYLE_GUIDE[style]["work"])
        if _needs_more_detail(brief_style(brief), style):
            rules.append("- This brief was written for a model that is given more latitude. Before you "
                         "act, turn it into explicit numbered steps for yourself, list them first in "
                         "your answer, then carry them out in order.")
    rules.append("- Your final message is the only thing the conductor reads. Follow your role's "
                 "return format, keep it under 400 words, no file dumps.")
    parts = [role_text.strip(), "---"]
    if meta.get("context"):
        parts.append(meta["context"])
    parts += ["## Run context", "\n".join(rules)]
    failed = [a for a in meta.get("attempts", []) if a.get("outcome") != "done"]
    if failed:
        parts += ["## Previous attempt",
                  "Another agent started this task and stopped (%s). Inspect the working tree first "
                  "(`git status`, `git diff`) and continue from what is already there."
                  % ", ".join("%s: %s" % (a["provider"], a["outcome"]) for a in failed)]
    parts += ["## Task brief", brief.strip()]
    return "\n\n".join(parts) + "\n"


def _snapshot(cwd: str) -> Optional[str]:
    try:
        p = subprocess.run(["git", "-C", cwd, "status", "--porcelain=v1", "-uall"], capture_output=True,
                           text=True, timeout=30)
        return p.stdout if p.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _run_cli(argv: List[str], stdin: Optional[str], cwd: str, timeout_s: int, run_dir: Path, n: int):
    out_path, err_path = run_dir / ("stdout.%d.log" % n), run_dir / ("stderr.%d.log" % n)
    with open(out_path, "w", encoding="utf-8") as out, open(err_path, "w", encoding="utf-8") as err:
        try:
            proc = subprocess.Popen(argv, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                    stdout=out, stderr=err, cwd=cwd, text=True, start_new_session=True)
        except OSError as e:
            return 127, "", str(e), False
        timed_out = False
        try:
            proc.communicate(stdin, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(10)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    pass
    read = lambda p: p.read_text(encoding="utf-8", errors="replace")  # noqa: E731
    return proc.returncode, read(out_path), read(err_path), timed_out


def execute(run_dir: Path) -> None:
    """Runs in the detached child: try providers in order until one finishes or none is left."""
    meta = _meta(run_dir)
    project = Path(meta["project"])
    cfg = config.load(project)
    fb = cfg["limit_fallback"]
    exclude: List[str] = []
    started = time.time()

    def finish(status: str, **extra):
        meta.update(status=status, finished=_now(), minutes=round((time.time() - started) / 60, 1), **extra)
        _save(run_dir, meta)
        log(project, event="finish", via="cli", run=meta["id"], role=meta["role"], label=meta.get("label"),
            status=status,
            provider=meta.get("provider"), model=meta.get("model"), minutes=meta["minutes"],
            switched=bool(meta.get("switched")), independent=meta.get("independent"),
            skipped=[x.get("provider") for x in meta.get("skipped") or []],
            substituted=meta.get("substituted"),
            failed=[a["provider"] + ":" + a["outcome"] for a in meta["attempts"] if a["outcome"] != "done"])

    while True:
        try:
            choice = roster.pick(meta["role"], cfg, avoid=meta.get("avoid"), exclude=exclude,
                                 skill=meta.get("skill"))
        except roster.NoModel as e:
            hit_limit = any(a.get("outcome") == "limit" for a in meta["attempts"])
            return finish("limit" if hit_limit else "no_model", error=str(e))
        prov = PROVIDERS[choice["provider"]]
        binary = prov.find(cfg)
        if not binary:
            exclude.append(choice["provider"])
            meta["attempts"].append({"provider": choice["provider"], "outcome": "not installed"})
            continue
        for k in ("substituted", "dropped", "independent", "weak_fit"):
            meta.pop(k, None)
        meta.update(status="running", **_brief_choice(choice))
        meta["switched"] = bool(choice["switched"] or meta["attempts"])
        meta["skipped"] = choice["skipped"]
        _save(run_dir, meta)

        n = len(meta["attempts"]) + 1
        out_file = str(run_dir / ("last-message.%d.txt" % n))
        spec = {"model": choice["model"], "effort": choice.get("effort")}
        argv, stdin = prov.command(binary, spec, meta["mode"], _prompt(meta, choice), meta["cwd"], out_file)
        extra = list(((cfg["providers"].get(prov.name) or {}).get("extra_args")) or [])
        argv = argv[:-1] + extra + argv[-1:] if argv[-1] == "-" else argv + extra
        before = _snapshot(meta["cwd"]) if meta["mode"] == "read" else None
        limits.count_call(prov.name)
        code, stdout, stderr, timed_out = _run_cli(argv, stdin, meta["cwd"], meta["timeout_minutes"] * 60,
                                                   run_dir, n)
        if timed_out:
            meta["attempts"].append({"provider": prov.name, "model": choice["model"], "outcome": "timeout"})
            return finish("timeout", error="no answer within %d minutes" % meta["timeout_minutes"])

        text, reported_error = prov.final(stdout, out_file)
        failed = code != 0 or reported_error or not text.strip()
        evidence = "\n".join([stderr[-3000:], stdout[-3000:], text[:2000]])
        if failed and LIMIT_RX.search(evidence):
            m = LIMIT_RX.search(evidence)
            line = next((ln for ln in evidence.splitlines() if m.group(0) in ln), m.group(0))
            limits.mark_exhausted(prov.name, line, fb["cooldown_minutes"])
            meta["attempts"].append({"provider": prov.name, "model": choice["model"], "outcome": "limit"})
            if fb["enabled"]:
                exclude.append(prov.name)
                continue
            return finish("limit", error="%s reported a usage limit: %s" % (prov.label, line.strip()[:200]))
        # no final message means stdout holds the CLI's own output, not a worker's prose
        model_evidence = "\n".join([stderr[-3000:], text[:1500] if reported_error else "",
                                    stdout[-3000:] if not text.strip() else ""])
        refusal = model_refusal(model_evidence, choice["model"]) if failed else None
        if refusal:
            # this account does not have the model: remember it and let the next candidate take over
            limits.mark_missing(prov.name, choice["model"], refusal)
            meta["attempts"].append({"provider": prov.name, "model": choice["model"],
                                     "outcome": "model unavailable"})
            continue
        if failed:
            meta["attempts"].append({"provider": prov.name, "model": choice["model"], "outcome": "error"})
            tail = (stderr.strip() or stdout.strip() or "no output")[-800:]
            return finish("error", error="%s exited with code %s: %s" % (prov.label, code, tail))

        meta["attempts"].append({"provider": prov.name, "model": choice["model"], "outcome": "done"})
        if before is not None:
            after = _snapshot(meta["cwd"])
            if after is not None and after != before:
                changed = sorted(set(after.splitlines()) ^ set(before.splitlines()))
                meta["violation"] = {"rule": "read-only run changed the working tree", "files": changed[:20]}
        (run_dir / "result.md").write_text(text.strip() + "\n", encoding="utf-8")
        return finish("done")


# -- images --------------------------------------------------------------------------------

IMAGE_MAGIC = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"), (b"GIF8", "gif"))
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def image_format(path: Path) -> Optional[str]:
    """png / jpg / webp / gif when the file really is a raster image, else None."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(16)
    except OSError:
        return None
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return next((fmt for magic, fmt in IMAGE_MAGIC if head.startswith(magic)), None)


def image_providers_cfg(cfg: Optional[dict]) -> List[str]:
    """Selected, working providers whose CLI can generate raster images, in the user's order."""
    if not cfg:
        return []
    provs = cfg.get("providers") or {}
    allowed = cfg.get("allowed_providers")
    return [p for p in cfg.get("order") or [] if p in PROVIDERS and PROVIDERS[p].image and p in provs
            and not provs[p].get("disabled") and (not allowed or p in allowed)]


def _new_images(dirs: List[Path], since: float, depth: int = 3) -> List[Path]:
    found = []
    for base in dirs:
        if not base.is_dir():
            continue
        stack = [(base, 0)]
        while stack:
            d, lvl = stack.pop()
            try:
                entries = list(d.iterdir())
            except OSError:
                continue
            for e in entries:
                if e.is_dir() and lvl < depth:
                    stack.append((e, lvl + 1))
                elif e.suffix.lower() in IMAGE_EXT and e.is_file() and e.stat().st_mtime >= since - 1:
                    found.append(e)
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def image(project: Path, cfg: dict, description: str, out_path: Path, aspect: Optional[str],
          timeout_s: int = 300) -> dict:
    """Generate one raster image through a provider's own CLI and save it at out_path.

    Experimental. Tries each image-capable provider in the user's order; a provider that returns
    no real image file is skipped. Raises NoModel when none of them delivers."""
    names = image_providers_cfg(cfg)
    if not names:
        raise roster.NoModel("no selected provider can generate images (Codex and Antigravity can)")
    fb = cfg["limit_fallback"]
    state = limits.load()
    attempts = []
    for name in names:
        prov = PROVIDERS[name]
        if fb["enabled"]:
            ok, reason = limits.availability(name, cfg, state)
            if not ok:
                attempts.append({"provider": name, "outcome": reason})
                continue
        binary = prov.find(cfg)
        tiers = (cfg["providers"].get(name) or {}).get("tiers") or {}
        gone = limits.missing(state)
        spec = next((tiers[t] for t in ("S2", "S1", "S3", "S4")
                     if tiers.get(t) and tiers[t].get("model") and (name, tiers[t]["model"]) not in gone), None)
        if not binary or not spec:
            attempts.append({"provider": name, "outcome": "not installed" if not binary else "no model"})
            continue
        run_id = "%s-image-%s" % (datetime.now().strftime("%m%d-%H%M%S"), uuid.uuid4().hex[:4])
        run_dir = work_dir(project) / "images" / run_id
        run_dir.mkdir(parents=True)
        target = run_dir / "image.png"
        prompt = ("Generate exactly one raster image with your image generation tool.\n"
                  "- Do not write code, and do not draw it as SVG, HTML or with a script.\n"
                  "- Do not create, change or delete any other file.\n"
                  "- Save it as: %s\n"
                  "  If your tool saves it somewhere else, leave it there and give the full path in your answer.\n"
                  "%s"
                  "- Answer with the path of the image file and nothing else.\n\n"
                  "Image description:\n%s\n" % (target, "- Aspect ratio: %s\n" % aspect if aspect else "",
                                                 description.strip()))
        started = time.time()
        out_file = str(run_dir / "last-message.txt")
        argv, stdin = prov.image_command(binary, spec, prompt, str(run_dir), out_file)
        limits.count_call(name)
        code, stdout, stderr, timed_out = _run_cli(argv, stdin, str(run_dir), timeout_s, run_dir, 1)
        text, _ = prov.final(stdout, out_file)
        evidence = "\n".join([stderr[-3000:], stdout[-3000:], text[:2000]])
        if code != 0 and LIMIT_RX.search(evidence):
            limits.mark_exhausted(name, LIMIT_RX.search(evidence).group(0), fb["cooldown_minutes"])
            attempts.append({"provider": name, "outcome": "limit"})
            continue
        mentioned = [Path(m) for m in re.findall(r"(/[^\s`'\"<>]+\.(?:png|jpe?g|webp|gif))", text or "", re.I)]
        cands = [target] + _new_images([run_dir], started, 2) + _new_images(prov.image_dirs(), started) + mentioned
        hit = next((c for c in cands if c.is_file() and image_format(c)), None)
        if not hit:
            attempts.append({"provider": name, "model": spec["model"],
                             "outcome": "timeout" if timed_out else "no image file produced"})
            continue
        fmt = image_format(hit)
        dest = Path(out_path)
        if dest.suffix.lower().lstrip(".").replace("jpeg", "jpg") != fmt:
            dest = dest.with_suffix("." + fmt)                  # never save a JPEG under a .png name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(hit.read_bytes())
        attempts.append({"provider": name, "model": spec["model"], "outcome": "done"})
        log(project, event="image", provider=name, model=spec["model"], path=str(dest),
            seconds=round(time.time() - started))
        return {"ok": True, "path": str(dest), "format": fmt, "bytes": dest.stat().st_size,
                "provider": name, "model": spec["model"], "seconds": round(time.time() - started),
                "renamed": str(dest) != str(out_path), "attempts": attempts}
    raise roster.NoModel("no image was produced: " + "; ".join(
        "%s: %s" % (a["provider"], a["outcome"]) for a in attempts))


# -- collection ----------------------------------------------------------------------------

def _row(meta: dict) -> dict:
    keys = ("id", "role", "label", "unit", "mode", "status", "provider", "model", "tier", "minutes", "switched",
            "substituted", "dropped", "weak_fit", "error", "violation")
    row = {k: meta[k] for k in keys if meta.get(k) not in (None, False)}
    if meta.get("independent") is False:
        row["independent"] = False
    if len(meta.get("attempts", [])) > 1:
        row["attempts"] = meta["attempts"]
    return row


def wait(project: Path, run_ids: List[str], timeout: int) -> dict:
    dirs = [find_run(project, r) for r in run_ids]
    deadline = time.time() + timeout
    while True:
        metas = [_meta(d) for d in dirs]
        pending = [m["id"] for m in metas if m.get("status") not in TERMINAL]
        if not pending or time.time() >= deadline:
            return {"all_finished": not pending, "pending": pending, "runs": [_row(m) for m in metas]}
        time.sleep(2)


def result(project: Path, run_id: str, full: bool, cfg: dict) -> str:
    run_dir = find_run(project, run_id)
    meta = _meta(run_dir)
    head = json.dumps(_row(meta), ensure_ascii=False)
    path = run_dir / "result.md"
    if not path.is_file():
        return head
    text = path.read_text(encoding="utf-8")
    cap = cfg.get("result_chars", 6000)
    if not full and len(text) > cap:
        text = text[:cap].rstrip() + "\n… [truncated; full text: %s]" % path
    return head + "\n\n" + text


def list_runs(project: Path) -> List[dict]:
    base = work_dir(project) / "runs"
    return [_row(_meta(d)) for d in sorted(base.glob("*")) if d.is_dir()] if base.is_dir() else []


def report(project: Path) -> dict:
    """Who actually did the work in this project: one entry per run, plus every model switch."""
    path = work_dir(project) / "log.jsonl"
    used, switches, problems, minutes = {}, [], [], 0.0
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            native = e.get("event") == "dispatch" and e.get("via") == "native"
            if not (native or e.get("event") == "finish"):
                continue
            if native or e.get("status") == "done":
                key = "%s -> %s:%s" % (e.get("label") or e.get("role"), e.get("provider"), e.get("model"))
                used[key] = used.get(key, 0) + 1
            else:
                problems.append({k: e.get(k) for k in ("role", "status", "provider", "run")})
            minutes += e.get("minutes") or 0
            if e.get("switched") or e.get("failed"):
                switches.append({"role": e.get("label") or e.get("role"), "ran_on": "%s:%s" % (e.get("provider"), e.get("model")),
                                 "instead_of": sorted(set((e.get("skipped") or []) +
                                                          [f.split(":")[0] for f in e.get("failed") or []])),
                                 "run": e.get("run")})
            if e.get("independent") is False:
                problems.append({"role": e.get("role"), "status": "review not independent", "run": e.get("run")})
    return {"runs": used, "switches": switches, "problems": problems, "worker_minutes": round(minutes, 1)}


def new_brief(project: Path, role: str, cfg: dict, style: Optional[str] = None) -> dict:
    """Create the next numbered brief from the template that suits the model this role runs on."""
    name = role
    role = roster.canonical(role)[0]
    model = None
    if style is None:
        try:
            choice = roster.pick(role, cfg)
            model = "%s:%s" % (choice["provider"], choice["model"])
            style = "peer" if role == "decider" else choice.get("style")
        except roster.NoModel:
            style = None
        style = style or ("peer" if role == "decider" else "structured")
    d = work_dir(project) / "briefs"
    d.mkdir(exist_ok=True)
    n = 1 + max([int(f.name[:2]) for f in d.glob("[0-9][0-9]-*.md")] or [0])
    path = d / ("%02d-%s.md" % (n, name))
    template = SKILL_DIR / "templates" / "briefs" / (style + ".md")
    text = template.read_text(encoding="utf-8") if template.is_file() else "# Brief · <role>\n"
    path.write_text(text.replace("<role>", name), encoding="utf-8")
    guide = STYLE_GUIDE[style]
    return {"path": str(path), "role": role, "model": model, "style": style,
            "written_for": guide["for"], "put_in": guide["write"]}


# -- worktrees -----------------------------------------------------------------------------

def _git(cwd: Path, *args: str, stdin: Optional[str] = None):
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, input=stdin)
    return p.returncode, p.stdout, p.stderr


def worktree_add(project: Path, name: str) -> dict:
    path = work_dir(project) / "wt" / name
    code, out, err = _git(project, "worktree", "add", "-b", "agentack/" + name, str(path), "HEAD")
    if code != 0:
        return {"ok": False, "error": err.strip()}
    return {"ok": True, "path": str(path), "note": "starts from HEAD: uncommitted changes in the main "
                                                    "tree are not included; install dependencies if "
                                                    "the project needs them to run tests"}


def worktree_apply(project: Path, name: str, remove: bool) -> dict:
    """Bring a worktree's changes into the main tree as uncommitted changes (no commits are made)."""
    path = work_dir(project) / "wt" / name
    if not path.is_dir():
        return {"ok": False, "error": "no such worktree: %s" % name}
    _git(path, "add", "-A")
    code, patch, err = _git(path, "diff", "--cached", "--binary", "HEAD")
    if code != 0:
        return {"ok": False, "error": err.strip()}
    if not patch.strip():
        result_ = {"ok": True, "changed": False}
    else:
        code, out, err = _git(project, "apply", "--whitespace=nowarn", "-", stdin=patch)
        if code != 0 and _git(project, "diff", "--cached", "--quiet")[0] == 0:
            # plain apply failed and nothing is staged: a 3-way merge is safe to try, then unstage it
            code, out, err = _git(project, "apply", "--3way", "--whitespace=nowarn", "-", stdin=patch)
            _git(project, "reset", "-q")
        if code != 0:
            return {"ok": False, "error": "patch did not apply cleanly", "details": err.strip()[-1500:],
                    "worktree": str(path)}
        code, files, _ = _git(path, "diff", "--cached", "--name-only", "HEAD")
        result_ = {"ok": True, "changed": True, "files": files.split()}
    if remove:
        result_["removed"] = worktree_remove(project, name)["ok"]
    return result_


def worktree_remove(project: Path, name: str) -> dict:
    path = work_dir(project) / "wt" / name
    code, out, err = _git(project, "worktree", "remove", "--force", str(path))
    _git(project, "branch", "-D", "agentack/" + name)
    return {"ok": code == 0, "error": err.strip() or None}
