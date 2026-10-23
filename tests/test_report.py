"""Phase 6：报告一键生成的冒烟测试（小数据集上跑通，检查产物与样本内/外标注）。"""

from reports.generate import run
from research.pipeline import ResearchConfig
from tests.conftest import SMALL_CFG


def test_report_generates(store_root, tmp_path):
    cfg = ResearchConfig(root=str(store_root), start=SMALL_CFG.start, end=SMALL_CFG.end, top_n=20,
                         min_history=30)
    path = run(cfg, tmp_path, window=180, refit=20)
    text = path.read_text(encoding="utf-8")
    for fig in ["fig_ic_timeseries.png", "fig_quantiles.png", "fig_factor_corr.png",
                "fig_composite_nav.png", "fig_cost_sensitivity.png"]:
        assert (tmp_path / fig).stat().st_size > 10_000
        assert fig in text
    # 每一条结论都要带样本内/样本外标签
    bullets = [l for l in text.splitlines() if l.startswith("- ") and "：" in l and "数据源" not in l
               and "标的总数" not in l and "股票池" not in l]
    assert bullets and all("【样本内】" in b or "【样本外】" in b for b in bullets)
