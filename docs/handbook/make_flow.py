"""生成流程图 flow_zh.svg / flow_en.svg（纯标准库，无需额外依赖）。"""
from pathlib import Path

STAGES = {
    "zh": [("数据", "cryptodata/", "时点对齐 · 下架币保留"),
           ("因子", "factors/", "篡改未来 · 截断重算"),
           ("评估", "research/evaluation", "完美 / 错位 / 随机对照"),
           ("带成本回测", "research/backtest", "手算核对 · 强平"),
           ("合成与样本外", "research/combine, oos", "shift(h) · 选择偏差"),
           ("报告", "reports/", "样本内 / 外标签")],
    "en": [("Data", "cryptodata/", "timing · delistings kept"),
           ("Factors", "factors/", "tamper · truncate"),
           ("Evaluation", "research/evaluation", "perfect / lagged / random"),
           ("Cost backtest", "research/backtest", "hand-checked P/L"),
           ("Combine + OOS", "research/combine, oos", "shift(h) · selection bias"),
           ("Report", "reports/", "IS / OOS labels")],
}
GUARD = {"zh": "每一步对应的偏差防护", "en": "Bias guard attached to each step"}
FONT = "Inter, 'WenQuanYi Zen Hei', 'PingFang SC', 'Microsoft YaHei', sans-serif"


def build(lang: str) -> str:
    w, h, bw, gap, x0 = 1000, 176, 150, 18, 5
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" font-family="{FONT}">',
           f'<rect width="{w}" height="{h}" fill="#ffffff"/>']
    for i, (title, mod, guard) in enumerate(STAGES[lang]):
        x = x0 + i * (bw + gap)
        out.append(f'<rect x="{x}" y="10" width="{bw}" height="66" rx="6" fill="#eaf2fc" stroke="#2a78d6" stroke-width="1.4"/>')
        out.append(f'<text x="{x + bw / 2}" y="38" text-anchor="middle" font-size="18" font-weight="600" fill="#0b0b0b">{title}</text>')
        out.append(f'<text x="{x + bw / 2}" y="60" text-anchor="middle" font-size="11.5" fill="#52514e" font-family="JetBrains Mono, monospace">{mod}</text>')
        out.append(f'<line x1="{x + bw / 2}" y1="76" x2="{x + bw / 2}" y2="102" stroke="#c3c2b7" stroke-dasharray="3 3"/>')
        out.append(f'<rect x="{x}" y="102" width="{bw}" height="38" rx="6" fill="#fdf3e7" stroke="#eb6834" stroke-width="1"/>')
        out.append(f'<text x="{x + bw / 2}" y="126" text-anchor="middle" font-size="11.5" fill="#0b0b0b">{guard}</text>')
        if i < 5:
            ax = x + bw
            out.append(f'<path d="M{ax + 3} 41 H{ax + gap - 5}" stroke="#52514e" stroke-width="1.6"/>')
            out.append(f'<path d="M{ax + gap - 8} 36 L{ax + gap - 2} 41 L{ax + gap - 8} 46 Z" fill="#52514e"/>')
    out.append(f'<text x="{x0}" y="164" font-size="12" fill="#898781">{GUARD[lang]}</text>')
    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    here = Path(__file__).parent
    for lang in STAGES:
        (here / f"flow_{lang}.svg").write_text(build(lang), encoding="utf-8")
