"""Phase 3 验收：用"完美因子"检验评估代码本身是否正确。

完美因子 = 直接拿未来收益当因子。它当然是作弊的，但正因如此，
一套正确的评估代码必须给它极高的 IC 和单调的分组收益；如果给不出来，说明评估代码有 bug
（例如因子和收益错位了一天）。这是检验评估流程的标准做法。
"""

import inspect
import re

import numpy as np
import pandas as pd
import pytest
from scipy import stats

import factors
from cryptodata.universe import liquidity_universe
from factors import FACTORS
from research import evaluation as ev
from research.labels import forward_returns


@pytest.fixture(scope="module")
def universe(panel):
    return liquidity_universe(panel["quote_volume"], panel["close"], top_n=20, min_history=30)


def _perfect_factor(panel, h=1):
    """只在测试里定义，绝不注册进因子库。"""
    return forward_returns(panel, h)


def test_perfect_factor_gets_extreme_ic(panel, universe):
    fwd = forward_returns(panel, 1)
    perfect = _perfect_factor(panel)
    ric = ev.ic_series(perfect, fwd, universe, "rank").dropna()
    ic = ev.ic_series(perfect, fwd, universe, "pearson").dropna()
    assert len(ric) > 300
    assert ric.min() > 0.999            # 排名完全一致
    assert ic.mean() > 0.999
    q = ev.quantile_returns(perfect, fwd, universe).dropna()
    means = q[[1, 2, 3, 4, 5]].mean()
    assert means.is_monotonic_increasing  # 分组收益严格单调
    assert (q["LS"] > 0).all()


def test_perfect_factor_lagged_one_day_is_useless(panel, universe):
    """把完美因子错位一天（用昨天的未来收益 = 今天的已实现收益），IC 应该接近 0。
    这个测试能抓住"标签和因子错位"这一类最常见的 bug。"""
    fwd = forward_returns(panel, 1)
    lagged = _perfect_factor(panel).shift(1)
    ric = ev.ic_series(lagged, fwd, universe, "rank")
    assert abs(ric.mean()) < 0.1


def test_random_factor_has_zero_ic(panel, universe):
    rng = np.random.default_rng(0)
    noise = pd.DataFrame(rng.standard_normal(panel["close"].shape),
                         index=panel.dates, columns=panel.symbols)
    ric = ev.ic_series(noise, forward_returns(panel, 1), universe, "rank")
    s = ev.ic_summary(ric)
    assert abs(s["ic_mean"]) < 0.02 and abs(s["t_stat"]) < 3


def test_perfect_factor_not_in_library():
    assert not any("perfect" in n or "future" in n for n in FACTORS)
    # 因子库源码里不能调用未来收益标签
    for mod in (factors.price, factors.volume, factors.funding, factors.base):
        src = inspect.getsource(mod)
        assert "forward_returns" not in src
        assert not re.search(r"shift\(\s*-\s*\d", src)  # 没有负向 shift（取未来值）


def test_rowwise_corr_matches_scipy():
    rng = np.random.default_rng(1)
    x = pd.DataFrame(rng.standard_normal((5, 30)))
    y = x * 0.3 + pd.DataFrame(rng.standard_normal((5, 30)))
    x.iloc[0, :3] = np.nan
    ours = ev.rowwise_corr(x, y)
    for i in range(5):
        m = x.iloc[i].notna()
        assert ours.iloc[i] == pytest.approx(stats.pearsonr(x.iloc[i][m], y.iloc[i][m])[0])
    rank = ev.rowwise_corr(x.rank(axis=1), y.where(x.notna()).rank(axis=1))
    assert rank.iloc[2] == pytest.approx(stats.spearmanr(x.iloc[2], y.iloc[2])[0])


def test_forward_returns_alignment(panel):
    """d 行的 1 日标签 = d+1 的已实现收益；h 日标签 = 复利。"""
    fwd1, fwd3 = forward_returns(panel, 1), forward_returns(panel, 3)
    r = panel["ret"].astype("float64")
    s = panel.symbols[0]
    d = panel["close"][s].dropna().index[50]
    i = panel.dates.get_loc(d)
    assert fwd1.loc[d, s] == pytest.approx(r[s].iloc[i + 1], rel=1e-6)
    assert fwd3.loc[d, s] == pytest.approx((1 + r[s].iloc[i + 1:i + 4]).prod() - 1, rel=1e-5)
    assert fwd1.iloc[-1].isna().all()


def test_ic_decay_and_turnover_shapes(panel, universe):
    f = factors.compute_factor("reversal_5d", panel)
    dec = ev.ic_decay(f, panel, universe, horizons=(1, 5))
    assert list(dec.index) == [1, 5]
    ac = ev.rank_autocorr(f, universe).mean()
    to = ev.top_group_turnover(f, universe).mean()
    assert 0 < ac < 1 and 0 < to < 1
    # 5 日反转的排名比 20 日波动率变化快得多
    vol = factors.compute_factor("volatility_20d", panel)
    assert ev.rank_autocorr(vol, universe).mean() > ac


def test_factor_corr_matrix_symmetric(panel, universe):
    fs = {n: factors.compute_factor(n, panel) for n in ["reversal_5d", "momentum_30d", "volatility_20d"]}
    m = ev.factor_corr_matrix(fs, universe)
    assert np.allclose(m.values, m.values.T) and np.allclose(np.diag(m), 1)
