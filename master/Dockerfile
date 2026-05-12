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

RUN mkdir -p /var/log/gaiops

WORKDIR /app
COPY --from=builder /src/dist ./dist
COPY --from=builder /src/node_modules ./node_modules
COPY package.json ./

EXPOSE 8080

ENTRYPOINT ["node", "dist/index.js"]
