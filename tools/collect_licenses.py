"""Copy license texts from the exact distributions used to build the EXEs."""
import importlib.metadata
from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parents[1]
dest = root / "dist" / "licenses"
dest.mkdir(parents=True, exist_ok=True)
for name in ("PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6", "PyInstaller"):
    distribution = importlib.metadata.distribution(name)
    for f in distribution.files or []:
        if any("license" in part.lower() or "copying" in part.lower() for part in f.parts):
            source = Path(distribution.locate_file(f))
            if source.is_file():
                target = dest / name / Path(*f.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
base = Path(sys.base_prefix)
for source in (base / "LICENSE.txt", base / "LICENSE", base / "lib" / "python3.13" / "LICENSE.txt"):
    if source.is_file():
        shutil.copy2(source, dest / "Python-LICENSE.txt")
        break
print(f"Collected {sum(1 for p in dest.rglob('*') if p.is_file())} license files")
