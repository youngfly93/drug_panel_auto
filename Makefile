.PHONY: dev dev-backend dev-frontend build test install clean

# Install all dependencies
install:
	cd backend && pip install -e ".[dev]"
	cd ../基因组panel自动化系统 && pip install -e .
	cd frontend && npm install

# Development: run backend + frontend in parallel
dev:
	@echo "Starting backend (port 8000) + frontend (port 5173)..."
	@trap 'kill 0' EXIT; \
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 & \
	cd frontend && npm run dev & \
	wait

dev-backend:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev

# Build frontend for production
build:
	cd frontend && npm run build
	rm -rf backend/static
	cp -r frontend/dist backend/static

# Run tests
test:
	cd backend && pytest tests/ -v

# Clean generated files
clean:
	rm -rf backend/static
	rm -rf frontend/dist
	rm -rf backend/__pycache__ backend/app/__pycache__
	find backend -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
