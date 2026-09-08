#!/usr/bin/env bash
cd "$(dirname "$0")/.."
exec python scripts/install_mcp.py "$@"
