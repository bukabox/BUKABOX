FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8080

 Perhatikan dua hal di bawah ini:
# --chdir app   → masuk ke folder app sebelum start
# "main:app"    → karena file di dalam folder app bernama main.py
CMD ["gunicorn", "--chdir", "app", "--bind", "0.0.0.0:8080", "main:app"]

