"""Tests for ml_signal_generator.py — MLSignalGenerator class."""

import os
import sys
import tempfile
import shutil
import numpy as np
import pytest

# Add shared_scripts to path
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _scripts_dir)

from ml_signal_generator import MLSignalGenerator


@pytest.fixture
def tmp_model_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


@pytest.fixture
def ml(tmp_model_dir):
    return MLSignalGenerator(
        symbol="BTC_USDT",
        rsi_threshold_buy=30,
        rsi_threshold_sell=70,
        adx_threshold=25,
        model_dir=tmp_model_dir,
    )


# ─── Feature Extraction ───────────────────────────

class TestFeatureExtraction:
    def test_feature_count(self, ml):
        """Should produce exactly 14 features."""
        features = ml.extract_features(
            price=40000, rsi=35, adx=28,
            lower_band=39000, upper_band=41000,
            rsi_threshold_buy=30, rsi_threshold_sell=70, adx_threshold=25
        )
        assert features.shape == (1, 14)

    def test_known_values(self, ml):
        """Verify specific feature values for known inputs."""
        features = ml.extract_features(
            price=100, rsi=20, adx=30,
            lower_band=90, upper_band=110,
            rsi_threshold_buy=30, rsi_threshold_sell=70, adx_threshold=25
        ).flatten()

        # Feature 0: BB position = (100-90)/(110-90) = 0.5
        assert features[0] == pytest.approx(0.5)
        # Feature 1: price/lower - 1 = 100/90 - 1 ≈ 0.111
        assert features[1] == pytest.approx(100 / 90 - 1, rel=1e-3)
        # Feature 3: RSI normalized = 20/100 = 0.2
        assert features[3] == pytest.approx(0.2)
        # Feature 5: ADX normalized = 30/100 = 0.3
        assert features[5] == pytest.approx(0.3)
        # Feature 8: BB width = (110-90)/100 = 0.2
        assert features[8] == pytest.approx(0.2)
        # Feature 10: Buy confluence = rsi(20) < 30 AND adx(30) > 25 → 1.0
        assert features[10] == 1.0
        # Feature 13: BB squeeze = 0.2 < 0.02 → 0.0
        assert features[13] == 0.0

    def test_zero_price_safe(self, ml):
        """Should not crash with price=0."""
        features = ml.extract_features(
            price=0, rsi=50, adx=20,
            lower_band=90, upper_band=110,
            rsi_threshold_buy=30, rsi_threshold_sell=70, adx_threshold=25
        )
        assert features.shape == (1, 14)
        assert not np.any(np.isnan(features))

    def test_equal_bands_safe(self, ml):
        """Should not crash when upper_band == lower_band."""
        features = ml.extract_features(
            price=100, rsi=50, adx=20,
            lower_band=100, upper_band=100,
            rsi_threshold_buy=30, rsi_threshold_sell=70, adx_threshold=25
        )
        assert features.shape == (1, 14)
        assert not np.any(np.isnan(features))


# ─── Buy Prediction (Untrained) ───────────────────

class TestBuyPredictionUntrained:
    def test_fallback_returns_probability(self, ml):
        """Untrained model should use fallback heuristic."""
        assert not ml.is_trained
        prob = ml.predict_buy_signal(
            price=38000, rsi=25, adx=30,
            lower_band=39000, upper_band=41000,
            rsi_threshold_buy=30, rsi_threshold_sell=70, adx_threshold=25
        )
        assert 0 <= prob <= 1

    def test_oversold_gives_high_probability(self, ml):
        """Oversold conditions should give higher fallback probability."""
        prob_oversold = ml.predict_buy_signal(
            price=85, rsi=15, adx=35,
            lower_band=90, upper_band=110,
            rsi_threshold_buy=30, rsi_threshold_sell=70, adx_threshold=25
        )
        prob_neutral = ml.predict_buy_signal(
            price=100, rsi=50, adx=15,
            lower_band=90, upper_band=110,
            rsi_threshold_buy=30, rsi_threshold_sell=70, adx_threshold=25
        )
        assert prob_oversold > prob_neutral


# ─── Sell Prediction (Untrained) ──────────────────

class TestSellPredictionUntrained:
    def test_fallback_returns_probability(self, ml):
        prob = ml.predict_sell_signal(
            price=42000, rsi=75, adx=30,
            upper_band=41000, lower_band=39000,
            rsi_threshold_sell=70, rsi_threshold_buy=30, adx_threshold=25,
            current_profit_loss=10.0
        )
        assert 0 <= prob <= 1

    def test_high_profit_increases_sell_probability(self, ml):
        """High unrealized profit should increase sell eagerness."""
        prob_high_profit = ml._fallback_sell_signal(
            price=115, rsi=75, adx=30, upper_band=110,
            adx_threshold=25, rsi_threshold_sell=70, pnl=20.0
        )
        prob_low_profit = ml._fallback_sell_signal(
            price=105, rsi=55, adx=20, upper_band=110,
            adx_threshold=25, rsi_threshold_sell=70, pnl=1.0
        )
        assert prob_high_profit > prob_low_profit


# ─── Sell Enhancement ─────────────────────────────

class TestSellEnhancement:
    def test_profit_boost(self, ml):
        """High profit should boost sell probability."""
        base = 0.5
        enhanced = ml._enhance_sell_probability(
            base, price=115, rsi=75, adx=30,
            upper_band=110, rsi_threshold_sell=70, pnl=20.0
        )
        assert enhanced > base

    def test_small_profit_hold(self, ml):
        """Small profit should reduce sell probability."""
        base = 0.5
        enhanced = ml._enhance_sell_probability(
            base, price=101, rsi=55, adx=20,
            upper_band=110, rsi_threshold_sell=70, pnl=1.0
        )
        assert enhanced < base

    def test_clamped_range(self, ml):
        """Enhanced probability should be in [0.05, 0.95]."""
        for pnl in [-30, -10, 0, 5, 20, 50]:
            result = ml._enhance_sell_probability(
                0.5, price=100, rsi=50, adx=25,
                upper_band=110, rsi_threshold_sell=70, pnl=pnl
            )
            assert 0.05 <= result <= 0.95


# ─── Training & Persistence ──────────────────────

class TestTrainingAndPersistence:
    def test_train_with_synthetic_data(self, ml):
        """Model should train successfully with enough diverse data."""
        np.random.seed(42)
        for i in range(60):
            profitable = i % 3 != 0  # 66% win rate
            features = np.random.rand(14)
            ml.prediction_history.append({
                'timestamp': '2024-01-01', 'probability': 0.5,
                'features': features, 'signal_type': 'buy',
            })
            ml.training_features.append(features)
            ml.training_labels.append(1 if profitable else 0)

        ml._retrain_model()
        assert ml.is_trained

    def test_prediction_after_training(self, ml):
        """Trained model should return valid probabilities."""
        # Train first
        np.random.seed(42)
        for i in range(60):
            features = np.random.rand(14)
            ml.training_features.append(features)
            ml.training_labels.append(1 if i % 3 != 0 else 0)
        ml._retrain_model()
        assert ml.is_trained

        prob = ml.predict_buy_signal(
            price=100, rsi=25, adx=30,
            lower_band=90, upper_band=110,
            rsi_threshold_buy=30, rsi_threshold_sell=70, adx_threshold=25
        )
        assert 0 <= prob <= 1

    def test_persistence_roundtrip(self, tmp_model_dir):
        """Saved model should produce identical predictions after reload."""
        ml1 = MLSignalGenerator("TEST", model_dir=tmp_model_dir)
        np.random.seed(42)
        for i in range(60):
            features = np.random.rand(14)
            ml1.training_features.append(features)
            ml1.training_labels.append(1 if i % 3 != 0 else 0)
        ml1._retrain_model()
        assert ml1.is_trained

        pred1 = ml1.predict_buy_signal(
            100, 25, 30, 90, 110, 30, 70, 25
        )
        ml1.save_to_disk()

        # Reload in new instance
        ml2 = MLSignalGenerator("TEST", model_dir=tmp_model_dir)
        assert ml2.is_trained
        pred2 = ml2.predict_buy_signal(
            100, 25, 30, 90, 110, 30, 70, 25
        )
        assert pred1 == pytest.approx(pred2, rel=1e-6)

    def test_record_outcome_triggers_save(self, ml, tmp_model_dir):
        """record_outcome should persist to disk."""
        np.random.seed(42)
        # Store enough for a retrain cycle (need features in prediction_history)
        for i in range(55):
            features = np.random.rand(14)
            ml.prediction_history.append({
                'timestamp': '2024-01-01', 'probability': 0.5,
                'features': features, 'signal_type': 'buy',
            })
            ml.training_features.append(features)
            ml.training_labels.append(1 if i % 3 != 0 else 0)

        # 50th sample should trigger training (50 >= 50 and 50 % 25 == 0)
        ml._retrain_model()

        # Now add prediction + record outcome
        ml.prediction_history.append({
            'timestamp': '2024-01-02', 'probability': 0.7,
            'features': np.random.rand(14), 'signal_type': 'buy',
        })
        ml.record_outcome(True, 5.0)

        # Verify file was created
        assert os.path.exists(os.path.join(tmp_model_dir, 'BTC_USDT_training.pkl'))

    def test_retrain_needs_class_diversity(self, ml):
        """Should not retrain with only one class."""
        for i in range(60):
            ml.training_features.append(np.random.rand(14))
            ml.training_labels.append(1)  # all same class
        ml._retrain_model()
        assert not ml.is_trained

    def test_retrain_needs_class_balance(self, ml):
        """Should not retrain with >80% class imbalance."""
        np.random.seed(42)
        for i in range(60):
            ml.training_features.append(np.random.rand(14))
            ml.training_labels.append(1 if i < 55 else 0)  # 91.7% vs 8.3%
        ml._retrain_model()
        assert not ml.is_trained


# ─── Performance Stats ───────────────────────────

class TestPerformanceStats:
    def test_empty_stats(self, ml):
        stats = ml.get_performance_stats()
        assert stats == {}

    def test_stats_after_outcomes(self, ml):
        ml.actual_outcomes.extend([
            {'profitable': True, 'profit_loss': 5.0},
            {'profitable': True, 'profit_loss': 3.0},
            {'profitable': False, 'profit_loss': -2.0},
        ])
        stats = ml.get_performance_stats()
        assert stats['win_rate'] == pytest.approx(2 / 3, rel=1e-3)
        assert stats['total_trades'] == 3
        assert stats['total_profit'] == pytest.approx(6.0)
