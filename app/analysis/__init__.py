"""app.analysis — LLM-backed chain analysis package."""

from app.analysis.adapters import (
    AnalysisAdapter,
    AnalysisInput,
    AnalysisResponse,
    ChainAnalysisResult,
    ChainRankingEntry,
    ChatMessage,
    EmptyRenderedMessagesError,
    GitHubModelsAdapter,
    GitHubModelsAPIError,
    GitHubModelsConfig,
    GitHubModelsError,
    MissingTokenError,
    ModelProviderInfo,
    PromptProfile,
    PromptRenderer,
    PromptTaskType,
    RankingOutput,
)
from app.analysis.engine import (
    AnalysisEngine,
    AnalysisEngineConfig,
    DryRunAnalysisAdapter,
)
from app.analysis.prompts import (
    FileSystemPromptRenderer,
    MissingPromptProfileError,
    MissingPromptTemplateError,
    PromptProfileConfig,
    PromptProfileError,
    PromptProfileLoader,
    PromptTemplateError,
    TaskTemplateMapping,
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
    # engine
    "AnalysisEngine",
    "AnalysisEngineConfig",
    "DryRunAnalysisAdapter",
    # prompts
    "FileSystemPromptRenderer",
    "MissingPromptTemplateError",
    "PromptTemplateError",
    # profile management
    "TaskTemplateMapping",
    "PromptProfileConfig",
    "PromptProfileLoader",
    "PromptProfileError",
    "MissingPromptProfileError",
]
