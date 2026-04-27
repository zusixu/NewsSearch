"""
主题标签体系（Theme Taxonomy）

为下游规则抽取和 LLM 标注提供稳定的主题分类参考。

设计原则：
- 每个主题有唯一字符串 ID（ThemeId 枚举），保证跨版本稳定性。
- ThemeDefinition 是只读 dataclass，包含中文标签、英文标签、说明与种子关键词。
- 本模块不实现任何抽取逻辑，仅作为"分类词典"供其他模块导入。

覆盖范围（共 11 个主题）：
  必选（来自 plan.md / entity-theme-tagging 上下文）：
    AI、本体模型、算力、内存、GPU、半导体、云服务、应用落地、供应链
  扩展（有 plan.md 明确依据）：
    光模块（plan.md § 信息链构建层 显式列出）
    存储（plan.md § 数据采集层 "算力、存储" 并列列出，与内存是不同细分赛道）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class ThemeId(str, Enum):
    """主题唯一标识符。值即 ID，便于序列化与数据库存储。"""

    AI = "ai"
    FOUNDATION_MODEL = "foundation_model"
    COMPUTE = "compute"
    MEMORY = "memory"
    GPU = "gpu"
    SEMICONDUCTOR = "semiconductor"
    CLOUD = "cloud"
    AI_APPLICATION = "ai_application"
    SUPPLY_CHAIN = "supply_chain"
    OPTICAL_MODULE = "optical_module"
    STORAGE = "storage"


@dataclass(frozen=True)
class ThemeDefinition:
    """单个主题的完整定义，冻结以保证只读。"""

    id: ThemeId
    label: str           # 中文短标签，用于展示
    label_en: str        # 英文短标签
    description: str     # 一句话说明，描述该主题覆盖的业务范围
    keywords: Tuple[str, ...]  # 种子关键词，用于后续规则匹配的初始词表

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("ThemeDefinition.id must not be empty")
        if not self.label:
            raise ValueError("ThemeDefinition.label must not be empty")
        if not self.keywords:
            raise ValueError("ThemeDefinition.keywords must not be empty")


# ---------------------------------------------------------------------------
# 主题词典（主数据）
# 修改词典时必须同步更新测试 test_theme_taxonomy.py 中的完整性断言。
# ---------------------------------------------------------------------------

THEME_TAXONOMY: Dict[ThemeId, ThemeDefinition] = {
    ThemeId.AI: ThemeDefinition(
        id=ThemeId.AI,
        label="人工智能",
        label_en="Artificial Intelligence",
        description="涵盖 AI 行业整体动态，包括大模型研发、AI 政策、行业投融资等宏观事件。",
        keywords=(
            "人工智能", "AI", "大模型", "机器学习", "深度学习",
            "神经网络", "智能", "artificial intelligence",
        ),
    ),
    ThemeId.FOUNDATION_MODEL: ThemeDefinition(
        id=ThemeId.FOUNDATION_MODEL,
        label="基础模型",
        label_en="Foundation Model",
        description="预训练大语言模型、多模态模型、模型架构创新及能力评测等。",
        keywords=(
            "基础模型", "本体模型", "大语言模型", "LLM", "GPT", "Claude",
            "Gemini", "Llama", "Qwen", "DeepSeek", "预训练", "fine-tuning",
            "RLHF", "Transformer", "MoE", "混合专家",
        ),
    ),
    ThemeId.COMPUTE: ThemeDefinition(
        id=ThemeId.COMPUTE,
        label="算力",
        label_en="AI Compute",
        description="AI 训练与推理所需的算力基础设施，包括数据中心、算力集群、功耗与互联技术。",
        keywords=(
            "算力", "算力集群", "数据中心", "训练集群", "推理加速",
            "FLOPS", "算力租用", "AI 基础设施", "互联", "InfiniBand",
            "NVLink", "功耗", "液冷", "浸没冷却",
        ),
    ),
    ThemeId.MEMORY: ThemeDefinition(
        id=ThemeId.MEMORY,
        label="内存",
        label_en="AI Memory / DRAM",
        description="高带宽内存（HBM）、DRAM 及内存带宽相关技术与供需动态。",
        keywords=(
            "内存", "HBM", "HBM2", "HBM3", "DRAM", "高带宽内存",
            "内存带宽", "SK 海力士", "三星内存", "美光", "Micron",
            "DDR5", "LPDDR", "内存容量",
        ),
    ),
    ThemeId.GPU: ThemeDefinition(
        id=ThemeId.GPU,
        label="GPU / AI 芯片",
        label_en="GPU / AI Chip",
        description="GPU、NPU、TPU 等 AI 加速芯片的研发、供需、出口管制及竞争格局。",
        keywords=(
            "GPU", "NPU", "TPU", "AI 芯片", "英伟达", "NVIDIA", "AMD",
            "A100", "H100", "H800", "B200", "华为昇腾", "昇腾",
            "寒武纪", "燧原", "出口管制", "芯片禁令", "算力芯片",
        ),
    ),
    ThemeId.SEMICONDUCTOR: ThemeDefinition(
        id=ThemeId.SEMICONDUCTOR,
        label="半导体",
        label_en="Semiconductor",
        description="芯片设计、晶圆代工、封装测试、EDA/材料设备等半导体全产业链动态。",
        keywords=(
            "半导体", "芯片", "晶圆", "代工", "台积电", "TSMC",
            "三星", "中芯国际", "SMIC", "封装", "先进封装", "CoWoS",
            "EDA", "光刻机", "ASML", "材料", "光刻胶", "氮化镓", "碳化硅",
            "fab", "制程", "节点", "3nm", "2nm",
        ),
    ),
    ThemeId.CLOUD: ThemeDefinition(
        id=ThemeId.CLOUD,
        label="云服务",
        label_en="Cloud Services",
        description="公有云、私有云、云厂商算力投入、云 AI 服务及云基础设施扩张。",
        keywords=(
            "云服务", "云计算", "公有云", "阿里云", "腾讯云", "华为云",
            "AWS", "Azure", "Google Cloud", "云厂商", "云 AI",
            "IaaS", "PaaS", "SaaS", "算力云", "云原生",
        ),
    ),
    ThemeId.AI_APPLICATION: ThemeDefinition(
        id=ThemeId.AI_APPLICATION,
        label="应用落地",
        label_en="AI Application",
        description="AI 在各行业的落地应用，包括 AIGC、智能体、自动驾驶、医疗、教育、机器人等。",
        keywords=(
            "应用落地", "AIGC", "AI 应用", "智能体", "Agent", "自动驾驶",
            "具身智能", "机器人", "医疗 AI", "教育 AI", "AI 助手",
            "Copilot", "工业 AI", "金融 AI", "AI 营销", "终端应用",
        ),
    ),
    ThemeId.SUPPLY_CHAIN: ThemeDefinition(
        id=ThemeId.SUPPLY_CHAIN,
        label="供应链",
        label_en="Supply Chain",
        description="AI 硬件与基础设施的上下游供应链，含 PCB、电源、散热、连接器、服务器整机等。",
        keywords=(
            "供应链", "上下游", "服务器", "PCB", "散热", "电源",
            "连接器", "ODM", "OEM", "交换机", "机架", "液冷板",
            "算力供应链", "AI 服务器", "整机柜",
        ),
    ),
    ThemeId.OPTICAL_MODULE: ThemeDefinition(
        id=ThemeId.OPTICAL_MODULE,
        label="光模块",
        label_en="Optical Module",
        description=(
            "数据中心高速光互联，包括光模块、光芯片、硅光技术及相关 A 股标的。"
            "（plan.md §信息链构建层 显式列出）"
        ),
        keywords=(
            "光模块", "光芯片", "硅光", "光通信", "光互联",
            "400G", "800G", "1.6T", "中际旭创", "新易盛", "天孚通信",
            "AOC", "DAC", "可插拔光模块", "CPO",
        ),
    ),
    ThemeId.STORAGE: ThemeDefinition(
        id=ThemeId.STORAGE,
        label="存储",
        label_en="Storage",
        description=(
            "NAND Flash、企业级 SSD、存储控制器及存储系统，"
            "区别于 DRAM/内存赛道。（plan.md §数据采集层 '算力、存储' 并列）"
        ),
        keywords=(
            "存储", "NAND", "SSD", "闪存", "固态硬盘", "存储控制器",
            "企业存储", "长江存储", "YMTC", "铠侠", "Kioxia",
            "Western Digital", "希捷", "Seagate", "NVMe", "存储扩容",
        ),
    ),
}


# ---------------------------------------------------------------------------
# 公开辅助 API
# ---------------------------------------------------------------------------

def get_theme(theme_id: ThemeId) -> ThemeDefinition:
    """通过 ThemeId 获取主题定义，不存在时抛出 KeyError。"""
    return THEME_TAXONOMY[theme_id]


def all_themes() -> List[ThemeDefinition]:
    """返回所有主题定义的列表，顺序与枚举声明一致。"""
    return [THEME_TAXONOMY[tid] for tid in ThemeId]


def find_themes_by_keyword(keyword: str) -> List[ThemeDefinition]:
    """
    在所有主题的种子关键词中执行大小写不敏感的子串匹配，
    返回命中的主题列表（可能为空或多个）。

    注意：这是辅助查找，不是正式抽取算法，后者由 rules/ 模块实现。
    """
    kw_lower = keyword.lower()
    return [
        defn
        for defn in THEME_TAXONOMY.values()
        if any(kw_lower in seed.lower() for seed in defn.keywords)
    ]


def theme_ids() -> List[ThemeId]:
    """返回所有主题 ID 的列表。"""
    return list(ThemeId)
