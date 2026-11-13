"""My Orders page: live status of active orders + order history."""
import pandas as pd
import streamlit as st

from agents.coordinator_agent import STUDENT_CANCELLABLE, CoordinatorAgent
from models.models import OPEN_STATUSES
from ui.components import empty_state, esc, eta_text, hero, section, status_badge, timeline
from utils.helpers import format_currency, format_time


def render(coordinator: CoordinatorAgent, student: dict) -> None:
    hero("My Orders", "Your tokens update live. This page refreshes automatically every few seconds.",
         eyebrow="📦 Live tracking")
    _live_orders(coordinator, student)
    st.divider()
    _history(coordinator, student)


@st.fragment(run_every="5s")
def _live_orders(coordinator: CoordinatorAgent, student: dict) -> None:
    active = coordinator.get_orders(list(OPEN_STATUSES), student_id=student["id"])
    section(f"Live orders · {len(active)}", "Confirmed → Preparing → Ready → Collected")
    if not active:
        empty_state("🍽️", "No active orders", "Head to Order Food to place one.")
        return

    for order in active:
        ready = order["status"] == "READY"
        with st.container(key=f"ocard_{order['id']}"):
            a, b, c = st.columns([1, 3.2, 1.2], gap="medium")
            a.markdown(f"<div class='oc-token{' ready' if ready else ''}'><div class='lbl'>TOKEN</div>"
                       f"<div class='num'>{esc(order['token_number'] or '-')}</div></div>", unsafe_allow_html=True)
            queue = (f" · queue position <b>#{order['queue_position']}</b>"
                     if order["status"] in ("CONFIRMED", "PREPARING") else "")
            b.markdown(
                f"{status_badge(order['status'])} <span class='sc-muted'>&nbsp;{esc(order['order_code'])} · "
                f"placed {format_time(order['created_at'])}</span>"
                f"<div class='oc-title'>{esc(order['items_text'])}</div>"
                f"<div class='sc-muted'>⏱️ Estimated ready: <b>{esc(eta_text(order))}</b>{queue}</div>"
                f"{timeline(order)}"
                + ("<div class='oc-ready'>✅ Your food is ready! Show this token at the counter to collect it.</div>" if ready else ""),
                unsafe_allow_html=True,
            )
            c.markdown(f"<div class='oc-kv'>Total</div><div class='oc-val'>{format_currency(order['total_amount'])}</div>",
                       unsafe_allow_html=True)
            if order["status"] in STUDENT_CANCELLABLE and c.button("Cancel order", key=f"cancel_{order['id']}",
                                                                   width="stretch"):
                result = coordinator.cancel_order_by_student(student["id"], order["id"])
                (st.toast("Order cancelled") if result.success else st.error(result.error))
                st.rerun()


def _history(coordinator: CoordinatorAgent, student: dict) -> None:
    orders = coordinator.get_orders(student_id=student["id"])
    section("Order history", f"{len(orders)} order(s) placed")
    if not orders:
        empty_state("📜", "No orders yet", "Your past orders will appear here.")
        return
    df = pd.DataFrame([{
        "Token": o["token_number"] or "-",
        "Order ID": o["order_code"],
        "Date": o["created_at"][:10],
        "Time": format_time(o["created_at"]),
        "Items": o["items_text"],
        "Total (₹)": o["total_amount"],
        "Status": o["status"],
        "Ordered via": "Smart Order" if o["source"] == "NATURAL_LANGUAGE" else "Menu",
        "Ready at": format_time(o["ready_at"]),
    } for o in orders])
    st.dataframe(df, hide_index=True, width="stretch",
                 column_config={"Total (₹)": st.column_config.NumberColumn(format="₹%.2f")})

    with st.expander("🔍 Order timeline & agent trace"):
        options = {f"{o['token_number'] or '-'} · {o['order_code']}": o["id"] for o in orders}
        choice = st.selectbox("Select an order", list(options))
        order = coordinator.get_order(options[choice])
        st.markdown(f"{status_badge(order['status'])}{timeline(order)}", unsafe_allow_html=True)
        st.markdown("**Status history**")
        st.dataframe(pd.DataFrame([{"From": h["from_status"] or "-", "To": h["to_status"], "By": h["changed_by"],
                                    "At": h["created_at"]} for h in order["history"]]),
                     hide_index=True, width="stretch")
        st.markdown("**Agent messages**")
        logs = coordinator.get_agent_logs(order_id=order["id"])
        st.dataframe(pd.DataFrame([{"Time": l["created_at"][11:], "From": l["sender"], "To": l["receiver"],
                                    "Intent": l["intent"], "OK": "✅" if l["success"] else "❌",
                                    "Detail": l["detail"]} for l in logs]),
                     hide_index=True, width="stretch")
