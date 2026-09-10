# Roadmap

The pcrecomp pipeline is always the same shape — **Analyze → Disassemble →
Classify → Lift → Shim → Build → Debug → Ship**. What changes per project is
where the time goes. This page says where it goes for Trespasser, and what
"done" looks like at each step.

## What we are actually building

Two things, and the order matters:

1. **A measured audit of the pcrecomp toolchain**, against a target where the
   answer is checkable. This is the deliverable.
2. **A running Trespasser built from the retail binary.** This is how we prove
   the audit, and it is the thing that forces every stage of the toolchain to be
   exercised honestly rather than sampled.

Every other target in the family has been a dig into the unknown. The
Quake-family set had public SDKs, which only ever told us about the SDK parts —
the custom engine stayed opaque. We have never held a lifted function up next to
what it was supposed to be. Trespasser is the first target where we can.

Method and metrics: [VALIDATION.md](VALIDATION.md). Results:
[SCORECARD.md](SCORECARD.md). The rule that makes it worth anything is that the
binary-derived claim gets written down **before** the oracle is consulted.

The strongest oracle is not the source tree — it is a binary we build from it
with debug info, whose PDB names every function, its exact address and size, and
its source file. That turns every stage into a precision/recall measurement
instead of an impression. The source tree itself is the weaker oracle and comes
with a caveat that must be repeated every time it is used: it is the
*development* tree, not what was compiled into `tpassp6.exe`. Where they
disagree, the binary is right.

The source is read-only, never vendored. See [LEGAL.md](LEGAL.md).

## Which build

`tpassp6.exe`. Reasons, in order:

1. Every CPU that will ever run the output is a P6 descendant. The P6 build's
   instruction selection is the one modern hardware was designed to run.
2. The K6 build uses 3DNow!, an extension we would have to teach the lifter for
   no benefit on any machine anyone owns.
3. Of the two Intel builds, P6 has the smaller self-modifying surface — 39,797
   bytes against the P5 build's 52,405. That is the hardest part of the project,
   so we take 24% less of it.

Measured after the fact, and it confirms the choice: **the P6 build contains no
MMX, no SSE and no 3DNow! at all** — it is pure x87. The K6 build would have
cost roughly 4,000 vector instructions across two instruction sets, one of them
3DNow!, which this toolchain has never lifted. The bill for choosing P6 is
113,243 x87 instructions, so the FPU model is now on the critical path. Full
census in [RECON](RECON.md#instruction-set-census).

Open question deferred to Phase 1: whether to target retail 1.0 (`tpassp6.exe`
as shipped) or 1.1 (`UPDATE\tresp1_1\PatchEXEOnly.exe`). 1.0 is what we have
disassembled; 1.1 is what people actually play. Decide once we know how much the
patch moves. Default is 1.0 — never chase a moving target during bring-up.

---

## Phase 0 — Reconnaissance ✅

**Done.** Findings in [RECON.md](RECON.md).

Headline: plain MSVC 6 PE32, no DRM, no packer, 297 imports across 11 DLLs,
513 RTTI type names intact, DirectDraw-only software renderer, CRT external.

Two follow-up measurements landed with it:

- **The target is pure x87.** No MMX, no SSE, no 3DNow!. The lifter needs the
  integer core and a correct FPU, and nothing else.
- **The self-modifying surface is about eighteen routines**, not hundreds of
  sites — 18 distinct addresses in `.text` point into `SelfMod`. That is a floor
  (computed addresses would not show up), but it takes the project's one real
  risk from unknown to roughly sized.

---

## Phase 1 — Disassembly and function recovery

**Goal:** a function catalog covering `.text` and `SelfMod`, with boundaries we
trust.

- [ ] Run `disasm32.py` over `.text` to convergence; record function count,
      instruction count, and unresolved indirect-call sites.
- [ ] Disassemble `SelfMod` separately and identify its function boundaries.
- [ ] Cross-check boundaries against Ghidra headless (`DumpBounds.java`) — two
      independent recoveries agreeing is the cheapest confidence available.
- [ ] Build the call graph; find the entry chain from `0x00626BE2` (CRT startup)
      to `WinMain` and from there to the main loop.
- [x] ~~Inventory the instruction set actually used.~~ Done in Phase 0: pure
      x87, no vector ISA. The lifter needs the integer core and the FPU.

**Done when:** every byte of `.text` is either inside a recovered function or
explained (padding, jump tables, embedded data), and we can name the main loop.

**Risk:** indirect calls. A C++ engine with 512 classes is mostly virtual
dispatch, so the static call graph will be full of holes by construction. That
is expected and is Phase 2's problem, not Phase 1's.

---

## Phase 2 — Classification

This is the phase that decides whether the project is weeks or months, and it is
where Trespasser's peculiar advantages get spent.

- [ ] **Parse the RTTI tree.** 513 type descriptors, their `_RTTICompleteObject
      Locator`s and base-class arrays give us the full class hierarchy, not just
      a list of names.
- [ ] **Recover vtables.** `tools/cpp/parse_vtables.js` against the RTTI
      locators. Every vtable entry is an indirect-call target the static graph
      missed — this is what fills Phase 1's holes.
- [ ] **Attribute functions to classes.** A function reachable only from
      `CActivityBite`'s vtable is a `CActivityBite` method. Cheap, and it names
      a large fraction of the binary.
- [ ] **Separate CRT and iostreams.** MSVCRT/MSVCIRT are external imports, so
      most of this is already outside the image — but MSVC 6 inlines plenty of
      CRT. Classify it out; we are not lifting `memcpy`.
- [ ] **Match against the source oracle.** With class names in hand, align
      recovered functions to source functions by signature and call structure.
      Expect this to name most of the binary. Names only — no code is copied.

**Done when:** ≥80% of recovered functions have a name and an owning subsystem,
and we have a ranked list of what must be lifted versus what can be shimmed.

---

## Phase 2.5 — Stand up the oracle

Runs in parallel with Phase 2; it gates the scoring, not the lifting.

- [x] ~~Build the reference tree with debug info.~~ **Done.** `trespass.exe`
      (8.8 MB, 32-bit) plus a 52 MB PDB and an 8.9 MB linker map. Four forced
      deviations, all recorded in [VALIDATION](VALIDATION.md#building-the-oracle);
      none touch engine C++. Use `Release`, which is both the config with debug
      info and the one that targets PentiumPro — the same variant as our target.
- [x] ~~Dump a ground-truth table.~~ **Done.** `tools/parse_map.py` reads the
      linker map (plain text, no PDB parser needed): **34,184 distinct function
      addresses**, 9,995 of them static. The PDB is kept for function *sizes*.
- [ ] Run the full pcrecomp front end (`pe_analyze` → `disasm32` → `callgraph` →
      `classify`) over *that* binary and score every stage against the map.
      **Blocked on scorecard #5** — `disasm32` has not converged on a 2.5 MB
      image in 3h20m of CPU, and the oracle binary is 3.5× larger.
- [ ] **Fix `disasm32` scaling first.** Profile the `find_functions` fixpoint,
      confirm the superlinear-rework hypothesis, fix upstream in pcrecomp.
- [ ] Write the numbers into [SCORECARD.md](SCORECARD.md); fix what is broken
      upstream in pcrecomp before lifting anything.
- [ ] Settle the open scorecard entries this can settle — in particular #3, the
      4,223 data-pointer-only functions.

**Done when:** we have precision and recall figures for function recovery and
call-graph edges on a binary where the answer is known, and we know how much to
trust the same tools on the retail image.

**Why here:** lifting a binary whose function boundaries are wrong produces
thousands of lines of confidently incorrect C. Measure the front end first.

---

## Phase 3 — Lifting

- [ ] Lift `.text` with `lift32_cpu.py` (the reentrant CPU-struct model — the
      hybrid boundary requires it; the global-register model will not do here
      because the real CRT will be calling into lifted code and back).
- [ ] Handle x87. Trespasser is a physics game from 1998; the FPU is load-bearing
      and the stack model has to be right, not approximately right.
- [ ] **`SelfMod`, in three steps:**
      1. Lift it as ordinary code, immediates and all. It will run and be wrong.
      2. Find the patch sites: every write into `0x0063B000–0x00644B75` from
         `.text`. Those writes are the renderer specialising a span loop.
      3. Rewrite each patched immediate as a read from a variable the patching
         code now writes instead. The self-modifying code becomes parameterised
         code, which is what it always meant.
- [ ] Validate with `difftest.py` — lifted C against Unicorn over the same bytes,
      comparing every register, flag and byte. Prioritise the physics and
      rasteriser functions.
- [ ] **Read the lifted C next to the original function.** difftest proves the
      code does what the *bytes* say; it cannot prove we lifted the right
      function, or that a pass was a pass for the right reason. This is the only
      check for that and it does not scale, so spend it deliberately — physics
      and rasterisers, not spread thin.
- [ ] Score the `SelfMod` patch-site model against what `DrawSubTriangle`
      actually patches (scorecard #2).

**Done when:** the whole image lifts with zero errors and difftest is clean on a
sampled set weighted toward physics and rendering.

**Risk, and it is the real one:** the self-modifying rasterisers. Everything else
here is a known quantity. Budget accordingly — if a step slips, it is this one.

---

## Phase 4 — Shimming

The import table is the TODO list. 297 functions, but they cluster:

- [ ] **Win32 → SDL2.** USER32 (75) + GDI32 (30) + KERNEL32 (59). The
      `runtime/compat/` layer already covers most of this shape from Fury³,
      Hellbender and Encarta.
- [ ] **DirectDraw → D3D11.** Only two imports, but they are the door to the
      whole COM surface behind them: surfaces, blits, palettes, page flipping.
      The renderer writes spans into a locked surface, which maps cleanly onto a
      dynamic texture and a full-screen quad.
- [ ] **The hybrid CRT boundary.** MSVCRT and MSVCIRT stay *real*. `runtime/
      hybrid/` handles the lifted↔real crossings, including `__thiscall`
      trampolines and vtable routing — the exact problem Encarta solved for MFC.
- [ ] **Audio.** `DSound.dll` and `A3d.dll` are `LoadLibrary`d, so the shim is a
      loader intercept rather than an import thunk. A3D (Aureal positional audio)
      is dead hardware; map it to plain DirectSound-equivalent mixing and accept
      losing the HRTF.
- [ ] **Smacker.** `smackw32.dll` is a real DLL on the disc and still runs on
      Win11. Ship it as-is first; replace later only if it becomes a problem.
- [ ] **Registry, LZ32, joystick.** Small and mechanical.

**Done when:** the shimmed binary reaches `WinMain` and opens a window.

---

## Phase 5 — Build and debug

Where most of the calendar time goes, on every project, always.

- [ ] CMake build from `templates/CMakeLists.txt.template` — no ASLR, large stack.
- [ ] VEH crash handler + ICALL trace buffer from day one. Do not debug lifted
      code without them.
- [ ] Bring-up order: startup → window → menu (`Menu.tpa`, the `.ddf` files) →
      load a level → render a frame → physics tick → input → play.
- [ ] Use the test scenes (`TestScene.scn`, `TestScnNght.scn`) before the real
      levels. They are smaller and they are what the developers debugged against.

**Milestones, in the order they should fall:**

1. Reaches `WinMain`
2. Window opens
3. Main menu renders
4. A level loads (`.grf` + `.scn` parsed by the game's own lifted code)
5. **One frame on screen** — the screenshot that goes in the README
6. Physics runs without exploding
7. Input works; you can walk
8. Playable

---

## Phase 6 — Ship

- [ ] Widescreen, high resolution, modern input.
- [ ] The obvious modern wins the 1998 engine could not have: uncapped framerate
      where the physics tolerates it, higher terrain LOD budgets.
- [ ] Document what the recompilation proved about the lifter, and push those
      fixes back into pcrecomp.

---

## Order of work, next six things

1. Finish the `.text` disassembly, get the function count. *(running — 4,917
   candidates from call targets and prologues, plus 4,223 found only via data
   pointers; the sweep is slow)*
2. Confirm the 18 `SelfMod` entry points are entry points, and find the patch
   offsets inside each one. This is the project's one real risk and it now looks
   about twenty routines wide.
3. Parse RTTI into a real class hierarchy; recover vtables.
4. Find `WinMain` and the main loop; trace the entry chain.
5. Build the reference tree with debug info and dump its PDB — the oracle that
   settles the open scorecard entries.
6. Decide 1.0 vs 1.1 by diffing `PatchEXEOnly.exe` against `tpassp6.exe`.
