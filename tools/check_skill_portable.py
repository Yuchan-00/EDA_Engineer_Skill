# Copyright (c) 2026 Yuchan (github.com/Yuchan-00). MIT License with Commons Clause (no selling) - see LICENSE.
"""Portability checks for the eda-engineer skill (PLAN 9.3 rules I1-I9, I11) - stdlib only, exit 1 on the first failing rule.

Run from the repository root:  python tools/check_skill_portable.py [--sync]
--sync copies .agents/skills/eda-engineer to .claude/skills/eda-engineer before the byte-identity check (I11).
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / ".agents" / "skills" / "eda-engineer"
COPY = ROOT / ".claude" / "skills" / "eda-engineer"
REFERENCES = ("pipeline.md", "answers.md", "without-cli.md")
MAX_SKILL_LINES = 250
MAX_DESCRIPTION = 1024
TOP_BLOCK_LINES = 40
ALLOWED_FRONTMATTER = {"name", "description", "license", "compatibility", "metadata"}
#: I5: every fenced command line must start with one of these
COMMAND_PREFIXES = ("ai-eda", "python -m ai_eda.cli", "<repo>/.venv/Scripts/ai-eda.exe", "<repo>/.venv/bin/ai-eda", "$env:PYTHONUTF8", "export PYTHONUTF8", "kicad-cli", "ngspice", "pytest", "cd ", "#", "python <skill>/scripts/deliver.py")
#: I3: host / tool names that must not appear, except on lines the allow list below matches
HOST_WORDS = re.compile(r"\b(claude|codex|cursor|gemini|copilot|antigravity|Read tool|Grep|Bash tool)\b", re.I)
HOST_ALLOW = (re.compile(r"--llm\s+\S*claude"), re.compile(r"claude cli", re.I), re.compile(r"^\s*>\s"), re.compile(r"doctor", re.I))
CLAUDE_ONLY = re.compile(r"\$ARGUMENTS|\$[0-9]\b|\$\{CLAUDE_|^!`", re.M)
SLASH_CALL = re.compile(r"/eda-engineer\b|\$eda-engineer\b")
ABS_PATHS = re.compile(r"~/\.claude|[A-Z]:\\")


def fail(rule: str, msg: str) -> None:
    print(f"FAIL {rule}: {msg}")
    sys.exit(1)


def frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        fail("I1", "SKILL.md has no frontmatter")
    end = text.index("\n---", 4)
    out: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def main() -> int:
    sync = "--sync" in sys.argv
    skill = SRC / "SKILL.md"
    if not skill.exists():
        fail("I1", f"{skill} missing")
    text = skill.read_text(encoding="utf-8")
    lines = text.splitlines()
    fm = frontmatter(text)
    if fm.get("name") != SRC.name:
        fail("I1", f"frontmatter name {fm.get('name')!r} != directory {SRC.name!r}")
    if not re.fullmatch(r"[a-z0-9-]{1,64}", fm.get("name", "")):
        fail("I1", "name must be lowercase-hyphen, <= 64 chars")
    extra = set(fm) - ALLOWED_FRONTMATTER
    if extra:
        fail("I1/I2", f"frontmatter keys not allowed: {sorted(extra)}")
    desc = fm.get("description", "")
    if not desc or len(desc) > MAX_DESCRIPTION:
        fail("I1", f"description missing or longer than {MAX_DESCRIPTION} chars ({len(desc)})")
    if len(re.findall(r'"[^"]{4,}"', desc)) < 5:
        fail("G6", "description quotes fewer than 5 trigger phrases")
    tree = [skill] + [SRC / "references" / r for r in REFERENCES]
    for p in tree:
        if not p.exists():
            fail("I7", f"{p} missing")
        body = p.read_text(encoding="utf-8")
        if CLAUDE_ONLY.search(body):
            fail("I2", f"{p.name}: Claude-Code-only syntax found")
        for n, ln in enumerate(body.splitlines(), 1):
            if HOST_WORDS.search(ln) and not any(a.search(ln) for a in HOST_ALLOW):
                fail("I3", f"{p.name}:{n}: host or tool name: {ln.strip()[:80]}")
        if SLASH_CALL.search(body):
            fail("I4", f"{p.name}: slash / $ invocation assumed")
        if ABS_PATHS.search(body):
            fail("I6", f"{p.name}: absolute or ~/.claude path")
        if p.name != "SKILL.md" and "references/" in body:
            fail("I7", f"{p.name}: a reference links another reference (one level only)")
        in_fence = False
        for n, ln in enumerate(body.splitlines(), 1):
            if ln.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence and ln.strip() and not ln.startswith(" ") and not ln.strip().startswith(COMMAND_PREFIXES):
                fail("I5", f"{p.name}:{n}: command line outside the allow list: {ln.strip()[:80]}")
    if len(lines) > MAX_SKILL_LINES:
        fail("I7", f"SKILL.md has {len(lines)} lines > {MAX_SKILL_LINES}")
    for r in REFERENCES:
        if f"references/{r}" not in text:
            fail("I7", f"SKILL.md does not link references/{r} with a reading cue")
    if "<repo>/.venv/Scripts/ai-eda.exe" not in text or "<repo>/.venv/bin/ai-eda" not in text:
        fail("I6", "both venv fallback forms must appear")
    if "$env:PYTHONUTF8" not in text or "export PYTHONUTF8" not in text:
        fail("I6", "PYTHONUTF8 must be given for PowerShell and bash")
    top = "\n".join(lines[:TOP_BLOCK_LINES]).lower()
    for needle, rule in (("hard limit", "I9 hard limits"), ("never", "I9 external actions"), ("data, not instruction", "I9 observed text")):
        if needle not in top:
            fail("I9", f"{rule} block not within the first {TOP_BLOCK_LINES} lines ({needle!r} missing)")
    # I8/I9: the tool's twelve external-action names, spelled as its ExternalAction enum, in the top block
    for action in ("git_push", "external_upload", "secret_access", "system_install", "system_delete", "pcb_order", "component_purchase",
                   "paid_api_call", "manufacturing_order", "regulatory_submission", "network_fetch", "subscription_use"):
        if action not in top:
            fail("I9", f"external action {action!r} not named within the first {TOP_BLOCK_LINES} lines")
    if sync:
        if COPY.exists():
            shutil.rmtree(COPY)
        shutil.copytree(SRC, COPY, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if "scripts/deliver.py" in text and not (SRC / "scripts" / "deliver.py").exists():
        fail("I7", "SKILL.md names scripts/deliver.py, which is missing")
    if COPY.exists():
        def shipped(base: Path) -> list[Path]:
            return sorted(q.relative_to(base) for q in base.rglob("*") if q.is_file() and "__pycache__" not in q.parts)

        if shipped(SRC) != shipped(COPY):  # both ways: a file only in the copy ships too
            fail("I11", f"{COPY} and {SRC} hold different files: {sorted(set(shipped(SRC)) ^ set(shipped(COPY)))} (run with --sync)")
        for p in (SRC / rel for rel in shipped(SRC)):  # every shipped file, not only the documents
            q = COPY / p.relative_to(SRC)
            if not q.exists() or q.read_bytes() != p.read_bytes():
                fail("I11", f"{q} differs from {p} (run with --sync)")
    print(f"OK: {skill.relative_to(ROOT)} {len(lines)} lines, description {len(desc)} chars, references {len(REFERENCES)}, copy {'checked' if COPY.exists() else 'absent'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
