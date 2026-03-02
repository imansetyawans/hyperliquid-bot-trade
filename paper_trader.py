"""
paper_trader.py
================
Paper trading simulator — same interface as executor.py but no real orders.
"""
import logging
from datetime import datetime

logger = logging.getLogger("bot")


class PaperTrader:
    """Simulate order execution without touching the exchange."""

    def __init__(self, initial_balance: float = 10000.0):
        self.balance = initial_balance
        self._positions: dict[str, dict] = {}
        self._trade_count = 0
        logger.info(f"Paper Trader initialized with ${initial_balance:,.2f}")

<<<<<<< HEAD
    def market_open_long(self, symbol: str, size_usd: float, current_price: float) -> dict | None:
        """Simulate opening a long position."""
=======
    def market_open_long(self, symbol: str, size_usd: float, current_price: float | None = None) -> dict | None:
        """Simulate opening a long position."""
        if current_price is None:
            logger.error("[PAPER] market_open_long requires current_price")
            return None

>>>>>>> 5d7e268 (Fix trade anomalies, strategy collisions, and paper trading bugs)
        if size_usd > self.balance:
            logger.warning(f"[PAPER] Insufficient balance: ${self.balance:.2f} < ${size_usd:.2f}")
            return None

        # Apply simulated slippage (0.05%)
        fill_price = current_price * 1.0005
        # Apply fee (0.1%)
        fee = size_usd * 0.001
        size_coins = size_usd / fill_price

        self.balance -= size_usd
        self._positions[symbol] = {
            "direction": "long",
            "entry_price": fill_price,
            "size_usd": size_usd,
            "size_coins": size_coins,
            "fee_paid": fee,
            "entry_time": datetime.now(),
        }
        self._trade_count += 1

        logger.info(
            f"[PAPER] BUY {symbol}: {size_coins:.6f} @ ${fill_price:.2f} "
            f"(${size_usd:.2f}) | Fee: ${fee:.2f} | Balance: ${self.balance:.2f}"
        )
        return {"status": "ok", "paper": True, "fill_price": fill_price}

<<<<<<< HEAD
    def market_open_short(self, symbol: str, size_usd: float, current_price: float) -> dict | None:
        """Simulate opening a short position."""
=======
    def market_open_short(self, symbol: str, size_usd: float, current_price: float | None = None) -> dict | None:
        """Simulate opening a short position."""
        if current_price is None:
            logger.error("[PAPER] market_open_short requires current_price")
            return None

>>>>>>> 5d7e268 (Fix trade anomalies, strategy collisions, and paper trading bugs)
        if size_usd > self.balance:
            logger.warning(f"[PAPER] Insufficient balance: ${self.balance:.2f} < ${size_usd:.2f}")
            return None

        # Apply simulated slippage (0.05%)
        fill_price = current_price * 0.9995  # Shorts enter slightly lower
        # Apply fee (0.1%)
        fee = size_usd * 0.001
        size_coins = size_usd / fill_price

        self.balance -= size_usd
        self._positions[symbol] = {
            "direction": "short",
            "entry_price": fill_price,
            "size_usd": size_usd,
            "size_coins": size_coins,
            "fee_paid": fee,
            "entry_time": datetime.now(),
        }
        self._trade_count += 1

        logger.info(
            f"[PAPER] SELL (SHORT) {symbol}: {size_coins:.6f} @ ${fill_price:.2f} "
            f"(${size_usd:.2f}) | Fee: ${fee:.2f} | Balance: ${self.balance:.2f}"
        )
        return {"status": "ok", "paper": True, "fill_price": fill_price}

<<<<<<< HEAD
    def market_close_long(self, symbol: str, current_price: float, size: float | None = None) -> dict | None:
        """Simulate closing a long position."""
=======
    def market_close_long(self, symbol: str, size: float | None = None, current_price: float | None = None) -> dict | None:
        """Simulate closing a long position."""
        if current_price is None:
            logger.error("[PAPER] market_close_long requires current_price")
            return None
            
>>>>>>> 5d7e268 (Fix trade anomalies, strategy collisions, and paper trading bugs)
        if symbol not in self._positions:
            logger.warning(f"[PAPER] No position to close for {symbol}")
            return None

        pos = self._positions.pop(symbol)
        # Apply simulated slippage (0.05%)
        fill_price = current_price * 0.9995
        # Apply fee (0.1%)
        exit_value = pos["size_coins"] * fill_price
        fee = exit_value * 0.001
        net_value = exit_value - fee

        pnl = net_value - pos["size_usd"]
        pnl_pct = (fill_price / pos["entry_price"] - 1) * 100
        self.balance += net_value

        emoji = "+" if pnl > 0 else ""
        logger.info(
            f"[PAPER] SELL {symbol}: {pos['size_coins']:.6f} @ ${fill_price:.2f} | "
            f"P&L: {emoji}${pnl:.2f} ({emoji}{pnl_pct:.2f}%) | "
            f"Balance: ${self.balance:.2f}"
        )
        return {
            "status": "ok", "paper": True, "fill_price": fill_price,
            "pnl": pnl, "pnl_pct": pnl_pct,
        }

<<<<<<< HEAD
    def market_close_short(self, symbol: str, current_price: float, size: float | None = None) -> dict | None:
        """Simulate closing a short position."""
=======
    def market_close_short(self, symbol: str, size: float | None = None, current_price: float | None = None) -> dict | None:
        """Simulate closing a short position."""
        if current_price is None:
            logger.error("[PAPER] market_close_short requires current_price")
            return None

>>>>>>> 5d7e268 (Fix trade anomalies, strategy collisions, and paper trading bugs)
        if symbol not in self._positions:
            logger.warning(f"[PAPER] No position to close for {symbol}")
            return None

        pos = self._positions.pop(symbol)
        # Apply simulated slippage (0.05%)
        fill_price = current_price * 1.0005  # Shorts exit (buy back) slightly higher
        # Apply fee (0.1%)
        exit_value = pos["size_coins"] * fill_price
        fee = exit_value * 0.001

        # Short P&L: (entry - exit) * coins
        pnl = (pos["entry_price"] - fill_price) * pos["size_coins"] - fee
        pnl_pct = (pos["entry_price"] / fill_price - 1) * 100
        
        # Balance = Initial margin + P&L
        returned_value = pos["size_usd"] + pnl
        self.balance += returned_value

        emoji = "+" if pnl > 0 else ""
        logger.info(
            f"[PAPER] BUY (COVER) {symbol}: {pos['size_coins']:.6f} @ ${fill_price:.2f} | "
            f"P&L: {emoji}${pnl:.2f} ({emoji}{pnl_pct:.2f}%) | "
            f"Balance: ${self.balance:.2f}"
        )
        return {
            "status": "ok", "paper": True, "fill_price": fill_price,
            "pnl": pnl, "pnl_pct": pnl_pct,
        }

    def place_tp_sl(self, symbol: str, size: float, tp_price: float, sl_price: float):
        """In paper mode, TP/SL are checked each loop iteration by strategy."""
        if symbol in self._positions:
            self._positions[symbol]["tp_price"] = tp_price
            self._positions[symbol]["sl_price"] = sl_price
            logger.info(f"[PAPER] TP/SL set for {symbol}: TP=${tp_price:.2f} SL=${sl_price:.2f}")

    def check_tp_sl(self, symbol: str, current_price: float) -> str | None:
        """Check if TP or SL is triggered. Returns 'tp', 'sl', or None."""
        if symbol not in self._positions:
            return None
        pos = self._positions[symbol]
        tp = pos.get("tp_price", 0)
        sl = pos.get("sl_price", 0)
        direction = pos.get("direction", "long")
        
        if direction == "long":
            if tp and current_price >= tp: return "tp"
            if sl and current_price <= sl: return "sl"
        else:
            if tp and current_price <= tp: return "tp"
            if sl and current_price >= sl: return "sl"
            
        return None

    def has_position(self, symbol: str) -> bool:
        return symbol in self._positions

    def get_position(self, symbol: str) -> dict | None:
        if symbol not in self._positions:
            return None
        pos = self._positions[symbol]
        return {
            "coin": symbol,
            "size": pos["size_coins"] if pos.get("direction", "long") == "long" else -pos["size_coins"],
            "entry_px": pos["entry_price"],
        }

    def get_balance(self) -> float:
        return self.balance

    def cancel_all_orders(self, symbol: str) -> bool:
        """No-op in paper mode (TP/SL are virtual)."""
        return True
