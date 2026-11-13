"""Token Agent and queue estimation."""
import sqlite3
import threading
from datetime import datetime, timedelta

import pytest

from models.models import AgentMessage
from services.queue_service import QueueEntry, RuleBasedEstimator, order_prep_minutes
from utils.helpers import TS_FORMAT


def make_pending_order(coordinator, student_id, item_id, qty=1):
    """Create an order through the Order Agent only (no token yet)."""
    oa = coordinator.order_agent
    lines = oa.on_validate_order([{"menu_item_id": item_id, "quantity": qty}]).data["lines"]
    created = oa.on_create_order(student_id, lines, 10.0, f"hash-{qty}-{item_id}")
    return created.data["order_id"], lines


def test_tokens_are_sequential(coordinator, student_id, other_student_id, item_ids):
    a = coordinator.place_order(student_id, [{"menu_item_id": item_ids["Tea"], "quantity": 1}])
    b = coordinator.place_order(other_student_id, [{"menu_item_id": item_ids["Tea"], "quantity": 1}])
    assert a.data["token_number"] == "T001"
    assert b.data["token_number"] == "T002"
    assert a.data["token_code"] != b.data["token_code"]


def test_issue_token_is_idempotent(coordinator, db, student_id, item_ids):
    order_id, lines = make_pending_order(coordinator, student_id, item_ids["Tea"])
    msg = AgentMessage("test", "TokenAgent", "issue_token", {"order_id": order_id, "lines": lines})
    first = coordinator.token_agent.handle(msg)
    second = coordinator.token_agent.handle(msg)
    assert first.success and second.success
    assert first.data["token_number"] == second.data["token_number"]
    assert second.data["reused"] is True
    assert db.query_one("SELECT COUNT(*) AS n FROM tokens WHERE order_id = ?", (order_id,))["n"] == 1


def test_database_rejects_duplicate_tokens(coordinator, db, student_id, item_ids):
    order_id, lines = make_pending_order(coordinator, student_id, item_ids["Tea"])
    token = coordinator.token_agent.on_issue_token(order_id, lines).data
    other_id, _ = make_pending_order(coordinator, student_id, item_ids["Coffee"])
    with pytest.raises(sqlite3.IntegrityError):   # same day + same sequence number
        db.execute("INSERT INTO tokens (order_id, token_date, sequence_no, token_number, token_code, issued_at) "
                   "VALUES (?, date('now','localtime'), ?, 'T001', 'dup', '2026-01-01 00:00:00')",
                   (other_id, token["sequence_no"]))


def test_token_for_missing_order(coordinator):
    result = coordinator.token_agent.handle(
        AgentMessage("test", "TokenAgent", "issue_token", {"order_id": 424242, "lines": []}))
    assert not result.success


def test_concurrent_token_generation_is_unique(coordinator, db, student_id, item_ids):
    orders = [make_pending_order(coordinator, student_id, item_ids["Tea"], qty) for qty in range(1, 11)]
    results, errors = [], []

    def worker(order_id, lines):
        try:
            results.append(coordinator.token_agent.on_issue_token(order_id, lines).data["token_number"])
        except Exception as exc:   # pragma: no cover - would indicate a bug
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=o) for o in orders]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(results) == 10 and len(set(results)) == 10


# ---------- queue / waiting-time estimation ----------
def test_order_prep_minutes():
    # slowest item 8 min + 0.5 min for each of the 2 extra units
    assert order_prep_minutes([{"prep_time_minutes": 8, "quantity": 2},
                               {"prep_time_minutes": 2, "quantity": 1}]) == 9.0
    assert order_prep_minutes([]) == 0


def test_rule_based_estimator():
    at = datetime(2026, 10, 29, 11, 0, 0)
    est = RuleBasedEstimator(kitchen_stations=2)
    ahead = [
        QueueEntry(1, "CONFIRMED", 8),
        QueueEntry(2, "PREPARING", 10, (at - timedelta(minutes=4)).strftime(TS_FORMAT)),  # 6 min left
    ]
    result = est.estimate(ahead, own_prep=6, at=at)
    # (8 + 6) / 2 stations = 7 min queue delay + 6 min own = 13
    assert result.wait_minutes == 13
    assert result.queue_position == 3
    assert result.orders_ahead == 2
    assert result.ready_at == "2026-10-29 11:13:00"
    assert result.label == "Estimated ready time: 13 minutes"


def test_empty_queue_wait_is_own_prep_time():
    result = RuleBasedEstimator(2).estimate([], own_prep=5, at=datetime(2026, 1, 1, 10, 0))
    assert result.wait_minutes == 5 and result.queue_position == 1


def test_wait_grows_with_queue(coordinator, db, item_ids):
    waits = []
    for usn in ("1BM22AI001", "1BM22AI042", "1BM22CS117"):
        sid = db.query_one("SELECT id FROM students WHERE usn = ?", (usn,))["id"]
        r = coordinator.place_order(sid, [{"menu_item_id": item_ids["Masala Dosa"], "quantity": 1}])
        waits.append((r.data["queue_position"], r.data["wait_minutes"]))
    assert [p for p, _ in waits] == [1, 2, 3]
    assert waits[0][1] < waits[1][1] < waits[2][1]
