"""
pytest configuration and shared fixtures for FaceLock tests.
"""

import sys
from pathlib import Path

# Add the project root to sys.path so modules can be imported
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
