#!/usr/bin/env python3
"""
Alpaca stock strategy check script.
Fetches OHLCV via Alpaca API, runs strategy, outputs JSON to stdout, exits.

Signal check mode (paper or live):
    check_alpaca.py <strategy> <symbol> <timeframe> [--mode=paper|live]

Execution mode (called by Go as phase 2):
    check_alpaca.py --execute --symbol=AAPL --side=buy --amount_usd=950 [--mode=paper|live]
    check_alpaca.py --execute --symbol=AAPL --side=sell --quantity=10 [--mode=paper|live]
"""

import sys
import os
import json
import traceback
from datetime import datetime, timezone

# Add paths: platforms/alpaca/ for adapter, shared_strategies/spot/ for apply_strategy,
# shared_tools/ for utilities.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'platforms', 'alpaca'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared_strategies', 'spot'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared_tools'))


def _make_dataframe(candles):
    """Convert raw OHLCV list to pandas DataFrame compatible with strategy functions."""
    import pandas as pd
    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("datetime")
    df.sort_index(inplace=True)
    return df


def run_signal_check(strategy_name, symbol, timeframe, mode, htf_filter_enabled=False):
    """Run strategy signal check using Alpaca OHLCV data."""
    try:
        from adapter import AlpacaExchangeAdapter
        from strategies import apply_strategy, get_strategy

        get_strategy(strategy_name)

        adapter = AlpacaExchangeAdapter(mode=mode)

        print(f"Fetching {symbol} {timeframe} from Alpaca ({mode})...", file=sys.stderr)
        candles = adapter.get_ohlcv(symbol, interval=timeframe, limit=200)

        if not candles or len(candles) < 30:
            print(json.dumps({
                "strategy": strategy_name,
                "symbol": symbol,
                "timeframe": timeframe,
                "signal": 0,
                "price": 0,
                "indicators": {},
                "mode": mode,
                "platform": "alpaca",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": f"Insufficient data: {len(candles) if candles else 0} candles",
            }))
            sys.exit(1)

        df = _make_dataframe(candles)
        result_df = apply_strategy(strategy_name, df)

        last = result_df.iloc[-1]
        signal = int(last.get("signal", 0))
        if signal > 0:
            signal = 1
        elif signal < 0:
            signal = -1
        else:
            signal = 0

        price = float(last["close"])

        # Apply HTF trend filter if enabled
        htf_info = {}
        if htf_filter_enabled and strategy_name != "delta_neutral_funding":
            from htf_filter import htf_trend_filter, apply_htf_filter

            def _fetch_htf(sym, tf, limit):
                candles = adapter.get_ohlcv(sym, interval=tf, limit=limit)
                return _make_dataframe(candles) if candles else None

            htf_info = htf_trend_filter(symbol, timeframe, _fetch_htf)
            original_signal = signal
            signal = apply_htf_filter(signal, htf_info.get("htf_trend", 0))
            if signal != original_signal:
                print(f"HTF filter: {original_signal} → {signal} (HTF trend={htf_info.get('htf_trend')})", file=sys.stderr)

        # Freshen price with live quote
        try:
            live_price = adapter.get_spot_price(symbol)
            if live_price > 0:
                price = live_price
        except Exception:
            pass

        indicators = {}
        skip_cols = {
            "open", "high", "low", "close", "volume",
            "timestamp", "signal", "position", "datetime",
        }
        for col in result_df.columns:
            if col in skip_cols:
                continue
            val = last.get(col)
            if val is not None:
                try:
                    indicators[col] = round(float(val), 6)
                except (ValueError, TypeError):
                    pass

        if htf_info:
            for k, v in htf_info.items():
                if isinstance(v, (int, float)):
                    indicators[k] = v

        print(json.dumps({
            "strategy": strategy_name,
            "symbol": symbol,
            "timeframe": timeframe,
            "signal": signal,
            "price": round(price, 2),
            "indicators": indicators,
            "mode": mode,
            "platform": "alpaca",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }))

    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({
            "strategy": strategy_name,
            "symbol": symbol,
            "timeframe": timeframe,
            "signal": 0,
            "price": 0,
            "indicators": {},
            "mode": mode,
            "platform": "alpaca",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        }))
        sys.exit(1)


def run_execute(symbol, side, amount_usd, quantity, mode):
    """Place a stock order on Alpaca."""
    try:
        from adapter import AlpacaExchangeAdapter
        adapter = AlpacaExchangeAdapter(mode=mode)

        is_buy = side.lower() == "buy"

        if is_buy:
            # Get current price and calculate shares
            price = adapter.get_spot_price(symbol)
            if price <= 0:
                raise ValueError(f"Could not get price for {symbol}")

            # Calculate shares from amount_usd
            if amount_usd <= 0:
                # Balance-based: use available buying power
                buying_power = adapter.get_balance()
                amount_usd = buying_power * 0.95

            raw_shares = amount_usd / price
            shares, err = adapter.validate_order(symbol, raw_shares, price)
            if err:
                raise ValueError(f"Order validation failed: {err}")

            print(f"Buying {shares} shares of {symbol} at ~${price:.2f} (${amount_usd:.2f})", file=sys.stderr)
            result = adapter.market_buy(symbol, shares)
        else:
            # Sell mode: use quantity
            if quantity <= 0:
                # Get current position
                pos = adapter.get_position(symbol)
                if not pos:
                    raise ValueError(f"No position in {symbol} to sell")
                quantity = pos["qty"]

            print(f"Selling {quantity} shares of {symbol}", file=sys.stderr)
            result = adapter.market_sell(symbol, quantity)

        # Extract fill info
        fill = {}
        if result:
            avg_px = result.get("filled_avg_price", 0) or 0
            filled_qty = result.get("filled_qty", 0) or 0
            if avg_px > 0:
                fill = {"avg_px": float(avg_px), "total_sz": float(filled_qty)}

        execution = {
            "action": "buy" if is_buy else "sell",
            "symbol": symbol,
            "fill": fill,
        }
        if is_buy:
            execution["amount_usd"] = amount_usd
        else:
            execution["quantity"] = quantity

        print(json.dumps({
            "execution": execution,
            "platform": "alpaca",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }))

    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({
            "execution": None,
            "platform": "alpaca",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        }))
        sys.exit(1)


def main():
    if "--execute" in sys.argv:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--symbol", required=True)
        parser.add_argument("--side", required=True, choices=["buy", "sell"])
        parser.add_argument("--amount_usd", type=float, default=0)
        parser.add_argument("--quantity", type=float, default=0)
        parser.add_argument("--mode", default="paper")
        args = parser.parse_args()
        run_execute(args.symbol, args.side, args.amount_usd, args.quantity, args.mode)
    else:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("strategy")
        parser.add_argument("symbol")
        parser.add_argument("timeframe")
        parser.add_argument("--mode", default="paper")
        parser.add_argument("--htf-filter", action="store_true", default=False)
        # ML flags (passthrough to strategy check)
        parser.add_argument("--ml-enabled", action="store_true", default=False)
        parser.add_argument("--profit-pct", type=float, default=0)
        parser.add_argument("--ml-buy-base", type=float, default=0.30)
        parser.add_argument("--ml-sell-base", type=float, default=0.70)
        args = parser.parse_args()
        run_signal_check(args.strategy, args.symbol, args.timeframe, args.mode, args.htf_filter)


if __name__ == "__main__":
    main()
