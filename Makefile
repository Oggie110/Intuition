.PHONY: dev-up dev-backend dev-web check-venv check-web-deps

check-venv:
	@if [ ! -x ".venv/bin/python" ]; then \
		echo "Missing .venv. Run: python3 -m venv .venv && .venv/bin/python -m pip install -r backend/requirements.txt"; \
		exit 1; \
	fi

check-web-deps:
	@if [ ! -d "web/node_modules" ]; then \
		echo "Missing web/node_modules. Run: cd web && pnpm install"; \
		exit 1; \
	fi

dev-backend: check-venv
	.venv/bin/python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8010

dev-web: check-web-deps
	cd web && pnpm dev --port 3010

dev-up: check-venv check-web-deps
	@echo "Starting backend on :8010 and frontend on :3010 (Ctrl+C stops both)"
	@trap 'kill 0' INT TERM EXIT; $(MAKE) -j2 dev-backend dev-web
