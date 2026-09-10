#!/usr/bin/env python3
"""Regenerate everything in analysis/ from the extracted game binaries.

Drives the pcrecomp tools over tpassp6.exe and pulls the RTTI class names out
of the image. Safe to re-run; it overwrites.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PCRECOMP = ROOT.parent / "tools" / "tools"   # sibling checkout of pcrecomp
TARGET = ROOT / "_iso" / "setup" / "tpassp6.exe"
OUT = ROOT / "analysis"

# MSVC RTTI type descriptors: ".?AV<name>@@" for classes, ".?AU" for structs.
RTTI_RE = re.compile(rb"\.\?A[VU][A-Za-z0-9_?$@]{2,200}")


def run(script, *args, capture_to=None):
    """Run a pcrecomp tool. Returns False if it's missing or fails."""
    path = PCRECOMP / script
    if not path.exists():
        print(f"  skip {script} (no pcrecomp checkout at {PCRECOMP})")
        return False
    cmd = [sys.executable, str(path), *args]
    if capture_to:
        with open(capture_to, "w") as fh:
            rc = subprocess.run(cmd, stdout=fh).returncode
    else:
        rc = subprocess.run(cmd).returncode
    if rc != 0:
        print(f"  {script} exited {rc}")
    return rc == 0


def extract_rtti(exe, dest):
    """Class names, straight out of the image. This is the free win."""
    names = sorted({m.group().decode("latin1") for m in RTTI_RE.finditer(exe.read_bytes())})
    dest.write_text("\n".join(names) + "\n")
    return names


def main():
    if not TARGET.exists():
        sys.exit(f"No {TARGET.relative_to(ROOT)} — run tools/extract_iso.py first.")
    OUT.mkdir(exist_ok=True)

    print(f"Target: {TARGET.name}  ({TARGET.stat().st_size:,} bytes)\n")

    names = extract_rtti(TARGET, OUT / "rtti.txt")
    print(f"  rtti.txt          {len(names)} class names")

    run("pe/pe_analyze.py", str(TARGET), "--json", capture_to=OUT / "pe.json")
    run("pe/analyze_sections.py", str(TARGET), capture_to=OUT / "sections.txt")
    run("pe/extract_imports.py", str(TARGET), capture_to=OUT / "imports.txt")

    # Slow — several minutes over 2.3 MB of code. Last, so the rest is already written.
    print("\n  disassembling (this takes a while)...")
    run("disasm/disasm32.py", str(TARGET), "-o", str(OUT / "functions.json"))

    print(f"\nWrote {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
