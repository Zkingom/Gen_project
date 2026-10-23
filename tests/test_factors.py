"""Phase 2 验收：每个因子都通过前视偏差测试。

核心思想：如果因子在日期 d 的值只依赖 d 及以前的数据，那么无论把 d 之后的数据改成什么，
d 之前（含 d 之前的所有日期）的因子值都必须**一模一样**。
"""

import numpy as np
import pandas as pd
import pytest

from factors import FACTORS, compute_factor

CUT_POS = 400  # 从第 400 天起篡改数据


def _tamper(panel, cut, how: str):
    """把 cut 及之后所有原始字段改成极端值（或全部删掉），返回新面板。"""
    rng = np.random.default_rng(0)
    new = {}
    for k, v in panel.fields.items():
        v = v.copy()
        future = v.index >= cut
        if how == "extreme":
            noise = rng.uniform(1e3, 1e5, size=v.loc[future].shape).astype("float32")
            v.loc[future] = (v.loc[future] * noise).astype("float32")
        else:  # "nan"：未来数据完全消失
            v.loc[future] = np.nan
        new[k] = v
    return panel.replace(**new)  # 新 Panel 会根据篡改后的 close 重新计算收益率


@pytest.mark.parametrize("name", sorted(FACTORS))
@pytest.mark.parametrize("how", ["extreme", "nan"])
def test_no_lookahead(panel, name, how):
    cut = panel.dates[CUT_POS]
    before = panel.dates < cut
    f0 = compute_factor(name, panel)
    f1 = compute_factor(name, _tamper(panel, cut, how))
    np.testing.assert_array_equal(f0.loc[before].values, f1.loc[before].values)
    # 反向检查：篡改确实生效了（否则上面的断言没有意义）
    assert not np.array_equal(f0.loc[~before].values, f1.loc[~before].values, equal_nan=True)


@pytest.mark.parametrize("name", sorted(FACTORS))
def test_point_in_time_truncation(panel, name):
    """另一种写法：只用截至 d 的数据计算出的 d 的因子值，应与用全样本计算的一致。"""
    d = panel.dates[CUT_POS]
    full = compute_factor(name, panel).loc[d]
    trunc = compute_factor(name, panel.slice(end=d)).loc[d]
    pd.testing.assert_series_equal(full, trunc)


@pytest.mark.parametrize("name", sorted(FACTORS))
def test_factor_shape_and_coverage(panel, name):
    f = compute_factor(name, panel)
    assert f.index.equals(panel.dates) and f.columns.equals(panel.symbols)
    assert f.dtypes.eq(np.float32).all()
    assert f.notna().values.mean() > 0.4          # 大部分有价格的位置都有值
    assert f.where(panel["close"].isna()).isna().all().all()  # 无价格处必为 NaN
    assert not np.isinf(f.values).any()


def test_registry_size_and_directions():
    assert 6 <= len(FACTORS) <= 8
    assert all(s.direction in (1, -1) and s.description for s in FACTORS.values())
