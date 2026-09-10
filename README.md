# Trespasser Static Recompilation

Static recompilation of **Jurassic Park: Trespasser** (1998, DreamWorks
Interactive / Electronic Arts) from its retail Win32 binary to native C for
modern Windows.

Trespasser is the ambitious failure everyone still argues about: a full rigid-body
physics engine, no HUD, dinosaurs with a real behaviour tree, and a software
rasteriser that rewrote its own inner loops at runtime to keep up. It shipped
broken and it shipped brilliant. This project takes the shipped executable apart
and puts it back together for a machine that did not exist when it was made.

No emulator. The 1998 machine code, translated once and compiled for today.

Built on the [pcrecomp](https://github.com/sp00nznet/pcrecomp) toolchain.

## Status

**Phase 0 complete — reconnaissance.** Nothing runs yet. What we know:

- Target selected: **`setup\tpassp6.exe`**, the Pentium Pro/II build. The disc
  ships three CPU-specific builds; [RECON](docs/RECON.md) explains the choice.
- **Plain MSVC 6.0 PE32. No DRM, no packer.** Entry point in `.text`, ordinary
  entropy, nothing to unwrap. The easy case, structurally.
- **513 C++ type names recovered** — the build kept its RTTI type descriptors,
  so we have the original type inventory rather than a list of addresses, down to
  the template parameters of the terrain LOD quadtree. The AI behaviour tree
  alone is 33 `CActivity*` classes: `CActivityBite`, `CActivityFlee`,
  `CActivityTailSwipe`, `CActivitySniffAir`.
- **297 imports across 11 DLLs.** DirectDraw with exactly two entry points and no
  Direct3D import — this is a software renderer. The C runtime is external
  (`MSVCRT.DLL` + `MSVCIRT.DLL` ship on the disc), which is the shape pcrecomp's
  hybrid boundary was built for.
- **Pure x87 — no MMX, no SSE, no 3DNow!.** Measured across every executable
  section. The lifter needs the x86-32 integer core and a correct FPU, and
  nothing else. The bill is 113,243 x87 instructions, so the FPU model is on the
  critical path for a physics game.
- **One genuinely hard thing:** a 39,797-byte `SelfMod` section, marked
  executable *and writable*. It holds the rasteriser inner loops, which the
  renderer patches constants into before running them. Sized it: **18 distinct
  addresses in `.text` reach into it**, so this is about twenty patchable
  routines, not hundreds of scattered sites.

**The oracle is up.** The reference tree builds: `trespass.exe` (8.8 MB,
32-bit) with a 52 MB PDB and an 8.9 MB linker map, giving **34,184 known
function addresses** to score the tooling against. Recipe and the four forced
deviations are in [VALIDATION](docs/VALIDATION.md#building-the-oracle).

**First hard result was a failure — ours — and it is fixed.** `disasm32.py`
ground for **3h20m on the retail image without converging**. We predicted
superlinear rework in the fixpoint; measurement said O(code^1.10), essentially
linear, with a flat and catastrophic constant of ~4 ms per byte of code. The
cause was `disassemble_at` materialising an 8 KB window of detail-mode
instruction objects per block leader when every caller breaks out after a
handful. Yielding instead: **~20× faster, byte-identical output**, shipped
upstream as pcrecomp `e9d96cb` so all fifteen projects get it.

**And the tooling has now been scored against ground truth.** Pointed at the
oracle, `disasm32` recovers function starts at **77.1% precision / 78.5%
recall** — but that average hides the shape: 95–99.7% on exception tables and
initialisers, **71.6% on the 7.3 MB of actual game code**, and **27.6% on
`SelfMod`**, the very code Phase 3 has to lift. The false positives are
concentrated rather than diffuse: 5% of functions absorb nearly all of them, at
~4.6 spurious starts each. Full table in [SCORECARD](docs/SCORECARD.md#3--function-recovery-scored-against-ground-truth).

Getting an honest number took two corrections first — a bug in our own map
parser that invented 25 phantom functions, and a measurement flaw that scored a
246 KB library-code chunk the map describes with 15 symbols, which made
precision read 62% instead of 77%.

**Phase 1 is done.** The same image now converges in **12.7 minutes**:

| | |
|---|---|
| Functions recovered | **11,122** (28 thunks, 5,101 leaves) |
| Instructions | 1,819,212 |
| Byte coverage | **99.7%** — 2,366,797 of 2,374,517 bytes |
| Discovery rounds | 6 |
| Reachable only via data pointers | 4,223 — **38% of the program** a direct-call-only pass would never see |

That is the project working as intended. Fifteen projects in, we had never
measured any of this.

## The one hard problem

Everything about this binary is ordinary except `SelfMod`.

The good news is that it is not a JIT. The code is statically present and starts
with a normal MSVC prologue, so it disassembles like anything else. What the
renderer does at runtime is poke *constants* into it — specialising a span loop
to a particular texture width, light level or step, the standard 1998 trick for
making a software rasteriser fast enough.

That is liftable, in three steps: lift it as ordinary code, find every write into
the section from `.text`, then rewrite each patched immediate as a read from a
variable the patching code now writes. The self-modifying code becomes
parameterised code, which is what it always meant.

The K6 build hands us a free map of what is in there: it splits the same work
across eight named sections — `StriCopy`, `StriTex`, `StriGTex`, `StriBump`,
`StriTerr`, `StriDTer`, `StriWate`. Copy, texture, gouraud-texture, bump,
terrain, detail terrain, water.

## What this project is actually for

Every other pcrecomp target has been a dig into something genuinely unknown. The
Quake-family set (gunman, sof, heavymetal) had public SDKs to classify against,
which is the closest we have come to checking our work — but an SDK only tells
you about the parts that came from the SDK. The custom engine, the part that
matters, stayed a black box. Across fifteen projects we have never once been
able to hold a lifted function up against what it was supposed to be.

Trespasser is the first target where we can see the other side. Its source
circulates publicly and the community tree carries a working CMake build.

So the deliverable here is not primarily a running game. It is an answer to the
question we have been carrying the whole time: **does the tooling actually do
what we think it does?** A running game is how we prove the answer — it is not
the answer.

The method, in one line: **run the tools, write down what they claim, then look
at the other side and score it.** Written down first, or we are not testing the
tooling, we are reading the source with extra steps.

The strongest oracle is not the source tree at all — it is a binary we build
ourselves from it. A build with debug info yields a PE *plus a PDB naming every
function, its exact address and size, and its source file*. Point pcrecomp at
that and every stage becomes exactly scorable: precision and recall against
ground truth, computed automatically. Then run the same tools on the retail
binary, where we do not know the answer, and we finally know how much to trust
the numbers.

Full method in [VALIDATION.md](docs/VALIDATION.md); results accumulate in
[SCORECARD.md](docs/SCORECARD.md), and fixes flow upstream into
[pcrecomp](https://github.com/sp00nznet/pcrecomp).

### It works already

Two datapoints fell out of Phase 0 before this was even the plan.

**`SelfMod`, inferred then confirmed.** From the binary alone we said: not a
JIT, static code, exec+write because the renderer pokes constants into
rasteriser span loops. The community tree's build config turns out to carry a
linker flag `/SECTION:SelfMod,ERW`, commented as required by the self-modifying
assembly in `DrawSubTriangle`, project `ScreenRenderDWI`. Confirmed — and
narrowed to a named function and subsystem the binary would not have given up
for weeks.

**Direct calls are not enough.** Function recovery found 4,917 candidates from
call targets and prologues, then the data-pointer scan found **4,223 more
functions reachable only through data pointers** — no direct `call` in the image
reaches them. Those are virtual methods behind vtables. Against the final count of 11,122 recovered functions that is **38% of the
program** direct-call-only recovery would never see. Whether
4,223 is *correct* is exactly what the PDB oracle is for.

### If you just want to play it

Go use [OpenTrespasser](https://github.com/OpenTrespasser/JurassicParkTrespasser).
That is the short path and it is a good project. This is a different exercise.

The circulating source is used as a read-only oracle. It is never vendored here,
nothing is copied from it, and everything committed is derived from the binary —
see [LEGAL](docs/LEGAL.md).

## Roadmap

Full detail in [ROADMAP.md](docs/ROADMAP.md). The shape:

| Phase | What | State |
|-------|------|-------|
| 0 | **Reconnaissance** — PE, sections, imports, RTTI, formats | ✅ done |
| 1 | **Disassembly** — function recovery over `.text` and `SelfMod`, call graph | ✅ done |
| 2 | **Classification** — RTTI hierarchy, vtable recovery, name the binary | ⬜ |
| 2.5 | **Stand up the oracle** — build the reference tree, dump its PDB, score the front end against it | ⬜ |
| 3 | **Lifting** — x86-32 → C, x87, and the `SelfMod` patch-site work | ⬜ |
| 4 | **Shimming** — Win32→SDL2, DirectDraw→D3D11, hybrid CRT, audio, Smacker | ⬜ |
| 5 | **Build & debug** — startup, window, menu, level load, first frame, physics | ⬜ |
| 6 | **Ship** — widescreen, modern input, high resolution | ⬜ |

Next five things, in order:

1. Fix the two recovery defects the scoring found: `SelfMod` over-splitting
   (27.6% precision) and the 1,719 over-split functions in `.text$mn`.
2. Confirm the 18 `SelfMod` entry points and find the patch offsets inside each.
3. Parse RTTI into a class hierarchy; recover vtables from the type locators.
4. Find `WinMain` and the main loop.
5. Build the reference tree with debug info and dump its PDB — the oracle that
   settles the open scorecard entries.
6. Decide retail 1.0 vs the 1.1 patch by diffing the two executables.

## Getting the binary

Nothing from the game is in this repo. Bring your own disc.

```bash
# Put Trespasser.iso in the project root, then:
python tools/extract_iso.py        # pulls setup/*.exe and the DLLs into _iso/
python tools/recon.py              # regenerates everything in analysis/
```

## Layout

```
docs/          RECON, ROADMAP, VALIDATION, SCORECARD, LEGAL
tools/         Project-specific extraction and analysis scripts
analysis/      Generated: function catalogs, RTTI, call graphs (gitignored)
config/        Pipeline configuration
src/           Runtime, shims, and generated code (generated code gitignored)
_iso/          Your extracted game files (gitignored, never committed)
_ref/          Reference source, used as an oracle only (gitignored)
```

## Licence

**MIT** for everything in this repo — see [LICENSE](LICENSE).

That licence covers the tools and the analysis. It cannot cover *Trespasser*,
which belongs to whoever holds DreamWorks Interactive's catalogue today. Lifted
output is a derivative work of the binary it came from and carries the original's
copyright, which is why it is generated locally and never committed. Own what you
take apart.

---

*Part of the [pcrecomp](https://github.com/sp00nznet/pcrecomp) family.*
