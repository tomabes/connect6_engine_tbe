"""Build the authors' Cloudict sources for the current Mac; never runs the engine."""

import argparse
from pathlib import Path
import subprocess
import shutil
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, help="Optional installed macOS SDK directory")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    sdk = args.sdk or Path(subprocess.check_output(
        ["xcrun", "--show-sdk-path"], text=True).strip())
    headers = sdk / "usr/include/c++/v1"
    if not (headers / "vector").is_file():
        raise FileNotFoundError(f"C++ headers missing in {headers}; specify --sdk")
    output = root.parent / "tbe_gui/engines/cloudict_native"
    if output.exists():
        output.read_bytes()  # Reread the current artifact before preserving it.
        snapshot = root.parent / "backups" / datetime.now().strftime("%Y%m%d-%H%M%S") / "tbe_gui/engines/cloudict_native"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output, snapshot)
        print("Previous executable saved:", snapshot)
    subprocess.run(["clang++", "-std=c++11", "-O2", "-isysroot", str(sdk),
                    "-isystem", str(headers),
                    *[str(p) for p in sorted((root / "src").glob("*.cc"))],
                    "-o", str(output)], check=True)
    print("Built:", output)


if __name__ == "__main__":
    main()
