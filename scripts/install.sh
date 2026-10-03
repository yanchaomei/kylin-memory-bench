#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
PREFIX="${PREFIX:-$HOME/.local/share/kylin-memory-bench}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
"$PYTHON" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ is required"'
mkdir -p "$PREFIX" "$BIN_DIR"
cp -R "$ROOT/kylin_memory_bench" "$PREFIX/"
cp "$ROOT/kmb" "$PREFIX/kmb"
cp -R "$ROOT/configs" "$PREFIX/"
cp -R "$ROOT/data" "$PREFIX/"
cp -R "$ROOT/docs" "$PREFIX/"
chmod +x "$PREFIX/kmb"
ln -sfn "$PREFIX/kmb" "$BIN_DIR/kmb"
printf 'Installed: %s\nRun: %s doctor\n' "$BIN_DIR/kmb" "$BIN_DIR/kmb"
