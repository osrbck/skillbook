# Sourced by the skillbook installer. Not copied into the agent's skills folder.
# Available: $SKILL, $SRC (this folder), $CLAUDE_DIR, $CODEX_DIR, $AGY_DIR, $CONFIG_HOME, $STATE_HOME.

post_install() {
  local name email
  echo
  if ! command -v git >/dev/null 2>&1; then
    echo "  git is not installed: gitcommit needs it."
    return 0
  fi
  name="$(git config --global user.name 2>/dev/null || true)"
  email="$(git config --global user.email 2>/dev/null || true)"
  if [ -n "$name" ] && [ -n "$email" ]; then
    echo "Your commits will carry: $name <$email>"
    echo "(a repository's own user.name / user.email wins where it is set)"
  else
    echo "git does not know who you are yet. Set it once:"
    echo '  git config --global user.name "Your Name"'
    echo '  git config --global user.email you@example.com'
  fi
  echo
  echo "Run: /gitcommit"
}
