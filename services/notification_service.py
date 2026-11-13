"""Notification delivery channels.

IN_APP  - always on. The notification row in SQLite *is* the in-app message,
          shown in the student's Notifications page and as a toast.
EMAIL   - optional. Enabled only when EMAIL_ENABLED=true and SMTP settings are
          present in .env. Failures are recorded, never raised, so email
          problems can't break ordering.

New channels (SMS, WhatsApp, push) only need to subclass NotificationChannel.
"""
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage

from database.database import Database
from utils.config import Settings
from utils.helpers import now_str

SENT, FAILED, SKIPPED = "SENT", "FAILED", "SKIPPED"


class NotificationChannel(ABC):
    name = "BASE"

    @property
    def enabled(self) -> bool:
        return True

    @abstractmethod
    def send(self, student, title: str, message: str) -> tuple[str, str | None]:
        """Deliver the message; return (delivery_status, error)."""


class InAppChannel(NotificationChannel):
    name = "IN_APP"

    def send(self, student, title, message):
        return SENT, None   # stored in the DB, picked up by the UI


class EmailChannel(NotificationChannel):
    name = "EMAIL"

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled(self) -> bool:
        s = self.settings
        return s.email_enabled and bool(s.smtp_host and s.email_from)

    def send(self, student, title, message):
        if not student["email"]:
            return SKIPPED, "Student has no email address"
        s = self.settings
        msg = EmailMessage()
        msg["Subject"] = f"[Smart Canteen] {title}"
        msg["From"] = s.email_from
        msg["To"] = student["email"]
        msg.set_content(f"Hi {student['name']},\n\n{message}\n\n- BMSCE Smart Canteen")
        try:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as server:
                if s.smtp_use_tls:
                    server.starttls()
                if s.smtp_user:
                    server.login(s.smtp_user, s.smtp_password)
                server.send_message(msg)
            return SENT, None
        except (smtplib.SMTPException, OSError) as exc:
            return FAILED, f"{type(exc).__name__}: {exc}"


class NotificationService:
    def __init__(self, db: Database, settings: Settings, channels: list[NotificationChannel] | None = None):
        self.db = db
        self.channels = channels if channels is not None else [InAppChannel(), EmailChannel(settings)]

    def send(self, student_id: int, order_id: int | None, event: str, title: str,
             message: str, use_email: bool = True) -> list[dict]:
        student = self.db.query_one("SELECT * FROM students WHERE id = ?", (student_id,))
        if not student:
            return []
        deliveries = []
        for channel in self.channels:
            if not channel.enabled or (channel.name == "EMAIL" and not use_email):
                continue
            status, error = channel.send(student, title, message)
            self.db.execute(
                """INSERT INTO notifications
                   (student_id, order_id, channel, title, message, event, delivery_status, error, is_read, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (student_id, order_id, channel.name, title, message, event, status, error,
                 0 if channel.name == "IN_APP" else 1, now_str()),
            )
            deliveries.append({"channel": channel.name, "status": status, "error": error})
        return deliveries

    def list_for_student(self, student_id: int, channel: str = "IN_APP"):
        return self.db.query(
            """SELECT n.*, t.token_number FROM notifications n
               LEFT JOIN tokens t ON t.order_id = n.order_id
               WHERE n.student_id = ? AND n.channel = ? ORDER BY n.id DESC""",
            (student_id, channel),
        )

    def unread_count(self, student_id: int) -> int:
        row = self.db.query_one(
            "SELECT COUNT(*) AS n FROM notifications WHERE student_id = ? AND channel = 'IN_APP' AND is_read = 0",
            (student_id,),
        )
        return row["n"]

    def mark_read(self, student_id: int, notification_id: int | None = None) -> None:
        if notification_id is None:
            self.db.execute("UPDATE notifications SET is_read = 1 WHERE student_id = ?", (student_id,))
        else:
            self.db.execute(
                "UPDATE notifications SET is_read = 1 WHERE student_id = ? AND id = ?",
                (student_id, notification_id),
            )
