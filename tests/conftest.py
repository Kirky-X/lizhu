import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "scripts"
for p in (ROOT / "pdf-parse", ROOT / "md-normalizer"):
    sys.path.insert(0, str(p))
