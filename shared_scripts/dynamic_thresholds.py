"""
Dynamic adaptive threshold calculator for ML signal enhancement.

Ported from dockertradingbot/trade.py lines 31-92.
Dynamically adjusts ML buy/sell confidence thresholds based on
market conditions (volatility, confluence, performance, urgency, profit).
"""


def calculate_dynamic_buy_threshold(ml_stats, price, rsi, adx,
                                    lower_band, upper_band,
                                    rsi_threshold_buy, adx_threshold):
    """
    Dynamically adjusts the ML buy confidence threshold based on market conditions.

    Args:
        ml_stats: dict from MLSignalGenerator.get_performance_stats()
                  (or empty dict if model untrained)
        price: current price
        rsi: current RSI value
        adx: current ADX value
        lower_band: Bollinger lower band
        upper_band: Bollinger upper band
        rsi_threshold_buy: oversold RSI threshold
        adx_threshold: ADX trend strength threshold

    Returns:
        float in [0.05, 0.60] — minimum ML probability needed to trigger a buy.
        Lower = more aggressive, Higher = more selective.
    """
    is_trained = ml_stats.get('is_trained', False)
    base = 0.30 if is_trained else 0.20

    # Factor 1: Volatility (wider bands = more volatile = lower threshold)
    bb_width = (upper_band - lower_band) / price if price > 0 else 0
    volatility_factor = min(bb_width * 10, 0.15)

    # Factor 2: Technical confluence (more signals agreeing = lower threshold)
    confluence_score = 0
    if price < lower_band:
        confluence_score += 1
    if rsi < rsi_threshold_buy:
        confluence_score += 1
    if rsi < rsi_threshold_buy * 0.8:  # very oversold
        confluence_score += 1
    if adx > adx_threshold:
        confluence_score += 1
    confluence_factor = (confluence_score / 4) * 0.20

    # Factor 3: Performance (high win rate = be selective; low = be aggressive)
    performance_factor = 0.0
    if is_trained:
        win_rate = ml_stats.get('win_rate', 0.5)
        if win_rate > 0.60:
            performance_factor = +0.05
        elif win_rate < 0.40:
            performance_factor = -0.05

    # Factor 4: Market urgency (extreme oversold = very aggressive)
    urgency_factor = 0.0
    if price < lower_band and rsi < rsi_threshold_buy * 0.7:
        urgency_factor = 0.10

    threshold = base - volatility_factor - confluence_factor + performance_factor - urgency_factor
    return max(0.05, min(0.60, threshold))


def calculate_dynamic_sell_threshold(ml_stats, price, rsi, adx,
                                     upper_band, current_profit_pct,
                                     rsi_threshold_sell, adx_threshold):
    """
    Dynamically adjusts the ML sell confidence threshold based on P&L and market.

    Args:
        ml_stats: dict from MLSignalGenerator.get_performance_stats()
        price: current price
        rsi: current RSI value
        adx: current ADX value
        upper_band: Bollinger upper band
        current_profit_pct: current unrealized P&L as percentage
        rsi_threshold_sell: overbought RSI threshold
        adx_threshold: ADX trend strength threshold

    Returns:
        float in [0.40, 0.85] — minimum ML probability needed to trigger a sell.
        Lower = more willing to sell, Higher = hold for more profit.
    """
    is_trained = ml_stats.get('is_trained', False)
    base = 0.70 if is_trained else 0.65

    # Volatility adjustment (minimal for sell)
    bb_width = (upper_band - price) / price if price > 0 else 0
    volatility_factor = min(abs(bb_width) * 5, 0.05)

    # Profit-based adjustment (critical for sell decisions)
    profit_factor = 0.0
    if current_profit_pct > 25:
        profit_factor = -0.10    # Big profit → sell eagerly
    elif current_profit_pct > 15:
        profit_factor = -0.05
    elif current_profit_pct > 8:
        profit_factor = 0.0      # Neutral
    elif current_profit_pct > 3:
        profit_factor = +0.10    # Small profit → hold
    elif current_profit_pct > 0:
        profit_factor = +0.15    # Tiny profit → hold strongly
    elif current_profit_pct > -20:
        profit_factor = +0.05    # Small loss → hold
    else:
        profit_factor = -0.08    # Big loss → willing to cut

    threshold = base - volatility_factor + profit_factor
    return max(0.40, min(0.85, threshold))
