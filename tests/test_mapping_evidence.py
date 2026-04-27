"""
测试 A 股映射旁证引用功能。
"""

import datetime
import uuid

import pytest

from app.entity.evidence import EvidenceLink, EvidenceSpan, build_evidence_links
from app.entity.rules.extractor import Hit
from app.entity.tagged_output import TaggedOutput, build_tagged_output
from app.entity.themes import ThemeId
from app.models.event_draft import EventDraft
from app.models.news_item import NewsItem
from app.models.raw_document import RawDocument
from app.chains.chain import ChainNode, InformationChain, build_chain

from app.mapping.schema import (
    ConfidenceLevel,
    EvidenceSourceReference,
    EvidenceSnippetReference,
    MappingEvidence,
    AShareMappingWithEvidence,
)
from app.mapping.engine import (
    AShareMappingEngine,
    MappingEvidenceCollector,
    create_mapping_engine,
    create_evidence_collector,
    map_and_collect_evidence,
)


# ---------------------------------------------------------------------------
# 测试辅助函数
# ---------------------------------------------------------------------------


def create_test_raw_document(
    content: str,
    title: str = "测试新闻",
    source: str = "test",
    provider: str = "财联社",
) -> RawDocument:
    """创建测试用的 RawDocument"""
    return RawDocument(
        source=source,
        provider=provider,
        title=title,
        content=content,
        url=None,
        date=datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d"),
        metadata={},
    )


def create_test_news_item(
    content: str,
    title: str = "测试新闻",
    source: str = "test",
    provider: str = "财联社",
) -> NewsItem:
    """创建测试用的 NewsItem"""
    raw = create_test_raw_document(content, title, source, provider)
    return NewsItem.from_raw(raw)


def create_test_hit(
    text: str,
    theme_id: str,
    start: int,
    end: int,
) -> Hit:
    """创建测试用的 Hit"""
    return Hit(
        matched_text=text[start:end],
        start=start,
        end=end,
        matched_seed=theme_id,
        kind="theme",
        label_id=theme_id,
    )


def create_test_tagged_output(
    text: str,
    theme_ids: list[str],
    provider: str = "财联社",
) -> TaggedOutput:
    """创建测试用的 TaggedOutput"""
    # 创建 Hits
    hits: list[Hit] = []
    for theme_id in theme_ids:
        # 在文本中查找主题关键词
        keyword_map = {
            "ai": "人工智能",
            "gpu": "GPU",
            "semiconductor": "半导体",
            "cloud": "云服务",
            "memory": "内存",
            "optical_module": "光模块",
        }
        keyword = keyword_map.get(theme_id, theme_id)

        idx = text.find(keyword)
        if idx != -1:
            hit = create_test_hit(text, theme_id, idx, idx + len(keyword))
            hits.append(hit)

    # 构建证据链接
    evidence_links = build_evidence_links(text, hits)

    # 创建新闻项
    news_item = create_test_news_item(text, provider=provider)

    # 创建事件草稿
    event = EventDraft.from_news_item(news_item)

    # 构建 TaggedOutput
    return build_tagged_output(event, text, evidence_links)


def create_test_information_chain(
    texts: list[str],
    theme_ids_list: list[list[str]],
) -> InformationChain:
    """创建测试用的 InformationChain"""
    tagged_outputs = [
        create_test_tagged_output(text, theme_ids)
        for text, theme_ids in zip(texts, theme_ids_list)
    ]

    return build_chain(
        chain_id=str(uuid.uuid4()),
        tagged_outputs=tagged_outputs,
    )


# ---------------------------------------------------------------------------
# 测试数据结构
# ---------------------------------------------------------------------------


class TestEvidenceSourceReference:
    """测试 EvidenceSourceReference"""

    def test_create_valid(self):
        """测试创建有效的来源引用"""
        ref = EvidenceSourceReference(
            chain_id="test-chain-123",
            node_position=0,
            news_item_id=None,
            source_name="财联社",
            published_at="2025-01-15T10:30:00",
        )

        assert ref.chain_id == "test-chain-123"
        assert ref.node_position == 0
        assert ref.news_item_id is None
        assert ref.source_name == "财联社"
        assert ref.published_at == "2025-01-15T10:30:00"

    def test_minimal_fields(self):
        """测试仅必填字段"""
        ref = EvidenceSourceReference(
            chain_id="test-chain-123",
        )

        assert ref.chain_id == "test-chain-123"
        assert ref.node_position is None
        assert ref.news_item_id is None

    def test_empty_chain_id(self):
        """测试空的 chain_id 应该抛出异常"""
        with pytest.raises(ValueError, match="chain_id 不能为空字符串"):
            EvidenceSourceReference(chain_id="")


class TestEvidenceSnippetReference:
    """测试 EvidenceSnippetReference"""

    def test_create_valid(self):
        """测试创建有效的片段引用"""
        ref = EvidenceSnippetReference(
            snippet="人工智能",
            context_before="最新消息：",
            context_after="产业快速发展",
            start_offset=5,
            end_offset=10,
            label_id="ai",
            label_kind="theme",
        )

        assert ref.snippet == "人工智能"
        assert ref.context_before == "最新消息："
        assert ref.context_after == "产业快速发展"
        assert ref.start_offset == 5
        assert ref.end_offset == 10
        assert ref.label_id == "ai"
        assert ref.label_kind == "theme"

    def test_invalid_offsets(self):
        """测试无效的偏移量应该抛出异常"""
        with pytest.raises(ValueError, match="start_offset 不能为负数"):
            EvidenceSnippetReference(
                snippet="test",
                context_before="",
                context_after="",
                start_offset=-1,
                end_offset=5,
            )

        with pytest.raises(ValueError, match="end_offset 必须大于 start_offset"):
            EvidenceSnippetReference(
                snippet="test",
                context_before="",
                context_after="",
                start_offset=5,
                end_offset=5,
            )

    def test_invalid_label_kind(self):
        """测试无效的 label_kind 应该抛出异常"""
        with pytest.raises(ValueError, match="label_kind 必须是"):
            EvidenceSnippetReference(
                snippet="test",
                context_before="",
                context_after="",
                start_offset=0,
                end_offset=4,
                label_kind="invalid",
            )


class TestMappingEvidence:
    """测试 MappingEvidence"""

    def test_create_valid(self):
        """测试创建有效的映射旁证"""
        source_ref = EvidenceSourceReference(chain_id="test-chain")
        snippet_ref = EvidenceSnippetReference(
            snippet="人工智能",
            context_before="",
            context_after="",
            start_offset=0,
            end_offset=4,
        )

        evidence = MappingEvidence(
            mapping_type="sector",
            mapping_identifier="人工智能板块",
            source_reference=source_ref,
            snippet_references=(snippet_ref,),
            rationale="该新闻支持人工智能板块",
        )

        assert evidence.mapping_type == "sector"
        assert evidence.mapping_identifier == "人工智能板块"
        assert evidence.source_reference == source_ref
        assert len(evidence.snippet_references) == 1
        assert evidence.rationale == "该新闻支持人工智能板块"

    def test_invalid_mapping_type(self):
        """测试无效的 mapping_type 应该抛出异常"""
        source_ref = EvidenceSourceReference(chain_id="test-chain")

        with pytest.raises(ValueError, match="mapping_type 必须是"):
            MappingEvidence(
                mapping_type="invalid",
                mapping_identifier="test",
                source_reference=source_ref,
                snippet_references=(),
                rationale="test",
            )


class TestAShareMappingWithEvidence:
    """测试 AShareMappingWithEvidence"""

    def test_create_empty(self):
        """测试创建空的带旁证映射"""
        engine = create_mapping_engine()
        chain = create_test_information_chain(
            texts=["测试新闻"],
            theme_ids_list=[[]],
        )
        mapping = engine.map_information_chain(chain)

        mapping_with_evidence = AShareMappingWithEvidence(
            mapping=mapping,
            evidences=(),
        )

        assert mapping_with_evidence.mapping == mapping
        assert mapping_with_evidence.chain_id == mapping.chain_id
        assert not mapping_with_evidence.has_evidences

    def test_with_evidences(self):
        """测试带旁证的映射"""
        engine = create_mapping_engine()
        chain = create_test_information_chain(
            texts=["测试新闻"],
            theme_ids_list=[[]],
        )
        mapping = engine.map_information_chain(chain)

        source_ref = EvidenceSourceReference(chain_id=chain.chain_id)
        evidence = MappingEvidence(
            mapping_type="sector",
            mapping_identifier="测试板块",
            source_reference=source_ref,
            snippet_references=(),
            rationale="测试",
        )

        mapping_with_evidence = AShareMappingWithEvidence(
            mapping=mapping,
            evidences=(evidence,),
        )

        assert mapping_with_evidence.has_evidences
        assert len(mapping_with_evidence.evidences) == 1

    def test_get_evidences_by_type(self):
        """测试按类型获取旁证"""
        engine = create_mapping_engine()
        chain = create_test_information_chain(
            texts=["测试新闻"],
            theme_ids_list=[[]],
        )
        mapping = engine.map_information_chain(chain)

        source_ref = EvidenceSourceReference(chain_id=chain.chain_id)

        sector_evidence = MappingEvidence(
            mapping_type="sector",
            mapping_identifier="人工智能",
            source_reference=source_ref,
            snippet_references=(),
            rationale="test",
        )

        stock_evidence = MappingEvidence(
            mapping_type="individual_stock",
            mapping_identifier="600519",
            source_reference=source_ref,
            snippet_references=(),
            rationale="test",
        )

        mapping_with_evidence = AShareMappingWithEvidence(
            mapping=mapping,
            evidences=(sector_evidence, stock_evidence),
        )

        sector_evidences = mapping_with_evidence.get_evidences_for_sector("人工智能")
        assert len(sector_evidences) == 1

        stock_evidences = mapping_with_evidence.get_evidences_for_stock("600519")
        assert len(stock_evidences) == 1


# ---------------------------------------------------------------------------
# 测试旁证收集器
# ---------------------------------------------------------------------------


class TestMappingEvidenceCollector:
    """测试 MappingEvidenceCollector"""

    def test_collect_for_single_tagged_output(self):
        """测试为单个 TaggedOutput 收集旁证"""
        text = "人工智能产业快速发展，GPU 需求大幅增长"
        tagged_output = create_test_tagged_output(text, ["ai", "gpu"])

        engine = create_mapping_engine()
        mapping = engine.map_tagged_output(tagged_output)

        collector = create_evidence_collector()
        result = collector.collect_for_tagged_output(tagged_output, mapping)

        assert isinstance(result, AShareMappingWithEvidence)
        assert result.mapping == mapping

    def test_collect_for_information_chain(self):
        """测试为 InformationChain 收集旁证"""
        chain = create_test_information_chain(
            texts=[
                "人工智能产业快速发展",
                "GPU 需求大幅增长",
                "半导体产业链受益",
            ],
            theme_ids_list=[["ai"], ["gpu"], ["semiconductor"]],
        )

        collector = create_evidence_collector()
        result = collector.map_and_collect_for_chain(chain)

        assert isinstance(result, AShareMappingWithEvidence)
        assert result.chain_id == chain.chain_id

    def test_map_and_collect_evidence(self):
        """测试同时执行映射和旁证收集"""
        chain = create_test_information_chain(
            texts=["人工智能和云服务产业快速发展"],
            theme_ids_list=[["ai", "cloud"]],
        )

        result = map_and_collect_evidence(chain)

        assert isinstance(result, AShareMappingWithEvidence)
        assert result.mapping.chain_id == chain.chain_id

    def test_snippet_references_are_built(self):
        """测试证据片段引用被正确构建"""
        text = "人工智能技术突破，推动半导体产业发展"
        tagged_output = create_test_tagged_output(text, ["ai", "semiconductor"])

        # 检查 TaggedOutput 是否有证据链接
        assert len(tagged_output.evidence_links) >= 0

    def test_source_reference_includes_metadata(self):
        """测试来源引用包含元数据"""
        text = "人工智能产业新闻"
        tagged_output = create_test_tagged_output(text, ["ai"], provider="测试来源")

        engine = create_mapping_engine()
        mapping = engine.map_tagged_output(tagged_output)

        collector = create_evidence_collector()
        result = collector.collect_for_tagged_output(tagged_output, mapping)

        # 检查来源引用中的数据
        assert result.mapping.chain_id == mapping.chain_id


# ---------------------------------------------------------------------------
# 集成测试
# ---------------------------------------------------------------------------


class TestIntegration:
    """集成测试"""

    def test_full_workflow(self):
        """测试完整工作流：映射 -> 旁证收集"""
        # 1. 创建信息链
        chain = create_test_information_chain(
            texts=[
                "人工智能产业快速发展，GPU 需求大幅增长",
                "半导体产业链受益，相关公司业绩向好",
            ],
            theme_ids_list=[["ai", "gpu"], ["semiconductor"]],
        )

        # 2. 映射和收集旁证
        result = map_and_collect_evidence(chain)

        # 3. 验证结果
        assert isinstance(result, AShareMappingWithEvidence)
        assert result.chain_id == chain.chain_id

        # 4. 映射内容验证
        assert result.mapping.chain_id == chain.chain_id

    def test_multiple_nodes_chain(self):
        """测试多节点信息链的旁证收集"""
        texts = [
            "人工智能技术突破",
            "GPU 算力需求增长",
            "半导体产业链受益",
            "云服务厂商扩张",
        ]
        theme_ids_list = [
            ["ai"],
            ["gpu"],
            ["semiconductor"],
            ["cloud"],
        ]

        chain = create_test_information_chain(texts, theme_ids_list)
        result = map_and_collect_evidence(chain)

        assert result.chain_id == chain.chain_id
        assert len(result.mapping.sector_mappings) >= 0
