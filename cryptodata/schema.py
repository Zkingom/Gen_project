"""表结构定义：原始数据（与 Binance 公开 CSV 完全一致）与清洗后的存储格式。

为什么单独放一个文件：真实数据下载器和合成数据生成器都必须产出**同一套列**，
清洗代码只认这里定义的列名。以后换数据源，只要能产出这些列，后面所有代码都不用改。
"""

# ---------------------------------------------------------------------------
# 原始格式：data.binance.vision 上 USDT 本位永续合约 (futures/um) 的 CSV 列
# ---------------------------------------------------------------------------

# K 线 CSV（例如 BTCUSDT-1d-2023-01.zip 解压后的文件）
# open_time/close_time 是毫秒时间戳（少数新文件可能是微秒，清洗时统一处理）
RAW_KLINE_COLUMNS = [
    "open_time",               # 这根 K 线开始时间
    "open", "high", "low", "close",
    "volume",                  # 成交量（以币计，base asset）
    "close_time",              # 这根 K 线结束时间（= 下一根 open_time - 1ms）
    "quote_volume",            # 成交额（以 USDT 计）——流动性筛选用它
    "count",                   # 成交笔数
    "taker_buy_volume",        # 主动买入成交量（吃单方为买方）
    "taker_buy_quote_volume",  # 主动买入成交额
    "ignore",                  # Binance 保留列，无意义
]

# 资金费率 CSV（例如 BTCUSDT-fundingRate-2023-01.zip）
RAW_FUNDING_COLUMNS = [
    "calc_time",               # 资金费结算时间（毫秒），实际值常带几毫秒抖动
    "funding_interval_hours",  # 结算间隔（通常 8 小时，部分合约改成 4 小时）
    "last_funding_rate",       # 该次结算的资金费率（正数：多头付给空头）
]

# ---------------------------------------------------------------------------
# 清洗后的存储格式（parquet，每个标的一个文件）
# ---------------------------------------------------------------------------

# 数值列一律 float32：日线价格 7 位有效数字足够，内存减半（主人本地只有 ~5GB）
KLINE_FLOAT_COLUMNS = [
    "open", "high", "low", "close", "volume", "quote_volume",
    "taker_buy_volume", "taker_buy_quote_volume",
]
KLINE_COLUMNS = ["open_time"] + KLINE_FLOAT_COLUMNS + ["trades"]

FUNDING_COLUMNS = [
    "funding_time",            # 结算时刻（UTC，已去掉毫秒抖动）
    "bar_date",                # 这次结算归属的日线日期，见 align.funding_bar_date
    "funding_rate",            # float32
    "funding_interval_hours",  # int8
]

# 标的元数据：用来记录上市/下架，避免幸存者偏差
SYMBOL_META_COLUMNS = ["symbol", "first_date", "last_date", "n_days", "status"]

STATUS_TRADING = "TRADING"
STATUS_DELISTED = "DELISTED"

# 日线一天的毫秒数
MS_PER_DAY = 86_400_000
