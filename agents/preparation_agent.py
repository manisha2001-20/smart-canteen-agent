"""Preparation Agent - owns the order state machine and kitchen estimates.

PENDING -> CONFIRMED -> PREPARING -> READY -> COLLECTED
   \\-----------\\------------\\--> CANCELLED
"""
from agents.base_agent import BaseAgent
from database.database import Database
from models.models import (ALLOWED_TRANSITIONS, STATUS_TIMESTAMP_COLUMN, AgentResult, OrderError,
                           OrderStatus)
from services.queue_service import QueueService, WaitEstimate, order_prep_minutes
from utils.helpers import now_str


class PreparationAgent(BaseAgent):
    name = "PreparationAgent"

    def __init__(self, db: Database, queue_service: QueueService):
        super().__init__(db)
        self.queue = queue_service

    def _get_order(self, order_id: int):
        order = self.db.query_one("SELECT * FROM orders WHERE id = ?", (order_id,))
        if order is None:
            raise OrderError(f"Order #{order_id} not found.")
        return order

    def _transition(self, order_id: int, new_status: OrderStatus, changed_by: str,
                    extra_sets: dict | None = None) -> tuple[str, str]:
        order = self._get_order(order_id)
        current = OrderStatus(order["status"])
        if new_status not in ALLOWED_TRANSITIONS[current]:
            raise OrderError(f"Cannot change order from {current.value} to {new_status.value}.")

        ts = now_str()
        sets = {"status": new_status.value, "updated_at": ts, STATUS_TIMESTAMP_COLUMN[new_status]: ts}
        sets.update(extra_sets or {})
        assignments = ", ".join(f"{col} = ?" for col in sets)
        with self.db.transaction() as conn:
            # "AND status = ?" makes the update safe if two staff members click at once
            updated = conn.execute(
                f"UPDATE orders SET {assignments} WHERE id = ? AND status = ?",
                (*sets.values(), order_id, current.value),
            ).rowcount
            if not updated:
                raise OrderError("Order was updated by someone else. Please refresh.")
            conn.execute(
                "INSERT INTO order_status_history (order_id, from_status, to_status, changed_by, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (order_id, current.value, new_status.value, changed_by, ts),
            )
        return current.value, ts

    # ---------- intents ----------
    def on_confirm_order(self, order_id: int, lines: list[dict], estimate: WaitEstimate) -> AgentResult:
        """Put a freshly tokenised order into the kitchen queue."""
        prep = order_prep_minutes(lines)
        self._transition(order_id, OrderStatus.CONFIRMED, self.name, {
            "estimated_prep_minutes": prep,
            "estimated_wait_minutes": estimate.wait_minutes,
            "estimated_ready_at": estimate.ready_at,
            "queue_position": estimate.queue_position,
        })
        return AgentResult.ok(self.name, status=OrderStatus.CONFIRMED.value, prep_minutes=prep,
                              wait_minutes=estimate.wait_minutes, ready_at=estimate.ready_at,
                              queue_position=estimate.queue_position)

    def on_update_status(self, order_id: int, new_status: str, changed_by: str = "staff",
                         reason: str = "") -> AgentResult:
        try:
            target = OrderStatus(new_status)
        except ValueError:
            raise OrderError(f"Unknown status '{new_status}'.")
        extra = {"cancel_reason": reason[:200] or f"Cancelled by {changed_by}"} if target == OrderStatus.CANCELLED else None
        previous, ts = self._transition(order_id, target, changed_by, extra)
        return AgentResult.ok(self.name, order_id=order_id, previous=previous, status=target.value, at=ts)

    def on_refresh_estimates(self) -> AgentResult:
        """Re-estimate every queued order after the queue changed."""
        updates = self.queue.recompute_all()
        with self.db.transaction() as conn:
            for order_id, est in updates:
                conn.execute(
                    "UPDATE orders SET estimated_ready_at = ?, queue_position = ? WHERE id = ?",
                    (est.ready_at, est.queue_position, order_id),
                )
        return AgentResult.ok(self.name, refreshed=len(updates))
