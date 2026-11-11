"""Configuration: user config (~/.config/agentack/config.json) merged with a project file (.agentack.json)."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULTS: Dict[str, Any] = {
    "version": 2,
    "order": [],                 # selected providers, in priority order
    "providers": {},             # name -> {"bin": str|None, "tiers": {S1..S4: {"model","effort"}|None}, "extra_args": []}
    "roles": {},                 # role -> provider preference chain
    "second_opinion": True,      # decider asks a second vendor's S4 when one exists
    "native_subagents": True,    # Claude Code host + claude provider -> use the host's own subagents
    "limit_fallback": {
        "enabled": False,
        "switch_at_percent": 85,
        "measure": True,                     # read usage where a provider exposes it
        "builders_may_drop_one_tier": True,
        "cooldown_minutes": 60,              # used when a limit error gives no reset time
    },
    "timeouts": {"S1": 10, "S2": 45, "S3": 30, "S4": 30},   # minutes per run
    "result_chars": 6000,        # how much of a worker's final message `result` prints
    "allowed_providers": None,   # project-level allowlist (set in .agentack.json)
    "statusline_passthrough": None,
}


def config_path() -> Path:
    if os.environ.get("AGENTACK_CONFIG"):
        return Path(os.environ["AGENTACK_CONFIG"]).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(Path.home(), ".config")
    return Path(base) / "agentack" / "config.json"


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(Path.home(), ".local", "state")
    d = Path(base) / "agentack"
    d.mkdir(parents=True, exist_ok=True)
    return d


def project_root(start: Optional[str] = None) -> Path:
    """Main repository root (also when called from inside a linked worktree), else the cwd."""
    cwd = Path(start or os.getcwd()).resolve()
    try:
        out = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            common = Path(out.stdout.strip())
            return common.parent if common.name == ".git" else cwd
    except (OSError, subprocess.SubprocessError):
        pass
    return cwd


def _merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in extra.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def read_json(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, data: dict) -> None:
    """Atomic write so concurrent runs never read a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def load(project: Optional[Path] = None) -> dict:
    cfg = _merge(DEFAULTS, read_json(config_path()) or {})
    cfg["_configured"] = bool(cfg.get("order"))
    if project:
        proj = read_json(Path(project) / ".agentack.json")
        if proj:
            cfg = _merge(cfg, proj)
            cfg["_project_config"] = True
    return cfg


def save(cfg: dict) -> Path:
    path = config_path()
    write_json(path, {k: v for k, v in cfg.items() if not k.startswith("_")})
    return path
