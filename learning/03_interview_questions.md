# 面试题（答案在代码哪里）

| # | 问题 | 答案位置 |
|---|---|---|
| 1 | 你的日线因子在什么时刻可以计算？用什么价格成交？ | `cryptodata/align.py` 模块 docstring；`research/labels.py` |
| 2 | 资金费结算时间和 K 线怎么对齐？为什么是左开右闭？ | `cryptodata/align.py::funding_bar_date`；`tests/test_data.py::test_funding_bar_date_rule` |
| 3 | 你怎么证明因子没有未来函数？ | `tests/test_factors.py::test_no_lookahead`、`test_point_in_time_truncation` |
| 4 | 怎么验证评估代码本身是对的？ | `tests/test_evaluation.py::test_perfect_factor_gets_extreme_ic`、`test_perfect_factor_lagged_one_day_is_useless` |
| 5 | IC 和 RankIC 有什么区别？加密货币为什么更看 RankIC？ | `research/evaluation.py::ic_series` docstring |
| 6 | 持有期大于 1 天时 IC 的 t 值为什么要调整？ | `research/evaluation.py::ic_summary` docstring |
| 7 | 什么是幸存者偏差？你在数据、股票池、标签、回测里分别怎么处理？ | [幸存者偏差](02_concepts/05_survivorship_bias.md)；`cryptodata/universe.py`；`research/labels.py`；`research/backtest.py::STALE_DAYS` |
| 8 | 数据缺了一天怎么办？为什么不直接 ffill 价格？ | `cryptodata/clean.py` 模块 docstring；`cryptodata/loader.py::compute_returns`；`tests/test_data.py::test_returns_bridge_missing_day` |
| 9 | 永续合约的资金费是什么？回测里怎么计入？多头和空头分别什么时候付钱？ | [永续合约与资金费机制](02_concepts/08_perpetual_funding.md)；`research/backtest.py` 模块 docstring；`tests/test_backtest.py::test_hand_calculated_long_short_with_funding` |
| 10 | 调仓频率怎么选？成本对高换手因子的影响有多大？ | `research/backtest.py::BacktestConfig`；报告第 5 节；`reports/generate.py::_cost_grid` |
| 11 | IC 加权合成时，为什么要先 `shift(h)` 再滚动？ | `research/combine.py::rolling_ic_weights`；`tests/test_combine.py::test_rolling_weights_use_only_lagged_ic` |
| 12 | 样本内和样本外表现差距从哪来？怎么减小？ | `docs/PROGRESS.md` "Phase 5 结果"；`research/oos.py` |
| 13 | 你试了很多参数/因子，怎么知道挑出来的不是运气？ | `research/overfit.py`；报告 6.2 节 |
| 14 | 为什么合成之前要做横截面标准化和截断？ | `research/combine.py::cs_zscore` |
| 15 | 为什么因子方向要用先验而不是用数据决定？ | `factors/base.py` 模块 docstring；`docs/DECISIONS.md` Phase 2 |
| 16 | 只有 5GB 内存时，如何处理几百个标的多年的数据？ | `cryptodata/store.py` 模块 docstring；`cryptodata/loader.py::_check_memory`、`load_klines_wide` |
| 17 | 多空组合为什么要美元中性？ | `research/backtest.py::long_short_weights`；`tests/test_backtest.py::test_long_short_weights_are_dollar_neutral` |
| 18 | 零成本回测和分组回测的结果应该是什么关系？ | `tests/test_backtest.py::test_zero_cost_backtest_matches_quantile_ls` |

**答题技巧**：先说结论，再说"为什么"（对应的偏差或风险），最后说"怎么验证"（指向测试）。面试官最看重第三部分。


---
[← 返回学习目录](README.md)
