FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create the apex/backend/ package structure so imports like
# "from apex.backend.xxx import" resolve correctly when running
# with PYTHONPATH=/app (build context root = apex/backend/).
RUN mkdir -p /app/apex/backend
COPY . /app/apex/backend/

RUN mkdir -p /app/uploads /app/data

# PYTHONPATH=/app means apex.backend.* resolves to /app/apex/backend/*
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["sh", "-c", "uvicorn apex.backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
