"""Initialise the database and load sample data.

Usage:
    python -m database.seed                 # create tables + menu + students
    python -m database.seed --reset         # wipe the DB first
    python -m database.seed --demo-orders   # also run a few demo orders through the agents
"""
import argparse

from database.database import Database
from utils.config import get_settings
from utils.helpers import now_str

# name, category, price (INR), prep minutes, available, stock (None = unlimited), description
MENU_ITEMS = [
    ("Masala Dosa",      "South Indian", 50, 8,  True,  40,   "Crispy dosa with potato masala, chutney & sambar"),
    ("Plain Dosa",       "South Indian", 40, 6,  True,  40,   "Classic crispy dosa with chutney & sambar"),
    ("Idli Vada",        "South Indian", 40, 4,  True,  50,   "2 idlis + 1 medu vada with sambar"),
    ("Set Dosa",         "South Indian", 45, 7,  True,  30,   "3 soft spongy dosas with sagu"),
    ("Veg Pulao",        "Meals",        60, 5,  True,  30,   "Spiced vegetable rice with raita"),
    ("Mini Meals",       "Meals",        80, 5,  True,  25,   "Rice, sambar, rasam, palya, curd"),
    ("Paneer Roll",      "Snacks",       70, 7,  True,  20,   "Grilled paneer tikka wrapped in a paratha"),
    ("Veg Sandwich",     "Snacks",       45, 5,  True,  30,   "Grilled veg sandwich with mint chutney"),
    ("Samosa",           "Snacks",       15, 2,  True,  80,   "Crispy potato samosa (per piece)"),
    ("Gobi Manchurian",  "Snacks",       60, 8,  False, 0,    "Indo-Chinese crispy cauliflower (evenings only)"),
    ("Coffee",           "Beverages",    15, 2,  True,  None, "Filter coffee"),
    ("Tea",              "Beverages",    12, 2,  True,  None, "Masala chai"),
    ("Fresh Lime Juice", "Beverages",    25, 3,  True,  None, "Sweet / salt lime soda"),
    ("Badam Milk",       "Beverages",    30, 2,  True,  20,   "Chilled almond milk"),
]

STUDENTS = [
    ("1BM22AI001", "Ananya Rao", "ananya.ai22@bmsce.ac.in"),
    ("1BM22AI042", "Rahul Kumar", "rahul.ai22@bmsce.ac.in"),
    ("1BM22CS117", "Priya Shetty", "priya.cs22@bmsce.ac.in"),
]


def seed_menu(db: Database) -> int:
    ts = now_str()
    with db.transaction() as conn:
        for name, cat, price, prep, avail, stock, desc in MENU_ITEMS:
            conn.execute(
                """INSERT INTO menu_items
                   (name, category, price, prep_time_minutes, is_available, stock, description, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(name) DO NOTHING""",
                (name, cat, price, prep, int(avail), stock, desc, ts, ts),
            )
    return len(MENU_ITEMS)


def seed_students(db: Database) -> int:
    ts = now_str()
    with db.transaction() as conn:
        for usn, name, email in STUDENTS:
            conn.execute(
                "INSERT INTO students (usn, name, email, created_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(usn) DO NOTHING",
                (usn, name, email, ts),
            )
    return len(STUDENTS)


def seed_demo_orders(db: Database) -> None:
    """Place a few real orders through the full agent workflow."""
    from agents.coordinator_agent import CoordinatorAgent

    coordinator = CoordinatorAgent(db)
    demo = [
        ("1BM22AI001", "I want two masala dosas and one coffee"),
        ("1BM22AI042", "1 veg pulao, 2 samosa and a tea"),
        ("1BM22CS117", "paneer roll and fresh lime juice"),
    ]
    for usn, text in demo:
        student = db.query_one("SELECT id FROM students WHERE usn = ?", (usn,))
        parsed = coordinator.parse_natural_language(text)
        result = coordinator.place_order(student["id"], parsed.items, source="NATURAL_LANGUAGE")
        status = f"token {result.data['token_number']}" if result.success else result.error
        print(f"  {usn}: '{text}' -> {status}")


def initialize(db: Database, reset: bool = False) -> None:
    if reset and db.db_path.exists():
        db.db_path.unlink()
    db.init_schema()
    seed_menu(db)
    seed_students(db)


def main():
    parser = argparse.ArgumentParser(description="Initialise and seed the canteen database")
    parser.add_argument("--reset", action="store_true", help="delete the existing database first")
    parser.add_argument("--demo-orders", action="store_true", help="place sample orders via the agents")
    args = parser.parse_args()

    db = Database(get_settings().db_path)
    initialize(db, reset=args.reset)
    print(f"Database ready at {db.db_path}")
    print(f"  menu items: {len(MENU_ITEMS)}, students: {len(STUDENTS)}")
    if args.demo_orders:
        print("Placing demo orders through the agent workflow:")
        seed_demo_orders(db)


if __name__ == "__main__":
    main()
