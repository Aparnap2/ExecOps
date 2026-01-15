"""Pytest configuration for ai_service tests."""

import sys
from pathlib import Path

# Add src directory to Python path - the actual package is under src/ai_service
_src_path = Path(__file__).parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

# Verify the package is accessible
try:
    import ai_service
    print(f"ai_service package loaded from: {ai_service.__file__}")
except ImportError as e:
    print(f"Warning: Could not import ai_service: {e}")
