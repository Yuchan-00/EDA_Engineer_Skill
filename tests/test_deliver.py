# Copyright (c) 2026 Yuchan (github.com/Yuchan-00). MIT License with Commons Clause (no selling) - see LICENSE.
"""scripts/deliver.py on a hand-made project folder: what it writes, what it copies, what it refuses (no KiCad, no browser needed)."""

from __future__ import annotations

import json
import hashlib
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".agents" / "skills" / "eda-engineer" / "scripts" / "deliver.py"
SPEC = importlib.util.spec_from_file_location("deliver", SCRIPT)
deliver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deliver)

STAGES = [
    {"stage": "spice", "status": "PASS", "message": "1 analysis(es) run, 1 expectation(s): 1 PASS"},
    {"stage": "schematic", "status": "PASS", "message": "demo.kicad_sch"},
    {"stage": "erc", "status": "PASS", "message": "0 error(s), 0 warning(s)"},
    {"stage": "pcb", "status": "PASS", "message": "demo.kicad_pcb"},
    {"stage": "drc", "status": "FAIL", "message": "2 error(s): clearance <too small> & more"},
    {"stage": "release", "status": "NOT_VERIFIED", "message": "not releasable: overall validation is FAIL (drc)"},
]
IR = {
    "project": {"id": "demo", "created_at": "2026-11-12T00:00:00Z"},
    "topology": {"name": "demo divider"},
    "requirements": {"requirements": [{"id": "req.output_voltage", "key": "output_voltage", "text": "output_voltage: 5 V", "value": {"value": 5.0, "unit": "V", "provenance": {"kind": "user_requirement"}}}]},
    "simulation": {
        "analyses": [{"id": "op", "kind": "op"}, {"id": "tran", "kind": "tran"}, {"id": "ac", "kind": "ac"}],
        "expectations": [
            {"id": "v_out", "analysis_id": "op", "vector": "v(VOUT)", "reduce": "value", "nominal": {"value": 5.0, "unit": "V"}, "requirement_id": "req.output_voltage"},
            {"id": "v_rise", "analysis_id": "tran", "vector": "v(VOUT)", "reduce": "max", "nominal": {"value": 5.0, "unit": "V"}},
        ],
    },
    "nets": [
        {"name": "VOUT", "kind": "signal", "net_class": "Default", "pins": [{"component_ref": "R1", "pin_number": "2"}, {"component_ref": "R2", "pin_number": "1"}]},
        {"name": "NC", "kind": "signal", "net_class": "Default", "pins": [{"component_ref": "J1", "pin_number": "3"}, {"component_ref": "J1", "pin_number": "4"}]},
    ],
    "validation": {"results": [
        {"check_id": "spice.v_out", "status": "FAIL", "message": "old run", "details": {"measured": 4.0}},
        {"check_id": "spice.v_out", "status": "PASS", "message": "v(VOUT) = 5 V, nominal 5 V", "details": {"measured": 5.0}},
    ]},
    "pcb": {"layers": [{"name": "F.Cu"}, {"name": "B.Cu"}], "placements": [1, 2], "vias": [{"net": "VOUT"}],
            "tracks": [{"net": "VOUT", "layer": "F.Cu", "start": [0, 0], "end": [3, 4]}, {"net": "VOUT", "layer": "B.Cu", "start": [3, 4], "end": [3, 10]}]},
}


def make_project(folder: Path, *, board: bool = True) -> Path:
    project = folder / "demo"
    (project / "reports").mkdir(parents=True)
    (project / "gerber").mkdir()
    (project / "ir.json").write_text(json.dumps(IR), encoding="utf-8")
    (project / "pipeline.json").write_text(json.dumps({"state": {"outcomes": STAGES}}), encoding="utf-8")
    (project / "bom.csv").write_text("Reference,Value,Description,Manufacturer,MPN,Package,Footprint,Supplier,SupplierPN,DatasheetHash,Qty\nR1,14k,upper,NOT_VERIFIED,NOT_VERIFIED,x,Resistor_SMD:R_0603,x,x,x,1\n", encoding="utf-8")
    for name in ("demo.kicad_pro", "demo.kicad_sch", "demo.cir", "cpl.csv", "gerber/demo-F_Cu.gbr", "gerber/demo.drl"):
        (project / name).write_text("x", encoding="utf-8")
    if board:
        (project / "demo.kicad_pcb").write_text("x", encoding="utf-8")
    (project / "reports" / "01_이론_보고서.html").write_text("<html><head><title>이론 보고서: demo</title><style>p{}</style></head><body><h1>이론</h1><h2>동작 원리</h2><p>본문</p></body></html>", encoding="utf-8")
    # ngspice rawfiles as the pipeline leaves them: a three-point transient, a one-point operating point, and none for the ac analysis
    (project / "spice" / "tran").mkdir(parents=True)
    (project / "spice" / "op").mkdir()
    (project / "spice" / "tran" / "demo.tran.raw").write_text(
        "Title: demo\nPlotname: Transient Analysis\nFlags: real\nNo. Variables: 2\nNo. Points: 3\nVariables:\n\t0\ttime\ttime\n\t1\tv(vout)\tvoltage\nValues:\n"
        " 0\t0.0\n\t0.0\n 1\t1.0e-3\n\t2.5\n 2\t2.0e-3\n\t5.0\n", encoding="utf-8")
    (project / "spice" / "op" / "demo.op.raw").write_text(
        "Title: demo\nPlotname: Operating Point\nFlags: real\nNo. Variables: 1\nNo. Points: 1\nVariables:\n\t0\tv(vout)\tvoltage\nValues:\n 0\t5.0\n", encoding="utf-8")
    # two more stage reports with the result figures the summary repeats
    (project / "reports" / "04_최종_보고서.html").write_text(
        "<html><head><title>최종 보고서: demo</title></head><body><h2>측정 파형</h2><figure><svg><title>시뮬레이션 파형 — 해석 tran</title></svg><figcaption>파이프라인 파형</figcaption></figure>"
        "<figure><svg><title>보드 3D</title></svg><figcaption>옮기지 않는 그림</figcaption></figure></body></html>", encoding="utf-8")
    (project / "reports" / "03_회로_보고서.html").write_text(
        "<html><head><title>회로 보고서: demo</title></head><body><h2>넷</h2><figure><svg><title>넷별 동박 길이</title></svg><figcaption>파이프라인 넷 차트</figcaption></figure>"
        "<figure><svg><title>demo: 보드 그림 (동박 포함)</title></svg><figcaption>파이프라인 보드 그림</figcaption></figure></body></html>", encoding="utf-8")
    (project / "report.html").write_text("<html><head><title>demo - design report</title><style>p{}</style></head><body><h1>demo</h1><h2>Pipeline stages</h2><p>body</p></body></html>", encoding="utf-8")
    return project


def run(*args: str) -> subprocess.CompletedProcess[str]:
    # a kicad-cli that cannot be started: the pictures are left out, and the script must say so instead of failing
    env = {**os.environ, "KICAD_CLI": str(ROOT / "no-such-kicad-cli"), "PYTHONUTF8": "1"}
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8", env=env)


class DeliverTest(unittest.TestCase):
    def test_evidence_package_resolves_after_extraction_without_changing_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(Path(tmp))
            contents = {
                "spice/tran/nested/sweep.raw": b"nested ngspice output",
                "spice/tran/nested/sweep.cir": b"companion deck",
                "spice/extra/results/raw.raw": b"directory reference",
                "sources/vendor/datasheet.pdf": b"archived source",
                "sources/vendor/archive.html": b"listed source document",
                "3d/demo.step": b"STEP export",
                "3d/demo.glb": b"GLB export",
                "3d/demo.png": b"listed PNG export",
                "evidence/measurement.txt": b"measurement",
                "sources/changed.pdf": b"changed source bytes",
                "private/notes.txt": b"private",
                "sources/.env": b"secret",
                "sources/tool.exe": b"not a source document",
                "sources/vendor/.ai-eda.lock": b"nested lock",
                ".ai-eda.lock": b"lock",
                "unrelated.txt": b"unrelated",
                "unlisted/subdir/file.txt": b"not selected by directory reference",
            }
            for relative, data in contents.items():
                path = project / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            outside = Path(tmp) / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            raw = str(project / "spice/tran/nested/sweep.raw")
            result = {"analyses": {"tran": {"result": {
                "raw_output_path": raw,
                "raw_output_hash": "sha256:" + hashlib.sha256(contents["spice/tran/nested/sweep.raw"]).hexdigest(),
                "deck_path": "spice/tran/nested/sweep.cir",
                "deck_hash": hashlib.sha256(contents["spice/tran/nested/sweep.cir"]).hexdigest(),
                "output_dir": "spice/extra",
            }}}}
            (project / "spice/results.json").write_text(json.dumps(result), encoding="utf-8")
            ir = json.loads((project / "ir.json").read_text(encoding="utf-8"))
            ir["validation"]["results"].append({"check_id": "spice", "evidence": [
                {"path": "spice/results.json", "content_hash": "sha256:" + deliver.file_sha256(project / "spice/results.json")},
                {"path": "sources/vendor/datasheet.pdf", "content_hash": "sha256:" + deliver.file_sha256(project / "sources/vendor/datasheet.pdf")},
                {"path": "sources/changed.pdf", "content_hash": "sha256:" + "0" * 64},
                {"path": "missing.raw"}, {"path": str(outside)},
                {"path": "../outside.txt"}, {"path": ".ai-eda.lock"},
                {"path": "private/notes.txt"}, {"path": "sources/.env"},
                {"path": "sources/vendor/.ai-eda.lock"}, {"path": "sources/tool.exe"},
                {"url": "https://example.invalid/datasheet.pdf"},
                {"path": "unlisted"},
            ], "artifact": "evidence/measurement.txt"})
            ir["artifacts"] = {"model": {"path": str(project / "3d/demo.step"),
                                         "content_hash": deliver.file_sha256(project / "3d/demo.step"),
                                         "files": ["3d/demo.glb"]}}
            (project / "ir.json").write_bytes((json.dumps(ir, indent=3) + "\r\n").encode("utf-8"))
            pipeline = {"state": {"outcomes": STAGES}, "ir_file_sha256": "sha256:" + deliver.file_sha256(project / "ir.json")}
            (project / "pipeline.json").write_text(json.dumps(pipeline), encoding="utf-8")
            originals = {p: p.read_bytes() for p in [project / "ir.json", project / "pipeline.json", *project.glob("*.kicad_*")]}
            done = run(str(project), "--lang", "en", "--no-pdf")
            self.assertEqual(done.returncode, 0, done.stderr)
            extracted = Path(tmp) / "recipient"
            with zipfile.ZipFile(project / "demo_deliverables.zip") as z:
                names = z.namelist()
                self.assertEqual(names, sorted(names))
                self.assertEqual(len(names), len(set(names)))
                z.extractall(extracted)
            index = json.loads((extracted / "demo/delivery-index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["pipeline_ir_association"]["outcome"], "match")
            self.assertEqual(set(index["files"]), set(names) - {"demo/delivery-index.json"})
            for path, info in index["files"].items():
                data = (extracted / path).read_bytes()
                self.assertEqual(info["sha256"], hashlib.sha256(data).hexdigest())
                self.assertEqual(info["size"], len(data))
            by_reference = {}
            for ref in index["references"]:
                by_reference.setdefault(ref["reference"], []).append(ref)
                if ref["outcome"] == "included":
                    self.assertTrue((extracted / ref["package_path"]).exists(), ref)
                    if ref["kind"] == "file":
                        self.assertEqual(ref["sha256"], deliver.file_sha256(extracted / ref["package_path"]))
            for ref, outcome in {
                raw: "included", "sources/vendor/datasheet.pdf": "included",
                str(project / "3d/demo.step"): "included", "3d/demo.glb": "included",
                "evidence/measurement.txt": "included", "missing.raw": "missing",
                "sources/changed.pdf": "included_changed", str(outside): "outside_project",
                "../outside.txt": "outside_project", ".ai-eda.lock": "excluded",
                "private/notes.txt": "excluded", "sources/.env": "excluded",
                "sources/tool.exe": "excluded", "sources/vendor/.ai-eda.lock": "excluded",
                "https://example.invalid/datasheet.pdf": "excluded", "unlisted": "excluded",
            }.items():
                self.assertTrue(all(r["outcome"] == outcome or (outcome == "included_changed" and r["outcome"] == "included"
                                                                and r.get("changed_since_record")) for r in by_reference[ref]), (ref, by_reference[ref]))
                if outcome not in ("included", "included_changed"):
                    self.assertTrue(all(r["package_path"] is None for r in by_reference[ref]))
            self.assertIn("demo/spice/tran/nested/sweep.cir", names)
            self.assertIn("demo/spice/extra/results/raw.raw", names)
            self.assertIn("demo/sources/vendor/archive.html", names)
            self.assertIn("demo/3d/demo.png", names)
            self.assertIn("demo/sources/changed.pdf", names)  # rewritten after recording: packaged, flagged in the index
            for omitted in ("unrelated.txt", "private/notes.txt", "sources/.env", "sources/tool.exe", "unlisted/subdir/file.txt"):
                self.assertNotIn("demo/" + omitted, names)
            self.assertFalse(any(n.endswith(".ai-eda.lock") for n in names))
            for p, data in originals.items():
                self.assertEqual(p.read_bytes(), data)
                self.assertEqual((extracted / "demo" / p.name).read_bytes(), data)
            # Stable index and ordering on a repeated packaging call; the existing ZIP uses file timestamps.
            second = deliver.make_zip(project, "demo", STAGES, [], "summary_report", target=Path(tmp) / "second.zip")
            with zipfile.ZipFile(second) as z:
                again = json.loads(z.read("demo/delivery-index.json"))
                self.assertEqual(again["references"], index["references"])
                self.assertEqual(z.namelist(), names)

    def test_duplicate_archive_paths_are_rejected_before_replacing_package(self) -> None:
        for reserved in ("README.txt", "delivery-index.json", "readme.txt"):
            with self.subTest(reserved=reserved), tempfile.TemporaryDirectory() as tmp:
                project = make_project(Path(tmp))
                (project / reserved).write_text("recorded evidence", encoding="utf-8")
                ir = json.loads((project / "ir.json").read_text(encoding="utf-8"))
                ir["artifacts"] = {"collision": {"path": reserved}}
                (project / "ir.json").write_text(json.dumps(ir), encoding="utf-8")
                target = project / "demo_deliverables.zip"
                target.write_bytes(b"previous package")
                with self.assertRaisesRegex(ValueError, "duplicate archive path"):
                    deliver.make_zip(project, "demo", STAGES, [], "summary_report")
                self.assertEqual(target.read_bytes(), b"previous package")

    def test_stale_pipeline_ir_hash_is_prominent_in_summary_index_and_readme(self) -> None:
        for lang in ("en", "ko"):
            with self.subTest(lang=lang), tempfile.TemporaryDirectory() as tmp:
                project = make_project(Path(tmp))
                record = {"state": {"outcomes": STAGES}, "ir_file_sha256": "sha256:" + "0" * 64}
                (project / "pipeline.json").write_text(json.dumps(record), encoding="utf-8")
                before = (project / "ir.json").read_bytes()
                done = run(str(project), "--no-pdf", "--lang", lang)
                self.assertEqual(done.returncode, 0, done.stderr)
                finding = "PIPELINE/IR HASH MISMATCH"
                summary = (project / "deliverables" / (deliver.TEXT[lang]["summary_stem"] + ".html")).read_text(encoding="utf-8")
                self.assertLess(summary.index(finding), summary.index('class="contents"'))
                self.assertIn(finding, done.stdout)
                with zipfile.ZipFile(project / "demo_deliverables.zip") as z:
                    index = json.loads(z.read("demo/delivery-index.json"))
                    self.assertIn(finding, z.read("demo/README.txt").decode("utf-8"))
                    self.assertEqual(z.read("demo/ir.json"), before)
                association = index["pipeline_ir_association"]
                self.assertEqual(association["outcome"], "mismatch")
                self.assertIn(finding, association["message"])
                self.assertEqual(association["sha256"], hashlib.sha256(before).hexdigest())

    def test_symlink_outside_project_is_not_packaged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(Path(tmp))
            outside = Path(tmp) / "outside.pdf"
            outside.write_bytes(b"external data")
            (project / "sources").mkdir()
            link = project / "sources/linked.pdf"
            try:
                link.symlink_to(outside)
            except OSError as e:
                self.skipTest(f"symlinks not available: {e}")
            package = deliver.make_zip(project, "demo", STAGES, [], "summary_report")
            with zipfile.ZipFile(package) as z:
                self.assertNotIn("demo/sources/linked.pdf", z.namelist())
                index = json.loads(z.read("demo/delivery-index.json"))
            ref = next(r for r in index["references"] if r["reference"] == "sources/linked.pdf")
            self.assertEqual(ref["outcome"], "outside_project")

    def test_korean_reports_and_zip_copy_the_pipelines_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(Path(tmp))
            done = run(str(project), "--no-pdf")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("stages that did not pass (copied from the pipeline): drc FAIL, release NOT_VERIFIED", done.stdout)
            self.assertIn("note: No pictures were drawn: kicad-cli was not found", done.stdout)
            summary = (project / "deliverables" / "주요결과_보고서.html").read_text(encoding="utf-8")
            detail = (project / "deliverables" / "상세_보고서.html").read_text(encoding="utf-8")
            # the first page says what is open; the newest result of a check wins; text from the pipeline is escaped
            self.assertIn('RELEASE: <span class="NOT_VERIFIED">NOT_VERIFIED</span>', summary)
            self.assertIn('<td class="PASS">PASS</td>', summary)
            self.assertNotIn("old run", summary)
            self.assertIn("output_voltage = 5 V", summary)
            self.assertIn('<td class="k">drc</td><td class="FAIL">FAIL</td>', summary)
            self.assertNotIn("<too small>", summary)  # the pipeline's text is escaped wherever it is printed
            self.assertIn("기록된 단계 6개 중 PASS가 아닌 단계 2개", summary)
            self.assertNotIn("모든 단계가 PASS", summary)
            self.assertIn("1행 (bom.csv의 MPN 칸이 NOT_VERIFIED인 행 1개)", summary)  # a count of cells, not a verdict on the part
            # simulation: the transient is drawn from its rawfile, the operating point is a table with the reason, the missing file is said
            # ... and the pipeline's own result figures are repeated unchanged: its waveform covers the one transient, so no second drawing
            self.assertIn("<figcaption>파이프라인 파형</figcaption>", summary)
            self.assertIn("<figcaption>파이프라인 넷 차트</figcaption>", summary)
            self.assertIn("파이프라인 보고서 04_최종_보고서.html의 그림을 그대로 옮긴 것입니다", summary)
            self.assertNotIn("옮기지 않는 그림", summary)
            # the PCB section shows the pipeline's board figure in place of the two KiCad sides
            self.assertIn("<figcaption>파이프라인 보드 그림</figcaption>", summary)
            self.assertNotIn("보드 그림 없음", summary)
            self.assertEqual(summary.count("<polyline"), 0)
            self.assertIn("해석 op는 동작점(한 점) 해석이라 파형이 없습니다", summary)
            self.assertIn("해석 ac: 결과 파일이 없어 파형을 그리지 못했습니다", summary)
            # nets: 5 mm + 6 mm of track on two layers and one via; a two-pin net without a segment is counted, not hidden
            self.assertIn('<td class="k">VOUT</td><td>signal</td><td>Default</td><td>R1.2, R2.1</td><td class="k">2</td><td class="k">11.00</td><td class="k">1</td><td>B.Cu, F.Cu</td>', summary)
            self.assertIn("넷 2개: 배선된 넷 1개, 핀이 둘 이상인데 배선 조각이 없는 넷 1개", summary)
            # a cover, a contents page, then the numbered sections
            self.assertLess(summary.index('class="cover"'), summary.index('class="contents"'))
            self.assertLess(summary.index('class="contents"'), summary.index('<h2 id="s1">1. 한눈에 보기</h2>'))
            self.assertIn('<h2 class="page" id="s7">7. 통과하지 못한 단계 (실패·미검증)</h2>', summary)
            # the summary keeps stage messages short; the detailed report carries them whole, then the bound report
            self.assertIn("clearance &lt;too small&gt; &amp; more", detail)
            self.assertIn("동작 원리", detail)
            self.assertIn('href="#c4-1"', detail)
            self.assertIn("<figcaption>파이프라인 넷 차트</figcaption>", detail)  # the same figures stay in the detailed report  # chapters 1-3 are this script's (stages, requirements, nets); the first bound report is the fourth
            self.assertIn("3. 넷 분석 (전체)", detail)
            self.assertIn("다음 파이프라인 보고서가 없어 묶지 못했습니다", detail)  # one of the four Korean stage reports is not in the folder: named, not passed over
            self.assertIn("묶지 못했습니다(먼저 `ai-eda stage-reports &lt;ir.json&gt;` 실행): 02_부품선정_보고서.html", detail)
            with zipfile.ZipFile(project / "demo_deliverables.zip") as z:
                names = set(z.namelist())
                readme = z.read("demo/README.txt").decode("utf-8")
            for wanted in ("demo/demo.kicad_pro", "demo/demo.kicad_sch", "demo/demo.kicad_pcb", "demo/gerber/demo.drl", "demo/bom.csv", "demo/cpl.csv",
                           "demo/reports/01_이론_보고서.html", "demo/deliverables/주요결과_보고서.html", "demo/deliverables/상세_보고서.html", "demo/ir.json"):
                self.assertIn(wanted, names)
            self.assertIn("drc                      FAIL", readme)
            self.assertIn("nothing here is a release approval", readme)

    def test_english_reports_replace_the_korean_ones(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(Path(tmp))
            self.assertEqual(run(str(project), "--no-pdf").returncode, 0)
            done = run(str(project / "ir.json"), "--no-pdf", "--lang", "en")
            self.assertEqual(done.returncode, 0, done.stderr)
            out = project / "deliverables"
            self.assertEqual(sorted(p.name for p in out.glob("*.html")), ["detailed_report.html", "summary_report.html"])  # the Korean pair of the first call is gone
            summary = (out / "summary_report.html").read_text(encoding="utf-8")
            self.assertIn("1. At a glance", summary)
            self.assertIn("5. Net analysis", summary)
            # the English report does not repeat the Korean figures: it draws the waveform and the copper lengths itself
            self.assertEqual(summary.count("<polyline"), 1)
            self.assertIn("spice/tran/demo.tran.raw (3 point(s))", summary)
            self.assertEqual(summary.count('<rect class="bar"'), 1)
            self.assertNotIn("파이프라인 파형", summary)
            self.assertNotIn("파이프라인 보드 그림", summary)
            self.assertIn("No board picture", summary)  # no kicad-cli in this test, and the Korean figure is not used in English
            self.assertIn("7. Stages that did not pass (failed or not verified)", summary)
            self.assertIn("Pipeline stages", (out / "detailed_report.html").read_text(encoding="utf-8"))

    def test_a_project_without_a_board_or_without_an_ir_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(Path(tmp), board=False)
            done = run(str(project), "--no-pdf")
            self.assertEqual(done.returncode, 1)
            self.assertIn("no demo.kicad_pcb yet", done.stderr)
            self.assertFalse((project / "demo_deliverables.zip").exists())
            empty = Path(tmp) / "empty"
            empty.mkdir()
            self.assertEqual(run(str(empty)).returncode, 2)

    def test_a_project_without_a_run_record_is_refused_and_never_called_all_pass(self) -> None:
        for content in (None, "not json", "{}", '{"state": null}', '{"state": {"outcomes": []}}', "[1, 2]"):
            with tempfile.TemporaryDirectory() as tmp:
                project = make_project(Path(tmp))
                if content is None:
                    (project / "pipeline.json").unlink()
                else:
                    (project / "pipeline.json").write_text(content, encoding="utf-8")
                done = run(str(project), "--no-pdf")
                self.assertEqual(done.returncode, 1, content)
                self.assertIn("pipeline.json records no stage outcome", done.stderr)
                self.assertFalse((project / "deliverables").exists(), content)
                self.assertFalse((project / "demo_deliverables.zip").exists(), content)

    def test_a_run_that_stopped_is_said_on_the_cover_in_the_last_section_and_in_the_readme(self) -> None:
        cases = (
            ({"state": {"outcomes": STAGES[:4]}, "aborted": "RuntimeError", "aborted_stage": "drc"}, "aborted in stage drc (RuntimeError)"),
            ({"state": {"outcomes": STAGES[:2], "blocked": True}}, "blocked at stage schematic on a required question"),
            ({"state": {"outcomes": STAGES[:4]}}, "stopped after stage pcb"),
        )
        for record, sentence in cases:
            with tempfile.TemporaryDirectory() as tmp:
                project = make_project(Path(tmp))
                (project / "pipeline.json").write_text(json.dumps(record), encoding="utf-8")
                done = run(str(project), "--no-pdf", "--lang", "en")
                self.assertEqual(done.returncode, 0, done.stderr)
                summary = (project / "deliverables" / "summary_report.html").read_text(encoding="utf-8")
                self.assertGreaterEqual(summary.count(f"The run did not finish</b>: {sentence}"), 3, sentence)  # cover, section 1, last section
                self.assertNotIn("Every stage is PASS", summary)
                with zipfile.ZipFile(project / "demo_deliverables.zip") as z:
                    self.assertIn(f"THE RUN DID NOT FINISH: {sentence}", z.read("demo/README.txt").decode("utf-8"))
                self.assertIn("note: The run did not finish", done.stdout)

    def test_pictures_of_an_earlier_call_do_not_ship_when_none_can_be_drawn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(Path(tmp))
            old = project / "deliverables" / "pictures"
            old.mkdir(parents=True)
            (old / "board_top.svg").write_text("<svg/>", encoding="utf-8")
            self.assertEqual(run(str(project), "--no-pdf").returncode, 0)
            with zipfile.ZipFile(project / "demo_deliverables.zip") as z:
                names = z.namelist()
                readme = z.read("demo/README.txt").decode("utf-8")
            self.assertFalse([n for n in names if n.endswith(".svg")])
            self.assertIn("read deliverables/주요결과_보고서.html, its last section", readme)  # no PDF was written: the README names the file that is there
            self.assertIn("absolute folder paths", readme)


if __name__ == "__main__":
    unittest.main()
