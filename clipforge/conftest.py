"""
pytest configuration — adds the clipforge/ directory to sys.path so
`import engine.*` works without installation.
"""

import sys
import pathlib

# Add clipforge/ parent to path so `engine` is importable
sys.path.insert(0, str(pathlib.Path(__file__).parent))

