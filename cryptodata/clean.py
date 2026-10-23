"""数据校验与清洗。

输入：原始格式（schema.RAW_*_COLUMNS），无论来自真实下载还是合成生成器。
输出：存储格式（schema.KLINE_COLUMNS / FUNDING_COLUMNS）+ 一份清洗报告。

缺失值处理原则（重要的研究设计决定，见 docs/DECISIONS.md）：
- **不在存储层填充价格**。交易所宕机、数据缺失的那天就是 NaN，如实保留。
  如果在这里 ffill，下游会误以为那天"价格没动、成交量为 0"，会扭曲波动率和成交额因子。
- 收益率怎么跨越缺口，交给 loader 统一处理（见 loader.compute_returns）。
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import align
from .schema import KLINE_COLUMNS, KLINE_FLOAT_COLUMNS, FUNDING_COLUMNS

# 资金费率的合理范围：Binance 单次结算上限一般是 ±0.3%~±2%，超过 5% 一定是脏数据
MAX_ABS_FUNDING_RATE = 0.05


@dataclass
class CleanReport:
    """记录清洗过程中发现了什么，方便排查数据问题。"""
    symbol: str
    n_raw: int = 0
    n_duplicates: int = 0
    n_invalid: int = 0
    n_missing_days: int = 0
    notes: list = field(default_factory=list)


def _kline_invalid_mask(df: pd.DataFrame) -> pd.Series:
    """找出逻辑上不可能的 K 线：价格非正、最高价低于开/收、最低价高于开/收、成交量为负。"""
    price = df[["open", "high", "low", "close"]]
    bad = (price <= 0).any(axis=1) | price.isna().any(axis=1)
    bad |= df["high"] < df[["open", "close"]].max(axis=1)
    bad |= df["low"] > df[["open", "close"]].min(axis=1)
    bad |= (df["volume"] < 0) | (df["quote_volume"] < 0)
    return bad


def clean_klines(raw: pd.DataFrame, symbol: str) -> tuple[pd.DataFrame, CleanReport]:
    """清洗一个标的的日线 K 线。

    步骤：时间戳统一 -> 去重 -> 逻辑校验（坏行置 NaN 而不是删除）-> 补齐日历（缺失日为 NaN）。
    """
    rep = CleanReport(symbol=symbol, n_raw=len(raw))
    df = raw.reset_index(drop=True)
    df["open_time"] = align.epoch_to_utc(df["open_time"])  # tz-aware UTC，毫秒精度
    for c in KLINE_FLOAT_COLUMNS:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    df["trades"] = pd.to_numeric(df["count"], errors="coerce")

    # 重复行：同一 open_time 出现多次（多次下载拼接时常见），保留最后一条
    df = df.sort_values("open_time")
    dup = df.duplicated("open_time", keep="last")
    rep.n_duplicates = int(dup.sum())
    df = df.loc[~dup]

    # 坏行：保留时间戳，把数值置为 NaN，这样"这天有记录但不可信"的信息不会丢
    bad = _kline_invalid_mask(df)
    rep.n_invalid = int(bad.sum())
    df.loc[bad, KLINE_FLOAT_COLUMNS + ["trades"]] = np.nan

    df = _reindex_daily(df, rep)
    for c in KLINE_FLOAT_COLUMNS:
        df[c] = df[c].astype("float32")
    df["trades"] = df["trades"].astype("float32")  # 用 float 才能表示 NaN
    return df[KLINE_COLUMNS].reset_index(drop=True), rep


def _reindex_daily(df: pd.DataFrame, rep: CleanReport) -> pd.DataFrame:
    """把 K 线补齐到 [首日, 末日] 的完整日历，缺失的日子数值为 NaN。

    只在首末日之间补：首日之前是"还没上市"，末日之后是"已经下架"，这两段不能补。
    """
    if df.empty:
        return df
    full = pd.date_range(df["open_time"].iloc[0], df["open_time"].iloc[-1], freq="D")
    out = df.set_index("open_time").reindex(full)
    out.index.name = "open_time"
    rep.n_missing_days = int(len(full) - len(df))
    return out.reset_index()


def clean_funding(raw: pd.DataFrame, symbol: str) -> tuple[pd.DataFrame, CleanReport]:
    """清洗一个标的的资金费率历史，并计算每次结算归属的日线日期。"""
    rep = CleanReport(symbol=symbol, n_raw=len(raw))
    raw = raw.reset_index(drop=True)
    df = pd.DataFrame({
        "funding_time": align.round_funding_time(align.epoch_to_utc(raw["calc_time"])),
        "funding_rate": pd.to_numeric(raw["last_funding_rate"], errors="coerce"),
        "funding_interval_hours": pd.to_numeric(raw["funding_interval_hours"], errors="coerce"),
    })
    df = df.sort_values("funding_time")
    dup = df.duplicated("funding_time", keep="last")
    rep.n_duplicates = int(dup.sum())
    df = df.loc[~dup]

    bad = df["funding_rate"].isna() | (df["funding_rate"].abs() > MAX_ABS_FUNDING_RATE)
    rep.n_invalid = int(bad.sum())
    df = df.loc[~bad].copy()  # 资金费没有"日历"概念，坏记录直接删除

    df["bar_date"] = align.funding_bar_date(df["funding_time"])
    df["funding_rate"] = df["funding_rate"].astype("float32")
    # 老文件没有间隔列（NaN），按 8 小时处理
    df["funding_interval_hours"] = df["funding_interval_hours"].fillna(8).astype("int8")
    return df[FUNDING_COLUMNS].reset_index(drop=True), rep
