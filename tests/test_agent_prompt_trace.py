from __future__ import annotations

from contextlib import contextmanager

from app import agent as agent_module


class ManagedPrompt:
    version = 3

    def compile(self, **variables: str) -> str:
        return (
            f"Feature={variables['feature']}\n"
            f"Docs={variables['docs']}\n"
            f"Question={variables['message']}"
        )


class RecordingLangfuseClient:
    def __init__(self) -> None:
        self.prompt = ManagedPrompt()
        self.span_updates: list[dict] = []

    def get_prompt(self, name: str, **kwargs):
        return self.prompt

    def update_current_span(self, **kwargs) -> None:
        self.span_updates.append(kwargs)


def test_agent_records_prompt_version_with_v4_observation_api(monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_PROMPT_NAME", "day13-chat")
    monkeypatch.setenv("LANGFUSE_PROMPT_LABEL", "production")
    client = RecordingLangfuseClient()
    monkeypatch.setattr(agent_module, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(agent_module, "tracing_enabled", lambda: True)

    propagated: list[dict] = []

    @contextmanager
    def record_attributes(**kwargs):
        propagated.append(kwargs)
        yield

    monkeypatch.setattr(agent_module, "propagate_attributes", record_attributes)

    agent = agent_module.LabAgent()
    agent_module.LabAgent.run.__wrapped__(
        agent,
        user_id="student-01",
        feature="qa",
        session_id="session-01",
        message="Explain traces",
        correlation_id="req-12345678",
    )

    span_update = client.span_updates[-1]
    assert span_update["metadata"] == {
        "doc_count": 1,
        "query_preview": "Explain traces",
        "prompt_name": "day13-chat",
        "prompt_label": "production",
        "prompt_version": "3",
        "prompt_source": "langfuse",
        "prompt_fetch_error": "",
    }
    assert span_update["version"] == "3"
    assert propagated[0]["metadata"]["correlation_id"] == "req-12345678"
    assert propagated[-1]["prompt"] is client.prompt


class FakeObservation:
    def __init__(self, kwargs: dict) -> None:
        self.kwargs = kwargs
        self.updates: list[dict] = []

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


class ObservationClient(RecordingLangfuseClient):
    def __init__(self) -> None:
        super().__init__()
        self.observations: list[FakeObservation] = []

    def start_as_current_observation(self, **kwargs) -> FakeObservation:
        obs = FakeObservation(kwargs)
        self.observations.append(obs)
        return obs


def test_agent_emits_retriever_and_generation_children_without_raw_pii(monkeypatch) -> None:
    client = ObservationClient()
    monkeypatch.setattr(agent_module, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(agent_module, "tracing_enabled", lambda: True)

    agent_module.LabAgent.run.__wrapped__(
        agent_module.LabAgent(),
        user_id="student-01",
        feature="qa",
        session_id="session-01",
        message="Refund policy? email a.b@example.com",
        correlation_id="req-12345678",
    )

    retriever, generation = client.observations
    assert retriever.kwargs["as_type"] == "retriever"
    assert generation.kwargs["as_type"] == "generation"
    assert generation.kwargs["model"] == "claude-sonnet-4-5"
    assert generation.kwargs["prompt"] is client.prompt

    update = generation.updates[-1]
    assert update["usage_details"]["input"] > 0 and update["usage_details"]["output"] > 0
    assert update["cost_details"]["total"] > 0

    captured = repr([o.kwargs for o in client.observations]) + repr(update)
    assert "a.b@example.com" not in captured
