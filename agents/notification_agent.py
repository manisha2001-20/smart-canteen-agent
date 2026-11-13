"""Notification Agent - decides *what* to tell the student and *when*.

Delivery itself (in-app, optional email) is done by NotificationService.
"""
from agents.base_agent import BaseAgent
from database.database import Database
from models.models import AgentResult, OrderError, OrderStatus
from services.notification_service import NotificationService
from utils.helpers import format_time

# Email is reserved for the event that really matters: food is ready.
EMAIL_EVENTS = {OrderStatus.READY.value}


class NotificationAgent(BaseAgent):
    name = "NotificationAgent"

    def __init__(self, db: Database, service: NotificationService):
        super().__init__(db)
        self.service = service

    def compose(self, order, status: str) -> tuple[str, str] | None:
        token = order["token_number"] or "-"
        if status == OrderStatus.CONFIRMED.value:
            return (f"Order confirmed - Token {token}",
                    f"Your token is {token}. Estimated ready time: {int(order['estimated_wait_minutes'] or 0)} "
                    f"minutes (around {format_time(order['estimated_ready_at'])}). You are #{order['queue_position']} in the queue.")
        if status == OrderStatus.PREPARING.value:
            return (f"Token {token} is being prepared",
                    f"The kitchen has started preparing your order {order['order_code']}.")
        if status == OrderStatus.READY.value:
            return (f"Token {token} is READY for pickup!",
                    f"Your food is ready. Show token {token} at the canteen counter to collect it.")
        if status == OrderStatus.COLLECTED.value:
            return (f"Token {token} collected", "Enjoy your meal! Thank you for using Smart Canteen.")
        if status == OrderStatus.CANCELLED.value:
            reason = order["cancel_reason"] or "No reason given"
            return (f"Token {token} cancelled", f"Your order {order['order_code']} was cancelled. Reason: {reason}.")
        return None

    def on_notify_status(self, order_id: int, status: str) -> AgentResult:
        order = self.db.query_one(
            """SELECT o.*, t.token_number FROM orders o LEFT JOIN tokens t ON t.order_id = o.id
               WHERE o.id = ?""",
            (order_id,),
        )
        if order is None:
            raise OrderError(f"Cannot notify: order #{order_id} not found.")
        composed = self.compose(order, status)
        if composed is None:
            return AgentResult.ok(self.name, deliveries=[], skipped=True)
        title, message = composed
        deliveries = self.service.send(order["student_id"], order_id, status, title, message,
                                       use_email=status in EMAIL_EVENTS)
        return AgentResult.ok(self.name, title=title, deliveries=deliveries)
