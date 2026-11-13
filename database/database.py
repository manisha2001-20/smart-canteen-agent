"""SQLite access layer.

Every operation opens a short-lived connection, which keeps things safe when
Streamlit runs several sessions (student + staff) at the same time.
`transaction()` uses BEGIN IMMEDIATE so that two concurrent orders can never
read the same "next token number" or oversell stock.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from database.schema import SCHEMA_SQL


class Database:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def connection(self):
        """Autocommit connection for simple reads/writes."""
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        """Atomic, write-locked block: commits on success, rolls back on error."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    # --- convenience helpers ---
    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple = ()):
        with self.connection() as conn:
            return conn.execute(sql, params).fetchone()

    def execute(self, sql: str, params: tuple = ()) -> int:
        with self.connection() as conn:
            return conn.execute(sql, params).lastrowid

    def init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(SCHEMA_SQL)
        finally:
            conn.close()

    def is_seeded(self) -> bool:
        row = self.query_one("SELECT COUNT(*) AS n FROM menu_items")
        return bool(row and row["n"])
