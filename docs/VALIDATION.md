# Validating the toolchain

This is the point of the project.

Every other pcrecomp target has been a dig into something genuinely unknown. The
Quake-family set (gunman, sof, heavymetal) had public SDKs to classify against,
which is the closest we have come to checking our work — but an SDK only tells
you about the parts that came from the SDK. The custom engine, the part that
matters, stayed a black box. We have never been able to hold up a lifted
function next to what it was supposed to be.

Trespasser is the first target where we can see the other side. So the primary
deliverable here is not a running game. It is an answer to a question we have
been carrying for fifteen projects: **does the tooling actually do what we think
it does?**

A running game is how we prove the answer. It is not the answer.

## Three oracles, in increasing strength

**1. RTTI in the retail binary.** 513 type descriptors, on the real target.
Weak — it tells us names and hierarchy, nothing about function bodies — but it
is the only oracle that describes the *actual shipped binary*, so anything it
confirms needs no caveat about which tree we are looking at.

**2. The source tree.** 446 `.cpp`, 478 `.hpp`, 227 `.h`, ~507k lines. Strong on
structure, names, types, and intent. Its limitation is real and must be stated
every time it is used: this is the *development* tree, not the thing that was
compiled into `tpassp6.exe`. Where the two disagree, the binary is right and the
source is a hint.

**3. A binary we build ourselves, with a PDB.** This is the one that makes the
project rigorous, and it is available because the community tree carries a
working CMake build.

The third oracle is the key move, so it is worth spelling out. Build the tree
with debug info and we get a PE *plus a PDB that names every function, gives its
exact address and byte size, and maps it to a source file and line*. Point
pcrecomp at that binary and every stage becomes exactly scorable — not "this
looks about right", but precision and recall against ground truth, computed
automatically, on a binary of the same code by the same compiler family.

That gives us the missing half of the loop: run the tools on a binary where we
know the answer, measure the error, fix the tools, then run them on the retail
binary where we do not.

## What gets measured

| Tool | Question | Metric | Oracle |
|------|----------|--------|--------|
| `pe/pe_analyze.py` | Are the headers, sections and imports read correctly? | Exact match | Trivially checkable |
| `disasm/disasm32.py` | Does it find the functions that exist, and not invent ones that don't? | Precision / recall on `(address, size)` pairs | PDB |
| `disasm/callgraph.py` | Are the call edges real, and how many are missed? | Precision / recall on edges | PDB + source |
| `classify/` | SDK/CRT versus application code | Confusion matrix | PDB module attribution |
| `cpp/parse_vtables.js` | Are vtables and class hierarchy recovered correctly? | Recall against the RTTI tree and the source's class list | RTTI + source |
| `lift/lift32_cpu.py` | Is the emitted C *semantically the same code*? | difftest pass rate; plus function-level review against the original source | Unicorn + source |
| The `SelfMod` model | Did we infer the patching mechanism correctly? | Does our inferred site list match what the code actually patches? | Source |

The lifter row is the one that matters most and is hardest to score. difftest
already compares lifted C against Unicorn register-for-register, which catches
semantic errors but cannot tell us whether we lifted *the right function*, or
whether a function we got "right" was right for the wrong reason. Reading the
lifted C next to the original function is the only check for that, and it does
not scale — so it gets spent deliberately, on the physics and the rasterisers,
not spread thin.

## The discipline: predict, then look

This only means anything if we write down the binary-derived answer **before**
consulting the source. Otherwise we are not testing the tooling, we are reading
the source with extra steps and congratulating ourselves.

Every entry in the scorecard records four things: what the tool said, what the
truth turned out to be, the verdict, and what changed in pcrecomp as a result.
An entry with nothing in the fourth column is a tool that passed — which is a
result worth recording, because "we checked and it was fine" is exactly the
knowledge fifteen previous projects could not produce.

## First two datapoints

Both of these fell out of Phase 0 before the reframing, which is a decent sign
the method works.

### `SelfMod` — inference confirmed

**What we said, from the binary alone:** the section is exec+write and starts
with an ordinary MSVC prologue, so it is not a JIT; the code is statically
present and the renderer pokes constants into rasteriser inner loops to
specialise them. 18 distinct addresses in `.text` point into the section, which
reads as ~18 patchable routines rather than hundreds of scattered sites.

**What the other side says:** the community tree's `CMakeLists.txt` carries a
linker flag `/SECTION:SelfMod,ERW` with a comment explaining it is required by
the self-modifying assembly in `DrawSubTriangle`, in the project
`ScreenRenderDWI`.

**Verdict: confirmed, and narrowed.** Self-modifying rasteriser code, exactly as
inferred — and now we have the function's name and its subsystem, which the
binary alone would not have given us for a long time. The specific claim about
~18 patchable routines is still open; that is a Phase 1 measurement.

### Function discovery — direct calls are not enough

**Measured on the retail binary:** recursive descent from call targets and
prologue patterns found 4,917 candidates. The subsequent data-pointer scan found
**4,223 functions reachable only via data pointers** — no direct `call` anywhere
in the image reaches them.

**Why it matters:** those are virtual methods, reached through vtables. In a C++
binary with 512 classes, a function-recovery pass built only on direct calls
would miss roughly half the program. This is a measurable claim about tool
behaviour on a real target, and it is the strongest argument yet for the
data-scan round being non-optional rather than a nice-to-have.

**Still to check:** whether 4,223 is *right*. The data scan could be over-firing
on non-code pointers. The PDB oracle settles it.

## Scorecard

Results land in [SCORECARD.md](SCORECARD.md) as they are measured, and fixes
flow upstream into [pcrecomp](https://github.com/sp00nznet/pcrecomp).
