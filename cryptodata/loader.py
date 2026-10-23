"""统一读取接口：给定时间范围和标的列表，返回整齐的"日期 × 标的"面板。

面板（panel）是横截面研究的基本数据结构：
- 行 = 日期，列 = 标的，每个字段（收盘价、成交额、资金费……）一张宽表；
- 所有宽表共享同一套行列索引，可以直接做逐元素运算，不会错位。
"""

from functools import cached_property

import numpy as np
import pandas as pd

from . import store
from .align import kline_date

KLINE_FIELDS = ["open", "high", "low", "close", "volume", "quote_volume",
                "taker_buy_volume", "taker_buy_quote_volume", "trades"]
FUNDING_FIELDS = ["funding", "funding_count"]

MAX_PANEL_BYTES = 1 << 30  # 1 GB：主人本地内存约 5GB，单步不能超过这个量级


class Panel:
    """多个字段的宽表集合，所有字段索引一致（日期 × 标的），数值为 float32。"""

    def __init__(self, fields: dict[str, pd.DataFrame]):
        dates = sorted(set().union(*[f.index for f in fields.values()]))
        syms = sorted(set().union(*[f.columns for f in fields.values()]))
        idx = pd.DatetimeIndex(dates, name="date")
        cols = pd.Index(syms, name="symbol")
        self.fields = {k: v.reindex(index=idx, columns=cols).astype("float32")
                       for k, v in fields.items()}

    def __getitem__(self, name: str) -> pd.DataFrame:
        if name == "ret":
            return self.ret
        return self.fields[name]

    def __contains__(self, name: str) -> bool:
        return name == "ret" or name in self.fields

    @property
    def dates(self) -> pd.DatetimeIndex:
        return next(iter(self.fields.values())).index

    @property
    def symbols(self) -> pd.Index:
        return next(iter(self.fields.values())).columns

    @cached_property
    def ret(self) -> pd.DataFrame:
        """日收益率（收盘到收盘），见 compute_returns。"""
        return compute_returns(self.fields["close"])

    def slice(self, start=None, end=None) -> "Panel":
        return Panel({k: v.loc[start:end] for k, v in self.fields.items()})

    def replace(self, **new_fields) -> "Panel":
        """返回替换了部分字段的新面板（原面板不变）；前视测试里用来篡改未来数据。"""
        return Panel({**self.fields, **new_fields})


def compute_returns(close: pd.DataFrame, max_gap: int = 3) -> pd.DataFrame:
    """简单收益率 r_d = close_d / close_{上一个有效收盘} - 1。

    为什么不用 close.pct_change()：如果中间缺了一天，pct_change 会让缺口后那天的收益变 NaN，
    这段真实发生的涨跌就凭空消失了（回测里持仓的盈亏会被漏算）。
    这里用"上一个有效收盘价"做分母（最多向前找 max_gap 天），缺口期间的涨跌会完整地记在缺口后第一天。
    缺失当天本身的收益仍是 NaN（那天没有价格，不能交易）。

    # [前视] ffill 只向过去找值，shift(1) 保证分母是 d 之前的价格，不会用到未来。
    """
    prev = close.ffill(limit=max_gap).shift(1)
    ret = close / prev - 1.0
    return ret.astype("float32")


def _date_filters(start, end) -> list:
    f = []
    if start is not None:
        f.append(("open_time", ">=", pd.Timestamp(start, tz="UTC").as_unit("ms")))
    if end is not None:
        f.append(("open_time", "<=", pd.Timestamp(end, tz="UTC").as_unit("ms")))
    return f or None


def _check_memory(n_days: int, n_syms: int, n_fields: int) -> None:
    est = n_days * n_syms * n_fields * 4
    if est > MAX_PANEL_BYTES:
        raise MemoryError(
            f"面板预计 {est / 1e9:.2f} GB，超过 1 GB 上限；请缩短时间范围或减少标的/字段，分块读取。")


def load_klines_wide(root, symbols, start=None, end=None, fields=KLINE_FIELDS) -> dict:
    """逐个标的读取 K 线并拼成宽表。每次只有一个标的的数据在内存里做转换。"""
    cols = {f: {} for f in fields}
    filters = _date_filters(start, end)
    for sym in symbols:
        t = store.read_table(root, store.KLINE_DIR, sym, columns=["open_time"] + list(fields),
                             filters=filters)
        if t.empty:
            continue
        t.index = pd.DatetimeIndex(kline_date(t["open_time"]))
        for f in fields:
            cols[f][sym] = t[f].astype("float32")
    return {f: pd.DataFrame(v) for f, v in cols.items()}


def load_funding_daily(root, symbols, start=None, end=None) -> dict:
    """读取资金费并按 bar_date 汇总成日度：当天所有结算费率之和、结算次数。

    日度费率之和 × 持仓名义价值 ≈ 持有这根日线期间付出（或收到）的资金费。
    """
    total, count = {}, {}
    f = []
    if start is not None:
        f.append(("bar_date", ">=", pd.Timestamp(start).as_unit("ms")))
    if end is not None:
        f.append(("bar_date", "<=", pd.Timestamp(end).as_unit("ms")))
    for sym in symbols:
        t = store.read_table(root, store.FUNDING_DIR, sym,
                             columns=["bar_date", "funding_rate"], filters=f or None)
        if t.empty:
            continue
        g = t.groupby("bar_date")["funding_rate"]
        total[sym] = g.sum().astype("float32")
        count[sym] = g.size().astype("float32")
    return {"funding": pd.DataFrame(total), "funding_count": pd.DataFrame(count)}


def load_panel(root, start=None, end=None, symbols=None, kline_fields=KLINE_FIELDS,
               with_funding: bool = True) -> Panel:
    """主入口：返回 [start, end] 区间、给定标的（默认全部，**包括已下架**）的面板。"""
    if symbols is None:
        symbols = store.list_symbols(root)
    n_days = (pd.Timestamp(end) - pd.Timestamp(start)).days + 1 if start and end else 4000
    _check_memory(n_days, len(symbols), len(kline_fields) + 2 * with_funding)
    fields = load_klines_wide(root, symbols, start, end, kline_fields)
    if with_funding:
        fields.update(load_funding_daily(root, symbols, start, end))
    panel = Panel(fields)
    # 资金费面板只保留有 K 线的日期（防止某个 bar_date 落在 K 线范围之外造成多出一行）
    kdates = fields["close"].index
    return Panel({k: v.reindex(index=kdates) for k, v in panel.fields.items()})


__all__ = ["Panel", "compute_returns", "load_panel", "load_klines_wide", "load_funding_daily"]
