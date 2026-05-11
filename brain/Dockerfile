# ── Build stage ──────────────────────────────────────────────────────────
FROM python:3.12-alpine AS builder

WORKDIR /src
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ── Runtime stage ────────────────────────────────────────────────────────
FROM python:3.12-alpine

RUN apk add --no-cache tzdata ca-certificates

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY . .

ENTRYPOINT ["python", "main.py"]
