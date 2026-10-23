"""股票池（universe）：每天哪些标的"可以投资"。

为什么需要动态股票池：
1. 幸存者偏差：如果只研究"今天还在交易"的合约，等于事先剔除了所有后来崩盘下架的币，
   回测会系统性高估收益。所以候选集合必须包含已下架合约，它们在下架前的每一天都可能入选。
2. 流动性：成交额太小的合约，真实交易时滑点巨大，回测收益不可实现。

规则：在日期 d，候选标的满足
- 当天有有效收盘价（能交易）；
- 上市已满 min_history 天（新币上市初期价格行为异常，且因子需要回看窗口）；
- 过去 lookback 天平均成交额排名前 top_n。

# [前视] 所有条件只用到 d 当天收盘及之前的数据（rolling 窗口向后看，没有 shift(-k)）。
# 在 d 收盘时刻决定 d 的股票池，并在同一时刻按因子调仓，这些信息都已可得。
# 绝不能用"最终是否下架"之类的元数据（store.build_symbol_meta）来筛选。
"""

import pandas as pd


def liquidity_universe(quote_volume: pd.DataFrame, close: pd.DataFrame, top_n: int = 50,
                       lookback: int = 30, min_history: int = 60) -> pd.DataFrame:
    """返回布尔宽表：True 表示该标的在该日期属于股票池。"""
    tradable = close.notna()
    # 上市天数：累计有效收盘价的天数（只数过去）
    history = tradable.cumsum()
    adv = quote_volume.rolling(lookback, min_periods=int(lookback * 0.8)).mean()
    eligible = tradable & (history >= min_history) & adv.notna()
    # 只在合格标的里排名；不合格的 adv 设成 NaN，不参与排名
    rank = adv.where(eligible).rank(axis=1, ascending=False, method="first")
    return eligible & (rank <= top_n)
