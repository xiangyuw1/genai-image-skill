#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
SKILL_NAME="genai-image-generation"
SKILL_SRC="$SCRIPT_DIR/skills/$SKILL_NAME"

usage() {
  cat <<'EOF'
Install the genai-image-generation skill into one or more agent skill directories.

Usage:
  ./install.sh [OPTIONS]

Options:
  --target NAME|PATH   Install into NAME (claude, opencode, codex, agents) or a
                       skills directory path. Repeatable.
  --all                Install into every standard agent directory.
  --copy               Copy files instead of creating a symlink.
  --force              Replace an existing non-symlink destination.
  --uninstall          Remove the installed skill instead of installing it.
  --list               Show resolved destinations and exit.
  -h, --help           Show this help.

Default: auto-detect agent directories that already exist. If none are found,
install into ~/.agents/skills.

Examples:
  ./install.sh
  ./install.sh --target opencode --target codex --copy
  ./install.sh --target ~/my-agent/skills
  ./install.sh --uninstall
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

if [[ ! -f "$SKILL_SRC/SKILL.md" ]]; then
  die "skill not found at $SKILL_SRC"
fi

MODE="link"
FORCE=0
UNINSTALL=0
LIST_ONLY=0
ALL=0
TARGETS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      [[ $# -ge 2 ]] || die "--target requires a value"
      TARGETS+=("$2")
      shift 2
      ;;
    --all) ALL=1; shift ;;
    --copy) MODE="copy"; shift ;;
    --force) FORCE=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    --list) LIST_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1 (use --help)" ;;
  esac
done

resolve_target() {
  local target="$1"
  case "$target" in
    claude)   printf '%s\n' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills" ;;
    opencode) printf '%s\n' "${XDG_CONFIG_HOME:-$HOME/.config}/opencode/skills" ;;
    codex)    printf '%s\n' "${CODEX_HOME:-$HOME/.codex}/skills" ;;
    agents)   printf '%s\n' "${AGENTS_HOME:-$HOME/.agents}/skills" ;;
    ~*)       printf '%s\n' "${target/#\~/$HOME}" ;;
    *)        printf '%s\n' "$target" ;;
  esac
}

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  if [[ $ALL -eq 1 ]]; then
    TARGETS=(claude opencode codex agents)
  else
    [[ -d "${CLAUDE_CONFIG_DIR:-$HOME/.claude}" ]] && TARGETS+=(claude)
    [[ -d "${XDG_CONFIG_HOME:-$HOME/.config}/opencode" ]] && TARGETS+=(opencode)
    [[ -d "${CODEX_HOME:-$HOME/.codex}" ]] && TARGETS+=(codex)
    [[ -d "${AGENTS_HOME:-$HOME/.agents}" ]] && TARGETS+=(agents)
    if [[ ${#TARGETS[@]} -eq 0 ]]; then
      TARGETS=(agents)
    fi
  fi
fi

DESTINATIONS=()
for target in "${TARGETS[@]}"; do
  DESTINATIONS+=("$(resolve_target "$target")/$SKILL_NAME")
done

if [[ $LIST_ONLY -eq 1 ]]; then
  for dest in "${DESTINATIONS[@]}"; do
    if [[ -e "$dest" || -L "$dest" ]]; then
      echo "installed  $dest"
    else
      echo "available  $dest"
    fi
  done
  exit 0
fi

for dest in "${DESTINATIONS[@]}"; do
  parent="$(dirname "$dest")"

  if [[ $UNINSTALL -eq 1 ]]; then
    if [[ -e "$dest" || -L "$dest" ]]; then
      rm -rf "$dest"
      echo "removed    $dest"
    else
      echo "skip       $dest (not installed)"
    fi
    continue
  fi

  if [[ -e "$dest" || -L "$dest" ]]; then
    if [[ -L "$dest" ]]; then
      rm -f "$dest"
    elif [[ $FORCE -eq 1 ]]; then
      rm -rf "$dest"
    else
      die "destination exists and is not a symlink: $dest (use --force to replace)"
    fi
  fi

  mkdir -p "$parent"

  if [[ "$MODE" == "link" ]]; then
    ln -s "$SKILL_SRC" "$dest"
    echo "linked     $dest -> $SKILL_SRC"
  else
    cp -R "$SKILL_SRC" "$dest"
    echo "copied     $dest"
  fi
done
