"""Small shared helpers: timestamps, formatting, hashing."""
import hashlib
import json
from datetime import datetime

TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


def now_str() -> str:
    return now().strftime(TS_FORMAT)


def today_str() -> str:
    return now().strftime("%Y-%m-%d")


def parse_ts(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.strptime(value, TS_FORMAT)


def minutes_between(start, end) -> float | None:
    start, end = parse_ts(start), parse_ts(end)
    if not start or not end:
        return None
    return round((end - start).total_seconds() / 60, 1)


def format_currency(amount: float) -> str:
    return f"₹{amount:,.2f}"


def format_time(value) -> str:
    ts = parse_ts(value)
    return ts.strftime("%I:%M %p") if ts else "-"


def request_hash(student_id: int, lines: list[dict]) -> str:
    """Fingerprint of an order (student + items + quantities).

    Used for duplicate-order protection: the same student submitting the
    exact same cart twice within a short window is treated as a double click.
    """
    canonical = sorted((int(l["menu_item_id"]), int(l["quantity"])) for l in lines)
    raw = json.dumps({"student": student_id, "items": canonical})
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
