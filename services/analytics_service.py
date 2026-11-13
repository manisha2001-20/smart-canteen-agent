"""Read-only analytics queries for the staff dashboard and Analytics page."""
import pandas as pd

from database.database import Database
from models.models import QUEUE_STATUSES
from utils.helpers import today_str


class AnalyticsService:
    def __init__(self, db: Database):
        self.db = db

    def _df(self, sql: str, params: tuple = ()) -> pd.DataFrame:
        rows = self.db.query(sql, params)
        return pd.DataFrame([dict(r) for r in rows])

    def today_summary(self, day: str | None = None) -> dict:
        day = day or today_str()
        placeholders = ",".join("?" * len(QUEUE_STATUSES))
        row = self.db.query_one(
            f"""SELECT
                  COUNT(*) AS total_orders,
                  SUM(status = 'COLLECTED') AS collected,
                  SUM(status = 'READY') AS ready,
                  SUM(status = 'CANCELLED') AS cancelled,
                  SUM(status IN ({placeholders})) AS in_queue,
                  COALESCE(SUM(CASE WHEN status != 'CANCELLED' THEN total_amount END), 0) AS revenue,
                  AVG(CASE WHEN ready_at IS NOT NULL AND preparing_at IS NOT NULL
                      THEN (julianday(ready_at) - julianday(preparing_at)) * 1440 END) AS avg_prep_minutes,
                  AVG(CASE WHEN ready_at IS NOT NULL
                      THEN (julianday(ready_at) - julianday(created_at)) * 1440 END) AS avg_wait_minutes,
                  AVG(CASE WHEN ready_at IS NOT NULL THEN estimated_wait_minutes END) AS avg_estimated_wait
                FROM orders WHERE date(created_at) = ?""",
            (*QUEUE_STATUSES, day),
        )
        summary = {k: (row[k] or 0) for k in row.keys()}
        summary["avg_order_value"] = (
            summary["revenue"] / (summary["total_orders"] - summary["cancelled"])
            if summary["total_orders"] - summary["cancelled"] > 0 else 0
        )
        return summary

    def status_distribution(self, day: str | None = None) -> pd.DataFrame:
        return self._df(
            "SELECT status, COUNT(*) AS orders FROM orders WHERE date(created_at) = ? GROUP BY status",
            (day or today_str(),),
        )

    def top_items(self, day: str | None = None, limit: int = 10) -> pd.DataFrame:
        return self._df(
            """SELECT oi.item_name AS item, SUM(oi.quantity) AS quantity, SUM(oi.line_total) AS revenue
               FROM order_items oi JOIN orders o ON o.id = oi.order_id
               WHERE date(o.created_at) = ? AND o.status != 'CANCELLED'
               GROUP BY oi.item_name ORDER BY quantity DESC LIMIT ?""",
            (day or today_str(), limit),
        )

    def orders_by_hour(self, day: str | None = None) -> pd.DataFrame:
        return self._df(
            """SELECT strftime('%H:00', created_at) AS hour, COUNT(*) AS orders
               FROM orders WHERE date(created_at) = ? GROUP BY hour ORDER BY hour""",
            (day or today_str(),),
        )

    def category_revenue(self, day: str | None = None) -> pd.DataFrame:
        return self._df(
            """SELECT m.category, SUM(oi.line_total) AS revenue
               FROM order_items oi JOIN orders o ON o.id = oi.order_id
               JOIN menu_items m ON m.id = oi.menu_item_id
               WHERE date(o.created_at) = ? AND o.status != 'CANCELLED'
               GROUP BY m.category ORDER BY revenue DESC""",
            (day or today_str(),),
        )

    def estimate_accuracy(self, limit: int = 50) -> pd.DataFrame:
        """Estimated vs actual wait for completed orders - training data for a future ML estimator."""
        return self._df(
            """SELECT t.token_number AS token, o.estimated_wait_minutes AS estimated,
                      ROUND((julianday(o.ready_at) - julianday(o.created_at)) * 1440, 1) AS actual
               FROM orders o JOIN tokens t ON t.order_id = o.id
               WHERE o.ready_at IS NOT NULL ORDER BY o.id DESC LIMIT ?""",
            (limit,),
        )

    def daily_history(self, days: int = 7) -> pd.DataFrame:
        return self._df(
            """SELECT date(created_at) AS day, COUNT(*) AS orders,
                      SUM(CASE WHEN status != 'CANCELLED' THEN total_amount ELSE 0 END) AS revenue
               FROM orders GROUP BY day ORDER BY day DESC LIMIT ?""",
            (days,),
        )
