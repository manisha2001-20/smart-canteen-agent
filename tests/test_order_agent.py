"""Order Agent: validation, pricing, stock, duplicate protection."""
from models.models import AgentMessage


def validate(coordinator, lines):
    return coordinator.order_agent.handle(AgentMessage("test", "OrderAgent", "validate_order", {"lines": lines}))


def test_valid_order_total(coordinator, item_ids):
    result = validate(coordinator, [{"menu_item_id": item_ids["Masala Dosa"], "quantity": 2},
                                    {"menu_item_id": item_ids["Coffee"], "quantity": 1}])
    assert result.success
    assert result.data["total"] == 2 * 50 + 15


def test_repeated_lines_are_merged(coordinator, item_ids):
    result = validate(coordinator, [{"menu_item_id": item_ids["Tea"], "quantity": 1},
                                    {"menu_item_id": item_ids["Tea"], "quantity": 2}])
    assert result.success
    assert result.data["lines"][0]["quantity"] == 3


def test_invalid_menu_item(coordinator):
    result = validate(coordinator, [{"menu_item_id": 9999, "quantity": 1}])
    assert not result.success
    assert "does not exist" in result.error


def test_unavailable_item_rejected(coordinator, item_ids):
    result = validate(coordinator, [{"menu_item_id": item_ids["Gobi Manchurian"], "quantity": 1}])
    assert not result.success
    assert "not available" in result.error


def test_empty_cart_and_bad_quantity(coordinator, item_ids):
    assert not validate(coordinator, []).success
    assert not validate(coordinator, [{"menu_item_id": item_ids["Tea"], "quantity": 0}]).success
    assert not validate(coordinator, [{"menu_item_id": item_ids["Tea"], "quantity": -3}]).success
    assert not validate(coordinator, [{"menu_item_id": item_ids["Tea"], "quantity": "abc"}]).success
    assert not validate(coordinator, [{"menu_item_id": item_ids["Tea"], "quantity": 11}]).success  # > max per item


def test_stock_limit(coordinator, db, item_ids):
    db.execute("UPDATE menu_items SET stock = 2 WHERE id = ?", (item_ids["Paneer Roll"],))
    result = validate(coordinator, [{"menu_item_id": item_ids["Paneer Roll"], "quantity": 3}])
    assert not result.success
    assert "Only 2" in result.error


def test_order_creation_persists_and_reserves_stock(coordinator, db, student_id, item_ids):
    before = db.query_one("SELECT stock FROM menu_items WHERE id = ?", (item_ids["Samosa"],))["stock"]
    result = coordinator.place_order(student_id, [{"menu_item_id": item_ids["Samosa"], "quantity": 4}])
    assert result.success
    order = db.query_one("SELECT * FROM orders WHERE id = ?", (result.data["order_id"],))
    assert order["order_code"].startswith("ORD-")
    assert order["total_amount"] == 60
    items = db.query("SELECT * FROM order_items WHERE order_id = ?", (order["id"],))
    assert len(items) == 1 and items[0]["quantity"] == 4 and items[0]["unit_price"] == 15
    after = db.query_one("SELECT stock FROM menu_items WHERE id = ?", (item_ids["Samosa"],))["stock"]
    assert after == before - 4


def test_cancel_releases_stock(coordinator, db, student_id, item_ids):
    before = db.query_one("SELECT stock FROM menu_items WHERE id = ?", (item_ids["Samosa"],))["stock"]
    result = coordinator.place_order(student_id, [{"menu_item_id": item_ids["Samosa"], "quantity": 4}])
    coordinator.cancel_order_by_student(student_id, result.data["order_id"])
    after = db.query_one("SELECT stock FROM menu_items WHERE id = ?", (item_ids["Samosa"],))["stock"]
    assert after == before


def test_duplicate_order_blocked(coordinator, student_id, other_student_id, item_ids):
    cart = [{"menu_item_id": item_ids["Coffee"], "quantity": 1}]
    assert coordinator.place_order(student_id, cart).success
    second = coordinator.place_order(student_id, cart)
    assert not second.success
    assert "Duplicate" in second.error
    # a different student ordering the same thing is fine
    assert coordinator.place_order(other_student_id, cart).success
    # the same student with a different cart is fine
    assert coordinator.place_order(student_id, [{"menu_item_id": item_ids["Coffee"], "quantity": 2}]).success


def test_max_active_orders_per_student(coordinator, student_id, item_ids):
    for qty in (1, 2, 3):
        assert coordinator.place_order(student_id, [{"menu_item_id": item_ids["Tea"], "quantity": qty}]).success
    fourth = coordinator.place_order(student_id, [{"menu_item_id": item_ids["Tea"], "quantity": 4}])
    assert not fourth.success
    assert "active orders" in fourth.error
