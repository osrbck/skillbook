# Sourced by the skillbook installer. Not copied into the agent's skills folder.
# Available: $SKILL, $SRC (this folder), $CLAUDE_DIR, $CODEX_DIR, $AGY_DIR, $CONFIG_HOME, $STATE_HOME.

post_install() {
  echo
  echo "Agent CLIs the research team can run on:"
  for bin in claude codex agy kiro-cli; do
    if command -v "$bin" >/dev/null 2>&1; then
      echo "  + $bin"
    else
      echo "  - $bin (not on PATH)"
    fi
  done
  echo
  echo "Run: /deepsearch setup     then: /deepsearch medium <topic>"
}
