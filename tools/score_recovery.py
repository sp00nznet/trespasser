#!/usr/bin/env python3
"""Score disasm32's function recovery against the oracle's ground truth.

The oracle (docs/VALIDATION.md) is the reference source built with MSVC and
linked with /MAP, so we know every function's real address. Point the same
disassembler at that binary and this measures how much it actually gets right.

  python tools/parse_map.py <trespass.map> -o analysis/oracle_truth.json
  python <pcrecomp>/tools/disasm/disasm32.py trespass.exe -o analysis/oracle_functions.json
  python tools/score_recovery.py

Comparison is on function *start addresses*, which is what both sides agree on:
the linker map gives starts, and recursive descent finds starts. Sizes would
need the PDB.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(path, what):
    p = ROOT / path
    if not p.exists():
        sys.exit(f"missing {what}: {p}")
    return json.loads(p.read_text())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", default="analysis/oracle_truth.json")
    ap.add_argument("--recovered", default="analysis/oracle_functions.json")
    ap.add_argument("--show", type=int, default=10, help="sample N of each error class")
    args = ap.parse_args()

    truth = load(args.truth, "ground truth (run tools/parse_map.py)")
    rec = load(args.recovered, "recovered functions (run disasm32.py)")

    truth_names = {f["va"]: f["names"] for f in truth["functions"]}
    rec_addrs = {f["address"] for f in rec["functions"]}

    # disasm32 only walks the code range it computed. Anything outside that is
    # not a miss the tool can be blamed for, so score inside the intersection.
    lo, hi = rec["code_start"], rec["code_end"]
    truth_in = {va for va in truth_names if lo <= va < hi}
    rec_in = {a for a in rec_addrs if lo <= a < hi}
    truth_out = len(truth_names) - len(truth_in)

    tp = truth_in & rec_in
    fn = truth_in - rec_in       # real functions the tool never found
    fp = rec_in - truth_in       # addresses the tool called functions and aren't

    precision = len(tp) / len(rec_in) if rec_in else 0.0
    recall = len(tp) / len(truth_in) if truth_in else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    print(f"code range          0x{lo:08X} - 0x{hi:08X}")
    print(f"ground truth        {len(truth_names):,} functions "
          f"({len(truth_in):,} in range, {truth_out:,} outside)")
    print(f"recovered           {len(rec_addrs):,} functions ({len(rec_in):,} in range)")
    print()
    print(f"  true positives    {len(tp):,}")
    print(f"  false negatives   {len(fn):,}   (real functions missed)")
    print(f"  false positives   {len(fp):,}   (invented -- not a function start)")
    print()
    print(f"  precision         {precision:6.2%}")
    print(f"  recall            {recall:6.2%}")
    print(f"  F1                {f1:6.2%}")

    # A false positive landing *inside* a real function is a different error
    # from one landing in data: the first is a split, the second is garbage.
    starts = sorted(truth_in)
    import bisect
    inside = 0
    for a in fp:
        i = bisect.bisect_right(starts, a) - 1
        if i >= 0:
            inside += 1
    print()
    print(f"  of the false positives, {inside:,} fall at or after some real "
          f"function start\n  (candidate mid-function splits) and "
          f"{len(fp) - inside:,} fall before any (garbage)")

    if args.show:
        print(f"\nsample missed functions (first {args.show}):")
        for va in sorted(fn)[:args.show]:
            print(f"  0x{va:08X}  {truth_names[va][0][:70]}")
        print(f"\nsample invented addresses (first {args.show}):")
        for a in sorted(fp)[:args.show]:
            print(f"  0x{a:08X}")

    out = {
        "code_start": lo, "code_end": hi,
        "truth_total": len(truth_names), "truth_in_range": len(truth_in),
        "recovered_total": len(rec_addrs), "recovered_in_range": len(rec_in),
        "true_positives": len(tp), "false_negatives": len(fn),
        "false_positives": len(fp),
        "precision": precision, "recall": recall, "f1": f1,
        "fp_inside_known_function": inside,
    }
    (ROOT / "analysis/recovery_score.json").write_text(json.dumps(out, indent=1))
    print("\nwrote analysis/recovery_score.json")


if __name__ == "__main__":
    main()
