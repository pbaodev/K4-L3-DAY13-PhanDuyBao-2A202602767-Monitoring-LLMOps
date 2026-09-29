from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx

from app import logging_config
from app.main import app

BODY = {
    "user_id": "student-01",
    "session_id": "session-01",
    "feature": "qa",
    "message": "My email is a.b@example.com, phone 0901234567, card 4111 1111 1111 1111",
}


def _post(headers: dict[str, str] | None = None, count: int = 1) -> list[httpx.Response]:
    async def go() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return [await client.post("/chat", json=BODY, headers=headers) for _ in range(count)]

    return asyncio.run(go())


def _events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_generates_request_id_and_returns_it(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")
    (response,) = _post()
    assert re.fullmatch(r"req-[0-9a-f]{8}", response.headers["x-request-id"])
    assert response.json()["correlation_id"] == response.headers["x-request-id"]
    assert int(response.headers["x-response-time-ms"]) >= 0


def test_accepts_client_request_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")
    (response,) = _post({"x-request-id": "req-deadbeef"})
    assert response.headers["x-request-id"] == "req-deadbeef"


def test_rejects_unsafe_request_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")
    (response,) = _post({"x-request-id": 'bad id"with spaces'})
    assert re.fullmatch(r"req-[0-9a-f]{8}", response.headers["x-request-id"])


def test_logs_are_enriched_scrubbed_and_isolated(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)
    responses = _post(count=2)

    api_events = [e for e in _events(log_path) if e["service"] == "api"]
    assert {e["correlation_id"] for e in api_events} == {
        r.headers["x-request-id"] for r in responses
    }
    for event in api_events:
        for field in ("user_id_hash", "session_id", "feature", "model", "env"):
            assert event[field]
        assert event["user_id_hash"] != "student-01"

    raw = log_path.read_text(encoding="utf-8")
    for secret in ("a.b@example.com", "0901234567", "4111 1111 1111 1111"):
        assert secret not in raw
