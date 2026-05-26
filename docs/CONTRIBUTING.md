# Contributing to gAIOps

## PR Workflow

1. Create a feature branch from `main`: `git checkout -b feat/my-feature`
2. Make changes and add tests
3. Run `make lint && make test` locally
4. Commit with conventional prefixes:
   - `feat:` / `fix:` / `chore:` / `docs:` / `refactor:` / `test:`
   - Optional scope: `(worker)` / `(master)` / `(brain)` / `(ci)` / `(docker)`
   - Example: `feat(worker): add /health HTTP endpoint`
5. Push and open a PR against `main`

## Coding Standards

### Go (Worker)
- Pass `golangci-lint` with errcheck, govet, staticcheck enabled
- `gofmt` + `goimports` for formatting
- Tests: table-driven tests for every public function

### TypeScript (Master)
- Pass `tsc --noEmit` type checking
- Pass `eslint` with `@typescript-eslint` rules
- Tests with `jest`, located in `__tests__/` directories

### Python (Brain)
- Pass `ruff` checks (select E, F, I, N, W)
- Tests with `pytest`
- Type hints on all function signatures

## Testing

Run full suite:
```bash
make test
```

Single layer:
```bash
make test-worker  # Go
make test-master  # TypeScript
make test-brain   # Python
```

## Project Structure

- `brain/` — Python/LangGraph decision engine
- `master/` — TypeScript/Node.js scheduler
- `worker/` — Go remote executor
- `proto/` — Shared protocol definitions
- `docs/` — Documentation
