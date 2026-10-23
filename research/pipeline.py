"""把数据层、因子库、评估串起来的便捷函数（报告生成和交互式研究都用它）。"""

from dataclasses import dataclass

import pandas as pd

from cryptodata import liquidity_universe, load_panel
from factors import FACTORS, compute_all
from .evaluation import (factor_corr_matrix, ic_decay, ic_series, ic_summary,
                         quantile_returns, rank_autocorr, top_group_turnover)
from .labels import forward_returns


@dataclass
class ResearchConfig:
    root: str = "data"
    start: str | None = None
    end: str | None = None
    top_n: int = 50          # 股票池大小
    adv_lookback: int = 30   # 流动性筛选回看天数
    min_history: int = 60    # 上市满多少天才可入选
    n_groups: int = 5


def prepare(cfg: ResearchConfig):
    """读取面板、构建股票池、计算全部因子，并按先验方向调整符号（使"越大越好"）。"""
    panel = load_panel(cfg.root, cfg.start, cfg.end)
    universe = liquidity_universe(panel["quote_volume"], panel["close"], cfg.top_n,
                                  cfg.adv_lookback, cfg.min_history)
    raw = compute_all(panel)
    signed = {n: v * FACTORS[n].direction for n, v in raw.items()}
    return panel, universe, signed


def evaluate_factor(factor, panel, universe, n_groups: int = 5) -> dict:
    """单因子全套评估，返回一个字典（报告用）。"""
    fwd1 = forward_returns(panel, 1)
    ic = ic_series(factor, fwd1, universe, "pearson")
    ric = ic_series(factor, fwd1, universe, "rank")
    return {
        "ic": ic, "rank_ic": ric,
        "ic_stats": ic_summary(ic), "rank_ic_stats": ic_summary(ric),
        "decay": ic_decay(factor, panel, universe),
        "quantiles": quantile_returns(factor, fwd1, universe, n_groups),
        "rank_autocorr": rank_autocorr(factor, universe).mean(),
        "top_turnover": top_group_turnover(factor, universe, n_groups).mean(),
    }


def summary_table(results: dict) -> pd.DataFrame:
    """把多个因子的评估结果汇总成一张表。"""
    rows = {}
    for n, r in results.items():
        q = r["quantiles"]
        rows[n] = {"IC": r["ic_stats"]["ic_mean"], "RankIC": r["rank_ic_stats"]["ic_mean"],
                   "ICIR": r["rank_ic_stats"]["icir"], "t": r["rank_ic_stats"]["t_stat"],
                   "LS_ann": q["LS"].mean() * 365, "LS_sharpe": q["LS"].mean() / q["LS"].std() * 365 ** 0.5,
                   "rank_autocorr": r["rank_autocorr"], "top_turnover": r["top_turnover"]}
    return pd.DataFrame(rows).T


__all__ = ["ResearchConfig", "prepare", "evaluate_factor", "summary_table", "factor_corr_matrix"]
