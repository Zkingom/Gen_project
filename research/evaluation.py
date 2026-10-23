"""单因子评估：IC / RankIC / ICIR / IC 衰减 / 分组回测 / 换手 / 因子相关性。

横截面评估的基本思路：每天单独看"因子排序"和"未来收益排序"是否一致，
再把每天的结果在时间上平均。这样市场整体涨跌（所有币一起涨）不影响结论。
"""

import numpy as np
import pandas as pd

from cryptodata.loader import Panel
from .labels import forward_returns

MIN_NAMES = 10  # 当天有效标的少于这个数，横截面统计没有意义，记为 NaN


def rowwise_corr(x: pd.DataFrame, y: pd.DataFrame, min_names: int = MIN_NAMES) -> pd.Series:
    """逐日（逐行）计算 x 与 y 的横截面 Pearson 相关系数，向量化实现。"""
    mask = x.notna() & y.notna()
    a = x.where(mask).astype("float64")
    b = y.where(mask).astype("float64")
    a = a.sub(a.mean(axis=1), axis=0)
    b = b.sub(b.mean(axis=1), axis=0)
    cov = (a * b).sum(axis=1)
    denom = np.sqrt((a ** 2).sum(axis=1) * (b ** 2).sum(axis=1))
    out = cov / denom.replace(0, np.nan)
    return out.where(mask.sum(axis=1) >= min_names)


def ic_series(factor: pd.DataFrame, fwd: pd.DataFrame, universe: pd.DataFrame,
              method: str = "rank") -> pd.Series:
    """每日 IC。method='pearson' 为普通 IC；'rank' 为 RankIC（Spearman，先排名再算相关）。

    RankIC 对极端值不敏感——加密货币收益肥尾严重，一个暴涨 300% 的币就能主导 Pearson IC，
    因此实践中更常看 RankIC。
    """
    mask = universe & factor.notna() & fwd.notna()
    f, r = factor.where(mask), fwd.where(mask)
    if method == "rank":
        f, r = f.rank(axis=1), r.rank(axis=1)
    return rowwise_corr(f, r)


def ic_summary(ic: pd.Series, h: int = 1) -> dict:
    """IC 统计量。

    - ICIR = mean / std：IC 的"信噪比"，衡量因子是否**稳定地**有效；
    - t 值：持有期 h>1 时相邻两天的标签重叠（共享 h-1 天收益），IC 序列自相关，
      把有效样本数近似为 n/h 来修正，否则 t 值会被高估。
    """
    ic = ic.dropna()
    n = len(ic)
    mean, std = ic.mean(), ic.std()
    icir = mean / std if std > 0 else np.nan
    return {"ic_mean": mean, "ic_std": std, "icir": icir,
            "icir_ann": icir * np.sqrt(365 / h), "t_stat": icir * np.sqrt(n / h),
            "win_rate": (ic > 0).mean(), "n_days": n}


def ic_decay(factor: pd.DataFrame, panel: Panel, universe: pd.DataFrame,
             horizons=(1, 2, 3, 5, 10, 20)) -> pd.DataFrame:
    """IC 衰减：因子对不同持有期收益的预测力。衰减快 = 信号短命 = 需要高频调仓（成本高）。"""
    rows = {}
    for h in horizons:
        ic = ic_series(factor, forward_returns(panel, h), universe, "rank")
        s = ic_summary(ic, h)
        rows[h] = {"rank_ic": s["ic_mean"], "icir": s["icir"], "t_stat": s["t_stat"]}
    return pd.DataFrame(rows).T.rename_axis("horizon")


def quantile_groups(factor: pd.DataFrame, universe: pd.DataFrame, n_groups: int = 5) -> pd.DataFrame:
    """每天把股票池内的标的按因子值分成 n 组：1 = 因子最小，n = 因子最大。"""
    pct = factor.where(universe).rank(axis=1, pct=True)
    return np.ceil(pct * n_groups)


def quantile_returns(factor: pd.DataFrame, fwd1: pd.DataFrame, universe: pd.DataFrame,
                     n_groups: int = 5) -> pd.DataFrame:
    """分组回测（不含成本）：每组等权持有一天的平均收益。列 1..n，外加 'LS' = 第 n 组 - 第 1 组。

    如果因子有效，组收益应随组号单调变化；多空组合 LS 剥离了市场涨跌，只留下因子本身的收益。
    """
    groups = quantile_groups(factor, universe & fwd1.notna(), n_groups)
    out = {}
    for g in range(1, n_groups + 1):
        out[g] = fwd1.where(groups == g).mean(axis=1)
    res = pd.DataFrame(out)
    res["LS"] = res[n_groups] - res[1]
    return res.where(groups.notna().sum(axis=1) >= MIN_NAMES)


def rank_autocorr(factor: pd.DataFrame, universe: pd.DataFrame, lag: int = 1) -> pd.Series:
    """因子排名的自相关：今天和 lag 天前的排名有多像。越接近 1，组合越稳定、换手越低。"""
    r = factor.where(universe).rank(axis=1)
    return rowwise_corr(r, r.shift(lag))


def top_group_turnover(factor: pd.DataFrame, universe: pd.DataFrame, n_groups: int = 5) -> pd.Series:
    """最高组的成分换手率：今天最高组中，有多少比例昨天不在最高组。"""
    top = quantile_groups(factor, universe, n_groups) == n_groups
    new = (top & ~top.shift(1, fill_value=False)).sum(axis=1)
    return (new / top.sum(axis=1).replace(0, np.nan)).iloc[1:]


def factor_corr_matrix(factors: dict, universe: pd.DataFrame) -> pd.DataFrame:
    """因子间相关性：逐日横截面 Spearman 相关，再在时间上平均。高度相关的因子合成时信息重复。"""
    names = list(factors)
    ranks = {n: factors[n].where(universe).rank(axis=1) for n in names}
    m = pd.DataFrame(np.eye(len(names)), index=names, columns=names)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            m.loc[a, b] = m.loc[b, a] = rowwise_corr(ranks[a], ranks[b]).mean()
    return m
