#!/usr/bin/env python3
"""Score disasm32's function recovery against the oracle's ground truth.

The oracle (docs/VALIDATION.md) is the reference source built with MSVC and
linked with /MAP, so we know every function's real address.

  python tools/parse_map.py <trespass.map> -o analysis/oracle_truth.json
  python <pcrecomp>/tools/disasm/disasm32.py trespass.exe -o analysis/oracle_functions.json
  python tools/score_recovery.py --map <trespass.map>

Scoring is per map CODE chunk, and chunks the linker map barely describes are
excluded from the aggregate rather than counted as tool error. That matters:
the plain `.text` chunk is a quarter-megabyte of linked-in library code with
almost no symbols, so scoring it would charge the tool ~8,300 false positives
for finding functions the ground truth simply does not know about. Absence of a
symbol is not evidence of absence of a function.

Comparison is on function *start addresses* — what both sides agree on. Sizes
would need the PDB.
"""
import argparse
import bisect
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# " 0001:00000000 0003c170H .text                   CODE"
CHUNK_RE = re.compile(r"^\s*([0-9a-fA-F]{4}):([0-9a-fA-F]{8})\s+([0-9a-fA-F]+)H\s+(\S+)\s+(CODE|DATA)\s*$")

# Below this many symbols per KB, we treat a chunk as undescribed by the map.
#
# The gap in the data is stark rather than marginal, so this is a judgment call
# made explicit rather than a tuned parameter. Measured densities:
#
#   .text$di  26.3/KB   .text$x  29.1/KB   .text$yd  28.0/KB
#   .text$mn   3.8/KB   SelfMod   0.65/KB  .text     0.06/KB
#
# SelfMod is legitimately sparse -- 37 symbols for a section of ~1.6 KB
# routines -- and is scored. The plain `.text` chunk has 15 symbols across
# 246 KB, and those 15 are the Smacker import thunks; the rest is linked-in
# library code the map never enumerates. Fifteen symbols is not a description
# of a quarter-megabyte, so scoring the 8,300 functions found there would
# charge the tool for ground truth we do not have.
MIN_DENSITY = 0.5


def load(path, what):
    p = Path(path) if Path(path).is_absolute() else ROOT / path
    if not p.exists():
        sys.exit(f"missing {what}: {p}")
    return json.loads(p.read_text())


def code_chunks(map_path, sect_base):
    """CODE chunks from the map header, as (name, start_va, end_va)."""
    out = []
    for line in Path(map_path).read_text(errors="replace").splitlines():
        m = CHUNK_RE.match(line)
        if not m or m.group(5) != "CODE":
            continue
        sect = int(m.group(1), 16)
        if sect not in sect_base:
            continue
        start = sect_base[sect] + int(m.group(2), 16)
        out.append((m.group(4), start, start + int(m.group(3), 16)))
    return sorted(out, key=lambda c: c[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", default="analysis/oracle_truth.json")
    ap.add_argument("--recovered", default="analysis/oracle_functions.json")
    ap.add_argument("--map", default="_work/oracle-build/cmake/trespass/Release/trespass.map")
    ap.add_argument("--show", type=int, default=0)
    args = ap.parse_args()

    truth = load(args.truth, "ground truth (run tools/parse_map.py)")
    rec = load(args.recovered, "recovered functions (run disasm32.py)")

    truth_names = {f["va"]: f["names"] for f in truth["functions"]}
    tv = sorted(truth_names)
    rv = sorted({f["address"] for f in rec["functions"]})
    tset = set(tv)

    # Locate each code section's base from the truth addresses we have for it.
    # Section 1 starts at the tool's code_start; section 2 we infer from the map
    # chunk offsets against the highest-addressed truth symbols.
    sect_base = {}
    for f in truth["functions"]:
        pass
    # Simpler and robust: derive per-section base by matching the map's own
    # section:offset pairs against Rva+Base, done in parse_map. Recompute here
    # from the first chunk of each section.
    base = truth["image_base"]
    raw = Path(args.map).read_text(errors="replace").splitlines()
    for line in raw:
        m = CHUNK_RE.match(line)
        if m and m.group(5) == "CODE":
            sect = int(m.group(1), 16)
            sect_base.setdefault(sect, None)
    # Section 1 base: tool's code_start. Section 2 base: from a SelfMod symbol.
    sect_base[1] = rec["code_start"]
    for line in raw:
        mm = re.match(r"^\s*0002:([0-9a-fA-F]{8})\s+\S+\s+([0-9a-fA-F]{8})\s", line)
        if mm:
            sect_base[2] = int(mm.group(2), 16) - int(mm.group(1), 16)
            break

    chunks = code_chunks(args.map, sect_base)

    print(f"ground truth  {len(tv):,} functions   recovered  {len(rv):,}\n")
    hdr = f"{'chunk':10} {'bytes':>10} {'truth':>7} {'rec':>7} {'tp':>7} {'fp':>7} {'fn':>7}  {'prec':>7} {'recall':>7}"
    print(hdr)
    print("-" * len(hdr))

    agg = {"tp": 0, "fp": 0, "fn": 0, "rec": 0, "truth": 0}
    excluded = []
    for nm, a, b in chunks:
        t = [x for x in tv if a <= x < b]
        r = [x for x in rv if a <= x < b]
        tp = sum(1 for x in r if x in tset)
        fp, fn = len(r) - tp, len(t) - tp
        density = len(t) / max((b - a) / 1024, 1)
        prec = tp / len(r) if r else 0
        recl = tp / len(t) if t else 0
        mark = ""
        if density < MIN_DENSITY:
            mark = "  <- excluded, map has no symbols here"
            excluded.append((nm, len(r)))
        else:
            for k, v in (("tp", tp), ("fp", fp), ("fn", fn),
                         ("rec", len(r)), ("truth", len(t))):
                agg[k] += v
        print(f"{nm:10} {b-a:>10,} {len(t):>7,} {len(r):>7,} {tp:>7,} {fp:>7,} {fn:>7,}  "
              f"{prec:>6.1%} {recl:>7.1%}{mark}")

    p = agg["tp"] / agg["rec"] if agg["rec"] else 0
    r_ = agg["tp"] / agg["truth"] if agg["truth"] else 0
    f1 = 2 * p * r_ / (p + r_) if (p + r_) else 0

    print(f"\nAggregate over map-described chunks only:")
    print(f"  true positives   {agg['tp']:,}")
    print(f"  false positives  {agg['fp']:,}")
    print(f"  false negatives  {agg['fn']:,}")
    print(f"  precision        {p:.2%}")
    print(f"  recall           {r_:.2%}")
    print(f"  F1               {f1:.2%}")
    if excluded:
        tot = sum(n for _, n in excluded)
        print(f"\n  excluded: {', '.join(n for n, _ in excluded)} "
              f"({tot:,} recovered functions unverifiable -- no symbols in the map)")

    # Classify the false positives that remain: a split inside a known function
    # is a different defect from an address invented in data.
    fps = [x for x in rv if x not in tset
           and any(a <= x < b for nm, a, b in chunks
                   if nm not in {n for n, _ in excluded})]
    starts = tv
    inside = 0
    for x in fps:
        i = bisect.bisect_right(starts, x) - 1
        if i >= 0:
            inside += 1
    print(f"\n  of {len(fps):,} false positives, {inside:,} land after some known "
          f"function start\n  (mid-function splits) and {len(fps)-inside:,} before any (invented in data)")

    (ROOT / "analysis/recovery_score.json").write_text(json.dumps({
        "precision": p, "recall": r_, "f1": f1, **agg,
        "excluded_chunks": excluded,
    }, indent=1))
    print("\nwrote analysis/recovery_score.json")


if __name__ == "__main__":
    main()
