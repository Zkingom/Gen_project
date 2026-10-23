# 自己动手的练习

由易到难：

1. **改参数看变化**：把 `research/pipeline.py::ResearchConfig.top_n` 从 50 改成 20 和 100，重新生成报告。股票池变小时 IC 的标准差怎么变？为什么？
2. **制造一个未来函数**：在 `factors/price.py::reversal_5d` 里把 `rolling(5)` 的结果加上 `.shift(-1)`，跑 `pytest tests/test_factors.py`，看测试如何抓住它。再看看报告里这个因子的 IC 变得多"好"。（做完记得改回来。）
3. **验证幸存者偏差**：在 `research/pipeline.py::prepare` 里只保留 `store.read_symbol_meta` 中 `status == "TRADING"` 的标的，重新跑评估。多空收益、尤其是做空端的收益怎么变？用[幸存者偏差](02_concepts/05_survivorship_bias.md)一节解释。
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


---
[← 返回学习目录](README.md)
