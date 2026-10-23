"""因子库的统一接口与注册表。

什么是"因子"：对每个日期 d、每个标的 i 给出一个数 f(d, i)，
希望它能**在横截面上**区分未来收益的高低——即同一天里，因子值高的币未来平均跑赢因子值低的币。

统一接口：
    factor_func(panel) -> DataFrame（行=日期，列=标的，float32）
约定 f(d, i) 只能用 d 收盘及以前的数据（见 cryptodata/align.py 的时点约定）。

direction：根据文献/经济直觉给出的**先验**方向（+1 表示因子值越大预期未来收益越高）。
它在看数据之前就定好，等权合成时用来统一方向；如果用样本数据来决定方向，就是一种过拟合。
"""

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from cryptodata.loader import Panel


@dataclass(frozen=True)
class FactorSpec:
    name: str
    func: Callable[[Panel], pd.DataFrame]
    direction: int          # 先验方向：+1 / -1
    category: str
    description: str


FACTORS: dict[str, FactorSpec] = {}


def register(name: str, direction: int, category: str):
    """装饰器：把因子函数登记到注册表，docstring 的第一行作为描述。"""
    def deco(func):
        doc = (func.__doc__ or "").strip().splitlines()
        FACTORS[name] = FactorSpec(name, func, direction, category, doc[0] if doc else "")
        return func
    return deco


def finalize(values: pd.DataFrame, panel: Panel) -> pd.DataFrame:
    """统一后处理：当天没有有效价格（未上市/已下架/缺失）的位置置 NaN，转 float32。"""
    return values.where(panel["close"].notna()).astype("float32")


def compute_factor(name: str, panel: Panel) -> pd.DataFrame:
    return finalize(FACTORS[name].func(panel), panel)


def compute_all(panel: Panel, names=None) -> dict[str, pd.DataFrame]:
    return {n: compute_factor(n, panel) for n in (names or FACTORS)}
