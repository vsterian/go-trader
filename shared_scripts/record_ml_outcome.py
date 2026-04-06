#!/usr/bin/env python3
"""
Record ML outcome for a completed trade.
Called by Go scheduler after a sell trade executes.

Usage: python3 shared_scripts/record_ml_outcome.py <strategy_id> <symbol> <profit_pct> <was_profitable>

Output: JSON {"recorded": true, "training_samples": N, "win_rate": 0.55}
"""

import json
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(_script_dir)
sys.path.insert(0, _script_dir)
sys.path.insert(0, os.path.join(_repo_root, 'shared_tools'))

from ml_signal_generator import MLSignalGenerator
from performance_monitor import PerformanceMonitor


def main():
    if len(sys.argv) < 5:
        print(json.dumps({"error": "Usage: record_ml_outcome.py <strategy_id> <symbol> <profit_pct> <was_profitable>"}))
        sys.exit(1)

    strategy_id = sys.argv[1]
    symbol = sys.argv[2]
    profit_pct = float(sys.argv[3])
    was_profitable = sys.argv[4].lower() in ('true', '1', 'yes')

    model_dir = os.path.join(_repo_root, 'models')

    # Record outcome in ML generator
    ml = MLSignalGenerator(symbol=symbol, model_dir=model_dir)
    ml.record_outcome(was_profitable)

    # Record trade in performance monitor
    pm = PerformanceMonitor(strategy_id, symbol, model_dir=model_dir)
    pm.record_trade({'pnl': profit_pct, 'profitable': was_profitable})

    stats = ml.get_performance_stats()
    result = {
        "recorded": True,
        "training_samples": stats.get('total_predictions', 0),
        "win_rate": pm.metrics.get('win_rate', 0.0),
        "total_trades": pm.metrics.get('total_trades', 0),
    }
    print(json.dumps(result))


if __name__ == '__main__':
    main()
