#!/usr/bin/env python3
"""Turn a linker .map into a ground-truth function table.

The oracle build (see docs/VALIDATION.md) is the reference source compiled with
MSVC and linked with /MAP. The map names every symbol and its address, which is
exactly what we need to score pcrecomp's function recovery against.

Emits JSON: {"image_base":..., "code_sections":[...], "functions":[{rva,va,name,section}]}
"""
import json
import re
import sys
from pathlib import Path

# " 0001:00000000 0003c170H .text                   CODE"
SEC_RE = re.compile(r"^\s*([0-9a-fA-F]{4}):([0-9a-fA-F]{8})\s+([0-9a-fA-F]+)H\s+(\S+)\s+(CODE|DATA)\s*$")
# " 0001:00048470  ?Foo@@YAXXZ    00449470 f   Lib:obj"
# group order: sect, offset, name, rva+base, flags/lib tail
SYM_RE = re.compile(r"^\s*([0-9a-fA-F]{4}):([0-9a-fA-F]{8})\s+(\S+)\s+([0-9a-fA-F]{8})\s+(.*)$")


def parse(path):
    base = None
    sections = {}      # sect index -> list of (start, length, name, klass)
    syms = []
    mode = None
    for line in Path(path).read_text(errors="replace").splitlines():
        if base is None:
            m = re.match(r"\s*Preferred load address is ([0-9a-fA-F]+)", line)
            if m:
                base = int(m.group(1), 16)
                continue
        if "Publics by Value" in line:
            mode = "pub"; continue
        if line.strip() == "Static symbols":
            mode = "static"; continue

        m = SEC_RE.match(line)
        if m and mode is None:
            sect = int(m.group(1), 16)
            sections.setdefault(sect, []).append(
                (int(m.group(2), 16), int(m.group(3), 16), m.group(4), m.group(5)))
            continue

        if mode:
            m = SYM_RE.match(line)
            if m:
                # "f" in the flags column marks a function; "f i" is an inline/COMDAT
                # function. Data symbols have no f. Keep only functions.
                tail = m.group(5)
                flags = tail.split()[0] if tail.split() else ""
                syms.append({
                    "sect": int(m.group(1), 16),
                    "va": int(m.group(4), 16),
                    "name": m.group(3),
                    "is_func": flags.startswith("f"),
                    "static": mode == "static",
                })
    return base, sections, syms


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: parse_map.py <trespass.map> [-o out.json]")
    src = sys.argv[1]
    base, sections, syms = parse(src)
    if base is None:
        sys.exit("no 'Preferred load address' line — is this an MSVC linker map?")

    code_sects = {i for i, entries in sections.items()
                  if any(k == "CODE" for *_, k in entries)}
    funcs = sorted((s for s in syms if s["is_func"] and s["sect"] in code_sects),
                   key=lambda s: s["va"])

    # Deduplicate identical addresses (COMDAT folding gives one address many names)
    byva = {}
    for f in funcs:
        byva.setdefault(f["va"], []).append(f["name"])

    out = {
        "source": Path(src).name,
        "image_base": base,
        "code_sections": sorted(code_sects),
        "stats": {
            "symbols_total": len(syms),
            "functions": len(funcs),
            "distinct_addresses": len(byva),
            "folded": len(funcs) - len(byva),
            "static_functions": sum(1 for f in funcs if f["static"]),
        },
        "functions": [{"va": va, "names": names} for va, names in sorted(byva.items())],
    }

    dest = None
    if "-o" in sys.argv:
        dest = sys.argv[sys.argv.index("-o") + 1]
    if dest:
        Path(dest).write_text(json.dumps(out, indent=1))

    st = out["stats"]
    print(f"image base      0x{base:08X}")
    print(f"code sections   {sorted(code_sects)}")
    print(f"symbols         {st['symbols_total']:,}")
    print(f"functions       {st['functions']:,}")
    print(f"distinct addrs  {st['distinct_addresses']:,}  (COMDAT-folded: {st['folded']:,})")
    print(f"  of which static {st['static_functions']:,}")
    if dest:
        print(f"wrote {dest}")


if __name__ == "__main__":
    main()
