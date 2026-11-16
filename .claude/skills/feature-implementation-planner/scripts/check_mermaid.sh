#!/usr/bin/env bash
# Checks that every ```mermaid block in a Markdown file renders.
# Usage: check_mermaid.sh <file.md>   Exit 0 = all diagrams render, 1 = at least one fails.
set -uo pipefail
markdown_file="${1:?usage: check_mermaid.sh <file.md>}"
MERMAID_CLI_VERSION="11.4.2"

# mermaid-cli asks Puppeteer for one exact Chrome build, which is often not installed.
# Any recent Chrome renders the same, so reuse one that is already on the machine.
find_installed_browser() {
  local cached
  cached="$(ls -d "$HOME"/.cache/puppeteer/chrome-headless-shell/*/chrome-headless-shell-*/chrome-headless-shell \
                  "$HOME"/.cache/puppeteer/chrome/*/chrome-*/chrome 2>/dev/null | sort -V | tail -n 1)"
  if [ -n "$cached" ]; then echo "$cached"; return; fi
  command -v chromium google-chrome-stable google-chrome chromium-browser 2>/dev/null | head -n 1
}
if [ -z "${PUPPETEER_EXECUTABLE_PATH:-}" ]; then
  installed_browser="$(find_installed_browser)"
  [ -n "$installed_browser" ] && export PUPPETEER_EXECUTABLE_PATH="$installed_browser"
fi

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

awk -v dir="$work_dir" '
  /^[ \t]*```mermaid[ \t]*$/ { inside=1; count++; file=sprintf("%s/diagram_%02d.mmd", dir, count); start=NR; print start > (file ".line"); next }
  inside && /^[ \t]*```[ \t]*$/ { inside=0; close(file); next }
  inside { print > file }
' "$markdown_file"

shopt -s nullglob
diagrams=("$work_dir"/*.mmd)
if [ ${#diagrams[@]} -eq 0 ]; then echo "No mermaid blocks found in $markdown_file"; exit 0; fi

failed=0
for diagram in "${diagrams[@]}"; do
  line="$(cat "$diagram.line")"
  if output="$(npx -y "@mermaid-js/mermaid-cli@$MERMAID_CLI_VERSION" -q -i "$diagram" -o "$diagram.svg" 2>&1)"; then
    echo "OK    mermaid block at line $line"
  else
    echo "FAIL  mermaid block at line $line"; echo "$output" | grep -iE 'error|parse|expect' | head -5 | sed 's/^/      /'
    failed=1
  fi
done
exit $failed
