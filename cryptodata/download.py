"""从 Binance 公开数据源 data.binance.vision 下载 USDT 本位永续合约数据。

数据源说明：
- data.binance.vision 是 Binance 官方的历史数据仓库（背后是 S3），不需要 API key。
- 路径规律：data/futures/um/monthly/klines/<SYM>/1d/<SYM>-1d-<YYYY-MM>.zip
           data/futures/um/monthly/fundingRate/<SYM>/<SYM>-fundingRate-<YYYY-MM>.zip
- 每个 zip 旁边有 .CHECKSUM 文件（sha256），下载后校验完整性。
- **已下架合约的历史文件仍然保留在仓库里**——这正是我们避免幸存者偏差所需要的：
  用 S3 列目录拿到"历史上出现过的全部合约"，而不是调用交易所"当前交易对"接口。

本模块只依赖标准库 urllib，不引入 requests，满足依赖约束。
"""

import hashlib
import io
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pandas as pd

from .schema import RAW_FUNDING_COLUMNS, RAW_KLINE_COLUMNS

BASE_URL = "https://data.binance.vision/"
LIST_URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
_S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


def _http_get(url: str, retries: int = 4, timeout: int = 60) -> bytes:
    """带指数退避重试的 GET；网络不稳定时很常见。"""
    for i in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read()
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2 ** i)
    raise RuntimeError("unreachable")


def _list_prefix(prefix: str) -> tuple[list[str], list[str]]:
    """列出 S3 某个前缀下的"子目录"和文件（自动翻页）。"""
    dirs, files, marker = [], [], ""
    while True:
        url = f"{LIST_URL}?delimiter=/&prefix={prefix}&marker={marker}"
        root = ET.fromstring(_http_get(url))
        dirs += [p.text for p in root.iter(f"{_S3_NS}Prefix")][1:]  # 第一个是 prefix 自身
        files += [k.text for k in root.iter(f"{_S3_NS}Key")]
        truncated = root.findtext(f"{_S3_NS}IsTruncated") == "true"
        if not truncated:
            return dirs, files
        marker = root.findtext(f"{_S3_NS}NextMarker") or (files or dirs)[-1]


def list_um_symbols(quote: str = "USDT") -> list[str]:
    """历史上所有 U 本位永续合约（含已下架），按计价币过滤。"""
    dirs, _ = _list_prefix("data/futures/um/monthly/klines/")
    syms = [d.rstrip("/").split("/")[-1] for d in dirs]
    # 交割合约形如 BTCUSDT_240329，带下划线，排除掉只留永续
    return sorted(s for s in syms if s.endswith(quote) and "_" not in s)


def _has_header(text: str) -> bool:
    """较新的文件第一行是列名，较老的没有；看第一个字符是不是数字即可。"""
    return not text.lstrip()[:1].isdigit()


def _read_zip_csv(blob: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        return z.read(z.namelist()[0]).decode()


def parse_kline_csv(blob: bytes) -> pd.DataFrame:
    """解析 K 线 zip（或已解压的 csv 字节），返回 RAW_KLINE_COLUMNS 格式。"""
    text = _read_zip_csv(blob) if blob[:2] == b"PK" else blob.decode()
    df = pd.read_csv(io.StringIO(text), header=0 if _has_header(text) else None)
    df.columns = RAW_KLINE_COLUMNS
    return df


def parse_funding_csv(blob: bytes) -> pd.DataFrame:
    """解析资金费 zip，返回 RAW_FUNDING_COLUMNS 格式。老文件可能缺少间隔列，补 NaN。"""
    text = _read_zip_csv(blob) if blob[:2] == b"PK" else blob.decode()
    df = pd.read_csv(io.StringIO(text), header=0 if _has_header(text) else None)
    if df.shape[1] == 2:  # 只有 calc_time, last_funding_rate
        df.columns = ["calc_time", "last_funding_rate"]
        df["funding_interval_hours"] = float("nan")
    else:
        df.columns = RAW_FUNDING_COLUMNS
    return df[RAW_FUNDING_COLUMNS]


def fetch_verified(key: str, cache_dir: Path) -> bytes:
    """下载一个 zip 并用 .CHECKSUM 校验；本地已有缓存则直接读取。"""
    path = Path(cache_dir) / key
    if path.exists():
        return path.read_bytes()
    blob = _http_get(BASE_URL + key)
    expected = _http_get(BASE_URL + key + ".CHECKSUM").decode().split()[0]
    if hashlib.sha256(blob).hexdigest() != expected:
        raise ValueError(f"checksum 不匹配: {key}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return blob


def download_symbol(symbol: str, cache_dir, kind: str = "klines") -> pd.DataFrame:
    """下载一个标的全部月度文件并拼接成原始格式。kind = 'klines' 或 'fundingRate'。"""
    prefix = (f"data/futures/um/monthly/klines/{symbol}/1d/" if kind == "klines"
              else f"data/futures/um/monthly/fundingRate/{symbol}/")
    _, files = _list_prefix(prefix)
    parse = parse_kline_csv if kind == "klines" else parse_funding_csv
    parts = [parse(fetch_verified(k, cache_dir)) for k in files if k.endswith(".zip")]
    cols = RAW_KLINE_COLUMNS if kind == "klines" else RAW_FUNDING_COLUMNS
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols)


def network_available(timeout: int = 10) -> bool:
    """探测能否访问 data.binance.vision。"""
    try:
        _http_get(f"{LIST_URL}?delimiter=/&prefix=data/futures/um/&max-keys=1",
                  retries=1, timeout=timeout)
        return True
    except Exception:
        return False
