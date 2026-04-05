"""
ML Signal Generator for go-trader.

Ported from dockertradingbot/ml_signal_generator.py.
Adapted for go-trader's stateless subprocess model:
  - Filesystem persistence (pickle) instead of PostgreSQL
  - No background save thread — save explicitly after record_outcome
  - No Config() singleton — all params passed via constructor

Usage (within check_strategy.py):
    ml = MLSignalGenerator("BTC_USDT")
    buy_prob = ml.predict_buy_signal(price, rsi, adx, lower, upper, 30, 70, 25)
    sell_prob = ml.predict_sell_signal(price, rsi, adx, upper, lower, 70, 30, 25, pnl)
"""

import logging
import os
import pickle
import numpy as np
from collections import deque
from datetime import datetime

from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', 'models')


class MLSignalGenerator:
    def __init__(self, symbol, rsi_threshold_buy=35, rsi_threshold_sell=43,
                 adx_threshold=30, max_memory_size=1000, model_dir=None):
        self.symbol = symbol
        self.rsi_threshold_buy = rsi_threshold_buy
        self.rsi_threshold_sell = rsi_threshold_sell
        self.adx_threshold = adx_threshold
        self.max_memory_size = max_memory_size
        self._model_dir = model_dir or MODEL_DIR

        # In-memory training data
        self.training_features = deque(maxlen=max_memory_size)
        self.training_labels = deque(maxlen=max_memory_size)

        # ML Models
        self.model = RandomForestClassifier(
            n_estimators=50, max_depth=10, random_state=42, n_jobs=1
        )
        self.scaler = StandardScaler()
        self.is_trained = False

        # Performance tracking
        self.prediction_history = deque(maxlen=100)
        self.actual_outcomes = deque(maxlen=100)

        # Load persisted model from disk
        self._load_from_disk()

    # ──────────────────────────────────────────────────────────────────
    # Filesystem persistence (replaces PostgreSQL)
    # ──────────────────────────────────────────────────────────────────
    def _model_path(self):
        return os.path.join(self._model_dir, f'{self.symbol}_model.pkl')

    def _training_path(self):
        return os.path.join(self._model_dir, f'{self.symbol}_training.pkl')

    def save_to_disk(self):
        """Persist model and training data to filesystem."""
        os.makedirs(self._model_dir, exist_ok=True)
        try:
            if self.is_trained:
                with open(self._model_path(), 'wb') as f:
                    pickle.dump({
                        'model': self.model,
                        'scaler': self.scaler,
                        'is_trained': True,
                    }, f)

            with open(self._training_path(), 'wb') as f:
                pickle.dump({
                    'features': list(self.training_features),
                    'labels': list(self.training_labels),
                    'prediction_history': [
                        {k: v for k, v in p.items() if k != 'features'}
                        for p in list(self.prediction_history)[-50:]
                    ],
                    'actual_outcomes': list(self.actual_outcomes)[-50:],
                }, f)
        except Exception as e:
            logger.error(f"[{self.symbol}] Save error: {e}")

    def _load_from_disk(self):
        """Load persisted model and training data from filesystem."""
        try:
            model_path = self._model_path()
            if os.path.exists(model_path):
                with open(model_path, 'rb') as f:
                    d = pickle.load(f)
                    self.model = d['model']
                    self.scaler = d['scaler']
                    self.is_trained = d.get('is_trained', True)
                logger.info(f"[{self.symbol}] ML model loaded from disk")
        except Exception as e:
            logger.error(f"[{self.symbol}] Failed to load model: {e}")

        try:
            training_path = self._training_path()
            if os.path.exists(training_path):
                with open(training_path, 'rb') as f:
                    d = pickle.load(f)
                    self.training_features.extend(d.get('features', []))
                    self.training_labels.extend(d.get('labels', []))
                    self.prediction_history.extend(d.get('prediction_history', []))
                    self.actual_outcomes.extend(d.get('actual_outcomes', []))
                logger.info(f"[{self.symbol}] Training data loaded ({len(self.training_features)} samples)")
        except Exception as e:
            logger.error(f"[{self.symbol}] Failed to load training data: {e}")

    # ──────────────────────────────────────────────────────────────────
    # Feature extraction (14 features — preserved exactly from source)
    # ──────────────────────────────────────────────────────────────────
    def extract_features(self, price, rsi, adx, lower_band, upper_band,
                         rsi_threshold_buy, rsi_threshold_sell, adx_threshold):
        """Extract 14-element feature vector for ML prediction.

        Features:
          0: BB position — (price - lower) / (upper - lower)
          1: Price vs lower — price / lower - 1
          2: Upper vs price — upper / price - 1
          3: RSI normalized — rsi / 100
          4: RSI buy gap — max(0, threshold - rsi) / threshold
          5: ADX normalized — adx / 100
          6: ADX ratio — adx / threshold
          7: ADX excess — max(0, adx - threshold) / threshold
          8: BB width — (upper - lower) / price
          9: RSI×ADX — (rsi/100) * (adx/100)
         10: Buy confluence — float(rsi < threshold AND adx > threshold)
         11: Price+RSI confluence — float(price < lower AND rsi < threshold)
         12: Momentum vs midline — (price - mid) / half_width
         13: BB squeeze — float(bb_width < 0.02)
        """
        bb_width = (upper_band - lower_band) / price if price > 0 else 0
        bb_range = upper_band - lower_band
        features = [
            (price - lower_band) / bb_range if bb_range > 0 else 0.5,
            price / lower_band - 1 if lower_band > 0 else 0,
            upper_band / price - 1 if price > 0 else 0,
            rsi / 100,
            max(0, rsi_threshold_buy - rsi) / rsi_threshold_buy if rsi_threshold_buy > 0 else 0,
            adx / 100,
            adx / adx_threshold if adx_threshold > 0 else 0,
            max(0, adx - adx_threshold) / adx_threshold if adx_threshold > 0 else 0,
            bb_width,
            (rsi / 100) * (adx / 100),
            float((rsi < rsi_threshold_buy) and (adx > adx_threshold)),
            float((price < lower_band) and (rsi < rsi_threshold_buy)),
            (price - (lower_band + upper_band) / 2) / (bb_range / 2) if bb_range > 0 else 0,
            float(bb_width < 0.02),
        ]
        return np.array(features, dtype=float).reshape(1, -1)

    # ──────────────────────────────────────────────────────────────────
    # Buy prediction
    # ──────────────────────────────────────────────────────────────────
    def predict_buy_signal(self, price, rsi, adx, lower_band, upper_band,
                           rsi_threshold_buy, rsi_threshold_sell, adx_threshold):
        """Return buy probability [0, 1]."""
        try:
            features = self.extract_features(
                price, rsi, adx, lower_band, upper_band,
                rsi_threshold_buy, rsi_threshold_sell, adx_threshold
            )
            if not self.is_trained:
                return self._fallback_signal(price, rsi, adx, lower_band, adx_threshold, rsi_threshold_buy)

            X = self.scaler.transform(features)
            prob = float(self.model.predict_proba(X)[0][1])
            self.prediction_history.append({
                'timestamp': datetime.now().isoformat(),
                'probability': prob,
                'signal_type': 'buy',
            })
            return prob
        except Exception as e:
            logger.error(f"[{self.symbol}] ML buy prediction error: {e}")
            return self._fallback_signal(price, rsi, adx, lower_band, adx_threshold, rsi_threshold_buy)

    # ──────────────────────────────────────────────────────────────────
    # Sell prediction
    # ──────────────────────────────────────────────────────────────────
    def predict_sell_signal(self, price, rsi, adx, upper_band, lower_band,
                            rsi_threshold_sell, rsi_threshold_buy, adx_threshold,
                            current_profit_loss=0.0):
        """Return sell probability [0, 1]."""
        try:
            features = self.extract_features(
                price, rsi, adx, lower_band, upper_band,
                rsi_threshold_buy, rsi_threshold_sell, adx_threshold
            )
            if not self.is_trained:
                return self._fallback_sell_signal(
                    price, rsi, adx, upper_band, adx_threshold,
                    rsi_threshold_sell, current_profit_loss
                )
            X = self.scaler.transform(features)
            buy_prob = float(self.model.predict_proba(X)[0][1])
            base_sell = 1.0 - buy_prob
            sell_prob = self._enhance_sell_probability(
                base_sell, price, rsi, adx, upper_band, rsi_threshold_sell, current_profit_loss
            )
            self.prediction_history.append({
                'timestamp': datetime.now().isoformat(),
                'probability': sell_prob,
                'signal_type': 'sell',
            })
            return sell_prob
        except Exception as e:
            logger.error(f"[{self.symbol}] ML sell error: {e}")
            return self._fallback_sell_signal(
                price, rsi, adx, upper_band, adx_threshold,
                rsi_threshold_sell, current_profit_loss
            )

    # ──────────────────────────────────────────────────────────────────
    # Sell probability helpers
    # ──────────────────────────────────────────────────────────────────
    def _enhance_sell_probability(self, base, price, rsi, adx, upper_band,
                                  rsi_threshold_sell, pnl):
        p = base
        if pnl > 15:
            p += min(pnl / 25.0, 0.35)
        elif pnl > 8:
            p += min(pnl / 30.0, 0.25)
        elif pnl > 3:
            p += min(pnl / 40.0, 0.15)
        elif pnl > 0.5:
            p -= 0.10
        elif pnl < -15:
            p += min(abs(pnl) / 30.0, 0.25)
        elif pnl < -8:
            p += min(abs(pnl) / 40.0, 0.15)

        if price > upper_band:
            p += 0.15
        if rsi > rsi_threshold_sell:
            p += 0.15
        if adx > 35:
            p += 0.08
        return max(0.05, min(p, 0.95))

    # ──────────────────────────────────────────────────────────────────
    # Fallback heuristics (used when model is untrained)
    # ──────────────────────────────────────────────────────────────────
    def _fallback_signal(self, price, rsi, adx, lower_band, adx_threshold, rsi_threshold_buy):
        c = 0.0
        tot = 3.5
        if price < lower_band:
            c += 1.5
        if rsi < rsi_threshold_buy:
            c += 1.5
        if adx > adx_threshold * 0.8:
            c += 1
        if rsi < rsi_threshold_buy * 1.3:
            c += 0.5
        if price < lower_band * 1.01:
            c += 0.3
        if rsi < 50:
            c += 0.2
        prob = min(c / tot, 1.0)
        return min(prob * 1.5, 1.0)

    def _fallback_sell_signal(self, price, rsi, adx, upper_band, adx_threshold,
                              rsi_threshold_sell, pnl):
        c = 0.0
        tot = 4.0
        if price > upper_band:
            c += 1.5
        if rsi > rsi_threshold_sell:
            c += 1.5
        if adx > adx_threshold:
            c += 1
        if pnl > 15:
            c += 1.0
        elif pnl > 8:
            c += 0.7
        elif pnl > 3:
            c += 0.4
        elif pnl > 0.5:
            c -= 0.3
        elif pnl < -15:
            c += 0.8
        elif pnl < -8:
            c += 0.5
        if rsi > rsi_threshold_sell * 1.1:
            c += 0.3
        if price > upper_band * 1.005:
            c += 0.2
        prob = min(c / tot, 1.0)
        return min(prob * 1.2, 0.9)

    # ──────────────────────────────────────────────────────────────────
    # Training & outcome recording
    # ──────────────────────────────────────────────────────────────────
    def record_outcome(self, was_profitable, profit_loss=0.0):
        """Record a trade outcome for online learning.

        Called by record_ml_outcome.py after each trade closes.
        Saves to disk after recording.
        """
        if self.prediction_history:
            recent = self.prediction_history[-1]
            self.actual_outcomes.append({
                'timestamp': datetime.now().isoformat(),
                'profitable': was_profitable,
                'profit_loss': profit_loss,
                'prediction_prob': recent.get('probability', 0),
            })
            # Store features for retraining (flatten if stored as array)
            feat = recent.get('features')
            if feat is not None:
                self.training_features.append(
                    feat.flatten() if hasattr(feat, 'flatten') else feat
                )
            else:
                # No features stored (stateless mode) — skip training update
                return

            self.training_labels.append(1 if was_profitable else 0)

            n = len(self.training_features)
            if n >= 50 and n % 25 == 0:
                self._retrain_model()

            self.save_to_disk()

    def _retrain_model(self):
        """Retrain the model with accumulated training data."""
        try:
            if len(self.training_features) < 15:
                return
            X = np.array(list(self.training_features))
            y = np.array(list(self.training_labels))
            unique, counts = np.unique(y, return_counts=True)
            if len(unique) < 2:
                logger.warning(f"[{self.symbol}] Not enough class diversity for retraining")
                return
            min_ratio = counts.min() / counts.sum()
            if min_ratio < 0.20:
                logger.warning(f"[{self.symbol}] Class imbalance too high ({min_ratio:.1%}), skipping retrain")
                return
            self.scaler.fit(X)
            self.model.fit(self.scaler.transform(X), y)
            self.is_trained = True
            acc = self.model.score(self.scaler.transform(X), y)
            logger.info(f"[{self.symbol}] Model retrained. Accuracy: {acc:.3f}, samples: {len(X)}")
        except Exception as e:
            logger.error(f"[{self.symbol}] Retraining failed: {e}")

    # ──────────────────────────────────────────────────────────────────
    # Performance stats
    # ──────────────────────────────────────────────────────────────────
    def get_performance_stats(self):
        """Return performance metrics for dynamic threshold calculation."""
        if not self.actual_outcomes:
            return {}
        recent = list(self.actual_outcomes)[-20:]
        wins = sum(1 for o in recent if o.get('profitable'))
        total = len(recent)
        return {
            'win_rate': wins / total if total else 0,
            'total_trades': total,
            'total_profit': sum(o.get('profit_loss', 0) for o in recent),
            'training_samples': len(self.training_features),
            'is_trained': self.is_trained,
        }
