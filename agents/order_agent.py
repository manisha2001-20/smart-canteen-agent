"""Order Agent - validates carts and creates orders."""
import uuid
from datetime import timedelta

from agents.base_agent import BaseAgent
from database.database import Database
from models.models import OPEN_STATUSES, AgentResult, MenuItem, OrderError, OrderStatus, ValidatedLine
from utils.config import Settings, get_settings
from utils.helpers import TS_FORMAT, now, now_str, request_hash


class OrderAgent(BaseAgent):
    name = "OrderAgent"

    def __init__(self, db: Database, settings: Settings | None = None):
        super().__init__(db)
        self.settings = settings or get_settings()

    # ---------- menu queries ----------
    def get_menu(self, only_available: bool = False) -> list[MenuItem]:
        rows = self.db.query("SELECT * FROM menu_items ORDER BY category, name")
        items = [MenuItem.from_row(r) for r in rows]
        return [i for i in items if i.orderable] if only_available else items

    def set_availability(self, menu_item_id: int, is_available: bool, stock: int | None = None) -> None:
        self.db.execute(
            "UPDATE menu_items SET is_available = ?, stock = ?, updated_at = ? WHERE id = ?",
            (int(is_available), stock, now_str(), menu_item_id),
        )

    # ---------- intents ----------
    def on_validate_order(self, lines: list[dict]) -> AgentResult:
        """Check items exist, are available, quantities are sane, and compute the total.

        `lines` is a list of {"menu_item_id": int, "quantity": int}.
        """
        if not lines:
            raise OrderError("Your cart is empty. Please select at least one item.")

        # merge repeated items (e.g. "dosa" added twice)
        merged: dict[int, int] = {}
        for line in lines:
            try:
                item_id, qty = int(line["menu_item_id"]), int(line["quantity"])
            except (KeyError, TypeError, ValueError):
                raise OrderError("Invalid cart line - each item needs an id and a whole-number quantity.")
            if qty <= 0:
                raise OrderError("Quantity must be at least 1.")
            merged[item_id] = merged.get(item_id, 0) + qty

        s = self.settings
        validated: list[ValidatedLine] = []
        for item_id, qty in merged.items():
            row = self.db.query_one("SELECT * FROM menu_items WHERE id = ?", (item_id,))
            if row is None:
                raise OrderError(f"Menu item #{item_id} does not exist.")
            item = MenuItem.from_row(row)
            if not item.is_available:
                raise OrderError(f"{item.name} is currently not available.")
            if qty > s.max_qty_per_item:
                raise OrderError(f"You can order at most {s.max_qty_per_item} x {item.name}.")
            if item.stock is not None and qty > item.stock:
                raise OrderError(
                    f"Only {item.stock} x {item.name} left today." if item.stock else f"{item.name} is sold out."
                )
            validated.append(ValidatedLine(item.id, item.name, qty, item.price, item.prep_time_minutes))

        total_units = sum(v.quantity for v in validated)
        if total_units > s.max_items_per_order:
            raise OrderError(f"Maximum {s.max_items_per_order} items per order (you have {total_units}).")

        total = round(sum(v.line_total for v in validated), 2)
        return AgentResult.ok(self.name, lines=[v.to_dict() for v in validated], total=total)

    def on_check_duplicate(self, student_id: int, lines: list[dict]) -> AgentResult:
        """Duplicate-order protection.

        Rejects (a) the identical cart from the same student within the
        duplicate window (double-click / refresh), and (b) too many open orders.
        """
        fingerprint = request_hash(student_id, lines)
        since = (now() - timedelta(seconds=self.settings.duplicate_window_seconds)).strftime(TS_FORMAT)
        dup = self.db.query_one(
            """SELECT o.order_code, t.token_number FROM orders o
               LEFT JOIN tokens t ON t.order_id = o.id
               WHERE o.student_id = ? AND o.request_hash = ? AND o.created_at >= ? AND o.status != 'CANCELLED'""",
            (student_id, fingerprint, since),
        )
        if dup:
            raise OrderError(
                f"Duplicate order blocked: you placed the same order moments ago "
                f"(token {dup['token_number'] or '-'}, {dup['order_code']})."
            )

        placeholders = ",".join("?" * len(OPEN_STATUSES))
        open_count = self.db.query_one(
            f"SELECT COUNT(*) AS n FROM orders WHERE student_id = ? AND status IN ({placeholders})",
            (student_id, *OPEN_STATUSES),
        )["n"]
        if open_count >= self.settings.max_active_orders_per_student:
            raise OrderError(
                f"You already have {open_count} active orders. Please collect them before ordering more."
            )
        return AgentResult.ok(self.name, request_hash=fingerprint)

    def on_create_order(self, student_id: int, lines: list[dict], total: float, request_hash: str,
                        source: str = "MENU", notes: str = "") -> AgentResult:
        """Persist the order + items and reserve stock in one atomic transaction."""
        ts = now_str()
        order_code = f"ORD-{now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        with self.db.transaction() as conn:
            for line in lines:   # re-check stock inside the lock (another student may have just ordered)
                row = conn.execute("SELECT name, stock, is_available FROM menu_items WHERE id = ?",
                                   (line["menu_item_id"],)).fetchone()
                if not row["is_available"] or (row["stock"] is not None and row["stock"] < line["quantity"]):
                    raise OrderError(f"{row['name']} just went out of stock.")
                if row["stock"] is not None:
                    conn.execute("UPDATE menu_items SET stock = stock - ?, updated_at = ? WHERE id = ?",
                                 (line["quantity"], ts, line["menu_item_id"]))

            order_id = conn.execute(
                """INSERT INTO orders (order_code, student_id, status, total_amount, source, notes,
                                       request_hash, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (order_code, student_id, OrderStatus.PENDING.value, total, source, notes.strip()[:200],
                 request_hash, ts, ts),
            ).lastrowid
            conn.executemany(
                """INSERT INTO order_items (order_id, menu_item_id, item_name, quantity, unit_price,
                                            line_total, prep_time_minutes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [(order_id, l["menu_item_id"], l["name"], l["quantity"], l["unit_price"],
                  l["line_total"], l["prep_time_minutes"]) for l in lines],
            )
            conn.execute(
                "INSERT INTO order_status_history (order_id, from_status, to_status, changed_by, created_at) "
                "VALUES (?, NULL, ?, ?, ?)",
                (order_id, OrderStatus.PENDING.value, self.name, ts),
            )
        return AgentResult.ok(self.name, order_id=order_id, order_code=order_code, created_at=ts)

    def on_release_stock(self, order_id: int) -> AgentResult:
        """Give reserved stock back when an order is cancelled."""
        with self.db.transaction() as conn:
            items = conn.execute("SELECT menu_item_id, quantity FROM order_items WHERE order_id = ?",
                                 (order_id,)).fetchall()
            for it in items:
                conn.execute(
                    "UPDATE menu_items SET stock = stock + ?, updated_at = ? WHERE id = ? AND stock IS NOT NULL",
                    (it["quantity"], now_str(), it["menu_item_id"]),
                )
        return AgentResult.ok(self.name, released=len(items))
