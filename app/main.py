import os, json, datetime, requests, webbrowser, socket
from flask import Flask, render_template, request, redirect, url_for, jsonify,  send_file, flash
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
import time
import requests
from functools import lru_cache
from functools import wraps
from flask import session
from werkzeug.security import generate_password_hash, check_password_hash
import calendar
from helpers import load_json
from networth_integration_v46 import networth_bp


app = Flask(__name__)

app.secret_key = os.getenv("FLASK_SECRET", "dev_secret")
app.register_blueprint(networth_bp)

def user_data_path(username, filename):
    """Path adaptif (lokal vs Fly.io)"""
    # Path lokal
    local_path = os.path.join(os.path.dirname(__file__), "data")
    # Path Fly.io (mount)
    fly_path = "/app/app/data"

    if os.path.exists(local_path):
        DATA_ROOT = local_path
    elif os.path.exists(fly_path):
        DATA_ROOT = fly_path
    else:
        # fallback terakhir agar tetap bisa jalan di dev
        DATA_ROOT = os.path.abspath("app/data")

    return os.path.join(DATA_ROOT, username, filename)


# --- Custom Jinja Filters ---
@app.template_filter('idr')
def idr(value):
    """Format angka ke dalam format Rupiah"""
    try:
        return f"Rp {float(value):,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "Rp 0"


@app.template_filter('currency_format')
def currency_format(value):
    """Alias untuk idr agar kompatibel dengan template lama"""
    try:
        return f"Rp {float(value):,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "Rp 0"



# ---------- PATHS ----------
# ======== SETUP DATA DIRECTORY (multi-environment safe) ========

def detect_data_dir():
    """Gunakan /data jika benar-benar writable, selain itu fallback ke ./data"""
    fly_data_path = "/data"
    local_data_path = os.path.join(os.path.dirname(__file__), "data")

    try:
        test_path = os.path.join(fly_data_path, ".test_write")
        with open(test_path, "w") as f:
            f.write("test")
        os.remove(test_path)
        return fly_data_path  # ✅ bisa nulis → berarti di Fly.io
    except Exception:
        return local_data_path  # ❌ gak bisa nulis → fallback ke lokal

DATA_DIR = detect_data_dir()
HISTORY_DIR = os.path.join(DATA_DIR, "history")
REPORT_DIR  = os.path.join(DATA_DIR, "reports")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(HISTORY_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

for f in ["income.json", "cashflow.json", "investment.json", "emergency.json"]:
    path = os.path.join(DATA_DIR, f)
    if not os.path.exists(path):
        with open(path, "w") as fp:
            fp.write("[]")

print(f"[INFO] Using data directory: {DATA_DIR}")


def get_all_investment_totals():
    """Ambil total semua investasi dari folder user aktif."""
    path = os.path.join(get_user_dir(), "investment.json")
    if not os.path.exists(path):
        print("DEBUG: investment.json tidak ditemukan di", path)
        return {"crypto": 0, "gold": 0, "land": 0, "business": 0, "stock": 0}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print("Gagal baca investment.json:", e)
        return {"crypto": 0, "gold": 0, "land": 0, "business": 0, "stock": 0}

    totals = {"crypto": 0, "gold": 0, "land": 0, "business": 0, "stock": 0}
    for inv in data:
        cat = inv.get("category")
        amount = float(inv.get("current_value", inv.get("amount_idr", 0)))
        if cat in totals:
            totals[cat] += amount
    print("[DEBUG] Total investasi (history_detail):", totals)
    return totals


# ---------- UTIL ----------


def fmt_idr(x):
    try:
        return "Rp {:,}".format(round(float(x))).replace(",", ".")
    except:
        return "-"

@app.template_filter("idr")
def jfmt(v):
    return fmt_idr(v)

def same_month(date_str, month):
    return date_str.startswith(month)

import calendar  # tambahkan sekali di bagian import atas

def get_monthly_summary():
    """Hitung total income, expense, dan investment per bulan tanpa double counting dan termasuk dana darurat"""
    income = load_json("income.json")
    cashflow = load_json("cashflow.json")

    monthly = {m: {"income": 0, "expense": 0, "investment": 0} for m in range(1, 13)}

    # === INCOME ===
    for i in income:
        try:
            d = datetime.datetime.strptime(i.get("date", ""), "%Y-%m-%d")
            monthly[d.month]["income"] += float(i.get("amount", 0))
        except Exception:
            continue

    # === EXPENSE & INVESTMENT (termasuk dana darurat) ===
    for c in cashflow:
        try:
            d = datetime.datetime.strptime(c.get("date", ""), "%Y-%m-%d")
        except Exception:
            continue

        t = c.get("type")
        cat = c.get("category", "").lower()
        a = float(c.get("amount", 0))

        if t == "expense":
            monthly[d.month]["expense"] += a
        elif t == "investment":
            # semua investasi termasuk dana darurat
            monthly[d.month]["investment"] += a

    # === OUTPUT ===
    labels = [calendar.month_abbr[m] for m in range(1, 13)]
    income_data = [monthly[m]["income"] for m in range(1, 13)]
    expense_data = [monthly[m]["expense"] for m in range(1, 13)]
    invest_data = [monthly[m]["investment"] for m in range(1, 13)]

    return {
        "labels": labels,
        "income": income_data,
        "expense": expense_data,
        "investment": invest_data,
    }




# ---------- UTIL MULTI-USER (v4.6) ----------
def get_user_dir():
    """
    Tentukan folder data aktif berdasarkan user login.
    Jika belum login, gunakan folder global (DATA_DIR) untuk mode single-user.
    """
    user = session.get("username")
    if user:
        user_dir = os.path.join(DATA_DIR, user)
        os.makedirs(user_dir, exist_ok=True)

        # Pastikan subfolder wajib selalu ada
        for sub in ["history", "reports"]:
            os.makedirs(os.path.join(user_dir, sub), exist_ok=True)

        # Simpan jalur history & reports global agar route lain bisa pakai
        global HISTORY_DIR, REPORT_DIR
        HISTORY_DIR = os.path.join(user_dir, "history")
        REPORT_DIR = os.path.join(user_dir, "reports")

        return user_dir
    else:
        # fallback single-user (untuk debugging)
        return DATA_DIR



def load_json(filename):
    """
    Membaca file JSON dari folder user aktif.
    Jika file tidak ditemukan, akan dikembalikan list kosong [].
    """
    user_dir = get_user_dir()
    path = os.path.join(user_dir, filename)

    # fallback ke DATA_DIR lama jika file belum ada di user_dir
    if not os.path.exists(path):
        global_path = os.path.join(DATA_DIR, filename)
        if os.path.exists(global_path):
            path = global_path
        else:
            return []

    try:
        with open(path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"[WARN] JSON rusak: {path}")
        return []
    except Exception as e:
        print(f"[ERROR] load_json({filename}):", e)
        return []


def save_json(filename, data):
    """
    Menulis file JSON ke folder user aktif.
    Semua struktur folder otomatis dibuat jika belum ada.
    """
    user_dir = get_user_dir()
    path = os.path.join(user_dir, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        # debug info
        print(f"[SAVE] {filename} → {path}")
    except Exception as e:
        print(f"[ERROR] save_json({filename}):", e)


        
# ---------- USER MANAGEMENT ----------
USER_FILE = os.path.join(DATA_DIR, "users.json")

def load_users():
    if not os.path.exists(USER_FILE):
        return []
    with open(USER_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    os.makedirs(os.path.dirname(USER_FILE), exist_ok=True)
    with open(USER_FILE, "w") as f:
        json.dump(users, f, indent=4)

def init_admin():
    """Buat akun admin default jika users.json kosong"""
    users = load_users()
    if not users:
        default_pass = "bukabox2025"
        users = [{
            "username": "admin",
            "password_hash": generate_password_hash(default_pass)
        }]
        save_users(users)
        print(f"[INIT] Admin user created. Username: admin | Password: {default_pass}")
    else:
        print("[INIT] Admin user already exists")
    return users

init_admin()

       
# ---------- API FETCH ----------
# ==========================================================
# ===   CACHED API FETCH (15 MINUTES LIMIT)               ===
# ==========================================================

# ----- CRYPTO -----
@lru_cache(maxsize=1)
def _cached_crypto_prices(ts: int):
    """Cache daftar harga crypto IDR maksimal 1x tiap 15 menit"""
    try:
        ids = "bitcoin,ethereum,cardano,solana,polkadot,velo,sui,ethena,xrp,nervos-network,binancecoin,gatechain-token"
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=idr"
        r = requests.get(url, timeout=10).json()
        return {
            "BTC": r.get("bitcoin", {}).get("idr", 0),
            "ETH": r.get("ethereum", {}).get("idr", 0),
            "ADA": r.get("cardano", {}).get("idr", 0),
            "SOL": r.get("solana", {}).get("idr", 0),
            "DOT": r.get("polkadot", {}).get("idr", 0),
            "VELO": r.get("velo", {}).get("idr", 0),
            "SUI": r.get("sui", {}).get("idr", 0),
            "ENA": r.get("ethena", {}).get("idr", 0),
            "XRP": r.get("xrp", {}).get("idr", 0),
            "CKB": r.get("nervos-network", {}).get("idr", 0),
            "BNB": r.get("binancecoin", {}).get("idr", 0),
            "GT":  r.get("gatechain-token", {}).get("idr", 0),
        }
    except Exception as e:
        print("Crypto API Error:", e)
        return {}

def get_crypto_prices():
    """Ambil daftar harga crypto IDR (cache 15 menit)"""
    ts = int(time.time() // (15 * 60))
    return _cached_crypto_prices(ts)


def get_crypto_price(symbol: str):
    """Ambil harga 1 coin tertentu IDR (pakai cache get_crypto_prices)"""
    symbol = symbol.upper()
    data = get_crypto_prices()
    return data.get(symbol, 0)


# ----- GOLD -----
@lru_cache(maxsize=1)
def _cached_gold_price(ts: int):
    """Fallback harga emas via metals-api.com"""
    try:
        # ambil harga gold dari metals-api mirror
        data = requests.get("https://metals-api.stream/api/v1/latest/XAU", timeout=10).json()
        usd_per_ounce = float(data["price"])
        usd_idr = 16000
        per_gram = (usd_per_ounce * usd_idr) / 31.1035
        return round(per_gram, 0)
    except Exception as e:
        print("Gold API fallback error:", e)
        return 0


def get_gold_price():
    """Wrapper dengan blok waktu 15 menit agar tidak kena rate-limit"""
    ts = int(time.time() // (15 * 60))
    return _cached_gold_price(ts)


# ----- STOCK -----
@lru_cache(maxsize=10)
def _cached_stock_price(symbol: str, ts: int):
    """Cache harga saham IDR via Yahoo Finance maksimal 1x tiap 15 menit per simbol"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.JK"
        r = requests.get(url, timeout=5).json()
        price = r["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return price
    except Exception as e:
        print(f"Stock API Error ({symbol}):", e)
        return 0

def get_stock_price(symbol: str):
    """Harga saham IDR via Yahoo Finance (cache 15 menit per simbol)"""
    ts = int(time.time() // (15 * 60))
    return _cached_stock_price(symbol.upper(), ts)

def rollover_buffer():
    """Tutup bulan berjalan: simpan laporan ke history dan reset income/expense."""
    today = datetime.date.today()
    month_tag = today.strftime("%Y-%m")

    # --- Hitung saldo buffer akhir bulan ini ---
    income = load_json("income.json")
    expense = load_json("expense.json")

    total_income = sum(x.get("amount", 0) for x in income)
    total_expense = sum(x.get("amount", 0) for x in expense)
    closing_buffer = total_income - total_expense

    # --- Siapkan data detail untuk laporan bulanan ---
    history_detail = load_json("history_detail.json")
    history_detail.append({
        "month": month_tag,
        "date_closed": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "income": income,
        "expense": expense,
        "summary": {
            "total_income": total_income,
            "total_expense": total_expense,
            "closing_buffer": closing_buffer
        }
    })
    save_json("history_detail.json", history_detail)

    # --- Simpan snapshot buffer di history ringkas ---
    buffer_history = load_json("buffer_history.json")
    buffer_history.append({
        "month": month_tag,
        "closing_buffer": closing_buffer,
        "timestamp": datetime.datetime.now().isoformat()
    })
    save_json("buffer_history.json", buffer_history)

    # --- Reset file income & expense untuk bulan baru ---
    save_json("income.json", [])
    save_json("expense.json", [])

    # --- Tambahkan saldo awal bulan baru ke buffer.json ---
    save_json("buffer.json", [{
        "date": today.isoformat(),
        "type": "income",
        "category": "Saldo Awal",
        "amount": closing_buffer,
        "note": f"Carry over from {month_tag}"
    }])

    print(f"[ROLLOVER] Bulan {month_tag} ditutup → Buffer: {closing_buffer:,.0f} IDR")


# ---------- LOGIN PROTECTION ----------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Silakan login untuk mengedit data.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


# ---------- GLOBAL ACCESS PROTECTION (v4.5) ----------
@app.before_request
def restrict_access():
    """
    Middleware untuk membatasi akses hanya bagi user yang sudah login.
    Hanya route login, register, logout, dan file static yang boleh diakses bebas.
    """
    open_endpoints = {"login", "register", "logout", "static"}
    endpoint = request.endpoint or ""

    # Jika bukan endpoint publik dan belum login → redirect ke login
    if not session.get("logged_in") and endpoint not in open_endpoints:
        if request.path not in [url_for("login"), url_for("register")]:
            return redirect(url_for("login"))


# ---------- ROUTES ----------
@app.route("/")
def index():
    today = datetime.date.today()
    month_now = today.strftime("%Y-%m")

    # === LOAD DATA ===
    income = load_json("income.json")
    cashflow = load_json("cashflow.json")
    investment = load_json("investment.json")
    emergency = load_json("emergency.json")
    investment_reduce = load_json("investment_reduce.json")
    networth = load_json("networth.json")

    crypto = get_crypto_prices()
    gold = get_gold_price()

    # === FILTER BULAN AKTIF ===
    month_income = [i for i in income if same_month(i.get("date", ""), month_now)]
    month_cashflow = [c for c in cashflow if same_month(c.get("date", ""), month_now)]

    # === HITUNG TOTAL ===
    total_income = sum(float(i.get("amount", 0)) for i in month_income)
    total_expense = sum(float(c.get("amount", 0)) for c in month_cashflow if c.get("type") == "expense")
    total_investment_savings = sum(float(c.get("amount", 0)) for c in month_cashflow if c.get("type") == "investment")

    # === BUFFER (saldo tersisa nyata) ===
    buffer_balance = total_income - (total_expense + total_investment_savings)
    buffer_state = "positive" if buffer_balance >= 0 else "negative"

    # === PORTFOLIO VALUE ===
    inv_crypto = sum(x.get("current_value", x.get("amount_idr", 0)) for x in investment if x.get("category") == "crypto")
    inv_gold = sum(x.get("current_value", x.get("amount_idr", 0)) for x in investment if x.get("category") == "gold")
    inv_land = sum(x.get("current_value", x.get("amount_idr", 0)) for x in investment if x.get("category") == "land")
    inv_business = sum(x.get("current_value", x.get("amount_idr", 0)) for x in investment if x.get("category") == "business")
    inv_stock = sum(x.get("current_value", x.get("amount_idr", 0)) for x in investment if x.get("category") == "stock")
    total_port = inv_crypto + inv_gold + inv_land + inv_business + inv_stock

    # === EMERGENCY FUND ===
    total_emergency = sum(e.get("amount", 0) for e in emergency)
    target1, target2 = 120_000_000, 240_000_000
    progress1 = min(100, (total_emergency / target1) * 100) if target1 else 0
    progress2 = min(100, (total_emergency / target2) * 100) if target2 else 0

    # === CRYPTO ACCUMULATION ===
    tokens = {}
    for inv in investment:
        if inv.get("category") != "crypto":
            continue

        sym = inv.get("asset", "").upper().strip()
        note = (inv.get("note") or "").strip().lower()

        if sym == "BTC" and note == "operasional":
            key = "BTC Operasional"
        elif sym == "BTC" and note == "anak":
            key = "BTC Anak"
        else:
            key = sym

        curr_price = crypto.get(sym, 0)
        entry_amount = float(inv.get("entry_amount", 0))
        amount_idr = float(inv.get("amount_idr", inv.get("amount", 0)))
        now_value = curr_price * entry_amount

        if key not in tokens:
            tokens[key] = {
                "symbol": key,
                "total_amount": amount_idr,
                "total_coin": entry_amount,
                "curr": curr_price,
                "current_value": now_value,
            }
        else:
            tokens[key]["total_amount"] += amount_idr
            tokens[key]["total_coin"] += entry_amount
            tokens[key]["current_value"] += now_value

    crypto_accumulation = []
    for sym, t in tokens.items():
        avg_price = (t["total_amount"] / t["total_coin"]) if t["total_coin"] else 0
        pnl = ((t["current_value"] - t["total_amount"]) / t["total_amount"] * 100) if t["total_amount"] else 0
        crypto_accumulation.append({
            "token": sym,
            "total_modal": t["total_amount"],
            "total_koin": t["total_coin"],
            "avg_price": avg_price,
            "current_value": t["current_value"],
            "pnl": pnl
        })

    # === MONTHLY HISTORY ===
    monthly_data = get_monthly_summary()
    liabilities_path = os.path.join(get_user_dir(), "liabilities.json")
    liabilities = load_json(liabilities_path) if os.path.exists(liabilities_path) else []

    # === RENDER TEMPLATE ===
    return render_template(
        "index.html",
        today=today.isoformat(),
        income=income,
        cashflow=month_cashflow,
        investment=investment,
        emergency=emergency,
        total_income=total_income,
        total_expense=total_expense,
        total_invest_month=total_investment_savings,
        total_port=total_port,
        inv_crypto=inv_crypto,
        inv_gold=inv_gold,
        inv_land=inv_land,
        inv_business=inv_business,
        crypto=crypto,
        gold=gold,
        total_emergency=total_emergency,
        progress1=progress1,
        progress2=progress2,
        target1=target1,
        target2=target2,
        buffer_balance=buffer_balance,
        buffer_state=buffer_state,
        crypto_accumulation=crypto_accumulation,
        investment_reduce=investment_reduce,
        monthly=monthly_data,
        total_expense_operasional=total_expense,
        total_investment_savings=total_investment_savings,
        networth=networth,
        liabilities=liabilities
    )

    
@app.route("/investment")
def investment_panel():
    today = datetime.date.today()

    investment = load_json("investment.json")
    investment_reduce = load_json("investment_reduce.json")
    emergency = load_json("emergency.json")  # 🟩 tambahan

    # ambil harga-harga realtime
    crypto = get_crypto_prices()
    gold_price = get_gold_price()
    print("DEBUG GOLD PRICE =", gold_price)

    # --- total per kategori investasi utama ---
    inv_crypto = sum(x.get("current_value", x.get("amount_idr", 0))
                     for x in investment if x.get("category") == "crypto")
    inv_gold = sum(x.get("current_value", x.get("amount_idr", 0))
                   for x in investment if x.get("category") == "gold")
    inv_land = sum(x.get("current_value", x.get("amount_idr", 0))
                   for x in investment if x.get("category") == "land")
    inv_business = sum(x.get("current_value", x.get("amount_idr", 0))
                       for x in investment if x.get("category") == "business")
    inv_stock = sum(x.get("current_value", x.get("amount_idr", 0))
                    for x in investment if x.get("category") == "stock")

    # 🟩 total dana darurat
    total_emergency = sum(e.get("amount", 0) for e in emergency)

    # 🟩 total portofolio + dana darurat
    total_port = inv_crypto + inv_gold + inv_land + inv_business + inv_stock
    total_assets = total_port + total_emergency

    # === CRYPTO ACCUMULATION (pisah anak & operasional) ===
    tokens = {}
    for inv in investment:
        if inv.get("category") != "crypto":
            continue

        sym = inv.get("asset", "").upper().strip()
        note = (inv.get("note") or "").strip().lower()

        # label unik BTC
        if sym == "BTC" and note == "operasional":
            key = "BTC Operasional"
        elif sym == "BTC" and note == "anak":
            key = "BTC Anak"
        else:
            key = sym

        curr_price = crypto.get(sym, 0)
        entry_amount = float(inv.get("entry_amount", 0))
        amount_idr = float(inv.get("amount_idr", 0))
        now_value = curr_price * entry_amount

        if key not in tokens:
            tokens[key] = {
                "symbol": sym,
                "label": key,
                "note": note,
                "total_modal": amount_idr,
                "total_koin": entry_amount,
                "curr": curr_price,
                "current_value": now_value,
            }
        else:
            tokens[key]["total_modal"] += amount_idr
            tokens[key]["total_koin"] += entry_amount
            tokens[key]["current_value"] += now_value

    crypto_accumulation = []
    for key, t in tokens.items():
        avg_price = (t["total_modal"] / t["total_koin"]) if t["total_koin"] else 0
        pnl = ((t["current_value"] - t["total_modal"]) / t["total_modal"] * 100) if t["total_modal"] else 0
        crypto_accumulation.append({
            "token": t["label"],
            "symbol": t["symbol"],
            "note": t["note"],
            "total_modal": round(t["total_modal"], 2),
            "total_koin": round(t["total_koin"], 8),
            "avg_price": round(avg_price, 2),
            "current_value": round(t["current_value"], 2),
            "pnl": round(pnl, 2)
        })

    # urutkan data terbaru
    investment = sorted(
        investment,
        key=lambda x: (x.get("timestamp", ""), x.get("date", "")),
        reverse=True
    )

    print(f"DEBUG INVESTMENT LEN = {len(investment)}")
    if len(investment) > 0:
        print("SAMPLE ITEM:", investment[0])

    # 🟩 Buat dictionary alokasi chart (termasuk dana darurat)
    asset_allocation = {
        "Crypto": inv_crypto,
        "Gold": inv_gold,
        "Land": inv_land,
        "Business": inv_business,
        "Stock": inv_stock,
        "Emergency Fund": total_emergency
    }

    # --- kirim ke template ---
    return render_template(
        "investment.html",
        today=today.isoformat(),
        investment=investment,
        investment_reduce=investment_reduce,
        crypto=crypto,
        gold=gold_price,
        inv_crypto=inv_crypto,
        inv_gold=inv_gold,
        inv_land=inv_land,
        inv_business=inv_business,
        inv_stock=inv_stock,
        total_port=total_port,
        total_assets=total_assets,        # 🟩 total keseluruhan investasi+dana darurat
        asset_allocation=asset_allocation, # 🟩 data pie chart gabungan
        total_emergency=total_emergency,   # 🟩 dana darurat dikirim eksplisit juga
        crypto_accumulation=crypto_accumulation,
    )



# ---------- INPUT ROUTES ----------
@app.route("/add_income", methods=["POST"])
@login_required
def add_income():
    """Tambah pendapatan baru dan sinkronkan ke cashflow"""
    date = request.form.get("date", "")
    stream = request.form.get("stream", "")
    note = request.form.get("note", "")
    try:
        amount = float(request.form.get("amount", "0").replace(".", "").replace(",", ""))
    except:
        amount = 0

    # Simpan ke income.json
    income = load_json("income.json")
    income.append({
        "date": date,
        "stream": stream,
        "amount": amount,
        "note": note
    })
    save_json("income.json", income)

    # 🟩 Tambahkan juga ke cashflow.json agar history sinkron
    cash = load_json("cashflow.json")
    if not isinstance(cash, list):
        cash = []

    cash.append({
        "date": date,
        "type": "income",
        "category": stream,
        "amount": amount,
        "note": note
    })
    save_json("cashflow.json", cash)

    flash(f"Pendapatan {stream} sebesar {fmt_idr(amount)} ditambahkan.", "success")
    return redirect(url_for("index"))


@app.route("/add_expense", methods=["POST"])
@login_required
def add_expense():
    """Tambah pengeluaran baru (termasuk otomatis update pelunasan loan & Net Worth)."""
    try:
        expense = load_json("expense.json")
        cash = load_json("cashflow.json")

        date = request.form.get("date", "")
        category = request.form.get("category", "").strip().title()
        note = request.form.get("note", "").strip()
        raw_amount = request.form.get("amount", "0")

        try:
            amount = float(raw_amount.replace(".", "").replace(",", ""))
        except:
            amount = 0

        if amount <= 0:
            flash("Nominal tidak valid.", "warning")
            return redirect(url_for("index"))

        # === Simpan ke expense.json ===
        expense.append({
            "date": date,
            "category": category,
            "amount": amount,
            "note": note
        })
        save_json("expense.json", expense)

        # === Catat ke cashflow.json ===
        cash.append({
            "date": date,
            "type": "expense",
            "category": category,
            "amount": amount,
            "note": note
        })
        save_json("cashflow.json", cash)

        # === 1️⃣ Jika kategori Loan → kurangi liabilitas aktif ===
        if category.lower() == "loan":
            try:
                liabilities_path = os.path.join(get_user_dir(), "liabilities.json")
                liabilities = load_json(liabilities_path)

                for l in liabilities:
                    l_id = l.get("id", "")
                    if l_id == note or l.get("note", "") == note:
                        paid = float(l.get("paid", 0)) + amount
                        total = float(l.get("amount", 0))
                        l["paid"] = paid
                        l["remaining"] = max(total - paid, 0)
                        l["progress"] = round((paid / total) * 100, 1) if total > 0 else 0
                        break

                save_json(liabilities_path, liabilities)
                print(f"[LOAN PAYMENT] Pembayaran {note} sebesar Rp{amount:,.0f} dicatat.")
            except Exception as e:
                print("[LOAN UPDATE ERROR]", e)

        # === 2️⃣ Update Net Worth real-time ===
        try:
            from networth_integration_v46 import calculate_networth
            summary = calculate_networth()
            save_json("networth.json", summary)
        except Exception as e:
            print("[NETWORTH UPDATE ERROR]", e)

        # === 3️⃣ Simpan juga ke snapshot bulan aktif ===
        try:
            today = datetime.date.today()
            month_label = today.strftime("%Y-%m")
            user_dir = get_user_dir()
            history_dir = os.path.join(user_dir, "history")
            os.makedirs(history_dir, exist_ok=True)
            snapshot_path = os.path.join(history_dir, f"{month_label}.json")

            if os.path.exists(snapshot_path):
                with open(snapshot_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {"month": month_label, "summary": {}, "entries": {}}

            # Tambahkan transaksi baru ke entries.expense
            data.setdefault("entries", {}).setdefault("expense", []).append({
                "date": date,
                "category": category,
                "note": note,
                "amount": amount
            })

            # Perbarui summary networth
            data["summary"]["networth"] = summary

            with open(snapshot_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            print(f"[SNAPSHOT] Net Worth bulan {month_label} diperbarui setelah pengeluaran.")
        except Exception as e:
            print("[EXPENSE SNAPSHOT UPDATE ERROR]", e)

        flash(f"Pengeluaran {category} sebesar {fmt_idr(amount)} ditambahkan.", "success")
        return redirect(url_for("index"))

    except Exception as e:
        print("[ADD_EXPENSE ERROR]", e)
        flash(f"Gagal menambahkan pengeluaran: {e}", "danger")
        return redirect(url_for("index"))



@app.route("/add_cashflow", methods=["POST"])
@login_required
def add_cashflow():
    data = load_json("cashflow.json")
    data.append({
        "date": request.form["date"],
        "type": request.form["type"],
        "category": request.form["category"],
        "amount": float(request.form["amount"].replace(".", "")),
        "note": request.form.get("note", ""),
    })
    save_json("cashflow.json", data)
    return redirect(url_for("index"))
def add_invest_record(category, payload):
    """Tambahkan data investasi ke investment.json tanpa menambah ke cashflow"""
    investment = load_json("investment.json")
    investment.append(payload)
    save_json("investment.json", investment)


@app.route("/add_invest", methods=["POST"])
@login_required
def add_invest():
    data = load_json("investment.json")
    cat = request.form["category"]
    date = request.form.get("date", datetime.date.today().isoformat())

    if cat == "land":
        luas_ubin = float(request.form.get("luas_ubin", 0))
        price_per_ubin = float(request.form.get("entry_price", 0))
        payload = {
            "category": "land",
            "date": date,
            "luas_ubin": luas_ubin,
            "luas_m2": round(luas_ubin * 14, 2),
            "price_per_ubin": price_per_ubin,
            "amount_idr": luas_ubin * price_per_ubin,
            "note": request.form.get("note", ""),
        }
        add_invest_record("land", payload)

    elif cat == "business":
        entry_amount = float(request.form.get("entry_amount", 0))
        payload = {
            "category": "business",
            "date": date,
            "asset": request.form.get("asset", ""),
            "sector": request.form.get("sector", ""),
            "entry_amount": entry_amount,
            "amount_idr": entry_amount,
            "note": request.form.get("note", ""),
        }
        add_invest_record("business", payload)

    else:
        entry_price = float(request.form.get("entry_price", 0))
        entry_amount = float(request.form.get("entry_amount", 0))
        payload = {
            "category": cat,
            "date": date,
            "asset": request.form.get("asset", ""),
            "entry_price": entry_price,
            "entry_amount": entry_amount,
            "amount_idr": entry_price * entry_amount,
            "note": request.form.get("note", ""),
            "timestamp": datetime.datetime.now().isoformat()
        }
        add_invest_record(cat, payload)

    # 🟩 catat ke cashflow agar muncul di summary
    cash = load_json("cashflow.json")
    if not isinstance(cash, list):
        cash = []
    cash.append({
        "date": date,
        "type": "investment",
        "category": f"Investment {cat.capitalize()}",
        "amount": float(payload.get("amount_idr", 0)),
        "note": payload.get("note", "")
    })
    save_json("cashflow.json", cash)

    return redirect(url_for("investment_panel"))


@app.route("/upload_investment_json", methods=["POST"])
def upload_investment_json():
    username = session.get("username", "ichi")
    file = request.files.get("file")

    if not file or not file.filename.endswith(".json"):
        flash("Upload file JSON valid dulu.", "danger")
        return redirect(url_for("investment_panel"))

    filepath = user_data_path(username, "investment.json")
    print("=== DEBUG UPLOAD ===")
    print("Saving to:", filepath)

    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    try:
        file.seek(0)
        new_data = json.load(file)
        print("Loaded data type:", type(new_data))
        if isinstance(new_data, list):
            print("List length:", len(new_data))
        else:
            print("Top-level keys:", list(new_data.keys()))

    except Exception as e:
        print("Error loading JSON:", e)
        flash(f"Gagal membaca file JSON: {e}", "danger")
        return redirect(url_for("investment_panel"))

    # Tulis langsung untuk uji pertama
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(new_data, f, indent=2)

    flash("Data berhasil disimpan ke investment.json (tes awal)", "success")


    print("=== DEBUG PATH ===")
    print("Local exists:", os.path.exists(os.path.join(os.path.dirname(__file__), "data")))
    print("Fly exists:", os.path.exists("/app/app/data"))
    print("Final path:", user_data_path("ichi", "investment.json"))
    return redirect(url_for("investment_panel"))

# ---- CRYPTO ----
@app.route("/add_crypto", methods=["POST"])
@login_required
def add_crypto():
    data = load_json("investment.json")

    asset = request.form.get("asset", "").upper()
    date = request.form.get("date", datetime.date.today().isoformat())
    entry_price = float(request.form.get("entry_price", 0))
    entry_amount = float(request.form.get("entry_amount", 0))
    amount_idr = float(request.form.get("amount_idr", 0))
    note = (request.form.get("note") or "").strip()

    payload = {
        "category": "crypto",
        "asset": asset,
        "date": date,
        "entry_price": entry_price,
        "entry_amount": entry_amount,
        "amount_idr": amount_idr if amount_idr > 0 else entry_price * entry_amount,
        "note": note,
        "timestamp": datetime.datetime.now().isoformat()
    }

    data.append(payload)
    save_json("investment.json", data)

    return redirect(url_for("index"))



# ---- GOLD ----
@app.route("/add_gold", methods=["POST"])
@login_required
def add_gold():
    date = request.form["date"]
    entry_price = float(request.form["entry_price"])
    amount_idr = float(request.form["amount_idr"])
    gram = amount_idr / entry_price if entry_price else 0

    price_now = get_gold_price()
    current_value = gram * price_now
    pnl = ((current_value - amount_idr) / amount_idr * 100) if amount_idr else 0

    payload = {
        "category": "gold", "asset": "Gold", "date": date,
        "entry_price": entry_price, "amount_idr": amount_idr,
        "entry_amount": gram, "current_value": current_value,
        "pnl": round(pnl,2)
    }
    add_invest_record("gold", payload)
    return redirect(url_for("index"))


# ---- STOCK ----
@app.route("/add_stock", methods=["POST"])
@login_required
def add_stock():
    sym = request.form["asset"]
    date = request.form["date"]
    entry_price = float(request.form["entry_price"])
    amount_idr = float(request.form["amount_idr"])
    lot = amount_idr / (entry_price * 100) if entry_price else 0

    price_now = get_stock_price(sym)
    current_value = lot * price_now * 100
    pnl = ((current_value - amount_idr) / amount_idr * 100) if amount_idr else 0

    payload = {
        "category": "stock", "asset": sym.upper(), "date": date,
        "entry_price": entry_price, "amount_idr": amount_idr,
        "entry_amount": lot, "current_value": current_value,
        "pnl": round(pnl,2)
    }
    add_invest_record("stock", payload)
    return redirect(url_for("index"))

@app.route("/add_land", methods=["POST"])
@login_required
def add_land():
    data = load_json("investment.json")
    luas_ubin = float(request.form.get("luas_ubin", 0))
    price_per_ubin = float(request.form.get("price_per_ubin", 0))
    luas_m2 = round(luas_ubin * 14, 2)
    total = luas_ubin * price_per_ubin
    data.append({
        "category": "land",
        "type": request.form.get("type", "Tanah"),
        "date": request.form.get("date", ""),
        "luas_ubin": luas_ubin,
        "luas_m2": luas_m2,
        "price_per_ubin": price_per_ubin,
        "amount_idr": total,
        "note": request.form.get("note", "")
    })
    save_json("investment.json", data)
    return redirect(url_for("index"))

@app.route("/add_business", methods=["POST"])
@login_required
def add_business():
    data = load_json("investment.json")
    nama_bisnis = request.form.get("asset", "")
    sektor = request.form.get("sector", "")
    date = request.form.get("date", "")
    unit_value = float(request.form.get("unit_value", 0))
    modal = float(request.form.get("entry_amount", 0))
    note = request.form.get("note", "")

    data.append({
        "category": "business",
        "asset": nama_bisnis,
        "sector": sektor,
        "date": date,
        "unit_value": unit_value,
        "entry_amount": modal,
        "amount_idr": modal,
        "note": note
    })

    save_json("investment.json", data)
    return redirect(url_for("index"))


# ---------- ADD EMERGENCY FUND ----------
@app.route("/add_emergency", methods=["POST"])
@login_required
def add_emergency():
    data = load_json("emergency.json")
    if not isinstance(data, list):
        data = []

    entry = {
        "date": request.form["date"],
        "amount": float(request.form["amount"].replace(".", "")),
        "note": request.form.get("note", "")
    }
    data.append(entry)
    save_json("emergency.json", data)

    # catat ke cashflow juga
    cash = load_json("cashflow.json")
    if not isinstance(cash, list):        # ⬅️ tambahkan ini
        cash = []

    cash.append({
        "date": request.form["date"],
        "type": "investment",
        "category": "Dana Darurat",
        "amount": float(request.form["amount"].replace(".", "")),
        "note": request.form.get("note", "")
    })
    save_json("cashflow.json", cash)

    return redirect(url_for("index"))


@app.route("/reduce_emergency", methods=["POST"])
@login_required
def reduce_emergency():
    data = load_json("emergency.json")
    date = request.form.get("date") or datetime.date.today().isoformat()
    amount = float(request.form.get("amount", 0))
    note = request.form.get("note", "")

    # Tambahkan log pengeluaran di emergency fund
    data.append({
        "date": date,
        "amount": -amount,
        "note": f"[KELUAR] {note}"
    })
    save_json("emergency.json", data)

    # Tambahkan otomatis ke cashflow.json
    cash = load_json("cashflow.json")
    cash.append({
        "date": date,
        "type": "expense",
        "category": "Emergency Fund",
        "amount": amount,
        "note": note
    })
    cash.sort(key=lambda x: x.get("date", ""), reverse=True)
    save_json("cashflow.json", cash)

    print(f"[Emergency] Pengeluaran Rp {amount:,.0f} tercatat di dana darurat & cashflow")
    return redirect(url_for("index"))



# ---------- CANCEL LAST ----------
@app.route("/cancel_last/<kind>", methods=["POST"])
@login_required
def cancel_last(kind):
    name = {"income": "income.json", "cashflow": "cashflow.json", "investment": "investment.json", "emergency": "emergency.json"}.get(kind)
    if not name: return redirect(url_for("index"))
    data = load_json(name)
    if data:
        data.pop()
        save_json(name, data)
    return redirect(url_for("index"))


# ---------- HISTORY ----------
@app.route("/rekap")
def rekap_redirect():
    return redirect(url_for("history_panel"))

@app.route("/history")
def history_panel():
    history_dir = os.path.join(get_user_dir(), "history")
    files = sorted([f for f in os.listdir(history_dir) if f.endswith(".json")], reverse=True)
    histories = []

    for fname in files:
        month = fname.replace(".json", "")
        path = os.path.join(history_dir, fname)
        with open(path, encoding="utf-8") as f:
            _ = json.load(f)  # isi file hanya dipakai ambil bulan

        cashflow = load_json("cashflow.json")

        # Ambil data cashflow bulan ini
        income_total = sum(
            float(c.get("amount", 0))
            for c in cashflow if c.get("type") == "income" and c.get("date", "").startswith(month)
        )
        expense_total = sum(
            float(c.get("amount", 0))
            for c in cashflow if c.get("type") == "expense" and c.get("date", "").startswith(month)
        )
        invest_total = sum(
            float(c.get("amount", 0))
            for c in cashflow if c.get("type") == "investment" and c.get("date", "").startswith(month)
        )

        buffer_real = income_total - (expense_total + invest_total)

        histories.append({
            "month": month,
            "total_income": income_total,
            "total_expense": expense_total,
            "total_investment": invest_total,
            "buffer": buffer_real
        })

    monthly_data = get_monthly_summary()
    return render_template("history.html", histories=histories, monthly=monthly_data)




@app.route("/history/snapshot")
@login_required
def save_month_snapshot():
    """
    Simpan snapshot bulanan yang konsisten dan sinkron:
    - Income diambil dari income.json
    - Expense & Investment dari cashflow.json
    - Investment mencakup Dana Darurat dan aset lain
    - Struktur investment disesuaikan agar tampil lengkap di tabel history_detail
    """
    today = datetime.date.today()
    month_label = today.strftime("%Y-%m")

    # === Ambil data utama ===
    income = load_json("income.json")
    cashflow = load_json("cashflow.json")

    # --- Filter berdasarkan bulan aktif ---
    def same_month(date_str):
        if not date_str:
            return False
        try:
            d = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            return d.strftime("%Y-%m") == month_label
        except Exception:
            return False

    # --- Ambil data bulan ini ---
    month_income = [i for i in income if same_month(i.get("date", ""))]
    month_expense = [c for c in cashflow if c.get("type") == "expense" and same_month(c.get("date", ""))]
    month_investment = [c for c in cashflow if c.get("type") == "investment" and same_month(c.get("date", ""))]

    # --- Konversi struktur investment agar tampil rapi di tabel ---
    month_investment_fixed = []
    for c in month_investment:
        category = c.get("category", "")
        # bersihkan prefix "Investment " biar tampil seperti "Crypto", "Dana Darurat", dll.
        asset_name = category.replace("Investment", "").strip() or "Dana Darurat"
        month_investment_fixed.append({
            "category": category,
            "asset": asset_name,
            "date": c.get("date", ""),
            "amount_idr": float(c.get("amount", 0)),
            "note": c.get("note", "")
        })

    # --- Hitung total ---
    total_income = sum(float(i.get("amount", 0)) for i in month_income)
    total_expense = sum(float(c.get("amount", 0)) for c in month_expense)
    total_investment = sum(float(c.get("amount", 0)) for c in month_investment)
    buffer_balance = total_income - (total_expense + total_investment)

        # --- Ambil referensi dari investment.json untuk melengkapi asset ---
    invest_full = load_json("investment.json")

    month_investment_fixed = []
    for c in month_investment:
        category = c.get("category", "")
        note = (c.get("note") or "").strip().lower()

        # Default asset name dari kategori
        asset_name = category.replace("Investment", "").strip() or "Dana Darurat"

        # Jika kategori adalah Investment Crypto, coba cocokkan dengan investment.json
        if "crypto" in category.lower():
            match = next(
                (i for i in invest_full if i.get("category", "").lower() == "crypto" and same_month(i.get("date", ""))),
                None
            )
            if match:
                asset_name = match.get("asset", asset_name)

        month_investment_fixed.append({
            "category": category,
            "asset": asset_name,
            "date": c.get("date", ""),
            "amount_idr": float(c.get("amount", 0)),
            "note": c.get("note", "")
        })

    # --- Susun struktur snapshot ---
    summary = {
        "income": total_income,
        "expense": total_expense,
        "investment": total_investment,
        "buffer": buffer_balance
    }

    entries = {
        "income": month_income,
        "expense": month_expense,
        "investment": month_investment_fixed
    }

    snapshot = {
        "month": month_label,
        "timestamp": today.isoformat(),
        "summary": summary,
        "entries": entries
    }

    # --- Simpan ke folder user ---
    history_dir = os.path.join(get_user_dir(), "history")
    os.makedirs(history_dir, exist_ok=True)
    out_path = os.path.join(history_dir, f"{month_label}.json")

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
        print(f"[Snapshot] {session.get('username')} → {out_path}")
        flash(f"Snapshot bulan {month_label} tersimpan dengan benar.", "success")
    except Exception as e:
        print(f"[ERROR] Gagal menyimpan snapshot: {e}")
        flash("Gagal menyimpan snapshot bulanan.", "danger")

    return redirect(url_for("history_panel"))





@app.route("/history/<month>")
def history_detail(month):
    path = os.path.join(HISTORY_DIR, f"{month}.json")
    if not os.path.exists(path):
        return f"Data {month} tidak ditemukan", 404

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("entries", {})

    # === Ambil ulang dari cashflow ===
    cash = load_json("cashflow.json")
    income_total = sum(
        float(c.get("amount", 0))
        for c in cash if c.get("type") == "income" and c.get("date", "").startswith(month)
    )
    expense_total = sum(
        float(c.get("amount", 0))
        for c in cash if c.get("type") == "expense" and c.get("date", "").startswith(month)
    )
    invest_total = sum(
        float(c.get("amount", 0))
        for c in cash if c.get("type") == "investment" and c.get("date", "").startswith(month)
    )

    buffer_balance = income_total - (expense_total + invest_total)

    inv_data = get_all_investment_totals()

    return render_template(
        "history_detail.html",
        month=month,
        summary={
            "income": income_total,
            "expense": expense_total,
            "investment": invest_total,
            "buffer": buffer_balance
        },
        entries=entries,
        total_income=income_total,
        total_expense=expense_total,
        total_invest_month=invest_total,
        buffer_balance=buffer_balance,
        inv_crypto=inv_data["crypto"],
        inv_gold=inv_data["gold"],
        inv_land=inv_data["land"],
        inv_business=inv_data["business"],
        inv_stock=inv_data["stock"]
    )



@app.route("/history/<month>/pdf")
def export_history_pdf(month):
    """
    Ekspor laporan bulanan ke PDF gaya profesional (font Poppins + layout rapi).
    Semua tabel seragam, warna pastel senada dashboard.
    """
    import os
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    path = os.path.join(HISTORY_DIR, f"{month}.json")
    if not os.path.exists(path):
        return f"Data {month} tidak ditemukan", 404

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    summary = data.get("summary", {})
    entries = data.get("entries", {})

        # === FONT POPPINS ===
    base_font = "Helvetica"

    # Coba prioritas Poppins-Light untuk efek tipis (setara font-weight 200)
    light_candidates = [
        "/usr/share/fonts/truetype/poppins/Poppins-Light.ttf",
        "/Library/Fonts/Poppins-Light.ttf",
    ]

    regular_candidates = [
        "/usr/share/fonts/truetype/poppins/Poppins-Regular.ttf",
        "/Library/Fonts/Poppins-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    try:
        # Coba daftarkan font tipis dulu
        for fp in light_candidates:
            if os.path.exists(fp):
                pdfmetrics.registerFont(TTFont("PoppinsLight", fp))
                base_font = "PoppinsLight"
                break

        # Jika belum ketemu font tipis, pakai Poppins-Regular
        if base_font == "Helvetica":
            for fp in regular_candidates:
                if os.path.exists(fp):
                    pdfmetrics.registerFont(TTFont("Poppins", fp))
                    base_font = "Poppins"
                    break

    except Exception as e:
        print(f"[FONT] Gagal memuat Poppins: {e}")


    # === SETUP PDF ===
    filename = f"history_{month}.pdf"
    reports_dir = os.path.join(get_user_dir(), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    pdf_path = os.path.join(reports_dir, filename)

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Header", fontName=base_font, fontSize=18,
                              leading=24, textColor=colors.HexColor("#2F3E46"), spaceAfter=14))
    styles.add(ParagraphStyle(name="SubHeader", fontName=base_font, fontSize=12,
                              leading=16, textColor=colors.HexColor("#495057"), spaceAfter=8))
    styles.add(ParagraphStyle(name="NormalText", fontName=base_font, fontSize=10,
                          leading=14, textColor=colors.black))


    elements = []

    # === HEADER ===
    elements.append(Paragraph("BUKABOX Financial Report", styles["Header"]))
    elements.append(Paragraph(f"Periode: {month}", styles["SubHeader"]))
    elements.append(Spacer(1, 10))

    # === DONUT CHART ===
    try:
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics.charts.piecharts import Pie

        total_income = float(summary.get("income", 0) or 0)
        total_expense = float(summary.get("expense", 0) or 0)
        total_invest = float(summary.get("investment", 0) or 0)
        total_buffer = abs(float(summary.get("buffer", 0) or 0))
        total_all = total_income + total_expense + total_invest + total_buffer or 1

        pie_vals = [
            (total_income / total_all) * 100,
            (total_expense / total_all) * 100,
            (total_invest / total_all) * 100,
            (total_buffer / total_all) * 100
        ]
        labels = ["Income", "Expense", "Investment", "Buffer"]

        d = Drawing(260, 160)
        pie = Pie()
        pie.x = 65
        pie.y = 15
        pie.width = 130
        pie.height = 130
        pie.data = pie_vals
        pie.labels = [f"{lbl} {val:.1f}%" for lbl, val in zip(labels, pie_vals)]
        pie.sideLabels = True
        pie.startAngle = 90
        pie.slices.strokeWidth = 0.3
        pie.slices.strokeColor = colors.white

        pastel = [
            colors.HexColor("#A5C8E4"),  # income
            colors.HexColor("#F4C7B8"),  # expense
            colors.HexColor("#B8E4C9"),  # invest
            colors.HexColor("#EAD1DC"),  # buffer
        ]
        for i, c in enumerate(pastel):
            pie.slices[i].fillColor = c

        d.add(pie)
        elements.append(d)
        elements.append(Spacer(1, 20))
    except Exception as e:
        print(f"[PDF Chart] Gagal render donut: {e}")

    # === TABEL RINGKASAN ===
    elements.append(Paragraph("RINGKASAN KEUANGAN", styles["SubHeader"]))
    summary_table = [
        ["Income", f"Rp {total_income:,.0f}"],
        ["Expense", f"Rp {total_expense:,.0f}"],
        ["Investment", f"Rp {total_invest:,.0f}"],
        ["Buffer", f"Rp {float(summary.get('buffer', 0) or 0):,.0f}"]
    ]
    t = Table(summary_table, colWidths=[250, 180])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8F9FA")),
        ("FONTNAME", (0, 0), (-1, -1), base_font),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT")
    ]))
    elements.append(t)
    elements.append(Spacer(1, 18))

    # === FUNGSI PEMBANGUN TABEL ===
    def make_table(title, headers, rows, widths):
        elements.append(Paragraph(title.upper(), styles["SubHeader"]))
        data = [headers] + rows
        tbl = Table(data, colWidths=[500 / len(headers)] * len(headers))  # sejajarkan semua tabel
        tbl.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D3D3D3")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9ECEF")),
            ("FONTNAME", (0, 0), (-1, -1), base_font),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (2, 1), (2, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(tbl)
        elements.append(Spacer(1, 16))

    # === PENDAPATAN ===
    if entries.get("income"):
        rows = []
        for i in entries["income"]:
            rows.append([
                i.get("date", ""),
                i.get("stream", ""),
                f"Rp {float(i.get('amount', 0) or 0):,.0f}",
                i.get("note", "")
            ])
        make_table("Daftar Pendapatan", ["Tanggal", "Stream", "Jumlah", "Catatan"], rows, [90, 160, 100, 80])

    # === PENGELUARAN ===
    if entries.get("expense"):
        rows = []
        for e in entries["expense"]:
            rows.append([
                e.get("date", ""),
                e.get("category", ""),
                f"Rp {float(e.get('amount', 0) or 0):,.0f}",
                e.get("note", "")
            ])
        make_table("Daftar Pengeluaran", ["Tanggal", "Kategori", "Jumlah", "Catatan"], rows, [90, 160, 100, 80])

    # === INVESTASI ===
    if entries.get("investment"):
        rows = []
        for inv in entries["investment"]:
            rows.append([
                inv.get("category", ""),
                inv.get("asset", ""),
                f"Rp {float(inv.get('amount_idr', inv.get('amount', 0) or 0)):,.0f}",
                inv.get("note", "")
            ])
        make_table("Daftar Investasi", ["Kategori", "Aset", "Modal (Rp)", "Catatan"], rows, [110, 110, 100, 90])
        # === NET WORTH SUMMARY ===
    try:
        from networth_integration_v46 import calculate_networth
        nw_summary = calculate_networth()

        elements.append(Spacer(1, 20))
        elements.append(Paragraph("NET WORTH SUMMARY", styles["SubHeader"]))
        elements.append(Spacer(1, 6))

        data_networth = [
            ["Investment", f"Rp {nw_summary['investment']:,.0f}"],
            ["Emergency Fund", f"Rp {nw_summary['emergency']:,.0f}"],
            ["Buffer (Cash)", f"Rp {nw_summary['buffer']:,.0f}"],
            ["Total Assets", f"Rp {nw_summary['investment'] + nw_summary['emergency'] + nw_summary['buffer']:,.0f}"],
            ["Liabilities", f"Rp {nw_summary['liabilities']:,.0f}"],
            ["Net Worth", f"Rp {nw_summary['net_worth']:,.0f}"],
        ]

        t_networth = Table(data_networth, colWidths=[220, 180])
        t_networth.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8F9FA")),
            ("FONTNAME", (0, 0), (-1, -1), base_font),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
        ]))
        elements.append(t_networth)

        # === DETAIL LIABILITIES ===
        elements.append(Spacer(1, 18))
        elements.append(Paragraph("LIABILITIES DETAIL", styles["SubHeader"]))
        elements.append(Spacer(1, 6))

        liabilities = nw_summary.get("liabilities_detail", [])

        if liabilities:
            liab_data = [["Date", "Category", "Amount", "Remaining", "Progress", "Note"]]
            for l in liabilities:
                liab_data.append([
                    l.get("date", "-"),
                    l.get("category", "-"),
                    f"Rp {float(l.get('amount', 0)):,.0f}",
                    f"Rp {float(l.get('remaining', 0)):,.0f}",
                    f"{float(l.get('progress', 0)):,.1f}%",
                    l.get("note", "-")
                ])

            t_liab = Table(liab_data, colWidths=[65, 70, 70, 70, 50, 100])
            t_liab.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9ECEF")),
                ("FONTNAME", (0, 0), (-1, -1), base_font),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (2, 1), (4, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            elements.append(t_liab)
        else:
            elements.append(Paragraph("Tidak ada data liabilitas aktif.", styles["NormalText"]))

    except Exception as e:
        print("[PDF] Gagal menambahkan Net Worth section:", e)

    # === FOOTER ===
    elements.append(Spacer(1, 30))
    elements.append(Paragraph("<i>Generated automatically by Bukabox Financial Dashboard</i>", styles["NormalText"]))

    # === BUILD PDF ===
    try:
        doc.build(elements)
        print(f"[PDF] Laporan tersimpan: {pdf_path}")
        return send_file(pdf_path, as_attachment=True)
    except Exception as e:
        print(f"[PDF ERROR] Gagal membuat PDF: {e}")
        flash("Gagal menyimpan file PDF.", "danger")
        return redirect(url_for("history_panel"))


@app.route("/save_history")
def save_history():
    """Membuat snapshot bulanan dari data real-time (index)"""
    today = datetime.date.today()
    month_id = today.strftime("%Y-%m")

    # ambil semua data dari file utama
    summary = load_json("summary.json")
    entries = load_json("entries.json")

    # --- pastikan struktur entries ---
    if isinstance(entries, dict):
        investment = entries.get("investment", [])
    elif isinstance(entries, list):
        investment = entries
    else:
        investment = []

    crypto_accumulation = []
    crypto_prices = load_json("crypto.json")

    tokens = {}
    for inv in investment:
        if inv.get("category") != "crypto":
            continue

        sym = inv.get("asset", "").upper().strip()
        note = (inv.get("note") or "").strip().lower()

        if sym == "BTC" and note == "operasional":
            key = "BTC Operasional"
        elif sym == "BTC" and note == "anak":
            key = "BTC Anak"
        else:
            key = sym

        curr_price = crypto_prices.get(sym, 0)
        entry_amount = float(inv.get("entry_amount", 0))
        amount_idr = float(inv.get("amount_idr", 0))
        now_value = curr_price * entry_amount

        if key not in tokens:
            tokens[key] = {
                "symbol": key,
                "total_amount": amount_idr,
                "total_coin": entry_amount,
                "curr": curr_price,
                "current_value": now_value,
            }
        else:
            tokens[key]["total_amount"] += amount_idr
            tokens[key]["total_coin"] += entry_amount
            tokens[key]["current_value"] += now_value

    for sym, t in tokens.items():
        avg_price = (t["total_amount"] / t["total_coin"]) if t["total_coin"] else 0
        pnl = ((t["current_value"] - t["total_amount"]) / t["total_amount"] * 100) if t["total_amount"] else 0
        crypto_accumulation.append({
            "token": sym,
            "total_modal": t["total_amount"],
            "total_koin": t["total_coin"],
            "avg_price": avg_price,
            "current_value": t["current_value"],
            "pnl": pnl
        })

    # struktur file snapshot
    snapshot = {
        "summary": summary,
        "entries": entries,
        "crypto_accumulation": crypto_accumulation,
        "saved_at": today.isoformat()
    }

    user_history = os.path.join(get_user_dir(), "history")
    os.makedirs(user_history, exist_ok=True)
    file_path = os.path.join(user_history, f"{month_id}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    print(f"[HISTORY] Snapshot tersimpan: {file_path}")
    return redirect(url_for("index"))

@app.route("/reduce_invest", methods=["POST"])
@login_required
def reduce_invest():
    token_label = request.form.get("asset", "").strip()
    raw_amount = request.form.get("amount", "0")
    note = request.form.get("note", "")

    try:
        amount = float(raw_amount.replace(".", "").replace(",", ""))
    except:
        amount = 0.0

    if amount <= 0:
        flash("Nominal pengurangan tidak valid.", "warning")
        return redirect(url_for("investment_panel"))

    # deteksi sub-group dari label dropdown
    target_asset = token_label.split()[0].upper().strip()
    target_note = ""
    low_label = token_label.lower()
    if "operasional" in low_label:
        target_note = "operasional"
    elif "anak" in low_label:
        target_note = "anak"

    crypto_prices = get_crypto_prices()
    current_price = crypto_prices.get(target_asset, 0)
    if current_price <= 0:
        flash(f"Harga {target_asset} tidak ditemukan, rebalance dibatalkan.", "danger")
        return redirect(url_for("investment_panel"))

    investments = load_json("investment.json")
    total_ditarik = amount
    sisa_rebalance = amount

    for inv in investments:
        if inv.get("category") != "crypto":
            continue

        sym = inv.get("asset", "").upper().strip()
        note_entry = (inv.get("note") or "").strip().lower()

        if sym != target_asset:
            continue
        if target_note and note_entry != target_note:
            continue

        entry_price = float(inv.get("entry_price", 0))
        entry_amount = float(inv.get("entry_amount", 0))
        amount_idr = float(inv.get("amount_idr", 0))

        if entry_amount <= 0 or sisa_rebalance <= 0:
            continue

        real_value = entry_amount * current_price
        if real_value <= 0:
            continue

        coin_reduced = min(entry_amount, sisa_rebalance / current_price)
        sisa_rebalance -= coin_reduced * current_price

        new_entry_amount = entry_amount - coin_reduced
        new_modal = new_entry_amount * entry_price

        inv["entry_amount"] = round(new_entry_amount, 8)
        inv["amount_idr"] = round(new_modal, 2)
        inv["entry_price"] = round(new_modal / new_entry_amount, 2) if new_entry_amount > 0 else entry_price

    save_json("investment.json", investments)

    # === catat ke investment_reduce.json ===
    reduce_log = load_json("investment_reduce.json")
    reduce_log.insert(0, {
        "date": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "asset": token_label,
        "amount": total_ditarik,
        "note": note
    })
    save_json("investment_reduce.json", reduce_log)

    # === CATAT DANA MASUK KE BUFFER ===
    buffer_data = load_json("buffer.json")
    buffer_data.append({
        "date": datetime.date.today().isoformat(),
        "type": "income",
        "category": f"Rebalance {token_label}",
        "amount": total_ditarik,
        "note": note or f"Rebalance {token_label}"
    })
    save_json("buffer.json", buffer_data)

    # === CATAT ARUS KE CASHFLOW (untuk tracking umum) ===
    cash = load_json("cashflow.json")
    cash.append({
        "date": datetime.date.today().isoformat(),
        "type": "income",  # 🔄 ubah ke income agar seimbang
        "category": f"Rebalance {token_label}",
        "amount": total_ditarik,
        "note": note or f"Dana masuk dari {token_label}"
    })
    save_json("cashflow.json", cash)

    # === CATAT KE INCOME.JSON UNTUK DASHBOARD ===
    income_data = load_json("income.json")
    income_data.append({
        "date": datetime.date.today().isoformat(),
        "stream": f"Rebalance {token_label}",
        "amount": total_ditarik,
        "note": note or f"Dana hasil reduce {token_label}"
    })
    save_json("income.json", income_data)

    flash(f"Rebalance {token_label} sebesar {fmt_idr(total_ditarik)} berhasil. Dana masuk ke buffer.", "success")
    return redirect(url_for("investment_panel"))

@app.route("/rollover", methods=["POST"])
@login_required
def rollover_action():
    rollover_buffer()
    flash("✅ Bulan telah ditutup dan data disimpan ke history.", "success")
    return redirect(url_for("index"))

# ---------- AUTH ROUTES ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    """
    Login multi-user dengan pembuatan folder data otomatis per user.
    Jika login berhasil, user diarahkan ke dashboard dan semua data
    akan diarahkan ke folder app/data/<username>/
    """
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()

        users = load_users()
        user = next((u for u in users if u["username"] == username), None)

        if user and check_password_hash(user["password_hash"], password):
            # ====== SESSION AKTIF ======
            session["logged_in"] = True
            session["username"] = username

            # ====== BUAT FOLDER DATA USER ======
            user_dir = os.path.join(DATA_DIR, username)
            os.makedirs(user_dir, exist_ok=True)

            # Buat subfolder wajib
            for sub in ["history", "reports"]:
                os.makedirs(os.path.join(user_dir, sub), exist_ok=True)

            # Inisialisasi file dasar jika belum ada
            for f in [
                "income.json", "cashflow.json", "investment.json",
                "emergency.json", "buffer.json", "investment_reduce.json"
            ]:
                path = os.path.join(user_dir, f)
                if not os.path.exists(path):
                    with open(path, "w") as fp:
                        fp.write("[]")

            print(f"[LOGIN] {username} masuk | Folder data: {user_dir}")
            flash(f"Selamat datang, {username}!", "success")
            return redirect(url_for("index"))

        # === LOGIN GAGAL ===
        flash("Username atau password salah.", "danger")
        return redirect(url_for("login"))

    # GET method → tampilkan halaman login
    return render_template("login.html")



@app.route("/logout")
def logout():
    session.clear()
    flash("Logout berhasil.", "info")
    return redirect(url_for("index"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username").strip()
        password = request.form.get("password").strip()
        confirm  = request.form.get("confirm").strip()

        if not username or not password:
            flash("Username dan password harus diisi.", "warning")
            return redirect(url_for("register"))
        if password != confirm:
            flash("Konfirmasi password tidak cocok.", "warning")
            return redirect(url_for("register"))

        users = load_users()
        if any(u["username"] == username for u in users):
            flash("Username sudah digunakan.", "danger")
            return redirect(url_for("register"))

        users.append({
            "username": username,
            "password_hash": generate_password_hash(password),
            "created_at": datetime.datetime.now().isoformat()
        })
        save_users(users)

        # 🧩 Buat folder data user baru
        user_dir = os.path.join(DATA_DIR, username)
        for sub in ["history", "reports"]:
            os.makedirs(os.path.join(user_dir, sub), exist_ok=True)

        # Buat file dasar
        for f in ["income.json", "cashflow.json", "investment.json",
                  "emergency.json", "buffer.json", "investment_reduce.json"]:
            open(os.path.join(user_dir, f), "w").write("[]")

        # 🧩 Buat settings.json default per user
        settings = {
            "currency": "IDR",
            "theme": "light",
            "language": "id",
            "created_at": datetime.datetime.now().isoformat()
        }
        with open(os.path.join(user_dir, "settings.json"), "w") as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)

        flash(f"User '{username}' berhasil dibuat. Silakan login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")



# ---------- RUN ----------
if __name__ == "__main__":
    port = 8124
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while sock.connect_ex(("127.0.0.1", port)) == 0:
        port += 1
    sock.close()
    url = f"http://127.0.0.1:{port}"
    webbrowser.open(url)
    app.run(port=port, debug=False)
    