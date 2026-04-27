"""
app/analysis/adapters/openai_compatible.py

OpenAI-compatible chat-completions adapter — implements ``AnalysisAdapter``
via any endpoint that follows the OpenAI chat-completions API format.

This is a generic adapter that works with any OpenAI-compatible provider
(e.g. Volcengine/Ark, DeepSeek, Together AI, local vLLM, etc.).

Required headers::

    Authorization: Bearer <api_key>
    Content-Type: application/json

The API key is read from the environment variable named by
``OpenAICompatibleConfig.api_key_env_var`` (default: ``LLM_API_KEY``),
or can be set directly via ``api_key``.

Prompt rendering is delegated to an injected :class:`PromptRenderer`.
Network calls are mockable via the ``_open_func`` constructor argument.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, runtime_checkable

from app.analysis.adapters.contracts import (
    AnalysisInput,
    AnalysisResponse,
    ChainAnalysisResult,
    ChainRankingEntry,
    ModelProviderInfo,
    PromptProfile,
    RankingOutput,
)
from app.analysis.adapters.github_models import ChatMessage, PromptRenderer

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_PROVIDER_ID = "openai_compatible"
_DEFAULT_TIMEOUT = 60


# ---------------------------------------------------------------------------
# OpenAICompatibleConfig — frozen adapter configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    """
    Frozen configuration for :class:`OpenAICompatibleAdapter`.

    Fields
    ------
    model_id
        Model identifier, e.g. ``"glm-5.1"``, ``"deepseek-chat"``.
        Must be non-empty.
    endpoint
        Full chat-completions endpoint URL.
        e.g. ``"https://ark.cn-beijing.volces.com/api/coding/v3"``.
    api_key
        API key string.  When non-empty, takes precedence over
        ``api_key_env_var``.
    api_key_env_var
        Name of the environment variable that holds the API key.
        Defaults to ``"LLM_API_KEY"``.
    timeout
        HTTP request timeout in seconds.  Must be > 0.
    temperature
        Optional sampling temperature in ``[0.0, 2.0]``.  When ``None``
        the parameter is omitted from the request payload.
    extra_headers
        Optional dict of extra HTTP headers to include in every request.
    """

    model_id: str
    endpoint: str = ""
    api_key: str = ""
    api_key_env_var: str = "LLM_API_KEY"
    timeout: int = _DEFAULT_TIMEOUT
    temperature: float | None = None
    extra_headers: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if not self.model_id:
            raise ValueError("OpenAICompatibleConfig.model_id must not be empty.")
        if self.timeout <= 0:
            raise ValueError(
                f"OpenAICompatibleConfig.timeout must be > 0; got {self.timeout}."
            )
        if self.temperature is not None and not (0.0 <= self.temperature <= 2.0):
            raise ValueError(
                f"OpenAICompatibleConfig.temperature must be in [0.0, 2.0]; "
                f"got {self.temperature}."
            )


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class OpenAICompatibleError(Exception):
    """Base class for OpenAI-compatible adapter errors."""


class MissingAPIKeyError(OpenAICompatibleError):
    """Raised when the API key is absent or empty."""


class EmptyRenderedMessagesError(OpenAICompatibleError):
    """Raised when the PromptRenderer returns no messages."""


class OpenAICompatibleAPIError(OpenAICompatibleError):
    """Raised when the API returns a non-2xx HTTP status."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"OpenAI-compatible API error {status}: {body}")
        self.status = status
        self.body = body


# ---------------------------------------------------------------------------
# OpenAICompatibleAdapter — AnalysisAdapter implementation
# ---------------------------------------------------------------------------

_OpenFunc = Callable[[urllib.request.Request, int], object]


class OpenAICompatibleAdapter:
    """
    :class:`~app.analysis.adapters.contracts.AnalysisAdapter` implementation
    for any OpenAI-compatible chat-completions API.

    Parameters
    ----------
    config
        Frozen :class:`OpenAICompatibleConfig` instance.
    renderer
        :class:`PromptRenderer` for converting AnalysisInput into messages.
    env
        Optional environment-variable mapping.  Defaults to ``os.environ``.
    _open_func
        Optional callable matching ``urllib.request.urlopen`` signature.
    """

    def __init__(
        self,
        config: OpenAICompatibleConfig,
        renderer: PromptRenderer,
        *,
        env: Mapping[str, str] | None = None,
        _open_func: _OpenFunc | None = None,
    ) -> None:
        self._config = config
        self._renderer = renderer
        self._env: Mapping[str, str] = env if env is not None else os.environ
        self._open_func: _OpenFunc = (
            _open_func if _open_func is not None else urllib.request.urlopen
        )

    # ------------------------------------------------------------------
    # AnalysisAdapter Protocol implementation
    # ------------------------------------------------------------------

    def analyse(self, analysis_input: AnalysisInput) -> AnalysisResponse:
        token = self._read_api_key()
        messages = self._render_messages(analysis_input)
        payload = self._build_payload(messages)
        raw = self._post(payload, token)
        return self._parse_response(raw, analysis_input.prompt_profile)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _read_api_key(self) -> str:
        key = self._config.api_key
        if not key:
            key = self._env.get(self._config.api_key_env_var, "")
        if not key:
            raise MissingAPIKeyError(
                f"API key not found: set OpenAICompatibleConfig.api_key directly "
                f"or set environment variable '{self._config.api_key_env_var}'."
            )
        return key

    def _render_messages(self, analysis_input: AnalysisInput) -> list[ChatMessage]:
        messages = self._renderer.render(analysis_input)
        if not messages:
            raise EmptyRenderedMessagesError(
                "PromptRenderer returned no messages; cannot call the API."
            )
        return messages

    def _build_payload(self, messages: list[ChatMessage]) -> dict:
        payload: dict = {
            "model": self._config.model_id,
            "messages": [m.to_dict() for m in messages],
            "response_format": {"type": "json_object"},
        }
        if self._config.temperature is not None:
            payload["temperature"] = self._config.temperature
        return payload

    def _build_headers(self, api_key: str) -> dict[str, str]:
        headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if self._config.extra_headers:
            headers.update(self._config.extra_headers)
        return headers

    def _post(self, payload: dict, api_key: str) -> dict:
        headers = self._build_headers(api_key)
        body_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=self._config.endpoint,
            data=body_bytes,
            headers=headers,
            method="POST",
        )
        try:
            resp = self._open_func(req, self._config.timeout)
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8")
            except Exception:
                body = str(exc)
            raise OpenAICompatibleAPIError(exc.code, body) from exc

        status: int = resp.getcode()  # type: ignore[union-attr]
        resp_body: str = resp.read().decode("utf-8")  # type: ignore[union-attr]
        if status >= 300:
            raise OpenAICompatibleAPIError(status, resp_body)
        return json.loads(resp_body)

    def _parse_response(
        self, raw: dict, prompt_profile: PromptProfile
    ) -> AnalysisResponse:
        choices = raw.get("choices") or []
        if not choices:
            raise OpenAICompatibleAPIError(200, "Response contained no choices.")

        content_str: str = choices[0]["message"]["content"]
        content: dict = json.loads(content_str)

        model_version: str = raw.get("model", self._config.model_id)

        chain_results = tuple(
            ChainAnalysisResult(
                chain_id=entry["chain_id"],
                summary=entry.get("summary", ""),
                completion_notes=entry.get("completion_notes", ""),
                key_entities=tuple(entry.get("key_entities", [])),
                confidence=float(entry.get("confidence", 0.0)),
                prompt_profile=prompt_profile,
            )
            for entry in content.get("chain_results", [])
        )

        ranking_data: dict = content.get("ranking", {})
        ranking_entries = tuple(
            ChainRankingEntry(
                chain_id=e["chain_id"],
                rank=int(e["rank"]),
                score=float(e.get("score", 0.0)),
                rationale=e.get("rationale", ""),
            )
            for e in ranking_data.get("entries", [])
        )
        ranking = RankingOutput(
            entries=ranking_entries,
            prompt_profile=prompt_profile,
        )

        provider_info = ModelProviderInfo(
            provider=_PROVIDER_ID,
            model_id=self._config.model_id,
            model_version=model_version,
            endpoint=self._config.endpoint,
        )

        return AnalysisResponse(
            chain_results=chain_results,
            ranking=ranking,
            provider_info=provider_info,
        )
