"""
conftest.py (Repo-Wurzel)
Macht die Engine-Module unter mcp/ importierbar, damit die Tests unter tests/
sowohl mit `pytest` als auch mit dem dependency-freien Runner `python tests/run.py`
laufen. KEINE Testlogik hier — nur sys.path-Setup (pytest lädt conftest automatisch
vor dem Einsammeln der Testmodule).
"""
import sys
from pathlib import Path

_MCP = Path(__file__).resolve().parent / "mcp"
if str(_MCP) not in sys.path:
    sys.path.insert(0, str(_MCP))
