#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ -x /opt/homebrew/bin/python3 ]]; then
  BUILDER_PYTHON=/opt/homebrew/bin/python3
elif [[ -x /usr/local/bin/python3 ]]; then
  BUILDER_PYTHON=/usr/local/bin/python3
else
  echo 'Install Python with Homebrew first: brew install python'
  read -r -p 'Press Enter to close...' _
  exit 1
fi
if "$BUILDER_PYTHON" build.py; then
  echo 'Installation complete.'
else
  echo 'Build stopped. See the error above.'
fi
read -r -p 'Press Enter to close...' _
