"""Phase 1 验收：缺失值处理、时间戳对齐、下架标的仍在历史数据中。"""

import io
import zipfile

import numpy as np
import pandas as pd
import pytest

from cryptodata import align, download, loader, store
from cryptodata.clean import clean_funding, clean_klines
from cryptodata.schema import RAW_FUNDING_COLUMNS, RAW_KLINE_COLUMNS, STATUS_DELISTED
from cryptodata.synthetic import SyntheticConfig, generate
from cryptodata.universe import liquidity_universe

DAY = 86_400_000
T0 = int(pd.Timestamp("2023-01-01", tz="UTC").value // 1_000_000)  # 毫秒


def _raw_klines(n=6, closes=None):
    closes = closes or [100.0 + i for i in range(n)]
    rows = []
    for i, c in enumerate(closes):
        rows.append([T0 + i * DAY, c, c + 1, c - 1, c, 10.0, T0 + (i + 1) * DAY - 1,
                     1000.0, 5, 5.0, 500.0, 0])
    return pd.DataFrame(rows, columns=RAW_KLINE_COLUMNS)


# ---------------------------- 缺失值处理 ----------------------------

def test_missing_day_is_nan_not_filled():
    raw = _raw_klines().drop(index=2)  # 删掉第 3 天
    kl, rep = clean_klines(raw, "X")
    assert rep.n_missing_days == 1
    assert len(kl) == 6
    assert kl.loc[2, ["open", "close", "quote_volume"]].isna().all()


def test_duplicates_and_invalid_rows():
    raw = _raw_klines()
    raw = pd.concat([raw, raw.iloc[[3]]])          # 重复一行
    raw.iloc[1, raw.columns.get_loc("high")] = 50  # high < close：逻辑错误
    kl, rep = clean_klines(raw, "X")
    assert rep.n_duplicates == 1 and rep.n_invalid == 1
    assert len(kl) == 6 and np.isnan(kl.loc[1, "close"])
    assert kl["close"].dtype == np.float32


def test_returns_bridge_missing_day():
    """缺口后第一天的收益应等于跨越缺口的总涨跌，不能凭空丢失。"""
    close = pd.DataFrame({"A": [100.0, 110.0, np.nan, 121.0, 133.1]},
                         index=pd.date_range("2023-01-01", periods=5))
    r = loader.compute_returns(close)
    assert np.isnan(r.iloc[0, 0]) and np.isnan(r.iloc[2, 0])
    assert r.iloc[3, 0] == pytest.approx(0.1, rel=1e-6)   # 121/110-1
    assert r.iloc[4, 0] == pytest.approx(0.1, rel=1e-6)
    # 复利总收益与价格一致
    assert (1 + r.fillna(0)).prod().iloc[0] == pytest.approx(133.1 / 100, rel=1e-5)


# ---------------------------- 时间戳对齐 ----------------------------

def test_epoch_units_ms_and_us():
    ms = align.epoch_to_utc([T0])
    us = align.epoch_to_utc([T0 * 1000])
    assert ms.iloc[0] == us.iloc[0] == pd.Timestamp("2023-01-01", tz="UTC")


def test_funding_bar_date_rule():
    """(d 00:00, d+1 00:00] 归属 d；毫秒抖动被去掉。"""
    times = pd.Series(pd.to_datetime([
        "2023-01-01 00:00:00.004", "2023-01-01 08:00:00.003",
        "2023-01-01 16:00:00", "2023-01-02 00:00:00.009"], utc=True, format="ISO8601"))
    bars = align.funding_bar_date(align.round_funding_time(times))
    assert list(bars.dt.strftime("%Y-%m-%d")) == ["2022-12-31", "2023-01-01",
                                                  "2023-01-01", "2023-01-01"]


def test_funding_daily_sum_aligned_with_kline(store_root):
    sym = store.list_symbols(store_root)[0]
    fr = store.read_table(store_root, store.FUNDING_DIR, sym)
    d = fr["bar_date"].iloc[10]
    expected = fr.loc[fr["bar_date"] == d, "funding_rate"].astype("float64").sum()
    daily = loader.load_funding_daily(store_root, [sym])["funding"][sym]
    assert daily.loc[d] == pytest.approx(expected, rel=1e-5)
    # 每次结算都落在它所属日线的 (开盘, 收盘] 之内
    open_ = fr["bar_date"].dt.tz_localize("UTC")
    assert ((fr["funding_time"] > open_) & (fr["funding_time"] <= open_ + pd.Timedelta("1D"))).all()


def test_funding_panel_index_matches_kline(panel):
    assert panel["funding"].index.equals(panel["close"].index)
    # 有价格的日子基本都有资金费记录
    has_px = panel["close"].notna()
    assert panel["funding"].notna()[has_px].mean().mean() > 0.99


# ---------------------------- 幸存者偏差 ----------------------------

def test_delisted_symbols_remain_in_history(store_root, panel):
    meta = store.read_symbol_meta(store_root)
    delisted = meta[meta["status"] == STATUS_DELISTED]
    assert len(delisted) > 0
    for _, row in delisted.iterrows():
        assert row["symbol"] in panel.symbols  # 默认读取包含已下架标的
        px = panel["close"][row["symbol"]]
        assert px.loc[: row["last_date"]].notna().sum() > 100
        assert px.loc[row["last_date"] + pd.Timedelta("1D"):].isna().all()


def test_universe_contains_delisted_before_delisting(store_root, panel):
    meta = store.read_symbol_meta(store_root)
    delisted = meta.loc[meta["status"] == STATUS_DELISTED, "symbol"]
    univ = liquidity_universe(panel["quote_volume"], panel["close"], top_n=15)
    assert univ[delisted].any().any()
    # 下架之后不可能在股票池里
    for s in delisted:
        last = meta.set_index("symbol").loc[s, "last_date"]
        assert not univ.loc[last + pd.Timedelta("1D"):, s].any()


def test_universe_has_no_lookahead(panel):
    cut = panel.dates[300]
    qv = panel["quote_volume"].copy()
    qv.loc[cut:] = 1e12  # 把未来成交额改成极端值
    u0 = liquidity_universe(panel["quote_volume"], panel["close"], top_n=15)
    u1 = liquidity_universe(qv, panel["close"], top_n=15)
    assert u0.loc[: cut - pd.Timedelta("1D")].equals(u1.loc[: cut - pd.Timedelta("1D")])


# ---------------------------- 格式与接口 ----------------------------

def test_synthetic_has_exact_binance_schema():
    sym, kl, fr = next(generate(SyntheticConfig(n_symbols=2, start="2023-01-01", end="2023-12-31")))
    assert list(kl.columns) == RAW_KLINE_COLUMNS
    assert list(fr.columns) == RAW_FUNDING_COLUMNS
    assert kl["open_time"].dtype == np.int64 and kl["open_time"].iloc[0] > 1e12


def _zip(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("x.csv", text)
    return buf.getvalue()


def test_parse_binance_csv_with_and_without_header():
    line = f"{T0},1,2,0.5,1.5,10,{T0 + DAY - 1},15,3,5,7,0\n"
    a = download.parse_kline_csv(_zip(line))
    b = download.parse_kline_csv(_zip(",".join(RAW_KLINE_COLUMNS) + "\n" + line))
    pd.testing.assert_frame_equal(a, b)
    f2 = download.parse_funding_csv(_zip(f"{T0},0.0001\n"))
    assert list(f2.columns) == RAW_FUNDING_COLUMNS and f2["funding_interval_hours"].isna().all()
    fr, _ = clean_funding(f2, "X")
    assert fr["funding_interval_hours"].iloc[0] == 8


def test_load_panel_slice_and_symbols(store_root):
    syms = store.list_symbols(store_root)[:3]
    p = loader.load_panel(store_root, "2022-01-01", "2022-01-31", symbols=syms)
    assert list(p.symbols) == syms and len(p.dates) == 31
    assert all(v.dtypes.eq(np.float32).all() for v in p.fields.values())


def test_memory_guard():
    with pytest.raises(MemoryError):
        loader._check_memory(n_days=100_000, n_syms=1000, n_fields=10)
