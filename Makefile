.PHONY: help install dev test lint format clean enroll run run-dry run-modules

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

help:
	@echo "FaceLock Development Commands"
	@echo "=============================="
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install production dependencies"
	@echo "  make dev              Install dev dependencies"
	@echo ""
	@echo "Running:"
	@echo "  make enroll           Start enrollment UI (register faces)"
	@echo "  make run-dry          Run daemon in dry-run mode (no lock)"
	@echo "  make run              Run daemon with live locking ⚠️"
	@echo "  make run-modules      Run all module self-tests"
	@echo ""
	@echo "Development:"
	@echo "  make test             Run pytest suite"
	@echo "  make test-cov         Run tests with coverage report"
	@echo "  make lint             Check code with ruff"
	@echo "  make format           Format code with black"
	@echo "  make format-check     Check formatting with black"
	@echo "  make clean            Remove cache and build files"

install:
	@echo "Installing production dependencies..."
	$(PIP) install -r requirements.txt

dev:
	@echo "Installing dev dependencies..."
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt

test:
	@echo "Running pytest..."
	$(PYTHON) -m pytest tests/ -v

test-cov:
	@echo "Running pytest with coverage..."
	$(PYTHON) -m pytest tests/ -v --cov=modules --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

lint:
	@echo "Linting with ruff..."
	$(PYTHON) -m ruff check . --exclude tests/

format:
	@echo "Formatting with black..."
	$(PYTHON) -m black . --exclude tests/

format-check:
	@echo "Checking format with black..."
	$(PYTHON) -m black --check . --exclude tests/

enroll:
	@echo "Starting enrollment UI..."
	$(PYTHON) enrollment_ui.py

run-dry:
	@echo "Running FaceLock in dry-run mode (no session lock)..."
	@echo "Press Ctrl+C to stop"
	$(PYTHON) main.py --no-lock

run:
	@echo "⚠️  Starting FaceLock with LIVE locking enabled!"
	@echo "Make sure you've enrolled a face first with: make enroll"
	@echo "Press Ctrl+C to stop"
	$(PYTHON) main.py

run-modules:
	@echo "Testing individual modules..."
	@echo ""
	@echo "1. Testing camera handler..."
	$(PYTHON) -m modules.camera_handler 2>&1 | head -20 || true
	@echo ""
	@echo "2. Testing face detector..."
	$(PYTHON) -m modules.face_detector 2>&1 | head -20 || true
	@echo ""
	@echo "3. Testing face encoder..."
	$(PYTHON) -m modules.face_encoder 2>&1 | head -20 || true
	@echo ""
	@echo "4. Testing face authenticator..."
	$(PYTHON) -m modules.face_authenticator 2>&1 | head -20 || true
	@echo ""
	@echo "5. Testing database..."
	$(PYTHON) -m modules.database

clean:
	@echo "Cleaning up..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov .ruff_cache
	@echo "Done!"
