"""合成数据生成器：在不能联网时代替 Binance 数据，产出**与真实原始数据完全相同的表结构**。

为什么要合成数据而不是随便造几列：
- 输出列与 data.binance.vision 的 CSV 一模一样（schema.RAW_*_COLUMNS，毫秒时间戳），
  后续走和真实数据完全相同的 clean -> store -> loader 流程，切换数据源时下游代码零改动。
- 故意注入真实数据里会遇到的问题：缺失日、重复行、逻辑错误的 K 线、资金费时间戳抖动、
  结算间隔从 8h 改为 4h、合约中途上市和下架——这样清洗代码和测试都有东西可测。

数据生成过程（DGP，data generating process）概要：
    r_{i,t} = beta_i * m_t + alpha_{i,t} + sigma_i * h_{i,t} * eps_{i,t}
- m_t：市场共同收益（随机波动率，肥尾 t 分布）——加密货币里 BTC 带动全市场；
- alpha_{i,t}：**人为植入的弱可预测性**，只依赖 t-1 及之前的信息（DGP 本身没有未来函数）：
    短期反转（过去 5 天特异收益越高，次日越弱）、中期动量、资金费率越高次日越弱；
- 资金费率由一个"拥挤度"隐变量驱动，拥挤度随近期上涨而升高（多头拥挤 -> 多头付费）；
- 即将下架的币在下架前 90 天负漂移、成交额萎缩（模拟"死亡币"，用于展示幸存者偏差）。

重要提醒：在合成数据上得到的任何"因子有效"的结论都只说明**代码流程正确**，
不代表真实市场的规律。植入信号的强度见 SyntheticConfig。
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .align import date_to_open_ms
from .schema import MS_PER_DAY, RAW_FUNDING_COLUMNS, RAW_KLINE_COLUMNS

MS_PER_HOUR = 3_600_000


@dataclass
class SyntheticConfig:
    n_symbols: int = 150
    start: str = "2020-01-01"
    end: str = "2025-06-30"
    seed: int = 7
    frac_initial: float = 0.4      # 开始时就已上市的比例，其余在样本期内陆续上市
    frac_delist: float = 0.25      # 样本期内会下架的比例
    min_life: int = 150            # 最短存续天数
    k_reversal: float = 0.04       # 植入信号强度（单位：特异波动率的倍数）
    k_momentum: float = 0.025
    k_funding: float = 0.04
    dying_days: int = 90           # 下架前的"死亡期"天数
    missing_rate: float = 0.002    # 随机缺失 K 线的比例
    duplicate_rate: float = 0.002  # 随机重复行比例


def _lifetimes(cfg: SyntheticConfig, rng, n_days: int):
    """为每个标的抽取上市日下标 [list_idx, end_idx)。"""
    n = cfg.n_symbols
    list_idx = np.where(rng.random(n) < cfg.frac_initial, 0,
                        rng.integers(0, n_days - cfg.min_life, n))
    end_idx = np.full(n, n_days)
    delist = rng.random(n) < cfg.frac_delist
    span = n_days - list_idx - cfg.min_life
    end_idx[delist] = (list_idx + cfg.min_life + (rng.random(n) * span).astype(int))[delist]
    end_idx = np.minimum(end_idx, n_days)
    return list_idx, end_idx


def _market(rng, n_days: int) -> np.ndarray:
    """市场收益：对数波动率 AR(1) 的随机波动率模型 + t(4) 肥尾冲击。"""
    v = np.zeros(n_days)
    for t in range(1, n_days):
        v[t] = 0.98 * v[t - 1] + 0.08 * rng.standard_normal()
    sigma = 0.03 * np.exp(v)
    return 0.0005 + sigma * rng.standard_t(4, n_days) / np.sqrt(2.0), sigma


def _alpha(cfg, u_buf: np.ndarray, c: np.ndarray) -> np.ndarray:
    """植入的可预测部分（标准化单位）。u_buf[:, -1] 是最近一天的标准化特异冲击。"""
    s_rev = u_buf[:, -5:].sum(axis=1) / np.sqrt(5)
    s_mom = u_buf[:, -30:-5].sum(axis=1) / np.sqrt(25)
    return -cfg.k_reversal * s_rev + cfg.k_momentum * s_mom - cfg.k_funding * c / 1.5


def _simulate(cfg: SyntheticConfig, rng, alive: np.ndarray, dying: np.ndarray):
    """逐日模拟收益、资金费拥挤度、成交额。所有用到的状态都来自 t-1 及以前。"""
    n_days, n = alive.shape
    m, sig_m = _market(rng, n_days)
    beta = rng.uniform(0.7, 1.5, n)
    sigma = rng.uniform(0.025, 0.07, n)
    liq = rng.normal(np.log(3e7), 1.2, n)
    u_buf, c, logh = np.zeros((n, 30)), np.zeros(n), np.zeros(n)
    R, C, QV = (np.full((n_days, n), np.nan) for _ in range(3))
    for t in range(n_days):
        a = _alpha(cfg, u_buf, c) - 0.006 / sigma * dying[t]  # 死亡币负漂移
        logh = 0.95 * logh + 0.1 * rng.standard_normal(n)
        z = rng.standard_t(4, n) / np.sqrt(2.0)
        u = a + np.exp(logh) * z
        r = np.clip(beta * m[t] + sigma * u, -0.6, 1.5)
        c = 0.93 * c + 0.35 * np.clip(u, -3, 3) + 0.25 * m[t] / sig_m[t] \
            + 0.3 * rng.standard_normal(n)
        qv = np.exp(liq + 0.4 * rng.standard_normal(n) + np.log1p(8 * np.abs(r)))
        qv *= np.where(dying[t], 0.3, 1.0)
        u_buf = np.roll(u_buf, -1, axis=1)
        u_buf[:, -1] = np.where(alive[t], u, 0.0)
        R[t], C[t], QV[t] = (np.where(alive[t], x, np.nan) for x in (r, c, qv))
    return R, C, QV, sigma


def _klines_raw(dates, r, qv, sigma, rng) -> pd.DataFrame:
    """把一个标的的收益/成交额序列转成 Binance K 线 CSV 格式。"""
    n = len(r)
    close = np.exp(rng.uniform(np.log(0.01), np.log(500))) * np.cumprod(1 + r)
    prev = np.concatenate([[close[0] / (1 + r[0])], close[:-1]])
    open_ = prev * np.exp(rng.normal(0, 0.0005, n))
    wick = np.abs(rng.normal(0, sigma * 0.6, (2, n)))
    high = np.maximum(open_, close) * (1 + wick[0])
    low = np.minimum(open_, close) * np.clip(1 - wick[1], 0.05, None)
    buy_share = 0.5 + 0.1 * np.tanh(r / 0.05)
    open_ms = date_to_open_ms(dates)
    return pd.DataFrame({
        "open_time": open_ms, "open": open_, "high": high, "low": low, "close": close,
        "volume": qv / ((open_ + close) / 2), "close_time": open_ms + MS_PER_DAY - 1,
        "quote_volume": qv, "count": (qv / 1500).astype("int64"),
        "taker_buy_volume": qv * buy_share / ((open_ + close) / 2),
        "taker_buy_quote_volume": qv * buy_share, "ignore": 0,
    })[RAW_KLINE_COLUMNS]


def _funding_raw(dates, c, switch_idx, rng) -> pd.DataFrame:
    """生成资金费结算记录。日线 d 的结算时刻在 (d 00:00, d+1 00:00]。

    费率 = 基准 0.01%（Binance 默认利率部分）+ 拥挤度溢价；结算间隔在 switch_idx 之后改为 4h。
    """
    rows = []
    open_ms = date_to_open_ms(dates)
    for k, (d0, ck) in enumerate(zip(open_ms, c)):
        hours = 4 if k >= switch_idx else 8
        per8h = 0.0001 + 0.00012 * ck
        for j in range(1, 24 // hours + 1):
            rate = np.clip(per8h * hours / 8 + rng.normal(0, 3e-5), -0.003, 0.003)
            jitter = int(rng.integers(0, 10))  # 真实数据的毫秒抖动
            rows.append((d0 + j * hours * MS_PER_HOUR + jitter, hours, rate))
    return pd.DataFrame(rows, columns=RAW_FUNDING_COLUMNS)


def _corrupt(df: pd.DataFrame, cfg: SyntheticConfig, rng, bad_row: bool) -> pd.DataFrame:
    """注入脏数据：随机删行（首尾除外）、重复行、一条 high<low 的错误 K 线。"""
    n = len(df)
    keep = rng.random(n) >= cfg.missing_rate
    keep[[0, -1]] = True
    out = df.loc[keep]
    dup = out.sample(frac=cfg.duplicate_rate, random_state=int(rng.integers(1 << 31)))
    out = pd.concat([out, dup]).sort_values(out.columns[0], kind="stable")
    if bad_row and len(out) > 10:
        i = out.index[len(out) // 2]
        out.loc[i, ["high", "low"]] = out.loc[i, ["low", "high"]].values
    return out.reset_index(drop=True)


def generate(cfg: SyntheticConfig = SyntheticConfig()):
    """生成器：逐个产出 (symbol, 原始K线, 原始资金费)，格式与 download.py 的输出相同。"""
    rng = np.random.default_rng(cfg.seed)
    dates = pd.date_range(cfg.start, cfg.end, freq="D")
    list_idx, end_idx = _lifetimes(cfg, rng, len(dates))
    t = np.arange(len(dates))[:, None]
    alive = (t >= list_idx) & (t < end_idx)
    delists = end_idx < len(dates)
    dying = alive & delists & (t >= end_idx - cfg.dying_days)
    R, C, QV, sigma = _simulate(cfg, rng, alive, dying)
    for i in range(cfg.n_symbols):
        sl = slice(list_idx[i], end_idx[i])
        sym = f"SYN{i:03d}USDT"
        kl = _klines_raw(dates[sl], R[sl, i], QV[sl, i], sigma[i], rng)
        switch = int(rng.integers(0, end_idx[i] - list_idx[i])) if rng.random() < 0.2 else 10**9
        fr = _funding_raw(dates[sl], C[sl, i], switch, rng)
        fr = pd.concat([fr, fr.sample(frac=cfg.duplicate_rate, random_state=i)])
        yield sym, _corrupt(kl, cfg, rng, bad_row=rng.random() < 0.3), fr.reset_index(drop=True)
