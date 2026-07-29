#!/bin/bash
# Double-click this file to fetch the newest WDFW reports and rebuild the dashboard.
cd "$(dirname "$0")" || exit 1
clear
echo "==================================================================="
echo "  WDFW Hatchery Escapement Dashboard — update"
echo "==================================================================="
echo

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys;exit(0 if sys.version_info>=(3,9) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done

if [ -z "$PY" ]; then
  echo "  Python 3.9 or newer is required and was not found."
  echo
  echo "  Install it from https://www.python.org/downloads/ (click the big"
  echo "  yellow button), then double-click this file again."
  echo
  read -n 1 -s -r -p "  Press any key to close."
  exit 1
fi

if [ ! -d .venv ]; then
  echo "  First run: setting up a private Python environment (about a minute)..."
  "$PY" -m venv .venv || { echo "  Could not create .venv"; read -n 1 -s -r -p "  Press any key."; exit 1; }
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip >/dev/null 2>&1
# Install from the hash-locked list: pip verifies the SHA-256 of every package and
# refuses anything that does not match, so a tampered release cannot get in.
if ! python -m pip install --quiet --require-hashes -r requirements.lock.txt; then
  echo
  echo "  Could not install the verified dependencies."
  echo "  If this persists, check your internet connection. Do NOT bypass the"
  echo "  hash check - it is what protects you from a tampered package."
  read -n 1 -s -r -p "  Press any key."; exit 1
fi

python src/pipeline.py "$@"
STATUS=$?

echo
if [ $STATUS -eq 0 ]; then
  echo "  Done. The dashboard should have opened in your browser."
else
  echo "  The update finished with problems — see the messages above."
fi
echo
read -n 1 -s -r -p "  Press any key to close this window."
echo
