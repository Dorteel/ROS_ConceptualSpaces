#!/usr/bin/env bash
# Focused standalone-tool tests; no ROS environment is needed.
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-all}" in
  backend) pattern='test_backend.py' ;;
  integration) pattern='test_wordnet_integration.py' ;;
  browser) pattern='test_browser.py' ;;
  all) pattern='test_*.py' ;;
  *) echo 'Usage: ./test.sh [all|backend|integration|browser]' >&2; exit 2 ;;
esac
exec "${PYTHON:-python3}" -m unittest discover -s tools/semantic_gradient/tests -p "$pattern" -v
