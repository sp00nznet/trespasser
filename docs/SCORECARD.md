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
| 1 | *(inference, not a tool)* | `SelfMod` is not a JIT: static code, exec+write because the renderer pokes constants into rasteriser span loops | Source build config names self-modifying asm in `DrawSubTriangle` / `ScreenRenderDWI` | **confirmed** | — |
| 2 | `disasm32.py` | ~18 patchable rasteriser routines (18 distinct `.text` → `SelfMod` references) | not yet checked | **open** | — |
| 3 | `disasm32.py` | 4,223 functions are reachable only via data pointers, not direct calls — i.e. a direct-call-only pass would miss about half a C++ binary | not yet checked (needs PDB) | **open** | — |
| 4 | ISA sweep | The P6 build contains no MMX, no SSE and no 3DNow! — pure x87 | not yet checked | **open** | — |

## Notes on open entries

**#2** needs the `SelfMod` disassembly plus a read of what `DrawSubTriangle`
actually patches. The risk is that 18 is a floor: sites reached by computed
address would not appear in an absolute-reference count.

**#3** is the highest-value open item. If the data scan over-fires on non-code
pointers, 4,223 is inflated and the function count is wrong in a way that would
quietly corrupt every downstream stage. A PDB settles it exactly. Note this cuts
both ways — the same measurement is also the argument that the data-scan round
is mandatory for C++ targets, so getting it right matters twice.

**#4** is a claim from linear sweep with resume, which decodes some data as
instructions. The counts are upper bounds; the *zeros* are the reliable part,
since linear sweep does not produce false absences. Worth confirming against a
symbol-guided disassembly anyway.
