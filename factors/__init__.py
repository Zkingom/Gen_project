"""因子库。导入本包即完成全部因子的注册。

    from factors import FACTORS, compute_all
    values = compute_all(panel)   # {因子名: 日期×标的 DataFrame}
"""

from . import funding, price, volume  # noqa: F401  导入即注册
from .base import FACTORS, FactorSpec, compute_all, compute_factor

__all__ = ["FACTORS", "FactorSpec", "compute_all", "compute_factor"]
