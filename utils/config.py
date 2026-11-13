"""Central configuration.

All settings are read from environment variables (optionally loaded from a
`.env` file in the project root). Nothing is required: every setting has a
safe default so the project runs in "local mode" out of the box.
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DEFAULT_LLM_MODELS = {
    "anthropic": "claude-haiku-5-5",
    "openai": "gpt-4o-mini",
}


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    db_path: Path
    # LLM
    llm_provider: str
    llm_api_key: str
    llm_model: str
    llm_base_url: str
    llm_timeout: int
    # Kitchen / ordering rules
    kitchen_stations: int
    duplicate_window_seconds: int
    max_active_orders_per_student: int
    max_qty_per_item: int
    max_items_per_order: int
    staff_pin: str
    # Email
    email_enabled: bool
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    email_from: str
    smtp_use_tls: bool

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider in DEFAULT_LLM_MODELS and bool(self.llm_api_key)


def get_settings() -> Settings:
    db_path = Path(os.getenv("DB_PATH", "data/canteen.db"))
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path

    provider = os.getenv("LLM_PROVIDER", "none").strip().lower()
    return Settings(
        db_path=db_path,
        llm_provider=provider,
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_model=os.getenv("LLM_MODEL", "").strip() or DEFAULT_LLM_MODELS.get(provider, ""),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        llm_timeout=_env_int("LLM_TIMEOUT_SECONDS", 15),
        kitchen_stations=max(1, _env_int("KITCHEN_STATIONS", 2)),
        duplicate_window_seconds=_env_int("DUPLICATE_WINDOW_SECONDS", 60),
        max_active_orders_per_student=_env_int("MAX_ACTIVE_ORDERS_PER_STUDENT", 3),
        max_qty_per_item=_env_int("MAX_QTY_PER_ITEM", 10),
        max_items_per_order=_env_int("MAX_ITEMS_PER_ORDER", 20),
        staff_pin=os.getenv("STAFF_PIN", "1234"),
        email_enabled=_env_bool("EMAIL_ENABLED", False),
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=_env_int("SMTP_PORT", 587),
        smtp_user=os.getenv("SMTP_USER", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        email_from=os.getenv("EMAIL_FROM", "") or os.getenv("SMTP_USER", ""),
        smtp_use_tls=_env_bool("SMTP_USE_TLS", True),
    )
