"""SQLite-backed URL frontier (source of truth). data/urls/url_frontier.csv is
re-exported after every mutating stage so the spec's CSV artifact stays current.

SQLite gives atomic status updates and upserts on normalized_url, which keeps
every stage restartable (spec Rule 6) while four different stages mutate the
frontier (discovery, prioritization, crawling, retry)."""

import datetime as dt
import sqlite3
from pathlib import Path

from src.common.columns import FRONTIER_COLUMNS, FRONTIER_STATUSES
from src.common.config import URLS_DIR
from src.common.io_utils import write_csv_dicts

DB_PATH = URLS_DIR / "frontier.db"
CSV_PATH = URLS_DIR / "url_frontier.csv"

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS frontier (
    frontier_id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    normalized_url TEXT NOT NULL UNIQUE,
    domain TEXT DEFAULT '',
    priority TEXT DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ({",".join(repr(s) for s in FRONTIER_STATUSES)})),
    discovered_from TEXT DEFAULT '',
    query_used TEXT DEFAULT '',
    first_seen_date TEXT DEFAULT '',
    last_checked_date TEXT DEFAULT '',
    retry_count INTEGER NOT NULL DEFAULT 0,
    crawl_error TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);
"""


class Frontier:
    def __init__(self, db_path: str | Path = DB_PATH):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(_SCHEMA)
        self.conn.commit()

    def __enter__(self) -> "Frontier":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    def upsert_urls(self, rows: list[dict]) -> int:
        """Insert new URLs; for existing not-yet-crawled rows, refresh priority and
        status (re-prioritization may promote/demote them). Returns rows inserted."""
        before = self.conn.execute("SELECT COUNT(*) FROM frontier").fetchone()[0]
        self.conn.executemany(
            """
            INSERT INTO frontier
                (url, normalized_url, domain, priority, status, discovered_from,
                 query_used, first_seen_date, retry_count, crawl_error, notes)
            VALUES
                (:url, :normalized_url, :domain, :priority, :status, :discovered_from,
                 :query_used, :first_seen_date, 0, '', :notes)
            ON CONFLICT(normalized_url) DO UPDATE SET
                priority = excluded.priority,
                status = excluded.status
            WHERE frontier.status IN ('new', 'queued', 'needs_review', 'rejected')
            """,
            rows,
        )
        self.conn.commit()
        after = self.conn.execute("SELECT COUNT(*) FROM frontier").fetchone()[0]
        return after - before

    def get_by_status(
        self,
        statuses: list[str],
        priorities: list[str] | None = None,
        limit: int | None = None,
    ) -> list[sqlite3.Row]:
        marks = ",".join("?" for _ in statuses)
        sql = f"SELECT * FROM frontier WHERE status IN ({marks})"
        params: list = list(statuses)
        if priorities:
            sql += f" AND priority IN ({','.join('?' for _ in priorities)})"
            params.extend(priorities)
        sql += " ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, frontier_id"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return self.conn.execute(sql, params).fetchall()

    def mark(self, frontier_id: int, status: str, error: str | None = None) -> None:
        self.conn.execute(
            "UPDATE frontier SET status = ?, last_checked_date = ?, crawl_error = ? "
            "WHERE frontier_id = ?",
            (status, dt.date.today().isoformat(), error or "", frontier_id),
        )
        self.conn.commit()

    def increment_retry(self, frontier_id: int) -> None:
        self.conn.execute(
            "UPDATE frontier SET retry_count = retry_count + 1 WHERE frontier_id = ?",
            (frontier_id,),
        )
        self.conn.commit()

    def requeue_failed(self, max_retries: int) -> int:
        cursor = self.conn.execute(
            "UPDATE frontier SET status = 'queued', retry_count = retry_count + 1 "
            "WHERE status = 'failed' AND retry_count < ?",
            (max_retries,),
        )
        self.conn.commit()
        return cursor.rowcount

    def counts(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT status, COUNT(*) FROM frontier GROUP BY status")
        return dict(rows.fetchall())

    def export_csv(self, path: str | Path = CSV_PATH) -> None:
        rows = self.conn.execute("SELECT * FROM frontier ORDER BY frontier_id").fetchall()
        write_csv_dicts(path, [dict(r) for r in rows], FRONTIER_COLUMNS)
