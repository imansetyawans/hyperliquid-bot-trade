"""
data_fetcher.py
================
Fetches OHLCV candle data from Hyperliquid for regime + entry calculations.
"""
import time
import logging
import pandas as pd
from hyperliquid.info import Info
from hyperliquid.utils import constants

logger = logging.getLogger("bot")


class DataFetcher:
    """Fetch and cache candle data from Hyperliquid."""

    # Hyperliquid candle interval strings
    INTERVAL_MAP = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "4h": "4h", "1d": "1d",
    }

    def __init__(self, use_testnet: bool = True):
        api_url = constants.TESTNET_API_URL if use_testnet else constants.MAINNET_API_URL
        # Retry init — testnet can return 502 temporarily
        for attempt in range(1, 4):
            try:
                self.info = Info(api_url, skip_ws=True)
                break
            except Exception as e:
                logger.warning(f"API init attempt {attempt}/3 failed: {e}")
                if attempt < 3:
                    import time as _time
                    _time.sleep(5)
                else:
                    logger.error("Could not connect to API after 3 attempts")
                    raise
        self._cache: dict[str, tuple[float, pd.DataFrame]] = {}
        self._cache_ttl = 25  # seconds — refresh slightly before new candle

    def get_candles(
        self, symbol: str, interval: str, count: int = 200
    ) -> pd.DataFrame:
        """
        Fetch recent candles for a symbol.
        Returns DataFrame with columns: open, high, low, close, volume, time.
        """
        cache_key = f"{symbol}_{interval}"

        # Return cached if fresh
        if cache_key in self._cache:
            ts, df = self._cache[cache_key]
            if time.time() - ts < self._cache_ttl:
                return df

        try:
            # Calculate start time: count * interval_seconds ago
            interval_sec = self._interval_to_seconds(interval)
            end_ms = int(time.time() * 1000)
            start_ms = end_ms - (count * interval_sec * 1000)

            raw = self.info.candles_snapshot(
                name=symbol,
                interval=self.INTERVAL_MAP.get(interval, interval),
                startTime=start_ms,
                endTime=end_ms,
            )

            if not raw:
                logger.warning(f"No candle data returned for {symbol} {interval}")
                return pd.DataFrame()

            df = pd.DataFrame(raw)
            # Hyperliquid returns: t (timestamp ms), T (close time), s (symbol),
            # i (interval), o, h, l, c, v (volume), n (num trades)
            df = df.rename(columns={
                "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "t": "time"
            })
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["time"] = pd.to_datetime(df["time"], unit="ms")
            df = df.sort_values("time").reset_index(drop=True)
            df = df.set_index("time")

            # Do NOT drop the current incomplete candle.
            # We want live Regime updates based on the current forming candle.

            self._cache[cache_key] = (time.time(), df)
            logger.debug(f"Fetched {len(df)} candles for {symbol} {interval}")
            return df

        except Exception as e:
            logger.error(f"Error fetching candles for {symbol} {interval}: {e}")
            # Return cached data if available (stale is better than nothing)
            if cache_key in self._cache:
                _, df = self._cache[cache_key]
                return df
            return pd.DataFrame()

    def get_mid_price(self, symbol: str) -> float | None:
        """Get current mid-market price."""
        try:
            all_mids = self.info.all_mids()
            if symbol in all_mids:
                return float(all_mids[symbol])
            logger.warning(f"Symbol {symbol} not found in mids")
            return None
        except Exception as e:
            logger.error(f"Error getting mid price for {symbol}: {e}")
            return None

    def get_account_value(self, address: str) -> float:
        """Get total account value (Perps + Spot USDC for unified accounts)."""
        total = 0.0
        try:
            state = self.info.user_state(address)
            total += float(state["marginSummary"]["accountValue"])
        except Exception as e:
            logger.error(f"Error getting perps account value: {e}")

        # Also check spot USDC balance (Hyperliquid unified account)
        try:
            spot = self.info.spot_user_state(address)
            for b in spot.get("balances", []):
                if b["coin"] == "USDC":
                    available = float(b["total"]) - float(b.get("hold", "0"))
                    total += available
                    break
        except Exception as e:
            logger.debug(f"Could not check spot balance: {e}")

        return total

    def get_open_positions(self, address: str) -> list[dict]:
        """Get list of open positions."""
        try:
            state = self.info.user_state(address)
            positions = []
            for pos in state.get("assetPositions", []):
                p = pos["position"]
                size = float(p["szi"])
                if size != 0:
                    positions.append({
                        "coin": p["coin"],
                        "size": size,
                        "entry_px": float(p["entryPx"]) if p.get("entryPx") else 0,
                        "unrealized_pnl": float(p["unrealizedPnl"]),
                        "leverage": float(p.get("leverage", {}).get("value", 1)),
                    })
            return positions
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []

    @staticmethod
    def _interval_to_seconds(interval: str) -> int:
        unit = interval[-1]
        num = int(interval[:-1])
        mult = {"m": 60, "h": 3600, "d": 86400}
        return num * mult.get(unit, 60)
