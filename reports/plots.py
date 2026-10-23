"""报告用的 matplotlib 图。

图中文字用英文：主人本地不一定装了中文字体，中文标签在缺字体时会显示成方框；
报告正文（markdown）用中文解释每张图。

配色规则：
- 不同实体（合成方式等）用固定顺序的分类色，颜色跟随实体而不是排名；
- 有序分组（Q1..Q5）用单一色相由浅到深；
- 相关系数矩阵用蓝-红发散色，0 为中性灰；
- 不使用双纵轴。
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
ORDINAL_BLUE = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]  # Q1(浅) -> Q5(深)
DIVERGING = LinearSegmentedColormap.from_list("div", ["#2a78d6", "#f0efec", "#e34948"])
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.titlecolor": INK,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
    "font.size": 9, "axes.titlesize": 10, "lines.linewidth": 1.6,
    "legend.frameon": False, "figure.dpi": 110,
})


def _grid(n: int, ncols: int = 4, w: float = 3.4, h: float = 2.4):
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(w * ncols, h * nrows), sharex=True)
    axes = np.atleast_1d(axes).ravel()
    for ax in axes[n:]:
        ax.set_visible(False)
    return fig, axes


def ic_timeseries(rank_ics: dict, path, window: int = 90):
    """各因子 RankIC 的滚动均值（小多图，一个因子一格）。"""
    fig, axes = _grid(len(rank_ics))
    for ax, (name, ic) in zip(axes, rank_ics.items()):
        roll = ic.rolling(window, min_periods=window // 2).mean()
        ax.axhline(0, color=AXIS, linewidth=1)
        ax.plot(roll.index, roll.values, color=CATEGORICAL[0])
        ax.set_title(f"{name}  (mean {ic.mean():+.3f})", loc="left")
    fig.suptitle(f"Rank IC, {window}-day rolling mean", x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def quantile_cumulative(quantiles: dict, path):
    """各因子 5 个分组相对股票池平均的累计超额收益（对数坐标），组号越大颜色越深。

    减去 5 组平均：去掉全市场共同涨跌，只看因子把好币和差币分开了多少。
    """
    fig, axes = _grid(len(quantiles))
    for ax, (name, q) in zip(axes, quantiles.items()):
        groups = q[[1, 2, 3, 4, 5]]
        excess = groups.sub(groups.mean(axis=1), axis=0).fillna(0)
        for g, color in zip(range(1, 6), ORDINAL_BLUE):
            nav = (1 + excess[g]).cumprod()
            ax.plot(nav.index, nav.values, color=color, linewidth=1.2, label=f"Q{g}")
        ax.set_yscale("log")
        ax.set_title(name, loc="left")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", ncol=5, fontsize=8)
    fig.suptitle("Quintile portfolios: cumulative return relative to the universe average "
                 "(no costs, log scale; Q5 = highest signal)", x=0.01, ha="left", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(path)
    plt.close(fig)


def corr_heatmap(corr, path):
    """因子相关性矩阵：蓝 = 负相关，红 = 正相关，灰 = 0。"""
    n = len(corr)
    fig, ax = plt.subplots(figsize=(1.0 * n + 2, 0.8 * n + 1.2))
    ax.grid(False)
    im = ax.imshow(corr.values, cmap=DIVERGING, vmin=-1, vmax=1)
    ax.set_xticks(range(n), corr.columns, rotation=40, ha="right")
    ax.set_yticks(range(n), corr.index)
    for i in range(n):
        for j in range(n):
            v = corr.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8,
                    color="#ffffff" if abs(v) > 0.6 else INK)
    fig.colorbar(im, ax=ax, shrink=0.8)
    ax.set_title("Average cross-sectional rank correlation between factors", loc="left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def nav_curves(navs, path, title: str):
    """多条净值曲线（对数坐标），颜色按固定顺序分配给每种方法。"""
    fig, ax = plt.subplots(figsize=(9, 4.2))
    for (name, s), color in zip(navs.items(), CATEGORICAL):
        s = s.dropna()
        ax.plot(s.index, s / s.iloc[0], color=color, label=name)
    ax.set_yscale("log")
    ax.set_ylabel("NAV (start = 1, log scale)")
    ax.set_title(title, loc="left")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def cost_sensitivity(table, path):
    """横轴单边成本，纵轴夏普；每条线一个调仓频率。"""
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.axhline(0, color=AXIS, linewidth=1)
    for (freq, s), color in zip(table.items(), CATEGORICAL):
        ax.plot(s.index * 1e4, s.values, color=color, marker="o", markersize=5,
                label=f"rebalance every {freq}d")
    ax.set_xlabel("cost per side (bps, fee + slippage)")
    ax.set_ylabel("Sharpe ratio (net)")
    ax.set_title("Cost sensitivity of the walk-forward composite (out-of-sample)", loc="left")
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
