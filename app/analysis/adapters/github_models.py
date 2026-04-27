"""
app/analysis/adapters/github_models.py

GitHub Models adapter — implements ``AnalysisAdapter`` via the GitHub Models
chat-completions API.

Official endpoint (2025)::

    POST https://models.github.ai/inference/chat/completions

Required headers::

    Accept: application/vnd.github+json
    Authorization: Bearer <token>
    X-GitHub-Api-Version: <version>
    Content-Type: application/json

The GitHub PAT must carry the ``models`` scope and is read from the
environment variable named by ``GitHubModelsConfig.token_env_var``
(default: ``GITHUB_TOKEN``).

Prompt rendering is fully delegated to an injected :class:`PromptRenderer` so
that node 3 can plug in filesystem-backed template loading without touching
this file.  No production prompt text is hard-coded here.

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

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_PROVIDER_ID = "github_models"
_DEFAULT_ENDPOINT = "https://models.github.ai/inference/chat/completions"
_DEFAULT_API_VERSION = "2022-11-28"
_DEFAULT_TOKEN_ENV_VAR = "GITHUB_TOKEN"
_DEFAULT_TIMEOUT = 60


# ---------------------------------------------------------------------------
# ChatMessage — typed chat message value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChatMessage:
    """A single chat-completion message with a role and text content."""

    role: str
    """One of ``"system"``, ``"user"``, or ``"assistant"``."""

    content: str
    """Text content of the message."""

    def to_dict(self) -> dict[str, str]:
        """Return a plain dict suitable for JSON serialisation."""
        return {"role": self.role, "content": self.content}


# ---------------------------------------------------------------------------
# GitHubModelsConfig — frozen adapter configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GitHubModelsConfig:
    """
    Frozen configuration for :class:`GitHubModelsAdapter`.

    Fields
    ------
    model_id
        GitHub Models model identifier, e.g. ``"gpt-4o"`` or
        ``"gpt-4o-mini"``.  Must be non-empty.
    endpoint
        Full chat-completions endpoint URL.  Defaults to the official
        GitHub Models endpoint.
    api_version
        Value for the ``X-GitHub-Api-Version`` header.
    token_env_var
        Name of the environment variable that holds the GitHub PAT.
        Defaults to ``"GITHUB_TOKEN"``.
    timeout
        HTTP request timeout in seconds.  Must be > 0.
    temperature
        Optional sampling temperature in ``[0.0, 2.0]``.  When ``None``
        the parameter is omitted from the request payload so the model
        default applies.
    """

    model_id: str
    endpoint: str = _DEFAULT_ENDPOINT
    api_version: str = _DEFAULT_API_VERSION
    token_env_var: str = _DEFAULT_TOKEN_ENV_VAR
    timeout: int = _DEFAULT_TIMEOUT
    temperature: float | None = None

    def __post_init__(self) -> None:
        if not self.model_id:
            raise ValueError("GitHubModelsConfig.model_id must not be empty.")
        if self.timeout <= 0:
            raise ValueError(
                f"GitHubModelsConfig.timeout must be > 0; got {self.timeout}."
            )
        if self.temperature is not None and not (0.0 <= self.temperature <= 2.0):
            raise ValueError(
                "GitHubModelsConfig.temperature must be in [0.0, 2.0]; "
                f"got {self.temperature}."
            )


# ---------------------------------------------------------------------------
# PromptRenderer — typed prompt-rendering contract
# ---------------------------------------------------------------------------


@runtime_checkable
class PromptRenderer(Protocol):
    """
    Contract for converting an :class:`~app.analysis.adapters.contracts.AnalysisInput`
    into an ordered list of :class:`ChatMessage` objects.

    This is the single injection point that decouples prompt authoring from
    HTTP transport.  Node 3 will inject a filesystem-backed implementation;
    tests inject a lightweight stub.

    Implementations must be **stateless** with respect to individual ``render``
    calls (state is acceptable for caching template files, etc.).
    """

    def render(self, analysis_input: AnalysisInput) -> list[ChatMessage]:
        """
        Return ordered chat messages for *analysis_input*.

        The returned list must be non-empty; :class:`GitHubModelsAdapter`
        will raise :class:`EmptyRenderedMessagesError` if it is empty.
        """
        ...


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class GitHubModelsError(Exception):
    """Base class for all GitHub Models adapter errors."""


class MissingTokenError(GitHubModelsError):
    """
    Raised when the GitHub token environment variable is absent or empty.
    """


class EmptyRenderedMessagesError(GitHubModelsError):
    """
    Raised when the injected :class:`PromptRenderer` returns no messages.
    """


class GitHubModelsAPIError(GitHubModelsError):
    """
    Raised when the GitHub Models API returns a non-2xx HTTP status or when
    a network-level :class:`urllib.error.HTTPError` is encountered.

    Attributes
    ----------
    status
        HTTP status code.
    body
        Response body text.
    """

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"GitHub Models API error {status}: {body}")
        self.status = status
        self.body = body


# ---------------------------------------------------------------------------
# GitHubModelsAdapter — AnalysisAdapter implementation
# ---------------------------------------------------------------------------

# Type alias for the injectable HTTP-open callable.
# Signature: (request: urllib.request.Request, timeout: int) -> http.client.HTTPResponse
_OpenFunc = Callable[[urllib.request.Request, int], object]


class GitHubModelsAdapter:
    """
    :class:`~app.analysis.adapters.contracts.AnalysisAdapter` implementation
    backed by the GitHub Models chat-completions API.

    Parameters
    ----------
    config
        Frozen :class:`GitHubModelsConfig` instance.
    renderer
        :class:`PromptRenderer` that converts :class:`AnalysisInput` into
        ordered :class:`ChatMessage` objects.  Injected so node 3 can swap
        in a filesystem-backed implementation without modifying this class.
    env
        Optional environment-variable mapping.  Defaults to ``os.environ``.
        Inject a plain ``dict`` in tests to avoid touching the real env.
    _open_func
        Optional callable with the same signature as
        ``urllib.request.urlopen``.  Defaults to ``urllib.request.urlopen``.
        Inject a stub in tests to avoid real HTTP calls.
    """

    def __init__(
        self,
        config: GitHubModelsConfig,
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
        """
        Run the full analysis pipeline against GitHub Models and return a
        structured :class:`~app.analysis.adapters.contracts.AnalysisResponse`.
        """
        token = self._read_token()
        messages = self._render_messages(analysis_input)
        payload = self._build_payload(messages)
        raw = self._post(payload, token)
        return self._parse_response(raw, analysis_input.prompt_profile)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _read_token(self) -> str:
        token = self._env.get(self._config.token_env_var, "")
        if not token:
            raise MissingTokenError(
                f"GitHub token not found: environment variable "
                f"'{self._config.token_env_var}' is not set or empty."
            )
        return token

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

    def _build_headers(self, token: str) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": self._config.api_version,
            "Content-Type": "application/json",
        }

    def _post(self, payload: dict, token: str) -> dict:
        headers = self._build_headers(token)
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
            raise GitHubModelsAPIError(exc.code, body) from exc

        status: int = resp.getcode()  # type: ignore[union-attr]
        resp_body: str = resp.read().decode("utf-8")  # type: ignore[union-attr]
        if status >= 300:
            raise GitHubModelsAPIError(status, resp_body)
        return json.loads(resp_body)

    def _parse_response(
        self, raw: dict, prompt_profile: PromptProfile
    ) -> AnalysisResponse:
        """
        Parse a GitHub Models API response envelope into
        :class:`~app.analysis.adapters.contracts.AnalysisResponse`.

        Expected LLM JSON content structure::

            {
              "chain_results": [
                {
                  "chain_id": "...",
                  "summary": "...",
                  "completion_notes": "...",
                  "key_entities": ["..."],
                  "confidence": 0.9
                }
              ],
              "ranking": {
                "entries": [
                  {
                    "chain_id": "...",
                    "rank": 1,
                    "score": 0.9,
                    "rationale": "..."
                  }
                ]
              }
            }
        """
        choices = raw.get("choices") or []
        if not choices:
            raise GitHubModelsAPIError(200, "Response contained no choices.")

        content_str: str = choices[0]["message"]["content"]
        content: dict = json.loads(content_str)

        # The "model" field in the response envelope may carry version info.
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
