# 推荐阅读顺序

| 顺序 | 文件 | 读完应该懂什么 |
|---|---|---|
| 1 | `cryptodata/schema.py` | 一根 K 线有哪些字段；资金费记录长什么样；为什么数值列用 float32 |
| 2 | `cryptodata/align.py` | **时点约定**："日期 d 的信息"指什么；资金费结算为什么归属 (d, d+1] 这一天。全项目最重要的 60 行 |
| 3 | `cryptodata/clean.py` | 数据清洗的三件事：去重、校验、补齐日历；为什么缺失值不填充 |
| 4 | `cryptodata/loader.py` | 面板（日期 × 标的宽表）是什么；`compute_returns` 如何处理缺失日 |
| 5 | `cryptodata/universe.py` | 股票池为什么要动态筛选；幸存者偏差是什么 |
| 6 | `cryptodata/synthetic.py` | 合成数据如何模拟市场；植入了哪些信号（这样你知道"正确答案"） |
| 7 | `cryptodata/download.py` / `build.py` | 真实数据从哪来；为什么用 S3 目录而不是交易所接口拿标的列表 |
| 8 | `factors/base.py` → `price.py` → `volume.py` → `funding.py` | 因子的统一接口；每个因子背后的经济直觉；先验方向 |
| 9 | `tests/test_factors.py` | **前视偏差测试**的两种写法 |
| 10 | `research/labels.py` | 未来收益标签；为什么这是唯一允许"看未来"的地方 |
| 11 | `research/evaluation.py` | IC、RankIC、ICIR、IC 衰减、分组回测、换手 |
| 12 | `tests/test_evaluation.py` | 用"完美因子"检验评估代码本身 |
| 13 | `research/backtest.py` + `tests/test_backtest.py` | 逐日记账；手续费、滑点、资金费怎么算；手算例子 |
| 14 | `research/combine.py` | 因子标准化与合成；walk-forward 里那个关键的 `shift(h)` |
| 15 | `research/oos.py` + `research/overfit.py` | 样本内 vs 样本外；选择偏差实验 |
| 16 | `reports/` | 报告如何自动生成、结论如何标注 |
| 17 | `docs/DECISIONS.md` | 每个设计选择的原因与备选方案——面试前重点复习 |

建议：每读一个文件，先读模块顶部的 docstring，再读带 `# [前视]` 标记的地方。
`grep -rn "\[前视\]" cryptodata factors research` 可以列出所有需要警惕未来数据的位置。


---
[← 返回学习目录](README.md)
