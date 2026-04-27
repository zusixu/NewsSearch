"""
AkShare 动态股票解析器。

通过 AkShare 实时查询板块/概念成分股，补充硬编码的 stock_candidates，
解决 A 股映射数据源静态、覆盖范围有限的问题。

设计原则
--------
- 懒加载 AkShare，模块导入时不依赖网络或 akshare 包。
- 所有 AkShare 调用包裹在 try/except 中，失败时静默回退到硬编码数据。
- 内存缓存（TTL 1 天）避免同一次 pipeline 运行中重复请求同一板块。
- 向后兼容：resolver 为可选组件，不注入时行为与之前完全一致。
"""

from __future__ import annotations

import datetime
import time as _time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.mapping.industry_chain import IndustryChainNode


# ---------------------------------------------------------------------------
# Internal cache entry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CacheEntry:
    """缓存条目，带过期时间。"""

    stocks: Tuple[Tuple[str, str], ...]
    expires_at: float


# ---------------------------------------------------------------------------
# Lazy AkShare import helper
# ---------------------------------------------------------------------------


def _import_akshare() -> Any:
    """懒加载 akshare，失败时返回 None 而不是抛异常。"""
    try:
        import akshare as ak  # noqa: PLC0415
        return ak
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Sector → AkShare concept/industry name mapping
# ---------------------------------------------------------------------------

# 将产业链节点的 sector_name 映射到 AkShare 东方财富概念/行业板块名称。
# 东方财富的板块名称会随时间微调，这里维护一个保守映射表。
_SECTOR_TO_AKSHARE_CONCEPT: Dict[str, str] = {
    "算力": "算力概念",
    "存储": "存储芯片",
    "内存": "存储芯片",
    "AI 芯片": "半导体概念",
    "半导体": "半导体概念",
    "光模块": "光通信模块",
    "AI 供应链": "服务器",
    "AI 大模型": "人工智能",
    "云服务": "云计算",
    "AI 应用": "人工智能",
    "人工智能": "人工智能",
}

# 备选映射：当概念板块查询不到时，可尝试行业板块（部分名称不同）
_SECTOR_TO_AKSHARE_INDUSTRY: Dict[str, str] = {
    "算力": "互联网服务",
    "存储": "电子元件",
    "内存": "电子元件",
    "AI 芯片": "半导体",
    "半导体": "半导体",
    "光模块": "通信设备",
    "AI 供应链": "计算机设备",
    "AI 大模型": "软件开发",
    "云服务": "互联网服务",
    "AI 应用": "软件开发",
    "人工智能": "软件开发",
}


# ---------------------------------------------------------------------------
# AkShareStockResolver
# ---------------------------------------------------------------------------


class AkShareStockResolver:
    """
    通过 AkShare 动态解析板块/概念对应 A 股成分股。

    使用方式::

        resolver = AkShareStockResolver()
        stocks = resolver.resolve_stocks_for_node(node)
        # 返回合并后的 (code, name) 列表，去重并按原顺序保留硬编码条目
    """

    # 默认缓存 TTL：1 天（秒）
    DEFAULT_TTL_SECONDS: int = 86400

    # 请求超时（秒）
    DEFAULT_TIMEOUT: int = 30

    def __init__(
        self,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        timeout: int = DEFAULT_TIMEOUT,
        enable_concept: bool = True,
        enable_industry: bool = True,
    ) -> None:
        """
        初始化解析器。

        Parameters
        ----------
        ttl_seconds
            内存缓存存活时间。
        timeout
            AkShare 请求超时时间（部分 akshare 函数不支持 timeout 参数，
            此时此参数仅作为预留）。
        enable_concept
            是否启用概念板块查询（东方财富概念板块）。
        enable_industry
            是否启用行业板块查询（东方财富行业板块）。
        """
        self._ttl_seconds = ttl_seconds
        self._timeout = timeout
        self._enable_concept = enable_concept
        self._enable_industry = enable_industry
        self._cache: Dict[str, _CacheEntry] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve_stocks_for_node(
        self,
        node: IndustryChainNode,
    ) -> Tuple[Tuple[str, str], ...]:
        """
        为产业链节点解析完整的个股列表。

        逻辑：
        1. 以硬编码 ``stock_candidates`` 为基准（优先保留）。
        2. 尝试通过 AkShare 查询该节点 sector_name 对应的板块成分股。
        3. 合并两者，按股票代码去重，硬编码条目排在前面。
        4. 若 AkShare 不可用或查询失败，直接返回硬编码数据。

        Returns
        -------
        tuple[tuple[str, str], ...]
            (股票代码, 股票名称) 元组，已去重。
        """
        base_candidates = list(node.stock_candidates)

        # 尝试从 AkShare 获取动态成分股
        dynamic_candidates = self._fetch_stocks_for_sector(node.sector_name)

        if not dynamic_candidates:
            return tuple(base_candidates)

        # 合并并去重：硬编码优先，保持硬编码的顺序和名称
        seen_codes = {code for code, _ in base_candidates}
        merged = list(base_candidates)

        for code, name in dynamic_candidates:
            clean_code = _clean_stock_code(code)
            if clean_code and clean_code not in seen_codes:
                seen_codes.add(clean_code)
                merged.append((clean_code, name))

        return tuple(merged)

    def clear_cache(self) -> None:
        """清空内存缓存。"""
        self._cache.clear()

    @property
    def cache_keys(self) -> List[str]:
        """返回当前缓存中的所有 key（调试用）。"""
        return list(self._cache.keys())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_stocks_for_sector(
        self,
        sector_name: str,
    ) -> List[Tuple[str, str]]:
        """
        获取指定板块名称对应的股票列表（带缓存）。

        先查概念板块，若失败或无结果则回退到行业板块。
        """
        cache_key = f"sector:{sector_name}"

        # 1. 检查缓存
        now = _time.time()
        entry = self._cache.get(cache_key)
        if entry is not None and now < entry.expires_at:
            return list(entry.stocks)

        # 2. 调用 AkShare
        ak = _import_akshare()
        if ak is None:
            return []

        results: List[Tuple[str, str]] = []

        # 2a. 概念板块
        if self._enable_concept and not results:
            concept_name = _SECTOR_TO_AKSHARE_CONCEPT.get(sector_name)
            if concept_name:
                results = self._try_fetch_concept(ak, concept_name)

        # 2b. 行业板块
        if self._enable_industry and not results:
            industry_name = _SECTOR_TO_AKSHARE_INDUSTRY.get(sector_name)
            if industry_name:
                results = self._try_fetch_industry(ak, industry_name)

        # 3. 写入缓存（包括空结果，避免频繁重试空查询）
        self._cache[cache_key] = _CacheEntry(
            stocks=tuple(results),
            expires_at=now + self._ttl_seconds,
        )

        return results

    def _try_fetch_concept(
        self,
        ak: Any,
        concept_name: str,
    ) -> List[Tuple[str, str]]:
        """尝试获取概念板块成分股。"""
        try:
            df = ak.stock_board_concept_cons_em(symbol=concept_name)
            return self._parse_dataframe(df)
        except Exception:  # noqa: BLE001
            return []

    def _try_fetch_industry(
        self,
        ak: Any,
        industry_name: str,
    ) -> List[Tuple[str, str]]:
        """尝试获取行业板块成分股。"""
        try:
            df = ak.stock_board_industry_cons_em(symbol=industry_name)
            return self._parse_dataframe(df)
        except Exception:  # noqa: BLE001
            return []

    def _parse_dataframe(self, df: Any) -> List[Tuple[str, str]]:
        """从 AkShare DataFrame 中提取 (code, name) 列表。"""
        if df is None or getattr(df, "empty", True):
            return []

        results: List[Tuple[str, str]] = []

        # 东方财富接口常见列名："代码"/" f2"、"名称"/" f14"
        # 优先使用中文列名，其次使用常见 f-code 列名
        code_col = self._pick_column(df, ("代码", " f12", "f12", "股票代码"))
        name_col = self._pick_column(df, ("名称", " f14", "f14", "股票名称"))

        if code_col is None or name_col is None:
            return []

        for _, row in df.iterrows():
            code = _clean_stock_code(str(row.get(code_col, "")))
            name = str(row.get(name_col, "")).strip()
            if code and name and name.lower() != "nan":
                results.append((code, name))

        return results

    @staticmethod
    def _pick_column(df: Any, candidates: Tuple[str, ...]) -> Optional[str]:
        """从 DataFrame 列名中匹配候选列名。"""
        columns = list(df.columns)
        for cand in candidates:
            if cand in columns:
                return cand
        # 模糊匹配（去除空格后）
        col_map = {c.strip(): c for c in columns}
        for cand in candidates:
            if cand.strip() in col_map:
                return col_map[cand.strip()]
        return None


def _clean_stock_code(raw: str) -> Optional[str]:
        """
        清洗股票代码。

        - 去掉 .SH / .SZ / .BJ / .SE 等后缀
        - 去掉空格
        - 保留 6 位数字代码
        """
        if not raw:
            return None

        cleaned = raw.strip().split(".")[0].split("-")[0].strip()

        # 只保留纯数字且长度为 6 的代码（A 股标准）
        if cleaned.isdigit() and len(cleaned) == 6:
            return cleaned

        return None


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def create_akshare_resolver(
    *,
    ttl_seconds: int = AkShareStockResolver.DEFAULT_TTL_SECONDS,
    enable_concept: bool = True,
    enable_industry: bool = True,
) -> AkShareStockResolver:
    """创建默认配置的 AkShare 股票解析器。"""
    return AkShareStockResolver(
        ttl_seconds=ttl_seconds,
        enable_concept=enable_concept,
        enable_industry=enable_industry,
    )
