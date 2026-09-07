"""Pytest fixtures for the trading desk tests."""
import pytest

from tests.factories import make_hot_pair, make_pair
from trading_desk.config import DeskConfig
from trading_desk.models import Chain


@pytest.fixture
def config() -> DeskConfig:
    cfg = DeskConfig(journal_path=":memory:")
    cfg.chains = (Chain.SOLANA,)
    return cfg


@pytest.fixture
def pair():
    return make_pair()


@pytest.fixture
def hot_pair():
    return make_hot_pair()
