#!/usr/bin/env bash
# One-command setup: creates .venv with Python 3.13 and installs dependencies.txt
set -euo pipefail
cd "$(dirname "$0")"
if command -v uv >/dev/null 2>&1; then
  [ -x .venv/bin/python ] || uv venv --python 3.13 .venv
  uv pip install --python .venv/bin/python -r dependencies.txt
else
  PY=$(command -v python3.13 || command -v python3.12 || true)
  if [ -z "$PY" ]; then
    echo "Need Python 3.12 or 3.13. Install with: brew install python@3.13 (or install uv)"; exit 1
  fi
  [ -x .venv/bin/python ] || "$PY" -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r dependencies.txt
fi
# DuckDB command-line tool (pip only installs the Python library).
# Placed in .venv/bin so `source .venv/bin/activate` puts `duckdb` on PATH.
DUCKDB_VERSION=$(.venv/bin/python -c "import duckdb; print(duckdb.__version__)")
if ! .venv/bin/duckdb --version >/dev/null 2>&1; then
  case "$(uname -s)-$(uname -m)" in
    Darwin-*)       ASSET=duckdb_cli-osx-universal.zip ;;
    Linux-x86_64)   ASSET=duckdb_cli-linux-amd64.zip ;;
    Linux-aarch64)  ASSET=duckdb_cli-linux-arm64.zip ;;
    *) echo "No DuckDB CLI download for this platform; skipping"; ASSET= ;;
  esac
  if [ -n "$ASSET" ]; then
    curl -fsSL -o .venv/duckdb_cli.zip "https://github.com/duckdb/duckdb/releases/download/v${DUCKDB_VERSION}/${ASSET}"
    unzip -o -q .venv/duckdb_cli.zip -d .venv/bin && rm -f .venv/duckdb_cli.zip
    chmod +x .venv/bin/duckdb
  fi
fi
.venv/bin/duckdb --version 2>/dev/null && echo "OK duckdb CLI in .venv/bin"
.venv/bin/python -c "import duckdb, pandas; print('OK duckdb', duckdb.__version__, '| pandas', pandas.__version__)"
echo "Activate with: source .venv/bin/activate"
