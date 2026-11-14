<!-- Copyright (c) 2026 Yuchan (github.com/Yuchan-00). MIT License with Commons Clause (no selling) - see LICENSE. -->
# The ai-eda pipeline: stages, check ids, statuses, evidence

Read this when you must explain what a stage did, what a check id means, why a status is what it is,
or what counts as evidence. Facts below were read from the tool's source (ai_eda 0.0.1) and measured on
KiCad 10.0.6 / ngspice-46; nothing here is a promise about other versions.

## The 19 stages (`ai-eda run`, in order)

The run stops at the first stage whose outcome is USER_INPUT_REQUIRED or that carries a required question
(`state.blocked = true`, exit 1). A stage that raises a Python exception is a defect, not a verdict.

| # | stage | what runs | PASS when | NOT_VERIFIED when | FAIL when | check ids |
|---|---|---|---|---|---|---|
| 1 | requirement_analysis | baseline checklist; with `--llm` the model extracts requirements from the request text | extraction confirmed by the user (with `--llm` it is USER_INPUT_REQUIRED until then) | no LLM or empty request: no result is written, free text not parsed; the model call failed | - | requirements.extraction (only with `--llm`) |
| 2 | missing_information | required checklist questions still open? | none open and the extraction confirmed | none open but no LLM analysis | - | (none) |
| 3 | regulatory_research | official texts (fetched only with `--online`; copies archived by an earlier online run are read offline), applicability, compliance | never: `regulatory.compliance` is ALWAYS NOT_VERIFIED, so the stage is at best NOT_VERIFIED (check level: `regulatory.sources` PASS when every text is archived and every quote found; `regulatory.applicability` PASS when all candidates are decided and grounded) | offline without an archive; undecided or ungrounded candidates | a claimed quote missing from the archived text (`regulatory.sources`) | regulatory.scope, regulatory.sources, regulatory.applicability, regulatory.compliance, regulatory.research (+ regulatory.proposals for model proposals) |
| 4 | architecture | template selection; `confirm_design` table; on `yes` the design is applied | template inputs still equal the requirements (`design.inputs_vs_requirements`) | proposals applied, nothing verified | inputs changed since (`repair=human`) | design.inputs_vs_requirements |
| 5 | component_selection | part existence = worst of six sub-checks (symbol, footprint, datasheet pointer, archived datasheet, MPN verbatim in it, catalog row: NOT_APPLICABLE without `--catalog`) and datasheet facts | every sub-check PASS (the first fetch needs `--online`; an archived, hash-verified copy also passes offline) | not fetched and not archived; an HTML page; facts not grounded | - | component.existence.`<ref>`, component.facts.`<ref>` (`.llm` for model facts), component.candidates |
| 6 | placement | deterministic placement + maze routing proposal | - (no result of its own) | always: a proposal is not evidence | - | (none) |
| 7 | fab_capability | fab limits from `--fab-capability FILE` grounded on the archived page; without the file, limits already in the IR are re-verified against the archive | every limit grounded (or re-verified) | page not obtained / no board; without a file and without IR limits no result at all | - | mfg.capability_source |
| 8 | ir_build | every registered IR validator that applies to the design (domain-scoped ones only when `ir.topology` lists their domain) | all validators PASS | a validator could not check | duplicate refs, unknown pins, keep-out violations, Tj over limit | ir.* (`ir.assumptions` / `ir.llm_requirements` block as USER_INPUT_REQUIRED), component.fit, domain.*, pcb.*, si.*, rf.*, block.interface.*, power.* |
| 9 | calculation | every `derived` value recomputed by its registered calculator | all values match | nothing derived, or an unregistered tool | a mismatch (`human`) | calc.recompute |
| 10 | spice | netlist compiled, analyses run on ngspice, expectations judged | every expectation PASS | no engine, no setup, nothing compilable, AM on ngspice < 43 | compile refused, an expectation FAIL | spice, spice.`<expectation>`, spice.si.`<net>`, spice.rf.`<network>` |
| 11 | schematic | `.kicad_sch` + `.kicad_pro` compiled from the IR (small nets drawn as wires, labels on every pin) | compiled | nothing to compile | compile refused (`human`) | compile.kicad_sch, compile.kicad_pro |
| 12 | erc | `kicad-cli sch erc` on the fresh schematic | 0 violations | kicad-cli missing / no schematic | any violation, warnings included | kicad.erc |
| 13 | pcb | `.kicad_pcb` compiled (+ a 3D preview that is a picture, never a check) | compiled | nothing to compile | compile refused | compile.kicad_pcb |
| 14 | drc | `kicad-cli pcb drc --severity-all --refill-zones` (+ `--schematic-parity` when `<stem>.kicad_sch` sits beside the board) | 0 violations, 0 unconnected items, 0 parity findings | kicad-cli missing / no board | any violation, unconnected item or parity finding, warnings included | kicad.drc |
| 15 | manufacturability | board geometry vs the fab limits in the IR | compared and within limits | no board / limits not proven | below the fab minimums (`fab_capability_shortfall`) | mfg.capability |
| 16 | manufacturing_outputs | BOM, CPL, gerbers, drill, 3D exports | all compiled and checked | export skipped (no kicad-cli / no board) | an output check FAIL | compile.bom, compile.cpl, compile.gerber, compile.drill, mfg.gerber, mfg.drill |
| 17 | independent_review | 14 review areas comparing IR, artifacts, tool reports and requirements | every area PASS | a needed artifact or tool report missing | a mismatch (details name both sides) | review.* (14, listed below) |
| 18 | repair | deterministic loop: regenerate artifacts, re-run tools (max 5 iterations) | every action succeeded, no failures left | an action failed | findings stay unresolved, or a strategy changed the IR | repair.loop |
| 19 | release | evidence audit of the latest result per check id | all PASS or NOT_APPLICABLE, tool-backed, about this IR version | otherwise ("not releasable: ...") | the overall status when it is FAIL | (none: a stage verdict only) |

Stage line format: `<stage padded to 24> <STATUS padded to 20> <message>`. Review areas (stage 17):
review.requirements_vs_ir, review.ir_vs_schematic, review.ir_vs_pcb, review.schematic_vs_pcb,
review.pcb_vs_bom, review.pcb_vs_cpl, review.manufacturing_outputs, review.calculations_vs_design,
review.spice_vs_requirements, review.erc, review.drc, review.regulatory_provenance,
review.component_provenance, review.manufacturing_capabilities.

## Statuses

`PASS`, `FAIL`, `NOT_VERIFIED`, `NOT_APPLICABLE`, `USER_INPUT_REQUIRED`, `UNRESOLVED`. Severity for
aggregation, worst last: NOT_APPLICABLE < PASS < NOT_VERIFIED < USER_INPUT_REQUIRED < UNRESOLVED < FAIL.
An empty set of results aggregates to NOT_VERIFIED ("absence of evidence is not evidence"). A result
without a `tool` is an opinion; RELEASE rejects a PASS opinion. UNRESOLVED is a measurement that could not
be judged: its bias bracket or sweep-interpolation bracket straddles the limit (the message names the
remedy: a lower tran step, a faster carrier, whole periods, a sweep point at `at`, or a wider tolerance), no
usable tolerance, a one-sided bound given beside a tolerance, or a review check that raised.

## Repair categories (`details.repair` on a FAIL)

`regenerate` (an artifact is stale or edited: the repair loop recompiles it), `rerun_tool` (a tool report
is stale: ERC, DRC, gerber/drill checks, spice are re-run), `human` (the design itself: calculation
mismatch, failed expectation, BOM/board disagreement, keep-out, thermal), `fab_capability_shortfall`,
`regulatory_conflict`, `unverified_component_data`, `circuit_structure_change`. Only the first two are
repaired automatically; the loop refuses to change the IR (a strategy that changes the IR hash is recorded
as failed).

## Evidence and freshness

- Every tool result is stamped with the IR hash it judged (`ir_hash`); one that read an artifact (ERC, DRC,
  gerber/drill checks, spice) also carries its hash (`artifact_hash`); the 14 review results, `repair.loop`
  and `mfg.capability` judge the IR alone. `evidence` rows are files, mostly with a `sha256:` content hash
  (ERC/DRC JSON reports, `spice/results.json`, the netlist, ngspice rawfiles); gerber/drill rows carry a path
  only and the report shows them as "present (no hash recorded)".
- `ai-eda report` labels each result: `fresh` (judged this IR version), `stale (IR <hash>)`, `unstamped
  (produced by the recorded run)`, `unstamped (carried over from an earlier run - vouches for nothing
  now)`, `unstamped (run unknown)`, `opinion (no tool)`. The report computes no verdict of its own; its one
  derived figure, the worst-of aggregate of the latest results, is labelled "aggregate of the latest results
  - not a release verdict; see RELEASE".
- `ai-eda review --json` prints the 14 text lines and a `review <STATUS>: ...` summary, then
  `{"ir_hash": ..., "results": [...]}` with the 14 review results; exit 1 on any FAIL, 0 otherwise.
- Artifacts (`.kicad_sch`, `.kicad_pcb`, `.kicad_pro`, BOM, CPL, gerbers, netlists) are derived from the IR
  and registered with the IR hash they came from; an edited or stale file is refused ("regenerate it
  first"). `pipeline.json` is a run log, never an artifact.

## Measured facts that bound what the tool can say

- KiCad: `kicad-cli` 10 or newer is required (the files are KiCad 10 format). `kicad-cli` exit codes 0 and 5
  are both "the check ran"; the verdict comes from the JSON report, where any violation (error or warning,
  excluded or not) is FAIL. Exit 3 (input not loadable) and 1 (bad flag) are tool errors, not verdicts.
- ngspice: `NGSPICE_DLL` (an absolute path to an existing file; empty or relative counts as unset, a missing
  file is "not found" with no fallback), else KiCad's bundled library (`ngspice.dll` beside `kicad-cli.exe`,
  `libngspice*.dylib` in KiCad.app), else the system `libngspice` (Linux packages, Homebrew); the standalone
  `ngspice` executable is optional and never used by the pipeline. Decks carry no `.control`
  block; analyses are issued as commands.
- AM sources are written in ngspice 43+'s form; on an older ngspice, or one whose version cannot be read,
  the SPICE stage stops before running (NOT_VERIFIED with the reason). Measured on ngspice-46.
- The astable template's frequency-deviation anchor is per engine version (ngspice-42: 4.9 %, ngspice-46:
  5.04 %). The anchor is a development-time test (skipped for an unmeasured engine, never borrowing a
  neighbour's number); the SPICE stage itself judges every engine against the template's 10 % tolerance.
- SPICE judges nominal part values at one temperature: no tolerance corners, no Monte Carlo; every `spice`
  summary and `spice.<expectation>` result of a run says so in `details.conditions` (retired and
  engine-unavailable results carry none).
- An expectation whose `bound` is set (a one-sided `at_most` / `at_least` limit, e.g. `on_drop` and
  `off_clamp` of bjt_lowside_switch, `rise` of i2c_pullup, many RF rows) cannot name a requirement id; the
  compiler refuses one that does. So `review.spice_vs_requirements` PASSes with `(0 traced to requirements,
  ...)` for such a design by design (measured on bjt_lowside_switch: `2 expectation(s) verified ... (0
  traced to requirements`): the count covers only expectations that name a requirement. A bound's link to
  its requirement is the template's own statement (the expectation's provenance text, the net or part whose
  `serves_requirements` names it); `review.requirements_vs_ir` checks that every design requirement is
  served by some part or net, not that a bound verified it. Report the bound's own `spice.<expectation>`
  verdict, and do not call "0 traced" a defect.
- Simulation-only elements (a bus capacitance, an idealised driver) appear in the netlist and the theory
  report with their reason, never in the BOM, CPL, schematic or placement.

## External actions and the only approvals (safety block)

Twelve actions the tool models and the agent never takes first: `git_push`, `external_upload`,
`secret_access`, `system_install`, `system_delete`, `pcb_order`, `component_purchase`, `paid_api_call`,
`manufacturing_order`, `regulatory_submission`, `network_fetch`, `subscription_use`. An approval never
generalises to another action: each flag grants one, consumed once when the run's network policy or model
service is built, and every fetch or model call of that run then rides on it (bounded by the trusted hosts
and the budget). The CLI grants exactly these, and only when the user types the flag:

| flag or answer | action approved |
|---|---|
| `--llm-budget-usd X` / `--llm-budget-tokens N` | paid_api_call (required with `--llm openrouter`) |
| `--llm claude` | subscription_use (the user's own CLI login; no per-call charge, quota is used) |
| `--online` (optionally `--trust-host HOST`, `--datasheet-url REF=URL`, `--source-url ID=URL`) | network_fetch: https only, trusted hosts only, archived by sha256 under `<workdir>/sources` |
| `ai-eda doctor --online` | secret_access (sends the OpenRouter key once to read its limit) |
| `--answer extract_datasheet_facts=yes`, `--answer propose_regulations=yes` | not an approval: a billed model call spent under the budget or subscription above (needs `--llm`) |

No flag exists for the other eight; they are never done by the tool and must not be done by the agent.
Without `--llm` the pipeline makes no model call; without `--online` nothing is fetched (no outbound socket
for sources). The only other outbound connections are model calls (`--llm openrouter`, approved by the budget
flags; `--llm claude` spawns the user's Claude CLI). `serve` and `gui` listen on 127.0.0.1 without a flag.
