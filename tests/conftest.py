"""pytest 公共夹具：用小规模合成数据建一个临时数据仓库，所有测试共享。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptodata.build import build_store  # noqa: E402
from cryptodata.loader import load_panel  # noqa: E402
from cryptodata.synthetic import SyntheticConfig, generate  # noqa: E402

SMALL_CFG = SyntheticConfig(n_symbols=30, start="2021-01-01", end="2022-12-31", seed=1,
                            frac_delist=0.3, min_life=120)


@pytest.fixture(scope="session")
def store_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("data")
    build_store(generate(SMALL_CFG), root)
    return root


@pytest.fixture(scope="session")
def panel(store_root):
    return load_panel(store_root, SMALL_CFG.start, SMALL_CFG.end)
