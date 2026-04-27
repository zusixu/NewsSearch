"""
实体类型体系（Entity Type Taxonomy）

为下游规则抽取、LLM 标注和信息链构建提供稳定的实体分类参考。

设计原则：
- 每个实体类型有唯一字符串 ID（EntityTypeId 枚举），保证跨版本稳定性。
- EntityTypeDefinition 是只读 dataclass，与 ThemeDefinition 结构平行。
- 本模块不实现任何抽取逻辑，仅作为"类型词典"供其他模块导入。

覆盖范围（共 6 种实体类型）：
  必选（来自 entity-theme-tagging 上下文建议）：
    公司、产品、技术、供应链角色、地区、政策主体
  说明：
    将"产品/技术"拆分为独立的 PRODUCT 和 TECHNOLOGY 两种类型，
    原因：产品是具体商业型号（如 H100 GPU），技术是底层工艺或架构
    （如 CoWoS 先进封装、Transformer 架构），二者在链路构建中作为
    不同类型节点连接，拆分有利于精确建模供需与创新关系。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple


class EntityTypeId(str, Enum):
    """实体类型唯一标识符。值即 ID，便于序列化与数据库存储。"""

    COMPANY = "company"
    PRODUCT = "product"
    TECHNOLOGY = "technology"
    SUPPLY_CHAIN_ROLE = "supply_chain_role"
    REGION = "region"
    POLICY_BODY = "policy_body"


@dataclass(frozen=True)
class EntityTypeDefinition:
    """单个实体类型的完整定义，冻结以保证只读。"""

    id: EntityTypeId
    label: str              # 中文短标签，用于展示
    label_en: str           # 英文短标签
    description: str        # 一句话说明，描述该类型覆盖的语义范围
    example_mentions: Tuple[str, ...]  # 典型提及示例，用于规则匹配的参考词表

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("EntityTypeDefinition.id must not be empty")
        if not self.label:
            raise ValueError("EntityTypeDefinition.label must not be empty")
        if not self.example_mentions:
            raise ValueError("EntityTypeDefinition.example_mentions must not be empty")


# ---------------------------------------------------------------------------
# 实体类型词典（主数据）
# 修改词典时必须同步更新测试 test_entity_types.py 中的完整性断言。
# ---------------------------------------------------------------------------

ENTITY_TYPE_TAXONOMY: Dict[EntityTypeId, EntityTypeDefinition] = {
    EntityTypeId.COMPANY: EntityTypeDefinition(
        id=EntityTypeId.COMPANY,
        label="公司",
        label_en="Company",
        description=(
            "在 AI 产业链中出现的企业主体，包括芯片商、云厂商、整机厂、"
            "模型公司、投资机构等各类组织实体。"
        ),
        example_mentions=(
            "英伟达", "NVIDIA", "台积电", "TSMC", "华为", "阿里巴巴",
            "谷歌", "微软", "OpenAI", "百度", "腾讯", "中芯国际",
            "三星", "SK海力士", "美光", "AMD", "Intel", "中际旭创",
        ),
    ),
    EntityTypeId.PRODUCT: EntityTypeDefinition(
        id=EntityTypeId.PRODUCT,
        label="产品",
        label_en="Product",
        description=(
            "具有商业型号或版本的具体产品，包括 GPU 型号、服务器产品线、"
            "AI 加速卡、芯片型号、终端产品等可购买的商业实体。"
        ),
        example_mentions=(
            "H100", "H800", "A100", "B200", "昇腾910", "昇腾910B",
            "DGX H100", "MI300X", "寒武纪MLU370", "ChatGPT", "GPT-4o",
            "Gemini Ultra", "Claude 3", "Qwen2.5", "DeepSeek-R1",
            "PowerEdge", "ThinkSystem", "AI服务器", "800G光模块",
        ),
    ),
    EntityTypeId.TECHNOLOGY: EntityTypeDefinition(
        id=EntityTypeId.TECHNOLOGY,
        label="技术",
        label_en="Technology",
        description=(
            "底层技术方案、工艺节点、架构范式或技术规范，不与特定商业型号绑定，"
            "包括封装工艺、训练范式、互联协议、存储技术等。"
        ),
        example_mentions=(
            "CoWoS", "SoIC", "先进封装", "HBM", "NVLink", "InfiniBand",
            "Transformer", "MoE", "RLHF", "3nm", "2nm", "GAA",
            "硅光", "CPO", "液冷", "浸没冷却", "RDMA", "RoCE",
            "NVMe-oF", "CXL", "PCIe 5.0",
        ),
    ),
    EntityTypeId.SUPPLY_CHAIN_ROLE: EntityTypeDefinition(
        id=EntityTypeId.SUPPLY_CHAIN_ROLE,
        label="供应链角色",
        label_en="Supply Chain Role",
        description=(
            "描述实体在 AI 硬件供应链中所扮演的角色类型，如晶圆代工厂、"
            "芯片设计商、封装测试厂、ODM/OEM 整机厂等。"
            "在信息链构建中作为节点类型标注，连接公司与其在链中的位置。"
        ),
        example_mentions=(
            "代工厂", "晶圆厂", "芯片设计商", "Fabless", "IDM",
            "封装测试厂", "OSAT", "ODM", "OEM", "EMS",
            "整机厂商", "系统集成商", "模块厂", "材料供应商",
            "设备商", "EDA厂商", "云服务商", "算力供应商",
        ),
    ),
    EntityTypeId.REGION: EntityTypeDefinition(
        id=EntityTypeId.REGION,
        label="地区",
        label_en="Region",
        description=(
            "与 AI 产业相关的地理区域，包括国家、经济体、城市及特定经济区，"
            "用于标注供应链地域分布、政策管辖范围及市场归属。"
        ),
        example_mentions=(
            "美国", "中国", "台湾", "韩国", "日本", "欧盟",
            "荷兰", "以色列", "东南亚", "硅谷", "深圳",
            "台积电台湾", "亚利桑那", "Dresden", "熊本",
        ),
    ),
    EntityTypeId.POLICY_BODY: EntityTypeDefinition(
        id=EntityTypeId.POLICY_BODY,
        label="政策主体",
        label_en="Policy Body",
        description=(
            "制定或执行 AI 及半导体相关政策、出口管制、产业规划的政府机构、"
            "监管机构或行业组织，是信息链中的政策节点来源。"
        ),
        example_mentions=(
            "美国商务部", "BIS", "工业和信息化部", "工信部",
            "国家发展改革委", "发改委", "中国证监会", "美联储",
            "欧盟委员会", "日本经济产业省", "METI",
            "SEMI", "IEEE", "JEDEC", "国务院", "白宫",
        ),
    ),
}


# ---------------------------------------------------------------------------
# 公开辅助 API
# ---------------------------------------------------------------------------

def get_entity_type(type_id: EntityTypeId) -> EntityTypeDefinition:
    """通过 EntityTypeId 获取实体类型定义，不存在时抛出 KeyError。"""
    return ENTITY_TYPE_TAXONOMY[type_id]


def all_entity_types() -> List[EntityTypeDefinition]:
    """返回所有实体类型定义的列表，顺序与枚举声明一致。"""
    return [ENTITY_TYPE_TAXONOMY[tid] for tid in EntityTypeId]


def find_types_by_mention(mention: str) -> List[EntityTypeDefinition]:
    """
    在所有实体类型的典型提及示例中执行大小写不敏感的子串匹配，
    返回命中的实体类型列表（可能为空或多个）。

    注意：这是辅助查找，不是正式抽取算法，后者由 rules/ 模块实现。
    """
    mention_lower = mention.lower()
    return [
        defn
        for defn in ENTITY_TYPE_TAXONOMY.values()
        if any(mention_lower in ex.lower() for ex in defn.example_mentions)
    ]


def entity_type_ids() -> List[EntityTypeId]:
    """返回所有实体类型 ID 的列表。"""
    return list(EntityTypeId)
