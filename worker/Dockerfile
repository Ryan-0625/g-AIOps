# ── Build stage ──────────────────────────────────────────────────────────
FROM golang:1.25-alpine AS builder

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /gaiops-worker ./cmd/worker/

# ── Runtime stage ────────────────────────────────────────────────────────
FROM alpine:3.21

RUN apk add --no-cache ca-certificates tzdata && \
    addgroup -S gaiops && adduser -S gaiops -G gaiops

COPY --from=builder /gaiops-worker /usr/local/bin/gaiops-worker

USER gaiops

EXPOSE 9090

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost:9090/health || exit 1

ENTRYPOINT ["gaiops-worker"]
CMD ["--config", "/etc/gaiops/worker.yaml"]
