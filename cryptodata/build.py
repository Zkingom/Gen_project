"""一键构建本地数据仓库：下载（或合成）-> 清洗 -> 写入 parquet -> 生成元数据。

用法：
    python -m cryptodata.build --source synthetic --root data          # 无网络环境
    python -m cryptodata.build --source binance --root data            # 真实数据（全部 U 本位永续）
    python -m cryptodata.build --source binance --symbols BTCUSDT ETHUSDT
    python -m cryptodata.build --source auto                           # 能联网就用真实数据

每次只处理一个标的，处理完立刻落盘，内存占用与单个标的的数据量成正比。
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from . import download, store
from .clean import clean_funding, clean_klines
from .synthetic import SyntheticConfig, generate


def _iter_binance(symbols, cache_dir):
    syms = symbols or download.list_um_symbols()
    for sym in syms:
        kl = download.download_symbol(sym, cache_dir, "klines")
        fr = download.download_symbol(sym, cache_dir, "fundingRate")
        yield sym, kl, fr


def build_store(source_iter, root) -> pd.DataFrame:
    """消费 (symbol, raw_klines, raw_funding) 迭代器，清洗并写盘，返回清洗报告表。"""
    reports = []
    for sym, raw_kl, raw_fr in source_iter:
        kl, rk = clean_klines(raw_kl, sym)
        fr, rf = clean_funding(raw_fr, sym)
        if kl.empty:
            continue
        store.write_table(kl, root, store.KLINE_DIR, sym)
        store.write_table(fr, root, store.FUNDING_DIR, sym)
        reports.append({"symbol": sym, "kline_rows": rk.n_raw, "kline_dups": rk.n_duplicates,
                        "kline_invalid": rk.n_invalid, "kline_missing_days": rk.n_missing_days,
                        "funding_rows": rf.n_raw, "funding_dups": rf.n_duplicates,
                        "funding_invalid": rf.n_invalid})
    rep = pd.DataFrame(reports)
    data_end = max(store.read_table(root, store.KLINE_DIR, s, columns=["open_time"])
                   ["open_time"].max() for s in store.list_symbols(root))
    store.build_symbol_meta(root, data_end.tz_localize(None).normalize())
    rep.to_csv(Path(root) / "meta" / "clean_report.csv", index=False)
    return rep


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--source", choices=["synthetic", "binance", "auto"], default="auto")
    p.add_argument("--root", default="data")
    p.add_argument("--symbols", nargs="*", default=None)
    p.add_argument("--n-symbols", type=int, default=SyntheticConfig.n_symbols)
    args = p.parse_args(argv)

    source = args.source
    if source == "auto":
        source = "binance" if download.network_available() else "synthetic"
        print(f"[build] auto 模式选择数据源: {source}")
    if source == "binance":
        it = _iter_binance(args.symbols, Path(args.root) / "raw")
    else:
        it = generate(SyntheticConfig(n_symbols=args.n_symbols))
    rep = build_store(it, args.root)
    (Path(args.root) / "meta" / "source.json").write_text(json.dumps({"source": source}))
    print(f"[build] 完成：{len(rep)} 个标的写入 {args.root}")
    print(rep.drop(columns="symbol").sum().to_string())


if __name__ == "__main__":
    main()
