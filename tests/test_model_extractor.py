"""
tests/test_model_extractor.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
测试模型辅助抽取接口（节点 4）：
- ModelExtractionRequest / ModelExtractionResponse 的构造与字段默认值
- ModelExtractor Protocol 的接口合规性检测（fake 实现）
- Hit 兼容性：响应中的 hits 与规则层 Hit 完全相同类型
- app.entity 的导入导出接口
"""

from __future__ import annotations

import pytest

from app.entity import (
    ModelExtractionRequest,
    ModelExtractionResponse,
    ModelExtractor,
    Hit,
)
from app.entity.model_extractor import (
    ModelExtractionRequest as _Req,
    ModelExtractionResponse as _Resp,
    ModelExtractor as _Proto,
)


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------

class _MinimalExtractor:
    """最简实现：只提供 extract 方法，不继承任何基类。"""

    def extract(self, request: ModelExtractionRequest) -> ModelExtractionResponse:
        return ModelExtractionResponse(
            hits=[],
            provider="fake",
            model="noop-v1",
        )


class _RichExtractor:
    """完整实现：返回来自请求文本的伪造 Hit，并写入元数据。"""

    provider = "test-provider"
    model = "test-model-1.0"

    def extract(self, request: ModelExtractionRequest) -> ModelExtractionResponse:
        hit = Hit(
            matched_text=request.text[:3] if len(request.text) >= 3 else request.text,
            start=0,
            end=min(3, len(request.text)),
            matched_seed="<model>",
            kind="theme",
            label_id="ai",
        )
        return ModelExtractionResponse(
            hits=[hit],
            provider=self.provider,
            model=self.model,
            notes="test note",
            metadata={"tokens": 42},
        )


class _ErrorExtractor:
    """模拟失败但仍返回响应的实现。"""

    def extract(self, request: ModelExtractionRequest) -> ModelExtractionResponse:
        return ModelExtractionResponse(
            hits=[],
            provider="err-provider",
            model="err-model",
            error="connection timeout",
        )


# ---------------------------------------------------------------------------
# ModelExtractionRequest 构造测试
# ---------------------------------------------------------------------------

class TestModelExtractionRequest:
    def test_required_field_text(self):
        req = ModelExtractionRequest(text="hello world")
        assert req.text == "hello world"

    def test_defaults(self):
        req = ModelExtractionRequest(text="x")
        assert req.rule_hits == []
        assert req.max_hits is None
        assert req.context_hint is None

    def test_with_rule_hits(self):
        hit = Hit(
            matched_text="GPU",
            start=0,
            end=3,
            matched_seed="GPU",
            kind="theme",
            label_id="gpu",
        )
        req = ModelExtractionRequest(text="GPU 算力", rule_hits=[hit])
        assert len(req.rule_hits) == 1
        assert req.rule_hits[0] is hit

    def test_with_max_hits(self):
        req = ModelExtractionRequest(text="text", max_hits=10)
        assert req.max_hits == 10

    def test_with_context_hint(self):
        req = ModelExtractionRequest(text="text", context_hint="半导体行业")
        assert req.context_hint == "半导体行业"

    def test_frozen_immutable(self):
        req = ModelExtractionRequest(text="frozen test")
        with pytest.raises((AttributeError, TypeError)):
            req.text = "mutated"  # type: ignore[misc]

    def test_equality(self):
        r1 = ModelExtractionRequest(text="abc")
        r2 = ModelExtractionRequest(text="abc")
        assert r1 == r2

    def test_inequality_different_text(self):
        r1 = ModelExtractionRequest(text="abc")
        r2 = ModelExtractionRequest(text="xyz")
        assert r1 != r2

    def test_empty_text_allowed(self):
        req = ModelExtractionRequest(text="")
        assert req.text == ""

    def test_rule_hits_default_independent(self):
        """每个实例的默认 rule_hits 列表互相独立（field_factory 保证）。"""
        r1 = ModelExtractionRequest(text="a")
        r2 = ModelExtractionRequest(text="b")
        assert r1.rule_hits is not r2.rule_hits


# ---------------------------------------------------------------------------
# ModelExtractionResponse 构造测试
# ---------------------------------------------------------------------------

class TestModelExtractionResponse:
    def test_required_fields(self):
        resp = ModelExtractionResponse(hits=[], provider="openai", model="gpt-4o")
        assert resp.hits == []
        assert resp.provider == "openai"
        assert resp.model == "gpt-4o"

    def test_optional_defaults(self):
        resp = ModelExtractionResponse(hits=[], provider="x", model="y")
        assert resp.notes is None
        assert resp.error is None
        assert resp.metadata == {}

    def test_with_notes(self):
        resp = ModelExtractionResponse(hits=[], provider="x", model="y", notes="v1 prompt")
        assert resp.notes == "v1 prompt"

    def test_with_error(self):
        resp = ModelExtractionResponse(hits=[], provider="x", model="y", error="timeout")
        assert resp.error == "timeout"

    def test_with_metadata(self):
        resp = ModelExtractionResponse(
            hits=[], provider="x", model="y", metadata={"latency_ms": 120}
        )
        assert resp.metadata["latency_ms"] == 120

    def test_metadata_default_independent(self):
        r1 = ModelExtractionResponse(hits=[], provider="x", model="y")
        r2 = ModelExtractionResponse(hits=[], provider="x", model="y")
        assert r1.metadata is not r2.metadata

    def test_mutable_response(self):
        """Response 是普通 dataclass（非 frozen），支持在后处理时追加元数据。"""
        resp = ModelExtractionResponse(hits=[], provider="x", model="y")
        resp.metadata["extra"] = "ok"
        assert resp.metadata["extra"] == "ok"


# ---------------------------------------------------------------------------
# Hit 兼容性测试
# ---------------------------------------------------------------------------

class TestHitCompatibility:
    def test_response_hits_are_hit_instances(self):
        hit = Hit(
            matched_text="英伟达",
            start=0,
            end=3,
            matched_seed="英伟达",
            kind="entity_type",
            label_id="company",
        )
        resp = ModelExtractionResponse(hits=[hit], provider="p", model="m")
        assert isinstance(resp.hits[0], Hit)

    def test_hit_fields_preserved_in_response(self):
        hit = Hit(
            matched_text="LLM",
            start=5,
            end=8,
            matched_seed="LLM",
            kind="theme",
            label_id="ai",
        )
        resp = ModelExtractionResponse(hits=[hit], provider="p", model="m")
        h = resp.hits[0]
        assert h.matched_text == "LLM"
        assert h.start == 5
        assert h.end == 8
        assert h.matched_seed == "LLM"
        assert h.kind == "theme"
        assert h.label_id == "ai"

    def test_response_hits_accept_entity_type_kind(self):
        hit = Hit(
            matched_text="H100",
            start=0,
            end=4,
            matched_seed="H100",
            kind="entity_type",
            label_id="product",
        )
        resp = ModelExtractionResponse(hits=[hit], provider="p", model="m")
        assert resp.hits[0].kind == "entity_type"

    def test_multiple_hits_in_response(self):
        hits = [
            Hit(matched_text="GPU", start=0, end=3, matched_seed="GPU",
                kind="theme", label_id="gpu"),
            Hit(matched_text="英伟达", start=4, end=7, matched_seed="英伟达",
                kind="entity_type", label_id="company"),
        ]
        resp = ModelExtractionResponse(hits=hits, provider="p", model="m")
        assert len(resp.hits) == 2

    def test_rule_hits_can_flow_into_response(self):
        """规则层 Hit 可以直接放入响应，证明两层类型完全兼容。"""
        from app.entity.rules import RuleExtractor
        extractor = RuleExtractor()
        rule_hits = extractor.extract("英伟达推出最新 GPU。")
        resp = ModelExtractionResponse(hits=rule_hits, provider="passthrough", model="rules-v1")
        assert all(isinstance(h, Hit) for h in resp.hits)


# ---------------------------------------------------------------------------
# Protocol 接口合规性测试
# ---------------------------------------------------------------------------

class TestModelExtractorProtocol:
    def test_minimal_extractor_is_model_extractor(self):
        assert isinstance(_MinimalExtractor(), ModelExtractor)

    def test_rich_extractor_is_model_extractor(self):
        assert isinstance(_RichExtractor(), ModelExtractor)

    def test_error_extractor_is_model_extractor(self):
        assert isinstance(_ErrorExtractor(), ModelExtractor)

    def test_non_extractor_rejected(self):
        class NotAnExtractor:
            pass
        assert not isinstance(NotAnExtractor(), ModelExtractor)

    def test_object_without_extract_rejected(self):
        class AlmostExtractor:
            def run(self, req):  # wrong method name
                return None
        assert not isinstance(AlmostExtractor(), ModelExtractor)

    def test_minimal_extractor_returns_response(self):
        ext = _MinimalExtractor()
        req = ModelExtractionRequest(text="test")
        resp = ext.extract(req)
        assert isinstance(resp, ModelExtractionResponse)

    def test_rich_extractor_returns_hits(self):
        ext = _RichExtractor()
        req = ModelExtractionRequest(text="英伟达")
        resp = ext.extract(req)
        assert len(resp.hits) == 1
        assert isinstance(resp.hits[0], Hit)

    def test_rich_extractor_provider_and_model(self):
        ext = _RichExtractor()
        resp = ext.extract(ModelExtractionRequest(text="text"))
        assert resp.provider == "test-provider"
        assert resp.model == "test-model-1.0"

    def test_error_extractor_returns_error_field(self):
        ext = _ErrorExtractor()
        resp = ext.extract(ModelExtractionRequest(text="fail"))
        assert resp.error == "connection timeout"
        assert resp.hits == []

    def test_extractor_with_rule_hits_in_request(self):
        ext = _RichExtractor()
        rule_hit = Hit(
            matched_text="GPU", start=0, end=3,
            matched_seed="GPU", kind="theme", label_id="gpu",
        )
        req = ModelExtractionRequest(text="GPU test", rule_hits=[rule_hit])
        resp = ext.extract(req)
        assert isinstance(resp, ModelExtractionResponse)

    def test_request_not_mutated_by_extractor(self):
        ext = _RichExtractor()
        req = ModelExtractionRequest(text="immutable", max_hits=5)
        ext.extract(req)
        assert req.text == "immutable"
        assert req.max_hits == 5

    def test_duck_typing_via_protocol(self):
        """任意实现了 extract 签名的对象均满足 Protocol，无需继承。"""
        class AnotherImpl:
            def extract(self, request):
                return ModelExtractionResponse(hits=[], provider="duck", model="v0")

        impl: ModelExtractor = AnotherImpl()
        resp = impl.extract(ModelExtractionRequest(text="duck"))
        assert resp.provider == "duck"


# ---------------------------------------------------------------------------
# 导入导出接口测试
# ---------------------------------------------------------------------------

class TestImportExportSurface:
    def test_import_from_app_entity(self):
        """从顶层包可以直接导入三个新符号。"""
        from app.entity import (  # noqa: F401
            ModelExtractionRequest,
            ModelExtractionResponse,
            ModelExtractor,
        )

    def test_import_from_module_directly(self):
        """也可以从具体模块导入。"""
        from app.entity.model_extractor import (  # noqa: F401
            ModelExtractionRequest,
            ModelExtractionResponse,
            ModelExtractor,
        )

    def test_all_exports_in_entity_init(self):
        import app.entity as pkg
        assert "ModelExtractionRequest" in pkg.__all__
        assert "ModelExtractionResponse" in pkg.__all__
        assert "ModelExtractor" in pkg.__all__

    def test_all_exports_in_model_extractor_module(self):
        import app.entity.model_extractor as mod
        assert "ModelExtractionRequest" in mod.__all__
        assert "ModelExtractionResponse" in mod.__all__
        assert "ModelExtractor" in mod.__all__

    def test_request_is_same_object_across_imports(self):
        from app.entity import ModelExtractionRequest as A
        from app.entity.model_extractor import ModelExtractionRequest as B
        assert A is B

    def test_response_is_same_object_across_imports(self):
        from app.entity import ModelExtractionResponse as A
        from app.entity.model_extractor import ModelExtractionResponse as B
        assert A is B

    def test_protocol_is_same_object_across_imports(self):
        from app.entity import ModelExtractor as A
        from app.entity.model_extractor import ModelExtractor as B
        assert A is B

    def test_hit_re_exported_from_entity(self):
        """Hit 仍可从 app.entity 顶层导入（向后兼容）。"""
        from app.entity import Hit  # noqa: F401
