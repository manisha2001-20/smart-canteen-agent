"""Coordinator Agent - the orchestrator.

The UI only ever talks to the Coordinator. For each request the Coordinator
decides which specialised agents to call, in what order, passes the output
of one agent as input to the next, records every message in `agent_logs`,
and rolls back (cancels) the order if a later step fails.

    Student -> Coordinator -> OrderAgent (validate, duplicate check, create)
                           -> TokenAgent (unique token + wait estimate)
                           -> PreparationAgent (CONFIRMED, queue, ETA)
                           -> NotificationAgent (in-app / email)
"""
import json
import re

from agents.base_agent import BaseAgent
from agents.notification_agent import NotificationAgent
from agents.order_agent import OrderAgent
from agents.preparation_agent import PreparationAgent
from agents.token_agent import TokenAgent
from database.database import Database
from models.models import OPEN_STATUSES, AgentMessage, AgentResult, OrderError, OrderStatus, ParsedRequest
from services.llm_service import LLMService
from services.nl_parser import NaturalLanguageOrderParser
from services.notification_service import NotificationChannel, NotificationService
from services.queue_service import QueueService, WaitTimeEstimator
from utils.config import Settings, get_settings
from utils.helpers import now_str

USN_PATTERN = re.compile(r"^[A-Za-z0-9]{5,15}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
STUDENT_CANCELLABLE = {OrderStatus.PENDING.value, OrderStatus.CONFIRMED.value}


class CoordinatorAgent(BaseAgent):
    name = "CoordinatorAgent"

    def __init__(self, db: Database, settings: Settings | None = None, llm: LLMService | None = None,
                 notification_channels: list[NotificationChannel] | None = None,
                 estimator: WaitTimeEstimator | None = None):
        super().__init__(db)
        self.settings = settings or get_settings()
        self.queue = QueueService(db, estimator, self.settings.kitchen_stations)
        self.notifications = NotificationService(db, self.settings, notification_channels)
        self.llm = llm or LLMService.from_settings(self.settings)

        self.order_agent = OrderAgent(db, self.settings)
        self.token_agent = TokenAgent(db, self.queue)
        self.preparation_agent = PreparationAgent(db, self.queue)
        self.notification_agent = NotificationAgent(db, self.notifications)

    # ================= agent messaging =================
    def send(self, receiver: BaseAgent, intent: str, payload: dict, trace: list) -> AgentResult:
        """Send one message to an agent, log it, and append it to the request trace."""
        message = AgentMessage(self.name, receiver.name, intent, payload)
        try:
            result = receiver.handle(message)
        except Exception as exc:   # unexpected bug inside an agent - contain it
            result = AgentResult.fail(receiver.name, f"Internal error in {receiver.name}: {exc}")

        order_id = payload.get("order_id") or result.data.get("order_id")
        summary = result.error or self._summarize(result.data)
        self.db.execute(
            "INSERT INTO agent_logs (order_id, sender, receiver, intent, success, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (order_id, self.name, receiver.name, intent, int(result.success), summary, message.created_at),
        )
        trace.append({"agent": receiver.name, "intent": intent, "success": result.success,
                      "detail": summary, "at": message.created_at})
        return result

    @staticmethod
    def _summarize(data: dict) -> str:
        brief = {k: v for k, v in data.items() if k not in ("lines", "estimate", "deliveries")}
        if "estimate" in data:
            brief["wait_minutes"] = data["estimate"].wait_minutes
        if "deliveries" in data:
            brief["channels"] = [f"{d['channel']}:{d['status']}" for d in data["deliveries"]]
        return json.dumps(brief, default=str)[:300]

    def _log_event(self, intent: str, detail: str, order_id: int | None = None, success: bool = True) -> None:
        self.db.execute(
            "INSERT INTO agent_logs (order_id, sender, receiver, intent, success, detail, created_at) "
            "VALUES (?, 'Student', ?, ?, ?, ?, ?)",
            (order_id, self.name, intent, int(success), detail[:300], now_str()),
        )

    # ================= student identification =================
    def identify_student(self, usn: str, name: str = "", email: str = "") -> dict:
        usn = (usn or "").strip().upper()
        name = (name or "").strip()
        email = (email or "").strip().lower()
        if not USN_PATTERN.match(usn):
            raise OrderError("Please enter a valid USN (5-15 letters/digits, e.g. 1BM22AI001).")
        existing = self.db.query_one("SELECT * FROM students WHERE usn = ?", (usn,))
        if existing:
            return dict(existing)
        if len(name) < 2:
            raise OrderError("New student - please enter your name to register.")
        if email and not EMAIL_PATTERN.match(email):
            raise OrderError("Please enter a valid email address (or leave it blank).")
        student_id = self.db.execute(
            "INSERT INTO students (usn, name, email, created_at) VALUES (?, ?, ?, ?)",
            (usn, name[:60], email or None, now_str()),
        )
        return dict(self.db.query_one("SELECT * FROM students WHERE id = ?", (student_id,)))

    # ================= natural language =================
    def parse_natural_language(self, text: str) -> ParsedRequest:
        parser = NaturalLanguageOrderParser(self.llm, self.order_agent.get_menu())
        parsed = parser.parse(text)
        self._log_event("parse_natural_language",
                        f"parser={parsed.parser} items={[(i['name'], i['quantity']) for i in parsed.items]} "
                        f"unrecognized={parsed.unrecognized}")
        return parsed

    # ================= main workflow =================
    def place_order(self, student_id: int, lines: list[dict], source: str = "MENU", notes: str = "") -> AgentResult:
        trace: list[dict] = []
        if not self.db.query_one("SELECT id FROM students WHERE id = ?", (student_id,)):
            return AgentResult.fail(self.name, "Unknown student. Please log in again.", trace=trace)

        # 1. Order Agent: validate items, availability, total
        validated = self.send(self.order_agent, "validate_order", {"lines": lines}, trace)
        if not validated.success:
            return AgentResult.fail(self.name, validated.error, trace=trace)
        clean_lines, total = validated.data["lines"], validated.data["total"]

        # 2. Order Agent: duplicate-order protection
        dup = self.send(self.order_agent, "check_duplicate", {"student_id": student_id, "lines": clean_lines}, trace)
        if not dup.success:
            return AgentResult.fail(self.name, dup.error, trace=trace)

        # 3. Order Agent: create the order (status PENDING)
        created = self.send(self.order_agent, "create_order", {
            "student_id": student_id, "lines": clean_lines, "total": total,
            "request_hash": dup.data["request_hash"], "source": source, "notes": notes,
        }, trace)
        if not created.success:
            return AgentResult.fail(self.name, created.error, trace=trace)
        order_id = created.data["order_id"]

        # 4. Token Agent: unique token + waiting-time estimate
        token = self.send(self.token_agent, "issue_token", {"order_id": order_id, "lines": clean_lines}, trace)
        if not token.success:
            self._rollback(order_id, f"Token generation failed: {token.error}", trace)
            return AgentResult.fail(self.name, token.error, trace=trace)
        estimate = token.data["estimate"]

        # 5. Preparation Agent: move to CONFIRMED and join the kitchen queue
        confirmed = self.send(self.preparation_agent, "confirm_order",
                              {"order_id": order_id, "lines": clean_lines, "estimate": estimate}, trace)
        if not confirmed.success:
            self._rollback(order_id, f"Confirmation failed: {confirmed.error}", trace)
            return AgentResult.fail(self.name, confirmed.error, trace=trace)

        # 6. Notification Agent: tell the student (failure here never fails the order)
        self.send(self.notification_agent, "notify_status",
                  {"order_id": order_id, "status": OrderStatus.CONFIRMED.value}, trace)

        return AgentResult.ok(
            self.name,
            order_id=order_id,
            order_code=created.data["order_code"],
            token_number=token.data["token_number"],
            token_code=token.data["token_code"],
            total=total,
            lines=clean_lines,
            wait_minutes=estimate.wait_minutes,
            ready_at=estimate.ready_at,
            queue_position=estimate.queue_position,
            orders_ahead=estimate.orders_ahead,
            status=OrderStatus.CONFIRMED.value,
            trace=trace,
        )

    def _rollback(self, order_id: int, reason: str, trace: list) -> None:
        self.send(self.preparation_agent, "update_status",
                  {"order_id": order_id, "new_status": OrderStatus.CANCELLED.value,
                   "changed_by": self.name, "reason": reason}, trace)
        self.send(self.order_agent, "release_stock", {"order_id": order_id}, trace)

    def update_order_status(self, order_id: int, new_status: str, changed_by: str = "staff",
                            reason: str = "") -> AgentResult:
        trace: list[dict] = []
        updated = self.send(self.preparation_agent, "update_status",
                            {"order_id": order_id, "new_status": new_status,
                             "changed_by": changed_by, "reason": reason}, trace)
        if not updated.success:
            return AgentResult.fail(self.name, updated.error, trace=trace)

        if new_status == OrderStatus.CANCELLED.value:
            self.send(self.order_agent, "release_stock", {"order_id": order_id}, trace)
        # the queue changed -> every waiting student gets a fresh ETA
        self.send(self.preparation_agent, "refresh_estimates", {}, trace)
        self.send(self.notification_agent, "notify_status", {"order_id": order_id, "status": new_status}, trace)
        return AgentResult.ok(self.name, order_id=order_id, status=new_status, trace=trace)

    def cancel_order_by_student(self, student_id: int, order_id: int) -> AgentResult:
        order = self.db.query_one("SELECT student_id, status FROM orders WHERE id = ?", (order_id,))
        if not order or order["student_id"] != student_id:
            return AgentResult.fail(self.name, "Order not found.")
        if order["status"] not in STUDENT_CANCELLABLE:
            return AgentResult.fail(self.name, "This order is already being prepared and can no longer be cancelled.")
        return self.update_order_status(order_id, OrderStatus.CANCELLED.value, "student", "Cancelled by student")

    # ================= order state queries (used by the UI) =================
    ORDER_SELECT = """
        SELECT o.*, t.token_number, t.token_code, t.issued_at,
               s.usn, s.name AS student_name, s.email AS student_email
        FROM orders o
        JOIN students s ON s.id = o.student_id
        LEFT JOIN tokens t ON t.order_id = o.id
    """

    def get_orders(self, statuses: list[str] | None = None, day: str | None = None,
                   student_id: int | None = None, limit: int = 200) -> list[dict]:
        where, params = [], []
        if statuses:
            where.append(f"o.status IN ({','.join('?' * len(statuses))})")
            params += statuses
        if day:
            where.append("date(o.created_at) = ?")
            params.append(day)
        if student_id:
            where.append("o.student_id = ?")
            params.append(student_id)
        sql = self.ORDER_SELECT + (f" WHERE {' AND '.join(where)}" if where else "") + " ORDER BY o.id DESC LIMIT ?"
        orders = [dict(r) for r in self.db.query(sql, (*params, limit))]
        self._attach_items(orders)
        return orders

    def get_active_orders(self) -> list[dict]:
        return self.get_orders(list(OPEN_STATUSES))

    def get_order(self, order_id: int) -> dict | None:
        row = self.db.query_one(self.ORDER_SELECT + " WHERE o.id = ?", (order_id,))
        if not row:
            return None
        order = dict(row)
        self._attach_items([order])
        order["history"] = [dict(r) for r in self.db.query(
            "SELECT * FROM order_status_history WHERE order_id = ? ORDER BY id", (order_id,))]
        return order

    def _attach_items(self, orders: list[dict]) -> None:
        if not orders:
            return
        ids = [o["id"] for o in orders]
        rows = self.db.query(
            f"SELECT * FROM order_items WHERE order_id IN ({','.join('?' * len(ids))}) ORDER BY id", tuple(ids))
        by_order: dict[int, list] = {}
        for r in rows:
            by_order.setdefault(r["order_id"], []).append(dict(r))
        for o in orders:
            o["items"] = by_order.get(o["id"], [])
            o["items_text"] = ", ".join(f"{i['quantity']} x {i['item_name']}" for i in o["items"])

    def get_agent_logs(self, order_id: int | None = None, limit: int = 100) -> list[dict]:
        if order_id:
            rows = self.db.query("SELECT * FROM agent_logs WHERE order_id = ? ORDER BY id", (order_id,))
        else:
            rows = self.db.query("SELECT * FROM agent_logs ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]
