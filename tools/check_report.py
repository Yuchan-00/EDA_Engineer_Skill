# Copyright (c) 2026 Yuchan (github.com/Yuchan-00). MIT License with Commons Clause (no selling) - see LICENSE.
"""G2: does a saved summary have the six sections of SKILL.md's report contract? Headers only - evidence stays with `ai-eda review` / `report`.

Run from anywhere:  python tools/check_report.py REPORT.md
Exit 0 = all six found, 1 = a section is missing (each is named), 2 = bad usage or unreadable file.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SECTIONS = ("Tools run", "Tools not run and why", "Verified vs reasoned", "Blockers", "Not performed / review limits", "Verdict")


def outside_code_fences(text: str) -> str:
    """The lines of ``text`` that are not in a fenced code block: an example of a header is not a header."""
    kept, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced:
            kept.append(line)
    return "\n".join(kept)


def has_header(title: str, text: str) -> bool:
    """A section header is a Markdown heading, a bold title, or the title and a colon, each at the start of a line."""
    t = re.escape(title).replace(r"\ ", r"[ \t]+")
    item = r"(?:(?:\d+[.)]|[-*])[ \t]+)?"
    pattern = rf"^[ \t]*(?:\#{{1,6}}[ \t]+{item}[*_]*{t}\b|{item}(?:\*\*|__){t}\b|{item}{t}[ \t]*:)"
    return re.search(pattern, text, re.I | re.M) is not None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_report.py REPORT.md")
        return 2
    try:
        text = Path(argv[1]).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        print(f"cannot read {argv[1]}: {e}")
        return 2
    text = outside_code_fences(text)
    missing = [s for s in SECTIONS if not has_header(s, text)]
    for s in missing:
        print(f"MISSING section: {s}")
    if not missing:
        print(f"OK: all {len(SECTIONS)} sections found")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
