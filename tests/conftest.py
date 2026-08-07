"""Pytest configuration for cement_app.

Makes the project root importable so tests can `import chemistry` etc.
Run from cement_app/ with:  python -m pytest tests/ -v
"""

import os
import sys

# Ensure the cement_app directory (parent of tests/) is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
