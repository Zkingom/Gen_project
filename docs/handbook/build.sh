#!/usr/bin/env bash
# 把 handbook_zh.md / handbook_en.md 转成 PDF：pandoc (md -> html) + Chromium (html -> pdf)。
# 依赖：pandoc、node + playwright（含 Chromium）、python3、中文字体（文泉驿正黑）。
set -euo pipefail
cd "$(dirname "$0")"
TMP="$(mktemp -d)"
python3 make_flow.py
build() {  # $1 = 语言, $2 = 页脚文字
  pandoc "handbook_$1.md" -f markdown+pipe_tables+implicit_figures -t html5 --standalone \
    --embed-resources --resource-path=. --css=style.css -o "$TMP/handbook_$1.html"
  NODE_PATH="${NODE_PATH:-$(npm root -g)}" node render.js "$TMP/handbook_$1.html" "handbook_$1.pdf" "$2"
}
build zh "合成数据：验证流程能否找回植入信号，不代表真实市场表现"
build en "Synthetic data: checks that the pipeline recovers planted signals; not real-market performance"
rm -rf "$TMP"
