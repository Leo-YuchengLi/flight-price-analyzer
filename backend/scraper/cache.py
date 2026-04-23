"""SQLite-backed search result cache with TTL."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class SearchCache:
    def __init__(self, db_path: Path, ttl_hours: int = 6):
        self.db_path = db_path
        self.ttl = timedelta(hours=ttl_hours)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key       TEXT PRIMARY KEY,
                    result    TEXT NOT NULL,
                    scraped_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scraped_at ON cache(scraped_at)")

    @staticmethod
    def _make_key(
        origin: str, destination: str, date: str,
        cabin: str, currency: str, trip_type: str,
    ) -> str:
        raw = f"{origin.upper()}|{destination.upper()}|{date}|{cabin}|{currency}|{trip_type}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(
        self,
        origin: str, destination: str, date: str,
        cabin: str, currency: str, trip_type: str = "one_way",
    ) -> list[dict] | None:
        key = self._make_key(origin, destination, date, cabin, currency, trip_type)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT result, scraped_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
        if not row:
            return None
        result_json, scraped_at_str = row
        scraped_at = datetime.fromisoformat(scraped_at_str)
        if datetime.now() - scraped_at > self.ttl:
            return None          # expired
        return json.loads(result_json)

    def set(
        self,
        result: list[dict],
        origin: str, destination: str, date: str,
        cabin: str, currency: str, trip_type: str = "one_way",
    ) -> None:
        key = self._make_key(origin, destination, date, cabin, currency, trip_type)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache VALUES (?, ?, ?)",
                (key, json.dumps(result, ensure_ascii=False),
                 datetime.now().isoformat()),
            )

    def invalidate(
        self,
        origin: str, destination: str, date: str,
        cabin: str, currency: str, trip_type: str = "one_way",
    ) -> None:
        key = self._make_key(origin, destination, date, cabin, currency, trip_type)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM cache WHERE key = ?", (key,))

    def clear_expired(self) -> int:
        cutoff = (datetime.now() - self.ttl).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("DELETE FROM cache WHERE scraped_at < ?", (cutoff,))
            return cur.rowcount

    def stats(self) -> dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            cutoff = (datetime.now() - self.ttl).isoformat()
            valid = conn.execute(
                "SELECT COUNT(*) FROM cache WHERE scraped_at >= ?", (cutoff,)
            ).fetchone()[0]
        return {"total": total, "valid": valid, "expired": total - valid}
