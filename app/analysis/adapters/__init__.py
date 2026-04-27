"""app.analysis.adapters — analysis adapter contracts and implementations."""

from app.analysis.adapters.contracts import (
    AnalysisAdapter,
    AnalysisInput,
    AnalysisResponse,
    ChainAnalysisResult,
    ChainRankingEntry,
    ModelProviderInfo,
    PromptProfile,
    PromptTaskType,
    RankingOutput,
)
from app.analysis.adapters.github_models import (
    ChatMessage,
    EmptyRenderedMessagesError,
    GitHubModelsAdapter,
    GitHubModelsAPIError,
    GitHubModelsConfig,
    GitHubModelsError,
    MissingTokenError,
    PromptRenderer,
)
from app.analysis.adapters.openai_compatible import (
    MissingAPIKeyError,
    OpenAICompatibleAdapter,
    OpenAICompatibleAPIError,
    OpenAICompatibleConfig,
    OpenAICompatibleError,
)

__all__ = [
    # contracts
    "AnalysisAdapter",
    "AnalysisInput",
    "AnalysisResponse",
    "ChainAnalysisResult",
    "ChainRankingEntry",
    "ModelProviderInfo",
    "PromptProfile",
    "PromptTaskType",
    "RankingOutput",
    # github_models
    "ChatMessage",
    "EmptyRenderedMessagesError",
    "GitHubModelsAdapter",
    "GitHubModelsAPIError",
    "GitHubModelsConfig",
    "GitHubModelsError",
    "MissingTokenError",
    "PromptRenderer",
    # openai_compatible
    "MissingAPIKeyError",
    "OpenAICompatibleAdapter",
    "OpenAICompatibleAPIError",
    "OpenAICompatibleConfig",
    "OpenAICompatibleError",
]
