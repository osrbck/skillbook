"""Antigravity (app, IDE and CLI): ~/.gemini/antigravity*/conversations/<id>.db.

Each conversation is an SQLite file. Its `steps` table holds one protobuf message per step in
`step_payload` and the step's metadata in `metadata`. There is no published schema, so this
adapter reads only what it has verified and skips everything else:

  metadata  1.1   time of the step (seconds)
            4     the tool call of the step: 4.2 its name, 4.3 its arguments as JSON
  payload   19.2  the user's request          (step_type 14)
            20.1  the agent's visible answer  (step_type 15)
  trajectory_metadata_blob.data  1.1  the workspace as a file:// URI
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from urllib.parse import unquote, urlparse

from ..model import Session
from ..redact import clean_prompt, looks_injected
from ..timeparse import in_range, to_dt
from ._util import configured, first_existing, modified_since

NAME = "agy"
LABEL = "Antigravity"

USER_STEP, ANSWER_STEP = 14, 15
SELF_COMMANDS = ("/worklog",)


def locate(cfg):
    base = first_existing(configured(cfg, NAME), Path.home() / ".gemini")
    if base and any(d.is_dir() for d in base.glob("antigravity*/conversations")):
        return base
    return None


def _varint(buf: bytes, i: int):
    value = shift = 0
    while True:
        byte = buf[i]
        i += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return value, i


def _fields(buf: bytes):
    """(field number, value) pairs of one protobuf message; [] when it does not parse."""
    out, i = [], 0
    try:
        while i < len(buf):
            key, i = _varint(buf, i)
            number, wire = key >> 3, key & 7
            if wire == 0:
                value, i = _varint(buf, i)
            elif wire == 2:
                size, i = _varint(buf, i)
                value = buf[i:i + size]
                if len(value) != size:
                    return []
                i += size
            elif wire == 1:
                value, i = buf[i:i + 8], i + 8
            elif wire == 5:
                value, i = buf[i:i + 4], i + 4
            else:
                return []
            out.append((number, value))
    except IndexError:
        return []
    return out


def _get(buf, *path):
    """Every value at a path of field numbers, e.g. _get(meta, 4, 2)."""
    level = [buf]
    for number in path:
        level = [v for b in level if isinstance(b, (bytes, bytearray)) for n, v in _fields(b) if n == number]
    return level


def _text(buf, *path) -> str:
    for value in _get(buf, *path):
        if isinstance(value, (bytes, bytearray)) and value:
            return bytes(value).decode("utf-8", "replace")
    return ""


def _workspace(con) -> str:
    try:
        row = con.execute("SELECT data FROM trajectory_metadata_blob LIMIT 1").fetchone()
    except sqlite3.Error:
        return ""
    uri = _text(row[0], 1, 1) if row and row[0] else ""
    return unquote(urlparse(uri).path) if uri.startswith("file://") else ""


def collect(base: Path, start, end, cfg, stats):
    out = []
    limit = cfg["prompt_chars"]
    for db in sorted(base.glob("antigravity*/conversations/*.db")):
        if not modified_since(db, start):
            continue
        stats["files"] = stats.get("files", 0) + 1
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        except sqlite3.Error as e:
            stats.setdefault("errors", []).append(f"{db.name}: {e}")
            continue
        try:
            s = Session(tool=NAME, session_id=db.stem, cwd=_workspace(con) or None)
            rows = con.execute("SELECT step_type, metadata, step_payload FROM steps ORDER BY idx")
            for step_type, meta, payload in rows:
                meta, payload = meta or b"", payload or b""
                seconds = next((v for v in _get(meta, 1, 1) if isinstance(v, int)), None)
                ts = to_dt(seconds) if seconds else None
                if not in_range(ts, start, end):
                    continue
                s.events.append(ts)
                if step_type == USER_STEP:
                    text = _text(payload, 19, 2)
                    if not text or looks_injected(text):
                        continue
                    if text.strip().startswith(SELF_COMMANDS):
                        s.events.pop()
                        continue
                    s.add_prompt(clean_prompt(text, limit))
                elif step_type == ANSWER_STEP:
                    answer = _text(payload, 20, 1)
                    if answer.strip():
                        s.last_reply = answer
                for call in _get(meta, 4):
                    try:
                        args = json.loads(_text(call, 3) or "{}")
                    except ValueError:
                        continue
                    if not isinstance(args, dict):
                        continue
                    if isinstance(args.get("TargetFile"), str):      # write_to_file, replace_file_content …
                        s.add_file(args["TargetFile"])
                    if isinstance(args.get("CommandLine"), str):     # run_command
                        s.add_command(args["CommandLine"])
                    if not s.cwd and isinstance(args.get("Cwd"), str):
                        s.cwd = args["Cwd"]
            out.append(s)
        except sqlite3.Error as e:
            stats.setdefault("errors", []).append(f"{db.name}: {e}")
        finally:
            con.close()
    return out
