# 加密货币横截面因子研究平台

Binance USDT 本位永续合约的横截面因子研究流程：数据 → 因子 → 评估 → 带成本回测 → 合成与样本外检验 → 报告。
学习路线见 [`docs/LEARNING_GUIDE.md`](docs/LEARNING_GUIDE.md)，示例报告见 [`reports/sample_synthetic/report.md`](reports/sample_synthetic/report.md)（合成数据）。

## 快速开始

```bash
pip install -r requirements.txt

# 1. 准备数据（二选一）
python -m cryptodata.build --source synthetic --root data   # 合成数据，约 15 秒，无需联网
python -m cryptodata.build --source binance   --root data   # 真实数据（data.binance.vision）

# 2. 一键生成研究报告
python -m reports.generate --root data --out reports/output

# 3. 跑测试
python -m pytest -q
```

## 目录

| 目录 | 内容 |
|---|---|
| `cryptodata/` | 数据层（可独立复用）：下载 / 合成、清洗、parquet 存储、面板读取、流动性股票池 |
| `factors/` | 因子库：8 个因子，统一接口 `f(panel) -> 日期×标的` |
| `research/` | 标签、IC 评估、分组回测、带成本回测、因子合成、walk-forward、过拟合实验 |
| `reports/` | 报告生成（markdown + matplotlib） |
| `tests/` | pytest：前视偏差、对齐、手算回测、完美因子等 |
| `docs/` | PROGRESS / DECISIONS / BLOCKERS / LEARNING_GUIDE |
