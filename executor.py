"""
executor.py
============
Handles order placement via Hyperliquid Exchange SDK.
Supports market open/close and TP/SL orders.
"""
import time
import logging
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

logger = logging.getLogger("bot")

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


class Executor:
    """Place and manage orders on Hyperliquid."""

    def __init__(self, secret_key: str, account_address: str, use_testnet: bool = True):
        api_url = constants.TESTNET_API_URL if use_testnet else constants.MAINNET_API_URL

        # Convert private key string to LocalAccount
        wallet = Account.from_key(secret_key)

        self.exchange = Exchange(
            wallet=wallet,
            base_url=api_url,
            account_address=account_address,
        )
        self.info = Info(api_url, skip_ws=True)
        self.address = account_address
        self._use_testnet = use_testnet

        # Get size decimals from exchange metadata
        self._sz_decimals = {}
        try:
            meta = self.info.meta()
            for coin in meta.get("universe", []):
                self._sz_decimals[coin["name"]] = coin.get("szDecimals", 4)
        except Exception as e:
            logger.warning(f"Could not fetch metadata for size decimals: {e}")

        env = "TESTNET" if use_testnet else "MAINNET"
        logger.info(f"Executor initialized on {env}")

    def set_leverage(self, symbol: str, leverage: int, is_cross: bool = True) -> bool:
        """Set leverage for a symbol. Must be called before opening a position."""
        try:
            mode = "Cross" if is_cross else "Isolated"
            result = self.exchange.update_leverage(leverage, symbol, is_cross)
            logger.info(f"Leverage set: {symbol} = {leverage}x ({mode})")
            return True
        except Exception as e:
            logger.error(f"Error setting leverage for {symbol}: {e}")
            return False

    def market_open_long(self, symbol: str, size_usd: float, current_price: float | None = None) -> dict | None:
        """
        Open a LONG position via market order.
        size_usd: notional value in USD to buy.
        current_price: optional price to use (otherwise fetches live).
        Returns order result dict or None on failure.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # Get current price to calculate size in coins
                mid = current_price or float(self.info.all_mids()[symbol])
                decimals = self._sz_decimals.get(symbol, 4)
                sz = round(size_usd / mid, decimals)

                if sz <= 0:
                    logger.error(f"Invalid size {sz} for {symbol} (${size_usd})")
                    return None

                logger.info(f"MARKET BUY {symbol}: ${size_usd:.2f} = {sz} coins @ ~${mid:.2f}")

                result = self.exchange.market_open(
                    name=symbol,
                    is_buy=True,
                    sz=sz,
                    slippage=0.01,  # 1% max slippage
                )

                if result.get("status") == "ok":
                    fill = result.get("response", {}).get("data", {})
                    logger.info(f"  -> Order filled: {fill}")
                    return result
                else:
                    logger.warning(f"  -> Order response: {result}")
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY * attempt)
                    continue

            except Exception as e:
                logger.error(f"  -> Error placing market buy (attempt {attempt}): {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)

        logger.error(f"FAILED to open long {symbol} after {MAX_RETRIES} attempts")
        return None

    def market_open_short(self, symbol: str, size_usd: float, current_price: float | None = None) -> dict | None:
        """
        Open a SHORT position via market order.
        size_usd: notional value in USD to sell.
        current_price: optional price to use (otherwise fetches live).
        Returns order result dict or None on failure.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # Get current price to calculate size in coins
                mid = current_price or float(self.info.all_mids()[symbol])
                decimals = self._sz_decimals.get(symbol, 4)
                sz = round(size_usd / mid, decimals)

                if sz <= 0:
                    logger.error(f"Invalid size {sz} for {symbol} (${size_usd})")
                    return None

                logger.info(f"MARKET SELL (SHORT) {symbol}: ${size_usd:.2f} = {sz} coins @ ~${mid:.2f}")

                result = self.exchange.market_open(
                    name=symbol,
                    is_buy=False,  # Short = sell to open
                    sz=sz,
                    slippage=0.01,  # 1% max slippage
                )

                if result.get("status") == "ok":
                    fill = result.get("response", {}).get("data", {})
                    logger.info(f"  -> Order filled: {fill}")
                    return result
                else:
                    logger.warning(f"  -> Order response: {result}")
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY * attempt)
                    continue

            except Exception as e:
                logger.error(f"  -> Error placing market sell (attempt {attempt}): {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)

        logger.error(f"FAILED to open short {symbol} after {MAX_RETRIES} attempts")
        return None

    def market_close_long(self, symbol: str, size: float | None = None, current_price: float | None = None) -> dict | None:
        """Close an existing LONG position via market order. 
        If size is provided, it closes exactly that amount."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if size is not None:
                    logger.info(f"MARKET CLOSE LONG {symbol} (Size: {size})")
                    # Sell to close the long
                    result = self.exchange.market_open(
                        name=symbol,
                        is_buy=False,
                        sz=size,
                        slippage=0.01,
                    )
                else:
                    logger.info(f"MARKET CLOSE LONG {symbol} (Full)")
                    result = self.exchange.market_close(
                        coin=symbol,
                        slippage=0.01,
                    )

                if result.get("status") == "ok":
                    logger.info(f"  -> Position closed: {result}")
                    return result
                else:
                    logger.warning(f"  -> Close response: {result}")
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY * attempt)

            except Exception as e:
                logger.error(f"  -> Error closing position (attempt {attempt}): {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)

        logger.error(f"FAILED to close {symbol} after {MAX_RETRIES} attempts")
        return None

    def market_close_short(self, symbol: str, size: float | None = None, current_price: float | None = None) -> dict | None:
        """Close an existing SHORT position via market order.
        If size is provided, it closes exactly that amount."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if size is not None:
                    logger.info(f"MARKET CLOSE SHORT {symbol} (Size: {size})")
                    # Buy to close the short
                    result = self.exchange.market_open(
                        name=symbol,
                        is_buy=True,
                        sz=size,
                        slippage=0.01,
                    )
                else:
                    logger.info(f"MARKET CLOSE SHORT {symbol} (Full)")
                    result = self.exchange.market_close(
                        coin=symbol,
                        slippage=0.01,
                    )

                if result.get("status") == "ok":
                    logger.info(f"  -> Position closed: {result}")
                    return result
                else:
                    logger.warning(f"  -> Close response: {result}")
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY * attempt)

            except Exception as e:
                logger.error(f"  -> Error closing position (attempt {attempt}): {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)

        logger.error(f"FAILED to close short {symbol} after {MAX_RETRIES} attempts")
        return None
    def place_tp_sl(
        self, symbol: str, size: float, tp_price: float, sl_price: float, is_long: bool = True
    ) -> tuple[dict | None, dict | None]:
        """
        Place take-profit and stop-loss orders for an open position.
        size: position size in coins (positive).
        tp_price: take profit trigger price.
        sl_price: stop loss trigger price.
        is_long: True if position is long, False if short.
        Returns (tp_result, sl_result).
        """
        # Ensure all values are float (can come as strings from API)
        size = float(size)
        tp_price = float(tp_price)
        sl_price = float(sl_price)

        tp_result = None
        sl_result = None

        # Take Profit — long sells, short buys
        tp_is_buy = not is_long
        try:
            # Round to 1 decimal for Hyperliquid price compatibility
            tp_px = round(tp_price, 1)
            action_str = "buy" if tp_is_buy else "sell"
            logger.info(f"Setting TP for {symbol}: {action_str} {size} @ ${tp_px:.1f}")
            tp_result = self.exchange.order(
                name=symbol,
                is_buy=tp_is_buy,
                sz=size,
                limit_px=tp_px,
                order_type={"trigger": {"triggerPx": tp_px, "isMarket": True, "tpsl": "tp"}},
                reduce_only=True,
            )
            logger.info(f"  -> TP order: {tp_result}")
        except Exception as e:
            logger.error(f"  -> Error setting TP: {e}")

        # Stop Loss — long sells, short buys
        sl_is_buy = not is_long
        try:
            sl_px = round(sl_price, 1)
            action_str = "buy" if sl_is_buy else "sell"
            logger.info(f"Setting SL for {symbol}: {action_str} {size} @ ${sl_px:.1f}")
            sl_result = self.exchange.order(
                name=symbol,
                is_buy=sl_is_buy,
                sz=size,
                limit_px=sl_px,
                order_type={"trigger": {"triggerPx": sl_px, "isMarket": True, "tpsl": "sl"}},
                reduce_only=True,
            )
            logger.info(f"  -> SL order: {sl_result}")
        except Exception as e:
            logger.error(f"  -> Error setting SL: {e}")

        return tp_result, sl_result

    def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all open orders for a symbol."""
        try:
            open_orders = self.info.open_orders(self.address)
            symbol_orders = [o for o in open_orders if o.get("coin") == symbol]
            if not symbol_orders:
                return True

            for order in symbol_orders:
                oid = order["oid"]
                self.exchange.cancel(name=symbol, oid=oid)
                logger.info(f"Cancelled order {oid} for {symbol}")
            return True
        except Exception as e:
            logger.error(f"Error cancelling orders for {symbol}: {e}")
            return False

    def get_position(self, symbol: str) -> dict | None:
        """Get current position for a symbol, or None if no position."""
        try:
            state = self.info.user_state(self.address)
            for pos in state.get("assetPositions", []):
                p = pos["position"]
                if p["coin"] == symbol and float(p["szi"]) != 0:
                    return {
                        "coin": symbol,
                        "size": float(p["szi"]),
                        "entry_px": float(p.get("entryPx", 0)),
                        "unrealized_pnl": float(p.get("unrealizedPnl", 0)),
                    }
            return None
        except Exception as e:
            logger.error(f"Error checking position {symbol}: {e}")
            return None
