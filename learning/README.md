# 学习资料

写给：计算机背景、没有金融背景、准备量化研究 / 数据分析实习面试的读者。
目标：读完代码后，能在面试里把每个研究设计**讲清楚"为什么这样做"**。

## 先跑起来（10 分钟）

```bash
pip install -r requirements.txt
python -m cryptodata.build --source synthetic --root data   # 生成合成数据
python -m reports.generate --root data --out reports/output # 生成报告
python -m pytest -q                                         # 67 个测试
```

先打开 `reports/output/report.md` 看一眼最终产物，再回头读代码——知道终点在哪里，读起来更有方向。

---

## 学习路线

| 步骤 | 文件 | 内容 |
|---|---|---|
| 1 | [01_reading_order.md](01_reading_order.md) | 代码推荐阅读顺序，每个文件读完应该懂什么 |
| 2 | [02_concepts/](02_concepts/) | 8 个核心概念，每个一篇 |
| 3 | [03_interview_questions.md](03_interview_questions.md) | 18 道面试题，标注答案在代码哪里 |
| 4 | [04_exercises.md](04_exercises.md) | 自己动手的练习 |

### 核心概念

1. [收益率怎么算](02_concepts/01_returns.md)
2. [横截面 vs 时间序列](02_concepts/02_cross_section_vs_time_series.md)
3. [IC 的含义](02_concepts/03_ic.md)
4. [前视偏差（look-ahead bias / 未来函数）](02_concepts/04_lookahead_bias.md)
5. [幸存者偏差（survivorship bias）](02_concepts/05_survivorship_bias.md)
6. [过拟合（overfitting）](02_concepts/06_overfitting.md)
7. [交易成本](02_concepts/07_transaction_costs.md)
8. [永续合约与资金费机制](02_concepts/08_perpetual_funding.md)

### 相关文档（不在本目录）

- 设计决策与原因：[`docs/DECISIONS.md`](../docs/DECISIONS.md)——面试前重点复习
- 进度与样本内/外结果：[`docs/PROGRESS.md`](../docs/PROGRESS.md)
- 示例报告（合成数据）：[`reports/sample_synthetic/report.md`](../reports/sample_synthetic/report.md)
