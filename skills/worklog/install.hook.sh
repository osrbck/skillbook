# Sourced by the skillbook installer. Not copied into the agent's skills folder.
# Available: $SKILL, $SRC (this folder), $CLAUDE_DIR, $CODEX_DIR, $AGY_DIR, $CONFIG_HOME, $STATE_HOME.

post_install() {
  echo
  echo "Session sources on this machine:"
  python3 "$SRC/scripts/worklog.py" --doctor | python3 -c "$(cat <<'PY'
import json, sys
d = json.load(sys.stdin)
for s in d["sources"]:
    mark = "+" if s["status"] == "found" else "-"
    print("  %s %-24s %s" % (mark, s["label"], s["path"] or s["status"]))
PY
)"
  echo
  echo "Run: /worklog today"
}
