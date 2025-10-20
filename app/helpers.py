import os, json
from flask import session

from flask import session
import os

def get_user_dir():
    """
    Pastikan semua modul (termasuk Net Worth) membaca dan menulis data
    di folder user yang sedang login, misal: app/data/ichi/
    Jika belum login, gunakan folder global app/data/
    """
    base_dir = os.path.join(os.path.dirname(__file__), "data")

    # Pastikan root data ada
    os.makedirs(base_dir, exist_ok=True)

    # Deteksi user dari session Flask
    user = session.get("username")
    if user:
        user_dir = os.path.join(base_dir, user)
        os.makedirs(user_dir, exist_ok=True)
        return user_dir

    # fallback jika belum login
    return base_dir


def load_json(filename):
    path = os.path.join(get_user_dir(), filename)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_json(filename, data):
    path = os.path.join(get_user_dir(), filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
