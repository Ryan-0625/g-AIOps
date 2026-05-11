.PHONY: build build-worker build-master test test-worker test-master test-brain \
        lint lint-worker lint-master lint-brain run run-worker run-master run-brain \
        clean dev-up dev-down init

# === 构建 ===

build: build-worker build-master
	@echo "[+] All builds completed"

build-worker:
	@echo "[+] Building Worker..."
	cd worker && go build -o worker ./cmd/worker/
	@echo "[+] Worker build OK"

build-master:
	@echo "[+] Building Master..."
	cd master && npm run build
	@echo "[+] Master build OK"

# === 测试 ===

test: test-worker test-master test-brain
	@echo "[+] All tests passed"

test-worker:
	cd worker && go test -v -race -count=1 ./... 2>&1 | tail -20

test-master:
	cd master && npm test 2>&1 | tail -20

test-brain:
	cd brain && python -m pytest -v --tb=short 2>&1 | tail -20

# === 代码检查 ===

lint: lint-worker lint-master lint-brain

lint-worker:
	cd worker && go vet ./...
	command -v golangci-lint >/dev/null && golangci-lint run ./... || true

lint-master:
	cd master && npx tsc --noEmit
	command -v eslint >/dev/null && npx eslint src/ || true

lint-brain:
	cd brain && python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	cd brain && python -m mypy . --ignore-missing-imports || true

# === 运行 ===

run-worker:
	cd worker && go run ./cmd/worker/

run-master:
	cd master && npm run dev

run-brain:
	cd brain && python main.py

# === 开发环境 ===

dev-up:
	@echo "[+] Starting gAIOps dev environment..."
	@mkdir -p /tmp/gaiops/logs
	@echo "[+] Checking dependencies..."
	@curl -sf http://localhost:11434/api/tags > /dev/null 2>&1 || (echo "[!] Ollama is not running. Start it first: ollama serve"; exit 1)
	@echo "[+] Starting Master..."
	cd master && npm run dev > /tmp/gaiops/logs/master.log 2>&1 & echo $$! > /tmp/gaiops/master.pid
	@sleep 2
	@curl -sf http://localhost:8080/health > /dev/null 2>&1 || (echo "[!] Master failed to start"; exit 1)
	@echo "[+] Master OK (pid $$(cat /tmp/gaiops/master.pid))"
	@echo "[+] Starting Worker..."
	cd worker && go run ./cmd/worker/ > /tmp/gaiops/logs/worker.log 2>&1 & echo $$! > /tmp/gaiops/worker.pid
	@sleep 1
	@echo "[+] Worker started (pid $$(cat /tmp/gaiops/worker.pid))"
	@echo "[+] Starting Brain..."
	cd brain && python main.py > /tmp/gaiops/logs/brain.log 2>&1 & echo $$! > /tmp/gaiops/brain.pid
	@echo "[+] Brain started (pid $$(cat /tmp/gaiops/brain.pid))"
	@echo "[+] All services started. Logs: /tmp/gaiops/logs/"

dev-down:
	@echo "[-] Stopping gAIOps..."
	-kill $$(cat /tmp/gaiops/brain.pid 2>/dev/null) 2>/dev/null
	-kill $$(cat /tmp/gaiops/worker.pid 2>/dev/null) 2>/dev/null
	-kill $$(cat /tmp/gaiops/master.pid 2>/dev/null) 2>/dev/null
	@rm -f /tmp/gaiops/*.pid
	@echo "[-] All services stopped"

dev-logs:
	@tail -f /tmp/gaiops/logs/*.log

dev-trace:
	@if [ -z "$(T)" ]; then echo "Usage: make dev-trace T=<trace_id>"; exit 1; fi
	@grep "$(T)" /tmp/gaiops/logs/*.log 2>/dev/null | sort || echo "No entries found for trace_id=$(T)"

# === 清理 ===

clean:
	rm -f worker/worker worker/worker.exe
	rm -rf master/dist master/node_modules
	find brain -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
	rm -rf /tmp/gaiops

# === 初始化 ===

init: init-worker init-master init-brain

init-worker:
	cd worker && go mod init github.com/your-org/gaiops/worker
	cd worker && go mod tidy

init-master:
	cd master && npm init -y
	cd master && npm install ws uuid express rate-limiter 2>&1 | tail -5
	cd master && npm install -D typescript @types/node @types/ws @types/express @types/uuid 2>&1 | tail -5

init-brain:
	cd brain && pip install langgraph aiohttp pydantic pyyaml 2>&1 | tail -5
