"""Token Agent - issues unique, sequential digital tokens.

Uniqueness is guaranteed at three levels:
  1. idempotency: asking twice for the same order returns the existing token
  2. BEGIN IMMEDIATE transaction: only one writer computes "next number" at a time
  3. database constraints: UNIQUE(order_id), UNIQUE(token_date, sequence_no), UNIQUE(token_code)
"""
import sqlite3

from agents.base_agent import BaseAgent
from database.database import Database
from models.models import AgentResult, OrderError
from services.queue_service import QueueService
from utils.helpers import now, now_str

MAX_RETRIES = 3


class TokenAgent(BaseAgent):
    name = "TokenAgent"

    def __init__(self, db: Database, queue_service: QueueService):
        super().__init__(db)
        self.queue = queue_service

    @staticmethod
    def format_token(sequence_no: int) -> str:
        return f"T{sequence_no:03d}"

    def get_token(self, order_id: int):
        return self.db.query_one("SELECT * FROM tokens WHERE order_id = ?", (order_id,))

    def on_issue_token(self, order_id: int, lines: list[dict]) -> AgentResult:
        order = self.db.query_one("SELECT id, status FROM orders WHERE id = ?", (order_id,))
        if order is None:
            raise OrderError(f"Cannot issue token: order #{order_id} not found.")

        existing = self.get_token(order_id)
        if existing:   # idempotent - never two tokens for one order
            token = dict(existing)
        else:
            token = self._create_token(order_id)

        # waiting time is estimated at the moment the token is issued
        estimate = self.queue.estimate_for_new_order(lines)
        return AgentResult.ok(
            self.name,
            token_number=token["token_number"],
            token_code=token["token_code"],
            sequence_no=token["sequence_no"],
            issued_at=token["issued_at"],
            reused=bool(existing),
            estimate=estimate,
        )

    def _create_token(self, order_id: int) -> dict:
        last_error = None
        for _ in range(MAX_RETRIES):
            try:
                with self.db.transaction() as conn:
                    day = now().strftime("%Y-%m-%d")
                    seq = conn.execute(
                        "SELECT COALESCE(MAX(sequence_no), 0) + 1 FROM tokens WHERE token_date = ?", (day,)
                    ).fetchone()[0]
                    token = {
                        "order_id": order_id,
                        "token_date": day,
                        "sequence_no": seq,
                        "token_number": self.format_token(seq),
                        "token_code": f"{day.replace('-', '')}-{self.format_token(seq)}",
                        "issued_at": now_str(),
                    }
                    conn.execute(
                        """INSERT INTO tokens (order_id, token_date, sequence_no, token_number, token_code, issued_at)
                           VALUES (:order_id, :token_date, :sequence_no, :token_number, :token_code, :issued_at)""",
                        token,
                    )
                    return token
            except sqlite3.IntegrityError as exc:
                last_error = exc
                existing = self.get_token(order_id)
                if existing:          # another process issued it concurrently
                    return dict(existing)
        raise OrderError(f"Could not generate a unique token: {last_error}")
