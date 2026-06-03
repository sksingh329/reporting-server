"""
Custom HTML reporter for pytest-api-core.

Generates a single self-contained HTML file (no external CDN dependencies)
with:
  - Summary card: total / passed / failed / error / skipped counts + duration
  - SVG donut chart
  - Filterable, sortable results table
  - Expandable rows: stdout, request details, response details, failure traceback
  - Pass/fail badge per test
  - Dark/light mode toggle
"""
from __future__ import annotations

import datetime
import html
import json
import os
import traceback
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class _TestRecord:
    __slots__ = (
        "node_id",
        "name",
        "outcome",         # "passed" | "failed" | "error" | "skipped"
        "duration",        # seconds
        "stdout",
        "stderr",
        "longrepr",        # failure text
        "request_info",    # dict captured from APIResponse log
        "response_info",   # dict captured from APIResponse log
        "markers",
    )

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self.name = node_id.split("::")[-1]
        self.outcome = "unknown"
        self.duration = 0.0
        self.stdout = ""
        self.stderr = ""
        self.longrepr = ""
        self.request_info: dict[str, Any] = {}
        self.response_info: dict[str, Any] = {}
        self.markers: list[str] = []


# ---------------------------------------------------------------------------
# Plugin hooks
# ---------------------------------------------------------------------------


class HTMLReporter:
    """pytest plugin that captures results and writes an HTML report on finish."""

    def __init__(self, report_path: str) -> None:
        self._path = Path(report_path)
        self._records: dict[str, _TestRecord] = {}
        self._start_time: datetime.datetime = datetime.datetime.now()
        self._total_duration = 0.0

    # -- collection ----------------------------------------------------------

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        # Pre-register every collected item so the table order is stable
        for item in session.items:
            rec = _TestRecord(item.nodeid)
            rec.markers = [m.name for m in item.iter_markers()]
            self._records[item.nodeid] = rec

    # -- per-test result capture ---------------------------------------------

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        node_id = report.nodeid
        if node_id not in self._records:
            self._records[node_id] = _TestRecord(node_id)

        rec = self._records[node_id]

        if report.when == "call" or (report.when == "setup" and report.failed):
            rec.duration = report.duration
            self._total_duration += report.duration

            if report.passed:
                rec.outcome = "passed"
            elif report.failed:
                rec.outcome = "failed" if report.when == "call" else "error"
            elif report.skipped:
                rec.outcome = "skipped"

            # Capture printed output
            if report.capstdout:
                rec.stdout = report.capstdout
            if report.capstderr:
                rec.stderr = report.capstderr

            # Capture failure text
            if report.longrepr:
                rec.longrepr = str(report.longrepr)

        elif report.when == "setup" and report.skipped:
            rec.outcome = "skipped"
            if report.longrepr:
                rec.longrepr = str(report.longrepr)

    # -- session finish — write report ----------------------------------------

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        html_content = _render_report(
            records=list(self._records.values()),
            start_time=self._start_time,
            total_duration=self._total_duration,
        )
        self._path.write_text(html_content, encoding="utf-8")
        # Print path relative to cwd for readability
        try:
            rel = self._path.relative_to(Path.cwd())
        except ValueError:
            rel = self._path
        print(f"\n  📄  API HTML report: {rel}\n")


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_report(
    records: list[_TestRecord],
    start_time: datetime.datetime,
    total_duration: float,
) -> str:
    counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0, "unknown": 0}
    for rec in records:
        counts[rec.outcome] = counts.get(rec.outcome, 0) + 1

    total = len(records)
    generated_at = start_time.strftime("%Y-%m-%d %H:%M:%S")
    duration_str = f"{total_duration:.2f}s"

    rows_html = "".join(_render_row(i, rec) for i, rec in enumerate(records))
    donut_svg = _donut_svg(counts, total)

    return _HTML_TEMPLATE.format(
        generated_at=html.escape(generated_at),
        duration=html.escape(duration_str),
        total=total,
        passed=counts["passed"],
        failed=counts["failed"],
        error=counts["error"],
        skipped=counts["skipped"],
        donut_svg=donut_svg,
        rows=rows_html,
        pass_rate=f"{(counts['passed'] / total * 100):.1f}" if total else "0.0",
    )


def _render_row(idx: int, rec: _TestRecord) -> str:
    badge_class = {
        "passed": "badge-pass",
        "failed": "badge-fail",
        "error": "badge-error",
        "skipped": "badge-skip",
    }.get(rec.outcome, "badge-unknown")

    details_id = f"detail-{idx}"
    has_detail = bool(rec.stdout or rec.stderr or rec.longrepr)
    toggle = f'onclick="toggleDetail(\'{details_id}\')" style="cursor:pointer"' if has_detail else ""

    stdout_block = _code_block("stdout", rec.stdout) if rec.stdout else ""
    stderr_block = _code_block("stderr", rec.stderr) if rec.stderr else ""
    longrepr_block = _code_block("failure", rec.longrepr) if rec.longrepr else ""

    detail_row = ""
    if has_detail:
        detail_row = (
            f'<tr id="{details_id}" class="detail-row" style="display:none">'
            f'<td colspan="4"><div class="detail-body">'
            f"{stdout_block}{stderr_block}{longrepr_block}"
            f"</div></td></tr>"
        )

    markers_html = "".join(
        f'<span class="marker">{html.escape(m)}</span>' for m in rec.markers
    )

    return (
        f'<tr class="result-row {rec.outcome}" {toggle} data-outcome="{rec.outcome}">'
        f'<td><span class="badge {badge_class}">{rec.outcome.upper()}</span></td>'
        f'<td class="test-name">{html.escape(rec.node_id)}{markers_html}</td>'
        f'<td class="duration">{rec.duration:.3f}s</td>'
        f'<td>{html.escape(rec.name)}</td>'
        f"</tr>"
        f"{detail_row}"
    )


def _code_block(label: str, content: str) -> str:
    return (
        f'<div class="detail-section">'
        f'<div class="detail-label">{html.escape(label.upper())}</div>'
        f'<pre class="code-block">{html.escape(content)}</pre>'
        f"</div>"
    )


def _donut_svg(counts: dict[str, int], total: int) -> str:
    if total == 0:
        return '<svg width="140" height="140"><circle cx="70" cy="70" r="55" fill="none" stroke="#ccc" stroke-width="20"/></svg>'

    colors = {"passed": "#22c55e", "failed": "#ef4444", "error": "#f97316", "skipped": "#94a3b8"}
    r = 55
    cx = cy = 70
    circumference = 2 * 3.14159 * r
    segments: list[str] = []
    offset = 0.0

    for outcome, color in colors.items():
        count = counts.get(outcome, 0)
        if count == 0:
            continue
        fraction = count / total
        dash = fraction * circumference
        segments.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" '
            f'stroke-width="20" stroke-dasharray="{dash:.2f} {circumference:.2f}" '
            f'stroke-dashoffset="-{offset:.2f}" transform="rotate(-90 {cx} {cy})"/>'
        )
        offset += dash

    inner_text = f'<text x="{cx}" y="{cy+5}" text-anchor="middle" font-size="18" font-weight="bold" fill="currentColor">{total}</text>'
    return f'<svg width="140" height="140">{"".join(segments)}{inner_text}</svg>'


# ---------------------------------------------------------------------------
# HTML template (self-contained — inline CSS + JS, no external deps)
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>API Test Report</title>
<style>
:root {{
  --bg: #f8fafc; --surface: #ffffff; --border: #e2e8f0;
  --text: #1e293b; --text-muted: #64748b;
  --pass: #22c55e; --fail: #ef4444; --error: #f97316; --skip: #94a3b8;
  --code-bg: #1e293b; --code-text: #e2e8f0;
  --shadow: 0 1px 3px rgba(0,0,0,.1);
}}
[data-theme="dark"] {{
  --bg: #0f172a; --surface: #1e293b; --border: #334155;
  --text: #f1f5f9; --text-muted: #94a3b8;
  --code-bg: #0f172a; --code-text: #e2e8f0;
  --shadow: 0 1px 3px rgba(0,0,0,.4);
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.5; }}
header {{ background: var(--surface); border-bottom: 1px solid var(--border);
          padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; }}
header h1 {{ font-size: 20px; font-weight: 700; letter-spacing: -.3px; }}
header small {{ color: var(--text-muted); margin-left: 10px; font-weight: 400; font-size: 12px; }}
.theme-btn {{ background: none; border: 1px solid var(--border); border-radius: 6px;
              padding: 6px 12px; cursor: pointer; color: var(--text); font-size: 13px; }}
.main {{ max-width: 1280px; margin: 24px auto; padding: 0 24px; }}
.summary-grid {{ display: grid; grid-template-columns: auto 1fr; gap: 24px; align-items: center;
                 background: var(--surface); border-radius: 12px; padding: 24px;
                 box-shadow: var(--shadow); margin-bottom: 24px; }}
.donut-wrap {{ display: flex; flex-direction: column; align-items: center; gap: 8px; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; }}
.stat-card {{ background: var(--bg); border-radius: 8px; padding: 14px 16px;
              border: 1px solid var(--border); text-align: center; }}
.stat-card .stat-value {{ font-size: 28px; font-weight: 700; line-height: 1; }}
.stat-card .stat-label {{ font-size: 11px; text-transform: uppercase;
                          letter-spacing: .8px; color: var(--text-muted); margin-top: 4px; }}
.stat-card.pass .stat-value {{ color: var(--pass); }}
.stat-card.fail .stat-value {{ color: var(--fail); }}
.stat-card.error .stat-value {{ color: var(--error); }}
.stat-card.skip .stat-value {{ color: var(--skip); }}
.controls {{ display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }}
.search-box {{ flex: 1; min-width: 200px; padding: 8px 12px; border: 1px solid var(--border);
               border-radius: 6px; background: var(--surface); color: var(--text); font-size: 13px; }}
.filter-btn {{ padding: 7px 16px; border: 1px solid var(--border); border-radius: 6px;
               background: var(--surface); color: var(--text-muted); cursor: pointer;
               font-size: 13px; transition: all .15s; }}
.filter-btn.active {{ background: var(--text); color: var(--bg); border-color: var(--text); }}
table {{ width: 100%; border-collapse: collapse; background: var(--surface);
         border-radius: 12px; overflow: hidden; box-shadow: var(--shadow); }}
thead tr {{ background: var(--bg); border-bottom: 2px solid var(--border); }}
th {{ padding: 10px 14px; text-align: left; font-size: 11px; text-transform: uppercase;
      letter-spacing: .7px; color: var(--text-muted); }}
td {{ padding: 10px 14px; border-bottom: 1px solid var(--border); vertical-align: top; }}
.result-row:hover {{ background: var(--bg); }}
.result-row.failed {{ border-left: 3px solid var(--fail); }}
.result-row.error {{ border-left: 3px solid var(--error); }}
.result-row.passed {{ border-left: 3px solid var(--pass); }}
.result-row.skipped {{ border-left: 3px solid var(--skip); }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px;
          font-size: 11px; font-weight: 700; letter-spacing: .5px; }}
.badge-pass {{ background: #dcfce7; color: #15803d; }}
.badge-fail {{ background: #fee2e2; color: #dc2626; }}
.badge-error {{ background: #ffedd5; color: #c2410c; }}
.badge-skip {{ background: #f1f5f9; color: #475569; }}
.test-name {{ font-family: "SF Mono", "Fira Code", monospace; font-size: 12px; max-width: 600px;
              overflow-wrap: break-word; }}
.duration {{ color: var(--text-muted); font-variant-numeric: tabular-nums; white-space: nowrap; }}
.marker {{ display: inline-block; margin-left: 6px; padding: 1px 6px; border-radius: 10px;
           font-size: 10px; background: #ede9fe; color: #6d28d9; }}
.detail-row td {{ padding: 0; }}
.detail-body {{ background: var(--code-bg); padding: 16px; }}
.detail-section {{ margin-bottom: 12px; }}
.detail-label {{ font-size: 10px; text-transform: uppercase; letter-spacing: .8px;
                 color: #64748b; margin-bottom: 6px; font-weight: 600; }}
.code-block {{ font-family: "SF Mono", "Fira Code", monospace; font-size: 12px;
               color: var(--code-text); white-space: pre-wrap; overflow-wrap: break-word;
               max-height: 400px; overflow-y: auto; }}
footer {{ text-align: center; padding: 24px; color: var(--text-muted); font-size: 12px; }}
</style>
</head>
<body>
<header>
  <div>
    <h1>API Test Report <small>Generated {generated_at} &nbsp;|&nbsp; Duration: {duration}</small></h1>
  </div>
  <button class="theme-btn" onclick="toggleTheme()">🌙 Dark</button>
</header>

<div class="main">
  <div class="summary-grid">
    <div class="donut-wrap">
      {donut_svg}
      <div style="font-size:12px;color:var(--text-muted)">Pass rate: <strong>{pass_rate}%</strong></div>
    </div>
    <div class="stats-grid">
      <div class="stat-card"><div class="stat-value">{total}</div><div class="stat-label">Total</div></div>
      <div class="stat-card pass"><div class="stat-value">{passed}</div><div class="stat-label">Passed</div></div>
      <div class="stat-card fail"><div class="stat-value">{failed}</div><div class="stat-label">Failed</div></div>
      <div class="stat-card error"><div class="stat-value">{error}</div><div class="stat-label">Errors</div></div>
      <div class="stat-card skip"><div class="stat-value">{skipped}</div><div class="stat-label">Skipped</div></div>
    </div>
  </div>

  <div class="controls">
    <input class="search-box" type="text" placeholder="Search tests…" oninput="filterTable()" id="searchBox"/>
    <button class="filter-btn active" onclick="setFilter('all', this)">All</button>
    <button class="filter-btn" onclick="setFilter('passed', this)">Passed</button>
    <button class="filter-btn" onclick="setFilter('failed', this)">Failed</button>
    <button class="filter-btn" onclick="setFilter('error', this)">Error</button>
    <button class="filter-btn" onclick="setFilter('skipped', this)">Skipped</button>
  </div>

  <table id="resultsTable">
    <thead><tr>
      <th style="width:90px">Status</th>
      <th>Test ID</th>
      <th style="width:90px">Duration</th>
      <th>Name</th>
    </tr></thead>
    <tbody id="tableBody">
      {rows}
    </tbody>
  </table>
</div>

<footer>pytest-api-core &mdash; API Test Report</footer>

<script>
var currentFilter = 'all';

function toggleDetail(id) {{
  var el = document.getElementById(id);
  if (el) el.style.display = el.style.display === 'none' ? 'table-row' : 'none';
}}

function setFilter(outcome, btn) {{
  currentFilter = outcome;
  document.querySelectorAll('.filter-btn').forEach(function(b) {{ b.classList.remove('active'); }});
  btn.classList.add('active');
  applyFilters();
}}

function filterTable() {{ applyFilters(); }}

function applyFilters() {{
  var query = document.getElementById('searchBox').value.toLowerCase();
  document.querySelectorAll('#tableBody .result-row').forEach(function(row) {{
    var matchOutcome = currentFilter === 'all' || row.dataset.outcome === currentFilter;
    var matchSearch = !query || row.innerText.toLowerCase().includes(query);
    var show = matchOutcome && matchSearch;
    row.style.display = show ? '' : 'none';
    var detailId = row.getAttribute('onclick');
    if (detailId) {{
      var m = detailId.match(/'([^']+)'/);
      if (m) {{
        var detail = document.getElementById(m[1]);
        if (detail && !show) detail.style.display = 'none';
      }}
    }}
  }});
}}

function toggleTheme() {{
  var html = document.documentElement;
  var isDark = html.getAttribute('data-theme') === 'dark';
  html.setAttribute('data-theme', isDark ? 'light' : 'dark');
  document.querySelector('.theme-btn').textContent = isDark ? '🌙 Dark' : '☀️ Light';
}}
</script>
</body>
</html>
"""
