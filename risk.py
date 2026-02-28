"""
risk.py
========
Risk management — position sizing, daily loss limits, cooldowns.
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("bot")


class RiskManager:
    """Enforce risk limits before allowing trades."""

    def __init__(self, config: dict):
        risk_cfg = config.get("risk", {})
        self.max_daily_loss_pct = risk_cfg.get("max_daily_loss_pct", 5.0)
        self.max_open_positions = risk_cfg.get("max_open_positions", 2)
        self.min_trade_interval = timedelta(minutes=risk_cfg.get("min_trade_interval_min", 5))

        self._daily_pnl = 0.0
        self._daily_reset = datetime.now().date()
        self._last_trade_time: datetime | None = None
        self._trade_count_today = 0

    def _reset_daily_if_needed(self):
        today = datetime.now().date()
        if today != self._daily_reset:
            logger.info(f"Daily risk reset. Previous day P&L: ${self._daily_pnl:.2f}")
            self._daily_pnl = 0.0
            self._trade_count_today = 0
            self._daily_reset = today

    def can_open_trade(self, account_value: float, num_open: int) -> tuple[bool, str]:
        """Check if a new trade is allowed. Returns (allowed, reason)."""
        self._reset_daily_if_needed()

        # Max positions
        if num_open >= self.max_open_positions:
            return False, f"Max open positions reached ({self.max_open_positions})"

        # Daily loss limit
        if account_value > 0:
            daily_loss_pct = (self._daily_pnl / account_value) * 100
            if daily_loss_pct < -self.max_daily_loss_pct:
                return False, f"Daily loss limit hit ({daily_loss_pct:.1f}% < -{self.max_daily_loss_pct}%)"

        # Cool-down between trades
        if self._last_trade_time:
            elapsed = datetime.now() - self._last_trade_time
            if elapsed < self.min_trade_interval:
                remaining = (self.min_trade_interval - elapsed).seconds
                return False, f"Trade cooldown ({remaining}s remaining)"

        return True, "OK"

    def calculate_position_size(self, account_value: float, capital_pct: float, leverage: int = 1) -> float:
        """Calculate USD notional size for a trade (margin × leverage)."""
        margin = account_value * capital_pct
        size = margin * leverage
        logger.debug(
            f"Position size: ${size:.2f} notional "
            f"(${margin:.2f} margin × {leverage}x leverage)"
        )
        return size

    def record_trade(self, pnl_usd: float):
        """Record a completed trade for risk tracking."""
        self._reset_daily_if_needed()
        self._daily_pnl += pnl_usd
        self._last_trade_time = datetime.now()
        self._trade_count_today += 1
        logger.debug(f"Daily P&L: ${self._daily_pnl:.2f} | Trades today: {self._trade_count_today}")

    def get_daily_summary(self) -> dict:
        self._reset_daily_if_needed()
        return {
            "daily_pnl": round(self._daily_pnl, 2),
            "trades_today": self._trade_count_today,
            "last_trade": self._last_trade_time.isoformat() if self._last_trade_time else None,
        }
