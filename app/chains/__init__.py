"""app.chains — 信息链构建包。"""

from app.chains.candidate_generation import generate_candidate_chains
from app.chains.chain import ChainNode, InformationChain, build_chain
from app.chains.evidence_retention import (
    ChainEvidenceBundle,
    collect_all_evidence,
    collect_chain_evidence,
)
from app.chains.relation_type import RelationType
from app.chains.same_topic_grouping import group_same_topic
from app.chains.temporal_connection import apply_temporal_order
from app.chains.upstream_downstream import apply_upstream_downstream_order

__all__ = [
    "ChainEvidenceBundle",
    "ChainNode",
    "InformationChain",
    "RelationType",
    "apply_temporal_order",
    "apply_upstream_downstream_order",
    "build_chain",
    "collect_all_evidence",
    "collect_chain_evidence",
    "generate_candidate_chains",
    "group_same_topic",
]
