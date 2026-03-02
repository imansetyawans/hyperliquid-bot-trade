"""
bot.py — Hyperliquid Trading Bot
==================================
Main entry point. Runs V6 BTC and V7 ETH strategies on Hyperliquid.

Usage:
  python bot.py                 # Runs with config.json
  python bot.py --config my.json  # Custom config file
"""
import json
import sys
import time
import signal
import argparse
import logging
from datetime import datetime

from logger_setup import setup_logger
from data_fetcher import DataFetcher
from strategy import Strategy
from executor import Executor
from paper_trader import PaperTrader
from position_manager import PositionManager
from risk import RiskManager

# ── Globals ──────────────────────────────────────────────────
running = True


def signal_handler(sig, frame):
    global running
    logger = logging.getLogger("bot")
    logger.info("Shutdown signal received. Stopping after current cycle...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_strategy_cycle(
    strat_id: str,
    strat: Strategy,
    fetcher: DataFetcher,
    executor,  # Executor or PaperTrader
    pos_mgr: PositionManager,
    risk_mgr: RiskManager,
    config: dict,
    is_paper: bool,
    logger: logging.Logger,
):
    """Run one cycle of the strategy for a single symbol."""

    strat_cfg = config["strategies"][strat_id]
    symbol = strat_cfg.get("symbol", strat_id)
    direction = strat_cfg.get("direction", "long").lower()
    is_long = (direction == "long")

    # ── 1. Fetch 4H candles and evaluate regime ──────────────
    candles_4h = fetcher.get_candles(symbol, strat_cfg.get("regime_tf", "4h"), count=200)
    if candles_4h.empty:
        logger.warning(f"{strat_id}: No 4H data, skipping cycle")
        return
    strat.update_regime(candles_4h)

    # ── 2. Fetch 30min candles and evaluate entry/FC ─────────
    candles_30m = fetcher.get_candles(symbol, strat_cfg.get("entry_tf", "30m"), count=200)
    if candles_30m.empty:
        logger.warning(f"{strat_id}: No 30m data, skipping cycle")
        return
    strat.update_entry(candles_30m)

    current_price = candles_30m["close"].iloc[-1]

    # ── 3. If in position, check exits ───────────────────────
    if pos_mgr.has_position(strat_id):
        pos = pos_mgr.get_position(strat_id)

        # Check TP/SL (paper mode only — live uses exchange-side orders)
        if is_paper:
            tp_sl_hit = executor.check_tp_sl(symbol, current_price)
            if tp_sl_hit == "tp":
                tp_price = pos.get("tp_price", current_price)
                result = executor.market_close_long(symbol, current_price=tp_price) if is_long else executor.market_close_short(symbol, current_price=tp_price)
                if result:
                    trade = pos_mgr.close_position(strat_id, tp_price, "Take Profit")
                    if trade:
                        risk_mgr.record_trade(trade["pnl_usd"])
                return
            elif tp_sl_hit == "sl":
                sl_price = pos.get("sl_price", current_price)
                result = executor.market_close_long(symbol, current_price=sl_price) if is_long else executor.market_close_short(symbol, current_price=sl_price)
                if result:
                    trade = pos_mgr.close_position(strat_id, sl_price, "Stop Loss")
                    if trade:
                        risk_mgr.record_trade(trade["pnl_usd"])
                return

        # Check Force Close
        if strat.should_force_close():
            logger.info(f"{strat_id} >>> FORCE CLOSE SIGNAL TRIGGERED <<<")
            logger.info(f"{strat_id}: Executing FORCE CLOSE for {direction.upper()} position")
            if is_paper:
                # size is handled internally by PaperTrader for full close if passed as None or if not using size-specific logic
                result = executor.market_close_long(symbol, current_price=current_price) if is_long else executor.market_close_short(symbol, current_price=current_price)
            else:
                executor.cancel_all_orders(symbol)
                # Fetch live position size to ensure we close the full actual size held by Exchange
                live_pos = executor.get_position(symbol)
                sz = abs(live_pos["size"]) if live_pos else None
                
                result = executor.market_close_long(symbol, size=sz, current_price=current_price) if is_long else executor.market_close_short(symbol, size=sz, current_price=current_price)

            if result:
                fill = result.get("fill_price", current_price) if is_paper else current_price
                trade = pos_mgr.close_position(strat_id, fill, "Force Close")
                if trade:
                    risk_mgr.record_trade(trade["pnl_usd"])
            return

        # Log position status
        if not is_paper:
            live_pos = executor.get_position(symbol)
            if live_pos:
                unrealized = live_pos.get("unrealized_pnl", 0)
                logger.debug(f"{strat_id} ({symbol}): In position, unrealized P&L: ${unrealized:.2f}")
            else:
                # Position was closed externally (TP/SL hit on exchange)
                logger.info(f"{strat_id} ({symbol}): Position closed externally (TP/SL hit)")
                pos_mgr.close_position(strat_id, current_price, "Exchange TP/SL")

        return  # Already in position, nothing to do

    # ── 4. If no position, check for entry ───────────────────
    if strat.should_enter():
        # Risk check
        if is_paper:
            account_val = executor.get_balance()
        else:
            account_val = fetcher.get_account_value(config["account_address"])

        num_open = len(pos_mgr.get_all_positions())
        allowed, reason = risk_mgr.can_open_trade(account_val, num_open)

        if not allowed:
            logger.info(f"{symbol}: Entry signal but blocked by risk: {reason}")
            return

        # Calculate position size (margin × leverage = notional)
        leverage = strat_cfg.get("leverage", 1)
        size_usd = risk_mgr.calculate_position_size(account_val, strat_cfg["capital_pct"], leverage)
        if size_usd < 10:
            logger.warning(f"{strat_id}: Position size too small (${size_usd:.2f})")
            return

        margin_used = size_usd / leverage if leverage > 0 else size_usd
        # Place order
        dir_str = "LONG" if is_long else "SHORT"
        logger.info(f"{strat_id} >>> {dir_str} ENTRY SIGNAL TRIGGERED <<<")
        logger.info(f"{strat_id}: ENTERING {dir_str} — ${size_usd:.2f} notional (${margin_used:.2f} margin × {leverage}x)")
        
        if is_paper:
            if is_long:
                result = executor.market_open_long(symbol, size_usd, current_price)
            else:
                result = executor.market_open_short(symbol, size_usd, current_price)
            fill_price = result.get("fill_price", current_price) if result else current_price
        else:
            if is_long:
                result = executor.market_open_long(symbol, size_usd, current_price)
            else:
                result = executor.market_open_short(symbol, size_usd, current_price)
            fill_price = current_price  # Approximate; real fill may differ

        if result and result.get("status") == "ok":
            tp_price, sl_price = strat.calc_tp_sl(fill_price)

            # Record position using strat_id as key
            pos_mgr.open_position(strat_id, symbol, fill_price, size_usd, tp_price, sl_price, direction=direction)

            # Set TP/SL
            if is_paper:
                executor.place_tp_sl(symbol, 0, tp_price, sl_price)
            else:
                # Add a brief delay to allow the exchange to process the position
                # and poll up to 3 times to get the correct filled size.
                live_pos = None
                for _ in range(3):
                    time.sleep(1.0)
                    live_pos = executor.get_position(symbol)
                    if live_pos:
                        break
                
                if live_pos:
                    logger.info(f"Retrieved live position size for {strat_id} ({symbol}): {live_pos['size']}")
                    executor.place_tp_sl(symbol, abs(live_pos["size"]), tp_price, sl_price, is_long=is_long)
                else:
                    logger.warning(f"Could not retrieve live position for {symbol} to set TP/SL")

            risk_mgr.record_trade(0)  # Record trade attempt (PnL logged on close)
        else:
            logger.error(f"{strat_id} ({symbol}): Order failed: {result}")


def main():
    parser = argparse.ArgumentParser(description="Hyperliquid Trading Bot")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    args = parser.parse_args()

    # Load config
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"ERROR: Config file '{args.config}' not found.")
        print("Copy config.example.json to config.json and fill in your credentials.")
        sys.exit(1)

    # Setup logging
    logger = setup_logger("bot", log_dir="logs", level=config.get("log_level", "INFO"))

    is_paper = config.get("paper_trade", True)
    is_testnet = config.get("use_testnet", True)

    logger.info("=" * 60)
    logger.info("  HYPERLIQUID TRADING BOT")
    logger.info(f"  Mode: {'PAPER TRADING' if is_paper else 'LIVE TRADING'}")
    logger.info(f"  Network: {'TESTNET' if is_testnet else 'MAINNET'}")
    logger.info("=" * 60)

    # ── Initialize components ────────────────────────────────
    fetcher = DataFetcher(use_testnet=is_testnet)
    pos_mgr = PositionManager()
    risk_mgr = RiskManager(config)

    if is_paper:
        # Paper trading — get initial balance from exchange for simulation
        try:
            initial_bal = fetcher.get_account_value(config["account_address"])
            if initial_bal <= 0:
                initial_bal = 10000.0
                logger.info(f"Using default paper balance: ${initial_bal:,.2f}")
        except Exception:
            initial_bal = 10000.0
        executor = PaperTrader(initial_balance=initial_bal)
    else:
        executor = Executor(
            secret_key=config["secret_key"],
            account_address=config["account_address"],
            use_testnet=is_testnet,
        )

    # ── Initialize strategies ────────────────────────────────
    strategies: dict[str, Strategy] = {}
    for strat_id, strat_cfg in config.get("strategies", {}).items():
        if strat_cfg.get("enabled", False):
            strategies[strat_id] = Strategy(strat_id, strat_cfg)
            lev = strat_cfg.get("leverage", 1)
            direction = strat_cfg.get("direction", "long").upper()
            logger.info(
                f"Strategy enabled: {strat_id} [{direction}] | "
                f"Leverage={lev}x | "
                f"TP={strat_cfg['tp_pct']*100:.0f}% SL={strat_cfg['sl_pct']*100:.0f}% "
                f"Capital={strat_cfg['capital_pct']*100:.0f}%"
            )

    if not strategies:
        logger.error("No strategies enabled! Check config.json")
        sys.exit(1)

    # ── Set leverage on exchange ──────────────────────────────
    if not is_paper:
        # Group strategies by symbol to avoid leverage overwrites
        symbol_leverages = {}
        for strat_id, strat_cfg in config.get("strategies", {}).items():
            if strat_cfg.get("enabled", False):
                sym = strat_cfg.get("symbol", strat_id)
                lev = strat_cfg.get("leverage", 1)
                symbol_leverages[sym] = max(symbol_leverages.get(sym, 1), lev)
        
        for sym, lev in symbol_leverages.items():
            logger.info(f"Initializing {sym} with {lev}x leverage (cross)...")
            executor.set_leverage(sym, lev, is_cross=True)

    # ── Sync existing positions (for bot restart) ────────────
    # Note: Syncing live positions to strategy-based tracking is complex 
    # as exchange doesn't know about strategy_ids. 
    # For now, we trust the internal state or manual intervention on restart.
    if not is_paper:
        logger.info("Bot restart: Live positions will be handled via strategy evaluation.")

    # ── Show account info at startup ───────────────────────────
    logger.info("-" * 60)
    logger.info("  ACCOUNT INFO")
    logger.info("-" * 60)
    try:
        addr = config["account_address"]
        logger.info(f"  Address:  {addr}")
        logger.info(f"  Network:  {'TESTNET' if is_testnet else 'MAINNET'}")

        # Perps balance (marginSummary.accountValue)
        perps_bal = 0.0
        try:
            state = fetcher.info.user_state(addr)
            perps_bal = float(state["marginSummary"]["accountValue"])
        except Exception:
            pass
        logger.info(f"  Perps Balance:  ${perps_bal:,.2f}")

        # Spot USDC balance
        spot_bal = 0.0
        try:
            spot = fetcher.info.spot_user_state(addr)
            for b in spot.get("balances", []):
                if b["coin"] == "USDC" and float(b["total"]) > 0:
                    spot_bal = float(b["total"])
        except Exception:
            pass
        logger.info(f"  Spot Balance:   ${spot_bal:,.2f} USDC")

        # Total
        total = perps_bal + spot_bal
        logger.info(f"  Total Value:    ${total:,.2f}")

        if total <= 0:
            logger.warning("  >>> No balance found! Fund your wallet to trade <<<")
        elif perps_bal <= 0 and spot_bal > 0:
            logger.warning("  >>> USDC is in SPOT only — transfer to PERPS on the website to trade <<<")

        # Open positions
        positions = fetcher.get_open_positions(addr)
        if positions:
            logger.info(f"  Open positions: {len(positions)}")
            for p in positions:
                logger.info(f"    {p['coin']}: size={p['size']} entry=${p['entry_px']:.2f} PnL=${p['unrealized_pnl']:.2f}")
        else:
            logger.info("  Open positions: none")
    except Exception as e:
        logger.warning(f"  Could not fetch account info: {e}")
    logger.info("-" * 60)

    # ── Main loop ────────────────────────────────────────────
    loop_interval = config.get("loop_interval_sec", 30)
    logger.info(f"Starting main loop (interval: {loop_interval}s)")
    logger.info(f"Symbols: {list(strategies.keys())}")

    cycle = 0
    while running:
        cycle += 1

        try:
            now = datetime.now()
            minute = now.minute
            is_candle_close = minute in [0, 30] or cycle == 1

            if is_candle_close:
                logger.info(f"--- Cycle {cycle} | {now.strftime('%Y-%m-%d %H:%M:%S')} ---")
                # ── 2. Run Strategy Loop ────────────────────────────────
                try:
                    for strat_id, strat in strategies.items():
                        logger.info(f"Running cycle for {strat_id}...")
                        run_strategy_cycle(
                            strat_id, strat, fetcher, executor, pos_mgr, risk_mgr, config, is_paper, logger
                        )
                except Exception as e:
                    logger.error(f"Error in strategy cycle: {e}", exc_info=True)

                # Show positions summary
                positions = pos_mgr.get_all_positions()
                pos_str = ", ".join(positions.keys()) if positions else "none"
                logger.info(f"--- Cycle {cycle} complete | Open: [{pos_str}] | Next check in {loop_interval}s ---")

            else:
                # Between candle closes — check TP/SL if in paper mode
                if is_paper:
                    for strat_id in strategies:
                        if pos_mgr.has_position(strat_id):
                            pos_data = pos_mgr.get_position(strat_id)
                            sym = pos_data["symbol"]
                            is_long = (pos_data["direction"] == "long")
                            mid = fetcher.get_mid_price(sym)
                            if mid:
                                tp_sl = executor.check_tp_sl(sym, mid)
                                if tp_sl == "tp":
                                    tp_px = pos_data.get("tp_price", mid)
                                    result = executor.market_close_long(sym, current_price=tp_px) if is_long else executor.market_close_short(sym, current_price=tp_px)
                                    if result:
                                        trade = pos_mgr.close_position(strat_id, tp_px, "Take Profit")
                                        if trade:
                                            risk_mgr.record_trade(trade["pnl_usd"])
                                elif tp_sl == "sl":
                                    sl_px = pos_data.get("sl_price", mid)
                                    result = executor.market_close_long(sym, current_price=sl_px) if is_long else executor.market_close_short(sym, current_price=sl_px)
                                    if result:
                                        trade = pos_mgr.close_position(strat_id, sl_px, "Stop Loss")
                                        if trade:
                                            risk_mgr.record_trade(trade["pnl_usd"])

                # Show heartbeat every 2 minutes
                if cycle % 4 == 0:
                    next_candle = 30 - (minute % 30)
                    logger.info(f"... waiting | next candle close in ~{next_candle}min ...")

            # Log daily summary periodically
            if cycle % 120 == 0:
                summary = risk_mgr.get_daily_summary()
                positions = pos_mgr.get_all_positions()
                logger.info(
                    f"Daily summary: P&L=${summary['daily_pnl']:.2f} | "
                    f"Trades={summary['trades_today']} | "
                    f"Open positions: {list(positions.keys()) or 'none'}"
                )

        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}", exc_info=True)

        # Wait for next cycle
        time.sleep(loop_interval)

    # ── Shutdown ─────────────────────────────────────────────
    logger.info("Bot shutting down gracefully")
    positions = pos_mgr.get_all_positions()
    if positions:
        logger.warning(f"Open positions at shutdown: {list(positions.keys())}")
        logger.warning("These positions are still open on the exchange!")
    summary = risk_mgr.get_daily_summary()
    logger.info(f"Final daily P&L: ${summary['daily_pnl']:.2f}")
    logger.info("Goodbye!")


if __name__ == "__main__":
    main()
