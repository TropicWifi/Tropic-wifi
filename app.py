from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import random
import string
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'tropic_wifi_limonade_509_sekre')
DB_NAME = 'tropic_wifi.db'
ADMIN_PIN = '1234'

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS vouchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            plan_name TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            price INTEGER NOT NULL,
            status TEXT DEFAULT 'DISPONIB',
            activated_at TEXT,
            expires_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def generate_code(length=6):
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(random.choice(chars) for _ in range(length))

@app.route('/', methods=['GET', 'POST'])
def captive_portal():
    message = None
    status_type = None
    remaining_time = None

    if request.method == 'POST':
        action = request.form.get('action')
        conn = get_db()
        c = conn.cursor()

        if action == 'free_trial':
            code = 'TEST-' + generate_code(4)
            now = datetime.now()
            exp = now + timedelta(minutes=10)
            c.execute("INSERT INTO vouchers (code, plan_name, duration_minutes, price, status, activated_at, expires_at) VALUES (?, ?, ?, ?, 'AKTIF', ?, ?)",
                      (code, '10 Minit Gratis (Tès)', 10, 0, now.strftime('%Y-%m-%d %H:%M:%S'), exp.strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
            message = f"Byenvini ! Kòd tès ou a se {code}."
            status_type = "success"
            remaining_time = "10 minit"
        else:
            code = request.form.get('code', '').strip().upper()
            c.execute("SELECT * FROM vouchers WHERE code = ?", (code,))
            voucher = c.fetchone()

            if not voucher:
                message = "Kòd sa a pa bon. Tanpri verifye l oswa achte yon kat."
                status_type = "error"
            else:
                v_id = voucher['id']
                plan_name = voucher['plan_name']
                duration = voucher['duration_minutes']
                status = voucher['status']
                expires_at = voucher['expires_at']
                now = datetime.now()

                if status == 'DISPONIB':
                    exp = now + timedelta(minutes=duration)
                    c.execute("UPDATE vouchers SET status = 'AKTIF', activated_at = ?, expires_at = ? WHERE id = ?",
                              (now.strftime('%Y-%m-%d %H:%M:%S'), exp.strftime('%Y-%m-%d %H:%M:%S'), v_id))
                    conn.commit()
                    message = f"Koneksyon reyisi ! Plan : {plan_name}."
                    status_type = "success"
                    remaining_time = f"{duration} minit"
                elif status == 'AKTIF':
                    exp_dt = datetime.strptime(expires_at, '%Y-%m-%d %H:%M:%S')
                    if now < exp_dt:
                        diff = exp_dt - now
                        mins_left = int(diff.total_seconds() // 60)
                        hours_left = mins_left // 60
                        rem_mins = mins_left % 60
                        message = f"Ou deja konekte sou plan {plan_name}."
                        status_type = "success"
                        remaining_time = f"{hours_left}h {rem_mins}m rete" if hours_left > 0 else f"{mins_left} minit rete"
                    else:
                        c.execute("UPDATE vouchers SET status = 'EKSPIRE' WHERE id = ?", (v_id,))
                        conn.commit()
                        message = "Tan kat sa a fini. Achte yon lòt kat."
                        status_type = "error"
                else:
                    message = "Kat sa a ekspire deja."
                    status_type = "error"

        conn.close()

    return render_template('login.html', message=message, status_type=status_type, remaining_time=remaining_time)

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        pin = request.form.get('pin', '').strip()
        if pin == ADMIN_PIN:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_panel'))
        else:
            error = "Kòd sekrè a pa bon !"
    return render_template('admin_login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    c = conn.cursor()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create':
            plan = request.form.get('plan')
            quantity = int(request.form.get('quantity', 1))
            plans = {
                '1_edtan': ('1 Èdtan', 60, 25),
                '24_edtan': ('24 Èdtan (1 Jou)', 1440, 75),
                '7_jou': ('7 Jou (1 Semèn)', 10080, 400),
                '30_jou': ('30 Jou (1 Mwa)', 43200, 1250)
            }
            if plan in plans:
                plan_name, duration, price = plans[plan]
                for _ in range(quantity):
                    code = generate_code()
                    try:
                        c.execute("INSERT INTO vouchers (code, plan_name, duration_minutes, price) VALUES (?, ?, ?, ?)",
                                  (code, plan_name, duration, price))
                    except sqlite3.IntegrityError:
                        pass
                conn.commit()
        elif action == 'delete':
            v_id = request.form.get('v_id')
            c.execute("DELETE FROM vouchers WHERE id = ?", (v_id,))
            conn.commit()

    c.execute("SELECT * FROM vouchers ORDER BY id DESC LIMIT 100")
    vouchers = c.fetchall()

    c.execute("SELECT COALESCE(SUM(price), 0) FROM vouchers WHERE status != 'DISPONIB'")
    total_revenue = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM vouchers WHERE status = 'DISPONIB'")
    available_count = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM vouchers WHERE status = 'AKTIF'")
    active_count = c.fetchone()[0]

    conn.close()
    return render_template('admin.html', vouchers=vouchers, total_revenue=total_revenue,
                           available_count=available_count, active_count=active_count)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
