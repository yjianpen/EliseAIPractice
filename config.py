"""Load secrets (the OpenAI API key) without ever committing or printing them.

Lookup order: the OPENAI_API_KEY environment variable, then the gitignored .env file at the repo root.
Set it up once:  cp .env.example .env && chmod 600 .env   then paste your key into .env.
"""
from __future__ import annotations

import os
import stat
import warnings
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent / ".env"
PLACEHOLDER = "sk-your-key-here"


def load_env_file(path: Path = ENV_FILE) -> dict[str, str]:
    """Parse KEY=VALUE lines from a .env file; missing file -> {}. Warns if others can read the file."""
    if not path.exists():
        return {}
    if path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        warnings.warn(f"{path.name} is readable by other users; run: chmod 600 {path}", stacklevel=2)
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def get_openai_api_key(env_file: Path = ENV_FILE) -> str:
    """Return the OpenAI API key, or raise with setup instructions. The key itself is never logged."""
    key = os.environ.get("OPENAI_API_KEY") or load_env_file(env_file).get("OPENAI_API_KEY", "")
    if not key or key == PLACEHOLDER:
        raise RuntimeError("OPENAI_API_KEY is not set. Run `cp .env.example .env && chmod 600 .env` "
                           "and paste your key into .env, or export OPENAI_API_KEY in your shell.")
    return key
