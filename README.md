<div align="center">

# EDA Engineer Skill

**Verification-first electronics design for AI agents**

[![License: MIT + Commons Clause](https://img.shields.io/badge/license-MIT%20%2B%20Commons%20Clause-blue)](LICENSE)
[![Agent Skill](https://img.shields.io/badge/Agent%20Skill-SKILL.md-black)](.agents/skills/eda-engineer/SKILL.md)
[![Hosts](https://img.shields.io/badge/hosts-Claude%20Code%20%7C%20Codex-555)](#supported-hosts)

[Skill](.agents/skills/eda-engineer/SKILL.md) / [Pipeline](.agents/skills/eda-engineer/references/pipeline.md) / [Answers](.agents/skills/eda-engineer/references/answers.md) / [한국어](README.ko.md)

</div>

The `eda-engineer` skill lets an AI agent design, simulate and check small electronic circuits through the
`ai-eda` CLI of the AI EDA Engineer reference system - KiCad schematic and PCB, ngspice simulation, ERC/DRC,
BOM/CPL and an independent review. Every number has a provenance, every verdict comes from a tool, and
"we could not check" is its own status.

## Quick start

Copy the skill into the folder your agent loads skills from:

```bash
# Claude Code
cp -r .claude/skills/eda-engineer <your-project>/.claude/skills/
# Codex (and other Agent Skills loaders)
cp -r .agents/skills/eda-engineer <your-project>/.agents/skills/
```

- The skill drives the `ai-eda` CLI; install the [AI EDA Engineer](https://github.com/Yuchan-00/AI_EDA_Engineer) reference system first ([what the skill expects](.agents/skills/eda-engineer/SKILL.md)).
- ERC / DRC need `kicad-cli` (KiCad 10+); SPICE needs a shared ngspice library ([details](.agents/skills/eda-engineer/references/pipeline.md)).
- No CLI at hand: [working without the CLI](.agents/skills/eda-engineer/references/without-cli.md).

Then ask in plain words - "design a 12 V to 5 V divider", "회로 설계해 줘". Under the hood the skill runs:

```bash
ai-eda new divider --dir ./divider --request "12 V to 5 V unloaded divider"
ai-eda run ./divider/ir.json --answer application="bench reference" --answer jurisdiction=EU \
  --answer input_voltage="12 V" --answer output_voltage="5 V" --no-pdf      # stops at the design table
ai-eda run ./divider/ir.json --answer confirm_design=yes --no-pdf            # only after you confirm it
ai-eda stage-reports ./divider/ir.json && ai-eda report ./divider/ir.json
python <skill>/scripts/deliver.py ./divider --lang en                       # two PDF reports + one zip
```

## Description

- Requirements to KiCad project in one confirmed step: templates or a design file (`ai-eda run --design FILE.json`), shown as a table you confirm before anything enters the design.
- Purchasable part values: resistors, capacitors and inductors placed at IEC 60063 E-series values, and the circuit judged with them.
- Simulation with ngspice against stated expectations; waveforms in the reports.
- ERC and DRC from `kicad-cli`, never from the model.
- Deterministic placement and routing in the reference system, with every track and via traceable to its rule.
- Hand-over: a summary report and a detailed report (PDF, Korean or English) and one zip with the KiCad project, Gerbers, drill files, BOM, CPL and reports.
- Hard limits: no installing, buying, uploading or pushing on the agent's own; no confirming a design for the user; part facts read from the manufacturer's datasheet, never from memory.

## Supported hosts

| Host | Skill folder | Notes |
|---|---|---|
| Claude Code | `.claude/skills/eda-engineer/` | byte-identical copy of the `.agents` folder |
| Codex | `.agents/skills/eda-engineer/` | `agents/openai.yaml` for Codex-only metadata |
| Other Agent Skills loaders | `.agents/skills/eda-engineer/` | loads `SKILL.md` by its description |

## Documentation

#### Skill

- [SKILL.md](.agents/skills/eda-engineer/SKILL.md) - what the agent may and may not do, the happy path
- [references/pipeline.md](.agents/skills/eda-engineer/references/pipeline.md) - stages, statuses, exit codes, external actions
- [references/answers.md](.agents/skills/eda-engineer/references/answers.md) - answer keys for `--answer`
- [references/without-cli.md](.agents/skills/eda-engineer/references/without-cli.md) - what to do without the CLI
- [scripts/deliver.py](.agents/skills/eda-engineer/scripts/deliver.py) - reports and zip at the end of a run

#### Tools

- [tools/check_skill_portable.py](tools/check_skill_portable.py) - portability checks (`--sync` refreshes the `.claude` copy)
- [tools/check_report.py](tools/check_report.py) - checks that a report has the promised section titles
- [tests/](tests/) - tests of the tools and of `deliver.py` (`python -m pytest tests -q`)

## Contributing

- Keep `.agents/skills/eda-engineer/` and `.claude/skills/eda-engineer/` identical: run `python tools/check_skill_portable.py --sync`.
- A "measured" claim needs its command, versions and result on record.
- Part facts (pinout, pin function, rating) come from the manufacturer's datasheet, cited; never from memory.
- Never widen a tolerance to make a test pass.

## Acknowledgements

- [AI EDA Engineer](https://github.com/Yuchan-00/AI_EDA_Engineer) reference system - the `ai-eda` CLI the skill drives (MIT + Commons Clause)
- [KiCad](https://www.kicad.org/) - schematic, PCB, ERC, DRC, Gerber export, run as an external tool (GPL-3.0-or-later)
- [ngspice](https://ngspice.sourceforge.io/) - circuit simulation, loaded as a shared library (license: see the project)
- [aklofas/kicad-happy](https://github.com/aklofas/kicad-happy) and [fxp/ee-skills](https://github.com/fxp/ee-skills) - studied as references for structure and method, no file copied (MIT; see [NOTICE](NOTICE))

## License

MIT License with the Commons Clause ([LICENSE](LICENSE)): free to use, copy, modify and share, including loading the skill into your own agent; not for sale, nor a product or service whose value comes substantially from it, without a separate agreement. Source-available, not OSI open source. This repository is an Agent Skill, not an MCP server; listings of it on third-party directories were not created by the author.

Copyright (c) 2026 Yuchan ([github.com/Yuchan-00](https://github.com/Yuchan-00)).
