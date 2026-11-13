# 🍽️ Agentic AI-Based Smart Canteen Token System

A working prototype that lets students **order canteen food from their phone or laptop, get a digital token with an estimated ready time, track live preparation status, and get notified when the food is ready**. A team of five cooperating software agents handles the whole workflow.

Built with **Python · Streamlit · SQLite · Pandas** and an **optional, pluggable LLM**. It runs fully offline without an API key.

---

## 1. Project Overview

During college breaks, students lose most of a 15-minute break standing in the canteen queue: first to order, then to wait for the food. This system moves both of those steps online:

| Without the system | With the system |
|---|---|
| Walk to canteen → queue to order → queue to wait | Order from class → get token **T014** → walk in when notified **READY** |
| No idea how long food will take | "Estimated ready time: 12 minutes" |
| Staff juggle paper slips | Staff dashboard with a live order board |

## 2. Problem Statement

Physical queues at the college canteen during short breaks cause long waits, crowding, missed orders and wasted break time. Staff can't see demand coming, and students can't see how long their food will take.

## 3. Objectives

1. Let students browse the menu and order digitally (by clicking, or by typing in plain English).
2. Issue a **unique, sequential digital token** for every order.
3. **Estimate waiting time** from the live kitchen queue.
4. Track every order through a strict status workflow with timestamps.
5. **Notify** the student the moment food is READY.
6. Give canteen staff a live dashboard, menu/stock control and analytics.
7. Use a modular **multi-agent architecture** in which each agent can be replaced (for example, an ML wait-time model or a different LLM).

## 4. Agent Architecture

```
                    ┌──────────────────────────┐
  Student / Staff → │     CoordinatorAgent     │ ← the only entry point for the UI
                    │  orchestrates, logs,     │
                    │  rolls back on failure   │
                    └──┬──────┬──────┬──────┬──┘
           AgentMessage│      │      │      │  (intent + payload → AgentResult)
              ┌────────▼┐ ┌───▼────┐ ┌▼──────────┐ ┌▼─────────────────┐
              │ Order   │ │ Token  │ │Preparation│ │ Notification     │
              │ Agent   │ │ Agent  │ │ Agent     │ │ Agent            │
              └────┬────┘ └───┬────┘ └────┬──────┘ └───────┬──────────┘
                   │      QueueService    │          NotificationService
                   │     (wait estimator) │          (In-app + Email channels)
                   └──────────┴───────────┴──────────────┴──→ SQLite
        LLMService (optional) ← used by Coordinator for natural-language orders
```

| Agent | File | Responsibilities (intents) |
|---|---|---|
| **CoordinatorAgent** | `agents/coordinator_agent.py` | Receives every request; calls agents in sequence; passes each agent's output to the next; logs every message; cancels the order and releases stock if a later step fails; handles student login and NL parsing |
| **OrderAgent** | `agents/order_agent.py` | `validate_order` (item exists, available, stock, quantity limits, total), `check_duplicate`, `create_order` (atomic, reserves stock), `release_stock` |
| **TokenAgent** | `agents/token_agent.py` | `issue_token`: daily sequence T001, T002…; idempotent; duplicate-proof; returns the wait estimate |
| **PreparationAgent** | `agents/preparation_agent.py` | `confirm_order`, `update_status` (enforces the state machine and stamps timestamps), `refresh_estimates` |
| **NotificationAgent** | `agents/notification_agent.py` | `notify_status`: writes the message for each event and delivers it in-app, plus email for READY when enabled |

### How agents communicate
Agents never call each other directly. The Coordinator sends an `AgentMessage(sender, receiver, intent, payload)`. The receiving agent's `handle()` dispatches it to its `on_<intent>()` method and always returns an `AgentResult(success, data, error)`; business errors come back as results, not exceptions. Every message is stored in the `agent_logs` table and shown on the **🤖 Agent Activity** page and in each order's trace.

## 5. Workflow

```
Student ─► Coordinator ─► OrderAgent.validate_order      (items, availability, stock, total)
                      ─► OrderAgent.check_duplicate      (same cart <60 s? too many open orders?)
                      ─► OrderAgent.create_order         (status PENDING, stock reserved)
                      ─► TokenAgent.issue_token          (T014 + "Estimated ready time: 12 minutes")
                      ─► PreparationAgent.confirm_order  (status CONFIRMED, joins queue)
                      ─► NotificationAgent.notify_status (🔔 "Order confirmed - Token T014")
Staff ───► Coordinator ─► PreparationAgent.update_status (PREPARING → READY → COLLECTED)
                      ─► PreparationAgent.refresh_estimates (everyone's ETA updated)
                      ─► NotificationAgent.notify_status (🔔 "Token T014 is READY for pickup!")
Student collects food ✔
```

**Order state machine** (enforced by PreparationAgent):
```
PENDING → CONFIRMED → PREPARING → READY → COLLECTED
   └──────────┴───────────┴──→ CANCELLED     (students may cancel only before PREPARING)
```

### Waiting-time algorithm (`services/queue_service.py`)
1. **Order prep time** = slowest item's prep time + 0.5 min for each extra unit (items cook in batches).
2. **Orders ahead** = CONFIRMED/PREPARING orders placed earlier (FIFO). PREPARING orders only count their *remaining* minutes.
3. **Queue delay** = total minutes ahead ÷ number of kitchen stations (`KITCHEN_STATIONS`, default 2).
4. **Wait** = ⌈queue delay + own prep time⌉ → *"Estimated ready time: 13 minutes"*.

Worked example: one 8-min order waiting, one order with 6 min left, 2 stations, own order 6 min → (8+6)/2 + 6 = **13 min**.

The estimator sits behind the `WaitTimeEstimator` interface. An ML model can replace it without changing any agent, and the Analytics page already records *estimated vs actual* wait as training data.

### Natural-language ordering (`services/nl_parser.py`)
"I want two masala dosas and one coffee" → `Masala Dosa ×2, Coffee ×1`
- **With an LLM configured:** the LLM extracts items as JSON, then **every name is re-checked against the real menu**, so made-up items (like "Pizza") are rejected.
- **Without an LLM, or if the LLM call fails:** a local parser handles number words ("two", "a", "couple"), digits, "x2" / "2x", plurals, local names (chai, kaapi, idly) and typos ("samosaa", "cofee").

## 6. Technology Stack

| Layer | Technology |
|---|---|
| UI | Streamlit (sidebar navigation, live auto-refreshing fragments, toasts) |
| Agents & services | Python 3.11 (classes, dataclasses, ABC interfaces) |
| Database | SQLite (foreign keys, UNIQUE/CHECK constraints, `BEGIN IMMEDIATE` transactions) |
| Analytics | Pandas + Streamlit charts |
| LLM (optional) | Anthropic Claude or any OpenAI-compatible API over plain HTTPS (no SDK required) |
| Email (optional) | `smtplib` (SMTP/TLS) |
| Tests | pytest (29 tests) |

## 7. Database Design (`database/schema.py`)

```
students 1───* orders 1───* order_items *───1 menu_items
                 │ 1
                 ├──── 1 tokens              (UNIQUE order_id, UNIQUE(token_date, sequence_no))
                 ├───* order_status_history  (audit trail of every status change)
                 ├───* notifications *───1 students
                 └···* agent_logs            (every agent message)
```

| Table | Key columns |
|---|---|
| `students` | id, **usn (unique)**, name, email, created_at |
| `menu_items` | id, name (unique), category, price, prep_time_minutes, is_available, stock (NULL = unlimited) |
| `orders` | id, **order_code (unique)**, student_id→students, status (CHECK), total_amount, source, request_hash, estimated_wait/ready_at, queue_position, created/confirmed/preparing/ready/collected/cancelled_at |
| `order_items` | order_id→orders, menu_item_id→menu_items, item_name & unit_price (snapshots at order time), quantity, line_total |
| `tokens` | order_id→orders (unique), token_date, sequence_no, token_number (T014), token_code (20261029-T014, unique), issued_at |
| `notifications` | student_id, order_id, channel (IN_APP/EMAIL), title, message, event, delivery_status, is_read, created_at |
| `order_status_history` | order_id, from_status, to_status, changed_by, created_at |
| `agent_logs` | order_id, sender, receiver, intent, success, detail, created_at |

**How duplicate tokens are prevented:** (1) `issue_token` is idempotent per order; (2) the next number is computed inside a write-locked `BEGIN IMMEDIATE` transaction; (3) the database's UNIQUE constraints reject any duplicate that gets past (1) and (2). A test fires 10 threads at once and checks that all 10 tokens are unique.

**Duplicate order protection:** the same student + identical cart within `DUPLICATE_WINDOW_SECONDS` (default 60 s) is blocked as a double-click. A student can have at most `MAX_ACTIVE_ORDERS_PER_STUDENT` (default 3) open orders.

## 8. Installation

Requires **Python 3.10+**.
```bash
cd smart-canteen-agent
pip install -r requirements.txt
```
(Optional) use a virtual environment first: `python -m venv .venv` then `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (Linux/macOS).

## 9. Environment Setup

**No configuration is required.** To customise, copy `.env.example` to `.env`:

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `none` | `anthropic`, `openai` (any OpenAI-compatible API) or `none` |
| `LLM_API_KEY` | *(empty)* | API key (never hard-coded; read from `.env` only) |
| `LLM_MODEL` | `claude-haiku-5-5` / `gpt-4o-mini` | Model name |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | For OpenAI-compatible providers (Groq, Ollama…) |
| `KITCHEN_STATIONS` | `2` | Parallel cooking capacity used in wait estimation |
| `DUPLICATE_WINDOW_SECONDS` | `60` | Duplicate-order window |
| `MAX_ACTIVE_ORDERS_PER_STUDENT` | `3` | Open-order limit per student |
| `STAFF_PIN` | `1234` | PIN for the staff dashboard |
| `EMAIL_ENABLED` | `false` | Turn on email for "food is READY" |
| `SMTP_HOST/PORT/USER/PASSWORD`, `EMAIL_FROM`, `SMTP_USE_TLS` | | SMTP settings (e.g. Gmail with an App Password) |

## 10. How to Run

```bash
python -m database.seed --reset --demo-orders   # (optional) fresh DB + 3 demo orders
python -m streamlit run app.py
```
Open **http://localhost:8501**. The app also creates and seeds the database automatically on first run.

Seed options: `python -m database.seed` (menu + students only), `--reset` (wipe first), `--demo-orders` (place 3 orders through the real agent workflow).

## 11. How to Test

```bash
python -m pytest -v
```
Tests use a temporary database and never touch `data/canteen.db`. Coverage:

| File | What it tests |
|---|---|
| `tests/test_order_agent.py` | order creation & totals, invalid item, unavailable item, empty cart / bad quantity, stock limits, stock reserve & release, duplicate-order blocking, max active orders |
| `tests/test_token_agent.py` | sequential tokens, idempotent issue, DB-level duplicate rejection, 10-thread concurrency, prep-time formula, estimator math, wait grows with queue |
| `tests/test_workflow.py` | full multi-agent workflow + trace order, status timestamps & history, invalid transitions, cancellation rules, ETA refresh, NL → order, parser variants, LLM output validated against menu, LLM failure fallback, email only on READY, student registration validation |

## 12. Example Student Workflow

1. Open the app → enter USN `1BM22AI001` → **Continue** (new USNs register with a name).
2. **🍽️ Order Food** → filter **South Indian** → add **Masala Dosa ×2**, then **Coffee** from Beverages.
3. The cart shows **Total ₹115.00** and *"Estimated ready time: N minutes · K orders ahead"*.
4. **✅ Place Order** → the token card appears (**T004**, ready-by time, queue position) with the agent trace below it.
5. Or use **💬 Smart Order**: type *"I want two masala dosas and one coffee"* → **Understand my order** → **Order these now**.
6. **📦 My Orders**: a live tracker (refreshes every 5 s) shows Confirmed → Preparing → Ready → Collected. You can cancel before cooking starts.
7. When staff mark the order READY, a toast pops up 🔔 and **Notifications** shows *"Token T004 is READY for pickup!"*.

## 13. Example Canteen Staff Workflow

1. Sidebar → **👨‍🍳 Canteen Dashboard** → PIN `1234`.
2. **Live Order Board**: three columns (Confirmed | Preparing | Ready) with token, student, items, notes and ETA. Metrics: active queue, ready count, today's orders, avg prep time, revenue.
3. Click **Start preparing** → **Mark READY** (the student is notified instantly) → **Mark COLLECTED** when the student shows the token.
4. **All Orders**: filter by status/date, search by token or USN, update any order manually.
5. **Menu & Stock**: mark items unavailable or set today's stock (e.g. Gobi Manchurian is off in the mornings).
6. **📊 Analytics**: top items, orders by hour, revenue by category, estimated-vs-actual wait chart.
7. **🤖 Agent Activity**: architecture diagram plus every agent message.

## 14. Future Enhancements

- **ML wait-time prediction** trained on `orders` timestamps (plug in via `WaitTimeEstimator`)
- UPI / online payment before token issue
- SMS / WhatsApp / push notification channels (subclass `NotificationChannel`)
- Demand forecasting for the kitchen (prepare popular items before breaks)
- QR-code tokens scanned at the counter
- Pickup time slots, and pre-ordering for a specific break
- Student login via college SSO; role-based staff accounts
- Multi-counter / multi-canteen support; PostgreSQL for campus-wide deployment

## Project Structure

```
smart-canteen-agent/
├── app.py                     # Streamlit entry point, sidebar navigation, login
├── requirements.txt  ·  README.md  ·  .env.example  ·  .gitignore  ·  .streamlit/config.toml
├── agents/                    # base_agent, coordinator, order, token, preparation, notification
├── services/                  # llm_service, nl_parser, queue_service, notification_service, analytics_service
├── database/                  # database (connection/transactions), schema, seed
├── models/models.py           # OrderStatus, state machine, AgentMessage/AgentResult, dataclasses
├── ui/                        # student, orders, notifications, canteen_dashboard, analytics, components
├── utils/                     # config (.env), helpers
├── data/canteen.db            # created automatically
└── tests/                     # conftest + 3 test modules (29 tests)
```
