#!/usr/bin/env python3
"""
Adaptation check — determines if a strategy needs re-optimization.

Usage: python3 check_adaptation.py <strategy_id> <symbol> <timeframe> [--force]

Output: JSON with needs_adaptation, reason, current_metrics, suggestion.
"""

import json
import os
import sys
import logging

logger = logging.getLogger(__name__)

_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _script_dir)
sys.path.insert(0, os.path.join(_script_dir, '..', 'shared_tools'))

from performance_monitor import PerformanceMonitor


def check_adaptation(strategy_id, symbol, timeframe, force=False, model_dir=None):
    """Check if a strategy needs adaptation / re-optimization.

    Returns dict with:
    - needs_adaptation: bool
    - reason: str
    - current_metrics: dict
    - suggestion: str (what action to take)
    """
    _model_dir = model_dir or os.path.join(_script_dir, '..', 'models')
    pm = PerformanceMonitor(strategy_id, symbol, model_dir=_model_dir)
    metrics = pm.get_current_metrics()

    if force:
        return {
            'needs_adaptation': True,
            'reason': 'forced by user',
            'current_metrics': metrics,
            'suggestion': 're-optimize strategy parameters via walk-forward optimization',
        }

    if pm.should_adapt():
        reason = pm.get_degradation_reason()
        return {
            'needs_adaptation': True,
            'reason': reason,
            'current_metrics': metrics,
            'suggestion': 're-optimize strategy parameters via walk-forward optimization',
        }

    return {
        'needs_adaptation': False,
        'reason': 'performance within acceptable bounds',
        'current_metrics': metrics,
        'suggestion': 'no action needed',
    }


def main():
    if len(sys.argv) < 4:
        # Filter out flags for positional arg count check
        pos_args = [a for a in sys.argv[1:] if not a.startswith("--")]
        if len(pos_args) < 3:
            print(json.dumps({
                "error": "Usage: check_adaptation.py <strategy_id> <symbol> <timeframe> [--force]"
            }))
            sys.exit(1)

    force = "--force" in sys.argv
    pos_args = [a for a in sys.argv[1:] if not a.startswith("--")]

    strategy_id = pos_args[0]
    symbol = pos_args[1]
    timeframe = pos_args[2]

    result = check_adaptation(strategy_id, symbol, timeframe, force=force)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
