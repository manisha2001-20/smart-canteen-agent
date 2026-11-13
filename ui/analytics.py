"""Analytics page + Agent Activity page."""
import pandas as pd
import streamlit as st

from agents.coordinator_agent import CoordinatorAgent
from services.analytics_service import AnalyticsService
from ui.components import (CHART_AMBER, CHART_EMERALD, STATUS_STYLE, empty_state, esc, hero, section,
                           stat_tiles)
from utils.helpers import format_currency, today_str


def _fmt_min(value) -> str:
    return f"{value:.1f} min" if value else "-"


def render(coordinator: CoordinatorAgent) -> None:
    hero("Analytics", "Canteen performance for the selected day, and how accurate the waiting-time estimates were.",
         eyebrow="📊 Insights")
    analytics = AnalyticsService(coordinator.db)
    c1, _ = st.columns([1, 3])
    day = c1.date_input("Day", value=pd.to_datetime(today_str())).strftime("%Y-%m-%d")
    s = analytics.today_summary(day)

    stat_tiles([
        ("🧾", "Orders", int(s["total_orders"]), "sl"),
        ("₹", "Revenue", format_currency(s["revenue"]), "am"),
        ("🛍️", "Avg order value", format_currency(s["avg_order_value"]), "am"),
        ("👨‍🍳", "Avg prep time", _fmt_min(s["avg_prep_minutes"]), "em"),
        ("⏱️", "Avg order → ready", _fmt_min(s["avg_wait_minutes"]), "em"),
    ])
    stat_tiles([
        ("🔥", "Active queue", coordinator.queue.active_queue_count(), "am"),
        ("✅", "Ready", int(s["ready"]), "em"),
        ("🍽️", "Collected", int(s["collected"]), "sl"),
        ("✖", "Cancelled", int(s["cancelled"]), "sl"),
        ("🎯", "Avg estimated wait", _fmt_min(s["avg_estimated_wait"]), "em"),
    ])

    if not s["total_orders"]:
        empty_state("📭", "No orders on this day yet", "Pick another day or place a few orders.")
        return

    l, r = st.columns(2, gap="medium")
    with l:
        with st.container(key="chart_top"):
            st.markdown("#### Top items")
            st.caption("Quantity sold")
            top = analytics.top_items(day)
            if not top.empty:
                st.bar_chart(top.set_index("item")["quantity"], color=CHART_EMERALD, horizontal=True,
                             x_label="", y_label="")
        st.write("")
        with st.container(key="chart_hour"):
            st.markdown("#### Orders by hour")
            st.caption("Number of orders placed")
            hourly = analytics.orders_by_hour(day)
            if not hourly.empty:
                st.bar_chart(hourly.set_index("hour")["orders"], color=CHART_EMERALD, x_label="", y_label="")
    with r:
        with st.container(key="chart_status"):
            st.markdown("#### Orders by status")
            st.caption("Where today's orders are right now")
            dist = analytics.status_distribution(day)
            if not dist.empty:
                biggest = max(dist["orders"].max(), 1)
                rows = []
                for rec in dist.sort_values("orders", ascending=False).to_dict("records"):
                    color, _, icon = STATUS_STYLE.get(rec["status"], ("#475569", "", "•"))
                    rows.append(f"<div class='r'><span>{icon} {esc(rec['status'].title())}</span>"
                                f"<div class='track'><div class='fill' style='width:{rec['orders'] / biggest * 100:.0f}%;"
                                f"background:{color}'></div></div><span class='n'>{rec['orders']}</span></div>")
                st.markdown(f"<div class='st-bars'>{''.join(rows)}</div>", unsafe_allow_html=True)
        st.write("")
        with st.container(key="chart_cat"):
            st.markdown("#### Revenue by category")
            st.caption("₹, excluding cancelled orders")
            cat = analytics.category_revenue(day)
            if not cat.empty:
                st.bar_chart(cat.set_index("category")["revenue"], color=CHART_AMBER, horizontal=True,
                             x_label="", y_label="")

    st.write("")
    with st.container(key="chart_acc"):
        st.markdown("#### Waiting-time estimate vs actual")
        st.caption("Minutes per token, for orders that reached READY. This is the training data for a future ML estimator.")
        acc = analytics.estimate_accuracy()
        if acc.empty:
            st.caption("Shown once orders reach READY.")
        else:
            st.line_chart(acc.iloc[::-1].set_index("token")[["estimated", "actual"]],
                          color=[CHART_EMERALD, CHART_AMBER], x_label="Token", y_label="Minutes")
            with st.expander("View as table"):
                st.dataframe(acc, hide_index=True, width="stretch")

    st.write("")
    with st.expander("📅 Last 7 days"):
        st.dataframe(analytics.daily_history(), hide_index=True, width="stretch",
                     column_config={"revenue": st.column_config.NumberColumn(format="₹%.2f")})


# ------------------------------------------------------------------ agent activity
AGENT_ROLES = {
    "OrderAgent": ("🧾", "Validates items, blocks duplicates, creates the order"),
    "TokenAgent": ("🎫", "Issues a unique token and estimates the wait"),
    "PreparationAgent": ("👨‍🍳", "Owns the status state machine and ETAs"),
    "NotificationAgent": ("🔔", "Notifies the student in-app (and by email)"),
}


def _flow_html(coordinator: CoordinatorAgent) -> str:
    arrow = "<div class='ag-arrow'>→</div>"
    nodes = ["<div class='ag-node actor'><div class='ic'>🧑‍🎓</div><div class='nm'>Student</div>"
             "<div class='rl'>Places an order or types a request</div></div>",
             "<div class='ag-node coord'><div class='ic'>🧠</div><div class='nm'>Coordinator Agent</div>"
             "<div class='rl'>Orchestrates the workflow, logs every message, rolls back on failure</div></div>"]
    agents = [coordinator.order_agent, coordinator.token_agent, coordinator.preparation_agent,
              coordinator.notification_agent]
    for i, agent in enumerate(agents, 1):
        icon, role = AGENT_ROLES[agent.name]
        intents = "".join(f"<code>{esc(c)}</code>" for c in agent.capabilities)
        nodes.append(f"<div class='ag-node'><span class='step'>STEP {i}</span><div class='ic'>{icon}</div>"
                     f"<div class='nm'>{esc(agent.name.replace('Agent', ' Agent'))}</div><div class='rl'>{esc(role)}</div>"
                     f"<div class='ag-intents'>{intents}</div></div>")
    nodes.append("<div class='ag-node actor'><div class='ic'>🍽️</div><div class='nm'>Student collects</div>"
                 "<div class='rl'>Shows the token at the counter</div></div>")
    return f"<div class='ag-flow'>{arrow.join(nodes)}</div>"


def render_agents(coordinator: CoordinatorAgent) -> None:
    hero("Agent Activity", "How the multi-agent system is wired, and every message the agents exchanged.",
         eyebrow="🤖 Multi-agent workflow")
    section("Workflow", "Each arrow is an AgentMessage (intent + payload) sent by the Coordinator; each agent answers with an AgentResult.")
    st.markdown(_flow_html(coordinator), unsafe_allow_html=True)

    st.markdown(
        f"<div class='cfg-row'><span>🧠 LLM: <b>{esc(coordinator.llm.description)}</b></span>"
        f"<span>📧 Email: <b>{'enabled' if coordinator.settings.email_enabled else 'disabled'}</b></span>"
        f"<span>🔥 Kitchen stations: <b>{coordinator.settings.kitchen_stations}</b></span></div>",
        unsafe_allow_html=True,
    )

    logs = coordinator.get_agent_logs(limit=200)
    section("Recent agent messages", f"Latest {min(len(logs), 15)} of {len(logs)} shown below · full log in the table")
    if not logs:
        empty_state("🤖", "No agent messages yet", "Place an order to see the agents talk to each other.")
        return
    feed = []
    for l in logs[:15]:
        mark = "✓" if l["success"] else "✖"
        order = f" &nbsp;<span class='sc-chip'>order #{l['order_id']}</span>" if l["order_id"] else ""
        feed.append(
            f"<div class='ag-msg{'' if l['success'] else ' fail'}'><div class='t'>{esc(l['created_at'][11:])}</div><div>"
            f"<div class='route'>{mark} <b>{esc(l['sender'])}</b><span class='x'>→</span><b>{esc(l['receiver'])}</b>"
            f" &nbsp;<span class='sc-chip am'>{esc(l['intent'])}</span>{order}</div>"
            f"<div class='d'>{esc(l['detail'])}</div></div></div>"
        )
    st.markdown(f"<div class='ag-feed'>{''.join(feed)}</div>", unsafe_allow_html=True)
    st.write("")
    with st.expander(f"📋 Full message log ({len(logs)})"):
        st.dataframe(pd.DataFrame([{"Time": l["created_at"], "Order": l["order_id"], "From": l["sender"],
                                    "To": l["receiver"], "Intent": l["intent"],
                                    "OK": "✅" if l["success"] else "❌", "Detail": l["detail"]} for l in logs]),
                     hide_index=True, width="stretch", height=420)
