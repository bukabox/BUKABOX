# === NET WORTH SYSTEM INTEGRATION v4.6 ===
# Integrasi sistem Net Worth berdasarkan file main.py v4.6
# Fokus: menggabungkan semua sumber aset (investment, emergency, buffer) menjadi 1 ringkasan nilai kekayaan bersih (Net Worth)

import os, json, datetime
from flask import Blueprint, jsonify, render_template, request, flash, url_for, redirect
from helpers import load_json, save_json, get_user_dir



networth_bp = Blueprint('networth', __name__)


def calculate_networth():
    """Hitung total kekayaan bersih user (aset, liabilitas, buffer, emergency, investment)"""
    user_dir = get_user_dir()

    # === MUAT SEMUA DATA ===
    investment_data = load_json("investment.json")
    emergency_data = load_json("emergency.json")
    cashflow = load_json("cashflow.json")
    liabilities_path = os.path.join(user_dir, "liabilities.json")
    liabilities = load_json(liabilities_path) if os.path.exists(liabilities_path) else []

    # === 1️⃣ HITUNG ASET ===
    total_investment = sum(float(i.get("amount_idr", 0)) for i in investment_data)
    total_emergency = sum(float(e.get("amount", 0)) for e in emergency_data)
    total_assets_invest = total_investment + total_emergency

    # === 2️⃣ HITUNG BUFFER (saldo kas akhir) ===
    total_income = sum(float(c.get("amount", 0)) for c in cashflow if c.get("type") == "income")
    total_expense = sum(float(c.get("amount", 0)) for c in cashflow if c.get("type") == "expense")
    total_investment_flow = sum(float(c.get("amount", 0)) for c in cashflow if c.get("type") == "investment")

    buffer = total_income - (total_expense + total_investment_flow)

    # === 3️⃣ HITUNG DETAIL & PROGRESS PER-LOAN (AMAN) ===
    cashflow_path = os.path.join(user_dir, "cashflow.json")
    cashflow_data = load_json(cashflow_path)

    for l in liabilities:
        # selalu definisikan ID untuk menghindari NameError
        l_id = l.get("id", l.get("note", "")) or ""
        total_paid = sum(
            float(c.get("amount", 0))
            for c in cashflow_data
            if c.get("type") == "expense"  # ✅ hanya hitung pembayaran
            and c.get("category", "").lower() == "loan"
            and c.get("note", "") == l_id
        )

        total_amount = float(l.get("amount", 0))
        remaining = max(total_amount - total_paid, 0)
        progress = round((total_paid / total_amount) * 100, 1) if total_amount > 0 else 0

        l["paid"] = total_paid
        l["remaining"] = remaining
        l["progress"] = progress

        # Auto flag status
        l["status"] = "Lunas" if remaining <= 0 else "Berjalan"

    # total liabilitas dihitung dari sisa (remaining)
    total_liabilities = sum(float(l.get("remaining", 0)) for l in liabilities)

    # === Update status liabilitas berdasarkan pembayaran di cashflow ===
    for l in liabilities:
        l_id = l.get("id", "").strip()
        total_paid = sum(
            float(c.get("amount", 0))
            for c in cashflow
            if c.get("type") == "expense"
            and c.get("category", "").lower() == "loan"
            and c.get("note", "").strip() == l_id
        )
        amount = float(l.get("amount", 0))
        remaining = max(amount - total_paid, 0)
        progress = round((total_paid / amount) * 100, 1) if amount else 0

        l["remaining"] = remaining
        l["progress"] = progress
        l["status"] = "Lunas" if remaining <= 0 else "Berjalan"


    # === 4️⃣ HITUNG NET WORTH ===
    total_assets = buffer + total_assets_invest
    net_worth = total_assets - total_liabilities
    save_json(os.path.join(user_dir, "liabilities.json"), liabilities)

    # === 5️⃣ SUSUN HASIL ===
    breakdown = {
        "investment": round(total_investment, 2),
        "emergency": round(total_emergency, 2),
        "buffer": round(buffer, 2),
        "liabilities": round(total_liabilities, 2),
        "liabilities_detail": liabilities,
        "net_worth": round(net_worth, 2)
    }

    return breakdown


@networth_bp.route('/networth', methods=['GET'])
def networth_summary():
    """Endpoint untuk menampilkan ringkasan Net Worth user aktif."""
    try:
        summary = calculate_networth()
        summary["timestamp"] = datetime.datetime.now().isoformat()

        # Simpan snapshot ke file
        user_dir = get_user_dir()
        file_path = os.path.join(user_dir, "networth.json")
        save_json("networth.json", summary)
        save_networth_snapshot()
        return jsonify({"status": "success", "data": summary}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


    try:
        summary = calculate_networth()
        save_json("networth.json", summary)
        save_networth_snapshot()  # auto snapshot bulanan
    except Exception as e:
        print("Auto networth update failed:", e)


@networth_bp.route('/networth/snapshot', methods=['POST'])
def save_networth_snapshot():
    """Simpan atau update hasil Net Worth ke file snapshot utama bulan aktif"""
    try:
        snapshot = calculate_networth()
        today = datetime.date.today()
        month_label = today.strftime('%Y-%m')

        user_dir = get_user_dir()
        history_dir = os.path.join(user_dir, "history")
        os.makedirs(history_dir, exist_ok=True)

        # File snapshot utama bulan berjalan
        main_path = os.path.join(history_dir, f"{month_label}.json")

        # Jika file sudah ada → load & update
        if os.path.exists(main_path):
            with open(main_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            # Jika belum ada, buat template baru
            data = {
                "month": month_label,
                "summary": {},
                "entries": {}
            }

        # Update bagian Net Worth
        data["summary"]["networth"] = snapshot

        # Simpan kembali ke file utama
        with open(main_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return jsonify({
            "status": "success",
            "message": f"Net Worth snapshot updated in {month_label}.json"
        }), 200

    except Exception as e:
        print("[NETWORTH SNAPSHOT ERROR]", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@networth_bp.route('/networth/dashboard')
def networth_dashboard():
    """Tampilkan halaman analitik Net Worth bulanan (real-time + history)"""
    try:
        # Hitung ulang Net Worth terbaru
        summary = calculate_networth()

        # Simpan file networth.json (opsional, update terakhir)
        user_dir = get_user_dir()
        save_json(os.path.join(user_dir, "networth.json"), summary)

        # Ambil direktori history user
        history_dir = os.path.join(user_dir, "history")
        os.makedirs(history_dir, exist_ok=True)

        # === BACA SEMUA SNAPSHOT BULAN ===
        networth_history = []
        for f in sorted(os.listdir(history_dir)):
            # hanya baca file utama (bukan networth_xx.json)
            if f.endswith(".json") and not f.startswith("networth_"):
                path = os.path.join(history_dir, f)
                try:
                    with open(path, "r", encoding="utf-8") as fp:
                        data = json.load(fp)
                        month = data.get("month", f.replace(".json", ""))

                        summary_data = data.get("summary", {})

                        # Ambil bagian networth dari summary
                        networth_data = summary_data.get("networth", {})

                        # === Fallback untuk file lama (tanpa networth key) ===
                        if not networth_data:
                            networth_data = {
                                "investment": summary_data.get("investment", 0),
                                "emergency": summary_data.get("emergency", 0),
                                "buffer": summary_data.get("buffer", 0),
                                "liabilities": summary_data.get("liabilities", 0),
                                "net_worth": summary_data.get("net_worth", 0),
                            }

                        # Jika data valid, tambahkan ke riwayat
                        networth_history.append({
                            "month": month,
                            "investment": networth_data.get("investment", 0),
                            "emergency": networth_data.get("emergency", 0),
                            "buffer": networth_data.get("buffer", 0),
                            "liabilities": networth_data.get("liabilities", 0),
                            "net_worth": networth_data.get("net_worth", 0)
                        })

                except Exception as e:
                    print(f"[NETWORTH DASHBOARD] Gagal baca file {f}: {e}")

        # Urutkan data berdasarkan bulan
        networth_history.sort(key=lambda x: x["month"])
        print("DEBUG NETWORTH HISTORY:", networth_history)

        # Render halaman dashboard Net Worth
        return render_template(
            "networth.html",
            networth=summary,
            networth_history=networth_history,
            today=datetime.date.today().isoformat()
        )

    except Exception as e:
        print("[NETWORTH DASHBOARD ERROR]", e)
        return render_template(
            "networth.html",
            networth={},
            networth_history=[],
            today=datetime.date.today().isoformat()
        )


@networth_bp.route('/add_liability', methods=['POST'])
def add_liability():
    """Tambah data liabilitas baru dengan ID unik, dan catat otomatis ke income serta cashflow (loan inflow)."""
    try:
        user_dir = get_user_dir()

        # === Ambil data dari form ===
        date = request.form.get("date", datetime.date.today().isoformat())
        category = request.form.get("category", "Loan")
        name = request.form.get("name", "Loan").strip()  # ✅ ambil nama pinjaman
        note = request.form.get("note", "").strip()
        raw_amount = request.form.get("amount", "0")

        # Parsing nominal seperti form lain
        try:
            amount = float(str(raw_amount).replace(".", "").replace(",", ""))
        except ValueError:
            amount = 0

        if amount <= 0:
            flash("Nominal liabilitas tidak valid.", "warning")
            return redirect(url_for("networth.networth_dashboard"))

        # === 1️⃣ Simpan ke liabilities.json ===
        liabilities_path = os.path.join(user_dir, "liabilities.json")
        liabilities = load_json(liabilities_path)

        # Buat ID unik otomatis (LN001, LN002, dst)
        new_id = f"LN{len(liabilities) + 1:03d}"  # ✅ pakai :03d biar LN001 bukan LN01

        new_liability = {
            "id": new_id,
            "date": date,
            "category": category,
            "name": name,
            "amount": amount,
            "note": note or "Liability baru",
            "status": "Berjalan"
        }

        liabilities.append(new_liability)
        save_json(liabilities_path, liabilities)
        print(f"[LIABILITIES] Ditambahkan: {category} ({new_id}) - Rp{amount:,.0f}")

        # === 2️⃣ Catat otomatis sebagai pemasukan (Loan Inflow) ===
        try:
            income_path = os.path.join(user_dir, "income.json")
            incomes = load_json(income_path)
            new_income = {
                "date": date,
                "category": "Loan",
                "amount": amount,
                "note": new_id,
                "stream": name
            }
            incomes.append(new_income)
            save_json(income_path, incomes)
            print(f"[INCOME] Dana pinjaman {new_id} dicatat di income.json: Rp{amount:,.0f}")
        except Exception as e:
            print("[LIABILITIES->INCOME ERROR]", e)

        # === 3️⃣ Tambahkan juga ke cashflow.json agar buffer ikut naik ===
        try:
            cashflow_path = os.path.join(user_dir, "cashflow.json")
            cashflows = load_json(cashflow_path)
            new_cashflow = {
                "date": date,
                "type": "income",
                "category": "Loan",
                "amount": amount,
                "note": new_id,
            }
            cashflows.append(new_cashflow)
            save_json(cashflow_path, cashflows)
            print(f"[CASHFLOW] Dana loan {new_id} masuk ke cashflow.json: Rp{amount:,.0f}")
        except Exception as e:
            print("[LIABILITIES->CASHFLOW ERROR]", e)

        # === 4️⃣ Update file networth.json ===
        try:
            summary = calculate_networth()
            save_json(os.path.join(user_dir, "networth.json"), summary)
            print("[NETWORTH] Data networth.json diperbarui.")
        except Exception as e:
            print("[NETWORTH UPDATE ERROR]", e)

        # === 5️⃣ Simpan juga ke snapshot bulan aktif (YYYY-MM.json) ===
        try:
            today = datetime.date.today()
            month_label = today.strftime("%Y-%m")
            history_dir = os.path.join(user_dir, "history")
            os.makedirs(history_dir, exist_ok=True)
            main_snapshot_path = os.path.join(history_dir, f"{month_label}.json")

            if os.path.exists(main_snapshot_path):
                with open(main_snapshot_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {"month": month_label, "summary": {}, "entries": {}}

            data["summary"]["networth"] = summary

            with open(main_snapshot_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            print(f"[SNAPSHOT] Net Worth bulan {month_label} diperbarui.")
        except Exception as e:
            print("[SNAPSHOT UPDATE ERROR]", e)

        flash(f"Liabilitas {new_id} berhasil ditambahkan dan tercatat di income serta cashflow.", "success")
        return redirect(url_for("networth.networth_dashboard"))

    except Exception as e:
        print("[ADD_LIABILITY ERROR]", e)
        flash(f"Gagal menambahkan liabilitas: {e}", "danger")
        return redirect(url_for("networth.networth_dashboard"))



