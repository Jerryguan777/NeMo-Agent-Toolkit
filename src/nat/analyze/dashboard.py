# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Failure dashboard - generates interactive HTML reports with fingerprint grouping."""

import json
import logging
from datetime import datetime
from pathlib import Path

from nat.analyze.models import AnalysisReport

logger = logging.getLogger(__name__)


class FailureDashboard:
    """Generate interactive failure analysis HTML dashboard."""

    def __init__(self, report: AnalysisReport) -> None:
        self.report = report

    def generate_html_report(self, output_path: Path) -> None:
        """Generate self-contained interactive HTML report."""
        html = self._build_html()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(html)
        logger.info(f"Generated HTML report: {output_path}")

    def generate_json_report(self, output_path: Path) -> None:
        """Save the analysis report as JSON."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(self.report.model_dump_json(indent=2))
        logger.info(f"Generated JSON report: {output_path}")

    def _build_report_data(self) -> str:
        """Serialize the full report data as JSON for embedding in HTML."""
        data = {
            "total_tasks": self.report.total_tasks,
            "total_failures": self.report.total_failures,
            "model_used": self.report.model_used,
            "analysis_timestamp": self.report.analysis_timestamp,
            "fingerprint_groups": [g.model_dump() for g in self.report.fingerprint_groups],
            "task_analyses": [],
        }

        for t in self.report.task_analyses:
            task_data = {
                "task_id": t.task_id,
                "question": t.question,
                "expected_answer": t.expected_answer,
                "actual_answer": t.actual_answer,
                "fingerprint": t.fingerprint,
                "group_name": t.group_name,
                "root_cause": t.root_cause,
                "root_cause_step_indices": t.root_cause_step_indices,
                "improvement_suggestions": t.improvement_suggestions,
                "confidence": t.confidence,
                "step_summaries": [s.model_dump() for s in t.step_summaries],
                "step_details": [self._truncate_detail(d) for d in t.step_details],
            }
            data["task_analyses"].append(task_data)

        return json.dumps(data, ensure_ascii=False)

    def _build_html(self) -> str:
        """Build the complete HTML dashboard."""
        report_json = self._build_report_data()
        timestamp = self.report.analysis_timestamp or datetime.now().isoformat()

        # Use placeholder replacement to avoid f-string brace escaping in CSS/JS
        return (
            _HTML_TEMPLATE
            .replace("%%REPORT_DATA%%", report_json)
            .replace("%%TIMESTAMP%%", self._escape_html(timestamp))
            .replace("%%MODEL_USED%%", self._escape_html(self.report.model_used))
        )

    @staticmethod
    def _truncate_detail(d) -> dict:
        """Truncate step detail fields for HTML embedding (keep full data in JSON only)."""
        MAX = 1000
        data = d.model_dump()
        for field in ("full_input", "full_output"):
            val = data.get(field, "")
            if val and len(val) > MAX:
                data[field] = val[:MAX] + "... (truncated)"
        return data

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agent Failure Analysis Report</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --bg:#0C0E14; --surface:#13161F; --surface-hover:#1A1D28;
  --border:#252836; --border-active:#3D4158;
  --text:#E2E4ED; --text-muted:#8B8FA3; --text-dim:#565A6E;
  --accent:#818CF8; --accent-dim:#4F46E5;
  --success:#47CD89; --error:#F97066; --warning:#F79009;
  --mono:'JetBrains Mono','Fira Code',monospace;
  --sans:'DM Sans','Segoe UI',system-ui,sans-serif;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:var(--sans);background:var(--bg);color:var(--text);min-height:100vh;display:flex;flex-direction:column}

/* Header */
.hdr{padding:18px 28px;border-bottom:1px solid var(--border);display:flex;align-items:center;
  background:rgba(19,22,31,.9);backdrop-filter:blur(12px);position:sticky;top:0;z-index:100}
.hdr-brand{display:flex;align-items:center;gap:14px}
.hdr-icon{width:32px;height:32px;border-radius:8px;background:linear-gradient(135deg,var(--accent),var(--accent-dim));
  display:flex;align-items:center;justify-content:center;font-size:16px;color:#fff}
.hdr-title{font-size:16px;font-weight:700;letter-spacing:-.01em}
.hdr-sub{font-family:var(--mono);font-size:11px;color:var(--text-dim);margin-top:2px}

/* Stats */
.stats{padding:20px 28px;display:flex;gap:16px;flex-wrap:wrap}
.sc{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:20px 24px;flex:1;min-width:140px;position:relative;overflow:hidden}
.sc-bar{position:absolute;top:0;left:0;right:0;height:2px}
.sc-label{font-size:13px;color:var(--text-muted);margin-bottom:8px;letter-spacing:.02em}
.sc-val{font-family:var(--mono);font-size:32px;font-weight:700;line-height:1}
.sc-sub{font-size:12px;color:var(--text-dim);margin-top:6px}

/* Distribution */
.dist{padding:0 28px 20px}
.dist-bar{display:flex;height:10px;border-radius:6px;overflow:hidden;gap:2px;margin-bottom:8px}
.dist-leg{display:flex;flex-wrap:wrap;gap:6px 16px}
.leg-item{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-muted)}
.leg-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}

/* Main layout */
.main{display:flex;flex:1;border-top:1px solid var(--border);overflow:hidden}

/* List panel */
.lp{width:100%;border-right:1px solid var(--border);display:flex;flex-direction:column;
  transition:width .3s ease;min-width:0}
.lp.shrink{width:42%}
.ctrls{padding:12px 20px;border-bottom:1px solid var(--border);display:flex;gap:10px;
  align-items:center;flex-wrap:wrap;background:rgba(19,22,31,.6)}
.ci,.cs{font-family:var(--mono);font-size:12px;color:var(--text);background:var(--surface);
  border:1px solid var(--border);border-radius:6px;padding:6px 10px;outline:none}
.ci{flex:1;min-width:180px}.cs{cursor:pointer}
.cs option{background:var(--surface);color:var(--text)}
.tc{padding:8px 20px;font-family:var(--mono);font-size:11px;color:var(--text-dim);
  border-bottom:1px solid var(--border)}
.tl{flex:1;overflow-y:auto}

/* Task row */
.tr{display:flex;align-items:center;gap:12px;padding:14px 20px;border-bottom:1px solid var(--border);
  cursor:pointer;transition:all .15s;border-left:3px solid transparent}
.tr:hover{background:rgba(26,29,40,.5)}
.tr.active{background:var(--surface-hover);border-left-color:var(--accent)}
.sd{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.ti{flex:1;min-width:0}
.tm{display:flex;align-items:center;gap:8px;margin-bottom:4px}
.gb{font-family:var(--mono);font-size:11px;padding:1px 6px;border-radius:3px;
  letter-spacing:.03em;white-space:nowrap;max-width:180px;overflow:hidden;text-overflow:ellipsis}
.tid{font-family:var(--mono);font-size:11px;color:var(--text-dim)}
.qt{font-size:13px;line-height:1.4;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.trt{text-align:right;flex-shrink:0}
.scl{font-family:var(--mono);font-size:12px;color:var(--text-muted)}

/* Detail panel */
.dp{flex:1;overflow-y:auto;min-width:0;background:rgba(19,22,31,.3);display:none}
.dp.active{display:block}
.dh{padding:20px 24px;border-bottom:1px solid var(--border);background:var(--surface)}
.dh-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.dh-left{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.fpb{font-family:var(--mono);font-size:12px;padding:3px 10px;border-radius:5px;font-weight:600}
.cb{font-family:var(--mono);font-size:11px;padding:2px 8px;border-radius:4px}
.close-btn{font-family:var(--mono);font-size:20px;color:var(--text-dim);background:none;
  border:none;cursor:pointer;padding:0 4px;line-height:1}
.close-btn:hover{color:var(--text)}
.dq{font-size:15px;line-height:1.5;margin-bottom:16px}
.ag{display:flex;gap:12px}
.ab{flex:1;padding:10px 14px;border-radius:8px}
.ab.exp{background:rgba(71,205,137,.05);border:1px solid rgba(71,205,137,.15)}
.ab.act{background:rgba(249,112,102,.05);border:1px solid rgba(249,112,102,.15)}
.al{font-family:var(--mono);font-size:10px;margin-bottom:4px;letter-spacing:.06em}
.av{font-family:var(--mono);font-size:14px;font-weight:600;word-break:break-word}

/* Root cause & suggestions */
.rcb{margin:16px 0;padding:14px 18px;border-radius:8px;background:rgba(249,112,102,.06);
  border:1px solid rgba(249,112,102,.2)}
.rct{font-family:var(--mono);font-size:10px;color:var(--error);letter-spacing:.06em;
  margin-bottom:8px;font-weight:600}
.rcx{font-size:14px;line-height:1.6}
.sgb{margin:16px 0;padding:14px 18px;border-radius:8px;background:rgba(71,205,137,.06);
  border:1px solid rgba(71,205,137,.2)}
.sgt{font-family:var(--mono);font-size:10px;color:var(--success);letter-spacing:.06em;
  margin-bottom:8px;font-weight:600}
.sgl{list-style:none;padding:0}
.sgl li{font-size:13px;color:var(--text-muted);padding:4px 0 4px 16px;position:relative}
.sgl li::before{content:'\2192';position:absolute;left:0;color:var(--success)}

/* Timeline */
.tls{padding:20px 24px}
.tlt{font-family:var(--mono);font-size:12px;color:var(--text-muted);letter-spacing:.06em;
  margin-bottom:16px;font-weight:600}
.sr{display:flex;cursor:pointer;transition:background .15s}
.sr:hover{background:var(--surface-hover)}
.sc2{display:flex;flex-direction:column;align-items:center;width:40px;flex-shrink:0}
.cl{width:2px;background:var(--border)}
.clt{height:12px}.clb{flex:1}
.dot{width:12px;height:12px;border-radius:50%;flex-shrink:0;border:2px solid transparent;transition:all .2s}
.dot.llm{background:var(--accent)}.dot.tool{background:var(--text-dim)}
.dot.ret{background:var(--warning)}
.dot.rc{width:16px;height:16px;background:var(--error);box-shadow:0 0 12px rgba(249,112,102,.3)}
.dot.sel{border-color:var(--text)}
.sb{flex:1;padding:8px 12px;border-radius:8px;border:1px solid transparent}
.sb.sel{border-color:var(--border-active);background:var(--surface-hover)}
.sh{display:flex;align-items:center;gap:8px;margin-bottom:4px;flex-wrap:wrap}
.st{font-family:var(--mono);font-size:11px;font-weight:600;padding:2px 8px;border-radius:4px;letter-spacing:.04em}
.st-l{background:rgba(129,140,248,.1);color:var(--accent)}
.st-t{background:rgba(86,90,110,.15);color:var(--text-muted)}
.st-r{background:rgba(247,144,9,.1);color:var(--warning)}
.rcbdg{font-family:var(--mono);font-size:10px;font-weight:700;padding:2px 8px;border-radius:4px;
  background:rgba(249,112,102,.12);color:var(--error);letter-spacing:.06em}
.sn{font-family:var(--mono);font-size:13px;font-weight:500}
.ssm{font-size:12px;color:var(--text-muted);margin-top:4px;line-height:1.5}
.stk{font-family:var(--mono);font-size:11px;color:var(--text-dim);margin-top:4px}
.sex{display:none;margin-top:10px;padding:12px;background:var(--surface);border-radius:8px;
  border:1px solid var(--border)}
.sex.active{display:block}
.sex pre{font-family:var(--mono);font-size:12px;color:var(--text-muted);white-space:pre-wrap;
  word-break:break-word;line-height:1.6;margin:0}
.fl{font-family:var(--mono);font-size:10px;color:var(--text-dim);letter-spacing:.06em;
  font-weight:600;margin-bottom:4px;margin-top:8px}
.fl:first-child{margin-top:0}
.err-t{color:var(--error)}

/* Scrollbar */
::-webkit-scrollbar{width:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--border-active)}
.empty{padding:40px;text-align:center;font-family:var(--mono);font-size:13px;color:var(--text-dim)}
</style>
</head>
<body>

<header class="hdr">
  <div class="hdr-brand">
    <div class="hdr-icon">&#9889;</div>
    <div>
      <div class="hdr-title">Agent Failure Analysis</div>
      <div class="hdr-sub">Generated: %%TIMESTAMP%% &middot; Model: %%MODEL_USED%% &middot; nat analyze</div>
    </div>
  </div>
</header>

<div class="stats" id="statsRow"></div>
<div class="dist" id="distSection"></div>

<div class="main">
  <div class="lp" id="listPanel">
    <div class="ctrls">
      <input type="text" class="ci" id="searchInput" placeholder="Search task ID or question...">
      <select class="cs" id="filterGroup"><option value="all">All Groups</option></select>
      <select class="cs" id="sortSelect">
        <option value="group">Sort: Group</option>
        <option value="task_id">Sort: Task ID</option>
        <option value="confidence">Sort: Confidence</option>
        <option value="steps">Sort: Steps</option>
      </select>
    </div>
    <div class="tc" id="taskCount"></div>
    <div class="tl" id="taskList"></div>
  </div>
  <div class="dp" id="detailPanel"></div>
</div>

<script>
const R = %%REPORT_DATA%%;
const COLORS = ['#F97066','#F79009','#B692F6','#36BFFA','#67E3F9','#818CF8','#47CD89','#EC4899','#84CC16','#F97316','#6366F1','#14B8A6'];
const gc = {};
(R.fingerprint_groups||[]).forEach((g,i) => { gc[g.group_name] = COLORS[i % COLORS.length]; });

let selId = null, selStep = null;

function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
function trn(s, n) { return (!s || s.length <= n) ? (s||'') : s.substring(0, n) + '\u2026'; }

function renderStats() {
  const el = document.getElementById('statsRow');
  const groups = R.fingerprint_groups || [];
  const tasks = R.task_analyses || [];
  const totalSteps = tasks.reduce((a, t) => a + (t.step_details||[]).length, 0);
  const avg = tasks.length ? Math.round(totalSteps / tasks.length) : 0;
  const top = groups.length ? groups.reduce((a, b) => a.count > b.count ? a : b) : null;
  el.innerHTML = `
    <div class="sc"><div class="sc-bar" style="background:var(--error)"></div>
      <div class="sc-label">Total Failures</div>
      <div class="sc-val" style="color:var(--error)">${R.total_failures}</div>
      <div class="sc-sub">out of ${R.total_tasks} tasks</div></div>
    <div class="sc"><div class="sc-bar" style="background:var(--accent)"></div>
      <div class="sc-label">Failure Groups</div>
      <div class="sc-val" style="color:var(--accent)">${groups.length}</div>
      <div class="sc-sub">distinct patterns</div></div>
    <div class="sc"><div class="sc-bar" style="background:var(--warning)"></div>
      <div class="sc-label">Most Common</div>
      <div class="sc-val" style="font-size:${top && top.group_name.length > 20 ? 14 : 18}px">${top ? esc(trn(top.group_name, 30)) : '\u2014'}</div>
      <div class="sc-sub">${top ? top.count + ' tasks' : ''}</div></div>
    <div class="sc"><div class="sc-bar" style="background:var(--accent)"></div>
      <div class="sc-label">Avg Steps</div>
      <div class="sc-val" style="color:var(--accent)">${avg}</div>
      <div class="sc-sub">per failed task</div></div>`;
}

function renderDist() {
  const el = document.getElementById('distSection');
  const groups = R.fingerprint_groups || [];
  const total = R.total_failures || 1;
  let h = '<div class="dist-bar">';
  groups.forEach(g => {
    const c = gc[g.group_name] || '#565A6E';
    h += `<div style="width:${(g.count/total)*100}%;background:${c};min-width:3px;transition:width .4s"></div>`;
  });
  h += '</div><div class="dist-leg">';
  groups.forEach(g => {
    const c = gc[g.group_name] || '#565A6E';
    h += `<div class="leg-item"><div class="leg-dot" style="background:${c}"></div>${esc(trn(g.group_name,35))} <span style="color:var(--text);font-weight:600">${g.count}</span></div>`;
  });
  h += '</div>';
  el.innerHTML = h;
}

function populateFilters() {
  const sel = document.getElementById('filterGroup');
  (R.fingerprint_groups||[]).forEach(g => {
    const o = document.createElement('option');
    o.value = g.group_name;
    o.textContent = g.group_name + ' (' + g.count + ')';
    sel.appendChild(o);
  });
}

function getFiltered() {
  const q = document.getElementById('searchInput').value.toLowerCase();
  const fg = document.getElementById('filterGroup').value;
  const sb = document.getElementById('sortSelect').value;
  let tasks = [...(R.task_analyses||[])];
  if (fg !== 'all') tasks = tasks.filter(t => t.group_name === fg);
  if (q) tasks = tasks.filter(t => t.task_id.toLowerCase().includes(q) || t.question.toLowerCase().includes(q));
  if (sb === 'group') tasks.sort((a,b) => a.group_name.localeCompare(b.group_name));
  else if (sb === 'task_id') tasks.sort((a,b) => a.task_id.localeCompare(b.task_id));
  else if (sb === 'confidence') tasks.sort((a,b) => b.confidence - a.confidence);
  else if (sb === 'steps') tasks.sort((a,b) => (b.step_details||[]).length - (a.step_details||[]).length);
  return tasks;
}

function renderList() {
  const tasks = getFiltered();
  const el = document.getElementById('taskList');
  document.getElementById('taskCount').textContent = 'Showing ' + tasks.length + ' of ' + (R.task_analyses||[]).length + ' failed tasks';
  el.innerHTML = '';
  if (!tasks.length) { el.innerHTML = '<div class="empty">No tasks match the current filters</div>'; return; }
  tasks.forEach(task => {
    const c = gc[task.group_name] || '#565A6E';
    const row = document.createElement('div');
    row.className = 'tr' + (selId === task.task_id ? ' active' : '');
    row.innerHTML = `
      <div class="sd" style="background:${c};box-shadow:0 0 8px ${c}40"></div>
      <div class="ti">
        <div class="tm">
          <span class="gb" style="background:${c}15;color:${c}">${esc(trn(task.group_name,25))}</span>
          <span class="tid">${esc(task.task_id.slice(0,12))}\u2026</span>
        </div>
        <div class="qt">${esc(task.question)}</div>
      </div>
      <div class="trt">
        <div class="scl">${(task.step_details||[]).length} steps</div>
      </div>`;
    row.addEventListener('click', () => { selId = task.task_id; selStep = null; renderList(); renderDetail(); });
    el.appendChild(row);
  });
}

function renderDetail() {
  const panel = document.getElementById('detailPanel');
  const lp = document.getElementById('listPanel');
  if (!selId) { panel.classList.remove('active'); lp.classList.remove('shrink'); return; }
  const task = (R.task_analyses||[]).find(t => t.task_id === selId);
  if (!task) return;
  panel.classList.add('active'); lp.classList.add('shrink');

  const c = gc[task.group_name] || '#565A6E';
  const ri = new Set(task.root_cause_step_indices || []);
  const sm = {};
  (task.step_summaries||[]).forEach(s => { sm[s.step_index] = s; });

  const confPct = Math.round(task.confidence * 100);
  const confCol = confPct >= 70 ? 'var(--success)' : confPct >= 40 ? 'var(--warning)' : 'var(--error)';

  // Timeline
  let tl = '';
  const steps = task.step_details || [];
  steps.forEach((d, idx) => {
    const isRC = ri.has(d.step_index);
    const summary = sm[d.step_index];
    const isSel = selStep === idx;
    const isFirst = idx === 0, isLast = idx === steps.length - 1;

    let dotCls = 'dot';
    if (isRC) dotCls += ' rc';
    else if (d.event_type === 'LLM_END') dotCls += ' llm';
    else if (d.event_type === 'RETRIEVER_END') dotCls += ' ret';
    else dotCls += ' tool';
    if (isSel) dotCls += ' sel';

    let stCls = 'st';
    if (d.event_type === 'LLM_END') stCls += ' st-l';
    else if (d.event_type === 'RETRIEVER_END') stCls += ' st-r';
    else stCls += ' st-t';

    let det = '';
    if (d.full_input) det += '<div class="fl">INPUT</div><pre>' + esc(trn(d.full_input, 3000)) + '</pre>';
    if (d.full_output) det += '<div class="fl">OUTPUT</div><pre>' + esc(trn(d.full_output, 3000)) + '</pre>';
    if (d.tool_args) det += '<div class="fl">TOOL ARGS</div><pre>' + esc(JSON.stringify(d.tool_args, null, 2)) + '</pre>';
    if (d.error_message) det += '<div class="fl">ERROR</div><pre class="err-t">' + esc(d.error_message) + '</pre>';

    tl += `<div class="sr" data-idx="${idx}">
      <div class="sc2">
        <div class="cl clt" style="${isFirst?'background:transparent':''}"></div>
        <div class="${dotCls}"></div>
        <div class="cl clb" style="${isLast?'background:transparent':''}"></div>
      </div>
      <div class="sb${isSel?' sel':''}">
        <div class="sh">
          <span class="${stCls}">${d.event_type}</span>
          ${isRC ? '<span class="rcbdg">ROOT CAUSE</span>' : ''}
        </div>
        <div class="sn">#${d.step_index} ${esc(d.name)}</div>
        ${summary ? '<div class="ssm">' + esc(summary.summary) + '</div>' : ''}
        ${d.event_type==='LLM_END' && d.prompt_tokens ? '<div class="stk">' + d.prompt_tokens + ' prompt \u00b7 ' + (d.completion_tokens||0) + ' completion tokens</div>' : ''}
        <div class="sex${isSel?' active':''}">${det}</div>
      </div>
    </div>`;
  });

  // Suggestions
  let sugH = '';
  if (task.improvement_suggestions && task.improvement_suggestions.length) {
    sugH = `<div class="sgb"><div class="sgt">IMPROVEMENT SUGGESTIONS</div>
      <ul class="sgl">${task.improvement_suggestions.map(s => '<li>' + esc(s) + '</li>').join('')}</ul></div>`;
  }

  panel.innerHTML = `
    <div class="dh">
      <div class="dh-top">
        <div class="dh-left">
          <span class="fpb" style="background:${c}15;color:${c}">${esc(task.group_name)}</span>
          <span style="font-family:var(--mono);font-size:12px;color:var(--text-dim)">${esc(task.task_id)}</span>
          <span class="cb" style="background:${confCol}15;color:${confCol}">${confPct}% confidence</span>
        </div>
        <button class="close-btn" onclick="closeDetail()">&times;</button>
      </div>
      <div class="dq">${esc(task.question)}</div>
      <div class="ag">
        <div class="ab exp">
          <div class="al" style="color:var(--success)">EXPECTED ANSWER</div>
          <div class="av">${esc(task.expected_answer)}</div>
        </div>
        <div class="ab act">
          <div class="al" style="color:var(--error)">ACTUAL ANSWER &cross;</div>
          <div class="av">${esc(task.actual_answer)}</div>
        </div>
      </div>
    </div>
    <div style="padding:20px 24px">
      <div class="rcb"><div class="rct">ROOT CAUSE ANALYSIS</div><div class="rcx">${esc(task.root_cause)}</div></div>
      ${sugH}
    </div>
    <div class="tls">
      <div class="tlt">EXECUTION TRACE &middot; ${steps.length} STEPS</div>
      <div>${tl}</div>
    </div>`;

  panel.querySelectorAll('.sr').forEach(row => {
    row.addEventListener('click', e => {
      e.stopPropagation();
      const idx = parseInt(row.dataset.idx);
      selStep = selStep === idx ? null : idx;
      renderDetail();
    });
  });
}

function closeDetail() { selId = null; selStep = null; renderList(); renderDetail(); }

// Init
renderStats();
renderDist();
populateFilters();
renderList();
document.getElementById('searchInput').addEventListener('input', renderList);
document.getElementById('filterGroup').addEventListener('change', renderList);
document.getElementById('sortSelect').addEventListener('change', renderList);
</script>
</body>
</html>"""
