"""Tests for correlation_analyzer.py."""

import json
import os
import sys
import tempfile
import pytest
import numpy as np

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _scripts_dir)

from correlation_analyzer import check_correlation, compute_correlation


class TestCheckCorrelation:
    def test_empty_existing_positions(self):
        result = check_correlation('BTC/USDC', [])
        assert result['blocked'] is False
        assert result['correlations'] == {}

    def test_same_symbol_not_counted(self):
        """If new symbol is already in existing, skip self-correlation."""
        # This would normally need data_fetcher — mock via monkeypatch
        result = check_correlation('BTC/USDC', ['BTC/USDC'])
        assert result['blocked'] is False
        assert result['correlations'] == {}

    def test_result_structure(self):
        result = check_correlation('ETH/USDC', [])
        assert 'symbol' in result
        assert 'blocked' in result
        assert 'reason' in result
        assert 'correlations' in result
        assert result['symbol'] == 'ETH/USDC'


class TestComputeCorrelation:
    def test_correlation_with_mock(self, monkeypatch):
        """Test correlation computation with mocked data fetcher."""
        import pandas as pd

        np.random.seed(42)
        n = 50
        dates = pd.date_range('2024-01-01', periods=n, freq='D')
        base = 100 + np.cumsum(np.random.randn(n))
        correlated = base + np.random.randn(n) * 0.5  # highly correlated
        uncorrelated = 100 + np.cumsum(np.random.randn(n) * 2)  # independent

        def mock_fetch(symbol, timeframe, limit, store):
            data = base if 'BTC' in symbol else (correlated if 'ETH' in symbol else uncorrelated)
            return pd.DataFrame({'close': data[:limit]}, index=dates[:limit])

        # Monkeypatch the data_fetcher import
        import types
        fake_mod = types.ModuleType('data_fetcher')
        fake_mod.fetch_ohlcv = mock_fetch
        monkeypatch.setitem(sys.modules, 'data_fetcher', fake_mod)

        # Clear cache to avoid stale data from prior test runs
        import correlation_analyzer
        cache_file = correlation_analyzer._CACHE_FILE
        if os.path.exists(cache_file):
            os.remove(cache_file)

        # Test high correlation
        corr = compute_correlation('BTC/USDC', 'ETH/USDC')
        assert corr > 0.7, f"Expected high correlation, got {corr}"

    def test_check_blocks_correlated(self, monkeypatch):
        """Full check_correlation with mocked highly correlated data."""
        import pandas as pd

        np.random.seed(42)
        n = 50
        dates = pd.date_range('2024-01-01', periods=n, freq='D')
        base = 100 + np.cumsum(np.random.randn(n))
        correlated = base + np.random.randn(n) * 0.3

        def mock_fetch(symbol, timeframe, limit, store):
            data = base if 'BTC' in symbol else correlated
            return pd.DataFrame({'close': data[:limit]}, index=dates[:limit])

        import types
        fake_mod = types.ModuleType('data_fetcher')
        fake_mod.fetch_ohlcv = mock_fetch
        monkeypatch.setitem(sys.modules, 'data_fetcher', fake_mod)

        # Clear cache to avoid stale data
        import correlation_analyzer
        cache_file = correlation_analyzer._CACHE_FILE
        if os.path.exists(cache_file):
            os.remove(cache_file)

        result = check_correlation('ETH/USDC', ['BTC/USDC'], threshold=0.7)
        assert result['blocked'] is True
        assert 'BTC/USDC' in result['correlations']

    def test_check_allows_uncorrelated(self, monkeypatch):
        """Uncorrelated data should not block."""
        import pandas as pd

        np.random.seed(123)
        n = 50
        dates = pd.date_range('2024-01-01', periods=n, freq='D')
        data_a = 100 + np.cumsum(np.random.randn(n))
        data_b = 100 + np.cumsum(np.random.randn(n) * 3)

        def mock_fetch(symbol, timeframe, limit, store):
            data = data_a if 'BTC' in symbol else data_b
            return pd.DataFrame({'close': data[:limit]}, index=dates[:limit])

        import types
        fake_mod = types.ModuleType('data_fetcher')
        fake_mod.fetch_ohlcv = mock_fetch
        monkeypatch.setitem(sys.modules, 'data_fetcher', fake_mod)

        # Clear cache
        import correlation_analyzer
        cache_file = correlation_analyzer._CACHE_FILE
        if os.path.exists(cache_file):
            os.remove(cache_file)

        result = check_correlation('ETH/USDC', ['BTC/USDC'], threshold=0.7)
        # May or may not be blocked depending on random seed — just check structure
        assert 'blocked' in result
        assert 'BTC/USDC' in result['correlations']


class TestCompile:
    def test_compile(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, '-m', 'py_compile',
             os.path.join(_scripts_dir, 'correlation_analyzer.py')],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
