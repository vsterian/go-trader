"""Tests for BinanceUS adapter live trading methods."""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Import adapter
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import importlib.util
spec = importlib.util.spec_from_file_location("binanceus_adapter",
    os.path.join(os.path.dirname(__file__), "adapter.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
BinanceUSExchangeAdapter = mod.BinanceUSExchangeAdapter


class TestRoundStepSize:
    def test_round_down(self):
        assert BinanceUSExchangeAdapter.round_step_size(0.123456, 0.001) == 0.123

    def test_exact_multiple(self):
        assert BinanceUSExchangeAdapter.round_step_size(0.005, 0.001) == 0.005

    def test_round_btc_lot(self):
        assert BinanceUSExchangeAdapter.round_step_size(0.00015678, 0.00001) == 0.00015

    def test_step_size_one(self):
        assert BinanceUSExchangeAdapter.round_step_size(3.7, 1.0) == 3.0

    def test_zero_step_size(self):
        assert BinanceUSExchangeAdapter.round_step_size(1.234, 0) == 1.234


class TestValidateOrder:
    def setup_method(self, method=None):
        with patch.dict(os.environ, {"BINANCE_API_KEY": "", "BINANCE_API_SECRET": ""}):
            with patch.object(mod, '_get_ccxt_exchange', return_value=MagicMock()):
                self.adapter = BinanceUSExchangeAdapter()
        # Mock market data
        self.adapter._markets_loaded = True
        self.adapter._exchange.markets = {
            "BTC/USDT": {
                "limits": {
                    "amount": {"min": 0.00001, "max": 9999.0},
                    "cost": {"min": 10.0},
                },
                "precision": {"amount": 5},
            },
            "ETH/USDT": {
                "limits": {
                    "amount": {"min": 0.0001, "max": 9999.0},
                    "cost": {"min": 10.0},
                },
                "precision": {"amount": 4},
            },
        }

    def test_valid_order(self):
        size, err = self.adapter.validate_order("BTC", 0.001, 67000.0)
        assert err == ""
        assert size > 0

    def test_below_min_notional_adjusts_up(self):
        # $5 worth of BTC at $67000 = 0.0000746 — below $10 min notional
        size, err = self.adapter.validate_order("BTC", 0.00005, 67000.0)
        assert err == ""
        # Should be adjusted up to at least $10 / $67000
        assert size * 67000.0 >= 10.0

    def test_step_size_rounding(self):
        # 0.123456 ETH should round to 0.1234 (step=0.0001)
        size, err = self.adapter.validate_order("ETH", 0.123456, 2000.0)
        assert err == ""
        assert size == 0.1234

    def test_small_order_rejected(self):
        # Order where max_qty prevents meeting min notional
        # BTC max_qty=9999 at $0.0001 → max notional $0.999 < $10
        self.adapter._exchange.markets["BTC/USDT"]["limits"]["amount"]["max"] = 0.0001
        size, err = self.adapter.validate_order("BTC", 0.00001, 67000.0)
        assert err != "" or size == 0

    def test_full_pair_symbol(self):
        # Should work with "BTC/USDT" too
        size, err = self.adapter.validate_order("BTC/USDT", 0.001, 67000.0)
        assert err == ""
        assert size > 0


class TestGetMinNotional:
    def setup_method(self, method=None):
        with patch.dict(os.environ, {"BINANCE_API_KEY": "", "BINANCE_API_SECRET": ""}):
            with patch.object(mod, '_get_ccxt_exchange', return_value=MagicMock()):
                self.adapter = BinanceUSExchangeAdapter()
        self.adapter._markets_loaded = True
        self.adapter._exchange.markets = {
            "BTC/USDT": {
                "limits": {"cost": {"min": 10.0}, "amount": {"min": 0.00001}},
                "precision": {"amount": 5},
            }
        }

    def test_returns_exchange_min(self):
        assert self.adapter.get_min_notional("BTC") == 10.0

    def test_floor_enforced(self):
        # Even if exchange says $5, we enforce $10 floor
        self.adapter._exchange.markets["BTC/USDT"]["limits"]["cost"]["min"] = 5.0
        assert self.adapter.get_min_notional("BTC") == 10.0

    def test_unknown_symbol_returns_floor(self):
        assert self.adapter.get_min_notional("UNKNOWN") == 10.0


class TestGetLotSize:
    def setup_method(self, method=None):
        with patch.dict(os.environ, {"BINANCE_API_KEY": "", "BINANCE_API_SECRET": ""}):
            with patch.object(mod, '_get_ccxt_exchange', return_value=MagicMock()):
                self.adapter = BinanceUSExchangeAdapter()
        self.adapter._markets_loaded = True
        self.adapter._exchange.markets = {
            "SOL/USDT": {
                "limits": {"amount": {"min": 0.01, "max": 100000.0}},
                "precision": {"amount": 2},
            }
        }

    def test_returns_lot_info(self):
        lot = self.adapter.get_lot_size("SOL")
        assert lot["min_qty"] == 0.01
        assert lot["max_qty"] == 100000.0
        assert lot["step_size"] == 0.01


class TestLiveMode:
    @patch.dict(os.environ, {"BINANCE_API_KEY": "test_key", "BINANCE_API_SECRET": "test_secret"})
    def test_live_mode_detected(self):
        with patch.object(mod, '_get_ccxt_exchange', return_value=MagicMock()) as mock:
            adapter = BinanceUSExchangeAdapter()
            assert adapter.is_live is True
            assert adapter.mode == "live"

    @patch.dict(os.environ, {"BINANCE_API_KEY": "", "BINANCE_API_SECRET": ""})
    def test_paper_mode_detected(self):
        with patch.object(mod, '_get_ccxt_exchange', return_value=MagicMock()):
            adapter = BinanceUSExchangeAdapter()
            assert adapter.is_live is False
            assert adapter.mode == "paper"


class TestMarketOrders:
    def setup_method(self, method=None):
        self.mock_exchange = MagicMock()
        self.mock_exchange.markets = {"BTC/USDT": {"id": "BTCUSDT"}}
        with patch.dict(os.environ, {"BINANCE_API_KEY": "test_key", "BINANCE_API_SECRET": "test_secret"}):
            with patch.object(mod, '_get_ccxt_exchange', return_value=self.mock_exchange):
                self.adapter = BinanceUSExchangeAdapter()
        self.adapter._markets_loaded = True

    def test_market_buy(self):
        self.mock_exchange.create_market_buy_order.return_value = {
            "id": "123", "average": 67000.0, "filled": 0.001, "status": "closed"
        }
        result = self.adapter.market_buy("BTC", 0.001)
        self.mock_exchange.create_market_buy_order.assert_called_once_with("BTC/USDT", 0.001)
        assert result["average"] == 67000.0

    def test_market_sell(self):
        self.mock_exchange.create_market_sell_order.return_value = {
            "id": "456", "average": 67100.0, "filled": 0.001, "status": "closed"
        }
        result = self.adapter.market_sell("BTC", 0.001)
        self.mock_exchange.create_market_sell_order.assert_called_once_with("BTC/USDT", 0.001)
        assert result["average"] == 67100.0

    def test_market_buy_full_pair(self):
        self.mock_exchange.create_market_buy_order.return_value = {"id": "789"}
        self.adapter.market_buy("BTC/USDT", 0.01)
        self.mock_exchange.create_market_buy_order.assert_called_once_with("BTC/USDT", 0.01)

    @patch.dict(os.environ, {"BINANCE_API_KEY": "", "BINANCE_API_SECRET": ""})
    def test_buy_raises_in_paper_mode(self):
        with patch.object(mod, '_get_ccxt_exchange', return_value=MagicMock()):
            adapter = BinanceUSExchangeAdapter()
        with pytest.raises(RuntimeError, match="live mode"):
            adapter.market_buy("BTC", 0.001)

    @patch.dict(os.environ, {"BINANCE_API_KEY": "", "BINANCE_API_SECRET": ""})
    def test_sell_raises_in_paper_mode(self):
        with patch.object(mod, '_get_ccxt_exchange', return_value=MagicMock()):
            adapter = BinanceUSExchangeAdapter()
        with pytest.raises(RuntimeError, match="live mode"):
            adapter.market_sell("BTC", 0.001)


class TestGetBalance:
    @patch.dict(os.environ, {"BINANCE_API_KEY": "k", "BINANCE_API_SECRET": "s"})
    def test_fetch_balance(self):
        mock_ex = MagicMock()
        mock_ex.fetch_balance.return_value = {"free": {"USDT": 1500.0, "BTC": 0.05}}
        with patch.object(mod, '_get_ccxt_exchange', return_value=mock_ex):
            adapter = BinanceUSExchangeAdapter()
        assert adapter.get_balance("USDT") == 1500.0
        assert adapter.get_balance("BTC") == 0.05

    @patch.dict(os.environ, {"BINANCE_API_KEY": "", "BINANCE_API_SECRET": ""})
    def test_raises_in_paper(self):
        with patch.object(mod, '_get_ccxt_exchange', return_value=MagicMock()):
            adapter = BinanceUSExchangeAdapter()
        with pytest.raises(RuntimeError, match="live mode"):
            adapter.get_balance("USDT")
