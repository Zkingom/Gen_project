"""把研究结果拼成 markdown 报告。结论文字根据数字自动生成，每条都带【样本内】/【样本外】标签。"""

import pandas as pd

IS, OOS = "【样本内】", "【样本外】"


def md_table(df: pd.DataFrame, fmt=None, index_name: str = "") -> str:
    """不依赖 tabulate 的简易 markdown 表格。fmt: {列名: 格式字符串} 或统一的格式字符串。"""
    def cell(col, v):
        f = fmt.get(col) if isinstance(fmt, dict) else fmt
        if f and isinstance(v, (int, float)) and not isinstance(v, bool) and pd.notna(v):
            return format(v, f)
        return str(v)
    idx_name = index_name or (df.index.name or "")
    lines = ["| " + " | ".join([idx_name] + [str(c) for c in df.columns]) + " |",
             "|" + "---|" * (len(df.columns) + 1)]
    for i, row in df.iterrows():
        label = " / ".join(map(str, i)) if isinstance(i, tuple) else str(i)
        lines.append("| " + " | ".join([label] + [cell(c, v) for c, v in row.items()]) + " |")
    return "\n".join(lines)


def _overview(o: dict) -> str:
    warn = ""
    if o["source"] != "binance":
        warn = ("\n> ⚠️ **本报告基于合成数据**（`cryptodata/synthetic.py`），数据里人为植入了反转、动量、"
                "资金费率三种弱信号。所有数字只用于验证研究流程是否正确，**不代表真实市场规律**。"
                "切换到真实数据见 `docs/PROGRESS.md`。\n")
    return f"""## 1. 数据概况
{warn}
- 数据源：`{o['source']}`；区间 {o['start']} ~ {o['end']}
- 标的总数 {o['n_symbols']}（其中 **{o['n_delisted']} 个在样本期内下架**，全部保留在研究样本中以避免幸存者偏差）
- 股票池：每天按过去 30 天平均成交额取前 {o['top_n']} 名（上市满 60 天），平均每天 {o['avg_universe']:.1f} 个标的
"""


def _single_factor_conclusions(s: pd.DataFrame) -> list[str]:
    out = []
    sig_pos = s.index[s["t"] > 2].tolist()
    sig_neg = s.index[s["t"] < -2].tolist()
    weak = s.index[s["t"].abs() <= 2].tolist()
    if sig_pos:
        out.append(f"{IS} 与先验方向一致且显著（t>2）的因子：{', '.join(sig_pos)}；"
                   f"其中 RankIC 最高的是 {s['RankIC'].idxmax()}（{s['RankIC'].max():.3f}）。")
    if sig_neg:
        out.append(f"{IS} 显著但方向与先验**相反**的因子：{', '.join(sig_neg)}——"
                   "要么先验错了，要么这段样本有特殊性，需要样本外确认后才能改方向。")
    if weak:
        out.append(f"{IS} 不显著（|t|≤2）的因子：{', '.join(weak)}，单独使用没有可靠的预测力。")
    fast = s["rank_autocorr"].idxmin()
    out.append(f"{IS} 换手最高的是 {fast}（排名自相关 {s.loc[fast, 'rank_autocorr']:.2f}），"
               "交易成本对它的侵蚀最大。")
    return out


def _single_factor(ctx) -> str:
    s, d = ctx["summary"], ctx["decay"]
    best = s["RankIC"].idxmax()
    half = d.loc[best][d.loc[best] < d.loc[best].iloc[0] / 2]
    decay_txt = (f"{IS} {best} 的 RankIC 在持有期 {half.index[0]} 天时降到 1 天的一半以下，"
                 "说明它的信息主要在这之前兑现。" if len(half) else
                 f"{IS} {best} 的 RankIC 在 20 天内没有衰减到一半以下。")
    concl = "\n".join(f"- {c}" for c in _single_factor_conclusions(s) + [decay_txt])
    fmt = {"IC": ".4f", "RankIC": ".4f", "ICIR": ".3f", "t": ".2f", "LS_ann": ".1%",
           "LS_sharpe": ".2f", "rank_autocorr": ".3f", "top_turnover": ".1%"}
    return f"""## 2. 单因子评估 {IS}

所有因子已按先验方向调整符号（值越大预期收益越高）。统计区间为全样本，属于样本内结果。
LS_ann / LS_sharpe 为 Q5−Q1 多空组合（不含成本）的年化收益和夏普。

{md_table(s, fmt, "因子")}

### IC 衰减（不同持有期的平均 RankIC）{IS}

{md_table(d, ".4f", "因子 \\ 持有期(天)")}

![IC 时序](fig_ic_timeseries.png)

![分组收益](fig_quantiles.png)

**结论**

{concl}
"""


def _correlation(ctx) -> str:
    c = ctx["corr"]
    pairs = [(a, b, c.loc[a, b]) for i, a in enumerate(c.index) for b in c.columns[i + 1:]
             if abs(c.loc[a, b]) > 0.4]
    txt = "；".join(f"{a} 与 {b}：{v:+.2f}" for a, b, v in pairs) or "没有 |相关| > 0.4 的因子对"
    return f"""## 3. 因子相关性 {IS}

![因子相关性](fig_factor_corr.png)

**结论**

- {IS} 相关性较高的因子对：{txt}。高相关的因子在合成时信息重复，等权会变相给这类信号更高权重。
"""


def _composite(ctx) -> str:
    t = ctx["wf_table"]
    is_row = [i for i in t.index if "样本内" in i][0]
    oos_row = [i for i in t.index if "样本外" in i][0]
    eq_row = t.index[0]
    fmt = {"RankIC": ".4f", "ICIR": ".3f", "t": ".2f", "ann_return": ".1%", "sharpe": ".2f",
           "max_dd": ".1%", "turnover": ".1%"}
    w = pd.DataFrame({"全样本权重【样本内】": ctx["wf_weights_full"],
                      "walk-forward 最新一期权重": ctx["wf_weights_last"]})
    gap = t.loc[is_row, "sharpe"] - t.loc[oos_row, "sharpe"]
    return f"""## 4. 因子合成：等权 vs IC 加权，样本内 vs 样本外

三种方法都在同一段样本外区间（{ctx['oos_start']} 起）评估；多空组合，每日调仓，
扣除 0.05% 手续费 + 0.05% 滑点和资金费。walk-forward 窗口 365 天、每 30 天重估一次。

{md_table(t, fmt, "合成方式")}

权重（平均 RankIC，正负号表示使用方向）：

{md_table(w, ".4f", "因子")}

![合成因子净值](fig_composite_nav.png)

**结论**

- {IS} 用全样本权重时，夏普 {t.loc[is_row, 'sharpe']:.2f}、RankIC {t.loc[is_row, 'RankIC']:.4f}。
- {OOS} 用 walk-forward 权重时，夏普 {t.loc[oos_row, 'sharpe']:.2f}、RankIC {t.loc[oos_row, 'RankIC']:.4f}，
  比样本内低 {gap:.2f} 个夏普单位——这就是"用未来数据估计权重"带来的虚高部分。
- {OOS} 等权合成（不估计任何参数）夏普 {t.loc[eq_row, 'sharpe']:.2f}。
"""


def _costs(ctx) -> str:
    g = ctx["cost_grid"]
    g_show = g.copy()
    g_show.index = [f"{c * 1e4:.0f} bp" for c in g.index]
    g_show.columns = [f"每 {c} 天调仓" for c in g.columns]
    at10 = g.loc[0.001]
    m = ctx["net_metrics"]
    neg = [f"{f} 天" for f in g.columns if (g[f] < 0).any()]
    top_cost = g.index.max() * 1e4
    neg_txt = (f"调仓频率为 {', '.join(neg)} 时，成本升到 {top_cost:.0f}bp 以内夏普即转负。" if neg
               else f"在 {top_cost:.0f}bp 以内的成本下各调仓频率夏普都为正（合成数据信号偏强，真实数据通常没这么乐观）。")
    return f"""## 5. 成本敏感性 {OOS}

对象：walk-forward IC 加权合成因子的多空组合（样本外区间）。

{md_table(g_show, ".2f", "单边成本")}

![成本敏感性](fig_cost_sensitivity.png)

**结论**

- {OOS} 默认设置（每日调仓、单边 10bp）：年化 {m['ann_return']:.1%}，夏普 {m['sharpe']:.2f}，
  最大回撤 {m['max_drawdown']:.1%}，日均换手 {m['turnover_daily']:.0%}；
  手续费年化 {m['fee_ann']:.1%}、滑点 {m['slippage_ann']:.1%}、资金费 {m['funding_ann']:+.1%}（负数表示净收入）。
- {OOS} 单边成本 10bp 时，夏普最高的调仓频率是每 {at10.idxmax()} 天（{at10.max():.2f}）。{neg_txt}
- {OOS} 单边成本 {top_cost:.0f}bp 时，最优调仓频率变为每 {g.iloc[-1].idxmax()} 天（夏普 {g.iloc[-1].max():.2f}）。
  成本越高，降低调仓频率越划算：少交易省下的成本超过了信号变"旧"损失的收益。
"""


def _split_and_selection(ctx) -> str:
    fmt = {"RankIC": ".4f", "ICIR": ".3f", "t": ".2f", "ann_return": ".1%", "sharpe": ".2f",
           "max_dd": ".1%", "turnover": ".1%"}
    s = ctx["sel_summary"]
    top = ctx["sel_table"].head(8)[["train_ic", "test_ic", "is_noise"]]
    return f"""## 6. 训练/测试切分与选择偏差

### 6.1 前半段训练、后半段测试（切分日 {ctx['split_date']}）

{md_table(ctx['split'], fmt, "信号 / 区间")}

### 6.2 选择偏差实验：在 26 个参数变体 + 40 个纯噪音因子中按训练集 IC 挑选

{md_table(s, ".4f", "")}

训练集 IC 最高的 8 个候选：

{md_table(top, {"train_ic": ".4f", "test_ic": ".4f"}, "候选")}

**结论**

- {IS}→{OOS} 只在噪音因子里挑出的 Top-5，训练集 IC {s.iloc[1, 0]:+.4f}，测试集 {s.iloc[1, 1]:+.4f}：
  噪音因子的"有效"完全来自运气，样本外消失。候选越多，样本内最优值被运气抬得越高。
- {OOS} 有真实机制的因子（反转等）在测试集上 IC 基本保持，这是区分"真信号"和"挖出来的噪音"的唯一可靠办法。
"""


def build_markdown(ctx: dict) -> str:
    parts = ["# 加密货币横截面因子研究报告\n",
             "标签说明：" + IS + " = 评估数据参与了因子挑选或参数估计，结果偏乐观；"
             + OOS + " = 评估区间的数据没有参与任何估计。\n",
             _overview(ctx["overview"]), _single_factor(ctx), _correlation(ctx),
             _composite(ctx), _costs(ctx), _split_and_selection(ctx)]
    return "\n".join(parts)
