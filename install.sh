#!/usr/bin/env bash
# skillbook — install AI agent skills for Claude Code, Codex, Antigravity and/or Kiro.
#
#   ./install.sh                         list the skills in this repo
#   ./install.sh <skill>...              install for Claude Code   (~/.claude/skills/<skill>)
#   ./install.sh <skill>... --codex      install for Codex         (~/.codex/skills/<skill>)
#   ./install.sh <skill>... --agy        install for Antigravity   (~/.gemini/config/skills/<skill>)
#   ./install.sh <skill>... --kiro       install for Kiro          (~/.kiro/skills/<skill>)
#   ./install.sh <skill>... --all        all four
#   ./install.sh <skill>... --uninstall  remove from all four
#   ./install.sh --everything [flags]    every skill in the repo
#
# Target flags can be combined (--codex --kiro). Each skill may ship an optional
# skills/<skill>/install.hook.sh with post_install / post_uninstall functions.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$ROOT/skills"
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CLAUDE_DIR="$CLAUDE_HOME/skills"
CODEX_DIR="${CODEX_HOME:-$HOME/.codex}/skills"
AGY_DIR="$HOME/.gemini/config/skills"
KIRO_DIR="${KIRO_HOME:-$HOME/.kiro}/skills"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
STAMP="$(date +%Y%m%d-%H%M%S)"

# Repo-only files that stay in the repo and are not copied into an agent's skills folder.
REPO_ONLY=(README.md 'README.*.md' CHANGELOG.md CONTRIBUTING.md install.hook.sh)

available() {
  local d
  for d in "$SKILLS_SRC"/*/; do [ -f "$d/SKILL.md" ] && basename "$d"; done
}

describe() {
  # first line of the description: field in SKILL.md frontmatter, cut to 90 chars
  sed -n 's/^description:[[:space:]]*//p' "$SKILLS_SRC/$1/SKILL.md" | head -n1 | cut -c1-90
}

list_skills() {
  echo "Skills in this skillbook:"
  local s
  for s in $(available); do printf "  %-14s %s...\n" "$s" "$(describe "$s")"; done
  echo
  echo "Install:  ./install.sh <skill>... [--codex] [--agy] [--kiro] [--all] [--uninstall]"
  echo "          ./install.sh --everything [--all]"
}

install_to() {   # <skill> <target dir>
  local skill="$1" dest="$2/$1" pat
  mkdir -p "$2"
  rm -rf "$dest"
  cp -R "$SKILLS_SRC/$skill" "$dest"
  for pat in "${REPO_ONLY[@]}"; do find "$dest" -maxdepth 1 -name "$pat" -exec rm -f {} +; done
  find "$dest" -name '__pycache__' -type d -prune -exec rm -rf {} +
  find "$dest/scripts" -maxdepth 1 -type f \( -name '*.py' -o -name '*.sh' \) -exec chmod +x {} + 2>/dev/null || true
  echo "  installed: $dest"
}

remove_from() {  # <skill> <target dir>
  if [ -d "$2/$1" ]; then rm -rf "${2:?}/$1"; echo "  removed: $2/$1"; fi
}

run_hook() {     # <skill> <function>
  local hook="$SKILLS_SRC/$1/install.hook.sh"
  [ -f "$hook" ] || return 0
  # hooks run in a subshell so one skill's functions never leak into the next
  ( SKILL="$1"; SRC="$SKILLS_SRC/$1"; # shellcheck source=/dev/null
    . "$hook"; if declare -F "$2" >/dev/null; then "$2"; fi )
}

skills=(); targets=(); uninstall=0; everything=0
for arg in "$@"; do
  case "$arg" in
    --codex)      targets+=("$CODEX_DIR") ;;
    --agy)        targets+=("$AGY_DIR") ;;
    --kiro)       targets+=("$KIRO_DIR") ;;
    --claude)     targets+=("$CLAUDE_DIR") ;;
    --all)        targets+=("$CLAUDE_DIR" "$CODEX_DIR" "$AGY_DIR" "$KIRO_DIR") ;;
    --uninstall)  uninstall=1 ;;
    --everything) everything=1 ;;
    --list|-l)    list_skills; exit 0 ;;
    -h|--help)    sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)           echo "unknown option: $arg" >&2; exit 2 ;;
    *)            skills+=("$arg") ;;
  esac
done

if [ "$everything" -eq 1 ]; then mapfile -t skills < <(available); fi
if [ "${#skills[@]}" -eq 0 ]; then list_skills; exit 0; fi

for s in "${skills[@]}"; do
  if [ ! -f "$SKILLS_SRC/$s/SKILL.md" ]; then
    echo "unknown skill: $s (run ./install.sh to list them)" >&2; exit 2
  fi
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required (3.8+)." >&2
  exit 1
fi

if [ "$uninstall" -eq 1 ]; then
  [ "${#targets[@]}" -gt 0 ] || targets=("$CLAUDE_DIR" "$CODEX_DIR" "$AGY_DIR" "$KIRO_DIR")
  for s in "${skills[@]}"; do
    for t in "${targets[@]}"; do remove_from "$s" "$t"; done
    run_hook "$s" post_uninstall
  done
  exit 0
fi

[ "${#targets[@]}" -gt 0 ] || targets=("$CLAUDE_DIR")
export CLAUDE_HOME CLAUDE_DIR CODEX_DIR AGY_DIR KIRO_DIR CONFIG_HOME STATE_HOME STAMP
for s in "${skills[@]}"; do
  echo "$s"
  for t in "${targets[@]}"; do install_to "$s" "$t"; done
  run_hook "$s" post_install
  echo
done
echo "Done. Restart your agent to pick up the new skills."
