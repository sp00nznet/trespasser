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

Phase 1 (disassembly and function recovery) is running — 4,917 function
candidates found so far from call targets and prologue patterns.

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

## Why bother, when the source is out there

Trespasser's development source circulates publicly and community source ports
exist. So this needs saying up front: **if you just want to play Trespasser on
Windows 11, go use [OpenTrespasser](https://github.com/OpenTrespasser/JurassicParkTrespasser).**
That is the short path and it is a good project.

This is a different exercise, worth doing for two reasons:

1. **It builds the game that shipped.** Not the development tree — the retail
   executable, with its actual compiler output and its self-modifying
   rasterisers, which no source port reproduces.
2. **It is the only project in this family with a ground-truth oracle.** Every
   other pcrecomp target has to guess whether a lifted function is semantically
   correct. Here we can check. That makes Trespasser the best available test case
   for the lifter itself, and every fix it forces flows back to the other
   fourteen projects.

The circulating source is used as a read-only naming and validation oracle. It is
never vendored here and nothing is copied from it — see [LEGAL](docs/LEGAL.md).

## Roadmap

Full detail in [ROADMAP.md](docs/ROADMAP.md). The shape:

| Phase | What | State |
|-------|------|-------|
| 0 | **Reconnaissance** — PE, sections, imports, RTTI, formats | ✅ done |
| 1 | **Disassembly** — function recovery over `.text` and `SelfMod`, call graph | 🔄 running |
| 2 | **Classification** — RTTI hierarchy, vtable recovery, name the binary | ⬜ |
| 3 | **Lifting** — x86-32 → C, x87, and the `SelfMod` patch-site work | ⬜ |
| 4 | **Shimming** — Win32→SDL2, DirectDraw→D3D11, hybrid CRT, audio, Smacker | ⬜ |
| 5 | **Build & debug** — startup, window, menu, level load, first frame, physics | ⬜ |
| 6 | **Ship** — widescreen, modern input, high resolution | ⬜ |

Next five things, in order:

1. Finish `.text` disassembly; get the function count.
2. Confirm the 18 `SelfMod` entry points and find the patch offsets inside each.
3. Parse RTTI into a class hierarchy; recover vtables from the type locators.
4. Find `WinMain` and the main loop.
5. Decide retail 1.0 vs the 1.1 patch by diffing the two executables.

## Getting the binary

Nothing from the game is in this repo. Bring your own disc.

```bash
# Put Trespasser.iso in the project root, then:
python tools/extract_iso.py        # pulls setup/*.exe and the DLLs into _iso/
python tools/recon.py              # regenerates everything in analysis/
```

## Layout

```
docs/          RECON, ROADMAP, LEGAL — the written record
tools/         Project-specific extraction and analysis scripts
analysis/      Generated: function catalogs, RTTI, call graphs (gitignored)
config/        Pipeline configuration
src/           Runtime, shims, and generated code (generated code gitignored)
_iso/          Your extracted game files (gitignored, never committed)
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
