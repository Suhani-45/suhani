import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

DB_NAME = "database.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    with open('schema.sql', 'r') as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

# Users
def create_user(email, password):
    conn = get_db()
    try:
        hashed = generate_password_hash(password)
        conn.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, hashed))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def verify_user(email, password):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    if user and check_password_hash(user['password'], password):
        return dict(user)
    return None

def reset_password(email, new_password):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if user:
        hashed = generate_password_hash(new_password)
        conn.execute("UPDATE users SET password = ? WHERE email = ?", (hashed, email))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def get_user_profile(user_id):
    conn = get_db()
    user = conn.execute("SELECT id, email, name, phone, photo, occupation, age FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None

def update_user_profile(user_id, name, phone, photo, occupation=None, age=None):
    conn = get_db()
    conn.execute("UPDATE users SET name = ?, phone = ?, photo = ?, occupation = ?, age = ? WHERE id = ?", (name, phone, photo, occupation, age, user_id))
    conn.commit()
    conn.close()

# Expenses
def add_expense(user_id, date, month, vendor, amount, category, description):
    conn = get_db()
    conn.execute(
        "INSERT INTO expenses (user_id, date, month, vendor, amount, category, description) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, date, month, vendor, amount, category, description)
    )
    conn.commit()
    conn.close()

def delete_expense(user_id, expense_id):
    conn = get_db()
    conn.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id))
    conn.commit()
    conn.close()

def get_all_expenses(user_id, month=None):
    conn = get_db()
    if month:
        expenses = conn.execute("SELECT * FROM expenses WHERE user_id = ? AND month = ? ORDER BY date ASC, id ASC", (user_id, month)).fetchall()
    else:
        expenses = conn.execute("SELECT * FROM expenses WHERE user_id = ? ORDER BY date ASC, id ASC", (user_id,)).fetchall()
    conn.close()
    return [dict(e) for e in expenses]

def get_total_spent(user_id, month):
    conn = get_db()
    total = conn.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ? AND month = ?", (user_id, month)).fetchone()[0]
    conn.close()
    return total if total else 0.0

def get_category_breakdown(user_id, month):
    conn = get_db()
    cats = conn.execute("SELECT category, SUM(amount) as total FROM expenses WHERE user_id = ? AND month = ? GROUP BY category", (user_id, month)).fetchall()
    conn.close()
    return [dict(c) for c in cats]

# Budgets
def get_budget(user_id, month):
    conn = get_db()
    b = conn.execute("SELECT amount FROM budgets WHERE user_id = ? AND month = ?", (user_id, month)).fetchone()
    conn.close()
    return float(b['amount']) if b else 10000.0

def set_budget(user_id, month, amount):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO budgets (user_id, month, amount) VALUES (?, ?, ?)", (user_id, month, amount))
    conn.commit()
    conn.close()

def get_suggestion(budget, spent, cat_data=None):
    if spent > budget:
        highest_cat_name = "your top spending category"
        if cat_data and len(cat_data) > 0:
            highest_cat = max(cat_data, key=lambda x: x['total'])
            highest_cat_name = highest_cat['category'].lower()
                
        return {
            'status': 'exceeded',
            'msg': f'Warning! You have exceeded your budget. Your overspending happened mainly in {highest_cat_name}. Try to find cheaper alternatives or cut non-essential purchases in this category to recover.'
        }
    else:
        diff = budget - spent
        return {
            'status': 'under',
            'savings_amount': diff,
            'msg': f'Congratulations! You stayed within your budget and saved ₹{diff:.2f}.'
        }

def compare_months(user_id, m1, m2):
    s1 = get_total_spent(user_id, m1)
    s2 = get_total_spent(user_id, m2)
    
    if s1 > s2:
        res = f"{m1} had higher spending than {m2}."
    elif s2 > s1:
        res = f"{m2} had higher spending than {m1}."
    else:
        res = "Both months had the exact same spending."
        
    diff = abs(s1 - s2)
    
    return {
        'm1_total': s1,
        'm2_total': s2,
        'higher_msg': res,
        'diff': diff,
        'conclusion': f"Overall difference is ₹{diff:.2f}."
    }
