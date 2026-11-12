# Sourced by the skillbook installer. Not copied into the agent's skills folder.
# Available: $SKILL, $SRC (this folder), $CLAUDE_HOME, $CLAUDE_DIR, $CODEX_DIR, $AGY_DIR,
#            $CONFIG_HOME, $STATE_HOME, $STAMP.

# 0.1 kept its ten roles as global subagents. 2.0 does not use them, and left in place they
# could be picked up in unrelated projects. Only files that are recognizably agentack's are moved.
retire_v1_agents() {
  local dir="$CLAUDE_HOME/agents" backup="$CLAUDE_HOME/backups/agentack-0.1-agents-$STAMP" name moved=0
  [ -d "$dir" ] || return 0
  for name in scout architect contract-guard be-go be-node fe-next fe-angular qa reviewer decider; do
    if [ -f "$dir/$name.md" ] && grep -qE 'agentack|fullstack-workflow' "$dir/$name.md"; then
      mkdir -p "$backup"
      mv "$dir/$name.md" "$backup/"
      moved=$((moved + 1))
    fi
  done
  if [ "$moved" -gt 0 ]; then echo "  moved $moved agentack 0.1 subagents to: $backup"; fi
}

# Earlier 2.0 previews were installed as "agentack2". Fold them into "agentack".
retire_preview() {
  local d
  for d in "$CLAUDE_DIR/agentack2" "$CODEX_DIR/agentack2" "$AGY_DIR/agentack2"; do
    if [ -d "$d" ]; then rm -rf "$d"; echo "  removed preview: $d"; fi
  done
  if [ -f "$CONFIG_HOME/agentack2/config.json" ] && [ ! -f "$CONFIG_HOME/agentack/config.json" ]; then
    mkdir -p "$CONFIG_HOME/agentack"
    cp "$CONFIG_HOME/agentack2/config.json" "$CONFIG_HOME/agentack/config.json"
    echo "  kept your roster: $CONFIG_HOME/agentack/config.json"
  fi
  if [ -f "$STATE_HOME/agentack2/limits.json" ] && [ ! -f "$STATE_HOME/agentack/limits.json" ]; then
    mkdir -p "$STATE_HOME/agentack"
    cp "$STATE_HOME/agentack2/limits.json" "$STATE_HOME/agentack/limits.json"
  fi
  rm -rf "$CONFIG_HOME/agentack2" "$STATE_HOME/agentack2"
  # a status line hook installed by the preview points at a script that no longer exists
  if [ -f "$CLAUDE_HOME/settings.json" ] && grep -q 'agentack2.py statusline' "$CLAUDE_HOME/settings.json"; then
    python3 - "$CLAUDE_HOME/settings.json" "$CLAUDE_DIR/agentack/scripts/agentack.py" <<'PY'
import json, shlex, sys
path, script = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)
# quoted: the command is run by a shell, and the path may contain spaces
data["statusLine"] = {"type": "command", "command": "python3 %s statusline" % shlex.quote(script)}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)
PY
    echo "  updated the status line hook in: $CLAUDE_HOME/settings.json"
  fi
}

post_install() {
  retire_v1_agents
  retire_preview
  echo
  echo "Agent CLIs on this machine:"
  python3 "$SRC/scripts/agentack.py" detect | python3 -c "$(cat <<'PY'
import json, sys
d = json.load(sys.stdin)
for p in d["providers"]:
    mark = "+" if p["installed"] else "-"
    extra = (p.get("version") or "") if p["installed"] else "not installed"
    print("  %s %-12s %s" % (mark, p["label"], extra))
PY
)"
  echo
  echo "Run: /agentack setup"
}

post_uninstall() {
  echo "  kept: $CONFIG_HOME/agentack (delete it to forget your roster)"
}
