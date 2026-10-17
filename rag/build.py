"""Build the two RAG databases from knowledge/.

  data/rag/policies.db  company guidebooks + property addenda + building guides, chunked by "## " section
  data/rag/laws.db      law records per jurisdiction (federal, state, city)

Both are SQLite files with an FTS5 full-text index (BM25 ranking), so they need no
extra dependencies and can be inspected with any SQLite client.

Usage:  python -m rag.build
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .common import BUILDINGS_DIR, DB_DIR, LAW_DIR, LAWS_DB, POLICIES_DB, POLICY_DIR, ROOT, taxonomy

SECTION_META = re.compile(r"<!--\s*(.*?)\s*-->")


def parse_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        raise ValueError("policy document must start with a --- front matter block")
    _, header, body = text.split("---", 2)
    meta = {}
    for line in header.strip().splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, body


def parse_section_meta(comment: str) -> dict:
    """'topics: a, b | cities: New York' -> {'topics': [...], 'cities': [...]}"""
    out = {}
    for part in comment.split("|"):
        key, _, value = part.partition(":")
        out[key.strip()] = [v.strip() for v in value.split(",") if v.strip()]
    return out


def chunk_policy(path: Path) -> list[dict]:
    meta, body = parse_front_matter(path.read_text())
    known_topics = set(taxonomy())
    chunks = []
    for i, block in enumerate(re.split(r"^## ", body, flags=re.M)[1:], start=1):
        heading, _, rest = block.partition("\n")
        m = SECTION_META.search(rest)
        smeta = parse_section_meta(m.group(1)) if m else {}
        topics = smeta.get("topics", [])
        unknown = set(topics) - known_topics
        if unknown:
            raise ValueError(f"{path.name} / {heading}: unknown topics {sorted(unknown)}")
        if meta["scope"] == "property":
            cities = [meta["city"]]
        else:
            cities = smeta.get("cities", ["all"])
        text = SECTION_META.sub("", rest).strip()
        posted, expires = smeta.get("posted", [None])[0], smeta.get("expires", [None])[0]
        chunks.append(dict(
            chunk_id=f"{meta['doc_id']}#{i:02d}",
            doc_id=meta["doc_id"], doc_type=meta.get("doc_type", "policy"), valid_from=posted, valid_until=expires,
            scope=meta["scope"], company_id=meta["company_id"],
            property_id=meta.get("property_id"), cities=",".join(cities), doc_title=meta["title"],
            version=meta.get("version", ""), section=heading.strip(), topics=" ".join(topics), text=text,
            source_path=str(path.relative_to(ROOT)),
        ))
    return chunks


def build_policies(db_path: Path = POLICIES_DB) -> int:
    paths = (sorted((POLICY_DIR / "companies").glob("*.md")) + sorted((POLICY_DIR / "properties").glob("*.md"))
             + sorted(BUILDINGS_DIR.glob("*.md")))
    chunks = [c for p in paths for c in chunk_policy(p)]
    db_path.unlink(missing_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE chunks (
            chunk_id TEXT PRIMARY KEY, doc_id TEXT,
            doc_type TEXT CHECK (doc_type IN ('policy','building_guide')),
            valid_from DATE, valid_until DATE,  -- time-limited sections (notices); NULL = always valid
            scope TEXT CHECK (scope IN ('company','property')),
            company_id TEXT, property_id TEXT, cities TEXT, doc_title TEXT, version TEXT,
            section TEXT, topics TEXT, text TEXT, source_path TEXT);
        CREATE VIRTUAL TABLE chunks_fts USING fts5(
            chunk_id UNINDEXED, section, text, topics, tokenize = 'porter unicode61');
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
    """)
    con.executemany("INSERT INTO chunks VALUES (:chunk_id,:doc_id,:doc_type,:valid_from,:valid_until,:scope,"
                    ":company_id,:property_id,:cities,:doc_title,:version,:section,:topics,:text,:source_path)",
                    chunks)
    con.executemany("INSERT INTO chunks_fts VALUES (:chunk_id,:section,:text,:topics)", chunks)
    _write_meta(con, "policies", len(chunks), len(paths))
    con.commit()
    con.close()
    return len(chunks)


def load_laws() -> list[dict]:
    known_topics = set(taxonomy())
    laws, seen = [], set()
    for path in sorted(LAW_DIR.glob("*.json")):
        doc = json.loads(path.read_text())
        j = doc["jurisdiction"]
        for law in doc["laws"]:
            if law["id"] in seen:
                raise ValueError(f"duplicate law id {law['id']}")
            unknown = set(law["topics"]) - known_topics
            if unknown:
                raise ValueError(f"{law['id']}: unknown topics {sorted(unknown)}")
            seen.add(law["id"])
            laws.append(dict(
                law_id=law["id"], level=j["level"], city=j["city"], state=j["state"], citation=law["citation"],
                title=law["title"], topics=" ".join(law["topics"]), summary=law["summary"],
                key_points=json.dumps(law.get("key_points", [])), source_url=law["source_url"],
                verified_on=law.get("verified_on"), verification_note=law.get("verification_note", ""),
                source_path=str(path.relative_to(ROOT)),
            ))
    return laws


def build_laws(db_path: Path = LAWS_DB) -> int:
    laws = load_laws()
    db_path.unlink(missing_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE laws (
            law_id TEXT PRIMARY KEY, level TEXT CHECK (level IN ('federal','state','city')),
            city TEXT, state TEXT, citation TEXT, title TEXT, topics TEXT, summary TEXT, key_points TEXT,
            source_url TEXT, verified_on TEXT, verification_note TEXT, source_path TEXT);
        CREATE VIRTUAL TABLE laws_fts USING fts5(
            law_id UNINDEXED, title, citation, summary, key_points, topics, tokenize = 'porter unicode61');
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
    """)
    con.executemany("INSERT INTO laws VALUES (:law_id,:level,:city,:state,:citation,:title,:topics,:summary,"
                    ":key_points,:source_url,:verified_on,:verification_note,:source_path)", laws)
    con.executemany("INSERT INTO laws_fts VALUES (:law_id,:title,:citation,:summary,:key_points,:topics)", laws)
    _write_meta(con, "laws", len(laws), len(list(LAW_DIR.glob('*.json'))))
    con.commit()
    con.close()
    return len(laws)


def _write_meta(con: sqlite3.Connection, corpus: str, n_rows: int, n_files: int) -> None:
    con.executemany("INSERT INTO meta VALUES (?, ?)", [
        ("corpus", corpus), ("rows", str(n_rows)), ("source_files", str(n_files)),
        ("built_at", datetime.now(timezone.utc).isoformat(timespec="seconds")),
    ])


def build_all() -> tuple[int, int]:
    """Build both RAG databases and the structured property-facts database."""
    from structured.build import build as build_structured
    DB_DIR.mkdir(parents=True, exist_ok=True)
    build_structured()
    return build_policies(), build_laws()


def main() -> None:
    n_policy, n_law = build_all()
    print(f"policies.db: {n_policy} chunks -> {POLICIES_DB.relative_to(ROOT)}")
    print(f"laws.db:     {n_law} laws   -> {LAWS_DB.relative_to(ROOT)}")
    print("property_facts.db (structured) -> data/structured/property_facts.db")


if __name__ == "__main__":
    main()
