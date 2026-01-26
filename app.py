from flask import Flask, render_template, request, jsonify, session, send_file
from supabase import create_client, Client
import os
import hashlib
import yadisk
from datetime import datetime, timedelta
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Inches
import tempfile

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

YANDEX_DISK_TOKEN = os.environ.get("YANDEX_TOKEN")
YANDEX_DISK_FOLDER = "Филин_отчёты"

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super-secret-key-12345")

def upload_to_yandex_disk(file_path, disk_filename):
    if not YANDEX_DISK_TOKEN:
        print("⚠️ YANDEX_DISK_TOKEN не задан — сохраняю локально")
        os.makedirs("reports", exist_ok=True)
        local_path = os.path.join("reports", disk_filename)
        with open(local_path, "wb") as dst, open(file_path, "rb") as src:
            dst.write(src.read())
        return True

    try:
        client = yadisk.YaDisk(token=YANDEX_DISK_TOKEN)
        if not client.exists(YANDEX_DISK_FOLDER):
            client.mkdir(YANDEX_DISK_FOLDER)
        remote_path = f"{YANDEX_DISK_FOLDER}/{disk_filename}"
        client.upload(file_path, remote_path, overwrite=True)
        print(f"✅ Загружено: {disk_filename}")
        return True
    except Exception as e:
        print("❌ Ошибка Яндекс.Диска:", e)
        return False

@app.route('/wake-up')
def wake_up():
    return jsonify({"status": "awake"})

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'error': 'Логин и пароль обязательны'}), 400

    password_hash = hashlib.sha256(password.encode()).hexdigest()

    try:
        existing = supabase.table("users").select("id").eq("username", username).execute()
        if len(existing.data) > 0:
            return jsonify({'error': 'Логин уже занят'}), 400

        supabase.table("users").insert({
            "username": username,
            "password_hash": password_hash,
            "balance": 10000
        }).execute()

        return jsonify({'success': True})
    except Exception as e:
        print("Register error:", e)
        return jsonify({'error': 'Ошибка регистрации'}), 500

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    password_hash = hashlib.sha256(password.encode()).hexdigest()

    try:
        res = supabase.table("users").select("*").eq("username", username).eq("password_hash", password_hash).execute()
        if len(res.data) == 0:
            return jsonify({'error': 'Неверный логин или пароль'}), 401
        user = res.data[0]
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['balance'] = user['balance']
        return jsonify({'success': True, 'username': user['username'], 'balance': user['balance']})
    except Exception as e:
        print("Login error:", e)
        return jsonify({'error': 'Ошибка входа'}), 500

@app.route('/objects')
def objects_page():
    username = session.get('username')
    balance = session.get('balance', 0)
    return render_template('objects.html', username=username, balance=balance)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return '<script>location="/"</script>'
    return render_template('dashboard.html', username=session['username'], balance=session['balance'])

@app.route('/report')
def report():
    if 'user_id' not in session:
        return '<script>location="/"</script>'
    return render_template('report.html', username=session['username'], balance=session['balance'])

@app.route('/shop')
def shop():
    if 'user_id' not in session:
        return '<script>location="/"</script>'
    return render_template('shop.html', username=session['username'], balance=session['balance'])

@app.route('/cart')
def cart():
    if 'user_id' not in session:
        return '<script>location="/"</script>'
    return render_template('cart.html', username=session['username'], balance=session['balance'])

@app.route('/api/generate_report', methods=['POST'])
def generate_report():
    if 'user_id' not in session:
        return jsonify({'error': 'Не авторизован'}), 401

    date_raw = request.form.get('date', '')
    time_str = request.form.get('time', '')
    address = request.form.get('address', '')
    state = request.form.get('state', '')
    name = request.form.get('name', '').strip() or "Без_названия"

    try:
        d = datetime.strptime(date_raw, '%Y-%m-%d')
        date_formatted = d.strftime('%d.%m.%Y')
    except:
        date_formatted = date_raw or "Без_даты"

    try:
        t = datetime.strptime(time_str, '%H:%M')
        time1 = (t + timedelta(hours=1)).strftime('%H:%M')
    except:
        time1 = time_str or "Без_времени"

    photos = request.files.getlist('photos')
    photo_paths = []
    for i, photo in enumerate(photos):
        if photo.filename:
            path = os.path.join(tempfile.gettempdir(), f"p_{i}.jpg")
            photo.save(path)
            photo_paths.append(path)

    akt_success = False
    try:
        akt = DocxTemplate("akt.docx")
        akt.render({
            'date': date_formatted,
            'time': time_str,
            'time1': time1,
            'address': address,
            'state': state,
            'name': name,
            'photos': [InlineImage(akt, p, width=Inches(5)) for p in photo_paths]
        })
        akt_filename = f"Акт_{name}_{date_formatted}_{time_str.replace(':', '-')}.docx"
        akt_path = os.path.join(tempfile.gettempdir(), akt_filename)
        akt.save(akt_path)

        if upload_to_yandex_disk(akt_path, akt_filename):
            akt_success = True
    except Exception as e:
        print("Акт ошибка:", e)

    proto_success = False
    try:
        proto = DocxTemplate("protokol.docx")
        proto.render({
            'date': date_formatted,
            'time': time_str,
            'time1': time1,
            'address': address,
            'state': state,
            'name': name,
            'photos': [InlineImage(proto, p, width=Inches(5)) for p in photo_paths]
        })
        proto_filename = f"Протокол_{name}_{date_formatted}_{time_str.replace(':', '-')}.docx"
        proto_path = os.path.join(tempfile.gettempdir(), proto_filename)
        proto.save(proto_path)

        if upload_to_yandex_disk(proto_path, proto_filename):
            proto_success = True
    except Exception as e:
        print("Протокол ошибка:", e)

    for p in photo_paths:
        if os.path.exists(p):
            os.remove(p)
    if 'akt_path' in locals() and os.path.exists(akt_path):
        os.remove(akt_path)
    if 'proto_path' in locals() and os.path.exists(proto_path):
        os.remove(proto_path)

    if akt_success or proto_success:
        try:
            new_balance = session['balance'] + 100
            supabase.table("users").update({"balance": new_balance}).eq("id", session['user_id']).execute()
            session['balance'] = new_balance
        except Exception as e:
            print("Balance update error:", e)
            return jsonify({'error': 'Ошибка начисления'}), 500

        return jsonify({
            'success': True,
            'message': 'Документы сохранены на Яндекс.Диск!',
            'new_balance': session['balance']
        })
    else:
        return jsonify({'error': 'Не удалось сохранить документы'}), 500

@app.route('/api/save_cart', methods=['POST'])
def save_cart():
    if 'user_id' not in session:
        return jsonify({'error': 'Не авторизован'}), 401

    data = request.json
    fullname = data.get('fullname', '').strip()
    phone = data.get('phone', '').strip()
    postcode = data.get('postcode', '').strip()
    cart = data.get('cart', [])

    if not fullname or not phone or not postcode or not cart:
        return jsonify({'error': 'Заполните все поля'}), 400

    total = sum(item['price'] for item in cart)
    if session['balance'] < total:
        return jsonify({'error': 'Недостаточно валюты'}), 400

    try:
        new_balance = session['balance'] - total
        supabase.table("users").update({"balance": new_balance}).eq("id", session['user_id']).execute()
        session['balance'] = new_balance

        for item in cart:
            supabase.table("orders").insert({
                "user_id": session['user_id'],
                "product": item['product'],
                "price": item['price'],
                "fullname": fullname,
                "phone": phone,
                "postcode": postcode
            }).execute()

        return jsonify({'success': True, 'new_balance': new_balance})
    except Exception as e:
        print("Cart error:", e)
        return jsonify({'error': 'Ошибка оформления'}), 500

@app.route('/instruction.png')
def view_instruction():
    return send_file("static/png/instruction.png", mimetype='image/png')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
