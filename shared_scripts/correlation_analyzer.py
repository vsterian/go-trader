#!/usr/bin/env python3
"""
Correlation analyzer — checks if a new position is too correlated with existing ones.

Usage: python3 correlation_analyzer.py <new_symbol> '<existing_symbols_json>'

Output: JSON {"symbol": "ETH/USDC", "blocked": true/false, "reason": "...", "correlations": {...}}
"""

import json
import os
import sys
import time
import logging

logger = logging.getLogger(__name__)

_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_script_dir, '..', 'shared_tools'))

CORRELATION_THRESHOLD = 0.70
CACHE_TTL_SECONDS = 6 * 3600  # 6 hours

# Simple in-memory cache (per process invocation, reloaded from disk)
_CACHE_FILE = os.path.join(_script_dir, '..', 'models', 'correlation_cache.json')


def _load_cache():
    try:
        if os.path.exists(_CACHE_FILE):
            with open(_CACHE_FILE, 'r') as f:
                data = json.load(f)
            now = time.time()
            return {k: v for k, v in data.items() if now - v.get('ts', 0) < CACHE_TTL_SECONDS}
    except Exception:
        pass
    return {}


def _save_cache(cache):
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, 'w') as f:
            json.dump(cache, f)
    except Exception:
        pass


def compute_correlation(symbol_a, symbol_b, days=30, timeframe='1d'):
    """Compute return correlation between two symbols over the last N days."""
    cache = _load_cache()
    key = f"{symbol_a}|{symbol_b}"
    key_rev = f"{symbol_b}|{symbol_a}"
    if key in cache:
        return cache[key]['value']
    if key_rev in cache:
        return cache[key_rev]['value']

    try:
        from data_fetcher import fetch_ohlcv
        import numpy as np

        limit = days + 5
        df_a = fetch_ohlcv(symbol=symbol_a, timeframe=timeframe, limit=limit, store=False)
        df_b = fetch_ohlcv(symbol=symbol_b, timeframe=timeframe, limit=limit, store=False)

        if df_a.empty or df_b.empty or len(df_a) < 10 or len(df_b) < 10:
            return 0.0

        # Align on datetime index
        merged = df_a[['close']].rename(columns={'close': 'a'}).join(
            df_b[['close']].rename(columns={'close': 'b'}), how='inner'
        )
        if len(merged) < 10:
            return 0.0

        returns_a = merged['a'].pct_change().dropna()
        returns_b = merged['b'].pct_change().dropna()

        if len(returns_a) < 5:
            return 0.0

        corr = float(np.corrcoef(returns_a.values, returns_b.values)[0, 1])
        if np.isnan(corr):
            corr = 0.0

        # Cache result
        cache[key] = {'value': corr, 'ts': time.time()}
        _save_cache(cache)
        return corr
    except Exception as e:
        logger.error(f"Correlation computation failed for {symbol_a}/{symbol_b}: {e}")
        return 0.0


def check_correlation(new_symbol, existing_symbols, threshold=CORRELATION_THRESHOLD):
    """Check if a new position is too correlated with existing positions.

    Returns dict with 'blocked', 'reason', 'correlations'.
    """
    if not existing_symbols:
        return {
            'symbol': new_symbol,
            'blocked': False,
            'reason': 'no existing positions',
            'correlations': {},
        }

    correlations = {}
    blocked = False
    reason = ''

    for sym in existing_symbols:
        if sym == new_symbol:
            continue
        corr = compute_correlation(new_symbol, sym)
        correlations[sym] = round(corr, 4)
        if abs(corr) >= threshold:
            blocked = True
            reason = f"High correlation with {sym} ({corr:.2f})"

    return {
        'symbol': new_symbol,
        'blocked': blocked,
        'reason': reason if blocked else 'correlation within bounds',
        'correlations': correlations,
    }


def main():
    if len(sys.argv) < 3:
        print(json.dumps({
            "error": "Usage: correlation_analyzer.py <new_symbol> '<existing_symbols_json>'"
        }))
        sys.exit(1)

    new_symbol = sys.argv[1]
    try:
        existing = json.loads(sys.argv[2])
    except json.JSONDecodeError:
        existing = []

    result = check_correlation(new_symbol, existing)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
