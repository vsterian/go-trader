"""Tests for performance_monitor.py."""

import os
import sys
import json
import tempfile
import pytest

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _scripts_dir)

from performance_monitor import PerformanceMonitor


@pytest.fixture
def tmp_model_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestRecordTrade:
    def test_record_profitable(self, tmp_model_dir):
        pm = PerformanceMonitor('test-strat', 'BTC/USDC', model_dir=tmp_model_dir)
        pm.record_trade({'pnl': 5.0})
        assert pm.metrics['total_trades'] == 1
        assert pm.metrics['wins'] == 1
        assert pm.metrics['losses'] == 0
        assert pm.metrics['win_rate'] == 1.0

    def test_record_unprofitable(self, tmp_model_dir):
        pm = PerformanceMonitor('test-strat', 'BTC/USDC', model_dir=tmp_model_dir)
        pm.record_trade({'pnl': -3.0})
        assert pm.metrics['total_trades'] == 1
        assert pm.metrics['losses'] == 1
        assert pm.metrics['win_rate'] == 0.0

    def test_multiple_trades(self, tmp_model_dir):
        pm = PerformanceMonitor('test-strat', 'BTC/USDC', model_dir=tmp_model_dir)
        for pnl in [5, -2, 3, -1, 8, -4, 2, 1, -3, 6]:
            pm.record_trade({'pnl': pnl})
        assert pm.metrics['total_trades'] == 10
        assert pm.metrics['wins'] == 6
        assert pm.metrics['win_rate'] == 0.6


class TestMetricsCalculation:
    def test_win_rate(self, tmp_model_dir):
        pm = PerformanceMonitor('test-strat', 'BTC/USDC', model_dir=tmp_model_dir)
        pm.record_trade({'pnl': 5.0})
        pm.record_trade({'pnl': -2.0})
        assert pm.metrics['win_rate'] == 0.5

    def test_profit_factor(self, tmp_model_dir):
        pm = PerformanceMonitor('test-strat', 'BTC/USDC', model_dir=tmp_model_dir)
        pm.record_trade({'pnl': 10.0})
        pm.record_trade({'pnl': -5.0})
        assert pm.metrics['profit_factor'] == 2.0

    def test_profit_factor_no_losses(self, tmp_model_dir):
        pm = PerformanceMonitor('test-strat', 'BTC/USDC', model_dir=tmp_model_dir)
        pm.record_trade({'pnl': 5.0})
        assert pm.metrics['profit_factor'] == float('inf')

    def test_drawdown(self, tmp_model_dir):
        pm = PerformanceMonitor('test-strat', 'BTC/USDC', model_dir=tmp_model_dir)
        for pnl in [10, -5, -3]:
            pm.record_trade({'pnl': pnl})
        assert pm.metrics['max_drawdown_pct'] == 8.0  # peak 10, trough 2, dd=8

    def test_avg_profit(self, tmp_model_dir):
        pm = PerformanceMonitor('test-strat', 'BTC/USDC', model_dir=tmp_model_dir)
        pm.record_trade({'pnl': 10.0})
        pm.record_trade({'pnl': -4.0})
        assert pm.metrics['avg_profit_pct'] == 3.0

    def test_cumulative_profit(self, tmp_model_dir):
        pm = PerformanceMonitor('test-strat', 'BTC/USDC', model_dir=tmp_model_dir)
        pm.record_trade({'pnl': 10.0})
        pm.record_trade({'pnl': -4.0})
        assert pm.metrics['cumulative_profit'] == 6.0


class TestShouldAdapt:
    def test_not_enough_trades(self, tmp_model_dir):
        pm = PerformanceMonitor('test-strat', 'BTC/USDC', model_dir=tmp_model_dir)
        for i in range(5):
            pm.record_trade({'pnl': 1.0})
        assert pm.should_adapt() is False

    def test_degradation_triggers(self, tmp_model_dir):
        """Simulate win rate drop — 50 wins then 20 losses."""
        pm = PerformanceMonitor('test-strat', 'BTC/USDC', model_dir=tmp_model_dir)
        # Build up high win rate
        for _ in range(50):
            pm.record_trade({'pnl': 3.0})
        # Now degrade — 20 losses
        for _ in range(20):
            pm.record_trade({'pnl': -2.0})
        assert pm.should_adapt() is True

    def test_stable_performance(self, tmp_model_dir):
        pm = PerformanceMonitor('test-strat', 'BTC/USDC', model_dir=tmp_model_dir)
        for i in range(30):
            pm.record_trade({'pnl': 2.0 if i % 2 == 0 else -1.0})
        # Steady ~50% win rate, no degradation
        assert pm.should_adapt() is False

    def test_time_based_adaptation(self, tmp_model_dir):
        """If last_optimized is >24h ago, should_adapt returns True."""
        pm = PerformanceMonitor('test-strat', 'BTC/USDC', model_dir=tmp_model_dir)
        for _ in range(15):
            pm.record_trade({'pnl': 1.0})
        # Simulate old optimization timestamp
        from datetime import datetime, timedelta
        pm.metrics['last_optimized'] = (datetime.now() - timedelta(hours=25)).isoformat()
        pm._save_metrics()
        assert pm.should_adapt() is True


class TestPersistence:
    def test_roundtrip(self, tmp_model_dir):
        pm1 = PerformanceMonitor('test-strat', 'BTC/USDC', model_dir=tmp_model_dir)
        pm1.record_trade({'pnl': 5.0})
        pm1.record_trade({'pnl': -2.0})

        pm2 = PerformanceMonitor('test-strat', 'BTC/USDC', model_dir=tmp_model_dir)
        assert pm2.metrics['total_trades'] == 2
        assert pm2.metrics['win_rate'] == 0.5
        assert len(pm2.trades) == 2

    def test_file_format(self, tmp_model_dir):
        pm = PerformanceMonitor('test-strat', 'BTC/USDC', model_dir=tmp_model_dir)
        pm.record_trade({'pnl': 3.0})
        path = os.path.join(tmp_model_dir, 'test-strat_metrics.json')
        assert os.path.exists(path)
        with open(path) as f:
            data = json.load(f)
        assert 'trades' in data
        assert 'metrics' in data

    def test_mark_optimized(self, tmp_model_dir):
        pm = PerformanceMonitor('test-strat', 'BTC/USDC', model_dir=tmp_model_dir)
        pm.mark_optimized()
        assert pm.metrics['last_optimized'] is not None
        pm2 = PerformanceMonitor('test-strat', 'BTC/USDC', model_dir=tmp_model_dir)
        assert pm2.metrics['last_optimized'] is not None
