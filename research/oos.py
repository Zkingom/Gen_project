"""样本内 vs 样本外对比研究。

两个实验：
1. walk-forward：等权 / 全样本 IC 加权（样本内）/ 滚动 IC 加权（样本外），在同一段样本外区间比较。
2. 前后半段切分：前半段估计权重（训练集），分别在前半段（样本内）和后半段（样本外）评估。
"""

import pandas as pd

from cryptodata.loader import Panel
from .backtest import BacktestConfig, long_short_weights, run_backtest
from .combine import (combine, cs_zscore, daily_ic_table, equal_weights,
                      full_sample_ic_weights, oos_start, rolling_ic_weights)
from .evaluation import ic_series, ic_summary
from .labels import forward_returns


def evaluate_signal(signal, panel: Panel, universe, start=None, end=None,
                    bt_cfg: BacktestConfig = BacktestConfig()) -> dict:
    """在 [start, end] 区间评估一个信号：RankIC 统计 + 扣成本的多空回测。"""
    in_period = pd.Series(True, index=panel.dates).loc[start:end].reindex(panel.dates, fill_value=False)
    sig = signal.where(in_period, axis=0)
    ric = ic_series(sig, forward_returns(panel, 1), universe, "rank")
    w = long_short_weights(sig, universe)
    # 区间结束后清仓：最后一天之后的目标权重为 0
    bt = run_backtest(w, panel.slice(None, end) if end is not None else panel, bt_cfg)
    s = ic_summary(ric)
    return {"RankIC": s["ic_mean"], "ICIR": s["icir"], "t": s["t_stat"],
            "ann_return": bt.metrics["ann_return"], "sharpe": bt.metrics["sharpe"],
            "max_dd": bt.metrics["max_drawdown"], "turnover": bt.metrics["turnover_daily"],
            "_nav": bt.nav.loc[start:end]}


def walk_forward_study(signals: dict, panel: Panel, universe, window: int = 365,
                       refit_every: int = 30, bt_cfg: BacktestConfig = BacktestConfig()):
    """实验 1：三种合成方式在同一样本外区间的表现。返回 (结果表, 净值曲线, 权重)。"""
    zs = {n: cs_zscore(f, universe) for n, f in signals.items()}
    ic = daily_ic_table(signals, panel, universe)
    # 至少积累半个窗口的 IC 才开始估计权重
    w_wf = rolling_ic_weights(ic, window, h=1, refit_every=refit_every, min_periods=window // 2)
    start = oos_start(w_wf)
    variants = {
        "等权（无需估计）": combine(zs, equal_weights(signals)),
        "IC加权-全样本权重【样本内】": combine(zs, full_sample_ic_weights(ic)),
        "IC加权-walk-forward【样本外】": combine(zs, w_wf),
    }
    rows, navs = {}, {}
    for name, sig in variants.items():
        r = evaluate_signal(sig, panel, universe, start, None, bt_cfg)
        navs[name] = r.pop("_nav")
        rows[name] = r
    return pd.DataFrame(rows).T, pd.DataFrame(navs), {"walk_forward": w_wf,
                                                       "full_sample": full_sample_ic_weights(ic)}


def split_study(signals: dict, panel: Panel, universe, split_date,
                bt_cfg: BacktestConfig = BacktestConfig()) -> pd.DataFrame:
    """实验 2：训练集估计 → 分别在训练集（IS）与测试集（OOS）评估。

    比较对象：IC 加权合成、以及"按训练集 IC 挑出的最好单因子"。
    """
    split = pd.Timestamp(split_date)
    train_end = split - pd.Timedelta(days=2)  # [前视] 训练集标签（d→d+1）必须在 split 之前已实现
    zs = {n: cs_zscore(f, universe) for n, f in signals.items()}
    ic_train = daily_ic_table(signals, panel, universe).loc[:train_end]
    w = ic_train.mean()
    best = w.idxmax()
    cands = {"IC加权合成": combine(zs, w), f"训练集最优单因子({best})": signals[best]}
    rows = {}
    for name, sig in cands.items():
        for label, (a, b) in {"样本内(训练集)": (None, train_end), "样本外(测试集)": (split, None)}.items():
            r = evaluate_signal(sig, panel, universe, a, b, bt_cfg)
            r.pop("_nav")
            rows[(name, label)] = r
    return pd.DataFrame(rows).T
