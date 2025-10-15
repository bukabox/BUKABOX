# Gunakan Python 3.11 resmi
FROM python:3.11-slim

# Set working directory di container
WORKDIR /app

# Salin semua file proyek ke dalam container
COPY . .

# Pastikan pip dan build tools up to date
RUN pip install --upgrade pip setuptools wheel

# Instal semua dependensi
RUN pip install --no-cache-dir -r requirements.txt

# Expose port (Render otomatis inject PORT env var)
EXPOSE 10000

# Jalankan Flask app via Gunicorn
# 'app.main:app' = folder app / file main.py / variabel Flask = app
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app.main:app"]
