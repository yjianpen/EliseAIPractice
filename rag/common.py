"""Shared paths, taxonomy loading and text helpers for the RAG databases."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE = ROOT / "knowledge"
POLICY_DIR = KNOWLEDGE / "policies"
LAW_DIR = KNOWLEDGE / "laws"
SYNTHETIC_DIR = ROOT / "data" / "synthetic"
DB_DIR = ROOT / "data" / "rag"
POLICIES_DB = DB_DIR / "policies.db"
LAWS_DB = DB_DIR / "laws.db"

URGENCY_RANK = {"city": 0, "routine": 1, "urgent": 2, "emergency": 3}

_STOPWORDS = set("""
a an and are as at be been but by can could did do does doing for from had has have how i i'm if in into is it
its me my no not of on or our please so that the their them then there these they this to too up us was we what
when where which who why will with would you your yours hi hello hey just about any also am im ive
apartment apartments unit units building buildings landlord landlords tenant tenants resident residents
property home get got going need want still been really very time times day days today
""".split()) # last two lines: domain words present in nearly every document, so they only add noise


@lru_cache(maxsize=1)
def taxonomy() -> dict:
    return json.loads((KNOWLEDGE / "taxonomy.json").read_text())["topics"]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", text.lower())).strip()


def detect_topics(text: str) -> list[str]:
    """Return taxonomy topics whose keywords appear in the text, most specific (longest keyword) first."""
    t = f" {normalize(text)} "
    hits: dict[str, int] = {}
    for topic, spec in taxonomy().items():
        for kw in spec["keywords"]:
            if f" {normalize(kw)} " in t:
                hits[topic] = max(hits.get(topic, 0), len(kw))
    return sorted(hits, key=lambda k: -hits[k])


def max_urgency(topics: list[str]) -> str | None:
    if not topics:
        return None
    return max((taxonomy()[t]["urgency"] for t in topics), key=URGENCY_RANK.__getitem__)


def fts_query(text: str) -> str:
    """Turn free text into a safe FTS5 OR-query of quoted terms (no FTS syntax injection)."""
    terms = [w for w in normalize(text).replace("'", " ").split() if len(w) > 2 and w not in _STOPWORDS]
    seen = dict.fromkeys(terms)  # de-duplicate, keep order
    return " OR ".join(f'"{w}"' for w in seen)
