"""
Saved results (history), in SQLite.

Each processed document keeps its file name, the model's result, the user's
corrections and which flagged fields they have checked. The PDF itself is
never stored: to see the pages again, the user uploads it again.

Results hold personal data (names, tax IDs, addresses). Set
HISTORY_RETENTION_DAYS to delete entries older than that many days.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path

from jobs import summary

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id       TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    model    TEXT NOT NULL,
    created  REAL NOT NULL,
    updated  REAL NOT NULL,
    result   TEXT NOT NULL,  -- the model's answer, with _validation and _meta
    edited   TEXT,           -- the deed as the user corrected it, if they did
    reviewed TEXT NOT NULL   -- JSON list of flagged fields the user has checked
)
"""


def to_check(result: dict, reviewed: list[str]) -> int:
    """Flagged fields the user has not ticked as checked yet."""
    flagged = {i.get("field") for i in result.get("_validation") or []}
    return len(flagged - set(reviewed))


class History:
    def __init__(self, path: Path, retention_days: float | None = None) -> None:
        self.path = path
        self.retention_days = retention_days
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute(SCHEMA)

    def _db(self) -> sqlite3.Connection:
        # One short connection per call: safe from the job threads and the API threads alike
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def _run(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with closing(self._db()) as db, db:
            return db.execute(sql, args).fetchall()

    def purge(self) -> None:
        if self.retention_days:
            self._run("DELETE FROM documents WHERE created < ?", (time.time() - self.retention_days * 86400,))

    def add(self, filename: str, model: str, result: dict) -> str:
        doc_id = uuid.uuid4().hex
        now = time.time()
        self._run(
            "INSERT INTO documents (id, filename, model, created, updated, result, edited, reviewed) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL, '[]')",
            (doc_id, filename, model, now, now, json.dumps(result, ensure_ascii=False)),
        )
        return doc_id

    def list(self, limit: int = 500) -> list[dict]:
        self.purge()
        rows = self._run("SELECT * FROM documents ORDER BY created DESC LIMIT ?", (limit,))
        items = []
        for row in rows:
            result, reviewed = json.loads(row["result"]), json.loads(row["reviewed"])
            current = json.loads(row["edited"]) if row["edited"] else result
            items.append({
                "id": row["id"],
                "filename": row["filename"],
                "model": row["model"],
                "created": row["created"],
                "updated": row["updated"],
                "edited": row["edited"] is not None,
                "summary": {**summary(current), "to_check": to_check(result, reviewed)},
            })
        return items

    def get(self, doc_id: str) -> dict | None:
        self.purge()
        rows = self._run("SELECT * FROM documents WHERE id = ?", (doc_id,))
        if not rows:
            return None
        row = rows[0]
        return {
            "id": row["id"],
            "filename": row["filename"],
            "model": row["model"],
            "created": row["created"],
            "updated": row["updated"],
            "result": json.loads(row["result"]),
            "edited": json.loads(row["edited"]) if row["edited"] else None,
            "reviewed": json.loads(row["reviewed"]),
        }

    def update(self, doc_id: str, edited: dict | None, reviewed: list[str]) -> bool:
        rows = self._run(
            "UPDATE documents SET edited = ?, reviewed = ?, updated = ? WHERE id = ? RETURNING id",
            (json.dumps(edited, ensure_ascii=False) if edited is not None else None,
             json.dumps(reviewed, ensure_ascii=False), time.time(), doc_id),
        )
        return bool(rows)

    def delete(self, doc_id: str) -> bool:
        return bool(self._run("DELETE FROM documents WHERE id = ? RETURNING id", (doc_id,)))
