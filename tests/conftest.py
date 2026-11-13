import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.coordinator_agent import CoordinatorAgent  # noqa: E402
from database.database import Database  # noqa: E402
from database.seed import initialize  # noqa: E402
from services.llm_service import LLMService  # noqa: E402
from utils.config import get_settings  # noqa: E402


@pytest.fixture
def settings(tmp_path):
    # isolated DB, no LLM, no email - tests never touch the real data/canteen.db
    return replace(get_settings(), db_path=tmp_path / "test.db", llm_provider="none", llm_api_key="",
                   email_enabled=False, kitchen_stations=2, duplicate_window_seconds=60,
                   max_active_orders_per_student=3)


@pytest.fixture
def db(settings):
    database = Database(settings.db_path)
    initialize(database)
    return database


@pytest.fixture
def coordinator(db, settings):
    return CoordinatorAgent(db, settings, llm=LLMService(None))


@pytest.fixture
def student_id(db):
    return db.query_one("SELECT id FROM students WHERE usn = '1BM22AI001'")["id"]


@pytest.fixture
def other_student_id(db):
    return db.query_one("SELECT id FROM students WHERE usn = '1BM22AI042'")["id"]


@pytest.fixture
def item_ids(db):
    return {r["name"]: r["id"] for r in db.query("SELECT id, name FROM menu_items")}
