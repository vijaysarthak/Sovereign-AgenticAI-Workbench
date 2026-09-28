FROM python:3.12-slim

WORKDIR /app

# System deps for lxml (python-pptx/python-docx) and pypdf's occasional native bits.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# severance.db is created fresh on first startup (init_*_table() calls in
# api/main.py's lifespan) if it doesn't already exist at SEVERANCE_DB_PATH --
# mount a volume there to persist it across container restarts.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
