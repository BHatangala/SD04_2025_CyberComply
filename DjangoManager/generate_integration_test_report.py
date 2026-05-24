"""
generate_integration_test_report.py
===================================
Generates a formatted PDF report specifically for integration tests.

Run from DjangoManager/:
    python generate_integration_test_report.py

Output:
    integration_test_report_<timestamp>.pdf
"""

import subprocess
import sys
import re
import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak,
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT


# ─────────────────────────────────────────────────────────────────────────────
# 1. Run integration tests
# ─────────────────────────────────────────────────────────────────────────────

def run_tests():
    test_module = "core.tests_integration"
    print(f"Running: python manage.py test {test_module} --verbosity=2")

    result = subprocess.run(
        [sys.executable, "manage.py", "test", test_module, "--verbosity=2"],
        capture_output=True,
        text=True,
    )

    return result.stderr + "\n" + result.stdout, result.returncode


# ─────────────────────────────────────────────────────────────────────────────
# 2. Parse test output
# ─────────────────────────────────────────────────────────────────────────────

HEADER_RE = re.compile(r'(test_\w+)\s+\(([^)]+)\)\s+\.\.\.', re.MULTILINE)


def parse_output(output):
    results = {
        "passed_tests": [],
        "failed_tests": [],
        "error_tests": [],
        "failure_details": [],
        "run_time": "unknown",
        "total": 0,
        "failures": 0,
        "errors": 0,
        "summary_line": "",
        "overall": "UNKNOWN",
    }

    ran_m = re.search(r'Ran (\d+) tests? in ([\d.]+s)', output)
    if ran_m:
        results["total"] = int(ran_m.group(1))
        results["run_time"] = ran_m.group(2)

    if re.search(r'^OK$', output, re.MULTILINE):
        results["overall"] = "PASSED"
        results["summary_line"] = "OK"

    fail_m = re.search(r'^FAILED\s*\((.+)\)', output, re.MULTILINE)
    if fail_m:
        results["overall"] = "FAILED"
        inner = fail_m.group(1)
        f = re.search(r'failures=(\d+)', inner)
        e = re.search(r'errors=(\d+)', inner)
        results["failures"] = int(f.group(1)) if f else 0
        results["errors"] = int(e.group(1)) if e else 0
        results["summary_line"] = f"FAILED ({inner})"

    matches = list(HEADER_RE.finditer(output))

    for i, match in enumerate(matches):
        test_name = match.group(1)
        class_path = match.group(2)
        parts = class_path.split(".")
        class_name = parts[-2] if len(parts) >= 2 else class_path

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(output)
        block = output[start:end]

        entry = {
            "name": test_name,
            "class": class_name,
            "full": class_path,
        }

        if re.search(r'\bok\b', block):
            results["passed_tests"].append(entry)
        elif re.search(r'\bFAIL\b', block):
            results["failed_tests"].append(entry)
        elif re.search(r'\bERROR\b', block):
            results["error_tests"].append(entry)
        elif results["overall"] == "PASSED":
            results["passed_tests"].append(entry)

    if results["total"] == 0:
        results["total"] = (
            len(results["passed_tests"])
            + len(results["failed_tests"])
            + len(results["error_tests"])
        )

    return results


# ─────────────────────────────────────────────────────────────────────────────
# 3. PDF constants and styles
# ─────────────────────────────────────────────────────────────────────────────

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm

PASS_GREEN = colors.HexColor("#1a7a3e")
FAIL_RED = colors.HexColor("#c0392b")
LIGHT_GREY = colors.HexColor("#f2f2f2")
MID_GREY = colors.HexColor("#cccccc")
DARK_GREY = colors.HexColor("#444444")
BRAND_BLUE = colors.HexColor("#1a3a5c")


def build_styles():
    base = getSampleStyleSheet()

    return {
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Title"],
            fontSize=26,
            textColor=BRAND_BLUE,
            spaceAfter=6,
            leading=32,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            parent=base["Normal"],
            fontSize=12,
            textColor=DARK_GREY,
            spaceAfter=4,
            alignment=TA_CENTER,
        ),
        "section_heading": ParagraphStyle(
            "section_heading",
            parent=base["Heading1"],
            fontSize=13,
            textColor=BRAND_BLUE,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "mono": ParagraphStyle(
            "mono",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=7,
            textColor=DARK_GREY,
            leading=10,
            leftIndent=4,
        ),
        "normal": base["Normal"],
        "meta_right": ParagraphStyle(
            "meta_right",
            parent=base["Normal"],
            fontSize=8,
            textColor=DARK_GREY,
            alignment=TA_RIGHT,
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. PDF components
# ─────────────────────────────────────────────────────────────────────────────

def stat_box_table(total, passed, failed, errors):
    col_w = (PAGE_W - 2 * MARGIN) / 4

    data = [[
        f"TOTAL\n{total}",
        f"PASSED\n{passed}",
        f"FAILED\n{failed}",
        f"ERRORS\n{errors}",
    ]]

    table = Table(data, colWidths=[col_w] * 4, rowHeights=[55])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 16),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), BRAND_BLUE),
        ("TEXTCOLOR", (0, 0), (0, 0), colors.white),
        ("TEXTCOLOR", (1, 0), (1, 0), colors.HexColor("#a8f0c6")),
        ("TEXTCOLOR", (2, 0), (2, 0),
         colors.HexColor("#f9b8b8") if failed else colors.HexColor("#a8f0c6")),
        ("TEXTCOLOR", (3, 0), (3, 0),
         colors.HexColor("#f9b8b8") if errors else colors.HexColor("#a8f0c6")),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("GRID", (0, 0), (-1, -1), 2, colors.white),
    ]))

    return table


def results_table(passed, failed, errors):
    all_tests = (
        [(test, "PASS") for test in passed]
        + [(test, "FAIL") for test in failed]
        + [(test, "ERROR") for test in errors]
    )

    all_tests.sort(key=lambda item: (item[0]["class"], item[0]["name"]))

    rows = [["#", "Test Class", "Test Name", "Result"]]

    for index, (test, status) in enumerate(all_tests, 1):
        rows.append([
            str(index),
            test["class"],
            test["name"],
            status,
        ])

    col_w = [10 * mm, 52 * mm, 90 * mm, 18 * mm]

    table = Table(rows, colWidths=col_w, repeatRows=1)

    commands = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ("GRID", (0, 0), (-1, -1), 0.5, MID_GREY),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (3, 0), (3, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ]

    for row_index, (_, status) in enumerate(all_tests, 1):
        colour = PASS_GREEN if status == "PASS" else FAIL_RED
        commands += [
            ("TEXTCOLOR", (3, row_index), (3, row_index), colour),
            ("FONTNAME", (3, row_index), (3, row_index), "Helvetica-Bold"),
        ]

    table.setStyle(TableStyle(commands))
    return table


def coverage_table(passed, failed, errors):
    counts = {}

    for test in passed:
        counts.setdefault(test["class"], {"pass": 0, "fail": 0})
        counts[test["class"]]["pass"] += 1

    for test in failed + errors:
        counts.setdefault(test["class"], {"pass": 0, "fail": 0})
        counts[test["class"]]["fail"] += 1

    rows = [["Test Class", "Passed", "Failed", "Total", "Status"]]

    for class_name, count in sorted(counts.items()):
        total = count["pass"] + count["fail"]
        status = "PASS" if count["fail"] == 0 else "FAIL"

        rows.append([
            class_name,
            str(count["pass"]),
            str(count["fail"]),
            str(total),
            status,
        ])

    col_w = [90 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm]

    table = Table(rows, colWidths=col_w, repeatRows=1)

    commands = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ("GRID", (0, 0), (-1, -1), 0.5, MID_GREY),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]

    for row_index, row in enumerate(rows[1:], 1):
        colour = PASS_GREEN if row[4] == "PASS" else FAIL_RED
        commands += [
            ("TEXTCOLOR", (4, row_index), (4, row_index), colour),
            ("FONTNAME", (4, row_index), (4, row_index), "Helvetica-Bold"),
        ]

    table.setStyle(TableStyle(commands))
    return table


def _safe(text):
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Generate PDF
# ─────────────────────────────────────────────────────────────────────────────

def generate_pdf(output_path, raw_output, parsed):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title="CyberComply Backend Integration Test Report",
    )

    styles = build_styles()
    story = []

    now_str = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")

    passed_count = len(parsed["passed_tests"])
    failed_count = len(parsed["failed_tests"])
    error_count = len(parsed["error_tests"])
    total = parsed["total"]

    is_pass = parsed["overall"] == "PASSED"

    verdict_text = (
        "ALL TESTS PASSED"
        if is_pass
        else f"TEST RUN FAILED — {failed_count + error_count} issue(s)"
    )
    verdict_colour = PASS_GREEN if is_pass else FAIL_RED

    story += [
        Spacer(1, 6 * mm),
        Paragraph("CyberComply", styles["cover_title"]),
        Paragraph("Backend Test Report — Integration Tests", styles["cover_sub"]),
        Paragraph(
            f"Generated: {now_str}  |  Module: core.tests_integration",
            styles["cover_sub"],
        ),
        Spacer(1, 4 * mm),
        HRFlowable(width="100%", thickness=2, color=BRAND_BLUE),
        Spacer(1, 4 * mm),
        Paragraph(
            verdict_text,
            ParagraphStyle(
                "verdict",
                parent=styles["normal"],
                fontSize=14,
                fontName="Helvetica-Bold",
                textColor=verdict_colour,
                alignment=TA_CENTER,
                spaceAfter=6,
            ),
        ),
        Spacer(1, 3 * mm),
        stat_box_table(total, passed_count, failed_count, error_count),
        Spacer(1, 2 * mm),
        Paragraph(f"Completed in {parsed['run_time']}", styles["meta_right"]),
        Spacer(1, 6 * mm),
    ]

    story += [
        Paragraph("Test Results", styles["section_heading"]),
        HRFlowable(width="100%", thickness=0.5, color=MID_GREY),
        Spacer(1, 2 * mm),
        results_table(
            parsed["passed_tests"],
            parsed["failed_tests"],
            parsed["error_tests"],
        ),
        Spacer(1, 6 * mm),
    ]

    story += [
        Paragraph("Coverage by Test Class", styles["section_heading"]),
        HRFlowable(width="100%", thickness=0.5, color=MID_GREY),
        Spacer(1, 2 * mm),
        coverage_table(
            parsed["passed_tests"],
            parsed["failed_tests"],
            parsed["error_tests"],
        ),
        Spacer(1, 6 * mm),
    ]

    story.append(PageBreak())

    story += [
        Paragraph("Full Test Output", styles["section_heading"]),
        HRFlowable(width="100%", thickness=0.5, color=MID_GREY),
        Spacer(1, 2 * mm),
    ]

    for line in raw_output.splitlines():
        stripped = line.strip()

        if stripped.startswith("{") and '"path"' in stripped:
            continue

        story.append(Paragraph(_safe(stripped) or "&nbsp;", styles["mono"]))

    doc.build(story)

    print(f"\nPDF report saved: {output_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"integration_test_report_{timestamp}.pdf",
    )

    raw_output, return_code = run_tests()
    parsed = parse_output(raw_output)

    print("\n--- Parse summary ---")
    print(f"Total:   {parsed['total']}")
    print(f"Passed:  {len(parsed['passed_tests'])}")
    print(f"Failed:  {len(parsed['failed_tests'])}")
    print(f"Errors:  {len(parsed['error_tests'])}")
    print(f"Overall: {parsed['overall']}")

    generate_pdf(output_path, raw_output, parsed)

    sys.exit(return_code)