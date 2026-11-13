"""SQLite schema for the Smart Canteen Token System."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS students (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    usn         TEXT    NOT NULL UNIQUE,          -- university seat number
    name        TEXT    NOT NULL,
    email       TEXT,
    phone       TEXT,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS menu_items (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT    NOT NULL UNIQUE,
    category           TEXT    NOT NULL,
    price              REAL    NOT NULL CHECK (price >= 0),
    prep_time_minutes  INTEGER NOT NULL CHECK (prep_time_minutes > 0),
    is_available       INTEGER NOT NULL DEFAULT 1,
    stock              INTEGER CHECK (stock IS NULL OR stock >= 0),  -- NULL = unlimited
    description        TEXT,
    created_at         TEXT    NOT NULL,
    updated_at         TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    order_code              TEXT    NOT NULL UNIQUE,     -- e.g. ORD-20261029-7F3A2C
    student_id              INTEGER NOT NULL REFERENCES students(id),
    status                  TEXT    NOT NULL CHECK (status IN
                              ('PENDING','CONFIRMED','PREPARING','READY','COLLECTED','CANCELLED')),
    total_amount            REAL    NOT NULL,
    source                  TEXT    NOT NULL DEFAULT 'MENU',  -- MENU | NATURAL_LANGUAGE
    notes                   TEXT,
    request_hash            TEXT    NOT NULL,            -- duplicate-order protection
    estimated_prep_minutes  REAL,
    estimated_wait_minutes  REAL,
    estimated_ready_at      TEXT,
    queue_position          INTEGER,
    cancel_reason           TEXT,
    created_at              TEXT    NOT NULL,
    confirmed_at            TEXT,
    preparing_at            TEXT,
    ready_at                TEXT,
    collected_at            TEXT,
    cancelled_at            TEXT,
    updated_at              TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orders_status  ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_student ON orders(student_id, created_at);

CREATE TABLE IF NOT EXISTS order_items (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id           INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    menu_item_id       INTEGER NOT NULL REFERENCES menu_items(id),
    item_name          TEXT    NOT NULL,       -- snapshot at order time
    quantity           INTEGER NOT NULL CHECK (quantity > 0),
    unit_price         REAL    NOT NULL,       -- snapshot at order time
    line_total         REAL    NOT NULL,
    prep_time_minutes  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tokens (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id      INTEGER NOT NULL UNIQUE REFERENCES orders(id),  -- one token per order
    token_date    TEXT    NOT NULL,           -- YYYY-MM-DD, sequence resets daily
    sequence_no   INTEGER NOT NULL,
    token_number  TEXT    NOT NULL,           -- what the student sees, e.g. T014
    token_code    TEXT    NOT NULL UNIQUE,    -- globally unique, e.g. 20261029-T014
    issued_at     TEXT    NOT NULL,
    UNIQUE (token_date, sequence_no)
);

CREATE TABLE IF NOT EXISTS notifications (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id       INTEGER NOT NULL REFERENCES students(id),
    order_id         INTEGER REFERENCES orders(id),
    channel          TEXT    NOT NULL,         -- IN_APP | EMAIL
    title            TEXT    NOT NULL,
    message          TEXT    NOT NULL,
    event            TEXT,                     -- status that triggered it
    delivery_status  TEXT    NOT NULL,         -- SENT | FAILED | SKIPPED
    error            TEXT,
    is_read          INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notifications_student ON notifications(student_id, is_read);

CREATE TABLE IF NOT EXISTS order_status_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER NOT NULL REFERENCES orders(id),
    from_status  TEXT,
    to_status    TEXT    NOT NULL,
    changed_by   TEXT    NOT NULL,
    created_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    INTEGER,   -- deliberately not a FK: rejected requests may name unknown orders
    sender     TEXT    NOT NULL,
    receiver    TEXT    NOT NULL,
    intent      TEXT    NOT NULL,
    success     INTEGER,
    detail      TEXT,
    created_at  TEXT    NOT NULL
);
"""
