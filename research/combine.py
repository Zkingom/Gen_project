"""因子合成：等权、IC 加权，以及滚动窗口（walk-forward）权重估计。

为什么要合成：单个因子的 IC 通常只有 0.01~0.05，噪音很大；
多个相关性不高的因子加在一起，噪音部分互相抵消，信号部分叠加，ICIR 往往更高。

样本内 vs 样本外：
- 样本内（in-sample, IS）：用全部数据估计权重，再在同一段数据上评估。
  权重"见过"了要预测的收益，结果一定偏乐观——这就是过拟合。
- 样本外（out-of-sample, OOS）：权重只用评估日期之前的数据估计（walk-forward），
  模拟真实情况下"站在当时"能做出的决策。OOS 才是对未来表现的诚实估计。
"""

import numpy as np
import pandas as pd

from cryptodata.loader import Panel
from .evaluation import ic_series
from .labels import forward_returns


def cs_zscore(f: pd.DataFrame, universe: pd.DataFrame, clip: float = 3.0) -> pd.DataFrame:
    """横截面标准化：每天在股票池内减均值、除标准差，并把极端值截断在 ±clip。

    不同因子量纲不同（收益率、相关系数、费率……），标准化后才能相加。
    截断防止单个异常值主导合成结果。只用同一天的数据，没有前视问题。
    """
    x = f.where(universe).astype("float64")
    z = x.sub(x.mean(axis=1), axis=0).div(x.std(axis=1), axis=0)
    return z.clip(-clip, clip)


def combine(zscores: dict, weights) -> pd.DataFrame:
    """按权重加总标准化因子。weights 可以是 Series（固定权重）或 DataFrame（日期×因子，时变权重）。

    某因子某天缺失时按 0（中性）处理；用 |权重| 之和归一化，使合成因子量纲稳定。
    """
    names = list(zscores)
    idx = next(iter(zscores.values())).index
    if isinstance(weights, pd.Series):
        weights = pd.DataFrame([weights[names].values] * len(idx), index=idx, columns=names)
    weights = weights.reindex(index=idx, columns=names)
    total = sum(zscores[n].fillna(0.0).mul(weights[n], axis=0) for n in names)
    norm = weights.abs().sum(axis=1).replace(0, np.nan)
    any_valid = sum(zscores[n].notna().astype(int) for n in names) > 0
    return total.div(norm, axis=0).where(any_valid)


def equal_weights(names) -> pd.Series:
    """等权：每个因子权重 1。因子方向已在 factors 注册表里按先验调整，不需要估计任何参数。"""
    return pd.Series(1.0, index=list(names))


def daily_ic_table(signals: dict, panel: Panel, universe: pd.DataFrame, h: int = 1) -> pd.DataFrame:
    """每个因子每天的 RankIC（日期 × 因子），是 IC 加权的原材料。"""
    fwd = forward_returns(panel, h)
    return pd.DataFrame({n: ic_series(f, fwd, universe, "rank") for n, f in signals.items()})


def full_sample_ic_weights(ic: pd.DataFrame) -> pd.Series:
    """【样本内】用全样本平均 IC 作为权重。

    # [前视] 有意使用全部日期的 IC（包括未来），只用来演示样本内结果为什么偏乐观，
    # 不能用于任何样本外结论。
    """
    return ic.mean()


def rolling_ic_weights(ic: pd.DataFrame, window: int = 365, h: int = 1,
                       refit_every: int = 30, min_periods: int = 180) -> pd.DataFrame:
    """【样本外】walk-forward IC 权重：每 refit_every 天用过去 window 天的平均 IC 重新估计一次。

    # [前视] 关键细节：日期 s 的 IC 需要 s 到 s+h 的收益，要到 s+h 收盘才知道。
    # 所以在日期 t 只能用 s <= t-h 的 IC：先 shift(h) 再 rolling。少了这一步就是隐蔽的未来函数。
    """
    est = ic.shift(h).rolling(window, min_periods=min_periods).mean()
    refit = np.arange(len(est)) % refit_every == 0
    # 非重估日沿用上一次的估计（ffill 只向过去取值）
    return est.where(pd.Series(refit, index=est.index), axis=0).ffill()


def oos_start(weights: pd.DataFrame) -> pd.Timestamp:
    """walk-forward 第一次有完整权重的日期，样本外评估从这里开始。"""
    return weights.dropna(how="all").index[0]
