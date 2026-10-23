# 幸存者偏差（survivorship bias）

只研究"今天还活着"的币，等于事先剔除了所有后来崩盘下架的币。这些币下架前往往大跌，剔除它们会系统性高估收益。
本项目的处理：

- 标的列表来自 data.binance.vision 的目录（包含已下架合约），而不是交易所"当前交易对"（`cryptodata/download.py::list_um_symbols`）；
- 股票池每天动态筛选，下架前的币照样可以入选（`cryptodata/universe.py`）；
- 评估标签和回测都正确处理下架：下架后收益按 0（在最后价格平仓），而不是让它从样本里消失（`research/labels.py`、`research/backtest.py` 的 `STALE_DAYS`）；
- 合成数据专门模拟了下架前 90 天负漂移的"死亡币"。


---
[← 返回学习目录](../README.md)
