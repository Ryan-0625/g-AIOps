#!/usr/bin/env bash
# Generate self-signed CA + server certificate for development TLS.
# Output: ../certs/ca.pem, ../certs/server.pem, ../certs/server-key.pem
set -euo pipefail

# Prevent Git Bash on Windows from converting /CN to a path.
export MSYS_NO_PATHCONV=1

CERTS_DIR="$(cd "$(dirname "$0")/../certs" && pwd)"
DAYS=3650  # 10 years for dev certs

echo "=== Generating dev TLS certificates ==="
echo "Output dir: $CERTS_DIR"

mkdir -p "$CERTS_DIR"

# --- CA key + cert ---
if [ ! -f "$CERTS_DIR/ca-key.pem" ]; then
  echo ">>> Generating CA key..."
  openssl genrsa -out "$CERTS_DIR/ca-key.pem" 4096
fi

echo ">>> Generating CA certificate..."
openssl req -x509 -new -nodes \
  -key "$CERTS_DIR/ca-key.pem" \
  -sha256 -days "$DAYS" \
  -out "$CERTS_DIR/ca.pem" \
  -subj "/CN=gAIOps Dev CA"

# --- Server key + CSR ---
echo ">>> Generating server key..."
openssl genrsa -out "$CERTS_DIR/server-key.pem" 2048

echo ">>> Generating server CSR..."
openssl req -new \
  -key "$CERTS_DIR/server-key.pem" \
  -out "$CERTS_DIR/server.csr" \
  -subj "/CN=localhost"

# --- Server cert config for SAN ---
SAN_CONFIG="$CERTS_DIR/san.cnf"
cat > "$SAN_CONFIG" <<EOF
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[req_distinguished_name]
CN = localhost

[v3_req]
keyUsage = keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = master
DNS.3 = *.gaiops.internal
IP.1 = 127.0.0.1
EOF

echo ">>> Generating server certificate (signed by CA)..."
openssl x509 -req \
  -in "$CERTS_DIR/server.csr" \
  -CA "$CERTS_DIR/ca.pem" \
  -CAkey "$CERTS_DIR/ca-key.pem" \
  -CAcreateserial \
  -out "$CERTS_DIR/server.pem" \
  -days "$DAYS" \
  -sha256 \
  -extfile "$SAN_CONFIG" \
  -extensions v3_req

# Cleanup
rm -f "$CERTS_DIR/server.csr" "$CERTS_DIR/san.cnf"

echo "=== Done ==="
echo "  CA:       $CERTS_DIR/ca.pem"
echo "  Cert:     $CERTS_DIR/server.pem"
echo "  Key:      $CERTS_DIR/server-key.pem"
echo ""
echo "For Docker, mount $CERTS_DIR to /etc/gaiops/certs"
