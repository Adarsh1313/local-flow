import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "localflow"))


def pytest_configure(config):
    config.addinivalue_line("markers", "windows: touches the real Windows desktop (opt-in: -m windows)")


def pytest_collection_modifyitems(config, items):
    if "windows" in (config.getoption("-m") or ""):
        return
    import pytest
    skip = pytest.mark.skip(reason="Windows integration test; run with -m windows")
    for item in items:
        if "windows" in item.keywords:
            item.add_marker(skip)
