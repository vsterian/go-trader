"""Tests for check_strategy.py --execute mode (BinanceUS live trading)."""
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


class TestRunExecute:
    """Test the run_execute() function in check_strategy.py."""

    def _run_execute(self, args, adapter_mock=None, capsys=None):
        """Helper to run execute with mocked sys.argv and adapter."""
        with patch.object(sys, 'argv', ['check_strategy.py'] + args):
            if adapter_mock is None:
                adapter_mock = MagicMock()
                adapter_mock.is_live = True
                adapter_mock.get_spot_price.return_value = 67000.0
                adapter_mock.validate_order.return_value = (0.001, "")
                adapter_mock.market_buy.return_value = {
                    "id": "123", "average": 67050.0, "filled": 0.001, "status": "closed"
                }
                adapter_mock.market_sell.return_value = {
                    "id": "456", "average": 66950.0, "filled": 0.001, "status": "closed"
                }

            mock_cls = MagicMock(return_value=adapter_mock)
            with patch.dict(sys.modules, {}):
                with patch('builtins.__import__', side_effect=lambda name, *a, **kw:
                    type('M', (), {'BinanceUSExchangeAdapter': mock_cls})()
                    if name == 'adapter' else __builtins__.__import__(name, *a, **kw)):
                    # Simpler approach: mock at module level
                    pass

            # Use direct patching of the adapter import
            import importlib
            adapter_mod = type('AdapterModule', (), {'BinanceUSExchangeAdapter': mock_cls})()

            with patch.dict('sys.modules', {'adapter': adapter_mod}):
                mod.run_execute()

    def test_buy_output_format(self, capsys):
        """Test that buy execute outputs correct JSON structure."""
        adapter = MagicMock()
        adapter.is_live = True
        adapter.get_spot_price.return_value = 67000.0
        adapter.validate_order.return_value = (0.001, "")
        adapter.market_buy.return_value = {
            "average": 67050.0, "filled": 0.001, "status": "closed"
        }
        mock_cls = MagicMock(return_value=adapter)
        adapter_mod = type('M', (), {'BinanceUSExchangeAdapter': mock_cls})()

        args = ['--execute', '--symbol=BTC', '--side=buy', '--size=0.001', '--mode=live']
        with patch.object(sys, 'argv', ['check_strategy.py'] + args):
            with patch.dict(sys.modules, {'adapter': adapter_mod}):
                mod.run_execute()

        out = capsys.readouterr().out
        result = json.loads(out)
        assert result["platform"] == "binanceus"
        assert result["execution"]["action"] == "buy"
        assert result["execution"]["fill"]["avg_px"] == 67050.0
        assert result["execution"]["fill"]["total_sz"] == 0.001

    def test_sell_output_format(self, capsys):
        adapter = MagicMock()
        adapter.is_live = True
        adapter.get_spot_price.return_value = 67000.0
        adapter.validate_order.return_value = (0.001, "")
        adapter.market_sell.return_value = {
            "average": 66950.0, "filled": 0.001, "status": "closed"
        }
        mock_cls = MagicMock(return_value=adapter)
        adapter_mod = type('M', (), {'BinanceUSExchangeAdapter': mock_cls})()

        args = ['--execute', '--symbol=BTC', '--side=sell', '--size=0.001', '--mode=live']
        with patch.object(sys, 'argv', ['check_strategy.py'] + args):
            with patch.dict(sys.modules, {'adapter': adapter_mod}):
                mod.run_execute()

        out = capsys.readouterr().out
        result = json.loads(out)
        assert result["execution"]["action"] == "sell"
        assert result["execution"]["fill"]["avg_px"] == 66950.0

    def test_paper_mode_rejected(self, capsys):
        args = ['--execute', '--symbol=BTC', '--side=buy', '--size=0.001', '--mode=paper']
        with patch.object(sys, 'argv', ['check_strategy.py'] + args):
            with pytest.raises(SystemExit):
                mod.run_execute()
        out = capsys.readouterr().out
        result = json.loads(out)
        assert "error" in result
        assert "live" in result["error"]

    def test_validation_failure_rejected(self, capsys):
        adapter = MagicMock()
        adapter.is_live = True
        adapter.get_spot_price.return_value = 67000.0
        adapter.validate_order.return_value = (0, "order value $5.00 below min notional $10.00")
        mock_cls = MagicMock(return_value=adapter)
        adapter_mod = type('M', (), {'BinanceUSExchangeAdapter': mock_cls})()

        args = ['--execute', '--symbol=BTC', '--side=buy', '--size=0.00001', '--mode=live']
        with patch.object(sys, 'argv', ['check_strategy.py'] + args):
            with patch.dict(sys.modules, {'adapter': adapter_mod}):
                with pytest.raises(SystemExit):
                    mod.run_execute()

        out = capsys.readouterr().out
        result = json.loads(out)
        assert "error" in result
        assert "min notional" in result["error"]

    def test_not_live_mode_adapter(self, capsys):
        adapter = MagicMock()
        adapter.is_live = False
        mock_cls = MagicMock(return_value=adapter)
        adapter_mod = type('M', (), {'BinanceUSExchangeAdapter': mock_cls})()

        args = ['--execute', '--symbol=BTC', '--side=buy', '--size=0.001', '--mode=live']
        with patch.object(sys, 'argv', ['check_strategy.py'] + args):
            with patch.dict(sys.modules, {'adapter': adapter_mod}):
                with pytest.raises(SystemExit):
                    mod.run_execute()

        out = capsys.readouterr().out
        result = json.loads(out)
        assert "error" in result
        assert "BINANCE_API_KEY" in result["error"]

    def test_size_adjusted_by_validation(self, capsys):
        """validate_order can adjust size up for min notional."""
        adapter = MagicMock()
        adapter.is_live = True
        adapter.get_spot_price.return_value = 67000.0
        adapter.validate_order.return_value = (0.00015, "")  # Adjusted up from requested 0.00005
        adapter.market_buy.return_value = {
            "average": 67000.0, "filled": 0.00015, "status": "closed"
        }
        mock_cls = MagicMock(return_value=adapter)
        adapter_mod = type('M', (), {'BinanceUSExchangeAdapter': mock_cls})()

        args = ['--execute', '--symbol=BTC', '--side=buy', '--size=0.00005', '--mode=live']
        with patch.object(sys, 'argv', ['check_strategy.py'] + args):
            with patch.dict(sys.modules, {'adapter': adapter_mod}):
                mod.run_execute()

        out = capsys.readouterr().out
        result = json.loads(out)
        assert result["execution"]["size"] == 0.00015
        adapter.market_buy.assert_called_once_with("BTC", 0.00015)

    def test_exception_outputs_error_json(self, capsys):
        adapter = MagicMock()
        adapter.is_live = True
        adapter.get_spot_price.return_value = 67000.0
        adapter.validate_order.return_value = (0.001, "")
        adapter.market_buy.side_effect = Exception("network timeout")
        mock_cls = MagicMock(return_value=adapter)
        adapter_mod = type('M', (), {'BinanceUSExchangeAdapter': mock_cls})()

        args = ['--execute', '--symbol=BTC', '--side=buy', '--size=0.001', '--mode=live']
        with patch.object(sys, 'argv', ['check_strategy.py'] + args):
            with patch.dict(sys.modules, {'adapter': adapter_mod}):
                with pytest.raises(SystemExit):
                    mod.run_execute()

        out = capsys.readouterr().out
        result = json.loads(out)
        assert result["error"] == "network timeout"
        assert result["execution"] is None
