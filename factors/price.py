"""价格类因子：短期反转、中期动量、波动率。

都基于对数收益 log(1+r)：对数收益可以直接相加得到区间收益，缺失一天时 rolling sum 仍可计算。

# [前视] 本文件所有 rolling 窗口都包含当天 d 并向过去延伸；
# 需要"跳过最近几天"时用 shift(k)，k 为正数表示取过去的值。不出现 shift(-k)。
"""

import numpy as np

from .base import register


def _log_ret(panel):
    return np.log1p(panel["ret"].astype("float64"))


@register("reversal_5d", direction=+1, category="价格")
def reversal_5d(panel):
    """短期反转：过去 5 天累计对数收益取负。过去涨多的币短期倾向回落（流动性冲击/过度反应）。"""
    return -_log_ret(panel).rolling(5, min_periods=4).sum()


@register("momentum_30d", direction=+1, category="价格")
def momentum_30d(panel):
    """中期动量：d-29 到 d-5 共 25 天累计收益，跳过最近 5 天以避开短期反转效应。"""
    # [前视] shift(5)：d 这一行取的是截至 d-5 的 25 天和，只用过去数据
    return _log_ret(panel).rolling(25, min_periods=20).sum().shift(5)


@register("volatility_20d", direction=-1, category="价格")
def volatility_20d(panel):
    """波动率：过去 20 天日收益标准差。"低波动异象"：高波动资产长期收益反而偏低。"""
    return panel["ret"].astype("float64").rolling(20, min_periods=15).std()
