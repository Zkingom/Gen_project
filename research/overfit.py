"""过拟合演示：参数挖掘 / 因子挑选带来的"选择偏差"。

做法：准备大量候选因子——真实因子的各种回看窗口变体，外加一批**与收益完全无关的随机噪音因子**。
在训练集上按 RankIC 挑出最好的几个，再看它们在测试集上的表现。

预期现象：
- 噪音因子在训练集上也能"挑出"看似不错的 IC（纯属运气），到测试集上 IC 回到 0 附近；
- 即使是真实因子，挑出来的"最优窗口"在测试集上也普遍不如训练集——
  因为挑选这个动作本身就利用了训练集里的噪音。
这就是为什么样本内结果几乎总是好于样本外，以及为什么候选越多，越需要严格的样本外检验。
"""

import numpy as np
import pandas as pd
from scipy.signal import lfilter

from cryptodata.loader import Panel
from .evaluation import ic_series
from .labels import forward_returns


def _variants(panel: Panel) -> dict:
    """真实因子思路的不同窗口变体（方向已按先验调整，越大越好）。"""
    lr = np.log1p(panel["ret"].astype("float64"))
    fund = panel["funding"].astype("float64")
    out = {}
    for w in (1, 2, 3, 5, 7, 10, 15, 20):
        out[f"reversal_{w}d"] = -lr.rolling(w, min_periods=w).sum()
    for w in (10, 20, 40, 60, 90):
        out[f"momentum_{w}d"] = lr.rolling(w, min_periods=w).sum().shift(5)
    for w in (3, 7, 14, 30):
        out[f"funding_{w}d"] = -fund.rolling(w, min_periods=w).mean()
    for w in (10, 20, 60):
        out[f"lowvol_{w}d"] = -lr.rolling(w, min_periods=w).std()
    return out


def _noise(panel: Panel, n: int, seed: int = 0) -> dict:
    """持续性的随机因子：每个标的一条 AR(1) 序列，和收益没有任何关系（真实 IC = 0）。"""
    rng = np.random.default_rng(seed)
    shape = panel["close"].shape
    out = {}
    for k in range(n):
        # x_t = 0.9 * x_{t-1} + e_t，沿时间轴（axis=0）递推
        x = lfilter([1.0], [1.0, -0.9], rng.standard_normal(shape), axis=0)
        out[f"noise_{k:02d}"] = pd.DataFrame(x, index=panel.dates, columns=panel.symbols)
    return out


def selection_bias_experiment(panel: Panel, universe, split_date, n_noise: int = 40,
                              top_k: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    """返回 (全部候选的训练/测试 IC 表, 训练集 Top-K 的汇总)。"""
    split = pd.Timestamp(split_date)
    fwd = forward_returns(panel, 1)
    cands = {**_variants(panel), **_noise(panel, n_noise)}
    rows = {}
    for name, f in cands.items():
        ic = ic_series(f.where(panel["close"].notna()), fwd, universe, "rank")
        # [前视] 训练集只到 split 前 2 天，保证训练集标签在 split 之前已经实现
        rows[name] = {"train_ic": ic.loc[:split - pd.Timedelta(days=2)].mean(),
                      "test_ic": ic.loc[split:].mean(), "is_noise": name.startswith("noise")}
    table = pd.DataFrame(rows).T.astype({"train_ic": float, "test_ic": float, "is_noise": bool})
    table = table.sort_values("train_ic", ascending=False)
    summary = pd.DataFrame({
        "训练集Top-K平均IC(样本内)": [table.head(top_k)["train_ic"].mean(),
                                 table[table.is_noise].head(top_k)["train_ic"].mean()],
        "同一批在测试集的平均IC(样本外)": [table.head(top_k)["test_ic"].mean(),
                                   table[table.is_noise].head(top_k)["test_ic"].mean()],
    }, index=[f"全部候选中挑 Top-{top_k}", f"只在噪音因子中挑 Top-{top_k}"])
    return table, summary
