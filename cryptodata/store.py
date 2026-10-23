"""parquet 存储布局与读写。

目录布局（root 默认为 data/）：
    root/klines_1d/<SYMBOL>.parquet   每个标的一个文件
    root/funding/<SYMBOL>.parquet
    root/meta/symbols.parquet         所有标的（含已下架）的上市/下架信息

为什么按标的分文件：
- 读取时可以只打开需要的标的，内存占用与"标的数 × 天数"成正比，不需要一次载入整表；
- 增量更新某个标的时不用重写全部数据。
"""

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .schema import SYMBOL_META_COLUMNS, STATUS_DELISTED, STATUS_TRADING

KLINE_DIR = "klines_1d"
FUNDING_DIR = "funding"
META_FILE = "meta/symbols.parquet"


def _path(root, sub: str, symbol: str) -> Path:
    return Path(root) / sub / f"{symbol}.parquet"


def write_table(df: pd.DataFrame, root, sub: str, symbol: str) -> Path:
    path = _path(root, sub, symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)
    return path


def read_table(root, sub: str, symbol: str, columns=None, filters=None) -> pd.DataFrame:
    """读取一个标的；filters 会下推到 parquet，只读需要的时间段。"""
    path = _path(root, sub, symbol)
    if not path.exists():
        return pd.DataFrame()
    return pq.read_table(path, columns=columns, filters=filters).to_pandas()


def list_symbols(root, sub: str = KLINE_DIR) -> list[str]:
    d = Path(root) / sub
    return sorted(p.stem for p in d.glob("*.parquet")) if d.exists() else []


def build_symbol_meta(root, data_end: pd.Timestamp, delist_gap_days: int = 3) -> pd.DataFrame:
    """扫描所有 K 线文件，生成标的元数据。

    一个标的最后一根 K 线早于全局数据结束日 delist_gap_days 天以上，就认为它已下架。
    [前视] 这张表本身包含"未来"信息（最终是否下架），因此**只能用于描述数据**，
    绝不能用于在历史某天筛选股票池——筛选必须用 universe.py 里只看过去的规则。
    """
    rows = []
    for sym in list_symbols(root):
        t = read_table(root, KLINE_DIR, sym, columns=["open_time", "close"])
        valid = t.dropna(subset=["close"])
        if valid.empty:
            continue
        first = valid["open_time"].min().tz_localize(None).normalize()
        last = valid["open_time"].max().tz_localize(None).normalize()
        status = STATUS_DELISTED if (data_end - last).days > delist_gap_days else STATUS_TRADING
        rows.append((sym, first, last, len(valid), status))
    meta = pd.DataFrame(rows, columns=SYMBOL_META_COLUMNS)
    path = Path(root) / META_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    meta.to_parquet(path, index=False)
    return meta


def read_symbol_meta(root) -> pd.DataFrame:
    return pd.read_parquet(Path(root) / META_FILE)
