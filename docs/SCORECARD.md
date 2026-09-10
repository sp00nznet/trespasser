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
| 2 | *(inference)* | ~18 patchable rasteriser routines, counted by absolute `.text` → `SelfMod` references | Oracle holds 35 `DrawSubtriangle` instantiations; re-measuring retail by direct `call rel32` gives **33** | **partial** — mechanism exactly right, counting method was structurally blind | — |
| 3 | `disasm32.py` | Function recovery is trustworthy | Scored against 34,159 known addresses: **P 77.1% / R 78.5% / F1 77.8%** | **partial** — good on some chunks, poor on the game code and bad on `SelfMod` | needed |
| 4 | ISA sweep | The P6 build is pure x87 — no MMX, SSE or 3DNow! | not yet checked | **open** | — |
| 5 | `disasm32.py` | Predicted superlinear rework in the fixpoint | Measured: O(code^1.10), a constant-factor problem instead | **wrong** | **fixed** — lazy decode, ~20× faster, identical output (pcrecomp `e9d96cb`) |
| 6 | `disasm32.py` | Round 5 is a separate bug | It converged; round 5 was the same constant applied to the biggest batch | **wrong** — folds into #5 | — |

---

## #5 — `disasm32.py` was ~20× slower than it needed to be — **fixed**

The first hard result, and the first time a hypothesis of ours got checked and
came back wrong.

### What we predicted

That the fixpoint in `find_functions` was re-walking work it had already done —
superlinear rework. Written down before measuring, per the rules.

### What the measurement said

`tools/scaling_probe.py` runs the real tool over a ladder of real 32-bit PEs and
fits an exponent to (code bytes → seconds):

| Binary | Code bytes | Seconds | ms/byte |
|--------|-----------:|--------:|--------:|
| `dxinst.exe` | 10,902 | 41.12 | 3.77 |
| `Processor.dll` | 15,782 | 75.43 | 4.78 |
| `dsetup.dll` | 18,476 | 47.27 | 2.56 |
| `dsetup32.dll` | 35,519 | 149.30 | 4.20 |
| `SMACKW32.DLL` | 70,146 | 312.44 | 4.45 |

**Fitted: O(code^1.10).** Essentially *linear*. The hypothesis was wrong — there
was no algorithmic blowup. What there was is a catastrophic constant factor of
~4 ms per byte of code: about 250 code bytes per second, from a library that
decodes megabytes per second. At that rate the retail image's 2.37 MB of code
predicts 2.6 hours, which is exactly the behaviour observed.

Worth keeping as a lesson: the shape of the symptom (grinding for hours, later
rounds feeling slower) read as superlinear, and it wasn't. The per-round
"slowdown" was noise on top of a flat, terrible constant.

### The actual cause

`disassemble_at` materialised its whole window. Both callers in
`disassemble_function` break out at the first branch, ret or known block leader
— usually within a handful of instructions — but the function first built an
`Instruction`, with capstone detail operands, for every one of up to 8 KB of
decoded bytes, then discarded nearly all of them. Once per block leader, and
the work is done twice over: leader discovery, then block building.

### The fix

Yield instead of materialise, so each caller pays only for what it consumes. A
~4-line change. Measured against the pre-fix baselines, with outputs compared
by SHA256:

| Binary | Before | After | Speedup | Output |
|--------|-------:|------:|--------:|--------|
| `dxinst.exe` | 37.69 s | 1.91 s | **19.7×** | identical |
| `Processor.dll` | 69.64 s | 3.11 s | **22.4×** | identical |
| `dsetup32.dll` | 142.76 s | 6.70 s | **21.3×** | identical |
| `dsetup.dll` | 45.26 s | 2.44 s | **18.5×** | identical |

Byte-identical JSON in every case, so this is purely a performance change. The
one new constraint is that callers must iterate the result at most once; both
current callers already do.

**Shipped upstream:** pcrecomp commit `e9d96cb`. Every project in the family
gets it.

---

## #6 — round 5 was not a separate bug. **Resolved: our hypothesis was wrong.**

We guessed round 5 had its own defect because it remained the holdout after the
#5 fix. It did not. The retail image converged in 12.7 minutes total; round 5
was simply the largest batch of candidates paying the same flat constant, and it
cleared once decoding went lazy. Folded into #5.

Original note, kept for the record:

Round 5 disassembles the 1,472 targets that fell out of the data-pointer scan's
follow-on. For scale, the initial 4,917 candidates now take about five minutes,
so 1,472 ought to take a minute and a half.

**Hypothesis, to be tested against the oracle, not acted on yet:** those targets
are largely *data* misidentified as code. Recursive descent over garbage
wanders — `disassemble_function` will follow a bogus jump up to 1 MB away
(`abs(target - start_va) < 0x100000`), so a single bogus "function" can
accumulate an enormous number of block leaders and each one is real decode work
now, not waste.

If that is right, it is not primarily a speed bug — it means the data-pointer
scan is over-firing, which makes **#3 wrong** rather than merely unverified, and
would inflate the function count in a way that corrupts everything downstream.
That is exactly the failure mode this project was built to catch, and the oracle
settles it.

---

## #2 — the rasteriser is a template matrix. Mechanism right, method wrong.

**What we claimed from the binary:** ~18 patchable rasteriser routines, from 18
distinct absolute references in `.text` pointing into `SelfMod`. Stated as a
floor at the time.

**What the oracle shows.** Its `SelfMod` carries 37 symbols, 35 of them
instantiations of one function template — `DrawSubtriangle` — all from
`ScreenRenderDWI:DrawSubTriangle.obj`, specialised across five axes:

| Axis | Values |
|------|--------|
| Gouraud | `CGouraudOn`, `CGouraudOff`, `CGouraudNone`, `CGouraudFog` |
| Transparency | `CTransparencyOn`, `CTransparencyOff`, `CTransparencyStipple` |
| Map | `CMapTexture`, `CMapFlat`, `CMapBump`, `CMapShadow`, `CMapShadow32`, `CMapAlphaColour` |
| Index | `CIndexLinear`, `CIndexPerspective`, `CIndexNone` |
| ColLookup | `CColLookupOn`, `CColLookupOff`, `CColLookupTerrain`, `CColLookupAlphaTexture`, `CColLookupAlphaWater` |

Full cross product 1,080; 35 instantiated. Sizes 352–3,392 bytes, median 816.

So the specialisation is **two-layer**: templates choose the algorithm at
compile time, self-modification patches constants at run time. The binary alone
showed us the second layer and not the first.

### The counting method was structurally blind

Seeing the templates immediately explained why 18 was wrong, and it was not
because it was a floor. A template instantiation is resolved at compile time, so
its callers reach it with a **direct `call rel32`** — a relative displacement,
not an address stored anywhere. An absolute-dword scan cannot see those calls in
principle, no matter how many there are.

Confirmed on the oracle first: scanning its whole image for pointers to the 35
known `DrawSubtriangle` addresses finds **zero**. There is no dispatch table.
(Which also kills the guess, recorded here earlier, that the 10 `.data`
references in retail were that table. They are something else.)

**Re-measured on retail the right way** — scanning `.text` for `E8`/`E9` rel32
branches landing inside `SelfMod`:

| | |
|---|---|
| Direct `call` sites | 267 |
| **Distinct entry points** | **33** |
| Direct `jmp` sites | 0 |
| Entry spacing | min 288, median 640, max 2,720 bytes |

**33 against the oracle's 35**, with routine spacing (288/640/2,720) closely
tracking the oracle's sizes (352/816/3,392). Two independently derived numbers
from two different builds of the same code, agreeing. That is the strongest
cross-validation the project has produced so far.

**Verdict: partial.** Mechanism exactly right. Count wrong, twice — 18 from a
method that could not see the dispatch, then ~24 from a density estimate. The
answer is 33, and it took the oracle to reveal *which question to ask*.

**What this buys Phase 3.** 33 routines, each a member of one known template
family, median well under a kilobyte, all reached by direct calls from 267 known
sites. The patch sites can be studied in the oracle with symbols attached — each
routine names its own configuration in its mangled symbol — before the retail
image is touched.

---

## #3 — function recovery scored against ground truth

The headline result of the audit so far. `disasm32` was pointed at the oracle
binary and its 43,064 recovered function starts compared against the map's
34,159 known ones.

### Scoring honestly took two corrections first

Both are worth recording, because the first numbers this produced were wrong in
opposite directions.

**A bug in our own parser.** The map's static-symbol table carries unresolved
thunks — `__ehhandler$`, `__ehfuncinfo$` — with a nonsense section offset
(`0001:fffff000`) and an `Rva+Base` equal to the image base. `parse_map.py` took
those at face value and manufactured 25 phantom functions at `0x400000`, and
inflated the symbol count by four thousand. Fixed; ground truth went from a
claimed 34,184 to a real 34,159.

**A flaw in the measurement.** The plain `.text` chunk is 246 KB of linked-in
library code with **15 symbols in the whole map**, and those 15 are the Smacker
import thunks. The tool finds 8,300 functions there. Scored naively, every one
counts as a false positive and precision reads 62.25% — but absence of a symbol
is not evidence of absence of a function. That chunk is now excluded and said
so out loud. Scoring only where the map actually describes the binary gives
**77.11%**.

### The numbers

| Chunk | Bytes | Truth | Recovered | TP | FP | FN | Precision | Recall |
|-------|------:|------:|----------:|---:|---:|---:|----------:|-------:|
| `.text` | 246,128 | 15 | 8,300 | — | — | — | *excluded* | *excluded* |
| `.text$di` | 49,920 | 1,281 | 1,345 | 1,281 | 64 | 0 | 95.2% | 100.0% |
| `.text$mn` | 7,329,504 | 26,892 | 27,331 | 19,563 | 7,768 | 7,329 | **71.6%** | **72.7%** |
| `.text$x` | 184,080 | 5,240 | 5,265 | 5,235 | 30 | 5 | 99.4% | 99.9% |
| `.text$yd` | 25,418 | 694 | 696 | 694 | 2 | 0 | 99.7% | 100.0% |
| `SelfMod` | 58,032 | 37 | 127 | 35 | 92 | 2 | **27.6%** | 94.6% |
| **Aggregate** | | **34,144** | **34,764** | **26,808** | **7,956** | **7,336** | **77.11%** | **78.51%** |

F1 **77.81%**.

### What that actually means

**The tool is excellent on structured chunks and mediocre on the code that
matters.** `.text$x`, `.text$yd` and `.text$di` — exception tables, dynamic
initialisers — score 95–99.7%. `.text$mn`, which is the 7.3 MB of actual game
code, scores 71.6% precision and 72.7% recall. About one in four recovered
functions there is not a function, and about one in four real functions is
never found.

**`SelfMod` is the worst chunk in the binary: 27.6% precision.** The tool finds
127 function starts where 37 exist. Recall is fine at 94.6% — it finds nearly
all the real ones — but it shreds each rasteriser into roughly three and a half
pieces. That is a pointed result given Phase 3 has to lift exactly this code,
and it is consistent with what these routines are: templated span loops full of
computed jumps, with constants that get patched at run time.

**The false positives are concentrated, not diffuse.** Of 7,864 spurious starts
in the scored `.text` chunks, only 2.1% sit within 16 bytes of a real function
start; the median is 902 bytes in. They fall inside just **1,719 distinct real
functions — 5% of the binary — at a mean of 4.6 spurious starts each.**

That last number is the most useful thing here. The tool is not hallucinating
functions across the image; it is over-splitting a small minority of large,
control-flow-heavy functions, almost certainly at basic-block boundaries it
mistakes for entry points. A defect concentrated in 5% of functions is
tractable in a way that a diffuse 23% error rate would not be.

### What is still open

The original #3 claim was specifically about the **4,223 retail functions
reachable only via data pointers**. This scoring measures the tool overall, not
that subset, because the JSON does not record how each function was discovered.
Adding a provenance field upstream would let us score the data-scan round on its
own, which is the measurement actually wanted. Until then: the data-scan round
finds real functions (recall is high everywhere), but the aggregate 77%
precision means a meaningful slice of *any* recovered set is suspect, and the
retail count of 11,122 should be read with that in mind.


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

**#3** is the highest-value open item, and #6 now gives us a concrete reason to
doubt it rather than merely to verify it. If the data scan over-fires on non-code
pointers, 4,223 is inflated and the function count is wrong in a way that would
quietly corrupt every downstream stage. Note this cuts both ways — the same
measurement is also the argument that the data-scan round is mandatory for C++
targets, so getting it right matters twice.

**#4** is a claim from linear sweep with resume, which decodes some data as
instructions. The counts are upper bounds; the *zeros* are the reliable part,
since linear sweep does not produce false absences.
