import sqlite3
from datetime import datetime

DB = "receipts.db"

def connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def setup():
    conn = connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            username   TEXT NOT NULL UNIQUE,
            password   TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            date        TEXT NOT NULL,
            vendor      TEXT NOT NULL,
            amount      REAL NOT NULL,
            category    TEXT NOT NULL DEFAULT 'Other',
            description TEXT,
            image_path  TEXT,
            created_at  TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            user_id INTEGER NOT NULL,
            month   TEXT NOT NULL,
            budget  REAL NOT NULL DEFAULT 5000,
            PRIMARY KEY(user_id, month)
        )
    """)
    conn.commit()
    conn.close()

# ── User functions ──────────────────────────────────────────────

def create_user(username, password):
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO users (username, password, created_at) VALUES (?,?,?)",
            (username, password, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_user(username, password):
    conn = connect()
    row = conn.execute(
        "SELECT * FROM users WHERE username=? AND password=?", (username, password)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_id(uid):
    conn = connect()
    row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return dict(row) if row else None

# ── Expense functions ───────────────────────────────────────────

def add_expense(user_id, date, vendor, amount, category, description, image_path):
    conn = connect()
    cur = conn.execute("""
        INSERT INTO expenses (user_id, date, vendor, amount, category, description, image_path, created_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (user_id, date, vendor, amount, category, description, image_path,
          datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid

def all_expenses(user_id, month=None):
    conn = connect()
    if month:
        rows = conn.execute(
            "SELECT * FROM expenses WHERE user_id=? AND date LIKE ? ORDER BY date DESC, created_at DESC",
            (user_id, f"{month}%")
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM expenses WHERE user_id=? ORDER BY date DESC, created_at DESC",
            (user_id,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def recent_expenses(user_id, month=None, n=10):
    conn = connect()
    if month:
        rows = conn.execute(
            "SELECT * FROM expenses WHERE user_id=? AND date LIKE ? ORDER BY date DESC LIMIT ?",
            (user_id, f"{month}%", n)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM expenses WHERE user_id=? ORDER BY date DESC LIMIT ?",
            (user_id, n)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def find_expense(eid, user_id):
    conn = connect()
    row = conn.execute(
        "SELECT * FROM expenses WHERE id=? AND user_id=?", (eid, user_id)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def remove_expense(eid, user_id):
    conn = connect()
    conn.execute("DELETE FROM expenses WHERE id=? AND user_id=?", (eid, user_id))
    conn.commit()
    conn.close()

def month_total(user_id, month):
    conn = connect()
    row = conn.execute(
        "SELECT COALESCE(SUM(amount),0) AS t FROM expenses WHERE user_id=? AND date LIKE ?",
        (user_id, f"{month}%")
    ).fetchone()
    conn.close()
    return float(row["t"])

def by_category(user_id, month=None):
    conn = connect()
    if month:
        rows = conn.execute("""
            SELECT category, COALESCE(SUM(amount),0) AS total
            FROM expenses WHERE user_id=? AND date LIKE ?
            GROUP BY category ORDER BY total DESC
        """, (user_id, f"{month}%")).fetchall()
    else:
        rows = conn.execute("""
            SELECT category, COALESCE(SUM(amount),0) AS total
            FROM expenses WHERE user_id=?
            GROUP BY category ORDER BY total DESC
        """, (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def by_month(user_id):
    conn = connect()
    rows = conn.execute("""
        SELECT strftime('%Y-%m', date) AS month, COALESCE(SUM(amount),0) AS total
        FROM expenses WHERE user_id=?
        GROUP BY month ORDER BY month DESC LIMIT 6
    """, (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]

def get_available_months(user_id):
    conn = connect()
    rows = conn.execute("""
        SELECT DISTINCT strftime('%Y-%m', date) AS month
        FROM expenses WHERE user_id=?
        ORDER BY month DESC
    """, (user_id,)).fetchall()
    conn.close()
    return [r["month"] for r in rows]

# ── Budget functions ────────────────────────────────────────────

def get_budget(user_id, month):
    conn = connect()
    row = conn.execute(
        "SELECT budget FROM settings WHERE user_id=? AND month=?", (user_id, month)
    ).fetchone()
    conn.close()
    return float(row["budget"]) if row else 5000.0

def save_budget(user_id, month, amount):
    conn = connect()
    conn.execute(
        "INSERT OR REPLACE INTO settings (user_id, month, budget) VALUES (?,?,?)",
        (user_id, month, float(amount))
    )
    conn.commit()
    conn.close()