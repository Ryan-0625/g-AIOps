#!/usr/bin/env bash
# gAIOps Worker Agent Installer
# Usage: curl -fsSL https://install.gaiops.io/worker | sh
#   or: curl -fsSL https://install.gaiops.io/worker | sh -s -- --master ws://master:8080/ws --token my-token

set -euo pipefail

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
NC="\033[0m"

info()  { printf "${GREEN}%s${NC}\n" "$*"; }
warn()  { printf "${YELLOW}WARN: %s${NC}\n" "$*"; }
error() { printf "${RED}ERROR: %s${NC}\n" "$*"; exit 1; }

REPO="${REPO:-Ryan-0625/g-AIOps}"
VERSION="${VERSION:-latest}"
INSTALL_DIR="${INSTALL_DIR:-/usr/local/bin}"
CONFIG_DIR="${CONFIG_DIR:-/etc/gaiops}"
DATA_DIR="${DATA_DIR:-/var/lib/gaiops/worker}"
WORKER_USER="${WORKER_USER:-_gaiops}"

# Parse CLI args
MASTER_URL=""
CLUSTER_TOKEN=""
WORKER_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --master) MASTER_URL="$2"; shift 2 ;;
    --token) CLUSTER_TOKEN="$2"; shift 2 ;;
    --worker-id) WORKER_ID="$2"; shift 2 ;;
    --help)
      echo "Usage: install.sh [options]"
      echo "  --master <url>     Master WebSocket URL (e.g. ws://master:8080/ws)"
      echo "  --token <token>    Cluster authentication token"
      echo "  --worker-id <id>   Unique worker identifier (default: hostname)"
      exit 0 ;;
    *) error "Unknown option: $1" ;;
  esac
done

# Detect OS and arch
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64)  ARCH="amd64" ;;
  aarch64) ARCH="arm64" ;;
  armv7l)  ARCH="arm" ;;
  *) error "Unsupported architecture: $ARCH" ;;
esac

info "==> gAIOps Worker Agent Installer"
info "    OS: $OS, Arch: $ARCH"
info "    Install Dir: $INSTALL_DIR"
echo ""

# Download binary
BINARY="gaiops-worker-${OS}-${ARCH}"
if [ "$VERSION" = "latest" ]; then
  DOWNLOAD_URL="https://github.com/${REPO}/releases/latest/download/${BINARY}"
else
  DOWNLOAD_URL="https://github.com/${REPO}/releases/download/${VERSION}/${BINARY}"
fi

info "==> Downloading Worker binary..."
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

if command -v curl &>/dev/null; then
  curl -fsSL "$DOWNLOAD_URL" -o "$TMP_DIR/gaiops-worker"
elif command -v wget &>/dev/null; then
  wget -q "$DOWNLOAD_URL" -O "$TMP_DIR/gaiops-worker"
else
  error "Neither curl nor wget found. Please install one and retry."
fi

chmod +x "$TMP_DIR/gaiops-worker"
info "    Downloaded to $TMP_DIR/gaiops-worker"

# Create user
if ! id "$WORKER_USER" &>/dev/null 2>&1; then
  info "==> Creating system user: $WORKER_USER"
  if command -v useradd &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$WORKER_USER"
  elif command -v adduser &>/dev/null; then
    adduser --system --no-create-home --shell /usr/sbin/nologin "$WORKER_USER"
  fi
fi

# Install binary
info "==> Installing binary to ${INSTALL_DIR}/gaiops-worker..."
install -o root -g root -m 0755 "$TMP_DIR/gaiops-worker" "${INSTALL_DIR}/gaiops-worker"

# Create directories
info "==> Creating config and data directories..."
mkdir -p "$CONFIG_DIR"
mkdir -p "$DATA_DIR"
chown "$WORKER_USER:" "$DATA_DIR"

# Generate config
if [ ! -f "${CONFIG_DIR}/worker.yaml" ]; then
  WORKER_ID="${WORKER_ID:-$(hostname)}"
  MASTER_URL="${MASTER_URL:-ws://localhost:8080/ws}"
  CLUSTER_TOKEN="${CLUSTER_TOKEN:-}"

  info "==> Generating config: ${CONFIG_DIR}/worker.yaml"
  cat > "${CONFIG_DIR}/worker.yaml" << EOF
# gAIOps Worker Agent Configuration
worker_id: "${WORKER_ID}"
master_url: "${MASTER_URL}"
cluster_token: "${CLUSTER_TOKEN}"

heartbeat_interval: 15
reconnect:
  base_delay: 1
  max_delay: 60
  max_attempts: 0

max_concurrent_tools: 10
data_dir: "${DATA_DIR}"

logging:
  level: "info"
  format: "json"

tools:
  exec:
    allowed_commands:
      - "/usr/bin/systemctl"
      - "/usr/bin/docker"
      - "/bin/df"
      - "/bin/ls"
      - "/usr/bin/tail"
      - "/usr/bin/grep"
      - "/usr/bin/journalctl"
      - "/bin/cat"
      - "/bin/ps"
      - "/usr/bin/top"

# Path safety constraints
allowed_log_paths:
  - "/var/log"
allowed_disk_paths:
  - "/"
EOF
  chmod 600 "${CONFIG_DIR}/worker.yaml"
fi

# Install systemd service
if command -v systemctl &>/dev/null; then
  info "==> Installing systemd service..."
  cat > /etc/systemd/system/gaiops-worker.service << EOF
[Unit]
Description=gAIOps Worker Agent
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=${WORKER_USER}
ExecStart=${INSTALL_DIR}/gaiops-worker --config ${CONFIG_DIR}/worker.yaml
Restart=always
RestartSec=5
LimitNOFILE=65536

# Security hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=${DATA_DIR} /var/log
CapabilityBoundingSet=~CAP_SYS_ADMIN CAP_NET_ADMIN CAP_SYS_PTRACE
ProtectKernelModules=yes
ProtectKernelTunables=yes

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  info "==> Starting gAIOps Worker..."
  systemctl enable gaiops-worker
  systemctl start gaiops-worker
  info "    Status: systemctl status gaiops-worker"
elif command -v launchctl &>/dev/null; then
  info "==> Installing launchd plist (macOS)..."
  cat > /Library/LaunchDaemons/io.gaiops.worker.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>io.gaiops.worker</string>
    <key>ProgramArguments</key>
    <array>
        <string>${INSTALL_DIR}/gaiops-worker</string>
        <string>--config</string>
        <string>${CONFIG_DIR}/worker.yaml</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>5</integer>
</dict>
</plist>
EOF
  launchctl load /Library/LaunchDaemons/io.gaiops.worker.plist
  info "    Started via launchctl"
else
  warn "No systemd or launchctl found. Manual start required:"
  warn "  ${INSTALL_DIR}/gaiops-worker --config ${CONFIG_DIR}/worker.yaml"
fi

info ""
info "==> Installation complete!"
info "    Binary: ${INSTALL_DIR}/gaiops-worker"
info "    Config: ${CONFIG_DIR}/worker.yaml"
info "    Data:   ${DATA_DIR}"
info ""
info "    To verify: ${INSTALL_DIR}/gaiops-worker --help"
info "    To check status: systemctl status gaiops-worker"
