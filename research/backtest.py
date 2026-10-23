"""带成本的组合回测：taker 手续费、滑点、永续合约资金费。

记账方式（逐日、按名义价值）：
    NAV            账户净值（USDT），初始为 1
    q_i            标的 i 的持仓名义价值，多头为正、空头为负（永续合约可以直接做空）

每天 t 的顺序：
    1. 持仓盈亏：     pnl_t     = Σ q_i * r_{i,t}           （r 为 t-1 收盘到 t 收盘的收益）
    2. 资金费：       funding_t = Σ q_i * F_{i,t}           （F 为日线 t 内各次结算费率之和）
                     多头 q>0 且 F>0 时为正，即付出；空头收到。NAV -= funding_t
    3. 持仓随价格漂移：q_i *= (1 + r_{i,t})
    4. 若 t 是调仓日：按目标权重 w 调到 q*_i = w_i * NAV，
                     交易成本 = Σ |q*_i - q_i| * (手续费率 + 滑点率)，NAV -= 成本

近似说明：资金费按"当天开始时的名义价值"计算（真实情况按每次结算时的标记价格），
日内价格变动带来的差异是二阶小量，换来的是可以手算核对的简单记账。

# [前视] 第 t 天的目标权重来自 weights.loc[t]，它只能由 t 收盘及以前的信息算出；
# 成交价是 t 收盘价，获得的是 t+1 及以后的收益。execution_lag 可以再推迟 L 天成交。
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from cryptodata.loader import Panel
from .evaluation import quantile_groups

STALE_DAYS = 3  # 持仓标的连续多少天无价格就强制平仓（视为下架结算）


@dataclass
class BacktestConfig:
    taker_fee: float = 0.0005     # Binance U 本位合约普通用户 taker 费率 0.05%
    slippage: float = 0.0005      # 滑点：成交价相对收盘价的不利偏移，按成交额比例
    rebalance_every: int = 1      # 每隔几天调仓一次
    execution_lag: int = 0        # 信号产生后再推迟几天成交
    include_funding: bool = True
    initial_nav: float = 1.0


@dataclass
class BacktestResult:
    nav: pd.Series
    daily: pd.DataFrame
    metrics: dict = field(default_factory=dict)


def long_short_weights(signal: pd.DataFrame, universe: pd.DataFrame, n_groups: int = 5,
                       gross: float = 1.0) -> pd.DataFrame:
    """多空组合目标权重：做多因子最高组、做空最低组，各组内等权；多头 +gross/2，空头 -gross/2。

    多空等额（美元中性）：市场整体涨跌对组合影响很小，收益主要来自因子的选币能力。
    """
    g = quantile_groups(signal, universe, n_groups)
    long, short = (g == n_groups), (g == 1)
    w_long = long.div(long.sum(axis=1).replace(0, np.nan), axis=0) * gross / 2
    w_short = short.div(short.sum(axis=1).replace(0, np.nan), axis=0) * gross / 2
    return (w_long - w_short).fillna(0.0)


def _prepare_inputs(weights, panel, cfg):
    """对齐成 numpy 数组。权重按 execution_lag 推迟，非调仓日标记为 NaN（不交易）。"""
    w = weights.reindex(index=panel.dates, columns=panel.symbols).fillna(0.0)
    # [前视] shift(L) 向后推迟：t 天执行的是 t-L 天产生的信号
    w = w.shift(cfg.execution_lag).fillna(0.0)
    is_rebal = (np.arange(len(w)) % cfg.rebalance_every) == 0
    R = panel["ret"].to_numpy("float64")
    F = panel["funding"].to_numpy("float64") if cfg.include_funding else np.zeros_like(R)
    tradable = panel["close"].notna().to_numpy()
    return w.to_numpy("float64"), is_rebal, np.nan_to_num(R), np.nan_to_num(F), tradable


def _rebalance(q, target_w, nav, tradable, stale):
    """调仓：可交易标的调到目标；无价格的标的无法交易，但连续 STALE_DAYS 天无价格则强制平仓。"""
    target = np.where(tradable, target_w * nav, q)
    target = np.where(stale >= STALE_DAYS, 0.0, target)
    traded = np.abs(target - q).sum()
    return target, traded


def run_backtest(weights: pd.DataFrame, panel: Panel, cfg: BacktestConfig = BacktestConfig()
                 ) -> BacktestResult:
    """逐日模拟。weights：日期×标的 目标权重（相对 NAV），正为多、负为空。"""
    W, is_rebal, R, F, tradable = _prepare_inputs(weights, panel, cfg)
    T, N = R.shape
    q, nav, stale = np.zeros(N), cfg.initial_nav, np.zeros(N)
    rows = []
    for t in range(T):
        pnl, fund = q @ R[t], q @ F[t]
        nav += pnl - fund
        q = q * (1.0 + R[t])
        stale = np.where(tradable[t], 0, stale + 1)
        traded = 0.0
        must_liquidate = ((stale >= STALE_DAYS) & (q != 0)).any()
        if is_rebal[t] or must_liquidate:
            # 非调仓日只处理强制平仓：目标权重取当前权重，其余仓位不动
            w_t = W[t] if is_rebal[t] else q / nav
            q, traded = _rebalance(q, w_t, nav, tradable[t], stale)
        fee, slip = traded * cfg.taker_fee, traded * cfg.slippage
        nav -= fee + slip
        rows.append((nav, pnl, fund, fee, slip, traded, np.abs(q).sum(), (q > 0).sum(), (q < 0).sum()))
    daily = pd.DataFrame(rows, index=panel.dates, columns=[
        "nav", "pnl", "funding", "fee", "slippage", "traded", "gross", "n_long", "n_short"])
    return BacktestResult(daily["nav"], daily, performance_metrics(daily))


def performance_metrics(daily: pd.DataFrame, periods: int = 365) -> dict:
    """年化收益、波动、夏普、最大回撤、换手、各项成本。加密货币全年无休，年化用 365 天。"""
    nav = daily["nav"]
    active = daily.index[daily["gross"].gt(0).to_numpy().argmax()]  # 从第一次建仓开始统计
    nav = nav.loc[active:]
    ret = nav.pct_change().dropna()
    n = len(ret)
    prev_nav = daily["nav"].shift(1).loc[active:]
    sharpe = ret.mean() / ret.std() * np.sqrt(periods) if ret.std() > 0 else np.nan
    dd = nav / nav.cummax() - 1
    return {
        "ann_return": (nav.iloc[-1] / nav.iloc[0]) ** (periods / max(n, 1)) - 1,
        "ann_vol": ret.std() * np.sqrt(periods),
        "sharpe": sharpe,
        "max_drawdown": dd.min(),
        "turnover_daily": (daily["traded"] / prev_nav).loc[active:].mean(),
        "fee_ann": (daily["fee"] / prev_nav).loc[active:].mean() * periods,
        "slippage_ann": (daily["slippage"] / prev_nav).loc[active:].mean() * periods,
        "funding_ann": (daily["funding"] / prev_nav).loc[active:].mean() * periods,
        "n_days": n,
    }


def cost_sensitivity(weights, panel, cost_levels=(0, 0.0002, 0.0005, 0.001, 0.002),
                     base: BacktestConfig = BacktestConfig()) -> pd.DataFrame:
    """成本敏感性：单边总成本（手续费+滑点）取不同水平时的绩效。滑点固定为 0，全部计入 taker_fee。"""
    rows = {}
    for c in cost_levels:
        cfg = BacktestConfig(c, 0.0, base.rebalance_every, base.execution_lag, base.include_funding)
        rows[c] = run_backtest(weights, panel, cfg).metrics
    return pd.DataFrame(rows).T.rename_axis("cost_per_side")
