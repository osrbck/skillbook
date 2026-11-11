"""Usage-limit state shared by every agentack run on this machine.

Three sources, in order of trust:
  * a limit error returned by a provider's CLI   -> the provider is exhausted until its reset time
  * a measured usage percentage (Codex app-server, Claude Code status line data)
  * agentack's own call counter (informational)
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from . import config
from .providers import PROVIDERS

USAGE_MAX_AGE = timedelta(hours=6)      # older measurements are ignored
MISSING_MAX_AGE = timedelta(days=7)     # re-try a model the account lacked after a week
PROBE_EVERY = timedelta(minutes=5)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts) -> Optional[datetime]:
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts / 1000 if ts > 1e11 else ts, tz=timezone.utc)
        s = str(ts)
        d = datetime.fromisoformat(s[:-1] + "+00:00" if s.endswith("Z") else s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def _path():
    return config.state_dir() / "limits.json"


def load() -> dict:
    return config.read_json(_path()) or {}


def _update(provider: str, **fields) -> dict:
    state = load()
    entry = state.setdefault(provider, {})
    entry.update(fields)
    config.write_json(_path(), state)
    return entry


def reset_minutes(text: str) -> Optional[int]:
    """Best-effort: 'try again in 2h 15m', 'resets in 45 minutes', 'retry after 3600s'."""
    rx = re.compile(r"\b(?:in|after)\s+(?:(\d+)\s*(?:h|hr|hrs|hours?)\b)?\s*"
                    r"(?:(\d+)\s*(?:m|min|mins|minutes?)\b)?\s*(?:(\d+)\s*(?:s|sec|secs|seconds?)\b)?", re.I)
    for m in rx.finditer(text or ""):
        if any(m.groups()):
            h, mi, s = (int(g) if g else 0 for g in m.groups())
            return max(1, h * 60 + mi + (s + 59) // 60)
    return None


def mark_exhausted(provider: str, text: str, cooldown: int) -> dict:
    minutes = reset_minutes(text) or cooldown
    until = _now() + timedelta(minutes=minutes)
    return _update(provider, exhausted_until=until.isoformat(timespec="seconds"),
                   exhausted_reason=" ".join((text or "").split())[:200])


def clear(provider: str) -> None:
    _update(provider, exhausted_until=None, exhausted_reason=None)


def mark_missing(provider: str, model: str, reason: str = "") -> None:
    """Remember that this account cannot use a model, so later runs skip it without trying."""
    state = load()
    state.setdefault("_missing", {})["%s\t%s" % (provider, model)] = {
        "at": _now().isoformat(timespec="seconds"), "reason": " ".join((reason or "").split())[:200]}
    config.write_json(_path(), state)


def missing(state: Optional[dict] = None) -> set:
    """{(provider, model)} learned at run time and still fresh."""
    entries = ((state if state is not None else load()).get("_missing") or {})
    out = set()
    for key, info in entries.items():
        at = _parse((info or {}).get("at"))
        if at and _now() - at <= MISSING_MAX_AGE and "\t" in key:
            out.add(tuple(key.split("\t", 1)))
    return out


def clear_missing(providers) -> None:
    state = load()
    entries = state.get("_missing") or {}
    state["_missing"] = {k: v for k, v in entries.items() if k.split("\t", 1)[0] not in set(providers)}
    config.write_json(_path(), state)


def set_usage(provider: str, windows: dict, source: str) -> dict:
    return _update(provider, usage={"windows": windows, "source": source,
                                    "checked_at": _now().isoformat(timespec="seconds")})


def count_call(provider: str) -> None:
    today = _now().date().isoformat()
    entry = load().get(provider, {})
    calls = entry.get("calls", {})
    _update(provider, calls={today: calls.get(today, 0) + 1})


def availability(provider: str, cfg: dict, state: Optional[dict] = None) -> Tuple[bool, Optional[str]]:
    """(usable, reason). Only meaningful when limit_fallback is enabled."""
    entry = (state if state is not None else load()).get(provider) or {}
    until = _parse(entry.get("exhausted_until"))
    if until and until > _now():
        return False, "limit reached, resets %s" % until.astimezone().strftime("%H:%M")
    usage = entry.get("usage") or {}
    checked = _parse(usage.get("checked_at"))
    if checked and _now() - checked <= USAGE_MAX_AGE:
        threshold = cfg["limit_fallback"]["switch_at_percent"]
        for window, w in (usage.get("windows") or {}).items():
            reset = _parse(w.get("resets_at"))
            if reset and reset <= _now():
                continue                      # that window has rolled over since the measurement
            if w.get("used") is not None and float(w["used"]) >= threshold:
                return False, "%s usage %d%% >= %d%%" % (window, round(float(w["used"])), threshold)
    return True, None


def refresh(cfg: dict, force: bool = False) -> None:
    """Run cheap usage probes for selected providers that have one."""
    fb = cfg["limit_fallback"]
    if not (fb["enabled"] and fb["measure"]) and not force:
        return
    state = load()
    for name in cfg.get("order") or []:
        prov = PROVIDERS.get(name)
        if prov is None:
            continue
        entry = state.get(name) or {}
        last = _parse(entry.get("probed_at"))
        every = timedelta(minutes=getattr(prov, "probe_minutes", 5))
        if not force and last and _now() - last < every:
            continue
        binary = prov.find(cfg)
        if not binary:
            continue
        try:
            data = prov.limit_probe(binary)
        except Exception:
            data = None
        _update(name, probed_at=_now().isoformat(timespec="seconds"))   # also when nothing came back
        if data and data.get("windows"):
            set_usage(name, data["windows"], "probe")


def from_statusline(payload: dict) -> Optional[dict]:
    """Extract Claude Code rate limits from the JSON the status line command receives."""
    rl = payload.get("rate_limits") or payload.get("rateLimits") or {}
    windows = {}
    for key, label in (("five_hour", "5h"), ("seven_day", "7d")):
        w = rl.get(key) or {}
        used = w.get("used_percentage", w.get("utilization", w.get("used_percent")))
        if used is not None:
            windows[label] = {"used": float(used), "resets_at": w.get("resets_at")}
    if windows:
        set_usage("claude", windows, "statusline")
    return windows or None


def summary(cfg: dict) -> list:
    state = load()
    rows = []
    for name in cfg.get("order") or []:
        entry = state.get(name) or {}
        ok, reason = availability(name, cfg, state)
        usage = entry.get("usage") or {}
        rows.append({"provider": name, "available": ok, "reason": reason,
                     "usage": usage.get("windows"), "source": usage.get("source"),
                     "checked_at": usage.get("checked_at"),
                     "calls_today": (entry.get("calls") or {}).get(_now().date().isoformat(), 0)})
    return rows
