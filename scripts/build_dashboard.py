"""Render the 6-panel dashboard defined in config/dashboard.yaml from data/logs.jsonl.

Usage:
    python scripts/build_dashboard.py            # one-shot -> data/dashboard.html
    python scripts/build_dashboard.py --watch    # regenerate every refresh_seconds
    python scripts/build_dashboard.py --all      # ignore the time window (whole log)

Pure standard library + PyYAML; charts are inline SVG so the page works offline.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = REPO_ROOT / "data" / "logs.jsonl"
DEFAULT_CONFIG = REPO_ROOT / "config" / "dashboard.yaml"
DEFAULT_OUT = REPO_ROOT / "data" / "dashboard.html"

COLORS = ["#2563eb", "#f59e0b", "#dc2626", "#059669"]


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct / 100
    lo, hi = int(rank), min(int(rank) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


def load_records(path: Path) -> list[dict]:
    records = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
            rec["_t"] = datetime.fromisoformat(rec["ts"].replace("Z", "+00:00"))
            records.append(rec)
        except (ValueError, KeyError):
            continue
    return records


def minute_key(t: datetime) -> datetime:
    return t.replace(second=0, microsecond=0)


def bucket(records: list[dict]) -> list[datetime]:
    """Continuous list of minute buckets covering the records."""
    if not records:
        return []
    start, end = minute_key(min(r["_t"] for r in records)), minute_key(max(r["_t"] for r in records))
    out, cur = [], start
    while cur <= end:
        out.append(cur)
        cur += timedelta(minutes=1)
    return out


def check(threshold: dict, value: float | None) -> bool | None:
    if value is None:
        return None
    limit = threshold["value"]
    return value <= limit if threshold["operator"] == "lte" else value >= limit


def fmt(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value:,.{digits}f}"


# ---------- SVG helpers ----------

W, H, PAD_L, PAD_R, PAD_T, PAD_B = 520, 190, 46, 10, 10, 26


def _scale(values: list[float], threshold: float | None) -> tuple[float, float]:
    pool = [v for v in values if v is not None]
    if threshold is not None:
        pool.append(threshold)
    hi = max(pool) if pool else 1.0
    return 0.0, (hi * 1.15 if hi > 0 else 1.0)


def chart(
    labels: list[str],
    series: dict[str, list[float | None]],
    *,
    threshold: float | None = None,
    kind: str = "line",
    unit: str = "",
) -> str:
    n = max(len(labels), 1)
    all_values = [v for s in series.values() for v in s]
    lo, hi = _scale(all_values, threshold)
    plot_w, plot_h = W - PAD_L - PAD_R, H - PAD_T - PAD_B

    def x(i: int) -> float:
        return PAD_L + (plot_w * (i + 0.5) / n)

    def y(v: float) -> float:
        return PAD_T + plot_h * (1 - (v - lo) / (hi - lo))

    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" class="chart">']
    for frac in (0, 0.5, 1):
        val = lo + (hi - lo) * frac
        yy = y(val)
        parts.append(f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{yy:.1f}" y2="{yy:.1f}" class="grid"/>')
        parts.append(f'<text x="{PAD_L - 4}" y="{yy + 3:.1f}" class="axis" text-anchor="end">{val:,.3g}</text>')
    step = max(1, n // 6)
    for i in range(0, len(labels), step):
        parts.append(f'<text x="{x(i):.1f}" y="{H - 8}" class="axis" text-anchor="middle">{html.escape(labels[i])}</text>')

    if kind == "bar":
        group = max(len(series), 1)
        bar_w = max(2.0, plot_w / n / group * 0.7)
        for si, values in enumerate(series.values()):
            for i, v in enumerate(values):
                if v is None:
                    continue
                bx = x(i) - bar_w * group / 2 + si * bar_w
                parts.append(
                    f'<rect x="{bx:.1f}" y="{y(v):.1f}" width="{bar_w:.1f}" height="{y(lo) - y(v):.1f}" '
                    f'fill="{COLORS[si % 4]}"><title>{v:,.4g}</title></rect>'
                )
    else:
        for si, values in enumerate(series.values()):
            pts = [f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(values) if v is not None]
            color = COLORS[si % 4]
            if len(pts) > 1:
                parts.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2"/>')
            for i, v in enumerate(values):
                if v is not None:
                    parts.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="3" fill="{color}"><title>{v:,.4g}</title></circle>')

    if threshold is not None:
        ty = y(threshold)
        parts.append(f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{ty:.1f}" y2="{ty:.1f}" class="thr"/>')
        parts.append(f'<text x="{W - PAD_R}" y="{ty - 3:.1f}" class="thr-label" text-anchor="end">threshold {threshold:g} {html.escape(unit)}</text>')
    if not labels:
        parts.append(f'<text x="{W / 2}" y="{H / 2}" class="axis" text-anchor="middle">no data in window</text>')
    parts.append("</svg>")
    legend = "".join(
        f'<span class="lg"><i style="background:{COLORS[i % 4]}"></i>{html.escape(name)}</span>'
        for i, name in enumerate(series)
    )
    return "".join(parts) + f'<div class="legend">{legend}</div>'


# ---------- panels ----------

def panel_card(panel: dict, stats: list[tuple[str, str]], ok: bool | None, body: str) -> str:
    thr = panel["threshold"]
    state = {True: ("ok", "OK"), False: ("bad", "BREACH"), None: ("na", "NO DATA")}[ok]
    ops = {"lte": "≤", "gte": "≥"}[thr["operator"]]
    stat_html = "".join(f'<div class="stat"><b>{html.escape(v)}</b><span>{html.escape(k)}</span></div>' for k, v in stats)
    return (
        f'<section class="card"><header><h2>{html.escape(panel["title"])}</h2>'
        f'<span class="badge {state[0]}">{state[1]}</span></header>'
        f'<p class="sub">unit: {html.escape(panel["unit"])} · SLO {html.escape(thr["aggregation"])} {ops} {thr["value"]:g}</p>'
        f'<div class="stats">{stat_html}</div>{body}</section>'
    )


def build_panels(cfg: dict, records: list[dict]) -> list[str]:
    panels = {p["id"]: p for p in cfg["panels"]}
    buckets = bucket(records)
    labels = [b.astimezone().strftime("%H:%M") for b in buckets]
    index = {b: i for i, b in enumerate(buckets)}
    sent = [r for r in records if r.get("event") == "response_sent"]
    received = [r for r in records if r.get("event") == "request_received"]
    failed = [r for r in records if r.get("event") == "request_failed"]

    def per_minute(rows: list[dict], fn) -> list[float | None]:
        groups: dict[int, list[dict]] = defaultdict(list)
        for r in rows:
            groups[index[minute_key(r["_t"])]].append(r)
        return [fn(groups[i]) if groups.get(i) else None for i in range(len(buckets))]

    def vals(rows: list[dict], key: str) -> list[float]:
        return [r[key] for r in rows if r.get(key) is not None]

    out = []

    # 1. latency
    p = panels["latency"]
    lat, ttft = vals(sent, "latency_ms"), vals(sent, "ttft_ms")
    p50, p95, p99, t95 = (percentile(lat, 50), percentile(lat, 95), percentile(lat, 99), percentile(ttft, 95))
    series = {
        "P50": per_minute(sent, lambda g: percentile(vals(g, "latency_ms"), 50)),
        "P95": per_minute(sent, lambda g: percentile(vals(g, "latency_ms"), 95)),
        "P99": per_minute(sent, lambda g: percentile(vals(g, "latency_ms"), 99)),
        "TTFT P95": per_minute(sent, lambda g: percentile(vals(g, "ttft_ms"), 95)),
    }
    out.append(panel_card(p, [("P50", fmt(p50, 0)), ("P95", fmt(p95, 0)), ("P99", fmt(p99, 0)), ("TTFT P95", fmt(t95, 0))],
                          check(p["threshold"], p95), chart(labels, series, threshold=p["threshold"]["value"], unit="ms")))

    # 2. traffic
    p = panels["traffic"]
    counts = per_minute(received, len)
    counts = [c or 0 for c in counts]
    rate = (sum(counts) / len(counts)) if counts else None
    out.append(panel_card(p, [("requests", str(len(received))), ("avg req/min", fmt(rate, 1))],
                          check(p["threshold"], rate),
                          chart(labels, {"requests/min": counts}, threshold=p["threshold"]["value"], kind="bar", unit="req/min")))

    # 3. errors + retrieval success
    p = panels["errors"]
    err_rate = (len(failed) / len(received) * 100) if received else None
    tool_rows = [r for r in records if r.get("tool_success") is not None]
    tool_rate = (sum(1 for r in tool_rows if r["tool_success"]) / len(tool_rows) * 100) if tool_rows else None
    by_type = Counter(r.get("error_type") or "unknown" for r in failed)
    err_series = per_minute(failed, len)
    err_series = [c or 0 for c in err_series]
    breakdown = ", ".join(f"{html.escape(k)}: {v}" for k, v in by_type.most_common()) or "none"
    body = chart(labels, {"errors/min": err_series}, threshold=None, kind="bar") + f'<p class="sub">error_type breakdown: {breakdown}</p>'
    out.append(panel_card(p, [("error rate %", fmt(err_rate, 2)), ("retrieval success %", fmt(tool_rate, 1)), ("failed", str(len(failed)))],
                          check(p["threshold"], err_rate), body))

    # 4. cost
    p = panels["cost"]
    total_cost = sum(vals(sent, "cost_usd"))
    cost_series = per_minute(sent, lambda g: sum(vals(g, "cost_usd")))
    out.append(panel_card(p, [("total USD", fmt(total_cost, 4)), ("avg / request", fmt(total_cost / len(sent) if sent else None, 5))],
                          check(p["threshold"], total_cost if sent else None),
                          chart(labels, {"USD/min": cost_series}, threshold=p["threshold"]["value"], unit="USD")))

    # 5. tokens
    p = panels["tokens"]
    t_in, t_out = sum(vals(sent, "tokens_in")), sum(vals(sent, "tokens_out"))
    series = {
        "tokens_in": per_minute(sent, lambda g: sum(vals(g, "tokens_in"))),
        "tokens_out": per_minute(sent, lambda g: sum(vals(g, "tokens_out"))),
    }
    out.append(panel_card(p, [("tokens in", f"{t_in:,}"), ("tokens out", f"{t_out:,}")],
                          check(p["threshold"], max(t_in, t_out) if sent else None),
                          chart(labels, series, threshold=p["threshold"]["value"], kind="bar", unit="tokens")))

    # 6. quality
    p = panels["quality"]
    q = vals(sent, "quality_score")
    q_mean = sum(q) / len(q) if q else None
    out.append(panel_card(p, [("mean quality", fmt(q_mean, 2)), ("samples", str(len(q)))],
                          check(p["threshold"], q_mean),
                          chart(labels, {"mean": per_minute(sent, lambda g: (sum(vals(g, "quality_score")) / max(1, len(vals(g, "quality_score")))) if vals(g, "quality_score") else None)},
                                threshold=p["threshold"]["value"], unit="score")))
    return out


CSS = """
:root{--bg:#f6f7f9;--fg:#111827;--card:#fff;--mut:#6b7280;--grid:#e5e7eb;--ok:#059669;--bad:#dc2626;--na:#6b7280}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--fg:#e5e7eb;--card:#181b22;--mut:#9ca3af;--grid:#2a2f3a}}
*{box-sizing:border-box}body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif}
h1{font-size:18px;margin:0 0 2px}.meta{color:var(--mut);margin:0 0 14px}
.grid-wrap{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:12px}
.card{background:var(--card);border-radius:10px;padding:12px 14px;box-shadow:0 1px 2px rgba(0,0,0,.08)}
.card header{display:flex;justify-content:space-between;align-items:center}h2{font-size:15px;margin:0}
.sub{color:var(--mut);font-size:12px;margin:2px 0 6px}
.badge{font-size:11px;font-weight:700;padding:2px 8px;border-radius:99px;color:#fff}
.badge.ok{background:var(--ok)}.badge.bad{background:var(--bad)}.badge.na{background:var(--na)}
.stats{display:flex;gap:16px;flex-wrap:wrap;margin:6px 0}.stat b{display:block;font-size:20px}.stat span{color:var(--mut);font-size:11px}
.chart{width:100%;height:auto}.grid{stroke:var(--grid)}.axis{fill:var(--mut);font-size:10px}
.thr{stroke:var(--bad);stroke-dasharray:5 4;stroke-width:1.5}.thr-label{fill:var(--bad);font-size:10px}
.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;color:var(--mut)}.lg i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px}
"""


def render(cfg: dict, records: list[dict], window_label: str) -> str:
    dash = cfg["dashboard"]
    cards = "".join(build_panels(dash, records))
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta http-equiv="refresh" content="{dash["refresh_seconds"]}"><title>{html.escape(dash["title"])}</title><style>{CSS}</style></head><body>'
        f'<h1>{html.escape(dash["title"])}</h1>'
        f'<p class="meta">Source: data/logs.jsonl · {html.escape(window_label)} · refresh {dash["refresh_seconds"]}s · generated {now}</p>'
        f'<div class="grid-wrap">{cards}</div></body></html>'
    )


def build(log_path: Path, config_path: Path, out_path: Path, use_all: bool) -> Path:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    minutes = cfg["dashboard"]["time_range_minutes"]
    records = load_records(log_path)
    if use_all:
        label = f"time range: all records ({len(records)})"
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        records = [r for r in records if r["_t"] >= cutoff]
        label = f"time range: last {minutes} min ({len(records)} records)"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(cfg, records, label), encoding="utf-8")
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--all", action="store_true", help="ignore the time window")
    ap.add_argument("--watch", action="store_true", help="regenerate every refresh_seconds")
    args = ap.parse_args()

    refresh = yaml.safe_load(args.config.read_text(encoding="utf-8"))["dashboard"]["refresh_seconds"]
    while True:
        path = build(args.log, args.config, args.out, args.all)
        print(f"wrote {path}", file=sys.stderr)
        if not args.watch:
            break
        time.sleep(refresh)


if __name__ == "__main__":
    main()
