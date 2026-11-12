#!/usr/bin/env bash
# One-time setup for ResearchChat on Linux / macOS:
#   a .venv on Python 3.11-3.13, the packages, and a .env to fill in.
# Safe to run again: it reuses what's already there.
set -euo pipefail
cd "$(dirname "$0")/.."

supported='import sys; sys.exit(not ((3, 11) <= sys.version_info[:2] <= (3, 13)))'

find_python() {
  for candidate in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "$supported" 2>/dev/null; then
      command -v "$candidate"
      return 0
    fi
  done
  # Python installed by uv (`uv python install 3.11`) isn't on PATH
  if command -v uv >/dev/null 2>&1; then
    uv python find '>=3.11,<3.14' 2>/dev/null && return 0
  fi
  return 1
}

# 1. Python environment
if [ -x .venv/bin/python ]; then
  if ! .venv/bin/python -c "$supported"; then
    echo "The existing .venv uses $(.venv/bin/python --version), which ResearchChat doesn't support."
    echo "Remove it (rm -rf .venv) and run this script again."
    exit 1
  fi
  echo "Using the existing .venv ($(.venv/bin/python --version))."
else
  if ! python_bin="$(find_python)"; then
    echo "Python 3.11-3.13 wasn't found (Python 3.14 doesn't work with Chainlit yet)."
    echo "Install one, for example with uv (https://docs.astral.sh/uv/):"
    echo "  uv python install 3.11"
    echo "then run this script again."
    exit 1
  fi
  echo "Creating .venv with $("$python_bin" --version)..."
  "$python_bin" -m venv .venv
fi

# 2. Packages
echo "Installing packages..."
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt

# 3. Settings
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example."
fi
if grep -q '^OPENROUTER_API_KEY=your-key-here' .env; then
  echo
  echo "Next: put your OpenRouter key in .env (OPENROUTER_API_KEY=...)."
  echo "      Get one at https://openrouter.ai/keys"
fi

# 4. Optional: Docker for running notebook code
if ! command -v docker >/dev/null 2>&1; then
  echo
  echo "Optional: install Docker to run notebook code (chat and search work without it)."
elif ! docker image inspect researchchat-kernel:1 >/dev/null 2>&1; then
  echo
  echo "Optional: to run notebook code, build the kernel image once:"
  echo "  docker build -f docker/kernel.Dockerfile -t researchchat-kernel:1 docker"
fi

echo
echo "Done. Start the app with:"
echo "  .venv/bin/chainlit run app.py"
echo "then open http://localhost:8000"
