"""
position_manager.py
====================
Tracks open positions, trade history, and P&L.
"""
import os
import csv
import logging
from datetime import datetime

logger = logging.getLogger("bot")

TRADE_LOG_FILE = os.path.join("logs", "trades.csv")
TRADE_HEADERS = [
    "timestamp", "symbol", "action", "entry_price", "exit_price",
    "size_usd", "pnl_usd", "pnl_pct", "exit_reason", "duration_min"
]


class PositionManager:
    """Track positions and log trades."""

    def __init__(self):
        self._positions: dict[str, dict] = {}  # symbol -> position info
        self._ensure_trade_log()

    def _ensure_trade_log(self):
        os.makedirs("logs", exist_ok=True)
        if not os.path.exists(TRADE_LOG_FILE):
            with open(TRADE_LOG_FILE, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(TRADE_HEADERS)

    def has_position(self, symbol: str) -> bool:
        return symbol in self._positions

    def open_position(
        self, symbol: str, entry_price: float, size_usd: float,
        tp_price: float, sl_price: float, direction: str = "long"
    ):
        """Record opening a new position."""
        self._positions[symbol] = {
            "direction": direction,
            "entry_price": entry_price,
            "size_usd": size_usd,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "entry_time": datetime.now(),
        }
        logger.info(
            f"POSITION OPENED: {symbol} [{direction.upper()}] @ ${entry_price:.2f} | "
            f"Size: ${size_usd:.2f} | TP: ${tp_price:.2f} | SL: ${sl_price:.2f}"
        )

    def close_position(self, symbol: str, exit_price: float, reason: str) -> dict | None:
        """Record closing a position. Returns trade summary."""
        if symbol not in self._positions:
            logger.warning(f"No position to close for {symbol}")
            return None

        pos = self._positions.pop(symbol)
        entry = pos["entry_price"]
        direction = pos.get("direction", "long")
        
        if direction == "long":
            pnl_pct = (exit_price / entry - 1) * 100
            pnl_usd = pos["size_usd"] * (exit_price / entry - 1)
        else:
            pnl_pct = (entry / exit_price - 1) * 100
            pnl_usd = pos["size_usd"] * (entry / exit_price - 1)
            
        duration = (datetime.now() - pos["entry_time"]).total_seconds() / 60

        trade = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "action": "CLOSE",
            "entry_price": round(entry, 2),
            "exit_price": round(exit_price, 2),
            "size_usd": round(pos["size_usd"], 2),
            "pnl_usd": round(pnl_usd, 2),
            "pnl_pct": round(pnl_pct, 4),
            "exit_reason": reason,
            "duration_min": round(duration, 1),
        }

        # Log to CSV
        with open(TRADE_LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([trade[h] for h in TRADE_HEADERS])

        emoji = "+" if pnl_usd > 0 else ""
        logger.info(
            f"POSITION CLOSED: {symbol} | {reason} | "
            f"Entry ${entry:.2f} -> Exit ${exit_price:.2f} | "
            f"P&L: {emoji}${pnl_usd:.2f} ({emoji}{pnl_pct:.2f}%) | "
            f"Duration: {duration:.0f}min"
        )
        return trade

    def get_position(self, symbol: str) -> dict | None:
        return self._positions.get(symbol)

    def get_all_positions(self) -> dict:
        return dict(self._positions)

    def sync_from_exchange(self, exchange_positions: list[dict]):
        """
        Sync internal state with exchange positions.
        Useful on bot restart to recover open positions.
        """
        for pos in exchange_positions:
            coin = pos["coin"]
            size = float(pos["size"])
            if coin not in self._positions and size != 0:
                direction = "long" if size > 0 else "short"
                logger.info(f"Syncing position from exchange: {coin} [{direction.upper()}] size={size} entry={pos['entry_px']}")
                self._positions[coin] = {
                    "direction": direction,
                    "entry_price": pos["entry_px"],
                    "size_usd": abs(size) * pos["entry_px"],
                    "tp_price": 0,  # Unknown — will need manual check
                    "sl_price": 0,
                    "entry_time": datetime.now(),  # Approximate
                }
