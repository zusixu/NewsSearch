"""app/collectors — unified collector interface and concrete collectors."""

from app.collectors.base import (
    BaseCollector,
    CollectResult,
    CollectorAuthError,
    CollectorError,
    CollectorRateLimitError,
    CollectorTimeoutError,
    CollectorUnavailableError,
    RunContext,
)
from app.collectors.collection_cache import CollectionCache
from app.collectors.copilot_research_collector import (
    NullTransport,
    ResearchRequest,
    ResearchResponse,
    ResearchTransport,
)
from app.collectors.web_access_transport import (
    WebAccessTransport,
    WebAccessTransportConfig,
)
from app.collectors.raw_document import RawDocument
from app.collectors.retry import with_retry

__all__ = [
    # base contracts
    "BaseCollector",
    "CollectResult",
    "CollectorAuthError",
    "CollectorError",
    "CollectorRateLimitError",
    "CollectorTimeoutError",
    "CollectorUnavailableError",
    "RunContext",
    # unified raw-source record
    "RawDocument",
    # collection-layer cache
    "CollectionCache",
    # research collector contracts
    "NullTransport",
    "ResearchRequest",
    "ResearchResponse",
    "ResearchTransport",
    # web-access transport
    "WebAccessTransport",
    "WebAccessTransportConfig",
    # retry utility
    "with_retry",
]
