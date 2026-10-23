# 前视偏差（look-ahead bias / 未来函数）

在历史某个时点做决策时，用到了那个时点还不知道的信息。回测会因此好得离谱，实盘却赚不到钱。常见来源：

1. 因子用了 `shift(-1)` 之类取未来值的操作；
2. 用全样本统计量（如全样本均值、全样本 IC）做标准化或定权重；
3. 时间戳对齐错误：比如把 d+1 00:00 才公布的资金费当成 d 开盘时已知；
4. 估计权重时用了**标签还没实现**的 IC（`research/combine.py::rolling_ic_weights` 的 `shift(h)`）；
5. 用"最终是否下架"等事后信息筛选股票池。

本项目的防线：统一时点约定（`cryptodata/align.py`）+ 所有风险点标 `# [前视]` + **篡改未来数据的自动化测试**（`tests/test_factors.py`、`tests/test_combine.py`、`tests/test_data.py::test_universe_has_no_lookahead`）。


---
[← 返回学习目录](../README.md)
