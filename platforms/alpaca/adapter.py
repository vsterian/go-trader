"""
Alpaca ExchangeAdapter — alpaca-py wrapper for US stock trading.
Supports paper and live modes via endpoint URL configuration.
Paper: https://paper-api.alpaca.markets  (default)
Live:  https://api.alpaca.markets

Env vars: ALPACA_PUBLIC_KEY, ALPACA_SECRET_KEY
"""

import os
import math
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional


PAPER_BASE_URL = "https://paper-api.alpaca.markets"
LIVE_BASE_URL = "https://api.alpaca.markets"

# Timeframe mapping: go-trader style → Alpaca TimeFrame
_TF_MAP = {
    "1m": "1Min",
    "5m": "5Min",
    "15m": "15Min",
    "30m": "30Min",
    "1h": "1Hour",
    "4h": "4Hour",
    "1d": "1Day",
    "1w": "1Week",
}


def _get_trading_client(api_key, secret_key, paper=True):
    from alpaca.trading.client import TradingClient
    return TradingClient(api_key, secret_key, paper=paper)


def _get_data_client(api_key, secret_key):
    from alpaca.data.historical import StockHistoricalDataClient
    return StockHistoricalDataClient(api_key, secret_key)


class AlpacaExchangeAdapter:
    """
    ExchangeAdapter for Alpaca — US stock trading (paper + live).
    """

    def __init__(self, mode="paper"):
        self._api_key = os.environ.get("ALPACA_PUBLIC_KEY", "")
        self._secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
        self._mode = mode
        self._paper = mode != "live"

        if self._api_key and self._secret_key:
            self._trading_client = _get_trading_client(
                self._api_key, self._secret_key, paper=self._paper
            )
            self._data_client = _get_data_client(self._api_key, self._secret_key)
        else:
            self._trading_client = None
            self._data_client = None

    @property
    def is_live(self) -> bool:
        return self._mode == "live"

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def name(self) -> str:
        return "alpaca"

    # ─────────────────────────────────────────────
    # Market data
    # ─────────────────────────────────────────────

    def get_spot_price(self, symbol: str) -> float:
        """Fetch current price for a stock symbol via latest trade."""
        if not self._data_client:
            return 0.0
        try:
            from alpaca.data.requests import StockLatestTradeRequest
            req = StockLatestTradeRequest(symbol_or_symbols=symbol)
            trades = self._data_client.get_stock_latest_trade(req)
            if symbol in trades:
                return float(trades[symbol].price)
            return 0.0
        except Exception:
            return 0.0

    def get_ohlcv(self, symbol: str, interval: str = "1h", limit: int = 200) -> list:
        """
        Fetch historical OHLCV bars.
        Returns list of [timestamp_ms, open, high, low, close, volume].
        """
        if not self._data_client:
            return []
        try:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

            tf_str = _TF_MAP.get(interval, "1Hour")
            tf = _parse_timeframe(tf_str)

            end = datetime.now(timezone.utc)
            # Estimate start time based on interval and limit
            if "Min" in tf_str:
                mins = int(tf_str.replace("Min", "")) if tf_str[0].isdigit() else 1
                start = end - timedelta(minutes=mins * limit * 1.5)
            elif "Hour" in tf_str:
                hours = int(tf_str.replace("Hour", "")) if tf_str[0].isdigit() else 1
                start = end - timedelta(hours=hours * limit * 1.5)
            elif "Day" in tf_str:
                start = end - timedelta(days=limit * 2)
            elif "Week" in tf_str:
                start = end - timedelta(weeks=limit * 2)
            else:
                start = end - timedelta(days=limit * 2)

            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=tf,
                start=start,
                end=end,
                limit=limit,
                feed="iex",
            )
            bars_set = self._data_client.get_stock_bars(req)

            candles = []
            if symbol in bars_set.data:
                for bar in bars_set.data[symbol]:
                    ts_ms = int(bar.timestamp.timestamp() * 1000)
                    candles.append([
                        ts_ms,
                        float(bar.open),
                        float(bar.high),
                        float(bar.low),
                        float(bar.close),
                        int(bar.volume),
                    ])
            return candles[-limit:] if len(candles) > limit else candles
        except Exception:
            return []

    # ─────────────────────────────────────────────
    # Account & positions
    # ─────────────────────────────────────────────

    def get_balance(self) -> float:
        """Get available buying power in USD."""
        if not self._trading_client:
            raise RuntimeError("get_balance requires API keys (set ALPACA_PUBLIC_KEY)")
        account = self._trading_client.get_account()
        return float(account.buying_power)

    def get_account_info(self) -> dict:
        """Get full account info."""
        if not self._trading_client:
            raise RuntimeError("get_account_info requires API keys")
        account = self._trading_client.get_account()
        return {
            "id": str(account.id),
            "cash": float(account.cash),
            "buying_power": float(account.buying_power),
            "portfolio_value": float(account.portfolio_value),
            "pattern_day_trader": account.pattern_day_trader,
            "daytrade_count": int(account.daytrade_count),
        }

    def get_positions(self) -> list:
        """Get all open positions."""
        if not self._trading_client:
            raise RuntimeError("get_positions requires API keys")
        positions = self._trading_client.get_all_positions()
        result = []
        for pos in positions:
            result.append({
                "symbol": pos.symbol,
                "qty": float(pos.qty),
                "avg_entry_price": float(pos.avg_entry_price),
                "market_value": float(pos.market_value),
                "cost_basis": float(pos.cost_basis),
                "unrealized_pl": float(pos.unrealized_pl),
                "current_price": float(pos.current_price),
                "side": str(pos.side),
            })
        return result

    def get_position(self, symbol: str) -> Optional[dict]:
        """Get position for a specific symbol."""
        if not self._trading_client:
            return None
        try:
            pos = self._trading_client.get_open_position(symbol)
            return {
                "symbol": pos.symbol,
                "qty": float(pos.qty),
                "avg_entry_price": float(pos.avg_entry_price),
                "market_value": float(pos.market_value),
                "cost_basis": float(pos.cost_basis),
                "unrealized_pl": float(pos.unrealized_pl),
                "current_price": float(pos.current_price),
                "side": str(pos.side),
            }
        except Exception:
            return None

    # ─────────────────────────────────────────────
    # Order sizing
    # ─────────────────────────────────────────────

    def is_fractionable(self, symbol: str) -> bool:
        """Check if a symbol supports fractional shares."""
        if not self._trading_client:
            return False
        try:
            asset = self._trading_client.get_asset(symbol)
            return getattr(asset, "fractionable", False)
        except Exception:
            return False

    def validate_order(self, symbol: str, size: float, price: float) -> Tuple[float, str]:
        """
        Validate and adjust order size.
        For non-fractionable stocks: rounds to whole shares.
        Returns (adjusted_size, error_message). error_message is empty on success.
        """
        if size <= 0:
            return 0, "size must be positive"
        if price <= 0:
            return 0, "price must be positive"

        fractionable = self.is_fractionable(symbol)

        if not fractionable:
            size = math.floor(size)
            if size < 1:
                return 0, f"need at least 1 share (${price:.2f}), insufficient funds"
        else:
            # Round to 2 decimal places for fractional
            size = math.floor(size * 100) / 100
            if size < 0.01:
                return 0, "minimum fractional order is 0.01 shares"

        notional = size * price
        if notional < 1.0:
            return 0, f"order value ${notional:.2f} below $1.00 minimum"

        return size, ""

    # ─────────────────────────────────────────────
    # Live order execution
    # ─────────────────────────────────────────────

    def market_buy(self, symbol: str, qty: float) -> dict:
        """Place a market buy order."""
        if not self._trading_client:
            raise RuntimeError("market_buy requires API keys (set ALPACA_PUBLIC_KEY, ALPACA_SECRET_KEY)")

        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        order = self._trading_client.submit_order(req)
        return self._order_to_dict(order)

    def market_sell(self, symbol: str, qty: float) -> dict:
        """Place a market sell order."""
        if not self._trading_client:
            raise RuntimeError("market_sell requires API keys (set ALPACA_PUBLIC_KEY, ALPACA_SECRET_KEY)")

        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        order = self._trading_client.submit_order(req)
        return self._order_to_dict(order)

    # ─────────────────────────────────────────────
    # Market hours
    # ─────────────────────────────────────────────

    def is_market_open(self) -> bool:
        """Check if the US stock market is currently open."""
        if not self._trading_client:
            return False
        try:
            clock = self._trading_client.get_clock()
            return clock.is_open
        except Exception:
            return False

    # ─────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────

    @staticmethod
    def _order_to_dict(order) -> dict:
        """Convert Alpaca Order object to dict."""
        result = {
            "id": str(order.id),
            "symbol": order.symbol,
            "side": str(order.side),
            "type": str(order.type),
            "status": str(order.status),
            "qty": float(order.qty) if order.qty else 0,
        }
        if order.filled_qty:
            result["filled_qty"] = float(order.filled_qty)
        if order.filled_avg_price:
            result["filled_avg_price"] = float(order.filled_avg_price)
        return result


def _parse_timeframe(tf_str: str):
    """Parse timeframe string to Alpaca TimeFrame."""
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    if tf_str == "1Min":
        return TimeFrame.Minute
    elif tf_str == "5Min":
        return TimeFrame(5, TimeFrameUnit.Minute)
    elif tf_str == "15Min":
        return TimeFrame(15, TimeFrameUnit.Minute)
    elif tf_str == "30Min":
        return TimeFrame(30, TimeFrameUnit.Minute)
    elif tf_str == "1Hour":
        return TimeFrame.Hour
    elif tf_str == "4Hour":
        return TimeFrame(4, TimeFrameUnit.Hour)
    elif tf_str == "1Day":
        return TimeFrame.Day
    elif tf_str == "1Week":
        return TimeFrame.Week
    else:
        return TimeFrame.Day
