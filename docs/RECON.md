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
