"""
generate_test_report.py
=======================
Runs the backend test suite and produces a formatted PDF report.

Usage (from the DjangoManager/ directory with venv active):
    python generate_test_report.py
    python generate_test_report.py core.tests_views_auth

Output:
    test_report_<timestamp>.pdf  in the same directory

How parsing works
-----------------
Django --verbosity=2 writes test output to stderr in this format:

    test_name (full.module.ClassName.test_name) ... ok
    test_name (full.module.ClassName.test_name) ... {"path": "..."}\nok

Our request middleware injects a JSON log line on the same line as the
test header, pushing "ok" / "FAIL" / "ERROR" to the NEXT line.
The parser handles both cases with a two-pass approach:
  Pass 1  - collect "test header" lines (contain " ... ")
  Pass 2  - for each header, look at the immediately following non-blank
             line (stripping any JSON) to find ok/FAIL/ERROR
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
# 1. Run the test suite
# ─────────────────────────────────────────────────────────────────────────────

def run_tests(test_module):
    print(f"Running: python manage.py test {test_module} --verbosity=2")
    result = subprocess.run(
        [sys.executable, "manage.py", "test", test_module, "--verbosity=2"],
        capture_output=True,
        text=True,
    )
    # Django writes ALL test output (progress + result) to stderr.
    return result.stderr, result.stdout, result.returncode


# ─────────────────────────────────────────────────────────────────────────────
# 2. Parse test output
# ─────────────────────────────────────────────────────────────────────────────

# Matches the test header line:
#   test_something (core.tests_views_auth.SignupViewTest.test_something) ...
HEADER_RE = re.compile(r'^(test_\w+)\s+\(([^)]+)\)\s+\.\.\.')

# Standalone status word after stripping JSON noise
STATUS_RE = re.compile(r'^(ok|FAIL|ERROR|skipped)', re.IGNORECASE)

# Full-line JSON log injected by request middleware
JSON_LINE_RE = re.compile(r'^\{.*"path".*\}')


def _strip_json(line):
    """Remove JSON middleware log suffix/whole-line from a test output line."""
    stripped = line.strip()
    if JSON_LINE_RE.match(stripped):
        return ""
    # Remove trailing {...} from lines like 'test_foo (...) ... {"path":...}'
    cleaned = re.sub(r'\{[^}]*"path"[^}]*\}.*$', '', stripped).rstrip()
    return cleaned


def parse_output(stderr_output):
    """
    Parses Django --verbosity=2 stderr into structured test result data.
    Returns a dict with parsed counts, test lists, and failure details.
    """
    results = {
        "passed_tests":    [],
        "failed_tests":    [],
        "error_tests":     [],
        "failure_details": [],
        "run_time":        "unknown",
        "total":           0,
        "failures":        0,
        "errors":          0,
        "summary_line":    "",
        "overall":         "UNKNOWN",
    }

    lines = stderr_output.splitlines()

    # ── Pass 1: find test headers and resolve their status ─────────────────
    for idx, raw_line in enumerate(lines):
        clean = _strip_json(raw_line)
        m     = HEADER_RE.match(clean)
        if not m:
            continue

        test_name  = m.group(1)
        class_path = m.group(2)
        # class_path: "core.tests_views_auth.SignupViewTest.test_name"
        # Extract the class name (second-to-last segment)
        parts      = class_path.split(".")
        class_name = parts[-2] if len(parts) >= 2 else class_path

        # Try to find status on the same line first (no JSON injection)
        same_line_status = re.search(
            r'\.\.\.\s*(ok|FAIL|ERROR|skipped)',
            clean,
            re.IGNORECASE,
        )

        if same_line_status:
            status = same_line_status.group(1).upper()
        else:
            # Status is on the next non-blank / non-JSON line
            status = "UNKNOWN"
            for j in range(idx + 1, min(idx + 4, len(lines))):
                next_clean = _strip_json(lines[j]).strip()
                if not next_clean:
                    continue
                sm = STATUS_RE.match(next_clean)
                if sm:
                    status = sm.group(1).upper()
                break

        entry = {"name": test_name, "class": class_name, "full": class_path}
        if status == "OK":
            results["passed_tests"].append(entry)
        elif status == "FAIL":
            results["failed_tests"].append(entry)
        elif status == "ERROR":
            results["error_tests"].append(entry)

    # ── "Ran N tests in X.XXXs" ────────────────────────────────────────────
    ran_m = re.search(r'Ran (\d+) tests? in ([\d.]+s)', stderr_output)
    if ran_m:
        results["total"]    = int(ran_m.group(1))
        results["run_time"] = ran_m.group(2)

    # ── Overall result ──────────────────────────────────────────────────────
    fail_m = re.search(r'^FAILED\s*\((.+)\)', stderr_output, re.MULTILINE)
    if fail_m:
        inner = fail_m.group(1)
        results["overall"] = "FAILED"
        f = re.search(r'failures=(\d+)', inner)
        e = re.search(r'errors=(\d+)',   inner)
        results["failures"]     = int(f.group(1)) if f else 0
        results["errors"]       = int(e.group(1)) if e else 0
        results["summary_line"] = f"FAILED ({inner})"
    else:
        for line in stderr_output.splitlines():
            if line.strip() == "OK":
                results["overall"]      = "PASSED"
                results["summary_line"] = "OK"
                break

    # ── Failure / error detail blocks (tracebacks) ─────────────────────────
    detail_re = re.compile(
        r'={10,}\n(FAIL|ERROR):\s+(.+?)\n-{10,}\n(.*?)(?=\n={10,}|\Z)',
        re.DOTALL,
    )
    for dm in detail_re.finditer(stderr_output):
        results["failure_details"].append({
            "title": f"{dm.group(1)}: {dm.group(2).strip()}",
            "body":  dm.group(3).strip(),
        })

    # ── Fallback total ─────────────────────────────────────────────────────
    if results["total"] == 0:
        results["total"] = (
            len(results["passed_tests"]) +
            len(results["failed_tests"]) +
            len(results["error_tests"])
        )

    return results


# ─────────────────────────────────────────────────────────────────────────────
# 3. PDF constants and styles
# ─────────────────────────────────────────────────────────────────────────────

PAGE_W, PAGE_H = A4
MARGIN     = 18 * mm
PASS_GREEN = colors.HexColor("#1a7a3e")
FAIL_RED   = colors.HexColor("#c0392b")
LIGHT_GREY = colors.HexColor("#f2f2f2")
MID_GREY   = colors.HexColor("#cccccc")
DARK_GREY  = colors.HexColor("#444444")
BRAND_BLUE = colors.HexColor("#1a3a5c")


def build_styles():
    base   = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title", parent=base["Title"],
            fontSize=26, textColor=BRAND_BLUE,
            spaceAfter=6, leading=32,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", parent=base["Normal"],
            fontSize=12, textColor=DARK_GREY,
            spaceAfter=4, alignment=TA_CENTER,
        ),
        "section_heading": ParagraphStyle(
            "section_heading", parent=base["Heading1"],
            fontSize=13, textColor=BRAND_BLUE,
            spaceBefore=10, spaceAfter=4,
        ),
        "mono": ParagraphStyle(
            "mono", parent=base["Normal"],
            fontName="Courier", fontSize=7,
            textColor=DARK_GREY, leading=10, leftIndent=4,
        ),
        "detail_title": ParagraphStyle(
            "detail_title", parent=base["Normal"],
            fontSize=9, textColor=FAIL_RED,
            fontName="Helvetica-Bold",
            spaceBefore=8, spaceAfter=2,
        ),
        "normal":     base["Normal"],
        "meta_right": ParagraphStyle(
            "meta_right", parent=base["Normal"],
            fontSize=8, textColor=DARK_GREY, alignment=TA_RIGHT,
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. PDF components
# ─────────────────────────────────────────────────────────────────────────────

def stat_box_table(total, passed, failed, errors):
    col_w = (PAGE_W - 2 * MARGIN) / 4
    data  = [[
        f"TOTAL\n{total}",
        f"PASSED\n{passed}",
        f"FAILED\n{failed}",
        f"ERRORS\n{errors}",
    ]]
    t = Table(data, colWidths=[col_w] * 4, rowHeights=[55])
    t.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 16),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND",    (0, 0), (-1, -1), BRAND_BLUE),
        ("TEXTCOLOR",     (0, 0), (0,  0),  colors.white),
        ("TEXTCOLOR",     (1, 0), (1,  0),  colors.HexColor("#a8f0c6")),
        ("TEXTCOLOR",     (2, 0), (2,  0),
            colors.HexColor("#f9b8b8") if failed else colors.HexColor("#a8f0c6")),
        ("TEXTCOLOR",     (3, 0), (3,  0),
            colors.HexColor("#f9b8b8") if errors else colors.HexColor("#a8f0c6")),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("GRID",          (0, 0), (-1, -1), 2, colors.white),
    ]))
    return t


def results_table(passed, failed, errors):
    all_tests = (
        [(t, "PASS")  for t in passed] +
        [(t, "FAIL")  for t in failed] +
        [(t, "ERROR") for t in errors]
    )
    all_tests.sort(key=lambda x: (x[0]["class"], x[0]["name"]))

    col_w = [10*mm, 52*mm, 90*mm, 18*mm]
    rows  = [["#", "Test Class", "Test Name", "Result"]]
    for i, (t, status) in enumerate(all_tests, 1):
        rows.append([str(i), t["class"], t["name"], status])

    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    cmds = [
        ("FONTNAME",       (0, 0), (-1,  0), "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1,  0), 9),
        ("BACKGROUND",     (0, 0), (-1,  0), BRAND_BLUE),
        ("TEXTCOLOR",      (0, 0), (-1,  0), colors.white),
        ("FONTNAME",       (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",       (0, 1), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ("GRID",           (0, 0), (-1, -1), 0.5, MID_GREY),
        ("ALIGN",          (0, 0), (0,  -1), "CENTER"),
        ("ALIGN",          (3, 0), (3,  -1), "CENTER"),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",     (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
        ("LEFTPADDING",    (0, 0), (-1, -1), 5),
    ]
    for i, (_, status) in enumerate(all_tests, 1):
        c = PASS_GREEN if status == "PASS" else FAIL_RED
        cmds += [
            ("TEXTCOLOR", (3, i), (3, i), c),
            ("FONTNAME",  (3, i), (3, i), "Helvetica-Bold"),
        ]
    tbl.setStyle(TableStyle(cmds))
    return tbl


def coverage_table(passed, failed, errors):
    counts = {}
    for t in passed:
        counts.setdefault(t["class"], {"pass": 0, "fail": 0})
        counts[t["class"]]["pass"] += 1
    for t in failed + errors:
        counts.setdefault(t["class"], {"pass": 0, "fail": 0})
        counts[t["class"]]["fail"] += 1

    col_w = [90*mm, 22*mm, 22*mm, 22*mm, 22*mm]
    rows  = [["Test Class", "Passed", "Failed", "Total", "Status"]]
    for cls, c in sorted(counts.items()):
        total  = c["pass"] + c["fail"]
        status = "PASS" if c["fail"] == 0 else "FAIL"
        rows.append([cls, str(c["pass"]), str(c["fail"]), str(total), status])

    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    cmds = [
        ("FONTNAME",       (0, 0), (-1,  0), "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1), 9),
        ("BACKGROUND",     (0, 0), (-1,  0), BRAND_BLUE),
        ("TEXTCOLOR",      (0, 0), (-1,  0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ("GRID",           (0, 0), (-1, -1), 0.5, MID_GREY),
        ("ALIGN",          (1, 0), (-1, -1), "CENTER"),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",     (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
    ]
    for i, row in enumerate(rows[1:], 1):
        c = PASS_GREEN if row[4] == "PASS" else FAIL_RED
        cmds += [
            ("TEXTCOLOR", (4, i), (4, i), c),
            ("FONTNAME",  (4, i), (4, i), "Helvetica-Bold"),
        ]
    tbl.setStyle(TableStyle(cmds))
    return tbl


# ─────────────────────────────────────────────────────────────────────────────
# 5. Build PDF
# ─────────────────────────────────────────────────────────────────────────────

def _safe(text):
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def generate_pdf(output_path, stderr_output, parsed, test_module):
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN,
        title="CyberComply Backend Test Report",
    )

    styles     = build_styles()
    story      = []
    now_str    = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    passed_cnt = len(parsed["passed_tests"])
    failed_cnt = len(parsed["failed_tests"])
    error_cnt  = len(parsed["error_tests"])
    total      = parsed["total"]
    is_pass    = parsed["overall"] == "PASSED"

    verdict_txt = ("ALL TESTS PASSED"
                   if is_pass
                   else f"TEST RUN FAILED  —  {failed_cnt + error_cnt} issue(s)")
    verdict_col = PASS_GREEN if is_pass else FAIL_RED

    # ── Header ─────────────────────────────────────────────────────────────
    story += [
        Spacer(1, 6*mm),
        Paragraph("CyberComply", styles["cover_title"]),
        Paragraph("Backend Test Report — Group 1: Authentication", styles["cover_sub"]),
        Paragraph(f"Generated: {now_str}  |  Module: {test_module}", styles["cover_sub"]),
        Spacer(1, 4*mm),
        HRFlowable(width="100%", thickness=2, color=BRAND_BLUE),
        Spacer(1, 4*mm),
        Paragraph(verdict_txt, ParagraphStyle(
            "v", parent=styles["normal"],
            fontSize=14, fontName="Helvetica-Bold",
            textColor=verdict_col, alignment=TA_CENTER, spaceAfter=6,
        )),
        Spacer(1, 3*mm),
        stat_box_table(total, passed_cnt, failed_cnt, error_cnt),
        Spacer(1, 2*mm),
        Paragraph(f"Completed in {parsed['run_time']}", styles["meta_right"]),
        Spacer(1, 6*mm),
    ]

    # ── Results table ───────────────────────────────────────────────────────
    story += [
        Paragraph("Test Results", styles["section_heading"]),
        HRFlowable(width="100%", thickness=0.5, color=MID_GREY),
        Spacer(1, 2*mm),
        results_table(parsed["passed_tests"], parsed["failed_tests"], parsed["error_tests"]),
        Spacer(1, 6*mm),
    ]

    # ── Coverage by class ───────────────────────────────────────────────────
    story += [
        Paragraph("Coverage by Test Class", styles["section_heading"]),
        HRFlowable(width="100%", thickness=0.5, color=MID_GREY),
        Spacer(1, 2*mm),
        coverage_table(parsed["passed_tests"], parsed["failed_tests"], parsed["error_tests"]),
        Spacer(1, 6*mm),
    ]

    # ── Failure details ─────────────────────────────────────────────────────
    if parsed["failure_details"]:
        story.append(PageBreak())
        story += [
            Paragraph("Failure Details", styles["section_heading"]),
            HRFlowable(width="100%", thickness=0.5, color=MID_GREY),
        ]
        for detail in parsed["failure_details"]:
            story.append(Spacer(1, 3*mm))
            story.append(Paragraph(detail["title"], styles["detail_title"]))
            for line in detail["body"].splitlines():
                story.append(Paragraph(_safe(line) or "&nbsp;", styles["mono"]))
        story.append(Spacer(1, 4*mm))

    # ── Full raw output ─────────────────────────────────────────────────────
    story.append(PageBreak())
    story += [
        Paragraph("Full Test Output", styles["section_heading"]),
        HRFlowable(width="100%", thickness=0.5, color=MID_GREY),
        Spacer(1, 2*mm),
    ]
    for line in stderr_output.splitlines():
        stripped = line.strip()
        # Skip JSON middleware log lines — they clutter the raw output
        if stripped.startswith("{") and '"path"' in stripped:
            continue
        story.append(Paragraph(_safe(stripped) or "&nbsp;", styles["mono"]))

    doc.build(story)
    print(f"\nPDF report saved: {output_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_module = sys.argv[1] if len(sys.argv) > 1 else "core.tests_views_auth"
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"test_report_{timestamp}.pdf",
    )

    stderr_output, stdout_output, returncode = run_tests(test_module)
    parsed = parse_output(stderr_output)

    print("\n--- Parse summary ---")
    print(f"Total:   {parsed['total']}")
    print(f"Passed:  {len(parsed['passed_tests'])}")
    print(f"Failed:  {len(parsed['failed_tests'])}")
    print(f"Errors:  {len(parsed['error_tests'])}")
    print(f"Overall: {parsed['overall']}")

    generate_pdf(output_path, stderr_output, parsed, test_module)
    sys.exit(returncode)