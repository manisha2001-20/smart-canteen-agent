"""Canteen staff dashboard: live order board, status updates, menu management."""
import pandas as pd
import streamlit as st

from agents.coordinator_agent import CoordinatorAgent
from models.models import OPEN_STATUSES, OrderStatus
from services.analytics_service import AnalyticsService
from ui.components import STATUS_STYLE, esc, eta_text, hero, section, stat_tiles
from utils.helpers import format_currency, format_time, minutes_between, now_str, today_str

# status -> (button label, next status)
NEXT_ACTION = {
    "CONFIRMED": ("👨‍🍳 Start preparing", OrderStatus.PREPARING.value),
    "PREPARING": ("✅ Mark READY", OrderStatus.READY.value),
    "READY": ("🍽️ Mark COLLECTED", OrderStatus.COLLECTED.value),
}
BOARD_COLUMNS = [("CONFIRMED", "New orders"), ("PREPARING", "In the kitchen"), ("READY", "Ready for pickup")]
ALL_STATUSES = [s.value for s in OrderStatus]


def render(coordinator: CoordinatorAgent) -> None:
    hero("Canteen Staff Dashboard", "Live kitchen queue · update order status · manage the menu",
         eyebrow="👨‍🍳 Staff console")

    if not st.session_state.get("staff_ok"):
        _, mid, _ = st.columns([1, 1.3, 1])
        with mid:
            with st.form("staff_login"):
                st.markdown("### 🔒 Staff access")
                st.caption("Enter the canteen staff PIN to open the live order board.")
                pin = st.text_input("Staff PIN", type="password", help="Set STAFF_PIN in .env (default 1234)")
                if st.form_submit_button("Unlock dashboard", type="primary", width="stretch"):
                    if pin == coordinator.settings.staff_pin:
                        st.session_state["staff_ok"] = True
                        st.rerun()
                    st.error("Incorrect PIN")
        return

    tab_board, tab_all, tab_menu = st.tabs(["🔥  Live Order Board", "📋  All Orders", "🍛  Menu & Stock"])
    with tab_board:
        _live_board(coordinator)
    with tab_all:
        _all_orders(coordinator)
    with tab_menu:
        _menu_management(coordinator)


def _today_metrics(coordinator: CoordinatorAgent) -> None:
    s = AnalyticsService(coordinator.db).today_summary()
    stat_tiles([
        ("🔥", "Active queue", coordinator.queue.active_queue_count(), "am"),
        ("✅", "Ready for pickup", int(s["ready"]), "em"),
        ("🧾", "Today's orders", int(s["total_orders"]), "sl"),
        ("🍽️", "Collected", int(s["collected"]), "sl"),
        ("⏱️", "Avg prep time", f"{s['avg_prep_minutes']:.1f} min" if s["avg_prep_minutes"] else "-", "em"),
        ("₹", "Revenue today", format_currency(s["revenue"]), "am"),
    ])


@st.fragment(run_every="5s")
def _live_board(coordinator: CoordinatorAgent) -> None:
    _today_metrics(coordinator)
    st.caption(f"🟢 Auto-refreshing every 5 s · last update {format_time(now_str())}")

    orders = coordinator.get_active_orders()
    columns = st.columns(3, gap="medium")
    for col, (status, title) in zip(columns, BOARD_COLUMNS):
        color, bg, icon = STATUS_STYLE[status]
        group = sorted([o for o in orders if o["status"] == status], key=lambda o: o["id"])
        with col:
            st.markdown(f"<div class='kb-head' style='background:{bg};color:{color}'><span>{icon} {title}</span>"
                        f"<span class='n'>{len(group)}</span></div>", unsafe_allow_html=True)
            if not group:
                st.markdown("<div class='kb-empty'>Nothing here right now</div>", unsafe_allow_html=True)
            for order in group:
                _order_card(coordinator, order)


def _order_card(coordinator: CoordinatorAgent, order: dict) -> None:
    with st.container(key=f"kcard_{order['status']}_{order['id']}"):
        waited = minutes_between(order["created_at"], now_str()) or 0
        items = "".join(f"<b>{i['quantity']}×</b> {esc(i['item_name'])}<br>" for i in order["items"])
        note = f"<div class='kc-note'>📝 {esc(order['notes'])}</div>" if order["notes"] else ""
        st.markdown(
            f"<div class='kc-top'><span class='kc-token'>{esc(order['token_number'] or '-')}</span>"
            f"<span class='kc-age'>🕒 {waited:.0f} min ago</span></div>"
            f"<div class='kc-student'>{esc(order['student_name'])} <span class='sc-muted'>· {esc(order['usn'])}</span></div>"
            f"<div class='kc-items'>{items}</div>{note}"
            f"<div class='kc-meta'><span>{format_currency(order['total_amount'])}</span><span>ETA {esc(eta_text(order))}</span></div>",
            unsafe_allow_html=True,
        )
        label, nxt = NEXT_ACTION[order["status"]]
        a, b = st.columns([2, 1])
        if a.button(label, key=f"next_{order['id']}", type="primary", width="stretch"):
            _apply(coordinator, order, nxt)
        if order["status"] != "READY" and b.button("Cancel", key=f"cx_{order['id']}", width="stretch"):
            _apply(coordinator, order, OrderStatus.CANCELLED.value, "Cancelled by canteen staff")


def _apply(coordinator: CoordinatorAgent, order: dict, status: str, reason: str = "") -> None:
    result = coordinator.update_order_status(order["id"], status, changed_by="staff", reason=reason)
    if result.success:
        st.toast(f"Token {order['token_number']} → {status}" + (" · student notified 🔔" if status == "READY" else ""))
    else:
        st.toast(f"⚠️ {result.error}")
    st.rerun()


def _all_orders(coordinator: CoordinatorAgent) -> None:
    with st.container(key="card_filters"):
        f1, f2, f3 = st.columns([2, 1, 1.2], vertical_alignment="bottom")
        statuses = f1.multiselect("Filter by status", ALL_STATUSES, default=list(OPEN_STATUSES))
        only_today = f2.toggle("Today only", value=True)
        token_search = f3.text_input("Search token / USN", placeholder="T005 or 1BM22...")

    orders = coordinator.get_orders(statuses or None, day=today_str() if only_today else None, limit=500)
    if token_search:
        q = token_search.strip().upper()
        orders = [o for o in orders if q in (o["token_number"] or "") or q in o["usn"] or q in o["order_code"]]

    st.write("")
    section("Orders", f"{len(orders)} order(s) match the filters")
    if not orders:
        return
    df = pd.DataFrame([{
        "Token": o["token_number"], "Order ID": o["order_code"], "Student": o["student_name"], "USN": o["usn"],
        "Items": o["items_text"], "Total (₹)": o["total_amount"], "Status": o["status"],
        "Placed": format_time(o["created_at"]), "Preparing": format_time(o["preparing_at"]),
        "Ready": format_time(o["ready_at"]), "Collected": format_time(o["collected_at"]),
        "Prep time (min)": minutes_between(o["preparing_at"], o["ready_at"]),
        "Source": o["source"],
    } for o in orders])
    st.dataframe(df, hide_index=True, width="stretch",
                 column_config={"Total (₹)": st.column_config.NumberColumn(format="₹%.2f")})

    open_orders = [o for o in orders if o["status"] in OPEN_STATUSES]
    st.write("")
    with st.container(key="card_update"):
        section("Update an order manually")
        if not open_orders:
            st.caption("No open orders in this view.")
            return
        u1, u2, u3 = st.columns([2, 1.3, 1], vertical_alignment="bottom")
        labels = {f"{o['token_number']} · {o['student_name']} · {o['status']}": o for o in open_orders}
        chosen = labels[u1.selectbox("Order", list(labels))]
        target = u2.selectbox("New status", ALL_STATUSES, index=ALL_STATUSES.index("READY"))
        if u3.button("Update status", type="primary", width="stretch"):
            result = coordinator.update_order_status(chosen["id"], target, changed_by="staff")
            (st.success(f"Token {chosen['token_number']} is now {target}") if result.success else st.error(result.error))


def _menu_management(coordinator: CoordinatorAgent) -> None:
    section("Menu & stock", "Toggle availability or update today's stock. Leave stock empty for unlimited (e.g. beverages).")
    menu = coordinator.order_agent.get_menu()
    df = pd.DataFrame([{"id": m.id, "Item": m.name, "Category": m.category, "Price (₹)": m.price,
                        "Prep (min)": m.prep_time_minutes, "Available": m.is_available, "Stock": m.stock}
                       for m in menu])
    edited = st.data_editor(
        df, hide_index=True, width="stretch", key="menu_editor",
        disabled=["id", "Item", "Category", "Price (₹)", "Prep (min)"],
        column_config={"id": None, "Stock": st.column_config.NumberColumn(min_value=0, step=1),
                       "Price (₹)": st.column_config.NumberColumn(format="₹%.2f")},
    )
    if st.button("💾 Save menu changes", type="primary"):
        changed = 0
        for before, after in zip(df.to_dict("records"), edited.to_dict("records")):
            stock = None if pd.isna(after["Stock"]) else int(after["Stock"])
            old_stock = None if pd.isna(before["Stock"]) else int(before["Stock"])
            if bool(after["Available"]) != bool(before["Available"]) or stock != old_stock:
                coordinator.order_agent.set_availability(int(after["id"]), bool(after["Available"]), stock)
                changed += 1
        st.success(f"Saved {changed} change(s).") if changed else st.info("No changes to save.")
