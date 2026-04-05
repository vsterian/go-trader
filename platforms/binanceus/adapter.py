"""
BinanceUS ExchangeAdapter — ccxt wrapper for spot trading.
Supports live order placement when BINANCE_API_KEY and BINANCE_API_SECRET
are set as environment variables.
Options methods raise NotImplementedError (BinanceUS is spot-only).
"""

import sys
import os as _os
import math
from decimal import Decimal
from typing import Tuple

sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..', 'shared_tools'))


def _get_ccxt_exchange(authenticated=False):
    try:
        import ccxt
    except ImportError:
        return None
    config = {"enableRateLimit": True}
    if authenticated:
        api_key = _os.environ.get("BINANCE_API_KEY", "")
        api_secret = _os.environ.get("BINANCE_API_SECRET", "")
        if api_key and api_secret:
            config["apiKey"] = api_key
            config["secret"] = api_secret
    return ccxt.binanceus(config)


class BinanceUSExchangeAdapter:
    """
    ExchangeAdapter for BinanceUS — spot trading.
    Live mode is enabled when BINANCE_API_KEY and BINANCE_API_SECRET env vars are set.
    """

    MIN_NOTIONAL_FLOOR = 10.0  # Minimum order value in USD (Binance floor)

    def __init__(self):
        api_key = _os.environ.get("BINANCE_API_KEY", "")
        api_secret = _os.environ.get("BINANCE_API_SECRET", "")
        self._is_live = bool(api_key and api_secret)
        self._exchange = _get_ccxt_exchange(authenticated=self._is_live)
        self._markets_loaded = False

    @property
    def is_live(self) -> bool:
        return self._is_live

    @property
    def mode(self) -> str:
        return "live" if self._is_live else "paper"

    @property
    def name(self) -> str:
        return "binanceus"

    # ─────────────────────────────────────────────
    # Market data
    # ─────────────────────────────────────────────

    def _load_markets(self):
        if not self._markets_loaded:
            self._exchange.load_markets()
            self._markets_loaded = True

    def _resolve_pair(self, symbol: str) -> str:
        """Resolve underlying (e.g. 'BTC') to a tradeable pair (e.g. 'BTC/USDT')."""
        if "/" in symbol:
            return symbol
        for suffix in ("/USDT", "/USD", "/USDC"):
            pair = symbol + suffix
            self._load_markets()
            if pair in self._exchange.markets:
                return pair
        return symbol + "/USDT"

    def get_spot_price(self, underlying: str) -> float:
        """Fetch current spot price for underlying via BinanceUS."""
        for suffix in ("/USDT", "/USD", "/USDC"):
            try:
                ticker = self._exchange.fetch_ticker(underlying + suffix)
                price = ticker.get("last") or 0
                if price and price > 0:
                    return float(price)
            except Exception:
                continue
        return 0.0

    # ─────────────────────────────────────────────
    # Order sizing: min notional + lot size
    # ─────────────────────────────────────────────

    def get_min_notional(self, symbol: str) -> float:
        """Get minimum order value in USD for a pair. Falls back to MIN_NOTIONAL_FLOOR."""
        try:
            self._load_markets()
            pair = self._resolve_pair(symbol)
            market = self._exchange.markets.get(pair, {})
            limits = market.get("limits", {})
            cost_min = (limits.get("cost") or {}).get("min")
            if cost_min and float(cost_min) > 0:
                return max(float(cost_min), self.MIN_NOTIONAL_FLOOR)
        except Exception:
            pass
        return self.MIN_NOTIONAL_FLOOR

    def get_lot_size(self, symbol: str) -> dict:
        """Get lot size constraints: min_qty, max_qty, step_size."""
        defaults = {"min_qty": 0.00001, "max_qty": 9999999.0, "step_size": 0.00001}
        try:
            self._load_markets()
            pair = self._resolve_pair(symbol)
            market = self._exchange.markets.get(pair, {})
            limits = market.get("limits", {})
            precision = market.get("precision", {})
            amount_limits = limits.get("amount") or {}
            min_qty = amount_limits.get("min")
            max_qty = amount_limits.get("max")
            # step_size from precision
            amount_prec = precision.get("amount")
            if amount_prec is not None:
                step_size = 10 ** (-int(amount_prec))
            else:
                step_size = defaults["step_size"]
            return {
                "min_qty": float(min_qty) if min_qty else defaults["min_qty"],
                "max_qty": float(max_qty) if max_qty else defaults["max_qty"],
                "step_size": float(step_size),
            }
        except Exception:
            return defaults

    @staticmethod
    def round_step_size(quantity: float, step_size: float) -> float:
        """Round quantity down to the nearest step_size (lot size compliance)."""
        if step_size <= 0:
            return quantity
        step_dec = Decimal(str(step_size))
        qty_dec = Decimal(str(quantity))
        return float((qty_dec // step_dec) * step_dec)

    def validate_order(self, symbol: str, size: float, price: float) -> Tuple[float, str]:
        """
        Validate and adjust order size for min notional and lot size.
        Returns (adjusted_size, error_message). error_message is empty on success.
        """
        min_notional = self.get_min_notional(symbol)
        lot = self.get_lot_size(symbol)

        notional = size * price
        if notional < min_notional:
            size = min_notional / price

        if size > lot["max_qty"]:
            return 0, f"size {size} exceeds max qty {lot['max_qty']}"

        size = self.round_step_size(size, lot["step_size"])

        if size < lot["min_qty"]:
            size = lot["min_qty"]

        # Round up to next step if still below min notional after rounding down
        if size * price < min_notional:
            size += lot["step_size"]
            size = self.round_step_size(size, lot["step_size"])

        if size * price < min_notional:
            return 0, f"order value ${size * price:.2f} below min notional ${min_notional:.2f}"

        return size, ""

    # ─────────────────────────────────────────────
    # Balance
    # ─────────────────────────────────────────────

    def get_balance(self, asset: str = "USDT") -> float:
        """Fetch available (free) balance for an asset. Requires live mode."""
        if not self._is_live:
            raise RuntimeError("get_balance requires live mode (set BINANCE_API_KEY)")
        balance = self._exchange.fetch_balance()
        return float(balance.get("free", {}).get(asset, 0))

    # ─────────────────────────────────────────────
    # Live order execution
    # ─────────────────────────────────────────────

    def market_buy(self, symbol: str, size: float) -> dict:
        """Place a market buy order. Requires live mode."""
        if not self._is_live:
            raise RuntimeError("market_buy requires live mode (set BINANCE_API_KEY, BINANCE_API_SECRET)")
        pair = self._resolve_pair(symbol)
        return self._exchange.create_market_buy_order(pair, size)

    def market_sell(self, symbol: str, size: float) -> dict:
        """Place a market sell order. Requires live mode."""
        if not self._is_live:
            raise RuntimeError("market_sell requires live mode (set BINANCE_API_KEY, BINANCE_API_SECRET)")
        pair = self._resolve_pair(symbol)
        return self._exchange.create_market_sell_order(pair, size)

    def get_vol_metrics(self, underlying: str) -> Tuple[float, float]:
        """Compute 14-day historical vol and IV rank from daily OHLCV."""
        try:
            ohlcv = self._exchange.fetch_ohlcv(underlying + "/USDT", "1d", limit=90)
            if not ohlcv or len(ohlcv) < 15:
                return 0.60, 50.0
            closes = [c[4] for c in ohlcv]
            returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
            if len(returns) < 14:
                return 0.60, 50.0
            w = 14
            mean = sum(returns[-w:]) / w
            variance = sum((r - mean) ** 2 for r in returns[-w:]) / w
            vol = math.sqrt(variance) * math.sqrt(365)

            hvs = []
            for i in range(len(returns) - w + 1):
                chunk = returns[i:i + w]
                m = sum(chunk) / w
                v = sum((r - m) ** 2 for r in chunk) / w
                hvs.append(math.sqrt(v) * math.sqrt(365) * 100)
            current_hv = vol * 100
            hv_min, hv_max = min(hvs), max(hvs)
            if hv_max > hv_min:
                iv_rank = (current_hv - hv_min) / (hv_max - hv_min) * 100
                iv_rank = round(min(max(iv_rank, 0.0), 100.0), 1)
            else:
                iv_rank = 50.0
            return round(vol, 4), iv_rank
        except Exception:
            return 0.60, 50.0

    def get_real_expiry(self, underlying: str, target_dte: int) -> Tuple[str, int]:
        raise NotImplementedError("BinanceUS does not support options")

    def get_real_strike(self, underlying: str, expiry: str,
                        option_type: str, target_strike: float) -> float:
        raise NotImplementedError("BinanceUS does not support options")

    def get_premium_and_greeks(self, underlying: str, option_type: str,
                                strike: float, expiry: str, dte: float,
                                spot: float, vol: float) -> Tuple[float, float, dict]:
        raise NotImplementedError("BinanceUS does not support options")
