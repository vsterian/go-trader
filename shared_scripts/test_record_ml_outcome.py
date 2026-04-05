"""Tests for record_ml_outcome.py subprocess script."""

import json
import os
import subprocess
import sys
import tempfile
import pytest

_scripts_dir = os.path.dirname(os.path.abspath(__file__))


class TestRecordMlOutcome:
    @pytest.fixture(autouse=True)
    def setup_env(self, tmp_path):
        """Patch MODEL_DIR env so the script writes to temp dir."""
        self.model_dir = str(tmp_path)
        self.script = os.path.join(_scripts_dir, 'record_ml_outcome.py')

    def _run(self, args, env_extra=None):
        env = os.environ.copy()
        if env_extra:
            env.update(env_extra)
        result = subprocess.run(
            [sys.executable, self.script] + args,
            capture_output=True, text=True, timeout=15, env=env,
        )
        return result

    def test_missing_args(self):
        r = self._run([])
        out = json.loads(r.stdout)
        assert 'error' in out
        assert r.returncode == 1

    def test_record_profitable_trade(self, tmp_path):
        sys.path.insert(0, _scripts_dir)
        from ml_signal_generator import MLSignalGenerator
        from performance_monitor import PerformanceMonitor

        model_dir = str(tmp_path)
        ml = MLSignalGenerator(symbol='BTC/USDT', model_dir=model_dir)
        ml.record_outcome(True)
        ml.record_outcome(True)

        pm = PerformanceMonitor('test-strat', 'BTC/USDT', model_dir=model_dir)
        pm.record_trade({'pnl': 5.0, 'profitable': True})

        assert pm.metrics['total_trades'] == 1
        assert pm.metrics['win_rate'] == 1.0

    def test_record_unprofitable_trade(self, tmp_path):
        sys.path.insert(0, _scripts_dir)
        from performance_monitor import PerformanceMonitor

        model_dir = str(tmp_path)
        pm = PerformanceMonitor('test-strat', 'BTC/USDT', model_dir=model_dir)
        pm.record_trade({'pnl': -3.0, 'profitable': False})

        assert pm.metrics['losses'] == 1
        assert pm.metrics['win_rate'] == 0.0

    def test_compile(self):
        """Script compiles without errors."""
        result = subprocess.run(
            [sys.executable, '-m', 'py_compile', self.script],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
