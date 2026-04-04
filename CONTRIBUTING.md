# Contributing to FaceLock

Thank you for your interest in contributing to FaceLock! This guide will help you get started.

## Development Setup

### 1. Clone and Install

```bash
cd FaceLock
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
make dev
```

### 2. Quick Commands

```bash
# Run tests
make test

# Run tests with coverage
make test-cov

# Lint code
make lint

# Format code
make format

# See all commands
make help
```

## Architecture

FaceLock is organized into modular components:

```
FaceLock/
├── main.py                  # Main daemon (state machine & loop)
├── enrollment_ui.py         # GUI for enrolling faces
└── modules/
    ├── camera_handler.py    # Webcam capture & brightness correction
    ├── face_detector.py     # Face detection & alignment (MediaPipe)
    ├── face_encoder.py      # Feature extraction (dlib)
    ├── face_authenticator.py # Face matching & authentication
    ├── database.py          # Encrypted local storage
    └── system_controller.py # OS-level session locking
```

## Testing

### Unit Tests

Run all tests:
```bash
make test
```

Run a specific test file:
```bash
pytest tests/test_database.py -v
```

Run a specific test:
```bash
pytest tests/test_database.py::TestDatabaseRoundTrip::test_add_and_retrieve_user -v
```

### Coverage

Generate coverage report:
```bash
make test-cov
```

View HTML report:
```bash
open htmlcov/index.html  # macOS
```

### Module Self-Tests

Each module has a built-in self-test:
```bash
# Test camera
python -m modules.camera_handler

# Test face detector
python -m modules.face_detector

# Test database
python -m modules.database
```

## Code Quality

### Linting

Check for style issues:
```bash
make lint
```

### Formatting

Format code automatically:
```bash
make format
```

Check formatting without changing files:
```bash
make format-check
```

## Making Changes

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Keep changes focused and atomic
   - Write clear commit messages

3. **Test your changes**
   ```bash
   make test
   make lint
   make format-check
   ```

4. **Push and open a PR**
   ```bash
   git push origin feature/your-feature-name
   ```

## Common Tasks

### Adding a New Test

Create a test file in `tests/` following the naming convention `test_*.py`:

```python
import pytest
import numpy as np
from modules.your_module import your_function

def test_your_function():
    """Test description."""
    result = your_function(...)
    assert result == expected
```

### Updating Dependencies

Update `requirements.txt` or `requirements-dev.txt`, then:
```bash
pip install -r requirements.txt
```

### Debugging Issues

**Enable verbose logging:**
```bash
python main.py --no-lock 2>&1 | grep ERROR
```

**Test with dry-run mode first:**
```bash
make run-dry
```

**Run module tests individually:**
```bash
python -m modules.face_detector
```

## Code Style

- **Python Version:** 3.10+
- **Formatting:** Black
- **Linting:** Ruff
- **Type Hints:** Recommended (checked with mypy)
- **Docstrings:** Google-style with parameter/return docs

## Documentation

- Update `QUICKSTART.md` for user-facing changes
- Update docstrings in modules for API changes
- Keep comments clear and concise

## Security Considerations

- Never commit database files or credentials
- Test encryption/decryption thoroughly
- Review any changes to `database.py` or `system_controller.py`
- Keep dependencies up to date

## Need Help?

- Check `QUICKSTART.md` for usage
- Look at existing tests for examples
- Review module docstrings
- Open an issue with details

---

**Happy coding!** 🚀
