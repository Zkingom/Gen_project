"""标签：未来收益。这是整个项目里**唯一允许"看未来"的地方**，而且只用于评估，绝不能喂给因子。

时点约定：因子 f(d) 在 d 收盘时算出，假设在 d 收盘价成交建仓，
那么持有 h 天的收益 = 从 close_d 到 close_{d+h}，即 r_{d+1} ... r_{d+h} 的复利。
"""

import numpy as np
import pandas as pd

from cryptodata.loader import Panel


def forward_returns(panel: Panel, h: int = 1) -> pd.DataFrame:
    """日期 d 这一行 = 从 d 收盘持有到 d+h 收盘的收益。

    # [前视] 这里**有意**使用未来数据（shift(-h)），所以它只能作为评估标签，
    # 因子代码里禁止调用本函数（tests/test_evaluation.py 有检查）。

    已下架/缺失的日子收益按 0 处理（相当于在最后可得价格平仓），而不是让整段标签变 NaN：
    否则即将下架、正在暴跌的币会从评估样本里"消失"，又是一种幸存者偏差。
    只有 d 当天本身有有效价格（能建仓）才有标签。
    """
    logr = np.log1p(panel["ret"].astype("float64").fillna(0.0))
    fwd = np.expm1(logr.rolling(h).sum().shift(-h))
    fwd = fwd.where(panel["close"].notna())
    # 样本最后 h 天没有完整的未来窗口，必须是 NaN
    fwd.iloc[len(fwd) - h:] = np.nan
    return fwd
