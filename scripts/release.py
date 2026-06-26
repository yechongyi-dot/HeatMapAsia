#!/usr/bin/env python
"""Build the app and publish a GitHub Release for the in-app updater.

The in-app updater (web/update.py) looks at the *latest* GitHub Release and
compares its tag (e.g. ``v0.2.0``) against ``version.__version__``. To ship an
update:

    1. Bump ``__version__`` in version.py
    2. Run this script

Usage:
    python scripts/release.py             # PyInstaller build + zip + gh release
    python scripts/release.py --no-build  # reuse existing dist/HeatMap

Requires: pyinstaller (pip), gh CLI (authenticated: ``gh auth login``).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from version import __version__  # noqa: E402


def run(cmd: list, **kw) -> None:
    print(">", " ".join(map(str, cmd)))
    subprocess.run(cmd, check=True, **kw)


def _gh() -> str:
    return shutil.which("gh") or r"C:\Program Files\GitHub CLI\gh.exe"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-build", action="store_true", help="skip PyInstaller, reuse dist/HeatMap")
    ap.add_argument("--notes", default="", help="release notes (markdown)")
    args = ap.parse_args()

    tag = f"v{__version__}"
    dist = ROOT / "dist" / "HeatMapAsia"

    if not args.no_build:
        run([sys.executable, "-m", "PyInstaller", "--noconfirm", "HeatMapAsia.spec"], cwd=ROOT)

    if not (dist / "HeatMapAsia.exe").exists():
        sys.exit(f"build output not found: {dist / 'HeatMapAsia.exe'}")

    # Zip the *contents* of dist/HeatMapAsia so the archive root holds
    # HeatMapAsia.exe (matches what web/update.py expects when extracting).
    zip_path = ROOT / f"HeatMapAsia-{tag}.zip"
    zip_path.unlink(missing_ok=True)
    print(f"zipping {dist} -> {zip_path.name}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in dist.rglob("*"):
            zf.write(p, p.relative_to(dist))

    notes = args.notes or f"HeatMap-Asia {tag}"
    run([_gh(), "release", "create", tag, str(zip_path), "-t", tag, "-n", notes], cwd=ROOT)
    print(f"\n[OK] Published {tag}. Existing clients will offer this update on next launch.")


if __name__ == "__main__":
    main()
