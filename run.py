import os
import re
import uuid
from datetime import datetime
from functools import wraps

import cv2
import pytesseract
from PIL import Image
from flask import (Flask, flash, jsonify, redirect,
                   render_template, request, session, url_for,
                   send_from_directory)
from werkzeug.utils import secure_filename
import storage

if os.name == 'nt':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

app = Flask(__name__)
app.secret_key = "receiptsecret2024"

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

ALLOWED = {"jpg", "jpeg", "png"}

CATEGORIES = {
    "Food":      ["restaurant", "cafe", "pizza", "burger", "food", "lunch",
                  "dinner", "breakfast", "coffee", "dhaba", "swiggy", "zomato"],
    "Travel":    ["petrol", "fuel", "taxi", "uber", "ola", "bus", "train",
                  "flight", "rapido", "parking", "toll", "metro"],
    "Shopping":  ["store", "mart", "amazon", "flipkart", "mall", "shop",
                  "market", "retail", "purchase", "buy"],
    "Utilities": ["electricity", "internet", "water", "gas", "phone", "mobile",
                  "bill", "wifi", "netflix", "spotify", "subscription"],
}

MONTH_NAMES = {
    "01":"January","02":"February","03":"March","04":"April",
    "05":"May","06":"June","07":"July","08":"August",
    "09":"September","10":"October","11":"November","12":"December"
}

# ── Auth decorator ──────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def current_user_id():
    return session.get("user_id")

def current_month():
    return request.args.get("month", datetime.now().strftime("%Y-%m"))

# ── OCR helpers ─────────────────────────────────────────────────

def is_allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED

def read_receipt(path):
    try:
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        img = cv2.bilateralFilter(img, 9, 75, 75)
        _, img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        text = pytesseract.image_to_string(Image.fromarray(img), config="--psm 6")
    except Exception:
        text = pytesseract.image_to_string(Image.open(path), config="--psm 6")
    return text

def find_amount(text):
    m = re.search(
        r'(?:total|grand\s*total|amount\s*due|subtotal|payable|balance)[^\d]{0,10}(\d[\d,]*\.?\d*)',
        text, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except: pass
    for m in re.finditer(r'(?:rs\.?|inr|\$|₹)\s*(\d[\d,]*\.?\d*)', text, re.IGNORECASE):
        try:
            v = float(m.group(1).replace(",", ""))
            if v > 0: return v
        except: pass
    nums = []
    for m in re.finditer(r'\b(\d{1,6}\.\d{2})\b', text):
        try: nums.append(float(m.group(1)))
        except: pass
    return max(nums) if nums else 0.0

def find_date(text):
    months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
               "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
    patterns = [
        (r'\b(\d{2})[/-](\d{2})[/-](\d{4})\b', "dmy"),
        (r'\b(\d{4})[/-](\d{2})[/-](\d{2})\b', "ymd"),
        (r'\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+(\d{4})\b', "named"),
    ]
    for pat, fmt in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                if fmt == "dmy":
                    d, mo, y = m.groups()
                    return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
                elif fmt == "ymd":
                    y, mo, d = m.groups()
                    return f"{y}-{mo}-{d}"
                elif fmt == "named":
                    d, mo_str, y = m.groups()
                    mo = months.get(mo_str[:3].lower(), 1)
                    return f"{y}-{mo:02d}-{int(d):02d}"
            except: pass
    return datetime.today().strftime("%Y-%m-%d")

def find_vendor(text):
    for line in text.splitlines()[:6]:
        line = line.strip()
        if len(line) >= 3 and not line.replace(" ", "").isdigit():
            clean = re.sub(r"[^A-Za-z0-9 &'\-\.]", "", line).strip()
            if clean: return clean[:50]
    return "Unknown Vendor"

def find_category(vendor, desc=""):
    text = (vendor + " " + desc).lower()
    for cat, keys in CATEGORIES.items():
        if any(k in text for k in keys): return cat
    return "Other"

def get_suggestion(pct, over, cats=None):
    """Dynamic suggestions based on spending and top categories"""
    top_cats = []
    if cats:
        top_cats = [c["category"] for c in cats[:2]]  # top 2 spending categories

    if over or pct >= 100:
        msg = "🚨 Budget exceeded! "
        if "Travel" in top_cats and "Shopping" in top_cats:
            msg += "You spent heavily on Travel and Shopping. Cut down on unnecessary trips and online purchases."
        elif "Travel" in top_cats:
            msg += "Travel is your biggest expense. Use public transport or carpool to reduce costs."
        elif "Shopping" in top_cats:
            msg += "Shopping is your biggest expense. Avoid impulse purchases and stick to essentials only."
        elif "Food" in top_cats:
            msg += "Food spending is very high. Cook at home more often and avoid eating out daily."
        elif "Utilities" in top_cats:
            msg += "Utility bills are high. Check for unused subscriptions and cancel them."
        else:
            msg += "Stop all non-essential spending immediately and review your expenses."
        return ("danger", msg)
    elif pct >= 90:
        msg = "⚠️ Over 90% budget used! "
        if top_cats:
            msg += f"Your top spending categories are {' and '.join(top_cats)}. Avoid any new purchases there."
        else:
            msg += "Avoid any unnecessary purchases this month."
        return ("warning", msg)
    elif pct >= 75:
        msg = "⚡ 75% of budget used. "
        if top_cats:
            msg += f"Be careful with {' and '.join(top_cats)} spending for the rest of the month."
        else:
            msg += "Be careful with spending for the rest of the month."
        return ("warning", msg)
    elif pct >= 50:
        return ("info", "📊 Half your budget is used. Keep tracking expenses to stay on target.")
    elif pct >= 25:
        return ("success", "✅ Good progress! Well within budget. You may have savings left this month.")
    else:
        return ("success", "🎉 Excellent! You have barely used your budget. Great financial discipline!")

def make_month_label(month):
    if "-" in month:
        parts = month.split("-")
        return MONTH_NAMES.get(parts[1], month) + " " + parts[0]
    return month

# ── Auth routes ─────────────────────────────────────────────────

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        user = storage.get_user(username, password)
        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash(f"Welcome back, {user['username']}!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        confirm  = request.form.get("confirm", "").strip()
        if len(username) < 3:
            flash("Username must be at least 3 characters.", "error")
        elif len(password) < 4:
            flash("Password must be at least 4 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif storage.create_user(username, password):
            flash("Account created! Please log in.", "success")
            return redirect(url_for("login"))
        else:
            flash("Username already taken. Try another.", "error")
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

# ── File serving ────────────────────────────────────────────────

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# ── App routes ──────────────────────────────────────────────────

@app.route("/upload")
@login_required
def home():
    return render_template("upload.html", username=session.get("username"))

@app.route("/scan", methods=["POST"])
@login_required
def scan():
    f = request.files.get("receipt")
    if not f or f.filename == "":
        flash("No file selected!", "error")
        return redirect(url_for("home"))
    if not is_allowed(f.filename):
        flash("Only JPG, JPEG, PNG files are allowed!", "error")
        return redirect(url_for("home"))
    ext   = secure_filename(f.filename).rsplit(".", 1)[1].lower()
    fname = uuid.uuid4().hex + "." + ext
    fpath = os.path.join(UPLOAD_FOLDER, fname)
    f.save(fpath)
    try:
        text = read_receipt(fpath)
    except Exception as e:
        flash(f"OCR error: {e}", "error")
        return redirect(url_for("home"))
    vendor   = find_vendor(text)
    date     = find_date(text)
    amount   = find_amount(text)
    desc     = text[:300].replace("\n", " ").strip()
    category = find_category(vendor, desc)
    storage.add_expense(current_user_id(), date, vendor, amount, category, desc, fname)
    flash(f"Receipt scanned! Vendor: {vendor} | Amount: ₹{amount:.2f} | Category: {category}", "success")
    return redirect(url_for("dashboard"))

@app.route("/manual", methods=["POST"])
@login_required
def manual():
    vendor = request.form.get("vendor", "").strip() or "Unknown"
    date   = request.form.get("date", datetime.today().strftime("%Y-%m-%d"))
    desc   = request.form.get("description", "").strip()
    try:
        amount = float(request.form.get("amount", 0))
    except:
        flash("Invalid amount!", "error")
        return redirect(url_for("home"))
    category = find_category(vendor, desc)
    storage.add_expense(current_user_id(), date, vendor, amount, category, desc, None)
    flash(f"Expense added: {vendor} — ₹{amount:.2f}", "success")
    return redirect(url_for("dashboard"))

@app.route("/dashboard")
@login_required
def dashboard():
    uid   = current_user_id()
    month = current_month()
    total   = storage.month_total(uid, month)
    budget  = storage.get_budget(uid, month)
    recent  = storage.recent_expenses(uid, month)
    cats    = storage.by_category(uid, month)
    monthly = storage.by_month(uid)
    over    = total > budget
    pct     = round((total / budget * 100), 1) if budget > 0 else 0
    sug_type, suggestion = get_suggestion(pct, over, cats)  # cats pass kiya
    month_label = make_month_label(month)
    return render_template("home.html",
        total=round(total,2), budget=round(budget,2),
        over=over, pct=pct, recent=recent, cats=cats,
        monthly=monthly, month=month, month_label=month_label,
        suggestion=suggestion, sug_type=sug_type,
        username=session.get("username")
    )

@app.route("/expenses")
@login_required
def expenses():
    uid   = current_user_id()
    month = current_month()
    all_exp = storage.all_expenses(uid, month)
    month_label = make_month_label(month)
    return render_template("expenses.html",
        expenses=all_exp, month=month,
        month_label=month_label,
        username=session.get("username")
    )

@app.route("/budget", methods=["GET", "POST"])
@login_required
def budget():
    uid = current_user_id()
    month = request.form.get("month", request.args.get("month", datetime.now().strftime("%Y-%m")))
    if request.method == "POST":
        try:
            storage.save_budget(uid, month, float(request.form.get("budget", 5000)))
            flash(f"Budget for {make_month_label(month)} updated!", "success")
        except:
            flash("Invalid amount!", "error")
        return redirect(url_for("budget", month=month))
    total = storage.month_total(uid, month)
    bgt   = storage.get_budget(uid, month)
    cats  = storage.by_category(uid, month)
    pct   = round((total / bgt * 100), 1) if bgt > 0 else 0
    over  = total > bgt
    sug_type, suggestion = get_suggestion(pct, over, cats)  # cats pass kiya
    month_label = make_month_label(month)
    return render_template("budget.html",
        budget=round(bgt,2), total=round(total,2),
        month=month, month_label=month_label,
        pct=pct, over=over,
        suggestion=suggestion, sug_type=sug_type,
        username=session.get("username")
    )

@app.route("/delete/<int:eid>", methods=["POST"])
@login_required
def delete(eid):
    uid = current_user_id()
    exp = storage.find_expense(eid, uid)
    if exp and exp.get("image_path"):
        p = os.path.join(UPLOAD_FOLDER, exp["image_path"])
        if os.path.exists(p):
            os.remove(p)
    storage.remove_expense(eid, uid)
    flash("Expense deleted.", "info")
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    return redirect(url_for("expenses", month=month))

@app.route("/api/cats")
@login_required
def api_cats():
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    return jsonify(storage.by_category(current_user_id(), month))

@app.route("/api/monthly")
@login_required
def api_monthly():
    return jsonify(storage.by_month(current_user_id()))

if __name__ == "__main__":
    storage.setup()
    app.run(debug=True, port=5000)