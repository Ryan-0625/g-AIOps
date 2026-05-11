#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${ROOT}/.dev-logs"
CONFIG_DIR="${1:-$ROOT}"

mkdir -p "$LOG_DIR"

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
GRAY='\033[0;90m'
NC='\033[0m'

echo -e "${CYAN}=== gAIOps Development Environment ===${NC}\n"

# ── Check dependencies ──
GO_OK=false; NODE_OK=false; PYTHON_OK=false
command -v go >/dev/null 2>&1 && { echo -e "  ${GRAY}[✓] Go${NC}"; GO_OK=true; } || echo -e "  ${YELLOW}[!] Go not found${NC}"
command -v node >/dev/null 2>&1 && { echo -e "  ${GRAY}[✓] Node.js${NC}"; NODE_OK=true; } || echo -e "  ${YELLOW}[!] Node.js not found${NC}"
command -v python3 >/dev/null 2>&1 && { echo -e "  ${GRAY}[✓] Python${NC}"; PYTHON_OK=true; } || echo -e "  ${YELLOW}[!] Python not found${NC}"

if ! $GO_OK && ! $NODE_OK && ! $PYTHON_OK; then
  echo -e "${YELLOW}No runtimes found — install Go, Node.js, or Python as needed${NC}"
  exit 1
fi

PIDS=()

cleanup() {
  echo -e "\n${YELLOW}[-] Stopping gAIOps...${NC}"
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  rm -f "$LOG_DIR"/*.pid
  echo -e "${YELLOW}[-] All services stopped${NC}"
  exit 0
}
trap cleanup SIGINT SIGTERM

# ── Worker ──
if $GO_OK; then
  WORKER_CFG="${CONFIG_DIR}/worker.yaml"
  if [ -f "$WORKER_CFG" ]; then
    CFG_FLAG="--config $WORKER_CFG"
  else
    CFG_FLAG=""
    echo -e "  ${YELLOW}[!] worker.yaml not found at $WORKER_CFG — using defaults${NC}"
  fi
  echo -e "${GREEN}[+] Starting Worker...${NC}"
  cd "$ROOT/worker"
  go run ./cmd/worker/ $CFG_FLAG > "$LOG_DIR/worker.log" 2>&1 &
  PIDS+=($!)
  echo $! > "$LOG_DIR/worker.pid"
  cd "$ROOT"
  echo -e "  ${GRAY}Worker PID $!${NC}"
  sleep 2
fi

# ── Master ──
if $NODE_OK; then
  if [ ! -d "$ROOT/master/node_modules" ]; then
    echo -e "  ${YELLOW}[i] Installing Master dependencies...${NC}"
    (cd "$ROOT/master" && npm install)
  fi
  echo -e "${GREEN}[+] Starting Master...${NC}"
  cd "$ROOT/master"
  npx ts-node src/index.ts > "$LOG_DIR/master.log" 2>&1 &
  PIDS+=($!)
  echo $! > "$LOG_DIR/master.pid"
  cd "$ROOT"
  echo -e "  ${GRAY}Master PID $!${NC}"
  sleep 2
fi

# ── Brain ──
if $PYTHON_OK; then
  VENV_DIR="$ROOT/brain/.venv"
  if [ ! -d "$VENV_DIR" ]; then
    echo -e "  ${YELLOW}[i] Creating Brain venv...${NC}"
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install -r "$ROOT/brain/requirements.txt" -q
  fi
  echo -e "${GREEN}[+] Starting Brain...${NC}"
  cd "$ROOT/brain"
  "$VENV_DIR/bin/python" main.py > "$LOG_DIR/brain.log" 2>&1 &
  PIDS+=($!)
  echo $! > "$LOG_DIR/brain.pid"
  cd "$ROOT"
  echo -e "  ${GRAY}Brain PID $!${NC}"
fi

echo -e "\n${GREEN}[+] All processes started. Logs: $LOG_DIR${NC}"
echo -e "${GRAY}[i] Ctrl+C to stop all services.${NC}"

wait
