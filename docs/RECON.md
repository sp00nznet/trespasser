# Reconnaissance

Everything on this page was read out of the retail binaries, not out of a wiki.
Reproduce it with `tools/recon.py` (see the bottom of this file).

## The disc

`Trespasser.iso`, 744,597,504 bytes, volume dated 1998. The game executable is
not at the root — it ships inside `setup\`, in **three CPU-specific builds**:

| File | Size | `.text` | Self-modifying code | Target |
|------|------|---------|---------------------|--------|
| `setup\tpassp5.exe` | 2,592,768 | 2,345,552 | `SelfMod` 52,405 | Pentium |
| `setup\tpassp6.exe` | 2,568,192 | 2,334,128 | `SelfMod` 39,797 | Pentium Pro / II |
| `setup\tpassk6.exe` | 2,367,488 | 2,130,880 | `SelfMod` 3,391 + 8 `Stri*` sections | AMD K6 / 3DNow! |

All three are dated 1998-10-09. `setup\Processor.dll` is what picks one at
install time; the installer copies exactly one of them out as the game exe.

Also on the disc and relevant later: `setup\SMACKW32.DLL` (RAD Smacker video),
`setup\MSVCRT.DLL` + `setup\MSVCIRT.DLL` (the game's C runtime, shipped
alongside rather than statically linked), and `UPDATE\tresp1_1\PatchEXEOnly.exe`
— the retail 1.1 patch, which replaces the executable only.

**We target `tpassp6.exe`.** Rationale in [ROADMAP](ROADMAP.md#which-build);
short version: every machine that will ever run this is a P6 descendant, the K6
build drags in 3DNow! for no benefit, and P6 has the smallest self-modifying
surface of the two Intel builds.

## What `tpassp6.exe` is

```
Machine        i386
Format         PE32 (EXE), Windows GUI
Image base     0x00400000
Entry point    0x00626BE2  (RVA 0x00226BE2)
Linker         6.00                    -> Microsoft Visual C++ 6.0
Timestamp      1998-10-09 17:06:31 UTC
Code range     0x00401000 - 0x00644B75   (2,374,517 bytes)
Data range     0x00645000 - 0x00741408   (1,033,224 bytes)
```

Sections:

| Name | VA | VSize | Flags |
|------|----|-------|-------|
| `.text`   | 0x00401000 | 0x239DB0 | CODE EXEC READ |
| `SelfMod` | 0x0063B000 | 0x009B75 | CODE EXEC READ **WRITE** |
| `.rdata`  | 0x00645000 | 0x017474 | READ |
| `.data`   | 0x0065D000 | 0x0E4408 | READ WRITE |
| `.rsrc`   | 0x00742000 | 0x0044B8 | READ |

**No DRM, no packer.** `analyze_sections.py` finds no protection indicators and
the entropy profile (6.29 on `.text`) is ordinary compiled code. The entry point
is in `.text`. This is a plain, unobfuscated MSVC binary — the easy case.

## Imports: 297 functions from 11 DLLs

| DLL | Count | Notes |
|-----|-------|-------|
| MSVCRT.dll | 79 | C runtime, **dynamically linked** — includes `__RTtypeid` |
| USER32.dll | 75 | Windowing, input, message loop |
| KERNEL32.dll | 59 | Files, memory, threads, critical sections |
| GDI32.dll | 30 | Fonts, DCs, palettes |
| MSVCIRT.dll | 26 | C++ iostreams (`istream`/`ostream`/`ifstream`) |
| smackw32.dll | 14 | Smacker video playback |
| ADVAPI32.dll | 6 | Registry (settings live in the registry) |
| LZ32.dll | 4 | `LZOpenFileA`/`LZRead`/`LZSeek` — LZ-compressed assets |
| DDRAW.dll | 2 | `DirectDrawCreate`, `DirectDrawEnumerateA` |
| WINMM.dll | 1 | `joyGetPosEx` — joystick only |
| COMCTL32.dll | 1 | ordinal 17 (`InitCommonControls`) |

Three things to read off that table:

- **DirectDraw only, two entry points.** There is no Direct3D import. Trespasser's
  renderer is software rasterisation into a DirectDraw surface — which is why the
  `SelfMod` section exists. Direct3D, where used, comes in through the DirectDraw
  object at runtime (the binary's own log strings mention "New direct 3d object
  created"), not through the import table.
- **Audio and A3D are loaded dynamically.** `DSound.dll` and `A3d.dll` appear as
  *strings*, not imports — the game `LoadLibrary`s them. That means the shim for
  audio is a library-load intercept, not an import thunk.
- **MSVCRT and MSVCIRT are external.** The CRT is not statically linked into the
  image. That is exactly the shape the pcrecomp `runtime/hybrid/` boundary was
  built for: keep the real CRT and iostreams real, run the app body lifted.

## RTTI: 513 named C++ types

The build kept its RTTI type descriptors: **512 classes and one struct, of which
173 are template instantiations**. Every one decodes to a real class name, so we
get the original type inventory for free — no guessing, no inventing names.

The template instantiations are as useful as the plain classes. Names like
`CQuadRootBaseTriT<CQuadNodeTIN, CQuadVertexTIN, CTriNodeInfoTIN, CTriangleTIN>`
in namespace `NMultiResolution` describe the terrain LOD quadtree's exact
parameterisation — that is a data structure recovered without reading a single
instruction.

Counted by prefix, the largest families are:

| Count | Family | What it is |
|-------|--------|-----------|
| 33 | `CActivity*` | The dinosaur AI behaviour tree — `CActivityBite`, `CActivityFlee`, `CActivityStalk`, `CActivityTailSwipe`, … |
| 22 | `CPlane*` | Clipping / geometry planes |
| 16 | `CMessage*` | The message-passing system the whole engine is wired with |
| 12 | `CSet*` | Typed set containers |
| 11 | `CPhysics*` | The physics engine |
|  9 | `CBound*` | Bounding volumes |
|  9 | `CRaster*` | Software rasteriser surfaces |
|  7 | `CPixel*` | Pixel format handling |
|  6 | `CCamera*`, `CRender*` | Camera and render pipeline |
|  5 | `CAudio*`, `CMesh*` | Audio, meshes |

Plus the named singles that tell you where the interesting code lives:
`CAISystem`, `CAIGraph`, `CAStarAIGraph`, `CAnimal`, `CBioMesh`, `CTerrain*`,
`CWater*`, `CQuad*`/`NMultiResolution` (the terrain LOD quadtree),
`CMagnet*` (the joint system), `CAutoGrabber`, `CBloodSplats`.

The full list is regenerated into `analysis/rtti.txt`.

## Instruction set census

Every executable section of both candidate builds, disassembled linearly and
resumed past undecodable bytes (so this covers the whole section, not just the
run up to the first bad byte):

| Build | Section | Instructions | x87 | MMX | 3DNow! | SSE |
|-------|---------|-------------:|----:|----:|-------:|----:|
| **p6** | `.text`   | 765,150 | 113,243 | 0 | 0 | 0 |
| **p6** | `SelfMod` | 10,245 | 2,615 | 0 | 0 | 0 |
| k6 | `.text`   | 723,829 | 89,506 | 1,902 | 2,101 | 0 |
| k6 | `StriCopy` | 1,087 | 0 | 278 | 96 | 0 |
| k6 | `StriTex`  | 1,093 | 0 | 270 | 96 | 0 |
| k6 | `StriGTex` | 1,038 | 0 | 226 | 92 | 0 |
| k6 | `StriBump` | 1,487 | 0 | 271 | 96 | 0 |
| k6 | `StriTerr` |   745 | 0 | 132 | 24 | 0 |
| k6 | `StriDTer` | 1,048 | 0 | 233 | 48 | 0 |
| k6 | `StriWate` |   856 | 0 | 160 | 100 | 0 |
| k6 | `SelfMod`  |   819 | 0 | 436 | 48 | 0 |

(A linear sweep decodes some data as instructions, so treat these as close
upper bounds rather than exact counts. The zeros are the reliable part — a
false *absence* is not something linear sweep produces.)

**The P6 build is pure x87.** No MMX, no SSE, no 3DNow! anywhere in it. The
lifter therefore needs exactly two things: the x86-32 integer core, and a
correct x87. Nothing else.

That settles the build choice with a number rather than a hunch: the K6 build
would have cost us roughly 4,000 vector instructions across *two* instruction
sets, one of which (3DNow!) is dead silicon nobody has emulated in this
toolchain and which we would be implementing from scratch.

The bill for that choice is the 113,243 x87 instructions the P6 build uses
instead. The x87 stack model has to be genuinely right — not approximately
right — and it is on the critical path for a physics game. Note also that the
two builds put the rasterisers in different worlds entirely: K6's `Stri*`
sections are pure integer SIMD with zero x87, while P6's `SelfMod` is
float-heavy (2,615 x87 in 10,245 instructions).

## How much self-modification, exactly

Counting every 4-byte little-endian value anywhere in the image that points
into the `SelfMod` range `0x63B000-0x644B75`:

| Source section | References | Distinct targets |
|----------------|-----------:|-----------------:|
| `.text`  | 42 | 18 |
| `.data`  | 21 | 10 |
| `.rdata` |  1 |  1 |

**Eighteen distinct addresses in `.text` reach into `SelfMod`**, spread across
the section from `0x63BF00` to `0x6446C7`.

That is a small number, and it is the shape you would hope for. A patcher does
not name every byte it pokes — it loads a routine's base address once and writes
at offsets from it. So 18 absolute references most likely means **18 patchable
rasteriser routines**, each with a handful of patch offsets inside it, rather
than hundreds of scattered independent sites. The 10 references from `.data` are
consistent with a dispatch table of rasteriser entry points.

Caveat worth stating plainly: this counts absolute references only. Any site
reached purely by computed address would not appear here, so 18 is a floor. It
still moves the risk from "unknown" to "probably about twenty routines", which
is what Phase 1 needs to confirm.

## Data formats to crack

From the disc layout and the binary's own strings:

| Extension | Guess | Evidence |
|-----------|-------|----------|
| `.grf` | GROFF — the main asset container (geometry, textures, objects) | Largest per-level file; the leaked toolchain has a `GroffBuild.exe` |
| `.scn` | Scene / level definition | One per level, small |
| `.tpa` | Audio pack | `Ambient.tpa`, `Effects.tpa`, `Stream.tpa`, `menu.tpa` |
| `.swp` | Paging / swap file | String `-130.swp` and `\*.swp` — built at install, per-resolution |
| `.pid`, `.spz` | Per-level paged data, resolution-tagged (`-130`) | Always paired with a level |
| `.wtd` | Water data | Pairs with levels that have water |
| `.smk` | Smacker video | `credits.smk` |
| `.ddf` | Menu/dialog definition | `audio.ddf`, `controls.ddf`, `gamewnd.ddf` |

Levels shipped: `as`, `as2`, `be`, `ij`, `it`, `jr`, `lab`, `sum`, plus `pv`
referenced in the binary but not on the disc, and two test scenes.

## The one hard thing: `SelfMod`

`SelfMod` is 39,797 bytes marked `CODE | EXEC | READ | WRITE`. It begins with an
ordinary MSVC prologue:

```
55              push ebp
8B EC           mov  ebp, esp
83 EC 18        sub  esp, 18h
53 56 57        push ebx, esi, edi
```

So this is **not** a JIT that builds code from nothing at runtime. The code is
statically present in the file and complete enough to disassemble; what makes the
section writable is that the renderer pokes *constants* into the rasteriser inner
loops before running them — the classic 1998 trick for specialising a span loop
to a texture width, a light level, a step value.

That matters enormously for the plan: we can lift this code like any other code.
What we cannot do is lift it and pretend the immediates are immediates. Each
patch site has to be found and turned into a variable that the patching code
writes. See [ROADMAP](ROADMAP.md#phase-3) for how that is staged.

The K6 build splits the same idea across eight separate executable sections
(`StriCopy`, `StriTex`, `StriGTex`, `StriBump`, `StriTerr`, `StriDTer`,
`StriWate`, plus its own small `SelfMod`) — one per rasteriser variant. Those
names are a free map of what the P6 build's single blob contains: copy, texture,
gouraud-texture, bump, terrain, detail-terrain, water.

## Reproducing this

```bash
python tools/recon.py            # writes analysis/*.json and analysis/rtti.txt
```

Or by hand, with pcrecomp:

```bash
python ../tools/tools/pe/pe_analyze.py      _iso/setup/tpassp6.exe --json > analysis/pe.json
python ../tools/tools/pe/analyze_sections.py _iso/setup/tpassp6.exe
python ../tools/tools/pe/extract_imports.py  _iso/setup/tpassp6.exe
python ../tools/tools/disasm/disasm32.py     _iso/setup/tpassp6.exe -o analysis/functions.json
```
