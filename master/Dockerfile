# ── Build stage ──────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json ./
COPY src/ ./src/
RUN npx tsc

# ── Runtime stage ────────────────────────────────────────────────────────
FROM node:20-alpine

RUN apk add --no-cache tzdata wget

RUN mkdir -p /var/log/gaiops && \
    addgroup -S gaiops && adduser -S gaiops -G gaiops

WORKDIR /app
COPY --from=builder /src/dist ./dist
COPY --from=builder /src/node_modules ./node_modules
COPY package.json ./

USER gaiops

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost:8080/health || exit 1

ENTRYPOINT ["node", "dist/index.js"]
