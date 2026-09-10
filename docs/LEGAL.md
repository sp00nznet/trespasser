# Legal position

Short version: **this repo contains no game files and no game source.** It
contains tools and analysis. You bring your own disc.

## The game

*Trespasser* (1998) is © DreamWorks Interactive / Electronic Arts. It is long out
of print, but copyright plainly still subsists. Nothing from the disc is
committed here — not the executables, not the assets, not the videos. `.gitignore`
blocks the whole family (`*.exe`, `*.iso`, `*.grf`, `*.scn`, `*.tpa`, `*.smk`, …)
and the extraction directory `_iso/` is ignored wholesale.

Lifted output is a derivative work of the binary it came from. That means the
generated code in `src/recomp/gen/` carries the original's copyright, not this
repo's MIT licence, and it is `.gitignore`d for that reason. Anyone reproducing
this project regenerates it from their own copy.

## The circulating source

Trespasser's development source code circulates publicly and community forks of
it exist on GitHub. Its status is *leaked*, not released — no licence was ever
granted for it.

This project's position:

- **It is never vendored into this repo.** Not a file, not a snippet, not a
  header. If it is ever consulted locally it lives in `_ref/`, which is ignored.
- **It is used as a naming and validation oracle only.** "The function at
  `0x004A1C30` matches the shape of `CActivityBite::Act`" is an observation about
  our binary. Copying the body of that function into this project is not
  something we do.
- **Everything committed here is derived from the binary we own.** The RTTI
  names, the class hierarchy, the function boundaries, the lifted code — all of
  it comes out of `tpassp6.exe`.

That line matters practically as well as legally: a recompilation that quietly
becomes a source port has stopped testing the lifter, which is half the point of
doing this one. See [ROADMAP.md](ROADMAP.md#why-this-project-is-unusual).

## This repo's own code

MIT — see [LICENSE](../LICENSE). The tools, the analysis scripts, the shims and
the runtime glue are ours to give away. The thing you point them at is not.
