# Toolchain scorecard

Running record of what pcrecomp got right and wrong on a target where the answer
is checkable. Method and rules in [VALIDATION.md](VALIDATION.md); the important
one is that the binary-derived claim is written down *before* the oracle is
consulted.

Verdicts: **confirmed** (tool was right) · **wrong** (tool was wrong, fixed
upstream) · **partial** (right in shape, wrong in detail) · **open** (claim made,
not yet checked).

| # | Tool | Claim from the binary | Oracle | Verdict | Upstream change |
|---|------|----------------------|--------|---------|-----------------|
| 1 | *(inference)* | `SelfMod` is not a JIT: static code, exec+write because the renderer pokes constants into rasteriser span loops | Reference build config names self-modifying asm in `DrawSubTriangle` / `ScreenRenderDWI` | **confirmed** | — |
| 2 | `disasm32.py` | ~18 patchable rasteriser routines (18 distinct `.text` → `SelfMod` references) | not yet checked | **open** | — |
| 3 | `disasm32.py` | 4,223 functions reachable only via data pointers — a direct-call-only pass would miss about half a C++ binary | oracle stood up, scoring blocked by #5 | **open** | — |
| 4 | ISA sweep | The P6 build is pure x87 — no MMX, SSE or 3DNow! | not yet checked | **open** | — |
| 5 | `disasm32.py` | *(performance, not correctness)* | Measured directly | **wrong** | **needed — blocking** |

---

## #5 — `disasm32.py` does not scale to multi-megabyte binaries

The first hard result, and it blocks the project.

**Measured** on `tpassp6.exe`, a 2.5 MB image with 2.37 MB of code:

| | |
|---|---|
| Wall clock | 3 h 20 m, still not converged |
| CPU time | 11,350 s (~3 h 9 m), single-threaded |
| CPU-bound? | Yes — gains ~19 s CPU per 20 s wall. Not deadlocked, not swapping. |
| Memory | ~1.09 GB, growing slowly and steadily |
| Progress | Initial 4,917 candidates disassembled, then discovery rounds 1–5. Round 5 (1,472 new targets) ran 27 minutes without emitting its completion line, against roughly 4 minutes per 1,000 candidates earlier. |

The per-round slowdown is the tell: the same unit of work costs several times
more in later rounds than in early ones, which points at superlinear behaviour
in the fixpoint loop rather than at the disassembly itself.

**Why this matters beyond Trespasser.** Every remaining large PC target has an
image this size or bigger, and the oracle binary we just built is 8.8 MB — 3.5×
the retail image. At the current curve, scoring the front end against its own
ground truth is not merely slow, it is not finishable. The audit cannot proceed
through this.

**Hypothesis, not yet confirmed:** the fixpoint in `find_functions` re-walks
work it has already done. Each candidate calls `disassemble_at(addr,
max_bytes=8192)`, so ~10,000 candidates across rounds re-decode on the order of
80 MB of instruction stream per pass, and the `covered` / `owner` bookkeeping is
rebuilt rather than updated incrementally. Needs profiling before anything is
changed — the point of this project is measuring, not guessing.

**Status:** the retail run is still going and will be left to converge so we get
the function count. The fix goes upstream into pcrecomp.

---

## The oracle

Stood up and working. Recipe and deviations in
[VALIDATION.md](VALIDATION.md#building-the-oracle).

| | |
|---|---|
| Binary | `trespass.exe`, 8,860,160 bytes, 32-bit, MSVC 14.44 |
| Symbols | `trespass.pdb` (52 MB) and `trespass.map` (8.9 MB) |
| Config | `Release` — the reference build defines `TARGET_PROCESSOR=PROCESSOR_PENTIUMPRO` there *and* keeps debug info, so it is the same P6 variant as our retail target |
| Ground truth | **34,184 distinct function addresses** (36,074 function symbols, 1,890 COMDAT-folded, 9,995 static) out of 57,081 symbols total |
| Sections | Code in sections 1 and 2 — and section 2 is `SelfMod`, 58,032 bytes, so the oracle reproduces the self-modifying architecture too |

Ground truth is regenerated with `python tools/parse_map.py <map> -o
analysis/oracle_truth.json`.

## Notes on open entries

**#2** needs the `SelfMod` disassembly plus a read of what `DrawSubTriangle`
actually patches. The risk is that 18 is a floor: sites reached by computed
address would not appear in an absolute-reference count.

**#3** is the highest-value open item and is now blocked only by #5. If the data
scan over-fires on non-code pointers, 4,223 is inflated and the function count is
wrong in a way that would quietly corrupt every downstream stage. Note this cuts
both ways — the same measurement is also the argument that the data-scan round is
mandatory for C++ targets, so getting it right matters twice.

**#4** is a claim from linear sweep with resume, which decodes some data as
instructions. The counts are upper bounds; the *zeros* are the reliable part,
since linear sweep does not produce false absences.
