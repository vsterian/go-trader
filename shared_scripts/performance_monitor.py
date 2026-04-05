"""
Performance monitor for strategy trade tracking and degradation detection.

Ported from dockertradingbot/performance_monitor.py.
Adapted for go-trader's stateless subprocess model with JSON file persistence.
"""

import json
import os
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', 'models')


class PerformanceMonitor:
    def __init__(self, strategy_id, symbol, model_dir=None):
        self.strategy_id = strategy_id
        self.symbol = symbol
        self._model_dir = model_dir or MODEL_DIR
        self.trades = []
        self.metrics = {
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0.0,
            'profit_factor': 0.0,
            'max_drawdown_pct': 0.0,
            'avg_profit_pct': 0.0,
            'cumulative_profit': 0.0,
            'last_optimized': None,
        }
        self._load_metrics()

    def _metrics_path(self):
        return os.path.join(self._model_dir, f'{self.strategy_id}_metrics.json')

    def _load_metrics(self):
        path = self._metrics_path()
        try:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    data = json.load(f)
                self.trades = data.get('trades', [])
                self.metrics.update(data.get('metrics', {}))
        except Exception as e:
            logger.error(f"[{self.strategy_id}] Failed to load metrics: {e}")

    def _save_metrics(self):
        os.makedirs(self._model_dir, exist_ok=True)
        try:
            with open(self._metrics_path(), 'w') as f:
                json.dump({
                    'trades': self.trades[-200:],  # keep last 200 trades
                    'metrics': self.metrics,
                }, f, indent=2)
        except Exception as e:
            logger.error(f"[{self.strategy_id}] Failed to save metrics: {e}")

    def record_trade(self, trade_data):
        """Record a completed trade and update metrics.

        Args:
            trade_data: dict with at least 'pnl' (float, profit %) and
                        optionally 'profitable' (bool), 'timestamp' (str).
        """
        self.trades.append(trade_data)
        self._update_metrics()
        self._save_metrics()

    def _update_metrics(self):
        if not self.trades:
            return
        total = len(self.trades)
        wins = sum(1 for t in self.trades if t.get('pnl', 0) > 0)
        losses = total - wins
        gross_profit = sum(t['pnl'] for t in self.trades if t.get('pnl', 0) > 0)
        gross_loss = abs(sum(t['pnl'] for t in self.trades if t.get('pnl', 0) < 0))

        # Equity curve for drawdown
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in self.trades:
            equity += t.get('pnl', 0)
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd

        self.metrics.update({
            'total_trades': total,
            'wins': wins,
            'losses': losses,
            'win_rate': wins / total if total > 0 else 0.0,
            'profit_factor': gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0.0,
            'max_drawdown_pct': max_dd,
            'avg_profit_pct': sum(t.get('pnl', 0) for t in self.trades) / total if total > 0 else 0.0,
            'cumulative_profit': sum(t.get('pnl', 0) for t in self.trades),
        })

    def should_adapt(self):
        """Check if strategy needs re-optimization.

        Returns True if:
        1. >= 10 total trades AND
        2. Rolling 20-trade win rate degraded >15% from historical average
        3. OR >24 hours since last optimization
        """
        if self.metrics['total_trades'] < 10:
            return False

        # Check performance degradation
        recent = self.trades[-20:]
        if len(recent) >= 10:
            recent_wr = sum(1 for t in recent if t.get('pnl', 0) > 0) / len(recent)
            historical_wr = self.metrics.get('win_rate', 0.5)
            degradation = (historical_wr - recent_wr) * 0.6
            if degradation > 0.15:
                return True

        # Check time since last optimization
        last_opt = self.metrics.get('last_optimized')
        if last_opt:
            try:
                elapsed = datetime.now() - datetime.fromisoformat(last_opt)
                if elapsed > timedelta(hours=24):
                    return True
            except (ValueError, TypeError):
                pass

        return False

    def get_degradation_reason(self):
        """Return reason string for why adaptation is needed."""
        recent = self.trades[-20:]
        if len(recent) >= 10:
            recent_wr = sum(1 for t in recent if t.get('pnl', 0) > 0) / len(recent)
            historical_wr = self.metrics.get('win_rate', 0.5)
            degradation = (historical_wr - recent_wr) * 0.6
            if degradation > 0.15:
                return f"win_rate_degraded (recent={recent_wr:.1%}, historical={historical_wr:.1%})"
        return "time_based (>24h since last optimization)"

    def get_current_metrics(self):
        self._update_metrics()
        return dict(self.metrics)

    def mark_optimized(self):
        """Mark that optimization was performed."""
        self.metrics['last_optimized'] = datetime.now().isoformat()
        self._save_metrics()
