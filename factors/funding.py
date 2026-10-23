"""资金费率类因子：永续合约特有。

资金费机制（详见 docs/LEARNING_GUIDE.md）：永续合约没有到期日，交易所用资金费把合约价格"拴"在现货附近。
合约价高于现货（多头更急切）时资金费为正，多头定期付钱给空头。
所以资金费率可以看作**多头拥挤度**的度量：费率越高，说明加杠杆做多的人越多，
一旦行情反转容易出现多头踩踏，同时持有多头还要持续付费。

# [前视] panel["funding"] 的日期 d = 结算时间在 (d 00:00, d+1 00:00] 的费率之和，
# 在 d 收盘时刻（d+1 00:00）全部已经公布，因此可以用于 d 的因子。见 cryptodata/align.py。
"""

from .base import register


@register("funding_level_7d", direction=-1, category="资金费")
def funding_level_7d(panel):
    """资金费率水平：过去 7 天日度资金费率均值。费率高 = 多头拥挤，预期未来偏弱。"""
    return panel["funding"].astype("float64").rolling(7, min_periods=5).mean()


@register("funding_change_7_30", direction=-1, category="资金费")
def funding_change_7_30(panel):
    """资金费率变化：7 天均值减 30 天均值。拥挤度正在快速上升的币，预期未来偏弱。"""
    f = panel["funding"].astype("float64")
    return f.rolling(7, min_periods=5).mean() - f.rolling(30, min_periods=20).mean()
