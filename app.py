"""Agentic AI-Based Smart Canteen Token System - Streamlit entry point.

Run with:  streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="Smart Canteen", page_icon="🍽️", layout="wide")

from agents.coordinator_agent import CoordinatorAgent  # noqa: E402
from database.database import Database  # noqa: E402
from database.seed import initialize  # noqa: E402
from models.models import OrderError  # noqa: E402
from ui import analytics, canteen_dashboard, notifications, orders, student  # noqa: E402
from ui.components import esc, hero, inject_css  # noqa: E402
from utils.config import get_settings  # noqa: E402

STUDENT_PAGES = {"🍽️ Order Food": student.render, "📦 My Orders": orders.render,
                 "🔔 Notifications": notifications.render}
STAFF_PAGES = {"👨‍🍳 Canteen Dashboard": canteen_dashboard.render, "📊 Analytics": analytics.render,
               "🤖 Agent Activity": analytics.render_agents}


@st.cache_resource
def get_coordinator() -> CoordinatorAgent:
    """One coordinator (and its agents) shared by all browser sessions."""
    settings = get_settings()
    db = Database(settings.db_path)
    db.init_schema()
    if not db.is_seeded():
        initialize(db)
    return CoordinatorAgent(db, settings)


LOGIN_STEPS = [
    ("Login with your USN", "First time? Add your name and you're registered."),
    ("Pick your food", "Browse the menu, or just type “2 masala dosa and a coffee”."),
    ("Get a digital token", "With an estimated ready time based on the live kitchen queue."),
    ("Track it live", "Follow Confirmed → Preparing → Ready while you're still in class."),
    ("Walk in & collect", "You're notified when it's READY. Show the token, collect your food."),
]


def login_panel(coordinator: CoordinatorAgent) -> None:
    hero("Skip the canteen queue.",
         "Order ahead from class, get a digital token, and walk in only when your food is ready.",
         eyebrow="BMSCE Smart Canteen")
    left, right = st.columns([1.05, 1], gap="large")
    with left:
        with st.form("login"):
            st.markdown("### Welcome 👋")
            st.caption("Sign in with your university seat number to start ordering.")
            usn = st.text_input("USN", placeholder="1BM22AI001")
            name = st.text_input("Name (only needed the first time)", placeholder="Your full name")
            email = st.text_input("Email (optional - for 'food ready' emails)", placeholder="you@bmsce.ac.in")
            if st.form_submit_button("Continue", type="primary", width="stretch"):
                try:
                    st.session_state["student"] = coordinator.identify_student(usn, name, email)
                    st.rerun()
                except OrderError as exc:
                    st.error(str(exc))
        st.markdown("<div class='lg-demo'>Demo students: <code>1BM22AI001</code> <code>1BM22AI042</code> "
                    "<code>1BM22CS117</code></div>", unsafe_allow_html=True)
    with right:
        steps = "".join(
            f"<div class='lg-step'><div class='n'>{i}</div><div><div class='h'>{esc(h)}</div>"
            f"<div class='s'>{esc(s)}</div></div></div>"
            for i, (h, s) in enumerate(LOGIN_STEPS, 1)
        )
        st.markdown(f"<h3 style='margin-top:0'>How it works</h3><div class='lg-steps'>{steps}</div>",
                    unsafe_allow_html=True)


def sidebar(coordinator: CoordinatorAgent) -> str:
    with st.sidebar:
        st.markdown("<div class='sb-brand'><div class='sb-logo'>🍽️</div><div><div class='sb-name'>Smart Canteen</div>"
                    "<div class='sb-sub'>AGENTIC AI TOKEN SYSTEM · BMSCE</div></div></div>", unsafe_allow_html=True)
        current = st.session_state.get("student")
        if current:
            initials = "".join(part[0] for part in current["name"].split()[:2]).upper()
            st.markdown(f"<div class='sb-user'><div class='sb-avatar'>{esc(initials)}</div><div>"
                        f"<div class='sb-uname'>{esc(current['name'])}</div><div class='sb-usn'>{esc(current['usn'])}</div>"
                        f"</div></div>", unsafe_allow_html=True)
            notifications.notification_watcher(coordinator, current)
        st.markdown("<div class='sb-label'>Student</div>", unsafe_allow_html=True)
        page = st.radio("Navigation", list(STUDENT_PAGES) + list(STAFF_PAGES),
                        label_visibility="collapsed", key="nav")
        st.markdown("<div class='sb-label' style='margin-top:1.2rem'>System status</div>", unsafe_allow_html=True)
        email = "Enabled" if coordinator.settings.email_enabled else "In-app only"
        st.markdown(
            f"<div class='sb-status'><div><span>🧠 LLM</span><span>{esc(coordinator.llm.description)}</span></div>"
            f"<div><span>📧 Email</span><span>{email}</span></div>"
            f"<div><span>🔥 Kitchen queue</span><span>{coordinator.queue.active_queue_count()} order(s)</span></div></div>",
            unsafe_allow_html=True,
        )
        if current:
            st.write("")
            if st.button("Log out", width="stretch"):
                for key in ("student", "cart", "last_order", "nl_parsed", "last_seen_notification_id"):
                    st.session_state.pop(key, None)
                st.rerun()
    return page


def main() -> None:
    inject_css()
    coordinator = get_coordinator()
    page = sidebar(coordinator)

    if page in STAFF_PAGES:
        STAFF_PAGES[page](coordinator)
        return
    current = st.session_state.get("student")
    if not current:
        login_panel(coordinator)
        return
    STUDENT_PAGES[page](coordinator, current)


main()
