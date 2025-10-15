#!/bin/bash
# Jalankan BukaboxMachine v3 secara otomatis

cd "$(dirname "$0")"
cd app

# aktifkan virtualenv kalau ada
if [ -d "../.venv" ]; then
    source ../.venv/bin/activate
fi

# jika Flask masih jalan di port lama, hentikan otomatis
OLD_PID=$(lsof -ti:8124)
if [ ! -z "$OLD_PID" ]; then
    echo "🔴 Menutup proses lama di port 8124..."
    kill -9 $OLD_PID
fi

echo "🚀 Menjalankan BukaboxMachine v3..."
python3 main.py
