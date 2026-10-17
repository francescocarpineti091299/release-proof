from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parent / "backend"))
