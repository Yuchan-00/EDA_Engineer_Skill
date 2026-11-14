# Copyright (c) 2026 Yuchan (github.com/Yuchan-00). MIT License with Commons Clause (no selling) - see LICENSE.
"""Deliverables of a finished ai-eda project: two PDF reports and one zip, in Korean or English.

    python deliver.py <project folder or its ir.json> [--lang ko|en]

Reads what the pipeline wrote (ir.json, pipeline.json, bom.csv, reports/, report.html, the KiCad files) and writes,
in <project>/deliverables/:

* the summary report (주요결과_보고서 / summary_report: .html, .pdf) - the main results on a few pages: an overview,
  the parts list, the schematic, the simulation results, the PCB, and what this run did not verify.
* the detailed report (상세_보고서 / detailed_report: .html, .pdf) - every stage with its full message, the
  requirements with their sources, then the pipeline's own reports bound with a table of contents: the four Korean
  stage reports (--lang ko) or the English design report `ai-eda report` writes (--lang en).
* <name>_deliverables.zip - the project, reports, referenced evidence, sources, 3D exports, README and delivery-index.json.

Rules this script keeps (the skill's): it reads and copies - every status, number and message is the pipeline's
own, taken from ir.json / pipeline.json and never re-judged; a stage that is NOT_VERIFIED or FAIL is printed as
such on the first page and in the zip's README. It runs two local programs with list arguments (kicad-cli to
draw, a Chromium-family browser to print - its throwaway profile is made inside deliverables/ and removed), opens no
network connection, and writes only inside the project folder. The zip carries the pipeline's own records, which hold
the absolute folder paths of this computer; the README says so.
Without kicad-cli the pictures are left out; without a browser the .html files are written and the PDFs are not.

Exit codes: 0 written (the README says what did not pass); 1 the project has no board yet, or pipeline.json records no
stage outcome; 2 usage error, or a file could not be replaced (open in another program). Python 3.8 or newer, standard
library only.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import glob
import hashlib
import html
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PureWindowsPath

OUT_DIR = "deliverables"
STAGE_REPORTS = ("01_이론_보고서", "02_부품선정_보고서", "03_회로_보고서", "04_최종_보고서")
BROWSER_NAMES = ("msedge", "google-chrome", "google-chrome-stable", "chrome", "chromium", "chromium-browser")
BROWSER_SUFFIXES = ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe")
PRINT_FLAGS = (
    "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--disable-extensions", "--disable-background-networking",
    "--disable-component-update", "--disable-sync", "--disable-breakpad", "--password-store=basic", "--use-mock-keychain",
    "--no-pdf-header-footer", "--no-proxy-server", "--host-resolver-rules=MAP * ~NOTFOUND",
)
OK_STATUSES = ("PASS", "NOT_APPLICABLE")

#: every sentence the two reports print, per language (the pipeline's own messages are copied as they are: English)
TEXT: dict[str, dict[str, str]] = {
    "ko": {
        "summary_stem": "주요결과_보고서", "detail_stem": "상세_보고서", "summary_title": "주요 결과물 보고서", "detail_title": "상세 보고서",
        "copied": "이 보고서는 파이프라인이 기록한 값(ir.json, pipeline.json)을 옮겨 적은 것이며 새로 판정하지 않습니다. 단계별 메시지 전문과 검사별 내용은 상세 보고서에 있습니다.",
        "created": "생성", "none": "기록 없음", "release_note": "기록된 단계 {k}개 중 PASS가 아닌 단계 {n}개는 이 실행이 검증하지 않았거나 실패한 것입니다(마지막 절).",
        "h_overview": "한눈에 보기", "h_bom": "부품 목록 (BOM)", "h_sch": "회로도", "h_sim": "시뮬레이션 결과", "h_pcb": "PCB", "h_open": "통과하지 못한 단계 (실패·미검증)",
        "item": "항목", "content": "내용", "design": "설계", "parts": "부품", "parts_n": "{n}행 (bom.csv의 MPN 칸이 NOT_VERIFIED인 행 {u}개)", "sim": "시뮬레이션", "sim_n": "기대값 {n}개 중 PASS {p}개",
        "requirements": "요구사항", "value": "값", "stage": "단계", "status": "상태", "message": "메시지", "source": "출처", "stages": "단계 상태",
        "bom_note": "bom.csv {n}행. MPN 칸이 NOT_VERIFIED인 행 {u}개, Manufacturer 칸이 NOT_VERIFIED인 행 {m}개(파이프라인이 그 부품의 제조사·부품 번호를 확인하지 않았다는 표시).",
        "no_bom": "bom.csv가 없습니다(제조 출력 단계에 도달하지 못함).", "no_sch": "회로도 그림 없음: kicad-cli를 찾지 못했거나 회로도 파일이 없습니다. KiCad로 .kicad_sch 파일을 여십시오.",
        "drawn": "KiCad가 그린", "spice_stage": "SPICE 단계", "exp": "기대값", "what": "분석: 벡터 (축약)", "nominal": "기준값", "measured": "측정값", "verdict": "판정", "verifies": "검증하는 요구사항",
        "no_exp": "시뮬레이션 기대값이 없습니다.", "other_checks": "계산·부품 적합성 검사", "check": "검사", "see_detail": "파형, 이론값 대 시뮬레이션 표, 검사별 내용은 상세 보고서에 있습니다.",
        "layers": "층", "placed": "부품 배치 수", "tracks": "트랙 / 비아", "pcb_compile": "PCB 컴파일", "mfg": "제조 출력", "gerbers": "Gerber·드릴 파일", "nofile": "없음",
        "top": "앞면: F.Cu, F.Silkscreen, 외곽선", "bottom": "뒷면: B.Cu, B.Silkscreen, 외곽선 (뒤집어 본 그림)", "no_board_pic": "보드 그림 없음: kicad-cli를 찾지 못했거나 보드 파일이 없습니다.",
        "all_pass": "모든 단계가 PASS 또는 NOT_APPLICABLE입니다.", "latest": "검사별 최신 결과", "reason": "이유 (요약)",
        "detail_intro": "단계별 결과와 요구사항 전문, 그리고 파이프라인이 쓴 보고서 {n}개를 한 문서로 묶었습니다. 파이프라인 보고서의 내용은 고치지 않았습니다.", "toc": "목차",
        "ch_stages": "단계별 결과 (메시지 전문)", "ch_reqs": "요구사항과 출처", "missing_reports": "다음 파이프라인 보고서가 없어 묶지 못했습니다(먼저 `ai-eda stage-reports <ir.json>` 실행):",
        "h_net": "넷 분석", "net": "넷", "kind": "종류", "net_class": "클래스", "pins": "연결된 핀", "segments": "배선 조각", "length": "동박 길이 (mm)", "vias": "비아", "on_layers": "층",
        "net_note": "넷 {n}개: 배선된 넷 {r}개, 핀이 둘 이상인데 배선 조각이 없는 넷 {u}개. 길이는 IR에 기록된 트랙 조각의 길이를 더한 값입니다(판정 아님).",
        "net_more": "긴 순서로 {k}개만 실었습니다. 전체 {n}개는 상세 보고서의 넷 분석 장에 있습니다.", "ch_nets": "넷 분석 (전체)",
        "wave": "시뮬레이션 파형", "wave_cap": "해석 {a} — ngspice 결과 파일 {f} ({n}점{s})에서 그린 것. 그림은 값을 다시 계산하지 않습니다.", "wave_stride": ", {k}점마다 1점 표시",
        "no_raw": "해석 {a}: 결과 파일이 없어 파형을 그리지 못했습니다(시뮬레이션이 실행되지 않았거나 엔진이 없음).",
        "op_note": "해석 {a}는 동작점(한 점) 해석이라 파형이 없습니다. 결과 파일 {f}의 값:", "vector": "벡터", "x_time": "시간 (s)", "x_freq": "주파수 (Hz)", "x_sweep": "스윕",
        "borrowed": "아래 그림은 파이프라인 보고서 {f}의 그림을 그대로 옮긴 것입니다(상세 보고서에도 같은 그림이 있습니다).", "net_chart": "넷별 동박 길이",
        "net_chart_cap": "넷별 동박 길이 (mm): IR에 기록된 트랙 조각 길이의 합, 긴 순서로 {k}개.",
        "stopped": "실행이 끝까지 가지 않았습니다", "left_out": "설계에서 뺀 요구사항 (사용자 결정)", "older": "마지막 실행보다 오래된 보고서(다시 만들지 않음)",
        "c_project": "프로젝트", "c_created": "설계 생성일", "c_issued": "보고서 작성일", "c_tool": "생성 도구", "c_verdict": "판정 (RELEASE)",
        "c_foot": "이 문서는 ai-eda 파이프라인의 기록(ir.json, pipeline.json)에서 자동으로 만들어졌습니다. 상태와 수치는 파이프라인이 기록한 그대로이며, 이 문서가 새로 판정한 것은 없습니다.",
    },
    "en": {
        "summary_stem": "summary_report", "detail_stem": "detailed_report", "summary_title": "Summary report", "detail_title": "Detailed report",
        "copied": "This report copies what the pipeline recorded (ir.json, pipeline.json) and judges nothing anew. Full stage messages and per-check details are in the detailed report.",
        "created": "created", "none": "no record", "release_note": "Of {k} recorded stage(s), {n} are not PASS: not verified by this run, or failed (last section).",
        "h_overview": "At a glance", "h_bom": "Parts list (BOM)", "h_sch": "Schematic", "h_sim": "Simulation results", "h_pcb": "PCB", "h_open": "Stages that did not pass (failed or not verified)",
        "item": "Item", "content": "Content", "design": "Design", "parts": "Parts", "parts_n": "{n} row(s) ({u} with MPN = NOT_VERIFIED in bom.csv)", "sim": "Simulation", "sim_n": "{p} of {n} expectation(s) PASS",
        "requirements": "Requirements", "value": "Value", "stage": "Stage", "status": "Status", "message": "Message", "source": "Source", "stages": "Stage statuses",
        "bom_note": "{n} row(s) in bom.csv. MPN is NOT_VERIFIED in {u} row(s), Manufacturer in {m} (the pipeline's mark that it did not verify that part's maker and part number).",
        "no_bom": "There is no bom.csv (the manufacturing-output stage was not reached).", "no_sch": "No schematic picture: kicad-cli was not found or the schematic file is missing. Open the .kicad_sch file in KiCad.",
        "drawn": "drawn by KiCad from", "spice_stage": "SPICE stage", "exp": "Expectation", "what": "Analysis: vector (reduction)", "nominal": "Nominal", "measured": "Measured", "verdict": "Verdict", "verifies": "Verifies",
        "no_exp": "There are no simulation expectations.", "other_checks": "Calculation and part-fit checks", "check": "Check", "see_detail": "Waveforms, the theory-versus-simulation table and per-check details are in the detailed report.",
        "layers": "Layers", "placed": "Parts placed", "tracks": "Tracks / vias", "pcb_compile": "PCB compile", "mfg": "Manufacturing outputs", "gerbers": "Gerber and drill files", "nofile": "none",
        "top": "Front: F.Cu, F.Silkscreen, outline", "bottom": "Back: B.Cu, B.Silkscreen, outline (mirrored view)", "no_board_pic": "No board picture: kicad-cli was not found or the board file is missing.",
        "all_pass": "Every stage is PASS or NOT_APPLICABLE.", "latest": "Latest result per check", "reason": "Reason (short)",
        "detail_intro": "Full stage results and requirements, followed by {n} report(s) the pipeline wrote, bound into one document. The pipeline's reports are not edited.", "toc": "Contents",
        "ch_stages": "Stage results (full messages)", "ch_reqs": "Requirements and their sources", "missing_reports": "These pipeline reports are missing and were not bound (run `ai-eda report <ir.json>` first):",
        "h_net": "Net analysis", "net": "Net", "kind": "Kind", "net_class": "Class", "pins": "Connected pins", "segments": "Track segments", "length": "Copper length (mm)", "vias": "Vias", "on_layers": "Layers",
        "net_note": "{n} net(s): {r} routed, {u} with two or more pins and no track segment. The length is the sum of the track segments recorded in the IR (not a verdict).",
        "net_more": "Only the {k} longest are shown. All {n} are in the net analysis chapter of the detailed report.", "ch_nets": "Net analysis (complete)",
        "wave": "Simulation waveform", "wave_cap": "Analysis {a} — drawn from the ngspice result file {f} ({n} point(s){s}). The picture recomputes nothing.", "wave_stride": ", every {k}th point drawn",
        "no_raw": "Analysis {a}: no result file, so no waveform could be drawn (the simulation did not run or the engine is missing).",
        "op_note": "Analysis {a} is an operating point (one point), so it has no waveform. Values in the result file {f}:", "vector": "Vector", "x_time": "Time (s)", "x_freq": "Frequency (Hz)", "x_sweep": "Sweep",
        "borrowed": "The figures below are copied unchanged from the pipeline's report {f} (the detailed report holds the same figures).", "net_chart": "Copper length per net",
        "net_chart_cap": "Copper length per net (mm): the sum of the track segments recorded in the IR, the {k} longest.",
        "stopped": "The run did not finish", "left_out": "Left out of the design (the user's decision)", "older": "Report older than the last run (not rewritten)",
        "c_project": "Project", "c_created": "Design created", "c_issued": "Report issued", "c_tool": "Generated by", "c_verdict": "Verdict (RELEASE)",
        "c_foot": "This document was generated from the records of the ai-eda pipeline (ir.json, pipeline.json). Every status and number is the pipeline's own; this document judges nothing anew.",
    },
}
STYLE = """
@page { size: A4; margin: 16mm 15mm 18mm; @bottom-center { content: counter(page); font-size: 8pt; color: #666; } }
@page :first { @bottom-center { content: none; } }
body { margin: 0 auto; max-width: 180mm; color: #111; font-family: "Noto Sans CJK KR", "Noto Sans KR", "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
  font-size: 10pt; line-height: 1.5; word-break: keep-all; overflow-wrap: anywhere; }
h1 { font-size: 18pt; margin: 0 0 6pt; } h2 { font-size: 13.5pt; margin: 16pt 0 6pt; padding-bottom: 2pt; border-bottom: 1px solid #ccc; break-after: avoid; }
h3 { font-size: 11pt; margin: 10pt 0 4pt; break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0; font-size: 8.5pt; } th, td { border: 1px solid #bbb; padding: 2pt 5pt; text-align: left; vertical-align: top; }
th { background: #eee; white-space: nowrap; } tr { break-inside: avoid; }
td.k, td.PASS, td.FAIL, td.NOT_VERIFIED, td.UNRESOLVED, td.USER_INPUT_REQUIRED, td.NOT_APPLICABLE { white-space: nowrap; }
.PASS { color: #0a6b2d; font-weight: 600; } .FAIL { color: #b00020; font-weight: 700; } .NOT_VERIFIED, .UNRESOLVED, .USER_INPUT_REQUIRED { color: #8a5a00; font-weight: 600; }
:root { color-scheme: light; background: #fff; }
.d-note { background: #f6f3e6; border-left: 3px solid #c9a200; padding: 4pt 8pt; margin: 6pt 0; } .small { font-size: 8.5pt; color: #444; }
.chips { display: grid; grid-template-columns: repeat(3, 1fr); gap: 3pt 10pt; margin: 6pt 0; font-size: 9pt; }
.chips div { display: flex; justify-content: space-between; border-bottom: 1px dotted #bbb; padding: 1pt 0; }
figure { margin: 8pt 0; text-align: center; break-inside: avoid; } figure svg { max-width: 100%; height: auto; max-height: 225mm; border: 1px solid #ddd; background: #fff; }
figcaption { font-size: 8.5pt; color: #444; } .page { break-before: page; } figure.board svg { max-height: 88mm; } .keep { break-inside: avoid; }
.bound { break-before: page; }
.cover { min-height: 245mm; display: flex; flex-direction: column; justify-content: space-between; break-after: page; }
.cover .kind { margin-top: 38mm; font-size: 12pt; letter-spacing: 3pt; color: #555; }
.cover h1 { font-size: 30pt; line-height: 1.2; margin: 5mm 0 3mm; } .cover .sub { font-size: 14pt; color: #333; } .cover .rule { border-top: 3px solid #111; width: 42mm; margin: 9mm 0; }
.cover table { width: 125mm; font-size: 10pt; } .cover td { border: 0; border-bottom: 1px solid #ccc; padding: 4pt 5pt; } .cover td.k { color: #555; width: 38mm; }
.cover .foot { font-size: 8.5pt; color: #555; }
.contents { break-after: page; } .contents h2 { font-size: 16pt; border-bottom: 2px solid #111; }
.contents ol { list-style: none; padding-left: 0; font-size: 11pt; line-height: 2.1; } .contents ol ol { padding-left: 16pt; font-size: 9.5pt; line-height: 1.6; color: #333; }
.contents a { color: inherit; text-decoration: none; }
"""


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def one_line(text: object, limit: int = 0) -> str:
    flat = " ".join(str(text or "").split())
    return flat if not limit or len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def load_json(path: Path) -> dict:
    """The JSON object in ``path``; an empty dict when the file is missing, unreadable or not an object."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def run(cmd: list[str], timeout: float = 300.0) -> tuple[int, str]:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return done.returncode, done.stdout + done.stderr


def find_program(env: str, names: tuple[str, ...], patterns: list[str]) -> str | None:
    """A program by environment variable, then PATH, then install folders (the newest version folder).

    Only absolute PATH entries are searched: on Windows a bare name is otherwise looked up in the current folder first,
    so a file named like the browser lying in the project folder would be run.
    """
    if os.environ.get(env):
        return os.environ[env]
    absolute = os.pathsep.join(d for d in os.environ.get("PATH", "").split(os.pathsep) if d and os.path.isabs(d))
    for n in names:
        found = shutil.which(n, path=absolute)
        if found and os.path.isabs(found):
            return found

    def version(hit: str) -> tuple[tuple[int, ...], str]:  # ...\KiCad\10.0\bin\kicad-cli.exe -> (10, 0): 10.0 is newer than 9.0
        return tuple(int(x) for x in re.findall(r"\d+", Path(hit).parent.parent.name)), hit

    hits = sorted((h for pattern in patterns if pattern for h in glob.glob(pattern)), key=version)
    return hits[-1] if hits else None


def find_kicad_cli() -> str | None:
    local = os.environ.get("LOCALAPPDATA", "")
    return find_program("KICAD_CLI", ("kicad-cli",), [
        r"C:\Program Files\KiCad\*\bin\kicad-cli.exe", os.path.join(local, "Programs", "KiCad", "*", "bin", "kicad-cli.exe") if local else "",
        "/usr/bin/kicad-cli", "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
    ])


def find_browser() -> str | None:
    roots = [os.environ.get(k, "") for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    patterns = [os.path.join(r, s) for r in roots if r for s in BROWSER_SUFFIXES]
    patterns += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    return find_program("AI_EDA_BROWSER", BROWSER_NAMES, patterns)


def print_pdf(page: Path, pdf: Path, browser: str | None) -> str | None:
    """Print ``page`` to ``pdf`` with a headless browser; the reason as text when it could not."""
    if browser is None:
        return "no Chromium-family browser found (set AI_EDA_BROWSER)"
    pdf.unlink(missing_ok=True)
    profile = tempfile.mkdtemp(prefix=".eda-deliver-profile-", dir=str(pdf.parent))  # inside the project: this script writes nowhere else
    try:
        code, said = run([browser, *PRINT_FLAGS, f"--user-data-dir={profile}", f"--print-to-pdf={pdf}", page.resolve().as_uri()], 180.0)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if not pdf.exists() or pdf.stat().st_size == 0:
        pdf.unlink(missing_ok=True)
        return f"the browser wrote no PDF (exit {code}): {one_line(said, 200)}"
    return None


def inline_svg(path: Path) -> str | None:
    """The ``<svg>`` element of a KiCad export, ready to sit in an HTML page (its XML prolog and doctype removed)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    start = text.find("<svg")
    return text[start:] if start >= 0 else None


def circuit_box(sch: Path, margin: float = 12.0) -> tuple[float, float, float, float] | None:
    """``(x, y, width, height)`` in mm of what a schematic sheet draws: every placed symbol, wire, junction and label, plus a margin.

    The coordinates are read from the .kicad_sch text (``(at x y`` and ``(xy x y)``) after the ``lib_symbols`` block,
    whose numbers are symbol-local, is cut out. ``None`` when nothing is placed or the file cannot be read.
    """
    try:
        text = sch.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    start = text.find("(lib_symbols")
    if start >= 0:
        depth, i = 0, start
        while i < len(text):
            depth += text[i] == "("
            depth -= text[i] == ")"
            i += 1
            if depth == 0:
                break
        text = text[:start] + text[i:]
    points = [(float(x), float(y)) for x, y in re.findall(r"\((?:xy|at)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)", text)]
    if not points:
        return None
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs) - margin, min(ys) - margin, max(xs) - min(xs) + 2 * margin, max(ys) - min(ys) + 2 * margin


def fill_width(svg: str) -> str:
    """``svg`` without its fixed size in mm, so the page scales it to the column (a 40 mm board is otherwise drawn 40 mm wide)."""
    return re.sub(r'(<svg\b[^>]*?)\swidth="[^"]*"\s+height="[^"]*"', r'\1 width="100%"', svg, count=1, flags=re.S)


def crop_svg(svg: str, box: tuple[float, float, float, float] | None) -> str:
    """``svg`` (a KiCad sheet export, user units = mm) showing only ``box``, scaled to the page width; unchanged without a box or a viewBox."""
    m = re.search(r'width="[^"]*"\s+height="[^"]*"\s+viewBox="([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)"', svg)
    if box is None or m is None:
        return svg
    x0, y0, w0, h0 = (float(g) for g in m.groups())
    x, y = max(box[0], x0), max(box[1], y0)
    w, h = min(box[0] + box[2], x0 + w0) - x, min(box[1] + box[3], y0 + h0) - y
    if w <= 0 or h <= 0:
        return svg
    return svg[: m.start()] + f'width="100%" viewBox="{x:.2f} {y:.2f} {w:.2f} {h:.2f}"' + svg[m.end():]


def draw(project: Path, name: str, out: Path) -> dict[str, Path]:
    """SVG pictures of the schematic sheets and of the board (KiCad's own renderer); empty without kicad-cli or the files."""
    cli, pictures = find_kicad_cli(), {}
    sch, pcb = project / f"{name}.kicad_sch", project / f"{name}.kicad_pcb"
    folder = out / "pictures"
    for stale in folder.glob("*.svg"):  # pictures of an earlier call are not this run's, with or without kicad-cli today
        stale.unlink()
    if cli is None:
        return pictures
    folder.mkdir(parents=True, exist_ok=True)
    if sch.exists():
        run([cli, "sch", "export", "svg", "--exclude-drawing-sheet", "--no-background-color", "-o", str(folder), str(sch)])
        for i, sheet in enumerate(sorted(folder.glob("*.svg"))):
            pictures[f"schematic{i or ''}"] = sheet
    if pcb.exists():
        for key, layers in (("board_top", "F.Cu,F.Silkscreen,Edge.Cuts"), ("board_bottom", "B.Cu,B.Silkscreen,Edge.Cuts")):
            target = folder / f"{key}.svg"
            run([cli, "pcb", "export", "svg", "-o", str(target), "--layers", layers, "--page-size-mode", "2", "--exclude-drawing-sheet", *(["--mirror"] if key == "board_bottom" else []), str(pcb)])
            if target.exists():
                pictures[key] = target
    return pictures


def read_raw(path: Path) -> dict | None:
    """An ngspice rawfile (ASCII or binary) as ``{"plot", "names", "rows"}``; ``None`` when it is not one.

    ``rows`` holds one list of floats per point, in the order of ``names`` (lower case, as ngspice writes them). A
    complex analysis (ac) gives the magnitude of every vector and the real part of the sweep variable.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return None
    marker = next((m for m in (b"Values:", b"Binary:") if m in data), None)
    if marker is None:
        return None
    cut = data.index(marker)
    head = data[:cut].decode("utf-8", "replace")

    def field(name: str) -> str:
        m = re.search(rf"^{re.escape(name)}:[ \t]*(.*)$", head, re.M)
        return m.group(1).strip() if m else ""

    try:
        nvars, npoints = int(field("No. Variables")), int(field("No. Points"))
    except ValueError:
        return None
    is_complex = "complex" in field("Flags").lower()
    names = [m.group(1).lower() for m in re.finditer(r"^[ \t]+\d+[ \t]+(\S+)[ \t]+\S+", head, re.M)]
    if len(names) != nvars or nvars < 1 or npoints < 1:
        return None
    body = data[cut + len(marker):]
    width = 2 if is_complex else 1
    try:
        if marker == b"Binary:":
            flat = struct.unpack(f"<{npoints * nvars * width}d", body.lstrip(b"\r\n")[: npoints * nvars * width * 8])
            numbers = [complex(flat[i], flat[i + 1]) if is_complex else flat[i] for i in range(0, len(flat), width)]
        else:
            tokens = body.decode("utf-8", "replace").split()
            numbers = []
            for point in range(npoints):
                chunk = tokens[point * (nvars + 1) + 1: (point + 1) * (nvars + 1)]
                numbers += [complex(*(float(x) for x in tok.split(","))) if is_complex else float(tok) for tok in chunk]
    except (ValueError, TypeError, struct.error):
        return None
    if len(numbers) != npoints * nvars:
        return None
    rows = [[(numbers[r * nvars + c].real if c == 0 else abs(numbers[r * nvars + c])) if is_complex else numbers[r * nvars + c] for c in range(nvars)] for r in range(npoints)]
    return {"plot": field("Plotname"), "names": names, "rows": rows, "complex": is_complex}


def raw_name(vector: str, names: list[str]) -> str | None:
    """The rawfile vector an expectation's ``v(NET)`` / ``i(SOURCE)`` names, or ``None`` (a phase or part vector is not drawn)."""
    v = vector.strip().lower()
    m = re.fullmatch(r"i\((.+)\)", v)
    candidates = [v] + ([f"i(v{m.group(1)})", f"v{m.group(1)}#branch", f"{m.group(1)}#branch"] if m else [])
    return next((c for c in candidates if c in names), None)


WAVE_COLORS = ("#2a78d6", "#eb6834", "#1baf7a", "#9b59b6", "#c9a200", "#555555")


def waveform_svg(title: str, x_label: str, xs: list[float], series: list[tuple[str, list[float]]], log_x: bool) -> str:
    """A line chart of ``series`` over ``xs`` as an SVG element (axes with five ticks each, a legend); no smoothing, no fitting."""
    w, h, left, right, top, bottom = 680.0, 300.0, 64.0, 16.0, 44.0, 40.0
    if log_x:
        keep = [i for i, x in enumerate(xs) if x > 0]
        xs, series = [math.log10(xs[i]) for i in keep], [(n, [ys[i] for i in keep]) for n, ys in series]
    x0, x1 = min(xs), max(xs)
    values = [y for _, ys in series for y in ys if math.isfinite(y)]
    y0, y1 = (min(values), max(values)) if values else (0.0, 1.0)
    if y1 == y0:
        y0, y1 = y0 - (abs(y0) or 1.0) * 0.05, y1 + (abs(y1) or 1.0) * 0.05
    pad = (y1 - y0) * 0.05
    y0, y1 = y0 - pad, y1 + pad
    sx = lambda x: left + (x - x0) / ((x1 - x0) or 1.0) * (w - left - right)  # noqa: E731
    sy = lambda y: h - bottom - (y - y0) / (y1 - y0) * (h - top - bottom)  # noqa: E731
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 {w:g} {h:g}" role="img" font-size="10" fill="#222"><title>{esc(title)}</title>',
           f'<rect x="{left}" y="{top}" width="{w - left - right}" height="{h - top - bottom}" fill="#fff" stroke="#999"/>']
    for k in range(5):
        yv, xv = y0 + (y1 - y0) * k / 4, x0 + (x1 - x0) * k / 4
        out.append(f'<line x1="{left}" x2="{w - right}" y1="{sy(yv):.1f}" y2="{sy(yv):.1f}" stroke="#e3e3e3"/><text x="{left - 5}" y="{sy(yv) + 3:.1f}" text-anchor="end">{yv:.4g}</text>')
        out.append(f'<text x="{sx(xv):.1f}" y="{h - bottom + 14}" text-anchor="middle">{(10 ** xv if log_x else xv):.4g}</text>')
    out.append(f'<text x="{(left + w - right) / 2:.1f}" y="{h - 6}" text-anchor="middle">{esc(x_label)}</text><text x="{left}" y="16" font-size="12" font-weight="600">{esc(title)}</text>')
    for i, (name, ys) in enumerate(series):
        color = WAVE_COLORS[i % len(WAVE_COLORS)]
        points = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in zip(xs, ys) if math.isfinite(y))
        out.append(f'<polyline fill="none" stroke="{color}" stroke-width="1.3" points="{points}"/>')
        out.append(f'<line x1="{left + 110 * i}" x2="{left + 110 * i + 16}" y1="32" y2="32" stroke="{color}" stroke-width="2"/><text x="{left + 110 * i + 20}" y="35">{esc(name)}</text>')
    out.append("</svg>")
    return "".join(out)


def waveforms_html(project: Path, name: str, ir: dict, t: dict[str, str], covered: int = 0) -> str:
    """One waveform per analysis, drawn from its ngspice rawfile; an operating point gets its values as a table and a missing file is said.

    ``covered`` is how many waveform figures of the pipeline's own report are already on the page: when they cover every
    analysis that has a waveform, the drawings are left out (the tables and the missing-file lines stay).
    """
    simulation = ir.get("simulation") or {}
    wanted: dict[str, list[str]] = {}
    for e in simulation.get("expectations") or []:
        if isinstance(e, dict):
            wanted.setdefault(str(e.get("analysis_id")), []).append(str(e.get("vector") or ""))
    parts: list[str] = []
    loaded = []
    for analysis in simulation.get("analyses") or []:
        ident = str(analysis.get("id")) if isinstance(analysis, dict) else ""
        path = project / "spice" / ident / f"{name}.{ident}.raw"
        loaded.append((ident, path, read_raw(path) if ident else None))
    drawable = sum(1 for _, _, raw in loaded if raw is not None and len(raw["rows"]) >= 2)
    draw_own = covered < drawable  # the pipeline's figures do not cover every analysis: draw them all here
    for ident, path, raw in loaded:
        shown = path.relative_to(project).as_posix()
        if raw is None:
            parts.append(f'<p class="d-note">{esc(t["no_raw"].format(a=ident))}</p>')
            continue
        names, rows = raw["names"], raw["rows"]
        if len(rows) < 2:  # an operating point: nothing to draw, the numbers themselves
            parts.append(f'<p class="small">{esc(t["op_note"].format(a=ident, f=shown))}</p>' + table([t["vector"], t["value"]], [[key_cell(n), esc(f"{v:.6g}")] for n, v in list(zip(names, rows[0]))[:40]]))
            continue
        if not draw_own:
            continue
        picked = [n for n in dict.fromkeys(raw_name(v, names) for v in wanted.get(ident, [])) if n]
        if not picked:  # no expectation names a drawable vector: the first node voltages
            picked = [n for n in names[1:] if n.startswith("v(")][:4] or names[1:5]
        stride = max(1, len(rows) // 1500)
        xs = [r[0] for r in rows[::stride]]
        series = [(f"|{n}|" if raw["complex"] else n, [r[names.index(n)] for r in rows[::stride]]) for n in picked[:6]]  # an ac vector is drawn as its magnitude
        plot = raw["plot"].lower()
        x_label, log_x = (t["x_freq"], True) if "ac" in plot else (t["x_time"], False) if "transient" in plot else (f'{t["x_sweep"]}: {names[0]}', False)
        caption = t["wave_cap"].format(a=ident, f=shown, n=len(rows), s=t["wave_stride"].format(k=stride) if stride > 1 else "")
        parts.append(f'<figure>{waveform_svg(f"{t["wave"]} — {ident}", x_label, xs, series, log_x)}<figcaption>{esc(caption)}</figcaption></figure>')
    return "".join(parts)


#: the pipeline's result figures the summary repeats, by the words in their titles (Korean stage reports)
SIM_FIGURES = ("이론 공칭값 대 시뮬레이션", "시뮬레이션 파형")
NET_FIGURES = ("넷별 동박 길이", "넷별 배선 지연과 임계 길이")
WAVE_TITLE = "시뮬레이션 파형"
BOARD_FIGURES = ("보드 그림 (동박 포함)",)


def pipeline_figures(project: Path, stem: str, wanted: tuple[str, ...]) -> tuple[list[str], bool]:
    """The ``<figure>`` blocks of a pipeline stage report whose title holds one of ``wanted``, unchanged; and whether that report is older than the last run."""
    path = project / "reports" / f"{stem}.html"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        record = project / "pipeline.json"
        stale = record.exists() and path.stat().st_mtime < record.stat().st_mtime
    except OSError:
        return [], False
    found = []
    for m in re.finditer(r"<figure>.*?</figure>", text, re.S):
        title = re.search(r"<title>(.*?)</title>", m.group(0), re.S)
        if title and any(w in title.group(1) for w in wanted):
            found.append(m.group(0))
    return found, stale


def borrowed_html(project: Path, stem: str, wanted: tuple[str, ...], t: dict[str, str]) -> tuple[str, list[str]]:
    """The wanted figures of one pipeline report with a line saying where they come from (and a note when that report is older than the last run)."""
    figures, stale = pipeline_figures(project, stem, wanted)
    if not figures:
        return "", []
    note = f'<p class="small">{esc(t["borrowed"].format(f=stem + ".html"))}</p>' + (f'<p class="d-note">{esc(t["older"])}: {esc(stem)}.html</p>' if stale else "")
    # the line that says where the figures come from stays on the page of the first one
    return f'<div class="keep">{note}{figures[0]}</div>' + "".join(figures[1:]), figures


def copper(ir: dict) -> tuple[dict[str, int], dict[str, float], dict[str, set[str]], dict[str, int]]:
    """Per net, from the tracks and vias the IR records: segment count, summed segment length (mm), layers used, via count."""
    pcb = ir.get("pcb") or {}
    segments: dict[str, int] = {}
    length: dict[str, float] = {}
    layers: dict[str, set[str]] = {}
    vias: dict[str, int] = {}
    for tr in pcb.get("tracks") or []:
        if not isinstance(tr, dict):
            continue
        net = str(tr.get("net"))
        try:
            (ax, ay), (bx, by) = tr["start"], tr["end"]
            length[net] = length.get(net, 0.0) + math.hypot(bx - ax, by - ay)
        except (KeyError, TypeError, ValueError):
            pass
        segments[net] = segments.get(net, 0) + 1
        layers.setdefault(net, set()).add(str(tr.get("layer")))
    for via in pcb.get("vias") or []:
        if isinstance(via, dict):
            vias[str(via.get("net"))] = vias.get(str(via.get("net")), 0) + 1
    return segments, length, layers, vias


def bars_svg(title: str, rows: list[tuple[str, float]]) -> str:
    """Horizontal bars, one per ``(name, value)``, longest first as given; the value is printed at the end of its bar."""
    w, left, right, top, row_h = 680.0, 150.0, 60.0, 28.0, 16.0
    h = top + row_h * len(rows) + 10
    biggest = max((v for _, v in rows), default=0.0) or 1.0
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 {w:g} {h:g}" role="img" font-size="10" fill="#222"><title>{esc(title)}</title>',
           f'<text x="{left}" y="16" font-size="12" font-weight="600">{esc(title)}</text>']
    for i, (name, value) in enumerate(rows):
        y = top + row_h * i
        width = (w - left - right) * value / biggest
        out.append(f'<text x="{left - 6}" y="{y + 11:.1f}" text-anchor="end">{esc(name)}</text><rect class="bar" x="{left}" y="{y + 2:.1f}" width="{width:.1f}" height="{row_h - 5}" fill="#2a78d6"/>'
                   f'<text x="{left + width + 4:.1f}" y="{y + 11:.1f}">{value:.2f}</text>')
    out.append("</svg>")
    return "".join(out)


def net_table(ir: dict, t: dict[str, str], limit: int | None = None) -> tuple[str, int, int, int, int]:
    """The nets of the design with what the IR records about them (pins, track segments, copper length, vias, layers): the table and four counts."""
    segments, length, layers, vias = copper(ir)
    nets = [n for n in ir.get("nets") or [] if isinstance(n, dict)]
    routed = sum(1 for n in nets if segments.get(str(n.get("name"))))
    unrouted = sum(1 for n in nets if len(n.get("pins") or []) >= 2 and not segments.get(str(n.get("name"))))
    order = sorted(nets, key=lambda n: -length.get(str(n.get("name")), 0.0))[:limit] if limit is not None and len(nets) > limit else nets
    rows = []
    for n in order:
        name = str(n.get("name"))
        pins = [f"{pin.get('component_ref')}.{pin.get('pin_number')}" for pin in n.get("pins") or [] if isinstance(pin, dict)]
        rows.append([
            key_cell(name), esc(n.get("kind") or "-"), esc(n.get("net_class") or "-"), esc(", ".join(pins[:10]) + (f" … (+{len(pins) - 10})" if len(pins) > 10 else "")),
            key_cell(segments.get(name, 0)), key_cell(f"{length.get(name, 0.0):.2f}"), key_cell(vias.get(name, 0)), esc(", ".join(sorted(layers.get(name, []))) or "-"),
        ])
    html_table = table([t["net"], t["kind"], t["net_class"], t["pins"], t["segments"], t["length"], t["vias"], t["on_layers"]], rows)
    return html_table, len(nets), routed, unrouted, len(order)


def latest_results(ir: dict) -> dict[str, dict]:
    """The newest validation result of every check id (the IR keeps the whole log; the last entry of an id is the current one)."""
    newest: dict[str, dict] = {}
    for result in (ir.get("validation") or {}).get("results", []):
        newest[str(result.get("check_id"))] = result
    return newest


def status_cell(status: object) -> str:
    return f'<td class="{esc(status)}">{esc(status)}</td>'


def key_cell(text: object) -> str:
    """A cell that is never wrapped (a stage name, a reference, an id)."""
    return f'<td class="k">{esc(text)}</td>'


def badge(status: object, none: str) -> str:
    return f'<span class="{esc(status)}">{esc(status or none)}</span>'


def table(headers: list[str], rows: list[list[str]]) -> str:
    """An HTML table; cells are already HTML (escape text with :func:`esc` before passing it)."""
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(c if c.startswith("<td") else f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def figure(svg: str | None, caption: str, missing: str) -> str:
    if svg is None:
        return f'<p class="d-note">{esc(missing)}</p>'
    return f"<figure>{svg}<figcaption>{esc(caption)}</figcaption></figure>"


def quantity(traced: dict | None) -> str:
    if not isinstance(traced, dict) or traced.get("value") is None:
        return "-"
    value = traced["value"]
    text = f"{value:.6g}" if isinstance(value, float) else str(value)
    return f"{text} {traced.get('unit') or ''}".strip()


def requirements(ir: dict) -> list[dict]:
    return [r for r in (ir.get("requirements") or {}).get("requirements") or [] if isinstance(r, dict)]


def left_out(ir: dict) -> list[str]:
    """The requirement keys the user left out of the design (``requirements.left_out``), as text."""
    return [str(x.get("key") or x.get("id") or x) if isinstance(x, dict) else str(x) for x in (ir.get("requirements") or {}).get("left_out") or []]


def run_stopped(record: dict, stages: list[dict]) -> str | None:
    """One sentence when the run record says the pipeline did not reach its last stage (aborted, blocked, no release outcome); ``None`` for a finished run."""
    state = record.get("state") if isinstance(record.get("state"), dict) else {}
    last = stages[-1].get("stage") if stages else "-"
    if record.get("aborted"):
        return f"aborted in stage {record.get('aborted_stage') or last} ({record.get('aborted')}); the stages after it were not run"
    if state.get("blocked"):
        return f"blocked at stage {last} on a required question; the stages after it were not run"
    if not any(s.get("stage") == "release" for s in stages):
        return f"stopped after stage {last}; the stages after it were not run"
    return None


def page(title: str, lang: str, body: str, style: str = STYLE) -> str:
    return f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><title>{esc(title)}</title><style>{style}</style></head><body>{body}</body></html>'


def cover_html(kind: str, name: str, ir: dict, stages: list[dict], pipeline: dict, lang: str, stopped: str | None = None, finding: str = "") -> str:
    """The cover page: the kind of report, the project, a small table of facts and the pipeline's RELEASE line."""
    t = TEXT[lang]
    release = next((s for s in stages if s.get("stage") == "release"), {})
    topology = (ir.get("topology") or {}).get("name")
    rows = [
        (t["c_project"], esc(name)), (t["design"], esc((ir.get("topology") or {}).get("name") or "-")),
        (t["c_created"], esc(str((ir.get("project") or {}).get("created_at", "-"))[:10])), (t["c_issued"], esc(datetime.date.today().isoformat())),
        (t["c_tool"], esc(f"ai-eda {pipeline.get('ai_eda_version', '-')}")), (t["c_verdict"], badge(release.get("status"), t["none"])),
    ]
    facts = "".join(f"<tr>{key_cell(k)}<td>{v}</td></tr>" for k, v in rows)
    return (
        f'<section class="cover"><div><div class="kind">AI-EDA</div><h1>{esc(kind)}</h1><div class="sub">{esc(name)}{esc(" — " + str(topology) if topology else "")}</div>'
        + (f'<p class="d-note FAIL"><b>{esc(finding)}</b></p>' if finding else "")
        + f'<div class="rule"></div><table><tbody>{facts}</tbody></table>' + (f'<p class="d-note"><b>{esc(t["stopped"])}</b>: {esc(stopped)}</p>' if stopped else "")
        + f'</div><div class="foot">{esc(t["c_foot"])}</div></section>'
    )


def contents_html(entries: list[tuple[str, str, list[tuple[str, str]]]], lang: str, intro: str = "") -> str:
    """The contents page: ``(anchor, title, [(anchor, sub-title), ...])`` per chapter, each a link into the document; ``intro`` is a line under the list."""
    items = "".join(
        f'<li><a href="#{a}">{esc(title)}</a>' + ("<ol>" + "".join(f'<li><a href="#{sa}">{esc(st)}</a></li>' for sa, st in subs) + "</ol>" if subs else "") + "</li>"
        for a, title, subs in entries
    )
    note = f'<p class="small">{esc(intro)}</p>' if intro else ""
    return f'<section class="contents"><h2>{esc(TEXT[lang]["toc"])}</h2><ol>{items}</ol>{note}</section>'


def summary_html(project: Path, name: str, ir: dict, stages: list[dict], pictures: dict[str, Path], lang: str, pipeline: dict, stopped: str | None = None) -> str:
    t = TEXT[lang]
    status = {s.get("stage"): s for s in stages}
    results = latest_results(ir)
    open_stages = [s for s in stages if s.get("status") not in OK_STATUSES]
    release = status.get("release", {})
    bom: list[dict] = []
    if (project / "bom.csv").exists():
        with open(project / "bom.csv", newline="", encoding="utf-8") as f:
            bom = list(csv.DictReader(f))
    unverified = sum(1 for row in bom if row.get("MPN") == "NOT_VERIFIED")  # counts of cells, copied: this script does not decide what is confirmed
    no_maker = sum(1 for row in bom if row.get("Manufacturer") == "NOT_VERIFIED")
    stop_line = f'<p class="d-note"><b>{esc(t["stopped"])}</b>: {esc(stopped)}</p>' if stopped else ""
    expectations = [e for e in ((ir.get("simulation") or {}).get("expectations") or []) if isinstance(e, dict)]
    passed = sum(1 for e in expectations if results.get(f"spice.{e.get('id')}", {}).get("status") == "PASS")

    def stage_line(stage_name: str, limit: int = 110) -> str:
        s = status.get(stage_name, {})
        return f"{badge(s.get('status'), t['none'])} — {esc(one_line(s.get('message'), limit))}"

    keys = ("h_overview", "h_bom", "h_sch", "h_sim", "h_net", "h_pcb", "h_open")
    title = {key: f"{n}. {t[key]}" for n, key in enumerate(keys, 1)}  # the numbers are made here, once
    heads = [(f"s{n}", title[key]) for n, key in enumerate(keys, 1)]
    finding = pipeline_association(project, pipeline)["message"]
    parts: list[str] = [cover_html(t["summary_title"], name, ir, stages, pipeline, lang, stopped, finding), contents_html([(a, title, []) for a, title in heads], lang)]
    # 1. at a glance: the verdict, a few facts, the requirements as key = value, the stages as name + status only
    parts.append(f'<h2 id="s1">{esc(title["h_overview"])}</h2>')
    parts.append(
        f'<p class="d-note"><b>RELEASE: {badge(release.get("status"), t["none"])}</b> — {esc(one_line(release.get("message"), 150))}<br>{esc(t["release_note"].format(n=len(open_stages), k=len(stages)))}</p>'
        f'{stop_line}<p class="small">{esc(t["copied"])}</p>'
    )
    parts.append(table([t["item"], t["content"]], [
        [key_cell(t["design"]), esc((ir.get("topology") or {}).get("name") or "-")],
        [key_cell(t["requirements"]), esc(", ".join(f"{r.get('key')} = {quantity(r.get('value'))}" for r in requirements(ir)) or "-")],
        *([[key_cell(t["left_out"]), esc(", ".join(left_out(ir)))]] if left_out(ir) else []),
        [key_cell(t["parts"]), esc(t["parts_n"].format(n=len(bom), u=unverified))],
        [key_cell(t["sim"]), f"{badge(status.get('spice', {}).get('status'), t['none'])} — {esc(t['sim_n'].format(n=len(expectations), p=passed))}"],
        [key_cell("ERC"), stage_line("erc")], [key_cell("DRC"), stage_line("drc")], [key_cell(t["mfg"]), stage_line("manufacturing_outputs", 90)],
    ]))
    parts.append(f"<h3>{esc(t['stages'])}</h3>" + '<div class="chips">' + "".join(f"<div><span>{esc(s.get('stage'))}</span>{badge(s.get('status'), t['none'])}</div>" for s in stages) + "</div>")

    parts.append(f'<h2 class="page" id="s2">{esc(title["h_bom"])}</h2>')
    if bom:
        cols = [c for c in ("Reference", "Value", "Description", "Manufacturer", "MPN", "Footprint", "Qty") if c in bom[0]]
        parts.append(table(cols, [[(status_cell(row[c]) if row[c] == "NOT_VERIFIED" else key_cell(row[c]) if c in ("Reference", "Value", "Qty") else esc(row[c])) for c in cols] for row in bom]))
        parts.append(f'<p class="small">{esc(t["bom_note"].format(n=len(bom), u=unverified, m=no_maker))}</p>')
    else:
        parts.append(f'<p class="d-note">{esc(t["no_bom"])}</p>')

    parts.append(f'<h2 class="page" id="s3">{esc(title["h_sch"])}</h2>')
    sheets = [k for k in pictures if k.startswith("schematic")]
    if not sheets:
        parts.append(figure(None, "", t["no_sch"]))
    for k in sheets:
        svg = inline_svg(pictures[k])
        if svg is not None and len(sheets) == 1:  # one sheet: show the circuit, not the empty rest of the sheet
            svg = crop_svg(svg, circuit_box(project / f"{name}.kicad_sch"))
        parts.append(figure(svg, f"{pictures[k].name} — {t['drawn']} {name}.kicad_sch", t["no_sch"]))
    parts.append(f"<p>ERC: {stage_line('erc', 200)}</p>")

    parts.append(f'<h2 class="page" id="s4">{esc(title["h_sim"])}</h2>')
    parts.append(f"<p>{esc(t['spice_stage'])}: {stage_line('spice', 300)}</p>")
    rows = []
    for e in expectations:
        r = results.get(f"spice.{e.get('id')}", {})
        measured = (r.get("details") or {}).get("measured")
        rows.append([
            key_cell(e.get("id")), esc(f"{e.get('analysis_id')}: {e.get('vector')} ({e.get('reduce')})"), key_cell(quantity(e.get("nominal"))),
            key_cell(f"{measured:.6g}" if isinstance(measured, (int, float)) and not isinstance(measured, bool) else "-"),
            status_cell(r.get("status", t["none"])), esc(one_line(r.get("message"), 160)), esc(e.get("requirement_id") or "-"),
        ])
    parts.append(table([t["exp"], t["what"], t["nominal"], t["measured"], t["verdict"], t["message"], t["verifies"]], rows) if rows else f'<p class="d-note">{esc(t["no_exp"])}</p>')
    other = [(k, r) for k, r in results.items() if k in ("calc.recompute", "component.fit", "domain.power.thermal", "domain.analog.bias")]
    if other:
        parts.append(f"<h3>{esc(t['other_checks'])}</h3>" + table([t["check"], t["status"], t["message"]], [[key_cell(k), status_cell(r.get("status")), esc(one_line(r.get("message"), 200))] for k, r in other]))
    sim_figures, sim_list = borrowed_html(project, "04_최종_보고서", SIM_FIGURES, t) if lang == "ko" else ("", [])
    covered = sum(1 for f in sim_list if WAVE_TITLE in f)
    parts.append(f"<h3>{esc(t['wave'])}</h3>" + sim_figures + waveforms_html(project, name, ir, t, covered))
    parts.append(f'<p class="small">{esc(t["see_detail"])}</p>')

    parts.append(f'<h2 class="page" id="s5">{esc(title["h_net"])}</h2>')
    nets_html, n_nets, n_routed, n_unrouted, n_shown = net_table(ir, t, limit=40)
    parts.append(f'<p class="small">{esc(t["net_note"].format(n=n_nets, r=n_routed, u=n_unrouted))}' + (f' {esc(t["net_more"].format(k=n_shown, n=n_nets))}' if n_shown < n_nets else "") + "</p>" + nets_html)
    net_figures, _ = borrowed_html(project, "03_회로_보고서", NET_FIGURES, t) if lang == "ko" else ("", [])
    if net_figures:
        parts.append(net_figures)
    else:  # no pipeline figure to repeat (English report, or the stage reports are missing): the same numbers as bars
        longest = sorted(((n, v) for n, v in copper(ir)[1].items() if v > 0), key=lambda item: -item[1])[:25]
        if longest:
            parts.append(f'<figure>{bars_svg(t["net_chart"], longest)}<figcaption>{esc(t["net_chart_cap"].format(k=len(longest)))}</figcaption></figure>')

    parts.append(f'<h2 class="page" id="s6">{esc(title["h_pcb"])}</h2>')
    pcb = ir.get("pcb") or {}
    gerbers = sorted(p.name for p in (project / "gerber").glob("*")) if (project / "gerber").is_dir() else []
    parts.append(table([t["item"], t["content"]], [
        [key_cell(t["layers"]), esc(", ".join(str(layer.get("name")) for layer in pcb.get("layers", []) if isinstance(layer, dict)) or "-")],
        [key_cell(t["placed"]), esc(len(pcb.get("placements", [])))], [key_cell(t["tracks"]), esc(f"{len(pcb.get('tracks', []))} / {len(pcb.get('vias', []))}")],
        [key_cell(t["pcb_compile"]), stage_line("pcb", 60)], [key_cell("DRC"), stage_line("drc", 200)], [key_cell(t["mfg"]), stage_line("manufacturing_outputs", 200)],
        [key_cell(t["gerbers"]), esc(", ".join(gerbers) or t["nofile"])],
    ]))
    board_figures, _ = borrowed_html(project, "03_회로_보고서", BOARD_FIGURES, t) if lang == "ko" else ("", [])
    if board_figures:  # the pipeline's own board picture: both copper layers in colour with the part names, as in the detailed report
        parts.append(board_figures)
    else:  # English report, or no stage report: KiCad's rendering of each side
        for key, caption in (("board_top", t["top"]), ("board_bottom", t["bottom"])):
            svg = inline_svg(pictures[key]) if key in pictures else None
            parts.append(figure(fill_width(svg) if svg else None, f"{caption} — {t['drawn']} {name}.kicad_pcb", f"{t['no_board_pic']} ({caption})").replace("<figure>", '<figure class="board">'))

    parts.append(f'<h2 class="page" id="s7">{esc(title["h_open"])}</h2>')
    parts.append(stop_line)
    if open_stages:
        parts.append(table([t["stage"], t["status"], t["reason"]], [[key_cell(s.get("stage")), status_cell(s.get("status")), esc(one_line(s.get("message"), 170))] for s in open_stages]))
    elif not stopped:  # only a finished run with every recorded stage PASS / NOT_APPLICABLE may say so
        parts.append(f"<p>{esc(t['all_pass'])}</p>")
    counts: dict[str, int] = {}
    for r in results.values():
        counts[str(r.get("status"))] = counts.get(str(r.get("status")), 0) + 1
    parts.append(f'<p class="small">{esc(t["latest"])}: ' + esc(", ".join(f"{k} {v}" for k, v in sorted(counts.items()))) + f". {esc(t['see_detail'])}</p>")
    return page(f"{t['summary_title']}: {name}", lang, "".join(parts))


def detail_html(project: Path, name: str, ir: dict, stages: list[dict], lang: str, pipeline: dict, stopped: str | None = None) -> tuple[str, int, list[str], list[str]]:
    """Full stage messages, requirements and nets, then the pipeline's own reports bound with a table of contents.

    Also returns how many reports were bound, the names of the ones that are missing, and the names of the ones that
    are older than pipeline.json (written before the last run and not rewritten since).
    """
    t = TEXT[lang]
    sources = [project / "reports" / f"{stem}.html" for stem in STAGE_REPORTS] if lang == "ko" else [project / "report.html"]
    reqs = requirements(ir)
    req_rows = []
    for r in reqs:
        value = r.get("value") if isinstance(r.get("value"), dict) else {}
        provenance = value.get("provenance") if isinstance(value.get("provenance"), dict) else {}
        req_rows.append([key_cell(r.get("id")), esc(r.get("text")), esc(quantity(value)), esc(provenance.get("kind", "-"))])
    reqs_html = table(["id", t["requirements"], t["value"], t["source"]], req_rows)
    if left_out(ir):
        reqs_html += f'<p class="small">{esc(t["left_out"])}: {esc(", ".join(left_out(ir)))}</p>'
    stop_line = f'<p class="d-note"><b>{esc(t["stopped"])}</b>: {esc(stopped)}</p>' if stopped else ""
    chapters: list[tuple[str, str]] = [
        (t["ch_stages"], stop_line + table([t["stage"], t["status"], t["message"]], [[key_cell(s.get("stage")), status_cell(s.get("status")), esc(one_line(s.get("message")))] for s in stages])),
        (t["ch_reqs"], reqs_html),
        (t["ch_nets"], net_table(ir, t)[0]),
    ]
    toc: list[tuple[str, str, list[tuple[str, str]]]] = [(f"c{n}", f"{n}. {title}", []) for n, (title, _) in enumerate(chapters, 1)]
    sections = [f'<section{" class=bound" if n > 1 else ""} id="c{n}"><h2>{n}. {esc(title)}</h2>{body}</section>' for n, (title, body) in enumerate(chapters, 1)]
    styles, bound = "", 0
    missing = [p.name for p in sources if not p.exists()]
    record = project / "pipeline.json"
    older: list[str] = []
    for path in sources:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not styles:
            m = re.search(r"<style>(.*?)</style>", text, re.S)
            styles = m.group(1) if m else ""
        m = re.search(r"<body[^>]*>(.*)</body>", text, re.S)
        body = m.group(1) if m else text
        if path.name == "report.html":  # its links are relative to the project folder; this page lives one level down
            body = body.replace('href="reports/', 'href="../reports/')
        stale = record.exists() and path.stat().st_mtime < record.stat().st_mtime
        if stale:
            older.append(path.name)
        n = len(sections) + 1
        counter = iter(range(1, 100_000))
        heads: list[tuple[str, str]] = []

        def anchor(match: re.Match[str], n: int = n, counter=counter, heads: list[tuple[str, str]] = heads) -> str:
            ident = f"c{n}-{next(counter)}"
            heads.append((ident, html.unescape(re.sub(r"<[^>]+>", "", match.group(2))).strip()))  # tags off, entities back to text: escaped once, where printed
            return f'<h2 id="{ident}"{match.group(1)}>{match.group(2)}</h2>'

        body = re.sub(r"<h2([^>]*)>(.*?)</h2>", anchor, body, flags=re.S)
        title = re.search(r"<title>(.*?)</title>", text, re.S)
        label = re.sub(r"\s+", " ", html.unescape(title.group(1))).strip() if title else path.stem
        toc.append((f"c{n}", f"{n}. {label}", heads))
        flag = f'<p class="d-note">{esc(t["older"])}: {esc(path.name)}</p>' if stale else ""
        sections.append(f'<section class="bound" id="c{n}">{flag}{body}</section>')
        bound += 1
    if missing:
        sections.append(f'<p class="d-note">{esc(t["missing_reports"])} {esc(", ".join(missing))}</p>')
    cover = cover_html(t["detail_title"], name, ir, stages, pipeline, lang, stopped) + contents_html(toc, lang, t["detail_intro"].format(n=bound))
    # the pipeline's own style first (its reports rely on it), then this script's tables and table of contents
    return page(f"{t['detail_title']}: {name}", lang, cover + "".join(sections), styles + "\n" + STYLE), bound, missing, older


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_matches(recorded: str, actual: str) -> bool:
    recorded = recorded.lower()
    return (recorded[7:] if recorded.startswith("sha256:") else recorded) == actual


def pipeline_association(project: Path, pipeline: dict) -> dict:
    recorded = pipeline.get("ir_file_sha256")
    actual = file_sha256(project / "ir.json")
    outcome = "not_recorded" if not recorded else "match" if hash_matches(str(recorded), actual) else "mismatch"
    return {"outcome": outcome, "recorded_sha256": recorded, "sha256": actual,
            "message": "PIPELINE/IR HASH MISMATCH: pipeline.json's ir_file_sha256 does not match ir.json; its stage outcomes are not associated with these IR bytes."
            if outcome == "mismatch" else ""}


def record_references(value: object, location: str):
    """Only reference fields, never paths guessed from messages, notes or URLs."""
    if isinstance(value, str) and value:
        yield location, value, None
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from record_references(item, f"{location}[{i}]")
    elif isinstance(value, dict):
        if value.get("path"):
            yield location + ".path", value["path"], value.get("content_hash") or value.get("sha256")
        elif value.get("url"):
            yield location + ".url", value["url"], None
        for key in ("files", "evidence", "artifact"):
            if key in value:
                yield from record_references(value[key], location + "." + key)


def spice_references(value: object, location: str):
    if isinstance(value, dict):
        for key, item in sorted(value.items()):
            if key in ("raw_output_path", "deck_path", "netlist_path", "output_dir", "result_dir", "workdir") and isinstance(item, str) and item:
                yield location + "." + key, item, value.get(key[:-5] + "_hash") if key.endswith("_path") else None
            elif isinstance(item, (dict, list)):
                yield from spice_references(item, location + "." + key)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from spice_references(item, f"{location}[{i}]")


SOURCE_SUFFIXES = {".pdf", ".html", ".htm", ".txt", ".md", ".json"}
MODEL_SUFFIXES = {".step", ".stp", ".glb", ".png"}
SPICE_SUFFIXES = {".raw", ".cir", ".spice", ".sp", ".ckt", ".lib", ".mod", ".json", ".log", ".txt"}


def exclusion_reason(relative: Path) -> str:
    parts = [p.casefold() for p in relative.parts]
    if any(p.startswith(".") or p.split(".")[0] in ("private", "secrets", "credentials", "__pycache__") for p in parts):
        return "hidden, lock or private path"
    if any(":" in p or any(ord(c) < 32 for c in p) for p in parts):
        return "unsafe archive path"
    if relative.suffix.lower() in (".key", ".pem", ".pfx", ".p12", ".env", ".kicad_prl"):
        return "private/local settings file"
    return ""


def delivery_index(project: Path, name: str, files: list[Path]) -> tuple[dict, dict[str, Path]]:
    """Index paths relative to the ZIP extraction directory; keep every record occurrence."""
    project = project.resolve()
    ir = load_json(project / "ir.json")
    pending = []
    for i, result in enumerate((ir.get("validation") or {}).get("results") or []):
        if isinstance(result, dict):
            for field in ("evidence", "artifact"):
                pending.extend(record_references(result.get(field), f"ir.json:validation.results[{i}].{field}"))
    artifacts = ir.get("artifacts") or {}
    if isinstance(artifacts, dict):
        for key, artifact in sorted(artifacts.items()):
            pending.extend(record_references(artifact, f"ir.json:artifacts.{key}"))
    else:
        pending.extend(record_references(artifacts, "ir.json:artifacts"))
    pending.extend(("listed file", p.relative_to(project).as_posix(), None) for p in files)
    pending.extend(("listed folder", folder, None) for folder in ("sources", "3d") if (project / folder).exists())
    rows, selected, metadata = [], {}, {}
    expanded, parsed, changed = set(), set(), set()

    def expand(folder: Path, location: str) -> None:
        if folder in expanded:
            return
        expanded.add(folder)
        for child in sorted(folder.iterdir()):
            pending.append((location, child.relative_to(project).as_posix(), None))

    for location, reference, recorded in pending:
        row = {"record": location, "reference": reference, "recorded_sha256": recorded,
               "outcome": "excluded", "package_path": None}
        rows.append(row)
        if not isinstance(reference, str) or "://" in reference:
            row["reason"] = "not a local file reference; no network fetch"
            continue
        # Do not reinterpret a foreign absolute path as a relative filename on POSIX.
        windows = PureWindowsPath(reference)
        if windows.drive and (os.name != "nt" or not windows.is_absolute()):
            row["outcome"] = "outside_project"
            continue
        path = Path(os.path.abspath(project / Path(reference.replace("\\", "/"))))
        try:
            relative = path.relative_to(project)
            resolved = path.resolve()
            resolved.relative_to(project)
        except ValueError:
            row["outcome"] = "outside_project"
            continue
        reason = exclusion_reason(relative) or exclusion_reason(resolved.relative_to(project))
        if reason:
            row["reason"] = reason
            continue
        if not path.exists():
            row["outcome"] = "missing"
            continue
        if path.is_dir():
            # Directory references can expand only these explicit evidence folders.
            if not relative.parts or relative.parts[0] not in ("sources", "3d", "spice") or path.is_symlink() or resolved != path:
                row["reason"] = "directory expansion not permitted"
                continue
            expand(path, location + " -> folder")
            row.update(outcome="included", kind="directory", package_path=f"{name}/{relative.as_posix()}")
            continue
        if not path.is_file():
            row["reason"] = "not a regular file"
            continue
        permitted = {"sources": SOURCE_SUFFIXES, "3d": MODEL_SUFFIXES}.get(relative.parts[0])
        if permitted is not None and path.suffix.lower() not in permitted:
            row["reason"] = "file type not permitted in this listed folder"
            continue
        package_path = f"{name}/{relative.as_posix()}"
        if package_path not in metadata:
            metadata[package_path] = {"sha256": file_sha256(path), "size": path.stat().st_size}
        info = metadata[package_path]
        row.update(info)
        if recorded and not hash_matches(str(recorded), info["sha256"]):
            # kept: a Gerber job, drill or 3D export the pipeline rewrote after recording it is still the board's file; the
            # index says its bytes are not the recorded ones instead of leaving it out of the package
            row.update(outcome="included_changed", kind="file", package_path=package_path,
                       reason="the recorded hash differs from the current bytes (rewritten after it was recorded); packaged as it is now")
            changed.add(package_path)
            selected[package_path] = path
            continue
        row.update(outcome="included", kind="file", package_path=package_path)
        selected[package_path] = path
        if relative.parts[0] == "spice":
            if path.suffix.lower() == ".json" and resolved not in parsed:
                parsed.add(resolved)
                pending.extend(spice_references(load_json(path), relative.as_posix()))
            if path.suffix.lower() == ".raw" and path.parent != project / "spice":
                # Companion decks/logs in the referenced analysis folder, not all project files.
                if path.parent not in expanded:
                    expanded.add(path.parent)
                    pending.extend((relative.as_posix() + " -> analysis folder", p.relative_to(project).as_posix(), None)
                                   for p in sorted(path.parent.iterdir()) if p.is_file() and p.suffix.lower() in SPICE_SUFFIXES)
    # every other row naming a file whose recorded hash differs says so too, so no row reads as a matching record
    for row in rows:
        if row["package_path"] in changed and row["outcome"] == "included":
            row["changed_since_record"] = True
    for row in rows:
        if row.get("kind") == "directory" and not any(p.startswith(row["package_path"] + "/") for p in selected):
            row.update(outcome="excluded", package_path=None, reason="directory has no included files")
    return {"schema_version": 1, "path_base": "ZIP extraction directory",
            "pipeline_ir_association": pipeline_association(project, load_json(project / "pipeline.json")),
            "policy": "Only referenced files and listed folders; hidden/private paths and locks excluded. A file whose recorded hash differs from its current bytes is packaged as it is now with outcome included_changed. Records are unchanged.",
            "references": sorted(rows, key=lambda r: (str(r["reference"]), r["record"])),
            "files": {p: metadata[p] for p in sorted(selected)}}, selected


def make_zip(project: Path, name: str, stages: list[dict], notes: list[str], summary_stem: str, stopped: str | None = None, *, target: Path | None = None) -> Path:
    project = project.resolve()
    if not name or name in (".", "..") or any(c in name for c in '/\\:'):
        raise ValueError("project id must be a single safe archive folder name")
    # the project's own files by their exact names (an id with [ or * in it is not a pattern), the folders by pattern
    files = [p for p in (project / f"{name}{ext}" for ext in (".kicad_pro", ".kicad_sch", ".kicad_pcb", ".kicad_prl", ".cir")) if p.is_file()]
    for pattern in ("bom.csv", "cpl.csv", "ir.json", "pipeline.json", "report.html", "gerber/*", "reports/*", f"{OUT_DIR}/*.pdf", f"{OUT_DIR}/*.html", f"{OUT_DIR}/pictures/*.svg"):
        files += [p for p in sorted(project.glob(pattern)) if p.is_file()]
    index, selected = delivery_index(project, name, files)
    association = index["pipeline_ir_association"]
    rewritten = sorted({r["package_path"] for r in index["references"] if r["outcome"] == "included_changed"})
    pdf = project / OUT_DIR / f"{summary_stem}.pdf"
    summary = f"{OUT_DIR}/{summary_stem}.{'pdf' if pdf.is_file() and pdf.stat().st_size > 0 else 'html'}"  # the file that is really in the zip
    readme = [
        f"{name} - deliverables of the ai-eda pipeline", "",
        *([association["message"], ""] if association["outcome"] == "mismatch" else []),
        f"Open the KiCad project with KiCad 10: {name}.kicad_pro", "",
        "Stage results (copied from pipeline.json; nothing here is a release approval):",
        *[f"  {str(s.get('stage')):<24} {s.get('status')}" for s in stages],
        *([f"  THE RUN DID NOT FINISH: {stopped}"] if stopped else []), "",
        f"A stage that is not PASS was not verified by this run or failed; read {summary}, its last section, before ordering boards or parts.",
        *([""] + notes if notes else []), "",
        "Contents: KiCad project (.kicad_pro / .kicad_sch / .kicad_pcb), gerber/ (layers + drill), bom.csv, cpl.csv, the SPICE netlist (.cir),",
        f"reports/ and report.html (the pipeline's own reports, ERC / DRC json), {OUT_DIR}/ (the two bound reports and the pictures), ir.json and pipeline.json (the design record).",
        "Referenced evidence, SPICE results/decks/rawfiles, permitted sources/ documents and 3d/ exports are included when available and unchanged.",
        "delivery-index.json maps original references to paths relative to the ZIP extraction directory, with SHA-256, byte sizes and explicit omission outcomes.",
        *([f"{len(rewritten)} packaged file(s) differ from the hash the records hold for them (rewritten after they were recorded; outcome "
           "included_changed in delivery-index.json): " + ", ".join(p.split("/", 1)[1] for p in rewritten)] if rewritten else []),
        "", "The pipeline's records and reports hold the absolute folder paths of the computer the design was made on; look before passing the zip on.",
    ]
    generated = {f"{name}/README.txt": ("\n".join(readme) + "\n").encode("utf-8")}
    archive_paths = [*selected, *generated, f"{name}/delivery-index.json"]
    if len({p.casefold() for p in archive_paths}) != len(archive_paths):
        raise ValueError("duplicate archive path (including case-insensitive or generated-file collision)")
    for path, data in generated.items():
        index["files"][path] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    index["files"] = dict(sorted(index["files"].items()))
    generated[f"{name}/delivery-index.json"] = (json.dumps(index, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    target = target or project / f"{name}_deliverables.zip"
    # Validate before replacing an existing package, and hash the exact bytes written.
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".zip", delete=False) as temp:
        temporary = Path(temp.name)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as z:
            for archive_path in sorted(archive_paths):
                if archive_path in generated:
                    z.writestr(archive_path, generated[archive_path])
                else:
                    path = selected[archive_path]
                    data = path.read_bytes()
                    info = index["files"][archive_path]
                    if hashlib.sha256(data).hexdigest() != info["sha256"] or len(data) != info["size"]:
                        raise ValueError(f"file changed while packaging: {path}")
                    z.writestr(zipfile.ZipInfo.from_file(path, archive_path), data, compress_type=zipfile.ZIP_DEFLATED)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # a Korean file name on a console of another code page is printed escaped, not a crash
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="backslashreplace")
            except (ValueError, OSError):
                pass
    ap = argparse.ArgumentParser(description="two PDF reports and one zip from a finished ai-eda project")
    ap.add_argument("project", help="the project folder or its ir.json")
    ap.add_argument("--lang", choices=sorted(TEXT), default="ko", help="language of the two reports (default ko); ask the user which one they want")
    ap.add_argument("--no-pdf", action="store_true", help="write the .html reports only")
    args = ap.parse_args(argv)
    given = Path(args.project).resolve()
    project = given.parent if given.is_file() else given
    ir = load_json(project / "ir.json")
    if not ir:
        print(f"{project}: no readable ir.json", file=sys.stderr)
        return 2
    name = str((ir.get("project") if isinstance(ir.get("project"), dict) else {}).get("id") or project.name)
    record = load_json(project / "pipeline.json")
    state = record.get("state") if isinstance(record.get("state"), dict) else {}
    stages = [s for s in state.get("outcomes") or [] if isinstance(s, dict)] if isinstance(state.get("outcomes"), list) else []
    if not stages:  # no record of what the pipeline found: nothing honest can be reported
        print(f"{project}: pipeline.json records no stage outcome (missing, unreadable or empty) - run `ai-eda run` first; nothing was written", file=sys.stderr)
        return 1
    if not (project / f"{name}.kicad_pcb").exists():
        print(f"{project}: no {name}.kicad_pcb yet - run the pipeline to the PCB stage first", file=sys.stderr)
        return 1
    t = TEXT[args.lang]
    stopped = run_stopped(record, stages)
    notes: list[str] = []
    association = pipeline_association(project, record)
    if association["message"]:
        notes.append(association["message"])
    if stopped:
        notes.append(f"The run did not finish: {stopped}. Files of an earlier run may still be in the folder; they are not this run's.")
    recorded_for = record.get("ir_file")
    if isinstance(recorded_for, str) and recorded_for and Path(recorded_for) != project / "ir.json":
        notes.append(f"pipeline.json was recorded for another ir.json ({recorded_for}): the folder was copied or moved; run `ai-eda relocate` and `ai-eda run` to make the record this project's.")
    out = project / OUT_DIR
    try:
        out.mkdir(exist_ok=True)
        for stale in [*out.glob("*.pdf"), *out.glob("*.html")]:  # a report of an earlier call (another language, an older run) is not this run's
            stale.unlink()
        pictures = draw(project, name, out)
        if not pictures:
            notes.append("No pictures were drawn: kicad-cli was not found (set KICAD_CLI) or its export failed; open the KiCad files instead.")
        detail, bound, missing, older = detail_html(project, name, ir, stages, args.lang, record, stopped)
        if missing:
            notes.append(f"Not bound into the detailed report (missing): {', '.join(missing)}; run " + ("`ai-eda stage-reports <ir.json>`" if args.lang == "ko" else "`ai-eda report <ir.json>`") + " first.")
        if older:
            notes.append(f"Older than the last run and bound as they are: {', '.join(older)}; run `ai-eda stage-reports <ir.json>` / `ai-eda report <ir.json>` to rewrite them.")
        pages = {t["summary_stem"]: summary_html(project, name, ir, stages, pictures, args.lang, record, stopped), t["detail_stem"]: detail}
        browser = None if args.no_pdf else find_browser()
        for stem, text in pages.items():
            target = out / f"{stem}.html"
            with open(target, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            if args.no_pdf:
                continue
            problem = print_pdf(target, out / f"{stem}.pdf", browser)
            if problem:
                notes.append(f"{stem}.pdf was not written: {problem}. The .html file holds the same content.")
        package = make_zip(project, name, stages, notes, t["summary_stem"], stopped)
    except ValueError as e:
        print(f"cannot package project: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"cannot replace {e.filename or e}: it may be open in another program - close it and run again", file=sys.stderr)
        return 2
    print(f"reports: {out}")
    for p in sorted(out.glob("*.pdf")) + sorted(out.glob("*.html")):
        print(f"  {p.name}  ({p.stat().st_size // 1024} kB)")
    print(f"zip: {package}  ({package.stat().st_size // 1024} kB)")
    not_pass = [f"{s.get('stage')} {s.get('status')}" for s in stages if s.get("status") not in OK_STATUSES]
    print("stages that did not pass (copied from the pipeline): " + (", ".join(not_pass) or "none of the recorded ones"))
    for note in notes:
        print("note: " + note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
