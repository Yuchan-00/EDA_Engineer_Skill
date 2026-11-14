# Copyright (c) 2026 Yuchan (github.com/Yuchan-00). MIT License with Commons Clause (no selling) - see LICENSE.
"""Repository checks (PLAN G2, G5), stdlib only. Run from the repository root:  python -m unittest discover -s tests"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import check_report  # noqa: E402

FULL = "\n".join(f"## {title}\n\ntext\n" for title in check_report.SECTIONS)
#: G5: scripts we ship or run take list arguments, never evaluate text and open no network connection before approval
FORBIDDEN = re.compile(r"shell=True|\beval\(|\bexec\(|urllib|requests|httpx")


def run_tool(report: str) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "report.md"
        path.write_text(report, encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "tools" / "check_report.py"), str(path)], capture_output=True, text=True)
    return done.returncode, done.stdout


class CheckReport(unittest.TestCase):
    def test_full_report_passes(self) -> None:
        self.assertEqual(run_tool(FULL), (0, "OK: all 6 sections found\n"))

    def test_each_removed_header_fails_and_is_named(self) -> None:
        for title in check_report.SECTIONS:
            with self.subTest(title):
                code, out = run_tool(FULL.replace(f"## {title}\n", "\n"))
                self.assertEqual(code, 1)
                self.assertEqual(out, f"MISSING section: {title}\n")

    def test_numbered_bold_and_colon_forms_count(self) -> None:
        for form in ("1. **{}** (detail)", "- {}: detail", "### 2. {}"):
            with self.subTest(form):
                text = "\n".join(form.format(t) for t in check_report.SECTIONS)
                self.assertEqual(run_tool(text)[0], 0)

    def test_a_word_in_prose_is_not_a_header(self) -> None:
        self.assertFalse(check_report.has_header("Verdict", "The verdict is pending.\nNo Verdict: yet here"))

    def test_headers_in_a_code_fence_do_not_count(self) -> None:
        self.assertEqual(run_tool(f"```\n{FULL}```\n")[0], 1)

    def test_a_title_broken_over_two_lines_is_not_a_header(self) -> None:
        self.assertFalse(check_report.has_header("Tools run", "## Tools\nrun"))

    def test_unreadable_file_is_exit_2(self) -> None:
        self.assertEqual(check_report.main(["check_report.py", str(ROOT / "no-such-report.md")]), 2)

    def test_titles_are_the_ones_skill_md_promises(self) -> None:
        skill = (ROOT / ".agents" / "skills" / "eda-engineer" / "SKILL.md").read_text(encoding="utf-8")
        contract = skill.split("## Report contract", 1)[1].split("\n## ", 1)[0]
        self.assertEqual(tuple(re.findall(r"\d\. \*\*([^*]+)\*\*", contract)), check_report.SECTIONS)


class NoForbiddenCalls(unittest.TestCase):
    def test_tools_and_skill_scripts_are_clean(self) -> None:
        files = sorted((ROOT / "tools").glob("*.py")) + sorted((ROOT / ".agents" / "skills").rglob("*.py"))
        self.assertTrue(files)
        hits = [f"{p.name}:{n}" for p in files for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if FORBIDDEN.search(line)]
        self.assertEqual(hits, [])


class CopyrightHeaders(unittest.TestCase):
    def test_every_skill_file_and_tool_names_the_copyright_holder(self) -> None:
        skill = ROOT / ".agents" / "skills" / "eda-engineer"
        files = [p for p in skill.rglob("*") if p.is_file() and "__pycache__" not in p.parts] + sorted((ROOT / "tools").glob("*.py")) + sorted((ROOT / "tests").glob("*.py"))  # a byte-code cache is not shipped (.gitignore)
        self.assertGreaterEqual(len(files), 8)
        missing = [p.name for p in files if "Copyright (c) 2026 Yuchan" not in "\n".join(p.read_text(encoding="utf-8").splitlines()[:5])]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
