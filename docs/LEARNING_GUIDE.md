# 学习指南：从零读懂这个因子研究项目

写给：计算机背景、没有金融背景、准备量化研究 / 数据分析实习面试的读者。
目标：读完代码后，能在面试里把每个研究设计**讲清楚"为什么这样做"**。

---

## 0. 先跑起来（10 分钟）

```bash
pip install -r requirements.txt
python -m cryptodata.build --source synthetic --root data   # 生成合成数据
python -m reports.generate --root data --out reports/output # 生成报告
python -m pytest -q                                         # 67 个测试
```

先打开 `reports/output/report.md` 看一眼最终产物，再回头读代码——知道终点在哪里，读起来更有方向。

---

## 1. 推荐阅读顺序

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

## 2. 核心概念

### 2.1 收益率怎么算

- **简单收益** r = P_t / P_{t-1} − 1。组合收益 = 各资产简单收益按权重加权，所以组合回测用简单收益。
- **对数收益** log(1 + r)。好处是**可以跨时间相加**：5 天的对数收益之和 = 5 天的总对数收益。所以计算"过去 N 天累计涨幅"的因子用对数收益（`factors/price.py::_log_ret`）。
- **复利**：多日收益是连乘 ∏(1 + r) − 1，不是相加（`research/labels.py::forward_returns`）。
- **年化**：加密货币 7×24 交易，一年按 365 天算（股票通常按 252 个交易日）。

### 2.2 横截面 vs 时间序列

- **时间序列**问题：BTC 明天涨还是跌？——预测一个资产在时间上的走势。
- **横截面**问题：今天这 50 个币里，明天谁会**相对**跑赢？——同一时刻比较多个资产。

本项目做的是横截面研究。好处：全市场一起涨跌（"beta"）对排序没影响，多空组合（做多前 20%、做空后 20%）把市场涨跌对冲掉，只赚"选币能力"的钱（"alpha"）。代码里所有 `axis=1`（按行）的操作都是在做横截面运算。

### 2.3 IC 的含义

- **IC（Information Coefficient）**：某一天，因子值与未来收益在横截面上的相关系数。IC = 0.05 意味着因子排序和未来收益排序"有一点点像"。
- 单日 IC 噪音极大（经常一天 +0.3、一天 −0.2），所以看**均值**。真实世界里平均 IC 0.02~0.05 已经是不错的因子。
- **RankIC**：先把两者都换成排名再算相关（Spearman）。对极端值不敏感，加密货币收益肥尾严重，所以主要看 RankIC。
- **ICIR** = IC 均值 / IC 标准差：衡量因子是否**稳定地**有效。IC 均值高但忽正忽负的因子不可靠。
- **IC 衰减**：用 1、2、5、10、20 天的未来收益分别算 IC。衰减快（如短期反转）= 信号短命 = 要频繁调仓 = 成本高。
- 代码：`research/evaluation.py::ic_series`、`ic_summary`、`ic_decay`。

### 2.4 前视偏差（look-ahead bias / 未来函数）

在历史某个时点做决策时，用到了那个时点还不知道的信息。回测会因此好得离谱，实盘却赚不到钱。常见来源：

1. 因子用了 `shift(-1)` 之类取未来值的操作；
2. 用全样本统计量（如全样本均值、全样本 IC）做标准化或定权重；
3. 时间戳对齐错误：比如把 d+1 00:00 才公布的资金费当成 d 开盘时已知；
4. 估计权重时用了**标签还没实现**的 IC（`research/combine.py::rolling_ic_weights` 的 `shift(h)`）；
5. 用"最终是否下架"等事后信息筛选股票池。

本项目的防线：统一时点约定（`cryptodata/align.py`）+ 所有风险点标 `# [前视]` + **篡改未来数据的自动化测试**（`tests/test_factors.py`、`tests/test_combine.py`、`tests/test_data.py::test_universe_has_no_lookahead`）。

### 2.5 幸存者偏差（survivorship bias）

只研究"今天还活着"的币，等于事先剔除了所有后来崩盘下架的币。这些币下架前往往大跌，剔除它们会系统性高估收益。
本项目的处理：

- 标的列表来自 data.binance.vision 的目录（包含已下架合约），而不是交易所"当前交易对"（`cryptodata/download.py::list_um_symbols`）；
- 股票池每天动态筛选，下架前的币照样可以入选（`cryptodata/universe.py`）；
- 评估标签和回测都正确处理下架：下架后收益按 0（在最后价格平仓），而不是让它从样本里消失（`research/labels.py`、`research/backtest.py` 的 `STALE_DAYS`）；
- 合成数据专门模拟了下架前 90 天负漂移的"死亡币"。

### 2.6 过拟合（overfitting）

用同一份数据既"找规律"又"验证规律"，找到的往往是噪音。表现：样本内很好，样本外变差。

- **参数过拟合**：试了 20 种回看窗口，报告最好的那个；
- **选择偏差**：试了 100 个因子，只报告显著的 5 个（`research/overfit.py` 的实验：40 个纯噪音因子里挑出的 Top-5，训练集 IC 为正，测试集归零）；
- **防线**：walk-forward（权重只用过去估计）、训练/测试切分（中间留间隔防标签泄漏）、先验方向（不看数据就定方向）、记录一共试了多少候选。

### 2.7 交易成本

- **手续费**：Binance U 本位合约普通用户 taker 费率 0.05%（吃单），按成交额收取；
- **滑点**：实际成交价比参考价格差一点（买得更贵、卖得更便宜），流动性越差越大；
- **换手率**：每天交易额 / 账户净值。日换手 60% × 单边成本 0.1% × 365 天 ≈ 每年 22% 的成本拖累——这就是为什么高换手的因子（短期反转）"纸面收益"高但实盘难做；
- 代码：`research/backtest.py`；成本敏感性见报告第 5 节。

### 2.8 永续合约与资金费机制

- **永续合约**：没有到期日的期货。可以加杠杆、可以直接做空。
- 问题：没有到期日，合约价格靠什么和现货价格保持一致？答案是**资金费（funding rate）**。
- 每隔 8 小时（00:00 / 08:00 / 16:00 UTC，部分合约 4 小时）结算一次：
  - 合约价 > 现货价（多头更急切）→ 资金费率为正 → **多头付钱给空头**；
  - 合约价 < 现货价 → 费率为负 → 空头付钱给多头。
  - 支付金额 = 持仓名义价值 × 费率。只有**在结算时刻持仓**的人才付/收。
- 基准费率约 0.01% / 8 小时（年化约 11%），所以长期做多永续合约有持仓成本。
- 研究含义：资金费率高 = 多头拥挤 = 杠杆多头多，容易踩踏；同时做空高费率币还能收资金费。这就是资金费类因子（`factors/funding.py`）的逻辑。
- 回测里：`research/backtest.py` 每天用 `持仓 × 当天费率之和` 扣减/增加净值；`tests/test_backtest.py` 有手算例子（含一次资金费结算）。

---

## 3. 面试题（答案在代码哪里）

| # | 问题 | 答案位置 |
|---|---|---|
| 1 | 你的日线因子在什么时刻可以计算？用什么价格成交？ | `cryptodata/align.py` 模块 docstring；`research/labels.py` |
| 2 | 资金费结算时间和 K 线怎么对齐？为什么是左开右闭？ | `cryptodata/align.py::funding_bar_date`；`tests/test_data.py::test_funding_bar_date_rule` |
| 3 | 你怎么证明因子没有未来函数？ | `tests/test_factors.py::test_no_lookahead`、`test_point_in_time_truncation` |
| 4 | 怎么验证评估代码本身是对的？ | `tests/test_evaluation.py::test_perfect_factor_gets_extreme_ic`、`test_perfect_factor_lagged_one_day_is_useless` |
| 5 | IC 和 RankIC 有什么区别？加密货币为什么更看 RankIC？ | `research/evaluation.py::ic_series` docstring |
| 6 | 持有期大于 1 天时 IC 的 t 值为什么要调整？ | `research/evaluation.py::ic_summary` docstring |
| 7 | 什么是幸存者偏差？你在数据、股票池、标签、回测里分别怎么处理？ | 本文 2.5 节；`cryptodata/universe.py`；`research/labels.py`；`research/backtest.py::STALE_DAYS` |
| 8 | 数据缺了一天怎么办？为什么不直接 ffill 价格？ | `cryptodata/clean.py` 模块 docstring；`cryptodata/loader.py::compute_returns`；`tests/test_data.py::test_returns_bridge_missing_day` |
| 9 | 永续合约的资金费是什么？回测里怎么计入？多头和空头分别什么时候付钱？ | 本文 2.8 节；`research/backtest.py` 模块 docstring；`tests/test_backtest.py::test_hand_calculated_long_short_with_funding` |
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

## 4. 自己动手的练习

由易到难：

1. **改参数看变化**：把 `research/pipeline.py::ResearchConfig.top_n` 从 50 改成 20 和 100，重新生成报告。股票池变小时 IC 的标准差怎么变？为什么？
2. **制造一个未来函数**：在 `factors/price.py::reversal_5d` 里把 `rolling(5)` 的结果加上 `.shift(-1)`，跑 `pytest tests/test_factors.py`，看测试如何抓住它。再看看报告里这个因子的 IC 变得多"好"。（做完记得改回来。）
3. **验证幸存者偏差**：在 `research/pipeline.py::prepare` 里只保留 `store.read_symbol_meta` 中 `status == "TRADING"` 的标的，重新跑评估。多空收益、尤其是做空端的收益怎么变？用 2.5 节解释。
4. **设计一个新因子并完整走一遍**（最重要的练习）：
   - 想一个经济直觉，比如"主动买入占比"：`taker_buy_quote_volume / quote_volume` 的 5 日均值（买方主动成交多 → 短期情绪过热？）；
   - 在 `factors/volume.py` 里用 `@register(...)` 写出来，写清 docstring 和先验方向；
   - 跑 `pytest tests/test_factors.py`——前视测试会自动覆盖新因子；
   - 生成报告，看它的 RankIC、衰减、分组单调性、和其他因子的相关性；
   - 把它加入合成，比较 walk-forward 样本外夏普有没有提高；
   - 在 `docs/DECISIONS.md` 记录你的设计决定。
5. **改调仓规则**：在 `research/backtest.py` 里实现"只有目标权重变化超过阈值才交易"（缓冲带），比较换手和夏普。
6. **修改合成数据的"真相"**：把 `cryptodata/synthetic.py::SyntheticConfig.k_reversal` 设为 0，重新生成数据。反转因子的 IC 是否回到 0？这个练习帮你确认"评估流程能识别出不存在的信号"。
7. **让信号在样本中途消失**：修改 `_alpha`，让反转信号在 2023 年之后变为 0（模拟因子被套利掉）。再看样本内外的差距——这时 walk-forward 的价值就显现出来了。
8. **接入真实数据**：回到能访问 Binance 的网络，按 `docs/PROGRESS.md` 的步骤下载真实数据，重新生成报告，对比合成数据的结论。真实数据才是你在面试里可以讲的"研究发现"。
