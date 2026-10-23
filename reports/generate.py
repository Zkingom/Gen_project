"""一键生成研究报告（markdown + 图）。

用法：
    python -m cryptodata.build --source synthetic --root data   # 先准备数据（只需一次）
    python -m reports.generate --root data --out reports/output

报告中每个结论都标注【样本内】或【样本外】：
- 【样本内】：用全样本数据评估（或用全样本估计参数后在同一段数据上评估），结果偏乐观；
- 【样本外】：评估区间的数据没有参与任何参数估计（walk-forward 或训练/测试切分）。
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from cryptodata import store
from research.backtest import BacktestConfig, long_short_weights, run_backtest
from research.combine import cs_zscore, daily_ic_table
from research.evaluation import factor_corr_matrix
from research.oos import split_study, walk_forward_composite, walk_forward_study
from research.overfit import selection_bias_experiment
from research.pipeline import ResearchConfig, evaluate_factor, prepare, summary_table
from . import plots
from .markdown import build_markdown


def _cost_grid(signal, panel, universe, freqs=(1, 3, 7), costs=(0, 5, 10, 20, 30, 50)):
    """合成因子在不同调仓频率 × 单边成本下的夏普（列 = 频率，行 = 成本）。"""
    w = long_short_weights(signal, universe)
    out = {}
    for f in freqs:
        out[f] = {c / 1e4: run_backtest(w, panel, BacktestConfig(c / 1e4, 0.0, f)).metrics["sharpe"]
                  for c in costs}
    return pd.DataFrame(out)


def _data_overview(cfg, panel, universe) -> dict:
    meta = store.read_symbol_meta(cfg.root)
    src_file = Path(cfg.root) / "meta" / "source.json"
    source = json.loads(src_file.read_text())["source"] if src_file.exists() else "unknown"
    return {"source": source, "start": panel.dates[0].date(), "end": panel.dates[-1].date(),
            "n_symbols": len(meta), "n_delisted": int((meta["status"] == "DELISTED").sum()),
            "avg_universe": float(universe.sum(axis=1)[universe.sum(axis=1) > 0].mean()),
            "top_n": cfg.top_n}


def run(cfg: ResearchConfig, out: Path, window: int = 365, refit: int = 30) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    panel, universe, signals = prepare(cfg)
    res = {n: evaluate_factor(f, panel, universe) for n, f in signals.items()}
    ctx = {"overview": _data_overview(cfg, panel, universe), "summary": summary_table(res),
           "decay": pd.DataFrame({n: r["decay"]["rank_ic"] for n, r in res.items()}).T,
           "corr": factor_corr_matrix(signals, universe)}
    ctx["wf_table"], navs, weights = walk_forward_study(signals, panel, universe, window, refit)
    zs = {n: cs_zscore(f, universe) for n, f in signals.items()}
    wf_signal, _, start = walk_forward_composite(zs, daily_ic_table(signals, panel, universe),
                                                 window, refit)
    ctx["oos_start"] = start.date()
    ctx["wf_weights_last"] = weights["walk_forward"].dropna().iloc[-1]
    ctx["wf_weights_full"] = weights["full_sample"]
    ctx["cost_grid"] = _cost_grid(wf_signal, panel, universe)
    ctx["net_metrics"] = run_backtest(long_short_weights(wf_signal, universe), panel).metrics
    split = panel.dates[len(panel.dates) // 2]
    ctx["split_date"] = split.date()
    ctx["split"] = split_study(signals, panel, universe, split)
    ctx["sel_table"], ctx["sel_summary"] = selection_bias_experiment(panel, universe, split)

    plots.ic_timeseries({n: r["rank_ic"] for n, r in res.items()}, out / "fig_ic_timeseries.png")
    plots.quantile_cumulative({n: r["quantiles"] for n, r in res.items()}, out / "fig_quantiles.png")
    plots.corr_heatmap(ctx["corr"], out / "fig_factor_corr.png")
    plots.nav_curves(_english_names(navs), out / "fig_composite_nav.png",
                     "Composite long-short NAV, net of fees, slippage and funding")
    plots.cost_sensitivity(ctx["cost_grid"], out / "fig_cost_sensitivity.png")
    path = out / "report.md"
    path.write_text(build_markdown(ctx), encoding="utf-8")
    return path


def _english_names(navs: pd.DataFrame) -> pd.DataFrame:
    names = ["Equal weight (no estimation)", "IC-weighted, full-sample weights [IN-SAMPLE]",
             "IC-weighted, walk-forward [OUT-OF-SAMPLE]"]
    return navs.set_axis(names, axis=1)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--root", default="data")
    p.add_argument("--out", default="reports/output")
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--top-n", type=int, default=50)
    p.add_argument("--window", type=int, default=365, help="walk-forward 估计窗口（天）")
    args = p.parse_args(argv)
    cfg = ResearchConfig(root=args.root, start=args.start, end=args.end, top_n=args.top_n)
    path = run(cfg, Path(args.out), args.window)
    print(f"[report] 已生成 {path}")


if __name__ == "__main__":
    main()
