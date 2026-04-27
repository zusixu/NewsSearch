"""
关系类型定义（Relation Type Definition）

信息链中节点之间的关系类型枚举，供 :class:`~app.chains.chain.ChainNode`
的 ``relation_to_prev`` 字段使用。

设计决策
--------
- 继承 ``str`` + ``Enum``：枚举成员本身即是字符串，直接支持 JSON / YAML 序列化；
  无需额外转换，不会丢失可读性。
- 枚举值使用中文标签，与文档和业务语义保持一致，避免翻译层引入歧义。
- 枚举不设 ``NONE`` 成员；"无关系"语义由 ``None`` 表达（见 ``ChainNode``）。

成员
----
CAUSAL
    因果关系：前一节点是后一节点的直接或间接原因。
TEMPORAL
    时间延续：两节点属于同一事件的时间线延伸，时序相邻但无直接因果。
UPSTREAM_DOWNSTREAM
    上下游影响：供应链、产业链或政策传导中的上下游传播关系。
SAME_TOPIC
    同主题发酵：两节点围绕同一主题持续讨论/扩散，情绪或热度传导。
"""

from __future__ import annotations

from enum import Enum


class RelationType(str, Enum):
    """信息链节点间的关系类型。

    所有成员均为字符串子类，可直接用于 JSON / YAML 序列化，
    也可通过 ``RelationType("因果")`` 从字符串值反向构造。
    """

    CAUSAL = "因果"
    TEMPORAL = "时间延续"
    UPSTREAM_DOWNSTREAM = "上下游影响"
    SAME_TOPIC = "同主题发酵"
