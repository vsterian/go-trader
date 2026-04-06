"""Tests for Alpaca ExchangeAdapter."""

import os
import sys
import math
import importlib.util
from unittest.mock import MagicMock, patch, PropertyMock
from types import SimpleNamespace
from datetime import datetime, timezone

import pytest

# Load adapter via file path to avoid import conflicts
_ADAPTER_PATH = os.path.join(os.path.dirname(__file__), "adapter.py")
_spec = importlib.util.spec_from_file_location("alpaca_adapter", _ADAPTER_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
AlpacaExchangeAdapter = _mod.AlpacaExchangeAdapter


# ─────────────── Adapter Creation ───────────────


class TestAdapterCreation:
    def test_paper_mode_default(self):
        adapter = AlpacaExchangeAdapter(mode="paper")
        assert adapter.mode == "paper"
        assert adapter.is_live is False
        assert adapter.name == "alpaca"

    def test_live_mode(self):
        adapter = AlpacaExchangeAdapter(mode="live")
        assert adapter.mode == "live"
        assert adapter.is_live is True

    def test_no_keys_no_client(self):
        with patch.dict(os.environ, {}, clear=True):
            adapter = AlpacaExchangeAdapter()
            assert adapter._trading_client is None
            assert adapter._data_client is None


# ─────────────── Validate Order ───────────────


class TestValidateOrder:
    def _adapter_with_fraction(self, fractionable=False):
        adapter = AlpacaExchangeAdapter(mode="paper")
        adapter.is_fractionable = MagicMock(return_value=fractionable)
        return adapter

    def test_whole_shares_rounds_down(self):
        adapter = self._adapter_with_fraction(fractionable=False)
        size, err = adapter.validate_order("AAPL", 3.7, 150.0)
        assert err == ""
        assert size == 3

    def test_whole_shares_insufficient(self):
        adapter = self._adapter_with_fraction(fractionable=False)
        size, err = adapter.validate_order("AAPL", 0.5, 150.0)
        assert size == 0
        assert "at least 1 share" in err

    def test_fractional_shares(self):
        adapter = self._adapter_with_fraction(fractionable=True)
        size, err = adapter.validate_order("AAPL", 2.567, 150.0)
        assert err == ""
        assert size == 2.56

    def test_fractional_too_small(self):
        adapter = self._adapter_with_fraction(fractionable=True)
        size, err = adapter.validate_order("AAPL", 0.001, 150.0)
        assert size == 0
        assert "minimum fractional" in err

    def test_zero_size(self):
        adapter = self._adapter_with_fraction(fractionable=False)
        size, err = adapter.validate_order("AAPL", 0, 150.0)
        assert size == 0
        assert "positive" in err

    def test_zero_price(self):
        adapter = self._adapter_with_fraction(fractionable=False)
        size, err = adapter.validate_order("AAPL", 5, 0)
        assert size == 0
        assert "positive" in err

    def test_notional_below_minimum(self):
        adapter = self._adapter_with_fraction(fractionable=True)
        size, err = adapter.validate_order("AAPL", 0.01, 0.50)
        assert size == 0
        assert "$1.00" in err


# ─────────────── Market Data ───────────────


class TestMarketData:
    def test_get_spot_price_no_client(self):
        with patch.dict(os.environ, {}, clear=True):
            adapter = AlpacaExchangeAdapter()
            assert adapter.get_spot_price("AAPL") == 0.0

    def test_get_ohlcv_no_client(self):
        with patch.dict(os.environ, {}, clear=True):
            adapter = AlpacaExchangeAdapter()
            assert adapter.get_ohlcv("AAPL") == []


# ─────────────── Balance & Positions ───────────────


class TestAccountOperations:
    def test_get_balance_no_client(self):
        with patch.dict(os.environ, {}, clear=True):
            adapter = AlpacaExchangeAdapter()
            with pytest.raises(RuntimeError, match="requires API keys"):
                adapter.get_balance()

    def test_get_account_info_no_client(self):
        with patch.dict(os.environ, {}, clear=True):
            adapter = AlpacaExchangeAdapter()
            with pytest.raises(RuntimeError, match="requires API keys"):
                adapter.get_account_info()

    def test_get_positions_no_client(self):
        with patch.dict(os.environ, {}, clear=True):
            adapter = AlpacaExchangeAdapter()
            with pytest.raises(RuntimeError, match="requires API keys"):
                adapter.get_positions()


# ─────────────── Order Execution ───────────────


class TestOrderExecution:
    def test_market_buy_no_client(self):
        with patch.dict(os.environ, {}, clear=True):
            adapter = AlpacaExchangeAdapter()
            with pytest.raises(RuntimeError, match="requires API keys"):
                adapter.market_buy("AAPL", 1)

    def test_market_sell_no_client(self):
        with patch.dict(os.environ, {}, clear=True):
            adapter = AlpacaExchangeAdapter()
            with pytest.raises(RuntimeError, match="requires API keys"):
                adapter.market_sell("AAPL", 1)


# ─────────────── Market Hours ───────────────


class TestMarketHours:
    def test_is_market_open_no_client(self):
        with patch.dict(os.environ, {}, clear=True):
            adapter = AlpacaExchangeAdapter()
            assert adapter.is_market_open() is False


# ─────────────── Order Conversion ───────────────


class TestOrderConversion:
    def test_order_to_dict(self):
        mock_order = SimpleNamespace(
            id="abc123",
            symbol="AAPL",
            side="buy",
            type="market",
            status="filled",
            qty=10.0,
            filled_qty=10.0,
            filled_avg_price=150.50,
        )
        result = AlpacaExchangeAdapter._order_to_dict(mock_order)
        assert result["id"] == "abc123"
        assert result["symbol"] == "AAPL"
        assert result["filled_qty"] == 10.0
        assert result["filled_avg_price"] == 150.50

    def test_order_to_dict_no_fill(self):
        mock_order = SimpleNamespace(
            id="abc123",
            symbol="AAPL",
            side="buy",
            type="market",
            status="new",
            qty=10.0,
            filled_qty=None,
            filled_avg_price=None,
        )
        result = AlpacaExchangeAdapter._order_to_dict(mock_order)
        assert "filled_qty" not in result
        assert "filled_avg_price" not in result


# ─────────────── Timeframe Parsing ───────────────


class TestTimeframeParsing:
    @pytest.mark.parametrize("tf_str", [
        "1Min", "5Min", "15Min", "30Min", "1Hour", "4Hour", "1Day", "1Week",
    ])
    def test_valid_timeframes(self, tf_str):
        result = _mod._parse_timeframe(tf_str)
        assert result is not None

    def test_invalid_defaults_to_day(self):
        result = _mod._parse_timeframe("invalid")
        # TimeFrame objects loaded from different module contexts may not be ==
        # Compare string representation instead
        assert str(result) == "1Day"
