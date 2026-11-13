"""Queue and waiting-time estimation.

The estimator is behind an abstract interface (`WaitTimeEstimator`) so the
simple rule-based version below can later be swapped for an ML model trained
on the historical timestamps stored in the `orders` table.

Rule-based algorithm
--------------------
1. Prep time of one order  = slowest item's prep time
                             + 0.5 min for every extra unit (items cook in batches)
2. Orders ahead            = CONFIRMED / PREPARING orders placed earlier (FIFO)
   - a PREPARING order only counts its *remaining* minutes
3. Queue delay             = total minutes of work ahead / number of kitchen stations
4. Estimated wait          = ceil(queue delay + own prep time)
"""
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta

from database.database import Database
from models.models import QUEUE_STATUSES, OrderStatus
from utils.helpers import TS_FORMAT, now, parse_ts

EXTRA_UNIT_MINUTES = 0.5


@dataclass
class QueueEntry:
    order_id: int
    status: str
    prep_minutes: float
    preparing_at: str | None = None


@dataclass
class WaitEstimate:
    queue_position: int          # 1 = next to be served
    orders_ahead: int
    own_prep_minutes: float
    wait_minutes: int
    ready_at: str

    @property
    def label(self) -> str:
        return f"Estimated ready time: {self.wait_minutes} minutes"


def order_prep_minutes(lines: list[dict]) -> float:
    """Estimated kitchen time for one order. `lines` need prep_time_minutes + quantity."""
    if not lines:
        return 0.0
    slowest = max(int(l["prep_time_minutes"]) for l in lines)
    total_units = sum(int(l["quantity"]) for l in lines)
    return slowest + EXTRA_UNIT_MINUTES * (total_units - 1)


class WaitTimeEstimator(ABC):
    """Interface for any waiting-time model (rule-based today, ML tomorrow)."""

    @abstractmethod
    def estimate(self, ahead: list[QueueEntry], own_prep: float, at: datetime) -> WaitEstimate:
        ...


class RuleBasedEstimator(WaitTimeEstimator):
    def __init__(self, kitchen_stations: int = 2):
        self.kitchen_stations = max(1, kitchen_stations)

    @staticmethod
    def remaining_minutes(entry: QueueEntry, at: datetime) -> float:
        if entry.status == OrderStatus.PREPARING.value and entry.preparing_at:
            elapsed = (at - parse_ts(entry.preparing_at)).total_seconds() / 60
            return max(1.0, entry.prep_minutes - elapsed)
        return entry.prep_minutes

    def estimate(self, ahead: list[QueueEntry], own_prep: float, at: datetime) -> WaitEstimate:
        work_ahead = sum(self.remaining_minutes(e, at) for e in ahead)
        queue_delay = work_ahead / self.kitchen_stations
        wait = max(1, math.ceil(queue_delay + own_prep))
        return WaitEstimate(
            queue_position=len(ahead) + 1,
            orders_ahead=len(ahead),
            own_prep_minutes=round(own_prep, 1),
            wait_minutes=wait,
            ready_at=(at + timedelta(minutes=wait)).strftime(TS_FORMAT),
        )


class QueueService:
    def __init__(self, db: Database, estimator: WaitTimeEstimator | None = None, kitchen_stations: int = 2):
        self.db = db
        self.estimator = estimator or RuleBasedEstimator(kitchen_stations)

    def queue_entries(self) -> list[QueueEntry]:
        """All orders currently occupying the kitchen, oldest first."""
        placeholders = ",".join("?" * len(QUEUE_STATUSES))
        rows = self.db.query(
            f"""SELECT id, status, estimated_prep_minutes, preparing_at
                FROM orders WHERE status IN ({placeholders}) ORDER BY id""",
            QUEUE_STATUSES,
        )
        return [
            QueueEntry(r["id"], r["status"], r["estimated_prep_minutes"] or 0, r["preparing_at"])
            for r in rows
        ]

    def active_queue_count(self) -> int:
        return len(self.queue_entries())

    def estimate_for_new_order(self, lines: list[dict]) -> WaitEstimate:
        """Estimate for an order that is about to join the end of the queue."""
        return self.estimator.estimate(self.queue_entries(), order_prep_minutes(lines), now())

    def recompute_all(self) -> list[tuple[int, WaitEstimate]]:
        """Fresh estimate for every queued order (called whenever the queue changes)."""
        entries = self.queue_entries()
        at = now()
        results = []
        for i, entry in enumerate(entries):
            if entry.status == OrderStatus.PREPARING.value:
                own = RuleBasedEstimator.remaining_minutes(entry, at)
            else:
                own = entry.prep_minutes
            results.append((entry.order_id, self.estimator.estimate(entries[:i], own, at)))
        return results
