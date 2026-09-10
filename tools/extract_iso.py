#!/usr/bin/env python3
"""Pull the game binaries out of Trespasser.iso into _iso/.

Nothing from the disc is committed to this repo; this is how you get your own
copy in place. Needs 7-Zip.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ponytail: shelling out to 7z beats a pure-Python ISO9660 reader we'd own forever
SEVENZIP_CANDIDATES = [
    "7z",
    r"C:\Program Files\7-Zip\7z.exe",
    r"C:\Program Files (x86)\7-Zip\7z.exe",
]

# The executables and DLLs we analyse. Assets stay on the disc until we need them.
WANTED = ["setup/*.exe", "setup/*.dll", "setup/*.DLL", "Readme.txt",
          "UPDATE/tresp1_1/PatchEXEOnly.exe"]


def find_7z():
    for c in SEVENZIP_CANDIDATES:
        if Path(c).exists() or shutil.which(c):
            return c
    sys.exit("7-Zip not found. Install it, or put 7z on PATH.")


def main():
    iso = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "Trespasser.iso"
    if not iso.exists():
        sys.exit(f"No ISO at {iso}. Put your Trespasser disc image there.")

    out = ROOT / "_iso"
    cmd = [find_7z(), "x", str(iso), f"-o{out}", *WANTED, "-y"]
    if subprocess.run(cmd, stdout=subprocess.DEVNULL).returncode != 0:
        sys.exit("extraction failed")

    exes = sorted(out.glob("setup/tpass*.exe"))
    if not exes:
        sys.exit("extraction ran but found no tpass*.exe — wrong disc image?")
    for e in exes:
        print(f"  {e.relative_to(ROOT)}  {e.stat().st_size:,} bytes")
    print(f"\n{len(exes)} game builds extracted. Now run: python tools/recon.py")


if __name__ == "__main__":
    main()
