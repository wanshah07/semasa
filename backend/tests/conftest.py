import pathlib

import pytest

FIX = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture():
    def _read(name: str) -> str:
        return (FIX / name).read_text(encoding="utf-8")
    return _read
