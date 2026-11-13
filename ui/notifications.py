"""Notifications page + background notification watcher (toasts)."""
import pandas as pd
import streamlit as st

from agents.coordinator_agent import CoordinatorAgent
from ui.components import STATUS_STYLE, empty_state, esc, hero, section
from utils.helpers import format_time


@st.fragment(run_every="5s")
def notification_watcher(coordinator: CoordinatorAgent, student: dict) -> None:
    """Runs in the sidebar on every page: shows unread count and pops a toast for new notifications."""
    service = coordinator.notifications
    rows = service.list_for_student(student["id"])
    seen = st.session_state.get("last_seen_notification_id")
    if seen is None:                      # first load: don't toast old messages
        st.session_state["last_seen_notification_id"] = rows[0]["id"] if rows else 0
    else:
        fresh = [r for r in rows if r["id"] > seen]
        for r in reversed(fresh):
            st.toast(f"**{r['title']}**\n\n{r['message']}", icon="🔔")
        if fresh:
            st.session_state["last_seen_notification_id"] = fresh[0]["id"]

    unread = service.unread_count(student["id"])
    if unread:
        st.markdown(f"<div class='sb-notif'>🔔 <span><b>{unread}</b> unread notification{'s' if unread > 1 else ''}</span></div>",
                    unsafe_allow_html=True)
    else:
        st.markdown("<div class='sb-notif none'>🔔 No new notifications</div>", unsafe_allow_html=True)


def render(coordinator: CoordinatorAgent, student: dict) -> None:
    hero("Notifications", "Order confirmations, preparation updates and pickup alerts.", eyebrow="🔔 Inbox")
    service = coordinator.notifications
    rows = service.list_for_student(student["id"])
    unread = service.unread_count(student["id"])

    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    with c1:
        section("All notifications", f"{len(rows)} notification(s) · {unread} unread")
    if c2.button("Mark all as read", width="stretch", disabled=not rows, icon=":material/done_all:"):
        service.mark_read(student["id"])
        st.rerun()

    if not rows:
        empty_state("🔕", "No notifications yet", "You'll be notified here when your food is ready.")
    for r in rows:
        color, bg, icon = STATUS_STYLE.get(r["event"] or "", ("#475569", "#f1f5f9", "🔔"))
        new = "" if r["is_read"] else "<span class='nt-new'>NEW</span>"
        with st.container(key=f"ncard_{r['id']}"):
            st.markdown(
                f"<div class='nt{' read' if r['is_read'] else ''}'><div class='nt-ic' style='background:{bg};color:{color}'>{icon}</div>"
                f"<div class='nt-body'><div class='nt-title'>{esc(r['title'])} {new}</div>"
                f"<div class='nt-msg'>{esc(r['message'])}</div></div>"
                f"<div class='nt-time'>{r['created_at'][:10]}<br>{format_time(r['created_at'])}</div></div>",
                unsafe_allow_html=True,
            )

    email_rows = service.list_for_student(student["id"], channel="EMAIL")
    st.write("")
    with st.expander(f"📧 Email delivery log ({len(email_rows)})"):
        if not email_rows:
            st.caption("Email notifications are disabled (set EMAIL_ENABLED=true and SMTP settings in .env to enable).")
        else:
            st.dataframe(pd.DataFrame([{"Time": r["created_at"], "Title": r["title"], "Status": r["delivery_status"],
                                        "Error": r["error"] or ""} for r in email_rows]),
                         hide_index=True, width="stretch")
