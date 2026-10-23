# 进度

| 阶段 | 状态 | 说明 |
|---|---|---|
| Phase 1 数据层 | ✅ | `cryptodata/`：下载（Binance）/ 合成数据、清洗、parquet 存储、面板读取、流动性股票池 |
| Phase 2 因子库 | ✅ | `factors/`：8 个因子，统一接口 + 注册表；每个因子 2 种前视测试 + 截断测试 |
| Phase 3 因子评估 | ✅ | `research/labels.py`、`research/evaluation.py`、`research/pipeline.py`：IC/RankIC/ICIR/衰减/分组/换手/相关性；完美因子 RankIC=1、错位一天 IC≈0、随机因子 IC≈0 |
| Phase 4 带成本回测 | ✅ | `research/backtest.py`：手续费/滑点/资金费、调仓频率、执行延迟、下架强平；手算场景（含一次资金费结算）逐项核对；零成本回测与分组多空收益互相印证 |

## 数据源说明（重要）

本次云端运行环境**无法访问 Binance**（代理对 data.binance.vision 返回 403），
因此全部流程用 `cryptodata/synthetic.py` 生成的合成数据跑通。合成数据的原始表结构与
data.binance.vision 的 CSV **完全相同**，走同一条 清洗 → 存储 → 读取 流程。

### 回到本地后切换到真实数据

```bash
pip install -r requirements.txt
# 1) 先用少量标的试一下（下载缓存在 data/raw/，可断点续传）
python -m cryptodata.build --source binance --root data --symbols BTCUSDT ETHUSDT SOLUSDT
# 2) 全部 U 本位永续（含已下架，约 500+ 个，耗时较长）
python -m cryptodata.build --source binance --root data
```

之后所有下游命令（因子、评估、回测、报告）不需要任何改动，只要 `--root data` 指向这个目录。
注意：
- 月度文件通常在次月初发布，最近一个月的数据可能缺失；
- `download.py` 的 S3 列目录与 CHECKSUM 校验逻辑未能在线验证，第一次运行时请留意报错；
- 真实数据的结论才有研究意义；合成数据上的所有数字只说明"代码流程正确"。
