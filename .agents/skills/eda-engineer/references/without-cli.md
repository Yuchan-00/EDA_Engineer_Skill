<!-- Copyright (c) 2026 Yuchan (github.com/Yuchan-00). MIT License with Commons Clause (no selling) - see LICENSE. -->
# When the tools are missing

Read this when `ai-eda doctor --strict` exits 1, or when the user has no `ai-eda` at all.

## 1. Read the doctor lines

`ai-eda doctor --strict` prints one line per tool and ends with `missing   : ...`. Exit 1 means at least one
of: `kicad-cli` (KiCad 10 or newer), `KiCad library tables`, `KiCad libraries`, `ngspice`. The `browser
(pdf)`, `LLM key` and `claude cli` lines never make it exit 1. The doctor's own hints name the
installer per platform (for example `winget install --id KiCad.KiCad -e`, `brew install --cask kicad`,
`sudo apt install libngspice0 ngspice`).

## 2. Propose, never install

Installing software is `system_install`: tell the user what is missing, quote the doctor's hint, and wait
for their decision. If they decline, continue with what exists:

- `kicad tables: MISSING ... - run ai-eda setup-kicad` only: `ai-eda setup-kicad` writes the two global
  library tables when absent and never changes an existing one (no install; ask first anyway, it writes into
  the user's KiCad settings). A `MISSING ... (no KiCad settings folder: ...)` line without that suffix means
  the named environment variable must be fixed first; setup-kicad would exit 1.
- `kicad-cli` missing but `kicad libs` found: the pipeline still runs; schematic and board are compiled from
  the IR; ERC, DRC and the gerber/drill stage are NOT_VERIFIED, KiCad's STEP/GLB/render exports are skipped
  with a note only (the built-in 3D preview still compiles). Say so in "Tools not run and why".
- `kicad libs: NOT FOUND` (no KiCad at all): no template can build, because every part's symbol and
  footprint are copied from the KiCad library. Measured: the ARCHITECTURE stage prints
  `template divider not proposed: symbol Device:R not found in the KiCad libraries []`, the design stays
  empty, the review FAILs with `requirements not traced to any component` and the run exits 1. There is
  nothing to design until KiCad 10 is installed; do not describe that run as a design.
- `ngspice` missing: the SPICE stage is NOT_VERIFIED; every expectation stays unverified. The optional
  standalone `ngspice` executable is not a fallback the pipeline uses. `NGSPICE_DLL=<absolute path>` points
  the tool at a `libngspice` the user already has.

## 3. Checks you can still run by hand on the compiled files

`ai-eda` writes `<workdir>/<name>.kicad_sch`, `.kicad_pcb` and `.kicad_pro`. With a `kicad-cli` the user
installs later (or on another machine), the same checks the tool runs are:

```
kicad-cli sch erc --format json --severity-all -o erc.json <name>.kicad_sch
kicad-cli pcb drc --format json --severity-all -o drc.json --refill-zones --schematic-parity <name>.kicad_pcb
```

(The pipeline's `<name>.cir` is compiled from `ir.json` by the tool itself; `kicad-cli sch export netlist`
makes a different netlist the tool never runs or simulates.)

Exit codes 0 and 5 both mean the check ran; the verdict is the JSON report, where any violation, warnings
included, counts as a finding. Exit 3 means the input did not load, 1 a bad flag.

A hand-run check is not a pipeline result: `ir.json` does not record it, `review` and RELEASE do not see
it, and the report labels nothing. Record it for the user as an evidence ledger row:

```
# tool | version | command | input file sha256 | report file sha256 | findings | run by / when
```

and say "manual check, not in the project's validation log". Re-run `ai-eda run` once the tool is on the
machine so the result is stamped with the IR hash.

## 4. No `ai-eda` at all

Do not reproduce the pipeline by hand. The agent can read an existing `ir.json`, `pipeline.json` and
`report.html` as data and explain them with the status rules of SKILL.md, but it must not produce a
verdict of its own: without the tool every claim is an opinion (NOT_VERIFIED). Point the user at the
installer of the AI EDA Engineer repository (`install.cmd` on Windows, `./install.sh` on macOS / Linux),
which ends with `ai-eda selftest` (it proves the installation) when KiCad is ready - skipped with
`--skip-selftest` / `-SkipSelftest`, `--no-kicad` / `-NoKicad` or after a failed `setup-kicad`, in which case
`ai-eda setup-kicad` and `ai-eda selftest` must be run by hand - and ask before running it (`system_install`).
