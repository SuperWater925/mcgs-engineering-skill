"""Packaged Pro engineering entry. Explicit .scope.json selects the task roots."""
from pathlib import Path
import runpy
import sys

def main():
    # This is a package asset location, never an inference of project/task roots.
    entry = Path(__file__).absolute().parent.parent / "assets" / "pro-native-bridge" / "client" / "native_engineering.py"
    if not entry.is_file():
        raise FileNotFoundError("Native engineering client is missing: " + str(entry))
    sys.path.insert(0, str(entry.parent))
    runpy.run_path(str(entry), run_name="__main__")


if __name__ == "__main__":
    main()
