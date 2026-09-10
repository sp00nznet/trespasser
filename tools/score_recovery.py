#!/usr/bin/env python3
"""Score function recovery against the oracle's ground truth — for any engine.

The oracle (docs/VALIDATION.md) is the reference source built with MSVC and
linked with /MAP, so we know every function's real address. This scores
pcrecomp's disasm32 against it, and optionally IDA and Ghidra alongside, so we
can tell whether a given number is respectable or embarrassing.

  python tools/parse_map.py <trespass.map> -o analysis/oracle_truth.json
  python <pcrecomp>/tools/disasm/disasm32.py trespass.exe -o analysis/oracle_functions.json
  py -3.11 <pcrecomp>/tools/ida/ida_funcs.py trespass.exe analysis/ida_functions.json
  analyzeHeadless ... -postScript DumpBounds.java analysis/ghidra_bounds.csv
  python tools/score_recovery.py

IDA and Ghidra are comparison baselines only. The point is improving our own
tooling, not depending on theirs — but a reference bar tells us how much of the
gap is our defect and how much is the problem being genuinely hard.

Scoring is per map CODE chunk, and chunks the map barely describes are excluded
rather than counted as engine error: absence of a symbol is not evidence of
absence of a function. Comparison is on function *start addresses*.
"""
import argparse
import bisect
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CHUNK_RE = re.compile(r"^\s*([0-9a-fA-F]{4}):([0-9a-fA-F]{8})\s+([0-9a-fA-F]+)H\s+(\S+)\s+(CODE|DATA)\s*$")

# Below this many symbols per KB, a chunk is treated as undescribed by the map.
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
# library code the map never enumerates.
MIN_DENSITY = 0.5


def load_pcrecomp(p):
    d = json.loads(Path(p).read_text())
    return {f["address"] for f in d["functions"]}, d


def load_ida(p):
    d = json.loads(Path(p).read_text())
    return {f["ea"] for f in d["functions"]}, d


def load_ghidra(p):
    out = set()
    with open(p, newline="") as fh:
        for row in csv.reader(fh):
            if not row or not row[0].strip():
                continue
            tok = row[0].strip().lstrip("0x")
            try:
                out.add(int(tok, 16))
            except ValueError:
                continue          # header line
    return out, None


def code_chunks(map_path, sect_base):
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


def score(name, addrs, tv, tset, chunks, excluded_names):
    agg = {"tp": 0, "fp": 0, "fn": 0, "rec": 0, "truth": 0}
    per = {}
    for nm, a, b in chunks:
        t = [x for x in tv if a <= x < b]
        r = [x for x in addrs if a <= x < b]
        tp = sum(1 for x in r if x in tset)
        per[nm] = (len(t), len(r), tp, len(r) - tp, len(t) - tp)
        if nm in excluded_names:
            continue
        agg["tp"] += tp
        agg["fp"] += len(r) - tp
        agg["fn"] += len(t) - tp
        agg["rec"] += len(r)
        agg["truth"] += len(t)
    p = agg["tp"] / agg["rec"] if agg["rec"] else 0
    r_ = agg["tp"] / agg["truth"] if agg["truth"] else 0
    f1 = 2 * p * r_ / (p + r_) if (p + r_) else 0
    return {"name": name, "per": per, "precision": p, "recall": r_, "f1": f1, **agg}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", default="analysis/oracle_truth.json")
    ap.add_argument("--pcrecomp", default="analysis/oracle_functions.json")
    ap.add_argument("--ida", default="analysis/ida_functions.json")
    ap.add_argument("--ghidra", default="analysis/ghidra_bounds.csv")
    ap.add_argument("--map", default="_work/oracle-build/cmake/trespass/Release/trespass.map")
    args = ap.parse_args()

    tp_ = ROOT / args.truth
    if not tp_.exists():
        sys.exit(f"missing ground truth: {tp_} (run tools/parse_map.py)")
    truth = json.loads(tp_.read_text())
    tv = sorted(f["va"] for f in truth["functions"])
    tset = set(tv)

    engines = []
    for label, path, loader in (
            ("pcrecomp", args.pcrecomp, load_pcrecomp),
            ("IDA", args.ida, load_ida),
            ("Ghidra", args.ghidra, load_ghidra)):
        p = ROOT / path
        if p.exists():
            try:
                addrs, meta = loader(p)
                engines.append((label, addrs, meta))
            except Exception as e:
                print(f"  (skipping {label}: {e})")
        else:
            print(f"  (no {label} output at {path} — skipping)")
    if not engines:
        sys.exit("no engine output to score")

    pcr = next((m for l, a, m in engines if l == "pcrecomp"), None)
    code_start = pcr["code_start"] if pcr else min(min(a) for _, a, _ in engines)
    sect_base = {1: code_start}
    for line in Path(ROOT / args.map).read_text(errors="replace").splitlines():
        mm = re.match(r"^\s*0002:([0-9a-fA-F]{8})\s+\S+\s+([0-9a-fA-F]{8})\s", line)
        if mm:
            sect_base[2] = int(mm.group(2), 16) - int(mm.group(1), 16)
            break
    chunks = code_chunks(ROOT / args.map, sect_base)

    excluded = {nm for nm, a, b in chunks
                if len([x for x in tv if a <= x < b]) / max((b - a) / 1024, 1) < MIN_DENSITY}

    results = [score(l, a, tv, tset, chunks, excluded) for l, a, _ in engines]

    print(f"\nground truth: {len(tv):,} function addresses "
          f"(excluded chunks: {', '.join(sorted(excluded)) or 'none'})\n")

    # Per-chunk precision for each engine
    names = [r["name"] for r in results]
    print(f"{'chunk':10} {'truth':>7} " + " ".join(f"{n:>18}" for n in names))
    print("-" * (18 + 19 * len(names)))
    for nm, a, b in chunks:
        t = results[0]["per"][nm][0]
        cells = []
        for r in results:
            _, rec, tp, fp, fn = r["per"][nm]
            cells.append(f"{rec:>6,} {tp/rec if rec else 0:>5.1%}p" +
                         (f" {tp/t if t else 0:>5.1%}r" if t else "        "))
        flag = " EXCL" if nm in excluded else ""
        print(f"{nm:10} {t:>7,} " + " ".join(f"{c:>18}" for c in cells) + flag)

    print(f"\n{'engine':10} {'recovered':>10} {'TP':>8} {'FP':>8} {'FN':>8} "
          f"{'precision':>10} {'recall':>8} {'F1':>8}")
    print("-" * 74)
    for r in sorted(results, key=lambda x: -x["f1"]):
        print(f"{r['name']:10} {r['rec']:>10,} {r['tp']:>8,} {r['fp']:>8,} {r['fn']:>8,} "
              f"{r['precision']:>9.2%} {r['recall']:>7.2%} {r['f1']:>7.2%}")

    # Agreement: where do the engines corroborate each other, and does
    # agreement in the *excluded* chunk suggest those functions are real?
    if len(engines) > 1:
        sets = {l: a for l, a, _ in engines}
        print("\nagreement between engines (all code chunks):")
        labels = list(sets)
        for i in range(len(labels)):
            for j in range(i + 1, len(labels)):
                A, B = sets[labels[i]], sets[labels[j]]
                inter = len(A & B)
                print(f"  {labels[i]:9} & {labels[j]:9}  {inter:>7,} shared  "
                      f"(Jaccard {inter/len(A|B):.1%})")
        if excluded:
            for nm, a, b in chunks:
                if nm not in excluded:
                    continue
                per_eng = {l: {x for x in s if a <= x < b} for l, s in sets.items()}
                if len(per_eng) < 2:
                    continue
                allsets = list(per_eng.values())
                common = set.intersection(*allsets)
                union = set.union(*allsets)
                print(f"\n  in excluded chunk '{nm}' ({b-a:,} bytes, map has "
                      f"{len([x for x in tv if a<=x<b])} symbols):")
                for l, s in per_eng.items():
                    print(f"    {l:9} finds {len(s):>6,}")
                print(f"    all engines agree on {len(common):,} of {len(union):,} "
                      f"({len(common)/len(union):.1%} of the union)")
                print("    -> agreement here is evidence these are real functions the")
                print("       map simply does not name, not engine error.")

    (ROOT / "analysis/recovery_score.json").write_text(json.dumps(
        [{k: v for k, v in r.items() if k != "per"} for r in results], indent=1))
    print("\nwrote analysis/recovery_score.json")


if __name__ == "__main__":
    main()
