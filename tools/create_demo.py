"""Generate synthetic data only; never copy user conversations for screenshots."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "tests"))
from conftest import make_home

destination = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / "artifacts" / "demo-home"
if (destination / "state_5.sqlite").exists():
    raise SystemExit("Demo already exists; choose an empty destination.")
make_home(destination)
print(destination)
