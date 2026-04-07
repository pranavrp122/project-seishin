"""SQLite warehouse + job metadata. Thin execution path for validated read-only SQL."""
import os
import sqlite3
from typing import Any

from .config import DATA_DIR, WAREHOUSE_DB_PATH


def ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _conn() -> sqlite3.Connection:
    ensure_data_dir()
    conn = sqlite3.connect(WAREHOUSE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_warehouse_schema() -> None:
    """Create demo analytic tables, seed rows, and report_jobs if missing."""
    ensure_data_dir()
    with _conn() as conn:
        conn.executescript(
            """
            PRAGMA journal_mode = WAL;

            CREATE TABLE IF NOT EXISTS report_jobs (
              job_id TEXT PRIMARY KEY,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              user_request TEXT,
              parsed_intent_json TEXT,
              sql_text TEXT,
              status TEXT,
              row_count INTEGER,
              error TEXT,
              tableau_link TEXT,
              summary_text TEXT,
              sample_result_json TEXT
            );

            CREATE TABLE IF NOT EXISTS customers (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL,
              team TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
              id INTEGER PRIMARY KEY,
              customer_id INTEGER NOT NULL,
              amount_cents INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
            CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
            """
        )
        cur = conn.execute("SELECT COUNT(*) AS c FROM customers")
        if cur.fetchone()["c"] == 0:
            conn.executemany(
                "INSERT INTO customers (id, name, team) VALUES (?, ?, ?)",
                [
                    (1, "Acme Corp", "sales"),
                    (2, "Globex", "engineering"),
                    (3, "Initech", "operations"),
                ],
            )
            conn.executemany(
                "INSERT INTO orders (id, customer_id, amount_cents, created_at) VALUES (?, ?, ?, ?)",
                [
                    (101, 1, 19900, "2026-03-01"),
                    (102, 1, 4500, "2026-03-15"),
                    (103, 2, 120000, "2026-03-20"),
                    (104, 3, 8800, "2026-04-01"),
                    (105, 2, 22000, "2026-04-02"),
                ],
            )
        conn.commit()


def execute_read_only_sql(sql: str, max_rows: int) -> list[dict[str, Any]]:
    """Run a single validated SELECT. Raises sqlite3.Error on failure."""
    init_warehouse_schema()
    with _conn() as conn:
        cur = conn.execute(sql)
        rows = cur.fetchmany(max_rows + 1)
    if len(rows) > max_rows:
        rows = rows[:max_rows]
    return [dict(r) for r in rows]
