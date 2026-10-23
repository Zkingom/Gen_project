"""成交量类因子：异常成交额（换手）、Amihud 非流动性、量价相关性。

加密货币没有统一可靠的"流通市值"数据，所以用成交额（USDT 计）的相对变化来代替股票里的换手率。

# [前视] 全部为包含当天 d 的向后看 rolling 窗口。
"""

import numpy as np

from .base import register


@register("volume_ratio_5_60", direction=-1, category="成交量")
def volume_ratio_5_60(panel):
    """异常成交额：近 5 天均值 / 近 60 天均值（取对数）。突然放量常伴随过度关注，之后偏弱。"""
    qv = panel["quote_volume"].astype("float64").where(lambda x: x > 0)  # 成交额为 0 视为缺失
    short = qv.rolling(5, min_periods=4).mean()
    long = qv.rolling(60, min_periods=45).mean()
    return np.log(short / long)


@register("amihud_20d", direction=+1, category="成交量")
def amihud_20d(panel):
    """Amihud 非流动性：mean(|r| / 成交额)，每单位成交额推动的价格变动。越不流动要求的补偿越高。"""
    qv = panel["quote_volume"].astype("float64").where(lambda x: x > 0)
    illiq = panel["ret"].abs().astype("float64") / qv
    # 取对数：原始值跨好几个数量级，对数后横截面分布更对称，IC 更稳健
    return np.log(illiq.rolling(20, min_periods=15).mean() * 1e9 + 1e-12)


@register("pv_corr_20d", direction=-1, category="量价")
def pv_corr_20d(panel):
    """量价相关性：过去 20 天日收益与对数成交额的相关系数。"放量上涨"多的币后续倾向反转。"""
    ret = panel["ret"].astype("float64")
    logv = np.log(panel["quote_volume"].astype("float64").where(lambda x: x > 0))
    return ret.rolling(20, min_periods=15).corr(logv)
