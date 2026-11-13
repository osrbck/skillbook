# Sourced by the skillbook installer. Not copied into the agent's skills folder.
# Available: $SKILL, $SRC (this folder), $CLAUDE_DIR, $CODEX_DIR, $AGY_DIR, $CONFIG_HOME, $STATE_HOME.

post_install() {
  echo
  echo "Run: /new-skill <what the skill should do>   or   /new-skill   to build one from the session"
}

post_uninstall() {
  if [ -d "$STATE_HOME/new-skill" ]; then
    echo "  drafts and backups were left in: $STATE_HOME/new-skill"
  fi
}
