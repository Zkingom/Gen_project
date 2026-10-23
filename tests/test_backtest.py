"""Phase 4 验收：手工构造的小场景，盈亏可以逐笔手算核对（含资金费结算）。"""

import numpy as np
import pandas as pd
import pytest

from cryptodata.loader import Panel
from cryptodata.universe import liquidity_universe
from factors import compute_factor
from research.backtest import BacktestConfig, long_short_weights, run_backtest
from research.evaluation import quantile_returns
from research.labels import forward_returns

DATES = pd.date_range("2024-01-01", periods=4, name="date")


def _tiny_panel():
    close = pd.DataFrame({"A": [100.0, 110.0, 99.0, 99.0],
                          "B": [50.0, 52.5, 52.5, 52.5]}, index=DATES)
    # 日线 d1 内的资金费：A 三次结算各 +0.01% => +0.03%；B 为 -0.02%
    funding = pd.DataFrame({"A": [0.0, 0.0003, 0.0, 0.0],
                            "B": [0.0, -0.0002, 0.0, 0.0]}, index=DATES)
    return Panel({"close": close, "funding": funding})


def test_hand_calculated_long_short_with_funding():
    """
    第 0 天收盘：NAV=1，建仓 多 A 0.5、空 B 0.5。成交额 1.0，成本 1.0×(0.04%+0.01%)=0.0005
                 NAV = 0.9995
    第 1 天：    A 涨 10%，B 涨 5%
                 价格盈亏 = 0.5×10% − 0.5×5% = 0.025
                 资金费   = 0.5×0.03% + (−0.5)×(−0.02%) = 0.00015 + 0.0001 = 0.00025
                 （多头在正费率下付费；空头在负费率下也付费）
                 NAV = 0.9995 + 0.025 − 0.00025 = 1.02425
                 持仓漂移：A = 0.55，B = −0.525（rebalance_every=2，今天不调仓）
    第 2 天：    A 跌 10%，B 不动：盈亏 = 0.55×(−10%) = −0.055，NAV = 0.96925
                 调仓日，目标全部平仓：成交额 0.495 + 0.525 = 1.02，成本 0.00051
                 NAV = 0.96874
    第 3 天：    空仓，NAV 不变。
    """
    p = _tiny_panel()
    w = pd.DataFrame({"A": [0.5, 0.5, 0.0, 0.0], "B": [-0.5, -0.5, 0.0, 0.0]}, index=DATES)
    cfg = BacktestConfig(taker_fee=0.0004, slippage=0.0001, rebalance_every=2)
    res = run_backtest(w, p, cfg)
    d = res.daily
    assert d["nav"].tolist() == pytest.approx([0.9995, 1.02425, 0.96874, 0.96874], abs=1e-6)
    assert d["pnl"].tolist() == pytest.approx([0, 0.025, -0.055, 0], abs=1e-6)
    assert d["funding"].tolist() == pytest.approx([0, 0.00025, 0, 0], abs=1e-8)
    assert d["traded"].tolist() == pytest.approx([1.0, 0, 1.02, 0], abs=1e-6)
    assert (d["fee"] + d["slippage"]).tolist() == pytest.approx([0.0005, 0, 0.00051, 0], abs=1e-8)


def test_funding_switch_off_and_execution_lag():
    p = _tiny_panel()
    w = pd.DataFrame({"A": [0.5, 0.5, 0.0, 0.0], "B": [-0.5, -0.5, 0.0, 0.0]}, index=DATES)
    nofund = run_backtest(w, p, BacktestConfig(0, 0, include_funding=False))
    assert nofund.daily["funding"].sum() == 0
    # 推迟一天成交：第 0 天的信号在第 1 天收盘才建仓，第 1 天的涨跌拿不到
    lag = run_backtest(w, p, BacktestConfig(0, 0, execution_lag=1, include_funding=False))
    assert lag.daily["pnl"].iloc[1] == 0
    assert lag.daily["pnl"].iloc[2] == pytest.approx(0.5 * -0.10)


def test_delisted_position_is_force_closed():
    close = pd.DataFrame({"A": [10.0, 9.0, 8.0, np.nan, np.nan, np.nan, np.nan],
                          "B": [10.0] * 7}, index=pd.date_range("2024-01-01", periods=7))
    p = Panel({"close": close, "funding": close * 0})
    w = pd.DataFrame({"A": [1.0] * 7, "B": [0.0] * 7}, index=close.index)
    res = run_backtest(w, p, BacktestConfig(0.001, 0, rebalance_every=1))
    d = res.daily
    # A 停止报价后持仓被冻结，第 3 个无价格日（index 5）强制平仓并付成本
    assert d["gross"].iloc[4] > 0 and d["gross"].iloc[5] == 0
    assert d["traded"].iloc[5] == pytest.approx(d["gross"].iloc[4])


def test_long_short_weights_are_dollar_neutral(panel):
    univ = liquidity_universe(panel["quote_volume"], panel["close"], top_n=20, min_history=30)
    w = long_short_weights(compute_factor("reversal_5d", panel), univ)
    active = w.abs().sum(axis=1) > 0
    assert active.sum() > 300
    assert np.allclose(w[active].sum(axis=1), 0, atol=1e-9)
    assert np.allclose(w[active].abs().sum(axis=1), 1.0)
    assert not (w.ne(0) & ~univ).any().any()  # 只持有股票池内的标的


def test_zero_cost_backtest_matches_quantile_ls(panel):
    """零成本、不计资金费、每日调仓时，组合日收益 = 0.5 × 分组回测的多空收益（向后错一天）。
    这把 Phase 3 的分组回测和 Phase 4 的回测引擎互相印证。

    例外：持仓标的第二天恰好缺失价格时，回测里该仓位无法调整、被"卡住"到价格恢复，
    而分组回测假设每天都能完美调仓。这类日子（及其后两天）不做比较。"""
    univ = liquidity_universe(panel["quote_volume"], panel["close"], top_n=20, min_history=30)
    f = compute_factor("reversal_5d", panel)
    w = long_short_weights(f, univ)
    res = run_backtest(w, panel, BacktestConfig(0, 0, include_funding=False))
    port = res.nav.pct_change()
    ls = quantile_returns(f, forward_returns(panel, 1), univ)["LS"].shift(1)
    stuck = (w.shift(1).ne(0) & panel["close"].isna()).any(axis=1)
    clean = ~(stuck | stuck.shift(1, fill_value=False) | stuck.shift(2, fill_value=False))
    assert clean.mean() > 0.95
    both = pd.concat([port, 0.5 * ls], axis=1)[clean].dropna()
    both = both[both.iloc[:, 1] != 0]
    assert len(both) > 300
    np.testing.assert_allclose(both.iloc[:, 0], both.iloc[:, 1], atol=2e-6)


def test_metrics_on_known_nav():
    from research.backtest import performance_metrics
    idx = pd.date_range("2024-01-01", periods=4)
    daily = pd.DataFrame({"nav": [1.0, 1.1, 0.99, 1.089], "traded": [1.0, 0, 0, 0],
                          "fee": 0.0, "slippage": 0.0, "funding": 0.0,
                          "gross": [1.0, 1, 1, 1]}, index=idx)
    m = performance_metrics(daily)
    assert m["max_drawdown"] == pytest.approx(0.99 / 1.1 - 1)
    assert m["ann_return"] == pytest.approx(1.089 ** (365 / 3) - 1)
