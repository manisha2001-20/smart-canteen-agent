"""Base class shared by all agents.

Agents communicate through `AgentMessage` objects. An agent receives a
message in `handle()`, which dispatches the message's `intent` to the method
named `on_<intent>` and always returns an `AgentResult` (never raises for
business errors). This keeps every agent independent and replaceable.
"""
from database.database import Database
from models.models import AgentMessage, AgentResult, OrderError


class BaseAgent:
    name = "BaseAgent"

    def __init__(self, db: Database):
        self.db = db

    def handle(self, message: AgentMessage) -> AgentResult:
        handler = getattr(self, f"on_{message.intent}", None)
        if handler is None:
            return AgentResult.fail(self.name, f"{self.name} cannot handle intent '{message.intent}'")
        try:
            return handler(**message.payload)
        except OrderError as exc:
            return AgentResult.fail(self.name, str(exc))

    @property
    def capabilities(self) -> list[str]:
        return [attr[3:] for attr in dir(self) if attr.startswith("on_")]
