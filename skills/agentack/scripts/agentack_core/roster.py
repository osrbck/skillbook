"""Roles are bound to tiers, tiers to models. This module decides who does what, right now."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from . import limits
from .providers import PROVIDERS, SKILLS, TIERS, WEAK, is_auto

ROLE_TIER = {
    "decider": "S4",
    "architect": "S3", "backend-architect": "S3", "designer": "S3", "reviewer": "S3",
    "backend": "S2", "frontend": "S2", "qa": "S2",
    "scout": "S1", "contract-guard": "S1",
}
ROLES = tuple(ROLE_TIER)
ROLE_SKILL = {
    "decider": "decide", "architect": "plan", "backend-architect": "plan", "designer": "visual",
    "reviewer": "review",
    "backend": "backend", "frontend": "frontend", "qa": "test", "scout": "mechanical", "contract-guard": "mechanical",
}
READ_ROLES = {"reviewer", "decider", "scout"}          # default run mode is read-only
GATE_ROLES = {"reviewer", "decider", "architect"}      # never downgraded, never on an "auto" model
DROP_OK = {"backend", "frontend", "qa", "scout"}
BUILDERS = ("backend", "frontend")
SPECIALISTS = {"designer"}                             # go to the provider rated best at their skill
TIER_PURPOSE = {"S4": "decision", "S3": "plan & review", "S2": "build", "S1": "mechanical"}


class NoModel(Exception):
    pass


def canonical(role: str):
    """`be-go` -> ("backend", "go"), `fe-angular` -> ("frontend", "angular"), `qa` -> ("qa", None).

    Builders are one role per layer; the project decides which stack they speak."""
    for prefix, base in (("be-", "backend"), ("fe-", "frontend"), ("fs-", "frontend")):
        if role.startswith(prefix) and len(role) > len(prefix):
            return base, role[len(prefix):]
    return role, None


def default_mode(role: str) -> str:
    return "read" if role in READ_ROLES else "write"


def default_roles(order: List[str]) -> Dict[str, List[str]]:
    """Builders follow the user's priority; the reviewer starts on a different provider when possible."""
    rotated = order[1:] + order[:1] if len(order) > 1 else list(order)
    return {role: (rotated if role == "reviewer" else list(order)) for role in ROLES}


def _spec(cfg: dict, provider: str, tier: str) -> Optional[dict]:
    spec = (((cfg.get("providers") or {}).get(provider) or {}).get("tiers") or {}).get(tier)
    return spec if spec and spec.get("model") else None


def rating(cfg: dict, provider: str, skill: str) -> int:
    """How good this provider is at a kind of work (1–5; 3 when nobody has rated it)."""
    custom = (cfg.get("ratings") or {}).get("%s:%s" % (provider, skill))
    return int(custom) if custom else PROVIDERS[provider].ratings.get(skill, 3)


def _providers(role: str, cfg: dict, skill: Optional[str] = None) -> List[str]:
    """Providers for a role, best choice first.

    The user's priority order decides, with three corrections: a provider that is weak at this
    kind of work goes to the back (last resort); the reviewer starts on a different vendor than
    the builders; and an explicit specialty (`skill`, e.g. visual) is served by the best-rated."""
    provs = cfg.get("providers") or {}
    allowed = cfg.get("allowed_providers")
    usable = [p for p in cfg.get("order") or [] if p in PROVIDERS and p in provs
              and not provs[p].get("disabled") and (not allowed or p in allowed)]
    custom = (cfg.get("roles") or {}).get(role)
    if custom and custom != default_roles(cfg.get("order") or []).get(role) and not skill:
        return [p for p in custom if p in usable]          # an order the user set by hand
    want = skill or ROLE_SKILL[role]
    index = {p: i for i, p in enumerate(usable)}
    if skill or role in SPECIALISTS:
        return sorted(usable, key=lambda p: (-rating(cfg, p, want), index[p]))
    chain = sorted(usable, key=lambda p: (rating(cfg, p, want) <= WEAK, index[p]))
    if role == "reviewer" and len(chain) > 1:
        builders = sorted(usable, key=lambda p: (rating(cfg, p, "backend") <= WEAK, index[p]))
        writer = PROVIDERS[builders[0]].vendor
        other = [p for p in chain if PROVIDERS[p].vendor != writer and rating(cfg, p, want) > WEAK]
        chain = other + [p for p in chain if p not in other]
    return chain


def candidates(role: str, cfg: dict, state: Optional[dict] = None, skill: Optional[str] = None) -> List[dict]:
    """Every (provider, tier, model) this role may run on, best first.

    Models the account does not have (never listed, pruned by `verify`, or refused at run time)
    are simply not candidates. When that empties the role's own tier on every provider, the
    nearest tier that does exist stands in, without asking anyone."""
    if role not in ROLE_TIER:
        raise NoModel("unknown role: %s" % role)
    tier = ROLE_TIER[role]
    provs = _providers(role, cfg, skill)
    want = skill or ROLE_SKILL[role]
    idx = TIERS.index(tier)
    gone = limits.missing(state)
    gate = role in GATE_ROLES

    def at(t: str, allow_auto: bool, **flags) -> List[dict]:
        out = []
        for p in provs:
            spec = _spec(cfg, p, t)
            if not spec or (p, spec["model"]) in gone:
                continue
            if is_auto(spec):
                if gate and not allow_auto:
                    continue
                if gate:
                    flags = dict(flags, auto_gate=True)
            out.append(dict(role=role, tier=t, provider=p, vendor=PROVIDERS[p].vendor,
                            model=spec["model"], effort=spec.get("effort"),
                            style=PROVIDERS[p].style(t, spec), fit=rating(cfg, p, want),
                            **({"weak_fit": True} if rating(cfg, p, want) <= WEAK else {}), **flags))
        return out

    out = at(tier, allow_auto=not gate)
    if not out:
        nearest = [TIERS[i] for i in range(idx - 1, -1, -1)] + list(TIERS[idx + 1:])
        # gate roles prefer any named model, on any tier, over a router ("auto") model
        for allow_auto in ((False, True) if gate else (True,)):
            for t in ([tier] if allow_auto and gate else []) + nearest:
                flags = {} if t == tier else {"substituted": True, "wanted": tier}
                out = at(t, allow_auto, **flags)
                if out:
                    break
            if out:
                break
    fb = cfg["limit_fallback"]
    if out and fb["enabled"] and fb["builders_may_drop_one_tier"] and role in DROP_OK and idx > 0:
        seen = {(c["provider"], c["model"], c.get("effort")) for c in out}
        out += [c for c in at(TIERS[idx - 1], True, dropped=True, wanted=tier)
                if (c["provider"], c["model"], c.get("effort")) not in seen]
    return out


def pick(role: str, cfg: dict, avoid: Optional[Iterable[str]] = None,
         exclude: Iterable[str] = (), state: Optional[dict] = None, skill: Optional[str] = None) -> dict:
    """Choose the model for one run. Honors limits only when limit_fallback is enabled."""
    state = limits.load() if state is None else state
    if skill and skill not in SKILLS:
        raise NoModel("unknown skill: %s (known: %s)" % (skill, ", ".join(SKILLS)))
    cands = candidates(role, cfg, state, skill)
    if not cands:
        raise NoModel("no usable model for %s on the selected providers" % role)
    avoid_vendors = {PROVIDERS[a].vendor for a in (avoid or []) if a in PROVIDERS}
    # stable partition: independent vendors first, within the same tier group
    primary = [c for c in cands if not c.get("dropped")]
    dropped = [c for c in cands if c.get("dropped")]
    ordered = []
    for group in (primary, dropped):
        # an independent vendor comes first, unless it is weak at this work
        indep = [c for c in group if c["vendor"] not in avoid_vendors and not c.get("weak_fit")]
        ordered += indep + [c for c in group if c not in indep and not c.get("weak_fit")]
        ordered += [c for c in group if c.get("weak_fit")]

    fb = cfg["limit_fallback"]
    skipped = []
    for c in ordered:
        if c["provider"] in exclude:
            skipped.append({"provider": c["provider"], "reason": "excluded after a failed attempt"})
            continue
        if fb["enabled"]:
            ok, reason = limits.availability(c["provider"], cfg, state)
            if not ok:
                skipped.append({"provider": c["provider"], "model": c["model"], "reason": reason})
                continue
        choice = dict(c)
        choice["independent"] = (c["vendor"] not in avoid_vendors) if avoid_vendors else None
        if choice["independent"] is False:
            others = [s_ for s_ in skipped if PROVIDERS[s_["provider"]].vendor not in avoid_vendors]
            choice["independence_note"] = (
                "another vendor is configured but unavailable: " +
                "; ".join("%s (%s)" % (o["provider"], o["reason"]) for o in others)
                if others else "no other vendor is configured for this role")
        choice["switched"] = bool(skipped)
        choice["skipped"] = skipped
        return choice
    why = "; ".join("%s: %s" % (s["provider"], s["reason"]) for s in skipped)
    if role in GATE_ROLES:
        raise NoModel("no %s model available for %s (%s); gate roles are never downgraded"
                      % (ROLE_TIER[role], role, why))
    raise NoModel("no model available for %s (%s)" % (role, why))


def table(cfg: dict, state: Optional[dict] = None) -> List[dict]:
    """The roster as it stands, ignoring live usage limits: primary model plus fallbacks per role."""
    state = limits.load() if state is None else state
    rows = []
    for role in ROLES:
        cands = candidates(role, cfg, state)
        fmt = ["%s:%s%s" % (c["provider"], c["model"], "@" + c["effort"] if c.get("effort") else "")
               for c in cands]
        first = cands[0] if cands else {}
        parts = []
        if not cands:
            parts.append("no usable model on the selected providers")
        if first.get("substituted"):
            parts.append("no %s model on your accounts, runs on %s" % (first["wanted"], first["tier"]))
        if first.get("auto_gate"):
            parts.append("runs on an Auto model (you cannot tell which model that is)")
        note = "; ".join(parts) or None
        if first.get("weak_fit"):
            parts.append("%s is weak at this kind of work (%d/5) and is used only because nothing "
                         "better is available" % (first["provider"], first["fit"]))
            note = "; ".join(parts)
        rows.append({"role": role, "tier": ROLE_TIER[role], "runs_on": first.get("tier"),
                     "style": first.get("style"), "skill": ROLE_SKILL[role], "fit": first.get("fit"),
                     "primary": fmt[0] if fmt else None, "fallbacks": fmt[1:], "note": note,
                     "substituted": bool(first.get("substituted"))})
    return rows


def notes(cfg: dict, state: Optional[dict] = None) -> List[str]:
    """Things the user should know about the roster. Informational: nothing here needs an answer."""
    out = ["%s: %s." % (r["role"], r["note"]) for r in table(cfg, state) if r["note"]]
    for name in cfg.get("order") or []:
        reason = ((cfg.get("providers") or {}).get(name) or {}).get("disabled")
        if reason:
            out.append("%s is set aside until it passes `verify` again: %s" % (name, reason))
            continue
        for tier, model in sorted((((cfg.get("providers") or {}).get(name) or {}).get("unavailable") or {}).items()):
            out.append("%s: %s (%s) is not available on this account; other providers cover %s."
                       % (name, model, tier, tier))
    for prov, model in sorted(limits.missing(state)):
        if prov in (cfg.get("order") or []):
            out.append("%s refused model %s at run time; it is skipped." % (prov, model))
    return out


def check_conductor(host: str, model: str, cfg: dict) -> dict:
    """Is the conductor session on a plan-and-review class (S3+) model of its host?"""
    prov = PROVIDERS.get(host)
    if prov is None or not prov.conductor:
        return {"ok": False, "message": "%s cannot host the conductor in this release "
                                        "(supported: claude, codex, agy)." % host}
    words = set(prov.conductor_keywords)
    recommended = []
    for tier in ("S3", "S4"):
        spec = _spec(cfg, host, tier) or prov.tiers.get(tier)
        if spec:
            recommended.append(spec["model"])
            words.add(spec["model"].lower())
    low = "-".join((model or "").lower().replace("_", " ").split())     # "Gemini 3.1 Pro" -> gemini-3.1-pro
    ok = any(w in low for w in words)
    msg = None if ok else (
        "The conductor holds the whole workflow in context, so it should run on a plan-and-review "
        "class model (%s). This session is on '%s'." % (" or ".join(recommended), model))
    return {"ok": ok, "host": host, "model": model, "recommended": recommended, "message": msg}
