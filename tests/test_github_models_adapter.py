"""
tests/test_github_models_adapter.py

Focused tests for app.analysis.adapters.github_models.

Coverage (13 tests)
-------------------
 1. test_config_defaults                      — GitHubModelsConfig default field values
 2. test_config_rejects_empty_model_id        — ValueError on empty model_id
 3. test_config_rejects_non_positive_timeout  — ValueError on timeout <= 0
 4. test_config_is_frozen                     — frozen dataclass immutability
 5. test_build_headers_contain_required_fields — all 4 required headers present + correct values
 6. test_build_payload_without_temperature    — payload shape; temperature omitted when None
 7. test_build_payload_includes_temperature   — temperature included in payload when configured
 8. test_missing_token_raises_error           — MissingTokenError when env var absent
 9. test_empty_rendered_messages_raises_error — EmptyRenderedMessagesError on empty list
10. test_successful_response_parsing          — AnalysisResponse built correctly from API reply
11. test_provider_info_filled_from_config     — provider_info populated from config + response
12. test_import_surface                       — new names importable from app.analysis.adapters
13. test_protocol_compatibility               — isinstance(adapter, AnalysisAdapter) is True
"""

from __future__ import annotations

import dataclasses
import json

import pytest

# ---------------------------------------------------------------------------
# Import surface (test 12 validates these don't raise)
# ---------------------------------------------------------------------------

from app.analysis.adapters import (
    AnalysisAdapter,
    ChatMessage,
    EmptyRenderedMessagesError,
    GitHubModelsAdapter,
    GitHubModelsAPIError,
    GitHubModelsConfig,
    GitHubModelsError,
    MissingTokenError,
    PromptRenderer,
)
from app.analysis.adapters.contracts import (
    AnalysisInput,
    PromptProfile,
    PromptTaskType,
)


# ---------------------------------------------------------------------------
# Shared stubs and helpers
# ---------------------------------------------------------------------------


def _make_config(
    model_id: str = "gpt-4o",
    temperature: float | None = None,
    timeout: int = 30,
) -> GitHubModelsConfig:
    return GitHubModelsConfig(
        model_id=model_id,
        timeout=timeout,
        temperature=temperature,
    )


def _make_profile() -> PromptProfile:
    return PromptProfile(
        profile_name="default",
        task_type=PromptTaskType.SUMMARY,
        version="1.0.0",
    )


def _make_analysis_input() -> AnalysisInput:
    return AnalysisInput(
        chains=(),
        evidence_bundles=(),
        prompt_profile=_make_profile(),
    )


class _StubRenderer:
    """Minimal PromptRenderer stub returning a fixed single message."""

    def render(self, analysis_input: AnalysisInput) -> list[ChatMessage]:
        return [ChatMessage(role="user", content="Analyse this.")]


class _EmptyRenderer:
    """PromptRenderer stub that always returns an empty list."""

    def render(self, analysis_input: AnalysisInput) -> list[ChatMessage]:
        return []


class _FakeResponse:
    """Fake HTTP response with getcode() / read() interface."""

    def __init__(self, body: str, code: int = 200) -> None:
        self._body = body.encode("utf-8")
        self._code = code

    def getcode(self) -> int:
        return self._code

    def read(self) -> bytes:
        return self._body


def _make_open_func(body: str, code: int = 200):
    """Return a callable that ignores the request and returns _FakeResponse."""
    fake = _FakeResponse(body, code)

    def _open(req, *, timeout=None, **kwargs):
        return fake

    return _open


def _make_api_response_body(
    chain_id: str = "chain-1",
    model_version: str = "gpt-4o-2024-11-20",
) -> str:
    """Build a minimal GitHub Models API JSON response body."""
    content = json.dumps(
        {
            "chain_results": [
                {
                    "chain_id": chain_id,
                    "summary": "AI芯片供应链摘要。",
                    "completion_notes": "补全说明。",
                    "key_entities": ["公司A", "公司B"],
                    "confidence": 0.9,
                }
            ],
            "ranking": {
                "entries": [
                    {
                        "chain_id": chain_id,
                        "rank": 1,
                        "score": 0.85,
                        "rationale": "最相关的投资链路。",
                    }
                ]
            },
        }
    )
    return json.dumps(
        {
            "id": "chatcmpl-test",
            "model": model_version,
            "choices": [
                {
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
        }
    )


def _make_adapter(
    config: GitHubModelsConfig | None = None,
    renderer=None,
    env: dict | None = None,
    open_func=None,
) -> GitHubModelsAdapter:
    return GitHubModelsAdapter(
        config=config or _make_config(),
        renderer=renderer or _StubRenderer(),
        env=env if env is not None else {"GITHUB_TOKEN": "ghp_test_token"},
        _open_func=open_func or _make_open_func(_make_api_response_body()),
    )


# ---------------------------------------------------------------------------
# 1. Config defaults
# ---------------------------------------------------------------------------


def test_config_defaults() -> None:
    """GitHubModelsConfig default fields match official API values."""
    cfg = GitHubModelsConfig(model_id="gpt-4o")

    assert cfg.endpoint == "https://models.github.ai/inference/chat/completions"
    assert cfg.api_version == "2022-11-28"
    assert cfg.token_env_var == "GITHUB_TOKEN"
    assert cfg.timeout == 60
    assert cfg.temperature is None


# ---------------------------------------------------------------------------
# 2. Config rejects empty model_id
# ---------------------------------------------------------------------------


def test_config_rejects_empty_model_id() -> None:
    """GitHubModelsConfig raises ValueError for an empty model_id."""
    with pytest.raises(ValueError, match="model_id"):
        GitHubModelsConfig(model_id="")


# ---------------------------------------------------------------------------
# 3. Config rejects non-positive timeout
# ---------------------------------------------------------------------------


def test_config_rejects_non_positive_timeout() -> None:
    """GitHubModelsConfig raises ValueError for timeout <= 0."""
    with pytest.raises(ValueError, match="timeout"):
        GitHubModelsConfig(model_id="gpt-4o", timeout=0)


# ---------------------------------------------------------------------------
# 4. Config is frozen
# ---------------------------------------------------------------------------


def test_config_is_frozen() -> None:
    """GitHubModelsConfig is immutable (frozen dataclass)."""
    cfg = GitHubModelsConfig(model_id="gpt-4o")
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.model_id = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 5. Headers contain all required fields
# ---------------------------------------------------------------------------


def test_build_headers_contain_required_fields() -> None:
    """
    _build_headers returns exactly the four headers required by the GitHub
    Models API with correct values.
    """
    cfg = GitHubModelsConfig(model_id="gpt-4o", api_version="2022-11-28")
    adapter = _make_adapter(config=cfg)

    headers = adapter._build_headers("ghp_mytoken")

    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["Authorization"] == "Bearer ghp_mytoken"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"
    assert headers["Content-Type"] == "application/json"


# ---------------------------------------------------------------------------
# 6. Payload shape without temperature
# ---------------------------------------------------------------------------


def test_build_payload_without_temperature() -> None:
    """
    _build_payload includes model, messages, and response_format; omits
    temperature when it is None.
    """
    cfg = _make_config(model_id="gpt-4o-mini", temperature=None)
    adapter = _make_adapter(config=cfg)
    messages = [ChatMessage(role="user", content="Hello")]

    payload = adapter._build_payload(messages)

    assert payload["model"] == "gpt-4o-mini"
    assert payload["messages"] == [{"role": "user", "content": "Hello"}]
    assert payload["response_format"] == {"type": "json_object"}
    assert "temperature" not in payload


# ---------------------------------------------------------------------------
# 7. Payload includes temperature when configured
# ---------------------------------------------------------------------------


def test_build_payload_includes_temperature() -> None:
    """temperature is present in the payload when set in config."""
    cfg = _make_config(temperature=0.3)
    adapter = _make_adapter(config=cfg)
    messages = [ChatMessage(role="user", content="Hello")]

    payload = adapter._build_payload(messages)

    assert payload["temperature"] == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# 8. Missing token raises MissingTokenError
# ---------------------------------------------------------------------------


def test_missing_token_raises_error() -> None:
    """MissingTokenError is raised when the token env var is absent."""
    adapter = _make_adapter(env={})  # empty env → token missing

    with pytest.raises(MissingTokenError, match="GITHUB_TOKEN"):
        adapter.analyse(_make_analysis_input())


# ---------------------------------------------------------------------------
# 9. Empty rendered messages raises EmptyRenderedMessagesError
# ---------------------------------------------------------------------------


def test_empty_rendered_messages_raises_error() -> None:
    """EmptyRenderedMessagesError is raised when renderer returns []."""
    adapter = _make_adapter(renderer=_EmptyRenderer())

    with pytest.raises(EmptyRenderedMessagesError):
        adapter.analyse(_make_analysis_input())


# ---------------------------------------------------------------------------
# 10. Successful response parsing
# ---------------------------------------------------------------------------


def test_successful_response_parsing() -> None:
    """
    analyse() correctly parses an API response into a complete AnalysisResponse
    with chain_results, ranking, and provider_info.
    """
    profile = _make_profile()
    adapter = _make_adapter(
        open_func=_make_open_func(_make_api_response_body(chain_id="chain-1"))
    )

    result = adapter.analyse(
        AnalysisInput(chains=(), evidence_bundles=(), prompt_profile=profile)
    )

    assert len(result.chain_results) == 1
    cr = result.chain_results[0]
    assert cr.chain_id == "chain-1"
    assert cr.summary == "AI芯片供应链摘要。"
    assert cr.completion_notes == "补全说明。"
    assert cr.key_entities == ("公司A", "公司B")
    assert cr.confidence == pytest.approx(0.9)
    assert cr.prompt_profile == profile

    assert len(result.ranking.entries) == 1
    entry = result.ranking.entries[0]
    assert entry.chain_id == "chain-1"
    assert entry.rank == 1
    assert entry.score == pytest.approx(0.85)
    assert result.ranking.prompt_profile == profile


# ---------------------------------------------------------------------------
# 11. Provider metadata populated from config + response
# ---------------------------------------------------------------------------


def test_provider_info_filled_from_config() -> None:
    """
    provider_info.provider == 'github_models', model_id from config, model_version
    from the API response 'model' field, and endpoint from config.
    """
    cfg = GitHubModelsConfig(model_id="gpt-4o")
    adapter = _make_adapter(
        config=cfg,
        open_func=_make_open_func(
            _make_api_response_body(model_version="gpt-4o-2024-11-20")
        ),
    )

    result = adapter.analyse(_make_analysis_input())

    pi = result.provider_info
    assert pi.provider == "github_models"
    assert pi.model_id == "gpt-4o"
    assert pi.model_version == "gpt-4o-2024-11-20"
    assert pi.endpoint == cfg.endpoint


# ---------------------------------------------------------------------------
# 12. Import surface
# ---------------------------------------------------------------------------


def test_import_surface() -> None:
    """All new public names are importable from app.analysis.adapters."""
    expected_new = {
        "ChatMessage",
        "EmptyRenderedMessagesError",
        "GitHubModelsAdapter",
        "GitHubModelsAPIError",
        "GitHubModelsConfig",
        "GitHubModelsError",
        "MissingTokenError",
        "PromptRenderer",
    }
    import app.analysis.adapters as _pkg

    for name in expected_new:
        assert hasattr(_pkg, name), f"Missing from app.analysis.adapters: {name}"


# ---------------------------------------------------------------------------
# 13. Protocol compatibility with AnalysisAdapter
# ---------------------------------------------------------------------------


def test_protocol_compatibility() -> None:
    """GitHubModelsAdapter satisfies the AnalysisAdapter Protocol at runtime."""
    adapter = _make_adapter()
    assert isinstance(adapter, AnalysisAdapter)
