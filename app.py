from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
from datetime import date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import smtplib
from email.mime.text import MIMEText
import schedule
import threading
import time
import datetime
import os 
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.header import Header
import re
load_dotenv()

EMAIL_SENDER = os.getenv('EMAIL_SENDER')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
SECRET_KEY = os.getenv('SECRET_KEY')

app = Flask(__name__)
app.secret_key = SECRET_KEY
DB = 'reminders.db'

def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            email TEXT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            reminder_date TEXT,
            notes TEXT,
            email_enabled INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    conn.commit()
    conn.close()

def clean_text(text):
    # Removes invalid surrogate characters that break utf-8 encoding
    return re.sub(r'[\ud800-\udfff]', '', text)

def send_email_to_user(receiver_email, subject, body):
    body = clean_text(body)  # ✅ Clean the body of surrogates
    subject = clean_text(subject)  # ✅ Clean subject too

    msg = MIMEText(body, _charset='utf-8')
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = EMAIL_SENDER
    msg['To'] = receiver_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print(f"✅ Email sent to {receiver_email}")
    except Exception as e:
        print(f"❌ Email error for {receiver_email}:", e)



def check_today_reminders():
    today = date.today().isoformat()
    print(f"🕒 Checking reminders for today: {today}")

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("""
        SELECT u.email, r.name, r.notes
        FROM reminders r
        JOIN users u ON r.user_id = u.id
        WHERE r.reminder_date = ? AND r.email_enabled = 1
    """, (today,))

    rows = cur.fetchall()
    conn.close()

    print(f"🔍 Found {len(rows)} reminders for today")

    if not rows:
        print("ℹ️ No reminders with today's date and email_enabled = 1")

    from collections import defaultdict
    user_reminders = defaultdict(list)

    for email, name, notes in rows:
        user_reminders[email].append(f"📌 {name}:\n{notes}")

    for email, reminders in user_reminders.items():
        body = "\n\n".join(reminders)
        print(f"📧 Sending email to {email}")
        send_email_to_user(email, " Today's Application Reminders", body)


def check_tomorrow_reminders():
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT u.email, r.name, r.notes 
        FROM reminders r 
        JOIN users u ON r.user_id = u.id 
        WHERE r.reminder_date = ? AND r.email_enabled = 1
    """, (tomorrow,))
    reminders = cur.fetchall()
    conn.close()
    for email, name, notes in reminders:
        body = f"\ud83d\udccc {name}:\n{notes}"
        send_email_to_user(email, " Tomorrow's Application Reminders", body)

def run_scheduler():
    check_today_reminders()
    check_tomorrow_reminders()
    #schedule.every().day.at("12:53").do(check_today_reminders)
    #schedule.every().day.at("08:00").do(check_tomorrow_reminders)
    print("🔁 Email scheduler running...")
    while True:
        schedule.run_pending()
        time.sleep(60)

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM reminders WHERE user_id = ? ORDER BY reminder_date", (session['user_id'],))
    reminders = cur.fetchall()
    conn.close()
    return render_template('index.html', reminders=reminders, today=str(date.today()))

@app.route('/add', methods=['POST'])
def add():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    name = request.form['name']
    input_str = request.form['reminder_date']
    date_obj = datetime.datetime.strptime(input_str, "%Y-%m-%d")
    date_str = date_obj.date().isoformat()
    notes = request.form['notes']
    email_enabled = 1 if 'email_enabled' in request.form else 0
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT INTO reminders (user_id, name, reminder_date, notes, email_enabled) VALUES (?, ?, ?, ?, ?)",
                (session['user_id'], name, date_str, notes, email_enabled))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
def delete(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM reminders WHERE id = ? AND user_id = ?", (id, session['user_id']))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    if request.method == 'POST':
        name = request.form['name']
        input_str = request.form['reminder_date']
        date_obj = datetime.datetime.strptime(input_str, "%Y-%m-%d")
        reminder_date = date_obj.date().isoformat()
        notes = request.form['notes']
        email_enabled = 1 if 'email_enabled' in request.form else 0

        cur.execute("UPDATE reminders SET name=?, reminder_date=?, notes=?, email_enabled=? WHERE id=? AND user_id=?",
                    (name, reminder_date, notes, email_enabled, id, session['user_id']))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))

    cur.execute("SELECT * FROM reminders WHERE id=? AND user_id=?", (id, session['user_id']))
    reminder = cur.fetchone()
    conn.close()
    return render_template('edit.html', reminder=reminder)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password_raw = request.form.get('password')

        if not (username and email and password_raw):
            return "❌ All fields are required."

        password = generate_password_hash(password_raw)

        try:
            conn = sqlite3.connect(DB)
            cur = conn.cursor()
            cur.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)",
                        (username, password, email))
            conn.commit()
            conn.close()
            print("✅ User saved:", username)
            return redirect(url_for('login'))
        except sqlite3.IntegrityError as e:
            print("❌ DB Error:", e)
            return "❌ Username already exists."

    return render_template('register.html')



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password_input = request.form['password']
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("SELECT id, password FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        conn.close()
        if user and check_password_hash(user[1], password_input):
            session['user_id'] = user[0]
            session['username'] = username
            return redirect(url_for('index'))
        else:
            return "\u274c Invalid credentials"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    message = ''
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("SELECT password FROM users WHERE id = ?", (session['user_id'],))
        user = cur.fetchone()
        if user and check_password_hash(user[0], current_password):
            hashed_new_password = generate_password_hash(new_password)
            cur.execute("UPDATE users SET password = ? WHERE id = ?", (hashed_new_password, session['user_id']))
            conn.commit()
            message = '\u2705 Password changed successfully!'
        else:
            message = '\u274c Current password is incorrect.'
        conn.close()
    return render_template('change_password.html', message=message)

if __name__ == '__main__':
    init_db()
    if not os.path.exists(DB):
        init_db()
        print("✅ Database initialized.")
    else:
        print("📂 Database already exists.")
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        threading.Thread(target=run_scheduler, daemon=True).start()
    app.run(debug=True)