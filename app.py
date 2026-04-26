import os
import uuid
from functools import wraps
from datetime import datetime
import cv2
import pytesseract
from PIL import Image
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
import database

if os.name == 'nt':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

app = Flask(__name__)
app.secret_key = 'super_secret_receipt_key'
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Decorator
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('username') or request.form.get('email')
        password = request.form.get('password')
        user = database.verify_user(email, password)
        if user:
            session['user_id'] = user['id']
            session['email'] = user['email']
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid email or password.', 'danger')
    return render_template('login.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('username') or request.form.get('email')
        new_password = request.form.get('new_password')
        
        if database.reset_password(email, new_password):
            flash('Password reset successfully! Please login with your new password.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Account with that email or phone number not found.', 'danger')
            
    return render_template('forgot_password.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('username') or request.form.get('email')
        password = request.form.get('password')
        if database.create_user(email, password):
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Email already exists!', 'danger')
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_id = session['user_id']
    if request.method == 'POST':
        name = request.form.get('name', '')
        phone = request.form.get('phone', '')
        occupation = request.form.get('occupation', '')
        age_str = request.form.get('age', '')
        
        age = int(age_str) if age_str.isdigit() else None
        
        # Get current profile to preserve existing photo if no new photo is uploaded
        current_profile = database.get_user_profile(user_id)
        photo_filename = current_profile.get('photo', '') if current_profile else ''
        
        photo = request.files.get('photo')
        if photo and photo.filename != '':
            ext = photo.filename.rsplit('.', 1)[-1].lower() if '.' in photo.filename else 'jpg'
            fname = f"user_{user_id}_{uuid.uuid4().hex}.{ext}"
            fpath = os.path.join(app.config['UPLOAD_FOLDER'], fname)
            photo.save(fpath)
            photo_filename = fname
            
        database.update_user_profile(user_id, name, phone, photo_filename, occupation, age)
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))
        
    user_profile = database.get_user_profile(user_id)
    return render_template('profile.html', user=user_profile)

@app.route('/dashboard')
@login_required
def dashboard():
    month = request.args.get('month')
    if month:
        session['selected_month'] = month
    else:
        month = session.get('selected_month', datetime.now().strftime('%Y-%m'))
    compare_month = request.args.get('compare_month', '')
    
    uid = session['user_id']
    spent = database.get_total_spent(uid, month)
    budget = database.get_budget(uid, month)
    cat_data = database.get_category_breakdown(uid, month)
    suggestion = database.get_suggestion(budget, spent, cat_data)
    
    comparison = None
    if compare_month and compare_month != month:
        comparison = database.compare_months(uid, month, compare_month)
        
    return render_template('dashboard.html', month=month, compare_month=compare_month, spent=spent, budget=budget, suggestion=suggestion, cat_data=cat_data, comparison=comparison)

@app.route('/generate_report/<month>')
@login_required
def generate_report(month):
    uid = session['user_id']
    spent = database.get_total_spent(uid, month)
    budget = database.get_budget(uid, month)
    cat_data = database.get_category_breakdown(uid, month)
    expenses = database.get_all_expenses(uid, month)
    user_profile = database.get_user_profile(uid)
    return render_template('report.html', month=month, spent=spent, budget=budget, cat_data=cat_data, expenses=expenses, user=user_profile)

@app.route('/history')
@login_required
def history():
    month = request.args.get('month')
    if month:
        session['selected_month'] = month
    else:
        month = session.get('selected_month', datetime.now().strftime('%Y-%m'))
    expenses = database.get_all_expenses(session['user_id'], month)
    return render_template('history.html', expenses=expenses, month=month)

@app.route('/delete_expense/<int:expense_id>', methods=['POST'])
@login_required
def delete_expense(expense_id):
    database.delete_expense(session['user_id'], expense_id)
    flash('Expense deleted successfully.', 'success')
    return redirect(url_for('history'))

@app.route('/add_expense', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'POST':
        date = request.form['date']
        month = date[:7] # YYYY-MM
        database.add_expense(
            session['user_id'], date, month,
            request.form['vendor'], float(request.form['amount']),
            request.form['category'], request.form['description']
        )
        flash('Expense added manually!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('add_expense.html')

def extract_vendor_name(text):
    """Extract vendor name from OCR text - usually first line or capitalized words"""
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    
    # Try to find vendor name from first few lines (usually has store name)
    for line in lines[:5]:  # Check first 5 lines
        # Skip lines with only numbers
        if any(c.isalpha() for c in line):
            # Remove common words and get meaningful name
            words = line.split()
            vendor_words = []
            for word in words:
                # Keep words that have letters and are meaningful (not just "Amount", "Total", etc)
                if len(word) > 1 and any(c.isalpha() for c in word):
                    word_clean = word.strip('.,!?;:')
                    if word_clean.lower() not in ['amount', 'total', 'price', 'bill', 'receipt', 'date', 'qty', 'quantity']:
                        vendor_words.append(word_clean)
            
            if vendor_words:
                vendor = ' '.join(vendor_words[:3])  # First 3 meaningful words
                if len(vendor) > 2:
                    return vendor
    
    return "Scanned Vendor"

def categorize_expense(text):
    """Categorize expense based on keywords found in scanned text"""
    text_lower = text.lower()
    
    # Category keywords mapping - ordered by priority
    categories = {
        'Medical': ['hospital', 'doctor', 'medical', 'pharmacy', 'medicine', 'clinic', 'health', 'dental', 'dentist', 'pathology', 'diagnostic', 'dr.', 'md', 'physician'],
        'Food': ['restaurant', 'cafe', 'food', 'pizza', 'biryani', 'hotel', 'bakery', 'coffee', 'burger', 'chicken', 'tea', 'lunch', 'dinner', 'breakfast', 'diner', 'eatery', 'mess', 'dhaba'],
        'Transportation': ['petrol', 'fuel', 'gas', 'taxi', 'auto', 'bus', 'metro', 'railway', 'flight', 'parking', 'toll', 'car', 'bike', 'travel'],
        'Groceries': ['grocery', 'supermarket', 'market', 'vegetable', 'fruits', 'milk', 'bread', 'store', 'provisions', 'kirana', 'bazaar'],
        'Entertainment': ['movie', 'cinema', 'theatre', 'concert', 'music', 'game', 'ticket', 'show', 'entertainment', 'multiplexes'],
        'Shopping': ['cloth', 'shirt', 'dress', 'apparel', 'shopping', 'mall', 'store', 'shoe', 'wear', 'garment', 'boutique', 'fashion', 'garments'],
        'Utilities': ['electricity', 'water', 'phone', 'internet', 'bill', 'power', 'broadband', 'telecom', 'utility'],
        'Education': ['book', 'stationery', 'pen', 'school', 'college', 'course', 'class', 'tuition', 'exam', 'studies', 'library'],
        'Fitness': ['gym', 'fitness', 'yoga', 'sports', 'exercise', 'training', 'center', 'wellness'],
    }
    
    # Check each category for keywords
    for category, keywords in categories.items():
        for keyword in keywords:
            if keyword in text_lower:
                return category
    
    # If no specific category found, check vendor name patterns
    if any(word in text_lower for word in ['shop', 'store', 'mall', 'bazaar', 'market']):
        return 'Shopping'
    
    return "Other"

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    month = session.get('selected_month', datetime.now().strftime('%Y-%m'))
    if request.method == 'POST':
        f = request.files.get('receipt')
        if not f or f.filename == '':
            flash('No file selected.', 'danger')
            return redirect(request.url)
        
        fname = uuid.uuid4().hex + '.jpg'
        fpath = os.path.join(app.config['UPLOAD_FOLDER'], fname)
        f.save(fpath)
        
        try:
            img = cv2.imread(fpath, cv2.IMREAD_GRAYSCALE)
            _, img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            text = pytesseract.image_to_string(Image.fromarray(img))
            print(f"OCR Text extracted: {text}")  # Debug logging
        except Exception as e:
            print(f"OCR Error: {e}")  # Debug logging
            text = ""
        
        # If OCR returned nothing or minimal text
        if not text or len(text.strip()) < 5:
            text = "Unknown Vendor\nAmount: 100"
        
        # Extract vendor name from text
        vendor = extract_vendor_name(text)
        
        # Categorize based on keywords
        category = categorize_expense(text)
        
        print(f"Extracted Vendor: {vendor}, Category: {category}")  # Debug logging
        
        # Extract amount - look for currency symbols first
        amount = 0.0
        # First try to find amount with ₹ or $ symbol
        import re
        currency_pattern = r'[₹$]\s*(\d+(?:\.\d{2})?)'
        matches = re.findall(currency_pattern, text)
        if matches:
            # Take the last match (usually final total)
            amount = float(matches[-1])
        else:
            # Fallback: look for any number that resembles amount
            for word in text.split():
                try:
                    val = float(word.replace('$','').replace('₹','').strip())
                    if val > 0 and val < 1000000:  # Reasonable amount range
                        amount = val
                except:
                    pass
        
        month = request.form.get('month', datetime.now().strftime('%Y-%m'))
        session['selected_month'] = month
        date = datetime.now().strftime('%Y-%m-%d')
        database.add_expense(session['user_id'], date, month, vendor, amount, category, "Scanned")
        
        flash(f'Scan successful! {vendor} - ₹{amount} ({category})', 'success')
        return redirect(url_for('dashboard'))
        
    return render_template('upload.html', month=month)

@app.route('/budget_settings', methods=['GET', 'POST'])
@login_required
def budget_settings():
    month = request.args.get('month')
    if month:
        session['selected_month'] = month
    else:
        month = session.get('selected_month', datetime.now().strftime('%Y-%m'))
    if request.method == 'POST':
        month = request.form.get('month', month)
        amount = request.form['budget']
        session['selected_month'] = month
        database.set_budget(session['user_id'], month, float(amount))
        flash(f'Budget setup for {month} updated!', 'success')
        return redirect(url_for('dashboard', month=month))
        
    current_b = database.get_budget(session['user_id'], month)
    spent = database.get_total_spent(session['user_id'], month)
    return render_template('budget_settings.html', month=month, current_budget=current_b, spent=spent)

if __name__ == '__main__':
    database.init_db()
    app.run(debug=True, port=8080)
