"""Tests for check_strategy.py --execute mode (Binance live trading, balance-based sizing)."""
import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

# Import the execute function
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import importlib.util
spec = importlib.util.spec_from_file_location("check_strategy",
    os.path.join(os.path.dirname(__file__), "check_strategy.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _make_adapter(balance_usdc=100.0, balance_asset=0.5, price=67000.0,
                  validate_return=None, buy_return=None, sell_return=None):
    """Create a mock adapter with sensible defaults for balance-based sizing."""
    adapter = MagicMock()
    adapter.is_live = True
    adapter.MIN_NOTIONAL_FLOOR = 10.0
    adapter.get_spot_price.return_value = price
    adapter.get_balance.side_effect = lambda asset: balance_usdc if asset == "USDC" else balance_asset
    adapter.validate_order.return_value = validate_return or (0.001, "")
    adapter.market_buy.return_value = buy_return or {
        "average": price + 50, "filled": 0.001, "status": "closed"
    }
    adapter.market_sell.return_value = sell_return or {
        "average": price - 50, "filled": balance_asset, "status": "closed"
    }
    return adapter


def _run(args, adapter):
    mock_cls = MagicMock(return_value=adapter)
    adapter_mod = type('M', (), {'BinanceUSExchangeAdapter': mock_cls})()
    with patch.object(sys, 'argv', ['check_strategy.py'] + args):
        with patch.dict(sys.modules, {'adapter': adapter_mod}):
            mod.run_execute()


class TestBalanceBasedBuy:
    """Buy sizing uses real USDC balance from exchange."""

    def test_buy_uses_exchange_balance(self, capsys):
        adapter = _make_adapter(balance_usdc=50.0, price=67000.0,
                                validate_return=(0.0007, ""))
        adapter.market_buy.return_value = {"average": 67050.0, "filled": 0.0007, "status": "closed"}

        _run(['--execute', '--symbol=BTC', '--side=buy', '--mode=live'], adapter)

        out = capsys.readouterr().out
        result = json.loads(out)
        assert result["platform"] == "binanceus"
        assert result["execution"]["action"] == "buy"
        assert result["execution"]["fill"]["avg_px"] == 67050.0
        # Adapter was called with balance-derived size, not a Go-provided size
        adapter.get_balance.assert_any_call("USDC")

    def test_buy_insufficient_balance_rejected(self, capsys):
        adapter = _make_adapter(balance_usdc=5.0)  # Below $10 min notional

        with pytest.raises(SystemExit):
            _run(['--execute', '--symbol=BTC', '--side=buy', '--mode=live'], adapter)

        out = capsys.readouterr().out
        result = json.loads(out)
        assert "insufficient USDC balance" in result["error"]

    def test_buy_validation_adjusts_size(self, capsys):
        adapter = _make_adapter(balance_usdc=100.0, price=67000.0,
                                validate_return=(0.00015, ""))
        adapter.market_buy.return_value = {"average": 67000.0, "filled": 0.00015, "status": "closed"}

        _run(['--execute', '--symbol=BTC', '--side=buy', '--mode=live'], adapter)

        out = capsys.readouterr().out
        result = json.loads(out)
        assert result["execution"]["size"] == 0.00015
        adapter.market_buy.assert_called_once_with("BTC", 0.00015)


class TestBalanceBasedSell:
    """Sell uses real asset balance from exchange."""

    def test_sell_uses_asset_balance(self, capsys):
        adapter = _make_adapter(balance_asset=0.25, price=67000.0,
                                validate_return=(0.25, ""))
        adapter.market_sell.return_value = {"average": 66950.0, "filled": 0.25, "status": "closed"}

        _run(['--execute', '--symbol=BTC', '--side=sell', '--mode=live'], adapter)

        out = capsys.readouterr().out
        result = json.loads(out)
        assert result["execution"]["action"] == "sell"
        assert result["execution"]["fill"]["avg_px"] == 66950.0
        adapter.get_balance.assert_any_call("BTC")

    def test_sell_no_asset_balance_rejected(self, capsys):
        adapter = _make_adapter(balance_asset=0.0)

        with pytest.raises(SystemExit):
            _run(['--execute', '--symbol=BTC', '--side=sell', '--mode=live'], adapter)

        out = capsys.readouterr().out
        result = json.loads(out)
        assert "no BTC balance" in result["error"]


class TestExecuteGuards:
    """Paper mode, missing keys, exceptions."""

    def test_paper_mode_rejected(self, capsys):
        with patch.object(sys, 'argv', ['check_strategy.py', '--execute', '--symbol=BTC',
                                         '--side=buy', '--mode=paper']):
            with pytest.raises(SystemExit):
                mod.run_execute()
        out = capsys.readouterr().out
        result = json.loads(out)
        assert "live" in result["error"]

    def test_not_live_adapter_rejected(self, capsys):
        adapter = _make_adapter()
        adapter.is_live = False
        mock_cls = MagicMock(return_value=adapter)
        adapter_mod = type('M', (), {'BinanceUSExchangeAdapter': mock_cls})()

        with patch.object(sys, 'argv', ['check_strategy.py', '--execute', '--symbol=BTC',
                                         '--side=buy', '--mode=live']):
            with patch.dict(sys.modules, {'adapter': adapter_mod}):
                with pytest.raises(SystemExit):
                    mod.run_execute()
        out = capsys.readouterr().out
        result = json.loads(out)
        assert "BINANCE_API_KEY" in result["error"]

    def test_exception_outputs_error_json(self, capsys):
        adapter = _make_adapter(balance_usdc=100.0)
        adapter.market_buy.side_effect = Exception("network timeout")

        with pytest.raises(SystemExit):
            _run(['--execute', '--symbol=BTC', '--side=buy', '--mode=live'], adapter)

        out = capsys.readouterr().out
        result = json.loads(out)
        assert result["error"] == "network timeout"
        assert result["execution"] is None

    def test_validation_failure_rejected(self, capsys):
        adapter = _make_adapter(balance_usdc=100.0,
                                validate_return=(0, "order value $5.00 below min notional $10.00"))

        with pytest.raises(SystemExit):
            _run(['--execute', '--symbol=BTC', '--side=buy', '--mode=live'], adapter)

        out = capsys.readouterr().out
        result = json.loads(out)
        assert "min notional" in result["error"]
