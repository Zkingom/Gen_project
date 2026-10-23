"""时间戳处理与资金费率—K 线对齐规则。

这是整个数据层最容易出错、也最容易在面试中被追问的地方，所以单独成文件。

约定（全部为 UTC）：
- 日线 K 线用"开盘日期" d 标识，覆盖区间 [d 00:00, d+1 00:00)。
  它的收盘价 close_d 在 d+1 00:00 才确定。
- 我们说"日期 d 的信息"，指的是**在 d+1 00:00（即 d 的收盘时刻）已经可得**的信息。
- 资金费在固定时刻结算（通常 00:00 / 08:00 / 16:00）。在结算时刻持有仓位的人
  按 仓位名义价值 × 资金费率 支付或收取。

对齐规则：结算时间 t 落在 (d 00:00, d+1 00:00] 的资金费，归属日线 d。
为什么是左开右闭：
- 假设在 d 的开盘（= d-1 的收盘，00:00）建仓、持有到 d 的收盘（d+1 00:00），
  那么持仓期间经历的结算正是 d 08:00、d 16:00、d+1 00:00 这三次。
  （d 00:00 那次结算发生在建仓的同一瞬间，按交易所规则此时刚开的仓不参与。）
- 这样"日线 d 的价格收益"和"日线 d 的资金费"描述的是**同一段持仓**，回测时可以直接相加。
- d+1 00:00 的费率在 d 收盘时刻已经公布，所以它属于"日期 d 的信息"，因子可以使用。
"""

import numpy as np
import pandas as pd

from .schema import MS_PER_DAY


def epoch_to_utc(values) -> pd.Series:
    """把 Binance 的整数时间戳转成 UTC datetime。

    Binance 大部分文件是毫秒；2025 年起部分文件改成了微秒。
    用数量级判断：毫秒时间戳在 2001~2286 年间约为 1e12~1e13，微秒则约 1e15~1e16。
    """
    arr = np.asarray(values, dtype="int64")
    unit = "us" if arr.size and np.nanmax(np.abs(arr)) > 1e14 else "ms"
    out = pd.to_datetime(arr, unit=unit, utc=True)
    return pd.Series(out).dt.as_unit("ms")


def round_funding_time(ts: pd.Series) -> pd.Series:
    """去掉资金费结算时间上的毫秒级抖动（真实数据里常见 xx:00:00.004 这种值）。

    四舍五入到整分钟：结算本来就在整点，抖动只有几毫秒，不会被错误地挪到别的分钟。
    """
    return ts.dt.round("min")


def funding_bar_date(funding_time: pd.Series) -> pd.Series:
    """按 (d 00:00, d+1 00:00] 规则，返回每次结算归属的日线日期（tz-naive 日期）。

    做法：先减 1 毫秒再向下取整到天。
    - 08:00 d  -> 07:59:59.999 d -> d
    - 00:00 d+1 -> 23:59:59.999 d -> d   （收盘时刻那一笔归属当天）
    """
    shifted = funding_time - pd.Timedelta(milliseconds=1)
    return shifted.dt.floor("D").dt.tz_localize(None)


def kline_date(open_time: pd.Series) -> pd.Series:
    """日线的标识日期 = 开盘时间所在的 UTC 日期（tz-naive，方便做面板索引）。"""
    return open_time.dt.floor("D").dt.tz_localize(None)


def date_to_open_ms(dates) -> np.ndarray:
    """日期 -> 当天 00:00 UTC 的毫秒时间戳（合成数据生成器用）。"""
    idx = pd.DatetimeIndex(dates)
    return idx.as_unit("ms").asi8.astype("int64")


__all__ = [
    "epoch_to_utc", "round_funding_time", "funding_bar_date",
    "kline_date", "date_to_open_ms", "MS_PER_DAY",
]
