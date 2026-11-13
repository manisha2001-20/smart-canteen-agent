"""End-to-end multi-agent workflow, status machine, notifications, NL parsing."""
import urllib.error

from agents.coordinator_agent import CoordinatorAgent
from services.llm_service import LLMProvider, LLMService
from services.notification_service import InAppChannel, NotificationChannel


def test_complete_workflow(coordinator, db, student_id, item_ids):
    # Student -> Coordinator -> Order -> Token -> Preparation -> Notification
    result = coordinator.place_order(student_id, [{"menu_item_id": item_ids["Masala Dosa"], "quantity": 2},
                                                  {"menu_item_id": item_ids["Coffee"], "quantity": 1}])
    assert result.success, result.error
    order_id = result.data["order_id"]
    assert result.data["token_number"] == "T001"
    assert result.data["status"] == "CONFIRMED"
    assert result.data["wait_minutes"] >= 1
    agents_called = [step["agent"] for step in result.data["trace"]]
    assert agents_called == ["OrderAgent", "OrderAgent", "OrderAgent", "TokenAgent",
                             "PreparationAgent", "NotificationAgent"]

    for status in ("PREPARING", "READY", "COLLECTED"):
        assert coordinator.update_order_status(order_id, status).success

    order = coordinator.get_order(order_id)
    assert order["status"] == "COLLECTED"
    for col in ("created_at", "confirmed_at", "preparing_at", "ready_at", "collected_at"):
        assert order[col], col
    assert [h["to_status"] for h in order["history"]] == ["PENDING", "CONFIRMED", "PREPARING", "READY", "COLLECTED"]

    events = [n["event"] for n in coordinator.notifications.list_for_student(student_id)]
    assert "READY" in events and "CONFIRMED" in events
    ready = [n for n in coordinator.notifications.list_for_student(student_id) if n["event"] == "READY"][0]
    assert "T001" in ready["title"] and ready["is_read"] == 0
    # every agent message is persisted
    assert len(coordinator.get_agent_logs(order_id=order_id)) >= 10


def test_invalid_status_transitions(coordinator, student_id, item_ids):
    order_id = coordinator.place_order(student_id, [{"menu_item_id": item_ids["Tea"], "quantity": 1}]).data["order_id"]
    assert not coordinator.update_order_status(order_id, "COLLECTED").success     # skip PREPARING/READY
    assert not coordinator.update_order_status(order_id, "FLYING").success        # unknown status
    assert coordinator.update_order_status(order_id, "PREPARING").success
    assert not coordinator.update_order_status(order_id, "CONFIRMED").success     # no going back
    assert not coordinator.update_order_status(999999, "READY").success           # missing order


def test_student_cancellation_rules(coordinator, student_id, other_student_id, item_ids):
    a = coordinator.place_order(student_id, [{"menu_item_id": item_ids["Tea"], "quantity": 1}]).data["order_id"]
    assert not coordinator.cancel_order_by_student(other_student_id, a).success   # not their order
    assert coordinator.cancel_order_by_student(student_id, a).success
    assert coordinator.get_order(a)["status"] == "CANCELLED"

    b = coordinator.place_order(student_id, [{"menu_item_id": item_ids["Coffee"], "quantity": 1}]).data["order_id"]
    coordinator.update_order_status(b, "PREPARING")
    assert not coordinator.cancel_order_by_student(student_id, b).success         # already cooking


def test_queue_refreshes_when_order_finishes(coordinator, db, student_id, other_student_id, item_ids):
    first = coordinator.place_order(student_id, [{"menu_item_id": item_ids["Masala Dosa"], "quantity": 1}]).data
    second = coordinator.place_order(other_student_id, [{"menu_item_id": item_ids["Masala Dosa"], "quantity": 1}]).data
    assert second["queue_position"] == 2
    coordinator.update_order_status(first["order_id"], "PREPARING")
    coordinator.update_order_status(first["order_id"], "READY")
    assert coordinator.get_order(second["order_id"])["queue_position"] == 1
    assert coordinator.queue.active_queue_count() == 1


def test_natural_language_to_order(coordinator, student_id):
    parsed = coordinator.parse_natural_language("I want two masala dosas and one coffee")
    assert parsed.parser == "local"
    assert {(i["name"], i["quantity"]) for i in parsed.items} == {("Masala Dosa", 2), ("Coffee", 1)}
    result = coordinator.place_order(student_id, parsed.items, source="NATURAL_LANGUAGE")
    assert result.success
    assert result.data["total"] == 115


def test_local_parser_variants(coordinator):
    cases = {
        "2x idli vada, 3 teas & a samosaa": {("Idli Vada", 2), ("Tea", 3), ("Samosa", 1)},
        "masala dosa x2 and lime soda": {("Masala Dosa", 2), ("Fresh Lime Juice", 1)},
        "one chai one kaapi": {("Tea", 1), ("Coffee", 1)},
    }
    for text, expected in cases.items():
        parsed = coordinator.parse_natural_language(text)
        assert {(i["name"], i["quantity"]) for i in parsed.items} == expected, text
    pizza = coordinator.parse_natural_language("one pizza and 2 cofee")
    assert pizza.unrecognized == ["pizza"]
    assert {(i["name"], i["quantity"]) for i in pizza.items} == {("Coffee", 2)}
    assert coordinator.parse_natural_language("").items == []


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, reply=None, fail=False):
        super().__init__("key", "fake-model")
        self.reply, self.fail = reply, fail

    def complete(self, system, prompt):
        if self.fail:
            raise urllib.error.URLError("network down")
        return self.reply


def test_llm_output_is_validated_against_menu(db, settings):
    reply = 'Sure! {"items": [{"name": "masala dosa", "quantity": 2}, {"name": "Pizza", "quantity": 1}], "unrecognized": []}'
    coordinator = CoordinatorAgent(db, settings, llm=LLMService(FakeProvider(reply)))
    parsed = coordinator.parse_natural_language("two dosas and a pizza")
    assert parsed.parser == "llm:fake"
    assert [(i["name"], i["quantity"]) for i in parsed.items] == [("Masala Dosa", 2)]
    assert "Pizza" in parsed.unrecognized   # hallucinated item never reaches the order


def test_llm_failure_falls_back_to_local(db, settings):
    coordinator = CoordinatorAgent(db, settings, llm=LLMService(FakeProvider(fail=True)))
    parsed = coordinator.parse_natural_language("2 tea")
    assert parsed.parser == "local"
    assert "LLM unavailable" in parsed.note
    assert parsed.items[0]["quantity"] == 2


class RecordingEmail(NotificationChannel):
    name = "EMAIL"

    def __init__(self):
        self.sent = []

    def send(self, student, title, message):
        self.sent.append(title)
        return "SENT", None


def test_email_channel_only_for_ready(db, settings, student_id, item_ids):
    email = RecordingEmail()
    coordinator = CoordinatorAgent(db, settings, llm=LLMService(None), notification_channels=[InAppChannel(), email])
    order_id = coordinator.place_order(student_id, [{"menu_item_id": item_ids["Tea"], "quantity": 1}]).data["order_id"]
    coordinator.update_order_status(order_id, "PREPARING")
    assert email.sent == []
    coordinator.update_order_status(order_id, "READY")
    assert len(email.sent) == 1 and "READY" in email.sent[0]


def test_student_identification(coordinator):
    s = coordinator.identify_student("1bm22ai099", "New Student", "new@bmsce.ac.in")
    assert s["usn"] == "1BM22AI099"
    assert coordinator.identify_student("1BM22AI099")["id"] == s["id"]    # login without name
    for bad in [("x", "Name", ""), ("1BM22AI100", "", ""), ("1BM22AI101", "Name", "not-an-email")]:
        try:
            coordinator.identify_student(*bad)
            assert False, bad
        except Exception as exc:
            assert "valid" in str(exc) or "name" in str(exc)
