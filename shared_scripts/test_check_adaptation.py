"""Tests for check_adaptation.py."""

import json
import os
import sys
import tempfile
import subprocess
import pytest

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _scripts_dir)

from check_adaptation import check_adaptation
from performance_monitor import PerformanceMonitor
from datetime import datetime, timedelta


class TestCheckAdaptation:
    def test_no_adaptation_no_trades(self, tmp_path):
        result = check_adaptation('test', 'BTC/USDC', '1h', model_dir=str(tmp_path))
        assert result['needs_adaptation'] is False

    def test_no_adaptation_stable(self, tmp_path):
        pm = PerformanceMonitor('test', 'BTC/USDC', model_dir=str(tmp_path))
        for i in range(20):
            pm.record_trade({'pnl': 2.0 if i % 2 == 0 else -1.0})
        result = check_adaptation('test', 'BTC/USDC', '1h', model_dir=str(tmp_path))
        assert result['needs_adaptation'] is False

    def test_adaptation_degradation(self, tmp_path):
        pm = PerformanceMonitor('test', 'BTC/USDC', model_dir=str(tmp_path))
        for _ in range(50):
            pm.record_trade({'pnl': 3.0})
        for _ in range(20):
            pm.record_trade({'pnl': -2.0})
        result = check_adaptation('test', 'BTC/USDC', '1h', model_dir=str(tmp_path))
        assert result['needs_adaptation'] is True
        assert 'degraded' in result['reason']

    def test_adaptation_time_based(self, tmp_path):
        pm = PerformanceMonitor('test', 'BTC/USDC', model_dir=str(tmp_path))
        for _ in range(15):
            pm.record_trade({'pnl': 1.0})
        pm.metrics['last_optimized'] = (datetime.now() - timedelta(hours=25)).isoformat()
        pm._save_metrics()
        result = check_adaptation('test', 'BTC/USDC', '1h', model_dir=str(tmp_path))
        assert result['needs_adaptation'] is True
        assert 'time_based' in result['reason']

    def test_force_flag(self, tmp_path):
        result = check_adaptation('test', 'BTC/USDC', '1h', force=True, model_dir=str(tmp_path))
        assert result['needs_adaptation'] is True
        assert 'forced' in result['reason']

    def test_output_format(self, tmp_path):
        result = check_adaptation('test', 'BTC/USDC', '1h', model_dir=str(tmp_path))
        assert 'needs_adaptation' in result
        assert 'reason' in result
        assert 'current_metrics' in result
        assert 'suggestion' in result


class TestCompile:
    def test_compile(self):
        result = subprocess.run(
            [sys.executable, '-m', 'py_compile',
             os.path.join(_scripts_dir, 'check_adaptation.py')],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
