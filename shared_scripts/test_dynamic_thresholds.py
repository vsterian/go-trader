"""Tests for dynamic_thresholds.py — dynamic buy/sell threshold calculation."""

import os
import sys
import pytest

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _scripts_dir)

from dynamic_thresholds import calculate_dynamic_buy_threshold, calculate_dynamic_sell_threshold


# ─── Buy Threshold ───────────────────────────────

class TestDynamicBuyThreshold:
    def test_default_trained(self):
        """Trained model with neutral conditions → base ~0.30."""
        stats = {'is_trained': True, 'win_rate': 0.5}
        t = calculate_dynamic_buy_threshold(
            stats, price=100, rsi=50, adx=20,
            lower_band=95, upper_band=105,
            rsi_threshold_buy=30, adx_threshold=25
        )
        assert 0.05 <= t <= 0.60

    def test_default_untrained(self):
        """Untrained model → base ~0.20 (lower, more aggressive)."""
        stats = {'is_trained': False}
        t = calculate_dynamic_buy_threshold(
            stats, price=100, rsi=50, adx=20,
            lower_band=95, upper_band=105,
            rsi_threshold_buy=30, adx_threshold=25
        )
        assert t < 0.30  # lower than trained base

    def test_volatile_market_lowers_threshold(self):
        """Wider Bollinger Bands (high volatility) → lower threshold."""
        stats = {'is_trained': True, 'win_rate': 0.5}
        narrow = calculate_dynamic_buy_threshold(
            stats, price=100, rsi=50, adx=20,
            lower_band=99.9, upper_band=100.1,  # very narrow bands
            rsi_threshold_buy=30, adx_threshold=25
        )
        wide = calculate_dynamic_buy_threshold(
            stats, price=100, rsi=50, adx=20,
            lower_band=80, upper_band=120,  # wide bands
            rsi_threshold_buy=30, adx_threshold=25
        )
        assert wide < narrow

    def test_confluence_lowers_threshold(self):
        """Multiple oversold signals → lower threshold (more aggressive)."""
        stats = {'is_trained': True, 'win_rate': 0.5}
        no_confluence = calculate_dynamic_buy_threshold(
            stats, price=100, rsi=50, adx=15,
            lower_band=95, upper_band=105,
            rsi_threshold_buy=30, adx_threshold=25
        )
        full_confluence = calculate_dynamic_buy_threshold(
            stats, price=88, rsi=20, adx=35,  # below lower band, low RSI, high ADX
            lower_band=90, upper_band=110,
            rsi_threshold_buy=30, adx_threshold=25
        )
        assert full_confluence < no_confluence

    def test_high_win_rate_raises_threshold(self):
        """High win rate → be more selective (higher threshold)."""
        high_wr = {'is_trained': True, 'win_rate': 0.70}
        low_wr = {'is_trained': True, 'win_rate': 0.30}
        t_high = calculate_dynamic_buy_threshold(
            high_wr, 100, 50, 20, 95, 105, 30, 25
        )
        t_low = calculate_dynamic_buy_threshold(
            low_wr, 100, 50, 20, 95, 105, 30, 25
        )
        assert t_high > t_low

    def test_urgency_extreme_oversold(self):
        """Extreme oversold (price < lower AND rsi < 0.7*threshold) → extra aggressive."""
        stats = {'is_trained': True, 'win_rate': 0.5}
        normal = calculate_dynamic_buy_threshold(
            stats, price=95, rsi=29, adx=20,
            lower_band=90, upper_band=110,
            rsi_threshold_buy=30, adx_threshold=25
        )
        extreme = calculate_dynamic_buy_threshold(
            stats, price=85, rsi=18, adx=20,  # price < lower AND rsi < 30*0.7=21
            lower_band=90, upper_band=110,
            rsi_threshold_buy=30, adx_threshold=25
        )
        assert extreme < normal

    def test_always_in_range(self):
        """Result should always be in [0.05, 0.60]."""
        for is_trained in [True, False]:
            for rsi in [5, 20, 50, 80, 95]:
                for adx in [5, 20, 40, 60]:
                    stats = {'is_trained': is_trained, 'win_rate': 0.3}
                    t = calculate_dynamic_buy_threshold(
                        stats, price=100, rsi=rsi, adx=adx,
                        lower_band=85, upper_band=115,
                        rsi_threshold_buy=30, adx_threshold=25
                    )
                    assert 0.05 <= t <= 0.60, f"Out of range: {t} (rsi={rsi}, adx={adx})"


# ─── Sell Threshold ──────────────────────────────

class TestDynamicSellThreshold:
    def test_default_trained(self):
        stats = {'is_trained': True}
        t = calculate_dynamic_sell_threshold(
            stats, price=100, rsi=50, adx=20,
            upper_band=105, current_profit_pct=5.0,
            rsi_threshold_sell=70, adx_threshold=25
        )
        assert 0.40 <= t <= 0.85

    def test_big_profit_lowers_threshold(self):
        """Big unrealized profit → more willing to sell (lower threshold)."""
        stats = {'is_trained': True}
        t_big = calculate_dynamic_sell_threshold(
            stats, 100, 50, 20, 105, current_profit_pct=30.0, rsi_threshold_sell=70, adx_threshold=25
        )
        t_small = calculate_dynamic_sell_threshold(
            stats, 100, 50, 20, 105, current_profit_pct=2.0, rsi_threshold_sell=70, adx_threshold=25
        )
        assert t_big < t_small

    def test_small_profit_holds(self):
        """Small profit → hold strongly (higher threshold)."""
        stats = {'is_trained': True}
        t_tiny = calculate_dynamic_sell_threshold(
            stats, 100, 50, 20, 105, current_profit_pct=1.0, rsi_threshold_sell=70, adx_threshold=25
        )
        t_neutral = calculate_dynamic_sell_threshold(
            stats, 100, 50, 20, 105, current_profit_pct=10.0, rsi_threshold_sell=70, adx_threshold=25
        )
        assert t_tiny > t_neutral

    def test_big_loss_willing_to_cut(self):
        """Big loss → willing to cut (lower threshold)."""
        stats = {'is_trained': True}
        t_loss = calculate_dynamic_sell_threshold(
            stats, 100, 50, 20, 105, current_profit_pct=-25.0, rsi_threshold_sell=70, adx_threshold=25
        )
        t_small_loss = calculate_dynamic_sell_threshold(
            stats, 100, 50, 20, 105, current_profit_pct=-5.0, rsi_threshold_sell=70, adx_threshold=25
        )
        assert t_loss < t_small_loss

    def test_always_in_range(self):
        """Result should always be in [0.40, 0.85]."""
        stats = {'is_trained': True}
        for profit in [-30, -15, -5, 0, 2, 5, 10, 20, 40]:
            t = calculate_dynamic_sell_threshold(
                stats, 100, 50, 20, 105,
                current_profit_pct=profit,
                rsi_threshold_sell=70, adx_threshold=25
            )
            assert 0.40 <= t <= 0.85, f"Out of range: {t} (profit={profit})"
