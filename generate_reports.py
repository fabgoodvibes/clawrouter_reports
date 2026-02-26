#!/usr/bin/env python3
"""
BlockRun Usage Report Generator
================================
Scans a directory of daily usage-YYYY-MM-DD.jsonl files, produces a single
self-contained HTML report with:
  • Aggregated overview (all days combined)
  • Per-day sections, each with full charts & stats
  • Sidebar navigation linking to each day

Usage:
    python3 generate_reports.py <log_dir> [output_path]

    log_dir      — directory containing usage-*.jsonl files
    output_path  — where to write report.html  (default: <log_dir>/report.html)

Exit codes: 0 = success, 1 = error
"""

import sys
import json
import os
import glob
from collections import defaultdict
from datetime import datetime

# ─── Palettes ─────────────────────────────────────────────────────────────────

# Pastel-cyber: deep slate + low-saturation tinted accents
MODEL_COLORS = {
    0: {"hex": "#6ee7df", "soft": "rgba(110,231,223,0.18)", "rgb": "110,231,223"},
    1: {"hex": "#f5c97e", "soft": "rgba(245,201,126,0.18)", "rgb": "245,201,126"},
    2: {"hex": "#d4a0c8", "soft": "rgba(212,160,200,0.18)", "rgb": "212,160,200"},
    3: {"hex": "#93c5fd", "soft": "rgba(147,197,253,0.18)", "rgb": "147,197,253"},
    4: {"hex": "#86efac", "soft": "rgba(134,239,172,0.18)", "rgb": "134,239,172"},
}
TIER_COLORS = {
    "SIMPLE": "#6ee7df",
    "MEDIUM": "#f5c97e",
    "DIRECT": "#d4a0c8",
}

# Neon-cyber: pitch-black base + full-saturation glowing accents
NEON_MODEL_COLORS = {
    0: {"hex": "#00f5d4", "soft": "rgba(0,245,212,0.2)",   "rgb": "0,245,212"},
    1: {"hex": "#ffb700", "soft": "rgba(255,183,0,0.2)",   "rgb": "255,183,0"},
    2: {"hex": "#ff3cac", "soft": "rgba(255,60,172,0.2)",  "rgb": "255,60,172"},
    3: {"hex": "#a78bfa", "soft": "rgba(167,139,250,0.2)", "rgb": "167,139,250"},
    4: {"hex": "#34d399", "soft": "rgba(52,211,153,0.2)",  "rgb": "52,211,153"},
}
NEON_TIER_COLORS = {
    "SIMPLE": "#00f5d4",
    "MEDIUM": "#ffb700",
    "DIRECT": "#ff3cac",
}


# ─── Data loading ─────────────────────────────────────────────────────────────
def load_jsonl(filepath):
    entries = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def find_daily_files(log_dir):
    """Return sorted list of (date_str, filepath) for all usage-*.jsonl files."""
    pattern = os.path.join(log_dir, "usage-*.jsonl")
    files = sorted(glob.glob(pattern))
    result = []
    for fp in files:
        name = os.path.basename(fp)
        date_str = name.replace("usage-", "").replace(".jsonl", "")
        result.append((date_str, fp))
    return result


# ─── Aggregation ─────────────────────────────────────────────────────────────
def aggregate(entries, label=""):
    if not entries:
        return None

    total_cost     = sum(e.get("cost", 0) for e in entries)
    total_baseline = sum(e.get("baselineCost", 0) for e in entries)
    total_requests = len(entries)
    avg_latency    = sum(e.get("latencyMs", 0) for e in entries) / max(total_requests, 1)
    real_savings   = max(0.0, total_baseline - total_cost)
    savings_rate   = max(0.0, min((real_savings / total_baseline * 100) if total_baseline > 0 else 0, 100.0))

    # By model
    by_model = defaultdict(lambda: {"count": 0, "cost": 0.0, "baseline": 0.0,
                                    "latencies": [], "input_tokens": 0, "output_tokens": 0})
    for e in entries:
        m = e.get("model", "unknown")
        by_model[m]["count"]         += 1
        by_model[m]["cost"]          += e.get("cost", 0)
        by_model[m]["baseline"]      += e.get("baselineCost", 0)
        by_model[m]["latencies"].append(e.get("latencyMs", 0))
        by_model[m]["input_tokens"]  += e.get("inputTokens", 0)
        by_model[m]["output_tokens"] += e.get("outputTokens", 0)

    models_list = []
    has_tokens  = False  # True if at least one entry in this dataset has token data
    for i, (model, v) in enumerate(by_model.items()):
        avg_lat = sum(v["latencies"]) / len(v["latencies"]) if v["latencies"] else 0
        mdl_savings = max(0.0, v["baseline"] - v["cost"])
        sr = (mdl_savings / v["baseline"] * 100) if v["baseline"] > 0 else 0
        total_tokens = v["input_tokens"] + v["output_tokens"]
        if total_tokens > 0:
            has_tokens = True
        models_list.append({
            "model":         model,
            "short":         model.split("/")[-1],
            "count":         v["count"],
            "cost":          v["cost"],
            "baseline":      v["baseline"],
            "savings":       mdl_savings,
            "savings_pct":   sr,
            "avg_latency":   avg_lat,
            "input_tokens":  v["input_tokens"],
            "output_tokens": v["output_tokens"],
            "total_tokens":  total_tokens,
            "color_idx":     i % len(MODEL_COLORS),
        })
    models_list.sort(key=lambda x: x["cost"], reverse=True)

    return_dict_tokens = has_tokens

    # By tier
    by_tier = defaultdict(lambda: {"count": 0, "cost": 0.0})
    for e in entries:
        t = e.get("tier", "UNKNOWN")
        by_tier[t]["count"] += 1
        by_tier[t]["cost"]  += e.get("cost", 0)

    # Timeline — bucket by minute for single-day, by date for multi-day
    timeline = defaultdict(lambda: defaultdict(float))
    for e in entries:
        ts = e.get("timestamp", "")
        model = e.get("model", "unknown")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            bucket = dt.strftime("%H:%M") if label != "global" else dt.strftime("%m-%d")
            timeline[bucket][model] += e.get("cost", 0)
        except Exception:
            pass

    # Latency histogram (2-second buckets)
    lat_buckets = [0] * 10
    for e in entries:
        idx = min(int(e.get("latencyMs", 0) / 2000), 9)
        lat_buckets[idx] += 1

    return {
        "label":          label,
        "total_cost":     total_cost,
        "total_baseline": total_baseline,
        "real_savings":   real_savings,
        "total_requests": total_requests,
        "avg_latency":    avg_latency,
        "savings_rate":   savings_rate,
        "models":         models_list,
        "has_tokens":     return_dict_tokens,
        "by_tier":        dict(by_tier),
        "timeline":       dict(timeline),
        "lat_buckets":    lat_buckets,
    }


# ─── Chart data helpers ───────────────────────────────────────────────────────
def mc(idx, key="hex"):
    return MODEL_COLORS[idx % len(MODEL_COLORS)][key]

def ncm(idx, key="hex"):
    return NEON_MODEL_COLORS[idx % len(NEON_MODEL_COLORS)][key]


def chart_data(data):
    models = data["models"]

    donut_labels = json.dumps([m["short"] for m in models])
    donut_costs  = json.dumps([round(m["cost"], 6) for m in models])

    # pastel colours
    donut_colors = json.dumps([mc(m["color_idx"]) for m in models])
    donut_soft   = json.dumps([mc(m["color_idx"], "soft") for m in models])
    bar_colors   = json.dumps([mc(m["color_idx"]) for m in models])
    bar_soft     = json.dumps([mc(m["color_idx"], "soft") for m in models])

    # neon colours
    donut_colors_neon = json.dumps([ncm(m["color_idx"]) for m in models])
    donut_soft_neon   = json.dumps([ncm(m["color_idx"], "soft") for m in models])
    bar_colors_neon   = json.dumps([ncm(m["color_idx"]) for m in models])
    bar_soft_neon     = json.dumps([ncm(m["color_idx"], "soft") for m in models])

    bar_labels   = json.dumps([m["short"] for m in models])
    bar_cost     = json.dumps([round(m["cost"], 4) for m in models])
    bar_baseline = json.dumps([round(m["baseline"], 4) for m in models])
    bar_savings  = json.dumps([round(m["savings"], 4) for m in models])

    all_times  = sorted(data["timeline"].keys())
    tl_labels  = json.dumps(all_times)

    tl_datasets_pastel = []
    tl_datasets_neon   = []
    for m in models:
        cp = MODEL_COLORS[m["color_idx"]]
        cn = NEON_MODEL_COLORS[m["color_idx"] % len(NEON_MODEL_COLORS)]
        vals = [round(data["timeline"].get(t, {}).get(m["model"], 0), 6) for t in all_times]
        base = {"label": m["short"], "data": vals, "fill": True, "tension": 0.4, "pointRadius": 2}
        tl_datasets_pastel.append({**base, "borderColor": cp["hex"], "backgroundColor": cp["soft"]})
        tl_datasets_neon.append(  {**base, "borderColor": cn["hex"], "backgroundColor": cn["soft"]})
    tl_datasets_json      = json.dumps(tl_datasets_pastel)
    tl_datasets_neon_json = json.dumps(tl_datasets_neon)

    lat_labels = json.dumps(["0-2s","2-4s","4-6s","6-8s","8-10s","10-12s","12-14s","14-16s","16-18s","18s+"])
    lat_data   = json.dumps(data["lat_buckets"])

    return dict(
        donut_labels=donut_labels, donut_costs=donut_costs,
        donut_colors=donut_colors, donut_soft=donut_soft,
        donut_colors_neon=donut_colors_neon, donut_soft_neon=donut_soft_neon,
        bar_labels=bar_labels, bar_cost=bar_cost,
        bar_baseline=bar_baseline, bar_savings=bar_savings,
        bar_colors=bar_colors, bar_soft=bar_soft,
        bar_colors_neon=bar_colors_neon, bar_soft_neon=bar_soft_neon,
        tl_labels=tl_labels,
        tl_datasets_json=tl_datasets_json,
        tl_datasets_neon_json=tl_datasets_neon_json,
        lat_labels=lat_labels, lat_data=lat_data,
    )


# ─── HTML fragments ───────────────────────────────────────────────────────────
def model_rows_html(models, has_tokens=False):
    rows = []
    for m in models:
        c   = MODEL_COLORS[m["color_idx"]]
        dot = f'<span class="dot" style="background:{c["hex"]};box-shadow:0 0 6px rgba({c["rgb"]},0.7);"></span>'
        pill = (f'<span class="pill" style="background:rgba({c["rgb"]},0.12);'
                f'color:{c["hex"]};border:1px solid rgba({c["rgb"]},0.3);">'
                f'{m["savings_pct"]:.1f}%</span>')

        if has_tokens:
            if m["total_tokens"] > 0:
                tok_cell = (
                    f'<span title="In: {m["input_tokens"]:,} · Out: {m["output_tokens"]:,}">'
                    f'{m["total_tokens"]:,}'
                    f'</span>'
                    f'<span class="tok-breakdown"> '
                    f'{m["input_tokens"]//1000}k↑ {m["output_tokens"]//1000}k↓'
                    f'</span>'
                )
            else:
                tok_cell = '<span class="dim">—</span>'
            token_td = f'<td class="num tok-cell">{tok_cell}</td>'
        else:
            token_td = ""

        rows.append(
            f'<tr>'
            f'<td>{dot}<span class="model-name">{m["short"]}</span></td>'
            f'<td class="num">{m["count"]:,}</td>'
            f'<td class="num">${m["cost"]:.4f}</td>'
            f'<td class="num dim">${m["baseline"]:.4f}</td>'
            f'<td class="num" style="color:{c["hex"]};">${m["savings"]:.4f}</td>'
            f'<td class="num">{pill}</td>'
            f'{token_td}'
            f'<td class="num dim">{m["avg_latency"]:.0f} ms</td>'
            f'</tr>'
        )
    return "\n".join(rows)


def tier_badges_html(by_tier):
    badges = []
    for tier, v in sorted(by_tier.items()):
        color = TIER_COLORS.get(tier, "#8899aa")
        rgb   = {"SIMPLE": "110,231,223", "MEDIUM": "245,201,126",
                 "DIRECT": "212,160,200"}.get(tier, "136,153,170")
        badges.append(
            f'<div class="tier-badge" style="border-color:rgba({rgb},0.4);'
            f'background:rgba({rgb},0.07);">'
            f'<span class="tier-name" style="color:{color};">{tier}</span>'
            f'<span class="tier-count">{v["count"]:,} req</span>'
            f'<span class="tier-cost" style="color:{color};">${v["cost"]:.4f}</span>'
            f'</div>'
        )
    return "\n".join(badges)


def gauge_svg(sr):
    """Return the SVG gauge elements for a given savings rate 0-100."""
    circ   = 339.3
    dash   = round(circ * min(sr / 100, 1), 2)
    offset = round(circ - dash, 2)
    if sr >= 70:
        color = "#6ee7df"
    elif sr >= 40:
        color = "#f5c97e"
    else:
        color = "#d4a0c8"
    return dash, offset, color


# ─── Section renderer ─────────────────────────────────────────────────────────
def render_section(data, section_id, is_global=False):
    """Render a full dashboard section (global or daily)."""
    if data is None:
        return f'<section id="{section_id}"><p class="empty">No data available.</p></section>'

    c  = chart_data(data)
    sr = data["savings_rate"]
    gauge_dash, gauge_offset, gauge_color = gauge_svg(sr)
    rows   = model_rows_html(data["models"], data.get("has_tokens", False))
    tiers  = tier_badges_html(data["by_tier"])
    uid    = section_id.replace("-", "_")  # safe JS var prefix
    has_tokens = data.get("has_tokens", False)
    token_th = '<th title="inputTokens + outputTokens">Tokens</th>' if has_tokens else ""

    heading = "Aggregated Overview — All Days" if is_global else f"Daily Report · {data['label']}"
    tag_cls = "section-tag-global" if is_global else "section-tag-daily"
    tag_lbl = "GLOBAL" if is_global else "DAILY"

    return f"""
<section id="{section_id}" class="dashboard-section">
  <div class="section-header">
    <div>
      <span class="section-tag {tag_cls}">{tag_lbl}</span>
      <h2 class="section-title">{heading}</h2>
    </div>
    <div class="section-meta">
      <span>{data['total_requests']:,} requests</span>
      <span>·</span>
      <span>{len(data['models'])} models</span>
      <span>·</span>
      <span>${data['total_cost']:.4f} actual</span>
    </div>
  </div>

  <!-- KPI strip -->
  <div class="kpi-strip">
    <div class="kpi" style="--accent:#6ee7df;">
      <div class="kpi-label">Requests</div>
      <div class="kpi-value">{data['total_requests']:,}</div>
    </div>
    <div class="kpi" style="--accent:#d4a0c8;">
      <div class="kpi-label">Actual Cost</div>
      <div class="kpi-value">${data['total_cost']:.4f}</div>
      <div class="kpi-sub">USD this period</div>
    </div>
    <div class="kpi" style="--accent:#8899aa;">
      <div class="kpi-label">Baseline Cost</div>
      <div class="kpi-value">${data['total_baseline']:.2f}</div>
      <div class="kpi-sub">without routing</div>
    </div>
    <div class="kpi" style="--accent:#86efac;">
      <div class="kpi-label">Real Savings</div>
      <div class="kpi-value">${data['real_savings']:.2f}</div>
      <div class="kpi-sub">baseline − actual</div>
    </div>
    <div class="kpi" style="--accent:#f5c97e;">
      <div class="kpi-label">Avg Latency</div>
      <div class="kpi-value">{data['avg_latency']:.0f}<span style="font-size:14px;"> ms</span></div>
    </div>
  </div>

  <!-- Main grid -->
  <div class="main-grid">

    <!-- Gauge + tiers -->
    <div class="card gauge-card">
      <div class="card-title" style="text-align:center;">Savings Rate</div>
      <div class="gauge-wrap">
        <svg width="140" height="140" viewBox="0 0 140 140">
          <circle class="gauge-bg"   cx="70" cy="70" r="54"/>
          <circle class="gauge-fill" cx="70" cy="70" r="54"
            style="stroke:{gauge_color};stroke-dasharray:{gauge_dash} {gauge_offset};filter:drop-shadow(0 0 6px {gauge_color})90;"/>
        </svg>
        <div class="gauge-center">
          <div class="gauge-pct" style="color:{gauge_color};text-shadow:0 0 14px {gauge_color}66;">{sr:.0f}%</div>
          <div class="gauge-lbl">SAVED</div>
        </div>
      </div>
      <div class="card-title" style="text-align:center;margin-top:4px;">Routing Tiers</div>
      <div class="tier-badges">{tiers}</div>
    </div>

    <!-- Bar chart -->
    <div class="card">
      <div class="card-title">Cost · Baseline · Savings by Model</div>
      <div class="chart-wrap">
        <canvas id="{uid}_barChart"></canvas>
      </div>
    </div>

    <!-- Donut -->
    <div class="card">
      <div class="card-title">Actual Cost Share</div>
      <div class="chart-wrap">
        <canvas id="{uid}_donutChart"></canvas>
      </div>
    </div>

    <!-- Timeline -->
    <div class="card span2">
      <div class="card-title">Cost Timeline {"per Minute" if not is_global else "per Day"}</div>
      <div class="chart-wrap">
        <canvas id="{uid}_tlChart"></canvas>
      </div>
    </div>

  </div>

  <!-- Bottom row -->
  <div class="bottom-grid">
    <div class="card">
      <div class="card-title">Model Breakdown</div>
      <table class="model-table">
        <thead>
          <tr>
            <th>Model</th><th>Req</th><th>Actual</th>
            <th>Baseline</th><th>Saved</th><th>Rate</th>{token_th}<th>Avg Lat</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    <div class="card">
      <div class="card-title">Latency Distribution</div>
      <div class="chart-wrap-tall">
        <canvas id="{uid}_latChart"></canvas>
      </div>
    </div>
  </div>

</section>

<script>
(function() {{
  window.CHARTS = window.CHARTS || {{}};
  const isNeon  = () => document.documentElement.getAttribute('data-theme') === 'neon';

  // Both palettes for this section
  const P_COLORS = {c['donut_colors']};
  const P_SOFT   = {c['donut_soft']};
  const N_COLORS = {c['donut_colors_neon']};
  const N_SOFT   = {c['donut_soft_neon']};
  const PB_COLORS = {c['bar_colors']};
  const PB_SOFT   = {c['bar_soft']};
  const NB_COLORS = {c['bar_colors_neon']};
  const NB_SOFT   = {c['bar_soft_neon']};
  const TL_PASTEL = {c['tl_datasets_json']};
  const TL_NEON   = {c['tl_datasets_neon_json']};

  const themeColors = () => {{
    const neon = isNeon();
    return {{
      grid:           neon ? 'rgba(0,245,212,0.06)'   : 'rgba(180,190,220,0.07)',
      tick:           neon ? '#3a4d6a'                 : '#7a86a8',
      legend:         neon ? '#5a7090'                 : '#a8b4cc',
      baselineBg:     neon ? 'rgba(58,77,106,0.3)'    : 'rgba(120,130,160,0.25)',
      baselineBorder: neon ? 'rgba(58,77,106,0.7)'    : 'rgba(120,130,160,0.6)',
      savingsBg:      neon ? 'rgba(0,245,212,0.1)'    : 'rgba(110,231,223,0.1)',
      savingsBorder:  neon ? '#00f5d4'                 : '#6ee7df',
      latBg:          neon ? 'rgba(255,183,0,0.18)'   : 'rgba(245,201,126,0.2)',
      latBorder:      neon ? '#ffb700'                 : '#f5c97e',
      modelColors:    neon ? N_COLORS : P_COLORS,
      modelSoft:      neon ? N_SOFT   : P_SOFT,
      barColors:      neon ? NB_COLORS : PB_COLORS,
      barSoft:        neon ? NB_SOFT   : PB_SOFT,
    }};
  }};

  const tc = themeColors();

  // ── Donut ──
  const donut = new Chart(document.getElementById('{uid}_donutChart'), {{
    type: 'doughnut',
    data: {{
      labels: {c['donut_labels']},
      datasets: [{{ data: {c['donut_costs']}, backgroundColor: tc.modelSoft, borderColor: tc.modelColors, borderWidth: 1.5, hoverOffset: 5 }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false, cutout: '68%',
      plugins: {{
        legend: {{ position: 'right', labels: {{ boxWidth: 10, padding: 12, color: tc.legend }} }},
        tooltip: {{ callbacks: {{ label: ctx => ' $' + ctx.parsed.toFixed(6) }} }}
      }}
    }}
  }});
  window.CHARTS['{uid}_donutChart'] = {{ chart: donut, role: 'donut',
    pastel: {{ colors: P_COLORS, soft: P_SOFT }}, neon: {{ colors: N_COLORS, soft: N_SOFT }} }};

  // ── Bar ──
  const bar = new Chart(document.getElementById('{uid}_barChart'), {{
    type: 'bar',
    data: {{
      labels: {c['bar_labels']},
      datasets: [
        {{ label: 'Baseline',    data: {c['bar_baseline']}, backgroundColor: tc.baselineBg, borderColor: tc.baselineBorder, borderWidth: 1, borderRadius: 4 }},
        {{ label: 'Actual Cost', data: {c['bar_cost']},     backgroundColor: tc.barSoft, borderColor: tc.barColors, borderWidth: 1.5, borderRadius: 4 }},
        {{ label: 'Savings',     data: {c['bar_savings']},  backgroundColor: tc.savingsBg, borderColor: tc.savingsBorder, borderWidth: 1, borderRadius: 4 }}
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{
        legend: {{ position: 'bottom', labels: {{ boxWidth: 10, padding: 10, color: tc.legend }} }},
        tooltip: {{ callbacks: {{ label: ctx => ' $' + ctx.parsed.y.toFixed(4) }} }}
      }},
      scales: {{
        x: {{ grid: {{ color: tc.grid }}, ticks: {{ color: tc.tick, maxRotation: 0 }} }},
        y: {{ grid: {{ color: tc.grid }}, ticks: {{ color: tc.tick, callback: v => '$' + v.toFixed(1) }} }}
      }}
    }}
  }});
  window.CHARTS['{uid}_barChart'] = {{ chart: bar, role: 'bar',
    pastel: {{ colors: PB_COLORS, soft: PB_SOFT }}, neon: {{ colors: NB_COLORS, soft: NB_SOFT }} }};

  // ── Timeline ──
  const tlData = isNeon() ? TL_NEON : TL_PASTEL;
  const tl = new Chart(document.getElementById('{uid}_tlChart'), {{
    type: 'line',
    data: {{ labels: {c['tl_labels']}, datasets: tlData }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ position: 'bottom', labels: {{ boxWidth: 10, padding: 12, color: tc.legend }} }},
        tooltip: {{ callbacks: {{ label: ctx => ' $' + ctx.parsed.y.toFixed(6) }} }}
      }},
      scales: {{
        x: {{ grid: {{ color: tc.grid }}, ticks: {{ color: tc.tick, maxTicksLimit: 18, maxRotation: 0 }} }},
        y: {{ grid: {{ color: tc.grid }}, stacked: true, ticks: {{ color: tc.tick, callback: v => '$' + v.toFixed(4) }} }}
      }}
    }}
  }});
  window.CHARTS['{uid}_tlChart'] = {{ chart: tl, role: 'tl',
    pastel: {{ tl: TL_PASTEL }}, neon: {{ tl: TL_NEON }} }};

  // ── Latency ──
  const lat = new Chart(document.getElementById('{uid}_latChart'), {{
    type: 'bar',
    data: {{
      labels: {c['lat_labels']},
      datasets: [{{ label: 'Requests', data: {c['lat_data']}, backgroundColor: tc.latBg, borderColor: tc.latBorder, borderWidth: 1, borderRadius: 3 }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ grid: {{ color: tc.grid }}, ticks: {{ color: tc.tick, maxRotation: 45, font: {{ size: 9 }} }} }},
        y: {{ grid: {{ color: tc.grid }}, ticks: {{ color: tc.tick }} }}
      }}
    }}
  }});
  window.CHARTS['{uid}_latChart'] = {{ chart: lat, role: 'lat' }};

}})();
</script>
"""


# ─── Full HTML page ───────────────────────────────────────────────────────────
CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

/* ── Pastel theme (default) ── */
:root {
  --bg:         #0f1320;
  --bg2:        #141929;
  --surface:    #1a2035;
  --surface2:   #1f2640;
  --border:     rgba(180,195,230,0.09);
  --border2:    rgba(180,195,230,0.15);
  --text:       #ccd6f0;
  --dim:        #7a86a8;
  --faint:      rgba(180,195,230,0.05);
  --teal:       #6ee7df;
  --amber:      #f5c97e;
  --mauve:      #d4a0c8;
  --sage:       #86efac;
  --blue:       #93c5fd;
  --grid-color: rgba(110,231,223,0.025);
  --font-hdr:   'Bebas Neue', sans-serif;
  --font-ui:    'DM Sans', sans-serif;
  --font-mono:  'JetBrains Mono', monospace;
  --sidebar-w:  200px;
  --radius:     10px;
}

/* ── Neon theme override ── */
[data-theme="neon"] {
  --bg:         #07080f;
  --bg2:        #0a0b14;
  --surface:    #0d0f1c;
  --surface2:   #111320;
  --border:     rgba(0,245,212,0.1);
  --border2:    rgba(0,245,212,0.22);
  --text:       #c8d8f0;
  --dim:        #3a4d6a;
  --faint:      rgba(0,245,212,0.04);
  --teal:       #00f5d4;
  --amber:      #ffb700;
  --mauve:      #ff3cac;
  --sage:       #a78bfa;
  --blue:       #22d3ee;
  --grid-color: rgba(0,245,212,0.05);
}

html, body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.5;
  min-height: 100vh;
  transition: background 0.3s, color 0.3s;
}

/* subtle grid overlay */
body::after {
  content: '';
  position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background-image:
    linear-gradient(var(--grid-color) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid-color) 1px, transparent 1px);
  background-size: 44px 44px;
  transition: background-image 0.3s;
}

/* neon body glow scanline */
[data-theme="neon"] body::before {
  content: '';
  position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 2px,
    rgba(0,0,0,0.08) 2px,
    rgba(0,0,0,0.08) 4px
  );
}

/* ── Layout ── */
.layout { display: flex; min-height: 100vh; position: relative; z-index: 1; }

/* ── Sidebar ── */
.sidebar {
  width: var(--sidebar-w);
  min-height: 100vh;
  background: var(--bg2);
  border-right: 1px solid var(--border);
  position: sticky; top: 0; align-self: flex-start;
  height: 100vh; overflow-y: auto;
  display: flex; flex-direction: column;
  padding: 20px 0 24px;
  transition: background 0.3s, border-color 0.3s;
}
.sidebar-brand {
  padding: 0 18px 18px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 16px;
}
.sidebar-brand h1 {
  font-family: var(--font-hdr);
  font-size: 28px;
  letter-spacing: 2px;
  background: linear-gradient(135deg, var(--teal), var(--blue));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1;
}
[data-theme="neon"] .sidebar-brand h1 {
  filter: drop-shadow(0 0 8px var(--teal));
}
.sidebar-brand .tagline {
  font-size: 9px; letter-spacing: 2px; text-transform: uppercase;
  color: var(--dim); margin-top: 4px;
}
.nav-section-label {
  font-size: 9px; letter-spacing: 2px; text-transform: uppercase;
  color: var(--dim); padding: 8px 18px 4px;
}
.nav-link {
  display: block; padding: 7px 18px;
  color: var(--dim); text-decoration: none; font-size: 12px;
  border-left: 2px solid transparent;
  transition: all 0.15s;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.nav-link:hover { color: var(--text); background: var(--faint); }
.nav-link.active { color: var(--teal); border-left-color: var(--teal); background: rgba(110,231,223,0.05); }
[data-theme="neon"] .nav-link.active { background: rgba(0,245,212,0.06); }
.nav-link .nav-date { display: block; font-size: 11px; color: inherit; }
.nav-link .nav-meta { display: block; font-size: 9px; color: var(--dim); }
.nav-link.global-link { color: var(--amber); }
.nav-link.global-link:hover, .nav-link.global-link.active {
  color: var(--amber); border-left-color: var(--amber);
  background: rgba(245,201,126,0.06);
}
[data-theme="neon"] .nav-link.global-link:hover,
[data-theme="neon"] .nav-link.global-link.active {
  background: rgba(255,183,0,0.07);
}
.sidebar-footer {
  margin-top: auto; padding: 12px 18px 0;
  border-top: 1px solid var(--border);
  font-size: 9px; color: var(--dim); letter-spacing: 1px;
  line-height: 1.8;
}

/* ── Theme toggle button ── */
.theme-toggle {
  display: flex; align-items: center; gap: 7px;
  margin: 10px 18px 0;
  padding: 7px 12px;
  background: var(--surface);
  border: 1px solid var(--border2);
  border-radius: 20px;
  color: var(--dim);
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: 1.5px;
  text-transform: uppercase;
  cursor: pointer;
  transition: all 0.2s;
  width: calc(100% - 36px);
  justify-content: center;
}
.theme-toggle:hover {
  color: var(--teal);
  border-color: var(--teal);
  background: var(--faint);
}
[data-theme="neon"] .theme-toggle:hover {
  box-shadow: 0 0 10px rgba(0,245,212,0.2);
}
.theme-toggle-icon { font-size: 13px; }

/* ── Main content ── */
.content { flex: 1; padding: 24px 28px; min-width: 0; }

/* ── Dashboard sections ── */
.dashboard-section { margin-bottom: 48px; }
.dashboard-section + .dashboard-section {
  padding-top: 40px;
  border-top: 1px solid var(--border);
}
.section-header {
  display: flex; justify-content: space-between; align-items: baseline;
  margin-bottom: 16px;
}
.section-tag {
  font-size: 9px; letter-spacing: 2px; text-transform: uppercase;
  padding: 3px 8px; border-radius: 3px;
  margin-right: 10px; vertical-align: middle;
  font-family: var(--font-mono);
}
.section-tag-global { background: rgba(245,201,126,0.15); color: var(--amber); border: 1px solid rgba(245,201,126,0.3); }
.section-tag-daily  { background: rgba(110,231,223,0.1);  color: var(--teal);  border: 1px solid rgba(110,231,223,0.25); }
[data-theme="neon"] .section-tag-global { background: rgba(255,183,0,0.1); border-color: rgba(255,183,0,0.4); }
[data-theme="neon"] .section-tag-daily  { background: rgba(0,245,212,0.08); border-color: rgba(0,245,212,0.3); }
.section-title {
  font-family: var(--font-hdr); font-size: 26px; letter-spacing: 1.5px;
  color: #dde8ff; display: inline;
}
[data-theme="neon"] .section-title { text-shadow: 0 0 20px rgba(110,180,255,0.3); }
.section-meta { font-size: 11px; color: var(--dim); display: flex; gap: 6px; align-items: center; }

/* ── KPI Strip ── */
.kpi-strip {
  display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px;
  margin-bottom: 12px;
}
.kpi {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 13px 15px;
  position: relative; overflow: hidden;
  transition: border-color 0.2s, background 0.3s;
}
.kpi::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: var(--accent, var(--teal));
  opacity: 0.7;
  transition: opacity 0.3s;
}
[data-theme="neon"] .kpi::before { opacity: 1; box-shadow: 0 0 8px var(--accent, var(--teal)); }
.kpi:hover { border-color: var(--border2); }
.kpi-label { font-size: 9px; letter-spacing: 2px; text-transform: uppercase; color: var(--dim); margin-bottom: 5px; }
.kpi-value { font-family: var(--font-hdr); font-size: 28px; letter-spacing: 1px; color: #e8eeff; line-height: 1; }
.kpi-sub   { font-size: 9px; color: var(--dim); margin-top: 3px; }

/* ── Grid ── */
.main-grid {
  display: grid;
  grid-template-columns: 220px 1fr 1fr;
  grid-template-rows: auto auto;
  gap: 10px; margin-bottom: 10px;
}
.span2 { grid-column: span 2; }
.bottom-grid {
  display: grid; grid-template-columns: 1fr 210px; gap: 10px;
  margin-bottom: 10px;
}

/* ── Cards ── */
.card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 14px 16px;
  transition: background 0.3s, border-color 0.3s;
}
[data-theme="neon"] .card:hover { border-color: rgba(0,245,212,0.18); }
.card-title {
  font-family: var(--font-ui, var(--font-mono));
  font-size: 10px; font-weight: 600; letter-spacing: 2px;
  text-transform: uppercase; color: var(--dim); margin-bottom: 11px;
}

/* ── Gauge ── */
.gauge-card {
  display: flex; flex-direction: column; align-items: center;
  justify-content: flex-start; grid-row: 1 / 3; padding: 18px 14px;
}
.gauge-wrap { position: relative; width: 140px; height: 140px; margin: 6px auto 14px; }
.gauge-wrap svg { transform: rotate(-90deg); }
.gauge-bg   { fill: none; stroke: rgba(180,195,230,0.07); stroke-width: 9; }
[data-theme="neon"] .gauge-bg { stroke: rgba(0,245,212,0.06); }
.gauge-fill { fill: none; stroke-width: 9; stroke-linecap: round; }
.gauge-center {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
}
.gauge-pct { font-family: var(--font-hdr); font-size: 32px; line-height: 1; }
.gauge-lbl { font-size: 9px; color: var(--dim); letter-spacing: 2px; margin-top: 1px; }

/* ── Tier badges ── */
.tier-badges { display: flex; flex-direction: column; gap: 7px; width: 100%; }
.tier-badge {
  border: 1px solid; border-radius: 7px; padding: 7px 10px;
  display: flex; justify-content: space-between; align-items: center;
  transition: all 0.3s;
}
[data-theme="neon"] .tier-badge { box-shadow: inset 0 0 12px rgba(0,0,0,0.3); }
.tier-name  { font-size: 10px; letter-spacing: 1px; font-weight: 600; }
.tier-count { font-size: 9px; color: var(--dim); }
.tier-cost  { font-size: 10px; font-weight: 600; }

/* ── Charts ── */
.chart-wrap      { position: relative; height: 175px; }
.chart-wrap-tall { position: relative; height: 195px; }

/* ── Table ── */
.model-table { width: 100%; border-collapse: collapse; }
.model-table th {
  font-size: 9px; font-weight: 600; letter-spacing: 1.5px;
  text-transform: uppercase; color: var(--dim);
  text-align: right; padding: 3px 8px 7px;
  border-bottom: 1px solid var(--border);
}
.model-table th:first-child { text-align: left; }
.model-table td { padding: 6px 8px; border-bottom: 1px solid rgba(180,195,230,0.04); vertical-align: middle; }
.model-table tr:last-child td { border-bottom: none; }
.model-table tr:hover td { background: rgba(255,255,255,0.02); }
td.num { text-align: right; }
td.dim { color: var(--dim); }
.dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 7px; vertical-align: middle; }
[data-theme="neon"] .dot { box-shadow: 0 0 5px currentColor; }
.tok-cell { white-space: nowrap; }
.tok-breakdown { font-size: 9px; color: var(--dim); margin-left: 4px; letter-spacing: 0.5px; }
.model-name { font-size: 11px; vertical-align: middle; }
.pill { display: inline-block; padding: 2px 6px; border-radius: 20px; font-size: 10px; font-weight: 600; }

/* ── Misc ── */
.empty { color: var(--dim); padding: 24px; text-align: center; }
@keyframes fadeUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.kpi { animation: fadeUp 0.4s ease both; }
.kpi:nth-child(1){animation-delay:0.04s} .kpi:nth-child(2){animation-delay:0.08s}
.kpi:nth-child(3){animation-delay:0.12s} .kpi:nth-child(4){animation-delay:0.16s}
.kpi:nth-child(5){animation-delay:0.20s}
"""


def build_html(global_data, daily_data_list, generated_at, log_dir):
    # Sidebar nav links
    nav_daily = ""
    for d in daily_data_list:
        total_str = f"${d['total_cost']:.3f}" if d else "no data"
        sec_id    = f"day-{d['label']}" if d else ""
        nav_daily += (
            f'<a class="nav-link" href="#{sec_id}">'
            f'<span class="nav-date">{d["label"]}</span>'
            f'<span class="nav-meta">{d["total_requests"]} req · {total_str}</span>'
            f'</a>\n'
        )

    # Daily sections HTML
    daily_sections = ""
    for d in daily_data_list:
        daily_sections += render_section(d, f"day-{d['label']}", is_global=False)

    global_section = render_section(global_data, "global", is_global=True)

    total_days  = len(daily_data_list)
    total_req   = global_data["total_requests"] if global_data else 0
    total_cost  = global_data["total_cost"] if global_data else 0

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="pastel">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BlockRun Reports · {log_dir}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;600&family=JetBrains+Mono:wght@300;400;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js/dist/chart.umd.min.js"></script>
<style>{CSS}</style>
</head>
<body>

<script>
// ── Theme engine (runs before sections render) ──────────────────────────────
window.CHARTS = {{}};

window.applyTheme = function(theme, save) {{
  const neon = theme === 'neon';
  document.documentElement.setAttribute('data-theme', theme);
  if (save) localStorage.setItem('blockrun-theme', theme);

  const btn = document.getElementById('theme-toggle');
  if (btn) {{
    btn.querySelector('.theme-toggle-icon').textContent = neon ? '◎' : '◈';
    btn.querySelector('.theme-toggle-label').textContent = neon ? 'Pastel' : 'Neon';
  }}

  const grid   = neon ? 'rgba(0,245,212,0.06)'  : 'rgba(180,190,220,0.07)';
  const tick   = neon ? '#3a4d6a'                : '#7a86a8';
  const legend = neon ? '#5a7090'                : '#a8b4cc';
  const bbg    = neon ? 'rgba(58,77,106,0.3)'   : 'rgba(120,130,160,0.25)';
  const bbd    = neon ? 'rgba(58,77,106,0.7)'   : 'rgba(120,130,160,0.6)';
  const sbg    = neon ? 'rgba(0,245,212,0.1)'   : 'rgba(110,231,223,0.1)';
  const sbd    = neon ? '#00f5d4'                : '#6ee7df';
  const lbg    = neon ? 'rgba(255,183,0,0.18)'  : 'rgba(245,201,126,0.2)';
  const lbd    = neon ? '#ffb700'                : '#f5c97e';

  Object.values(window.CHARTS).forEach(reg => {{
    const ch = reg.chart;

    if (reg.role === 'donut') {{
      const colors = neon ? reg.neon.colors : reg.pastel.colors;
      const soft   = neon ? reg.neon.soft   : reg.pastel.soft;
      ch.data.datasets[0].borderColor     = colors;
      ch.data.datasets[0].backgroundColor = soft;
      ch.options.plugins.legend.labels.color = legend;

    }} else if (reg.role === 'bar') {{
      const colors = neon ? reg.neon.colors : reg.pastel.colors;
      const soft   = neon ? reg.neon.soft   : reg.pastel.soft;
      ch.data.datasets[0].backgroundColor = bbg;
      ch.data.datasets[0].borderColor     = bbd;
      ch.data.datasets[1].backgroundColor = soft;
      ch.data.datasets[1].borderColor     = colors;
      ch.data.datasets[2].backgroundColor = sbg;
      ch.data.datasets[2].borderColor     = sbd;
      ch.options.plugins.legend.labels.color   = legend;
      ch.options.scales.x.grid.color           = grid;
      ch.options.scales.x.ticks.color          = tick;
      ch.options.scales.y.grid.color           = grid;
      ch.options.scales.y.ticks.color          = tick;

    }} else if (reg.role === 'tl') {{
      const ds = neon ? reg.neon.tl : reg.pastel.tl;
      ds.forEach((d, i) => {{
        if (ch.data.datasets[i]) {{
          ch.data.datasets[i].borderColor     = d.borderColor;
          ch.data.datasets[i].backgroundColor = d.backgroundColor;
        }}
      }});
      ch.options.plugins.legend.labels.color   = legend;
      ch.options.scales.x.grid.color           = grid;
      ch.options.scales.x.ticks.color          = tick;
      ch.options.scales.y.grid.color           = grid;
      ch.options.scales.y.ticks.color          = tick;

    }} else if (reg.role === 'lat') {{
      ch.data.datasets[0].backgroundColor = lbg;
      ch.data.datasets[0].borderColor     = lbd;
      ch.options.scales.x.grid.color      = grid;
      ch.options.scales.x.ticks.color     = tick;
      ch.options.scales.y.grid.color      = grid;
      ch.options.scales.y.ticks.color     = tick;
    }}

    ch.update('none');
  }});
}};

// Restore saved theme (before sections create their charts)
const _saved = localStorage.getItem('blockrun-theme') || 'pastel';
if (_saved !== 'pastel') document.documentElement.setAttribute('data-theme', _saved);
</script>

<div class="layout">

  <!-- ── Sidebar ── -->
  <nav class="sidebar">
    <div class="sidebar-brand">
      <h1>BlockRun</h1>
      <div class="tagline">Usage Reports</div>
    </div>

    <div class="nav-section-label">Overview</div>
    <a class="nav-link global-link" href="#global">
      <span class="nav-date">All Days</span>
      <span class="nav-meta">{total_req:,} req · ${total_cost:.3f}</span>
    </a>

    <div class="nav-section-label">Daily</div>
    {nav_daily}

    <div class="sidebar-footer">
      {total_days} day(s) ingested<br>
      Generated {generated_at}<br>
      BlockRun Intelligence
      <button class="theme-toggle" id="theme-toggle"
        onclick="applyTheme(document.documentElement.getAttribute('data-theme')==='neon'?'pastel':'neon', true)">
        <span class="theme-toggle-icon">◈</span>
        <span class="theme-toggle-label">Neon</span>
      </button>
    </div>
  </nav>

  <!-- ── Main content ── -->
  <main class="content">
    {global_section}
    {daily_sections}
  </main>

</div>

<script>
// Highlight active nav link on scroll
const sections = document.querySelectorAll('.dashboard-section');
const links    = document.querySelectorAll('.nav-link');
const observer = new IntersectionObserver(entries => {{
  entries.forEach(e => {{
    if (e.isIntersecting) {{
      links.forEach(l => l.classList.remove('active'));
      const a = document.querySelector('.nav-link[href="#' + e.target.id + '"]');
      if (a) a.classList.add('active');
    }}
  }});
}}, {{ threshold: 0.25 }});
sections.forEach(s => observer.observe(s));

// Sync toggle button label to saved theme after everything is rendered
applyTheme(localStorage.getItem('blockrun-theme') || 'pastel', false);
</script>
</body>
</html>"""


# ─── Entry point ─────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python3 generate_reports.py <log_dir> [output_path]", file=sys.stderr)
        sys.exit(1)

    log_dir = sys.argv[1]
    if not os.path.isdir(log_dir):
        print(f"Error: '{log_dir}' is not a directory", file=sys.stderr)
        sys.exit(1)

    output_path = sys.argv[2] if len(sys.argv) == 3 else os.path.join(log_dir, "report.html")

    daily_files = find_daily_files(log_dir)
    if not daily_files:
        print(f"Error: no usage-*.jsonl files found in {log_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(daily_files)} daily file(s). Loading...", file=sys.stderr)

    all_entries    = []
    daily_data_list = []
    for date_str, fp in daily_files:
        entries = load_jsonl(fp)
        print(f"  {date_str}: {len(entries)} entries", file=sys.stderr)
        all_entries.extend(entries)
        d = aggregate(entries, label=date_str)
        if d:
            daily_data_list.append(d)

    # Most recent day first
    daily_data_list.sort(key=lambda x: x["label"], reverse=True)

    global_data  = aggregate(all_entries, label="global")
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html         = build_html(global_data, daily_data_list, generated_at, os.path.basename(log_dir))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nReport written → {output_path}", file=sys.stderr)
    print(f"  {global_data['total_requests']:,} total requests  "
          f"${global_data['total_cost']:.4f} cost  "
          f"{global_data['savings_rate']:.1f}% savings rate", file=sys.stderr)


if __name__ == "__main__":
    main()
