FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY frontend ./frontend

# Override with a managed Postgres URL for production; SQLite under /data
# is fine for early testing as long as /data is a persistent volume.
ENV PET_SITTER_DB_URL=sqlite:////data/pet_sitter.db
VOLUME ["/data"]

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
