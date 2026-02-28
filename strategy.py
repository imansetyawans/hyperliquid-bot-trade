"""
strategy.py
============
Core strategy logic — runs every 30min on candle close.
Implements V6 BTC (TP=10%/SL=6%) and V7 ETH (TP=18%/SL=10%).
"""
import logging
import pandas as pd
from indicators import compute_rsi, compute_macd, compute_mas

logger = logging.getLogger("bot")


class Strategy:
    """
    Multi-timeframe momentum strategy:
      Regime (4H): MACD > Signal AND RSI > regime_rsi
      Entry (30m): Price > MA7/14/28/111 AND RSI > entry_rsi AND regime = BULL
      Exit: TP / SL / Force Close (Price < all MAs AND RSI < fc_rsi)
    """

    def __init__(self, config_key: str, config: dict):
        self.config_key = config_key
        self.symbol = config.get("symbol", config_key)
        self.direction = config.get("direction", "long").lower()
        self.tp_pct = config["tp_pct"]
        self.sl_pct = config["sl_pct"]
        self.capital_pct = config["capital_pct"]
        self.regime_rsi_thresh = config.get("regime_rsi", 55)
        self.entry_rsi_thresh = config.get("entry_rsi", 55)
        self.fc_rsi_thresh = config.get("fc_rsi", 45)
        self.regime_tf = config.get("regime_tf", "4h")
        self.entry_tf = config.get("entry_tf", "30m")

        # State
        self._regime_valid = False
        self._entry_signal = False
        self._force_close_signal = False
        self._last_regime_info = {}
        self._last_entry_info = {}

    def update_regime(self, candles_4h: pd.DataFrame) -> bool:
        """
        Evaluate the 4H regime filter.
        Returns True if regime allows trading (BULL for long, BEAR for short).
        """
        if candles_4h.empty or len(candles_4h) < 30:
            logger.warning(f"{self.config_key}: Insufficient 4H data ({len(candles_4h)} candles)")
            self._regime_valid = False
            return False

        close = candles_4h["close"]
        rsi_s = compute_rsi(close, 14)
        macd_line, signal_line = compute_macd(close, 12, 26, 9)

        latest_rsi = rsi_s.iloc[-1]
        latest_macd = macd_line.iloc[-1]
        latest_signal = signal_line.iloc[-1]

        if self.direction == "long":
            self._regime_valid = (latest_macd > latest_signal) and (latest_rsi > self.regime_rsi_thresh)
            regime_type = "BULL"
        else:
            self._regime_valid = (latest_macd < latest_signal) and (latest_rsi < self.regime_rsi_thresh)
            regime_type = "BEAR"

        self._last_regime_info = {
            "macd": round(latest_macd, 4),
            "signal": round(latest_signal, 4),
            "rsi_4h": round(latest_rsi, 2),
            "valid": self._regime_valid,
            "direction": self.direction
        }

        status_str = regime_type if self._regime_valid else "WAIT"
        check_op = ">" if self.direction == "long" else "<"
        logger.info(
            f"{self.config_key} REGIME [{status_str}]: "
            f"MACD={latest_macd:.4f} vs Sig={latest_signal:.4f} | "
            f"RSI={latest_rsi:.1f} ({check_op}{self.regime_rsi_thresh}?)"
        )
        return self._regime_valid

    def update_entry(self, candles_30m: pd.DataFrame) -> bool:
        """
        Evaluate the 30min entry signal.
        Returns True if entry conditions are met.
        """
        if candles_30m.empty or len(candles_30m) < 120:
            logger.warning(f"{self.config_key}: Insufficient 30m data ({len(candles_30m)} candles)")
            self._entry_signal = False
            self._force_close_signal = False
            return False

        close = candles_30m["close"]
        rsi_s = compute_rsi(close, 14)
        mas = compute_mas(close, [7, 14, 28, 111])

        price = close.iloc[-1]
        latest_rsi = rsi_s.iloc[-1]
        ma7 = mas[7].iloc[-1]
        ma14 = mas[14].iloc[-1]
        ma28 = mas[28].iloc[-1]
        ma111 = mas[111].iloc[-1]

        above_all_mas = (price > ma7) and (price > ma14) and (price > ma28) and (price > ma111)
        below_all_mas = (price < ma7) and (price < ma14) and (price < ma28) and (price < ma111)

        if self.direction == "long":
            # Entry: price > all MAs AND RSI > threshold AND regime valid
            self._entry_signal = above_all_mas and (latest_rsi > self.entry_rsi_thresh) and self._regime_valid
            # Force close: price < all MAs AND RSI < threshold
            self._force_close_signal = below_all_mas and (latest_rsi < self.fc_rsi_thresh)
            
            ma_check = "ABOVE" if above_all_mas else "BELOW"
            rsi_check = "OK" if latest_rsi > self.entry_rsi_thresh else "LOW"
        else:
            # Short entry: price < all MAs AND RSI < threshold AND regime valid
            self._entry_signal = below_all_mas and (latest_rsi < self.entry_rsi_thresh) and self._regime_valid
            # Force close: price > all MAs AND RSI > threshold
            self._force_close_signal = above_all_mas and (latest_rsi > self.fc_rsi_thresh)
            
            ma_check = "BELOW" if below_all_mas else "ABOVE"
            rsi_check = "OK" if latest_rsi < self.entry_rsi_thresh else "HIGH"

        self._last_entry_info = {
            "price": round(price, 2),
            "rsi_30m": round(latest_rsi, 2),
            "ma7": round(ma7, 2),
            "ma14": round(ma14, 2),
            "ma28": round(ma28, 2),
            "ma111": round(ma111, 2),
            "mas_valid": above_all_mas if self.direction == "long" else below_all_mas,
            "entry_signal": self._entry_signal,
            "fc_signal": self._force_close_signal,
        }

        # Always log status so bot doesn't appear stuck
        logger.info(
            f"{self.config_key} 30m: ${price:.2f} | MAs: {ma_check} "
            f"(7={ma7:.2f} 14={ma14:.2f} 28={ma28:.2f} 111={ma111:.2f}) | "
            f"RSI={latest_rsi:.1f} [{rsi_check}]"
        )

        # The signals are logged by the bot loop when they are acted upon
        # so we don't need to unconditionally log them here.

        return self._entry_signal

    def should_enter(self) -> bool:
        """Returns True if all conditions for a new entry are met."""
        return self._entry_signal and self._regime_valid

    def should_force_close(self) -> bool:
        """Returns True if force close conditions are met."""
        return self._force_close_signal

    def is_regime_valid(self) -> bool:
        return self._regime_valid

    def calc_tp_sl(self, entry_price: float) -> tuple[float, float]:
        """Calculate TP and SL prices from entry price."""
        if self.direction == "long":
            tp = entry_price * (1 + self.tp_pct)
            sl = entry_price * (1 - self.sl_pct)
        else:
            tp = entry_price * (1 - self.tp_pct)
            sl = entry_price * (1 + self.sl_pct)
        # Round to 1 decimal — Hyperliquid API requires this precision for TP/SL
        return round(tp, 1), round(sl, 1)

    def get_status(self) -> dict:
        """Get full strategy state for logging/monitoring."""
        return {
            "config_key": self.config_key,
            "symbol": self.symbol,
            "direction": self.direction,
            "regime": self._last_regime_info,
            "entry": self._last_entry_info,
            "tp_pct": f"{self.tp_pct*100:.0f}%",
            "sl_pct": f"{self.sl_pct*100:.0f}%",
        }
