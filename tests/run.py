"""
run.py — dependency-freier Test-Runner (kein pytest nötig)
Sammelt alle test_*-Funktionen aus tests/test_*.py, führt sie aus und meldet
PASS/FAIL. Liefert das von einigen Tests genutzte `tmp_path`-Fixture (ein frisches
Temp-Verzeichnis je Test) nach, sodass exakt dieselben Funktionen später auch unter
`pytest` laufen. Exit 1, sobald ein Test scheitert (taugt damit als CI-Gate).

Aufruf:  python tests/run.py
"""
import importlib.util
import inspect
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mcp"))  # Engine importierbar machen
sys.stdout.reconfigure(encoding="utf-8")


def _load(modpath: Path):
    spec = importlib.util.spec_from_file_location(modpath.stem, modpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    bestanden, gescheitert = 0, []
    for modpath in sorted((ROOT / "tests").glob("test_*.py")):
        mod = _load(modpath)
        for name, fn in sorted(vars(mod).items()):
            if not (name.startswith("test_") and callable(fn) and inspect.isfunction(fn)):
                continue
            params = inspect.signature(fn).parameters
            try:
                if "tmp_path" in params:
                    with tempfile.TemporaryDirectory() as d:
                        fn(Path(d))
                else:
                    fn()
                bestanden += 1
                print(f"  PASS  {modpath.stem}::{name}")
            except Exception:  # noqa: BLE001 — Test-Runner fängt bewusst alles
                gescheitert.append(f"{modpath.stem}::{name}")
                print(f"  FAIL  {modpath.stem}::{name}")
                traceback.print_exc()

    print("-" * 60)
    print(f"{bestanden} bestanden, {len(gescheitert)} gescheitert")
    if gescheitert:
        print("Gescheitert:\n  - " + "\n  - ".join(gescheitert))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
