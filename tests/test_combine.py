"""Phase 5 验收：合成与 walk-forward 只用过去数据；样本内权重确实"偷看"了未来。"""

import numpy as np
import pandas as pd
import pytest

from cryptodata.universe import liquidity_universe
from factors import FACTORS, compute_all
from research import combine as cb
from research.oos import split_study, walk_forward_study
from research.overfit import selection_bias_experiment
from tests.test_factors import _tamper

WINDOW, MINP, REFIT = 120, 60, 20


def _signals(panel):
    return {n: v * FACTORS[n].direction for n, v in compute_all(panel).items()}


def _universe(panel):
    return liquidity_universe(panel["quote_volume"], panel["close"], top_n=20, min_history=30)


def _wf_composite(panel):
    sig, univ = _signals(panel), _universe(panel)
    zs = {n: cb.cs_zscore(f, univ) for n, f in sig.items()}
    ic = cb.daily_ic_table(sig, panel, univ)
    w = cb.rolling_ic_weights(ic, WINDOW, 1, REFIT, MINP)
    return cb.combine(zs, w), cb.combine(zs, cb.full_sample_ic_weights(ic)), w


def test_rolling_weights_use_only_lagged_ic():
    rng = np.random.default_rng(0)
    ic = pd.DataFrame(rng.normal(0.02, 0.1, (300, 3)), columns=list("abc"),
                      index=pd.date_range("2022-01-01", periods=300))
    h, k = 3, 200
    w0 = cb.rolling_ic_weights(ic, 100, h, refit_every=1, min_periods=50)
    ic2 = ic.copy()
    ic2.iloc[k:] = 99.0  # 篡改第 k 天及以后的 IC
    w1 = cb.rolling_ic_weights(ic2, 100, h, refit_every=1, min_periods=50)
    # 第 t 天只能用 t-h 及以前的 IC，所以 t < k+h 的权重不变，t = k+h 开始变化
    pd.testing.assert_frame_equal(w0.iloc[:k + h], w1.iloc[:k + h])
    assert not w0.iloc[k + h].equals(w1.iloc[k + h])


def test_walk_forward_composite_has_no_lookahead(panel):
    cut = panel.dates[450]
    wf0, is0, w0 = _wf_composite(panel)
    wf1, is1, _ = _wf_composite(_tamper(panel, cut, "extreme"))
    before = panel.dates < cut
    assert w0.loc[before].notna().any().any()  # 确保比较区间里已经有估计出来的权重
    np.testing.assert_array_equal(wf0.loc[before].values, wf1.loc[before].values)
    # 对照：全样本（样本内）权重用到了未来，篡改未来后过去的合成值也变了
    assert not np.allclose(is0.loc[before].values, is1.loc[before].values, equal_nan=True)


def test_zscore_and_combine_basic(panel):
    univ = _universe(panel)
    f = _signals(panel)["reversal_5d"]
    z = cb.cs_zscore(f, univ, clip=10)
    ok = z.notna().sum(axis=1) > 10
    assert np.allclose(z[ok].mean(axis=1), 0, atol=1e-9)
    assert np.allclose(z[ok].std(axis=1), 1, atol=1e-9)
    same = cb.combine({"a": z, "b": z}, cb.equal_weights(["a", "b"]))
    pd.testing.assert_frame_equal(same, z, check_names=False)
    opp = cb.combine({"a": z, "b": -z}, pd.Series({"a": 1.0, "b": 1.0}))
    assert np.allclose(opp[ok].fillna(0), 0)


def test_oos_studies_run(panel):
    sig, univ = _signals(panel), _universe(panel)
    table, navs, weights = walk_forward_study(sig, panel, univ, WINDOW, REFIT)
    assert len(table) == 3 and navs.shape[1] == 3
    assert table["RankIC"].notna().all()
    split = split_study(sig, panel, univ, panel.dates[len(panel.dates) // 2])
    assert len(split) == 4


def test_selection_bias_noise_factors(panel):
    univ = _universe(panel)
    table, summary = selection_bias_experiment(panel, univ, panel.dates[400], n_noise=30)
    noise = table[table.is_noise]
    top = noise.head(5)
    assert top["train_ic"].mean() > 0                # 挑出来的噪音因子样本内"看起来有效"
    assert top["train_ic"].mean() > top["test_ic"].mean()  # 样本外衰减
    assert abs(noise["test_ic"].mean()) < 0.01       # 噪音整体在样本外没有预测力
