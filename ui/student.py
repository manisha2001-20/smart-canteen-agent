"""Student ordering page: menu browsing, cart, natural-language ordering, token."""
import streamlit as st

from agents.coordinator_agent import CoordinatorAgent
from ui.components import agent_trace, empty_state, esc, hero, item_emoji, section, stat_tiles, token_card
from utils.helpers import format_currency


def _cart() -> dict[int, int]:
    return st.session_state.setdefault("cart", {})


def _add_to_cart(item_id: int, qty: int) -> None:
    cart = _cart()
    cart[item_id] = cart.get(item_id, 0) + qty


def _availability(item) -> tuple[str, str, str]:
    """(label, text color, background)"""
    if not item.is_available:
        return "Unavailable", "#be123c", "#ffe4e6"
    if item.stock is not None and item.stock == 0:
        return "Sold out", "#be123c", "#ffe4e6"
    if item.stock is not None and item.stock <= 10:
        return f"Only {item.stock} left", "#b45309", "#fef3c7"
    return "Available", "#047857", "#d1fae5"


def render(coordinator: CoordinatorAgent, student: dict) -> None:
    hero(f"Hi {student['name'].split()[0]}, what would you like today?",
         "Order now, get a digital token, and walk in only when your food is ready.",
         eyebrow="🍽️ Order food")

    last = st.session_state.get("last_order")
    if last:
        st.success("Order placed successfully! Your token is below. Track it live in **My Orders**.", icon="🎉")
        token_card(last)
        with st.expander("🤖 How the agents processed this order"):
            agent_trace(last["trace"])
        if st.button("Start a new order", type="secondary"):
            st.session_state.pop("last_order", None)
            st.rerun()
        st.divider()

    menu = coordinator.order_agent.get_menu()
    menu_by_id = {m.id: m for m in menu}

    typical = coordinator.queue.estimate_for_new_order([{"prep_time_minutes": 5, "quantity": 1}]).wait_minutes
    stat_tiles([
        ("🔥", "Orders in kitchen queue", coordinator.queue.active_queue_count(), "am"),
        ("⏱️", "Typical wait right now", f"{typical} min", "em"),
        ("🥗", "Items available", sum(1 for m in menu if m.orderable), "em"),
    ])

    left, right = st.columns([2.25, 1], gap="large")
    with left:
        tab_menu, tab_nl = st.tabs(["📋  Browse Menu", "💬  Smart Order"])
        with tab_menu:
            _menu_section(menu)
        with tab_nl:
            _natural_language_section(coordinator, student, menu_by_id)
    with right:
        _cart_section(coordinator, student, menu_by_id)


def _menu_section(menu) -> None:
    categories = ["All"] + sorted({m.category for m in menu})
    f1, f2 = st.columns([2.2, 1], vertical_alignment="center")
    with f1:
        category = st.segmented_control("Category", categories, default="All", label_visibility="collapsed") or "All"
    search = f2.text_input("Search", placeholder="🔍  Search menu...", label_visibility="collapsed")

    items = [m for m in menu if (category == "All" or m.category == category)
             and (not search or search.lower() in m.name.lower())]
    if not items:
        empty_state("🔎", "No items match your search", "Try another name or category.")
        return

    cols = st.columns(3, gap="medium")
    for idx, item in enumerate(items):
        label, color, bg = _availability(item)
        icon, gradient = item_emoji(item.name, item.category)
        off = "" if item.orderable else " mc-off"
        with cols[idx % 3]:
            with st.container(key=f"mcard_{item.id}"):
                st.markdown(
                    f"<div class='mc-thumb{off}' style='background:{gradient}'>{icon}"
                    f"<span class='avail sc-badge' style='color:{color};background:{bg}'>{esc(label)}</span>"
                    f"<span class='prep'>⏱ {item.prep_time_minutes} min</span></div>"
                    f"<div class='mc-name'>{esc(item.name)}</div>"
                    f"<div class='mc-desc'>{esc(item.description)}</div>"
                    f"<div class='mc-foot'><span class='sc-price'>{format_currency(item.price)}</span>"
                    f"<span class='sc-chip'>{esc(item.category)}</span></div>",
                    unsafe_allow_html=True,
                )
                q, b = st.columns([1, 1.15], vertical_alignment="bottom")
                max_qty = 10 if item.stock is None else max(1, min(10, item.stock))
                qty = q.number_input("Qty", 1, max_qty, 1, key=f"qty_{item.id}", label_visibility="collapsed",
                                     disabled=not item.orderable)
                if b.button("Add", key=f"add_{item.id}", disabled=not item.orderable, width="stretch",
                            type="primary", icon=":material/add_shopping_cart:"):
                    _add_to_cart(item.id, int(qty))
                    st.toast(f"Added {qty} x {item.name}", icon="🛒")
                    st.rerun()


def _natural_language_section(coordinator: CoordinatorAgent, student: dict, menu_by_id) -> None:
    with st.container(key="card_nl"):
        section("Tell us what you want", f"Parser: {coordinator.llm.description}. Falls back to the local parser automatically.")
        text = st.text_area("Your order", placeholder="e.g. I want two masala dosas and one coffee",
                            max_chars=500, key="nl_text", label_visibility="collapsed")
        if st.button("🧠 Understand my order", type="primary"):
            st.session_state["nl_parsed"] = coordinator.parse_natural_language(text)

        parsed = st.session_state.get("nl_parsed")
        if not parsed:
            st.markdown("<span class='sc-muted'>Try: <span class='sc-chip am'>2 plain dosa, a samosa and lime juice</span>"
                        "<span class='sc-chip am'>idli vada x2 and 3 teas</span></span>", unsafe_allow_html=True)
            return

        if parsed.note:
            st.info(parsed.note)
        if parsed.unrecognized:
            st.warning("Not on our menu: " + ", ".join(f"“{u}”" for u in parsed.unrecognized))
        if not parsed.items:
            st.error("I couldn't find any menu items in that request. Try naming items from the menu.")
            return

        rows = []
        for it in parsed.items:
            m = menu_by_id[it["menu_item_id"]]
            icon, gradient = item_emoji(m.name, m.category)
            avail = ("<span class='sc-badge' style='color:#047857;background:#d1fae5'>Available</span>" if m.orderable
                     else "<span class='sc-badge' style='color:#be123c;background:#ffe4e6'>Not available</span>")
            rows.append(
                f"<div style='display:flex;align-items:center;gap:.75rem;padding:.55rem 0;border-bottom:1px solid var(--line)'>"
                f"<div style='width:40px;height:40px;border-radius:10px;display:grid;place-items:center;font-size:1.3rem;"
                f"background:{gradient}'>{icon}</div>"
                f"<div style='flex:1'><div class='mc-name'>{it['quantity']} × {esc(m.name)}</div>"
                f"<div class='sc-muted'>{format_currency(m.price)} each</div></div>"
                f"{avail}<div class='sc-price' style='min-width:84px;text-align:right'>{format_currency(m.price * it['quantity'])}</div></div>"
            )
        st.markdown(f"<div style='margin:.6rem 0 .2rem 0'><b>Here's what I understood</b> "
                    f"<span class='sc-chip'>parser: {esc(parsed.parser)}</span></div>{''.join(rows)}",
                    unsafe_allow_html=True)
        st.write("")
        a, b = st.columns(2)
        if a.button("➕ Add these to cart", width="stretch"):
            for it in parsed.items:
                _add_to_cart(it["menu_item_id"], it["quantity"])
            st.session_state.pop("nl_parsed", None)
            st.rerun()
        if b.button("⚡ Order these now", type="primary", width="stretch"):
            _submit(coordinator, student, parsed.items, source="NATURAL_LANGUAGE")


def _cart_section(coordinator: CoordinatorAgent, student: dict, menu_by_id) -> None:
    with st.container(key="cartbox"):
        cart = _cart()
        units = sum(cart.values())
        st.markdown(f"<div class='cart-head'><h3>🛒 Your Cart</h3><span class='cart-count'>{units} item{'s' if units != 1 else ''}"
                    f"</span></div>", unsafe_allow_html=True)
        if not cart:
            st.markdown("<div class='cart-empty'><div class='big'>🍱</div><b>Your cart is empty</b><br>"
                        "<span style='font-size:.84rem'>Add items from the menu or use Smart Order.</span></div>",
                        unsafe_allow_html=True)
            return

        total = 0.0
        for item_id, qty in list(cart.items()):
            item = menu_by_id.get(item_id)
            if not item:
                cart.pop(item_id)
                continue
            line = item.price * qty
            total += line
            n, minus, plus, rm = st.columns([3.1, .85, .85, .85], vertical_alignment="center", gap="small")
            n.markdown(f"<div class='cart-line'><div class='nm'>{qty} × {esc(item.name)}</div>"
                       f"<div class='sub'>{format_currency(line)}</div></div>", unsafe_allow_html=True)
            if minus.button("−", key=f"minus_{item_id}", width="stretch"):
                cart[item_id] = qty - 1
                if cart[item_id] <= 0:
                    cart.pop(item_id)
                st.rerun()
            if plus.button("+", key=f"plus_{item_id}", width="stretch"):
                cart[item_id] = qty + 1
                st.rerun()
            if rm.button("🗑", key=f"rm_{item_id}", width="stretch"):
                cart.pop(item_id)
                st.rerun()

        lines = [{"menu_item_id": i, "quantity": q} for i, q in cart.items()]
        preview_lines = [{"prep_time_minutes": menu_by_id[i].prep_time_minutes, "quantity": q} for i, q in cart.items()]
        estimate = coordinator.queue.estimate_for_new_order(preview_lines)
        st.markdown(
            f"<div class='cart-sum'><div class='row'><span>Items</span><span>{units}</span></div>"
            f"<div class='row total'><span>Total</span><span>{format_currency(total)}</span></div></div>"
            f"<div class='eta-pill'>⏱️ <div><b>{esc(estimate.label)}</b><br>{estimate.orders_ahead} order(s) ahead of you</div></div>",
            unsafe_allow_html=True,
        )
        notes = st.text_input("Note for the kitchen (optional)", max_chars=200, placeholder="e.g. less spicy")
        c1, c2 = st.columns([1, 1.6])
        if c1.button("Clear", width="stretch"):
            cart.clear()
            st.rerun()
        if c2.button("✅ Place Order", type="primary", width="stretch"):
            _submit(coordinator, student, lines, notes=notes)


def _submit(coordinator: CoordinatorAgent, student: dict, lines: list[dict], source: str = "MENU",
            notes: str = "") -> None:
    with st.spinner("Coordinator agent is processing your order..."):
        result = coordinator.place_order(student["id"], lines, source=source, notes=notes)
    if result.success:
        st.session_state["last_order"] = result.data
        st.session_state["cart"] = {}
        st.session_state.pop("nl_parsed", None)
        st.balloons()
        st.rerun()
    else:
        st.error(f"Order not placed: {result.error}")
        with st.expander("Agent trace"):
            agent_trace(result.data.get("trace", []))
