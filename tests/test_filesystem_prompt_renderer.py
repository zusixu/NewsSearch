"""
Focused tests for FileSystemPromptRenderer and default prompt templates.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analysis import FileSystemPromptRenderer
from app.analysis.adapters import ChatMessage, PromptRenderer
from app.analysis.adapters.contracts import AnalysisInput, PromptProfile, PromptTaskType
from app.analysis.prompts import MissingPromptTemplateError, PromptTemplateError
from app.chains import (
    ChainEvidenceBundle,
    ChainNode,
    InformationChain,
)
from app.entity.evidence import EvidenceLink, EvidenceSpan
from app.entity.rules.extractor import Hit
from app.entity.tagged_output import TaggedOutput
from app.models.event_draft import EventDraft
from app.models.news_item import NewsItem
from app.models.raw_document import RawDocument


def _make_news(title: str = "news", date: str = "2025-01-01") -> NewsItem:
    raw = RawDocument(
        source="web",
        provider="test",
        title=title,
        content=title,
        url=None,
        date=date,
    )
    return NewsItem.from_raw(raw)


def _make_chain_bundle(
    task_type: PromptTaskType = PromptTaskType.SUMMARY,
) -> tuple[AnalysisInput, FileSystemPromptRenderer]:
    news = _make_news("GPU demand rises", "2025-01-02")
    event = EventDraft.from_news_item(news)
    hit = Hit(
        matched_text="GPU",
        start=0,
        end=3,
        matched_seed="GPU",
        kind="theme",
        label_id="gpu",
    )
    link = EvidenceLink(
        hit=hit,
        span=EvidenceSpan(
            snippet="GPU",
            context_before="",
            context_after=" demand rises",
            start=0,
            end=3,
        ),
    )
    tagged = TaggedOutput(
        event=event,
        text="GPU demand rises",
        theme_ids=("gpu",),
        entity_type_ids=(),
        evidence_links=(link,),
    )
    chain = InformationChain(
        chain_id="same-topic-0001",
        nodes=(ChainNode(tagged_output=tagged, position=0),),
        theme_ids=("gpu",),
        entity_type_ids=(),
    )
    bundle = ChainEvidenceBundle(
        chain_id=chain.chain_id,
        source_items=(news,),
        evidence_links=(link,),
    )
    analysis_input = AnalysisInput(
        chains=(chain,),
        evidence_bundles=(bundle,),
        prompt_profile=PromptProfile(
            profile_name="default",
            task_type=task_type,
            version="1.0.0",
            description="default prompts",
        ),
    )
    return analysis_input, FileSystemPromptRenderer()


def test_default_template_files_exist() -> None:
    renderer = FileSystemPromptRenderer()
    for task_type in PromptTaskType:
        assert renderer.template_path_for(task_type).is_file()


def test_task_type_maps_to_summary_template() -> None:
    renderer = FileSystemPromptRenderer()
    assert renderer.template_path_for(PromptTaskType.SUMMARY).name == "summary.json"


def test_task_type_maps_to_chain_completion_template() -> None:
    renderer = FileSystemPromptRenderer()
    assert (
        renderer.template_path_for(PromptTaskType.CHAIN_COMPLETION).name
        == "chain_completion.json"
    )


def test_task_type_maps_to_investment_ranking_template() -> None:
    renderer = FileSystemPromptRenderer()
    assert (
        renderer.template_path_for(PromptTaskType.INVESTMENT_RANKING).name
        == "investment_ranking.json"
    )


def test_renderer_returns_chat_messages() -> None:
    analysis_input, renderer = _make_chain_bundle()
    messages = renderer.render(analysis_input)
    assert messages
    assert all(isinstance(message, ChatMessage) for message in messages)


def test_renderer_matches_prompt_renderer_protocol() -> None:
    _, renderer = _make_chain_bundle()
    assert isinstance(renderer, PromptRenderer)


def test_rendered_messages_include_profile_metadata() -> None:
    analysis_input, renderer = _make_chain_bundle()
    messages = renderer.render(analysis_input)
    user_message = messages[-1].content
    assert "default@1.0.0" in user_message


def test_rendered_messages_include_chain_payload() -> None:
    analysis_input, renderer = _make_chain_bundle()
    messages = renderer.render(analysis_input)
    user_message = messages[-1].content
    assert "same-topic-0001" in user_message
    assert "GPU demand rises" in user_message


def test_rendered_payload_is_deterministic() -> None:
    analysis_input, renderer = _make_chain_bundle()
    first = [message.content for message in renderer.render(analysis_input)]
    second = [message.content for message in renderer.render(analysis_input)]
    assert first == second


def test_missing_template_raises() -> None:
    analysis_input, _ = _make_chain_bundle()
    renderer = FileSystemPromptRenderer(base_dir=Path("D:\\project\\mm\\tests\\missing-prompts"))
    with pytest.raises(MissingPromptTemplateError):
        renderer.render(analysis_input)


def test_malformed_template_json_raises(tmp_path: Path) -> None:
    bad = tmp_path / "summary.json"
    bad.write_text("{not json}", encoding="utf-8")
    renderer = FileSystemPromptRenderer(base_dir=tmp_path)
    analysis_input, _ = _make_chain_bundle()
    with pytest.raises(PromptTemplateError):
        renderer.render(analysis_input)


def test_template_without_messages_raises(tmp_path: Path) -> None:
    bad = tmp_path / "summary.json"
    bad.write_text(json.dumps({"description": "oops"}), encoding="utf-8")
    renderer = FileSystemPromptRenderer(base_dir=tmp_path)
    analysis_input, _ = _make_chain_bundle()
    with pytest.raises(PromptTemplateError):
        renderer.render(analysis_input)


def test_template_with_bad_message_shape_raises(tmp_path: Path) -> None:
    bad = tmp_path / "summary.json"
    bad.write_text(json.dumps({"messages": [{"role": "user"}]}), encoding="utf-8")
    renderer = FileSystemPromptRenderer(base_dir=tmp_path)
    analysis_input, _ = _make_chain_bundle()
    with pytest.raises(PromptTemplateError):
        renderer.render(analysis_input)


def test_import_surface_from_app_analysis() -> None:
    import app.analysis as analysis_pkg

    assert hasattr(analysis_pkg, "FileSystemPromptRenderer")


def test_import_surface_from_prompts_package() -> None:
    import app.analysis.prompts as prompts_pkg

    assert hasattr(prompts_pkg, "FileSystemPromptRenderer")
    assert hasattr(prompts_pkg, "PromptTemplateError")

