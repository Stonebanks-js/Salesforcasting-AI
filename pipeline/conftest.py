import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Insert order matters: `tests` package must resolve to backend/tests (fakes).
sys.path.insert(0, str(Path(__file__).resolve().parent))  # transforms.*
sys.path.insert(0, str(ROOT / "backend"))                 # tests.fakes
sys.path.insert(0, str(ROOT))                             # ml.*
