"""cryptodata：Binance U 本位永续合约数据层（可独立复用）。

只依赖 numpy / pandas / pyarrow，不依赖本项目的因子或研究模块，
可以直接拷贝到其它项目（如资金费率论文）里使用：

    from cryptodata import load_panel, liquidity_universe
    panel = load_panel("data", "2022-01-01", "2024-12-31")
    univ = liquidity_universe(panel["quote_volume"], panel["close"], top_n=50)
"""

from .loader import Panel, compute_returns, load_panel
from .universe import liquidity_universe

__all__ = ["Panel", "compute_returns", "load_panel", "liquidity_universe"]
