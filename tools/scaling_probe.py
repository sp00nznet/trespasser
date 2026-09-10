#!/usr/bin/env python3
"""Measure how disasm32.py's runtime scales with code size.

The retail image has not converged in 3h20m of CPU. Before anyone optimises
anything, establish the complexity class from data: run the real tool over a
ladder of real binaries and fit an exponent to (code_bytes -> seconds).

Usage: python tools/scaling_probe.py [--timeout SEC]
"""
import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DISASM = ROOT.parent / "tools" / "tools" / "disasm" / "disasm32.py"

# A size ladder of ordinary 32-bit PEs that happen to be lying around on the
# disc. Nothing special about them beyond spanning ~16 KB to ~2.5 MB.
LADDER = [
    "_iso/setup/DisableAudio.exe",
    "_iso/setup/dxinst.exe",
    "_iso/setup/Processor.dll",
    "_iso/setup/dsetup32.dll",
    "_iso/setup/dsetup16.dll",
    "_iso/setup/SMACKW32.DLL",
    "_iso/setup/dsetup.dll",
    "_iso/setup/MSVCRT.DLL",
    "_iso/Ip.exe",
    "_iso/setup/setup95.exe",
    "_iso/setup/tpassk6.exe",
]


def code_bytes(path):
    """Size of the executable sections, which is what the tool actually walks."""
    import struct
    d = path.read_bytes()
    pe = struct.unpack("<I", d[0x3C:0x40])[0]
    if d[pe:pe + 4] != b"PE\0\0":
        return None
    nsec = struct.unpack("<H", d[pe + 6:pe + 8])[0]
    opt = struct.unpack("<H", d[pe + 20:pe + 22])[0]
    off = pe + 24 + opt
    total = 0
    for i in range(nsec):
        s = d[off + i * 40:off + (i + 1) * 40]
        vs = struct.unpack("<I", s[8:12])[0]
        chars = struct.unpack("<I", s[36:40])[0]
        if chars & 0x20000000:      # IMAGE_SCN_MEM_EXECUTE
            total += vs
    return total


def fit_exponent(points):
    """Least-squares slope of log(time) vs log(size) — the exponent n in O(size^n)."""
    pts = [(math.log(s), math.log(t)) for s, t in points if s > 0 and t > 0]
    if len(pts) < 2:
        return None
    n = len(pts)
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    num = sum((x - mx) * (y - my) for x, y in pts)
    den = sum((x - mx) ** 2 for x, _ in pts)
    return num / den if den else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=900,
                    help="per-binary timeout in seconds (default 900)")
    ap.add_argument("-o", "--output", default="analysis/scaling.json")
    args = ap.parse_args()

    if not DISASM.exists():
        sys.exit(f"no disasm32.py at {DISASM}")

    rows = []
    for rel in LADDER:
        p = ROOT / rel
        if not p.exists():
            print(f"  skip {rel} (missing)")
            continue
        cb = code_bytes(p)
        if not cb:
            print(f"  skip {rel} (not a PE32)")
            continue

        t0 = time.perf_counter()
        try:
            r = subprocess.run(
                [sys.executable, str(DISASM), str(p)],
                capture_output=True, text=True, timeout=args.timeout)
            elapsed = time.perf_counter() - t0
            timed_out = False
            nfunc = None
            for line in r.stdout.splitlines():
                if line.startswith("[*] Functions:"):
                    nfunc = int(line.split(":")[1].split("(")[0].strip())
        except subprocess.TimeoutExpired:
            elapsed = time.perf_counter() - t0
            timed_out = True
            nfunc = None

        rows.append({"file": rel, "code_bytes": cb, "seconds": round(elapsed, 2),
                     "functions": nfunc, "timed_out": timed_out})
        flag = "  TIMEOUT" if timed_out else ""
        print(f"  {Path(rel).name:22} code {cb:>9,}  {elapsed:8.2f}s  "
              f"funcs {nfunc if nfunc is not None else '-':>6}{flag}")

    done = [(r["code_bytes"], r["seconds"]) for r in rows if not r["timed_out"]]
    exp = fit_exponent(done)
    out = {"rows": rows, "exponent": exp}
    (ROOT / args.output).write_text(json.dumps(out, indent=1))

    print()
    if exp is not None:
        print(f"fitted exponent: O(code^{exp:.2f})  over {len(done)} completed points")
        if exp > 1.5:
            print("  -> superlinear. Doubling the binary more than doubles the work.")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
