#!/usr/bin/env python3
"""
Stateless spot strategy check script.
Fetches data, runs strategy, outputs JSON to stdout, exits.

Usage: python3 check_strategy.py <strategy> <symbol> <timeframe> [symbol_b]

  symbol_b  Optional second asset symbol for pairs_spread (e.g. ETH/USDT).
            When provided, close prices of symbol_b are merged into the
            dataframe as the 'close_b' column so the strategy runs proper
            stat-arb.  Without it, pairs_spread degrades to self-mean-reversion.
"""

import sys
import os
import json
import traceback
from datetime import datetime, timezone

# Add parent dirs to path so we can import from strategies/ and core/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared_strategies', 'spot'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared_tools'))


def main():
    # Parse optional flags from argv before positional args
    htf_filter_enabled = "--htf-filter" in sys.argv
    ml_enabled = "--ml-enabled" in sys.argv
    positional_args = [a for a in sys.argv[1:] if not a.startswith("--")]

    # Extract key=value flags
    def _flag_val(name, default=None):
        prefix = f"--{name}="
        for a in sys.argv[1:]:
            if a.startswith(prefix):
                return a[len(prefix):]
        return default

    ml_profit_pct = float(_flag_val("profit-pct", "0.0"))
    ml_buy_base = float(_flag_val("ml-buy-base", "0.30"))
    ml_sell_base = float(_flag_val("ml-sell-base", "0.70"))

    if len(positional_args) < 3:
        print(json.dumps({
            "error": f"Usage: {sys.argv[0]} <strategy> <symbol> <timeframe> [symbol_b] [--htf-filter]"
        }))
        sys.exit(1)

    strategy_name = positional_args[0]
    symbol = positional_args[1]
    timeframe = positional_args[2]
    symbol_b = positional_args[3] if len(positional_args) >= 4 else None

    try:
        from strategies import apply_strategy, get_strategy
        from data_fetcher import fetch_ohlcv

        # Verify strategy exists
        get_strategy(strategy_name)

        # Warn when pairs_spread will degrade due to missing secondary symbol
        if strategy_name == "pairs_spread" and not symbol_b:
            print(
                "Warning: pairs_spread requires a secondary symbol (symbol_b); "
                "degrading to self-mean-reversion. Pass a 4th argument to enable "
                "proper stat-arb (e.g. ETH/USDT for a BTC/USDT primary).",
                file=sys.stderr,
            )

        # Fetch primary data
        print(f"Fetching {symbol} {timeframe}...", file=sys.stderr)
        df = fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=200, store=False)

        # Fetch and merge secondary data for pairs strategies
        if strategy_name == "pairs_spread" and symbol_b:
            print(f"Fetching secondary {symbol_b} {timeframe}...", file=sys.stderr)
            df_b = fetch_ohlcv(symbol=symbol_b, timeframe=timeframe, limit=200, store=False)
            if df_b.empty:
                print(json.dumps({
                    "strategy": strategy_name,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "signal": 0,
                    "price": 0,
                    "indicators": {},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": f"No data returned for secondary symbol {symbol_b}",
                }))
                sys.exit(1)
            # Inner join on datetime index so both assets have the same timestamps
            df = df.join(df_b[["close"]].rename(columns={"close": "close_b"}), how="inner")
            print(f"Merged pair: {len(df)} aligned candles ({symbol} / {symbol_b})", file=sys.stderr)

        if df.empty or len(df) < 30:
            print(json.dumps({
                "strategy": strategy_name,
                "symbol": symbol,
                "timeframe": timeframe,
                "signal": 0,
                "price": 0,
                "indicators": {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": f"Insufficient data: {len(df)} candles"
            }))
            return

        # Run the strategy
        result_df = apply_strategy(strategy_name, df)

        # Get the last row's signal
        last = result_df.iloc[-1]
        signal = int(last.get("signal", 0))
        # Clamp to -1, 0, 1
        if signal > 0:
            signal = 1
        elif signal < 0:
            signal = -1
        else:
            signal = 0

        price = float(last["close"])

        # Apply HTF trend filter if enabled (skip for funding-rate strategies — #103)
        htf_info = {}
        if htf_filter_enabled and strategy_name != "delta_neutral_funding":
            from htf_filter import htf_trend_filter, apply_htf_filter

            def _fetch_htf(sym, tf, limit):
                return fetch_ohlcv(symbol=sym, timeframe=tf, limit=limit, store=False)

            htf_info = htf_trend_filter(symbol, timeframe, _fetch_htf)
            original_signal = signal
            signal = apply_htf_filter(signal, htf_info.get("htf_trend", 0))
            if signal != original_signal:
                print(f"HTF filter: {original_signal} → {signal} (HTF trend={htf_info.get('htf_trend')})", file=sys.stderr)

        # ── ML signal enhancement (opt-in) ────────────────────────────────
        ml_block = None
        if ml_enabled:
            try:
                from ml_signal_generator import MLSignalGenerator
                from dynamic_thresholds import (
                    calculate_dynamic_buy_threshold,
                    calculate_dynamic_sell_threshold,
                )
                from indicators import calculate_adx

                ml = MLSignalGenerator(symbol=symbol, model_dir=os.path.join(
                    os.path.dirname(__file__), '..', 'models'))

                # Gather indicator values from strategy output
                rsi = float(last.get('rsi', 50))
                adx_val = float(last.get('adx', 20))
                upper_band = float(last.get('bb_upper', last.get('upper_band', price * 1.02)))
                lower_band = float(last.get('bb_lower', last.get('lower_band', price * 0.98)))
                rsi_threshold_buy = 30
                rsi_threshold_sell = 70
                adx_threshold = 25

                # If ADX not in strategy output, compute it from data
                if 'adx' not in [c.lower() for c in result_df.columns]:
                    try:
                        adx_series = calculate_adx(result_df)
                        adx_val = float(adx_series.iloc[-1]) if not adx_series.empty else 20
                    except Exception:
                        adx_val = 20

                stats = ml.get_performance_stats()
                stats['is_trained'] = ml.is_trained

                # Dynamic thresholds
                buy_thresh = calculate_dynamic_buy_threshold(
                    stats, price, rsi, adx_val, lower_band, upper_band,
                    rsi_threshold_buy, adx_threshold,
                )
                sell_thresh = calculate_dynamic_sell_threshold(
                    stats, price, rsi, adx_val, upper_band,
                    current_profit_pct=ml_profit_pct,
                    rsi_threshold_sell=rsi_threshold_sell,
                    adx_threshold=adx_threshold,
                )

                # ML predictions
                buy_prob = ml.predict_buy_signal(
                    price, rsi, adx_val, lower_band, upper_band,
                    rsi_threshold_buy, rsi_threshold_sell, adx_threshold,
                )
                sell_prob = ml.predict_sell_signal(
                    price, rsi, adx_val, upper_band, lower_band,
                    rsi_threshold_sell, rsi_threshold_buy, adx_threshold,
                    current_profit_loss=ml_profit_pct,
                )

                # Apply ML to rule signal
                rule_signal = signal
                strong_mult = 1.5

                if signal == 1:
                    # Rule says BUY — ML must agree
                    if buy_prob < buy_thresh:
                        signal = 0  # ML blocks the buy
                        print(f"ML: blocked BUY (prob={buy_prob:.3f} < thresh={buy_thresh:.3f})", file=sys.stderr)
                elif signal == -1:
                    # Rule says SELL — ML must agree
                    if sell_prob < sell_thresh:
                        signal = 0  # ML blocks the sell
                        print(f"ML: blocked SELL (prob={sell_prob:.3f} < thresh={sell_thresh:.3f})", file=sys.stderr)
                elif signal == 0:
                    # No rule signal — check for strong ML override
                    if buy_prob > buy_thresh * strong_mult:
                        signal = 1  # Strong ML buy
                        print(f"ML: strong BUY override (prob={buy_prob:.3f})", file=sys.stderr)
                    elif sell_prob > sell_thresh * strong_mult:
                        signal = -1  # Strong ML sell
                        print(f"ML: strong SELL override (prob={sell_prob:.3f})", file=sys.stderr)

                ml_block = {
                    "enabled": True,
                    "buy_probability": round(buy_prob, 4),
                    "sell_probability": round(sell_prob, 4),
                    "rule_signal": rule_signal,
                    "dynamic_buy_threshold": round(buy_thresh, 4),
                    "dynamic_sell_threshold": round(sell_thresh, 4),
                    "model_trained": ml.is_trained,
                    "training_samples": len(ml.training_features),
                }
            except Exception as e:
                print(f"ML enhancement error: {e}", file=sys.stderr)
                ml_block = {"enabled": True, "error": str(e)}

        # Collect relevant indicators
        indicators = {}
        indicator_cols = [c for c in result_df.columns
                         if c not in ("open", "high", "low", "close", "close_b", "volume",
                                      "timestamp", "signal", "position", "datetime")]
        for col in indicator_cols:
            val = last.get(col)
            if val is not None:
                try:
                    indicators[col] = round(float(val), 6)
                except (ValueError, TypeError):
                    pass

        # Merge HTF indicators
        if htf_info:
            for k, v in htf_info.items():
                if isinstance(v, (int, float)):
                    indicators[k] = v

        output = {
            "strategy": strategy_name,
            "symbol": symbol,
            "timeframe": timeframe,
            "signal": signal,
            "price": round(price, 2),
            "indicators": indicators,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        if ml_block is not None:
            output["ml"] = ml_block
        print(json.dumps(output))

    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({
            "strategy": strategy_name,
            "symbol": symbol,
            "timeframe": timeframe,
            "signal": 0,
            "price": 0,
            "indicators": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }))
        sys.exit(1)  # Exit 1; Go will still parse the JSON error field


if __name__ == "__main__":
    main()
