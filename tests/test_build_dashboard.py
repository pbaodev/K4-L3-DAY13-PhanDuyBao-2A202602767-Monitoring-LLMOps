from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.build_dashboard import build, percentile

ROOT = Path(__file__).resolve().parents[1]


def _log(ts: datetime, event: str, **fields) -> str:
    return json.dumps({"ts": ts.isoformat().replace("+00:00", "Z"), "event": event, "level": "info", **fields})


def test_percentile_interpolates() -> None:
    assert percentile([], 95) is None
    assert percentile([10], 99) == 10
    assert percentile([0, 100], 50) == 50
    assert percentile(list(range(1, 101)), 95) == 95.05


def test_dashboard_renders_six_panels_with_threshold_state(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    lines = []
    for i in range(6):
        t = now - timedelta(minutes=i)
        lines.append(_log(t, "request_received"))
        lines.append(_log(t, "response_sent", latency_ms=5000 if i == 0 else 400, ttft_ms=50,
                          tokens_in=30, tokens_out=100, cost_usd=0.002, quality_score=0.9,
                          tool_name="retrieval", tool_success=True))
    lines.append(_log(now, "request_received"))
    lines.append(_log(now, "request_failed", error_type="RuntimeError", tool_name="retrieval", tool_success=False))
    log = tmp_path / "logs.jsonl"
    log.write_text("\n".join(lines), encoding="utf-8")

    out = build(log, ROOT / "config" / "dashboard.yaml", tmp_path / "d.html", use_all=False)
    page = out.read_text(encoding="utf-8")

    assert page.count('class="card"') == 6
    for title in ("Latency percentiles and TTFT", "Request traffic", "Error rate and retrieval success",
                  "Cost over time", "Input and output tokens", "Quality proxy"):
        assert title in page
    assert "RuntimeError: 1" in page
    assert "TTFT P95" in page and "retrieval success %" in page


def test_dashboard_handles_empty_log(tmp_path: Path) -> None:
    out = build(tmp_path / "missing.jsonl", ROOT / "config" / "dashboard.yaml", tmp_path / "d.html", use_all=False)
    assert "NO DATA" in out.read_text(encoding="utf-8")
