"""
模型辅助抽取接口（Model-Assisted Extraction Contract）

本模块定义模型补充抽取层的 **输入/输出契约** 和 **抽取器协议**，
不包含任何真实的模型调用或网络请求。

设计要点
--------
- :class:`ModelExtractionRequest` — 请求结构，携带待分析文本及可选上下文。
- :class:`ModelExtractionResponse` — 响应结构，核心输出为与规则层兼容的
  ``list[Hit]``；附带来源元数据（provider / model）、可选备注和错误说明。
- :class:`ModelExtractor` — ``typing.Protocol``，声明抽取器实现必须提供的
  ``extract`` 方法，便于依赖注入与测试替身。

与规则层的关系
--------------
- 规则抽取层（``app.entity.rules``）产出确定性 :class:`~app.entity.rules.Hit`。
- 本层使用 **相同的** :class:`~app.entity.rules.Hit` 结构作为输出单元，
  保证两层结果可以在节点 5（证据关联）中统一处理，无需类型转换。
- 区别在于响应附加了 ``provider``、``model`` 等来源字段，
  供下游区分命中来源（规则 vs. 模型）。

使用示例（伪代码）::

    from app.entity.model_extractor import (
        ModelExtractionRequest,
        ModelExtractionResponse,
        ModelExtractor,
    )
    from app.entity.rules import Hit

    class FakeExtractor:
        provider = "fake"
        model = "noop-v1"

        def extract(self, request: ModelExtractionRequest) -> ModelExtractionResponse:
            return ModelExtractionResponse(
                hits=[],
                provider=self.provider,
                model=self.model,
            )

    req = ModelExtractionRequest(text="英伟达发布 H100 GPU。")
    extractor: ModelExtractor = FakeExtractor()
    resp = extractor.extract(req)
    combined: list[Hit] = resp.hits
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from app.entity.rules import Hit

__all__ = [
    "ModelExtractionRequest",
    "ModelExtractionResponse",
    "ModelExtractor",
]

# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelExtractionRequest:
    """
    模型辅助抽取的输入请求。

    字段
    ----
    text
        待分析的原始文本（必填）。
    rule_hits
        规则层已产出的命中列表（可选）。模型实现可利用这些前置命中聚焦
        未覆盖区域，但不强制要求使用。
    max_hits
        期望返回的最大命中数量（可选，None 表示不限制）。
        实现可不理会此字段，由调用方截断。
    context_hint
        自由文本提示，例如文档来源、行业上下文，帮助模型更精确抽取（可选）。
    """

    text: str
    rule_hits: List[Hit] = field(default_factory=list)
    max_hits: Optional[int] = None
    context_hint: Optional[str] = None


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


@dataclass
class ModelExtractionResponse:
    """
    模型辅助抽取的输出响应。

    核心字段
    --------
    hits
        与规则层 :class:`~app.entity.rules.Hit` 完全相同结构的命中列表；
        偏移基准与 :class:`ModelExtractionRequest` 的 ``text`` 保持一致。
    provider
        模型服务来源标识，例如 ``"openai"``、``"anthropic"``、``"local"``。
    model
        具体模型版本标识，例如 ``"gpt-4o"``、``"claude-3-5-sonnet"``。

    可选字段
    --------
    notes
        实现方可写入的自由文本备注，例如置信度说明或提示词版本。
    error
        若抽取未完全成功，可写入错误描述；``hits`` 仍应尽量包含已获取结果。
    metadata
        扩展元数据字典，供特定实现传递额外信息（如 token 用量、延迟等）。
    """

    hits: List[Hit]
    provider: str
    model: str
    notes: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ModelExtractor(Protocol):
    """
    模型辅助抽取器协议。

    任何实现只需提供 ``extract`` 方法即可满足此协议；
    无需显式继承，支持结构子类型（structural subtyping）。

    ``@runtime_checkable`` 允许在测试中使用 ``isinstance`` 核查接口合规性。

    实现规约
    --------
    - ``extract`` 必须接受一个 :class:`ModelExtractionRequest` 并返回
      :class:`ModelExtractionResponse`。
    - 实现 **不得** 修改传入请求对象（request 为 frozen dataclass，天然保证）。
    - 实现 **应当** 在发生错误时仍返回响应对象，将错误写入 ``response.error``，
      而非直接抛出异常（除非错误无法恢复）。
    """

    def extract(self, request: ModelExtractionRequest) -> ModelExtractionResponse:
        """执行模型辅助抽取，返回命中结果及来源元数据。"""
        ...
