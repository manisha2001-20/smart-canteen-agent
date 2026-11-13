"""Domain models shared by agents, services and the UI."""
from dataclasses import dataclass, field
from enum import Enum

from utils.helpers import now_str


class OrderStatus(str, Enum):
    PENDING = "PENDING"        # created by OrderAgent, waiting for a token
    CONFIRMED = "CONFIRMED"    # token issued, in the kitchen queue
    PREPARING = "PREPARING"    # kitchen staff started cooking
    READY = "READY"            # food ready at the counter -> student notified
    COLLECTED = "COLLECTED"    # student picked up the food (final)
    CANCELLED = "CANCELLED"    # cancelled by student/staff/system (final)


# Orders that occupy the kitchen queue (used for waiting-time estimation)
QUEUE_STATUSES = (OrderStatus.CONFIRMED.value, OrderStatus.PREPARING.value)
# Orders that are not finished yet
OPEN_STATUSES = (
    OrderStatus.PENDING.value,
    OrderStatus.CONFIRMED.value,
    OrderStatus.PREPARING.value,
    OrderStatus.READY.value,
)

# The order state machine enforced by the PreparationAgent
ALLOWED_TRANSITIONS = {
    OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
    OrderStatus.PREPARING: {OrderStatus.READY, OrderStatus.CANCELLED},
    OrderStatus.READY: {OrderStatus.COLLECTED},
    OrderStatus.COLLECTED: set(),
    OrderStatus.CANCELLED: set(),
}

# Which timestamp column is stamped when an order enters a status
STATUS_TIMESTAMP_COLUMN = {
    OrderStatus.CONFIRMED: "confirmed_at",
    OrderStatus.PREPARING: "preparing_at",
    OrderStatus.READY: "ready_at",
    OrderStatus.COLLECTED: "collected_at",
    OrderStatus.CANCELLED: "cancelled_at",
}


class OrderError(Exception):
    """Raised by agents for business-rule violations (invalid item, duplicate, ...)."""


@dataclass
class MenuItem:
    id: int
    name: str
    category: str
    price: float
    prep_time_minutes: int
    is_available: bool
    stock: int | None
    description: str = ""

    @classmethod
    def from_row(cls, row) -> "MenuItem":
        return cls(
            id=row["id"],
            name=row["name"],
            category=row["category"],
            price=row["price"],
            prep_time_minutes=row["prep_time_minutes"],
            is_available=bool(row["is_available"]),
            stock=row["stock"],
            description=row["description"] or "",
        )

    @property
    def orderable(self) -> bool:
        return self.is_available and (self.stock is None or self.stock > 0)


@dataclass
class ValidatedLine:
    menu_item_id: int
    name: str
    quantity: int
    unit_price: float
    prep_time_minutes: int

    @property
    def line_total(self) -> float:
        return round(self.quantity * self.unit_price, 2)

    def to_dict(self) -> dict:
        return {
            "menu_item_id": self.menu_item_id,
            "name": self.name,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "prep_time_minutes": self.prep_time_minutes,
            "line_total": self.line_total,
        }


@dataclass
class AgentMessage:
    """A message sent from one agent to another.

    `intent` names the action requested, `payload` carries its arguments.
    Each agent dispatches the intent to its `on_<intent>` handler.
    """
    sender: str
    receiver: str
    intent: str
    payload: dict = field(default_factory=dict)
    created_at: str = field(default_factory=now_str)


@dataclass
class AgentResult:
    agent: str
    success: bool
    data: dict = field(default_factory=dict)
    error: str | None = None

    @classmethod
    def ok(cls, agent: str, **data) -> "AgentResult":
        return cls(agent=agent, success=True, data=data)

    @classmethod
    def fail(cls, agent: str, error: str, **data) -> "AgentResult":
        return cls(agent=agent, success=False, data=data, error=error)


@dataclass
class ParsedRequest:
    """Output of natural-language order parsing."""
    items: list[dict]                 # [{"menu_item_id", "name", "quantity"}]
    unrecognized: list[str]
    parser: str                       # "llm:<provider>" or "local"
    note: str = ""
