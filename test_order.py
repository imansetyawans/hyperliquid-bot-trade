"""
test_order.py
==============
Comprehensive test of ALL order functions on Hyperliquid testnet.
Tests: Buy, Check Position, Set TP/SL, Cancel Orders, Close Position.
"""
import json
import sys
import time

sys.path.insert(0, ".")
from logger_setup import setup_logger
from executor import Executor
from data_fetcher import DataFetcher

logger = setup_logger("test", log_dir="logs", level="INFO")

PASS = "[PASS]"
FAIL = "[FAIL]"
results = []


def test(name, passed, detail=""):
    status = PASS if passed else FAIL
    results.append((name, passed))
    logger.info(f"  {status} {name}" + (f" — {detail}" if detail else ""))


def main():
    # Load config
    with open("config.json", "r") as f:
        config = json.load(f)

    if not config.get("use_testnet", True):
        print("ERROR: This test is only for TESTNET!")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("  COMPREHENSIVE ORDER TEST (TESTNET)")
    logger.info("=" * 60)

    # ── Init ──────────────────────────────────────────────────
    logger.info("\n--- Initializing ---")
    fetcher = DataFetcher(use_testnet=True)
    executor = Executor(
        secret_key=config["secret_key"],
        account_address=config["account_address"],
        use_testnet=True,
    )
    test("Executor init", True)

    # ── Step 1: Account Info ─────────────────────────────────
    logger.info("\n--- Step 1: Account Info ---")
    balance = fetcher.get_account_value(config["account_address"])
    logger.info(f"  Total balance: ${balance:,.2f}")
    test("Get balance", balance > 0, f"${balance:,.2f}")

    if balance <= 0:
        logger.error("No balance available! Cannot test orders.")
        logger.error("Make sure your testnet wallet has USDC.")
        return

    # ── Step 2: Get Price ────────────────────────────────────
    logger.info("\n--- Step 2: Get ETH Price ---")
    eth_mid = fetcher.get_mid_price("ETH")
    logger.info(f"  ETH mid price: ${eth_mid:,.2f}" if eth_mid else "  ETH: N/A")
    test("Get mid price", eth_mid is not None and eth_mid > 0, f"${eth_mid:,.2f}")

    # ── Step 3: Market Buy (Open Long) ───────────────────────
    logger.info("\n--- Step 3: Market BUY (Open Long ETH $50) ---")
    buy_result = executor.market_open_long("ETH", 50.0)
    buy_ok = buy_result is not None and buy_result.get("status") == "ok"
    test("Market BUY", buy_ok, str(buy_result)[:100] if buy_result else "None")

    if not buy_ok:
        logger.error("BUY failed — cannot continue remaining tests")
        show_results()
        return

    # Wait for order to settle
    time.sleep(3)

    # ── Step 4: Check Position ───────────────────────────────
    logger.info("\n--- Step 4: Check Position ---")
    pos = executor.get_position("ETH")
    pos_ok = pos is not None and pos["size"] > 0
    if pos:
        logger.info(f"  Position: size={pos['size']} entry=${pos['entry_px']:.2f}")
    test("Position exists", pos_ok, str(pos)[:100] if pos else "None")

    if not pos_ok:
        logger.error("No position found — cannot test TP/SL")
        show_results()
        return

    entry_px = pos["entry_px"]
    pos_size = abs(pos["size"])

    # ── Step 5: Set Take Profit ──────────────────────────────
    logger.info("\n--- Step 5: Set Take Profit (+5%) / Stop Loss (-3%) ---")
    tp_price = round(entry_px * 1.05, 2)
    sl_price = round(entry_px * 0.97, 2)
    logger.info(f"  Entry: ${entry_px:.2f}  TP: ${tp_price:.2f}  SL: ${sl_price:.2f}")

    tp_result, sl_result = executor.place_tp_sl("ETH", pos_size, tp_price, sl_price)

    tp_ok = tp_result is not None and tp_result.get("status") == "ok"
    sl_ok = sl_result is not None and sl_result.get("status") == "ok"
    test("Set Take Profit", tp_ok, str(tp_result)[:100] if tp_result else "None")
    test("Set Stop Loss", sl_ok, str(sl_result)[:100] if sl_result else "None")

    time.sleep(2)

    # ── Step 6: Check Open Orders ────────────────────────────
    logger.info("\n--- Step 6: Check Open Orders ---")
    try:
        open_orders = executor.info.open_orders(config["account_address"])
        eth_orders = [o for o in open_orders if o.get("coin") == "ETH"]
        logger.info(f"  Total open orders: {len(open_orders)}")
        logger.info(f"  ETH orders: {len(eth_orders)}")
        for o in eth_orders:
            logger.info(f"    {o.get('side', '?')} {o.get('sz', '?')} @ ${o.get('limitPx', '?')} | oid={o.get('oid', '?')}")
        test("Open orders exist", len(eth_orders) >= 2, f"{len(eth_orders)} ETH orders")
    except Exception as e:
        test("Open orders check", False, str(e))

    # ── Step 7: Cancel All Orders ────────────────────────────
    logger.info("\n--- Step 7: Cancel All Orders ---")
    cancel_ok = executor.cancel_all_orders("ETH")
    test("Cancel all orders", cancel_ok)

    time.sleep(2)

    # Verify cancellation
    try:
        remaining = executor.info.open_orders(config["account_address"])
        eth_remaining = [o for o in remaining if o.get("coin") == "ETH"]
        test("Orders cancelled", len(eth_remaining) == 0, f"{len(eth_remaining)} remaining")
    except Exception as e:
        test("Verify cancellation", False, str(e))

    # ── Step 8: Market Close (Sell) ──────────────────────────
    logger.info("\n--- Step 8: Market CLOSE (Sell ETH) ---")
    close_result = executor.market_close_long("ETH")
    close_ok = close_result is not None and close_result.get("status") == "ok"
    test("Market CLOSE", close_ok, str(close_result)[:100] if close_result else "None")

    time.sleep(3)

    # ── Step 9: Verify No Position ───────────────────────────
    logger.info("\n--- Step 9: Verify Position Closed ---")
    pos_after = executor.get_position("ETH")
    test("Position closed", pos_after is None, "No position" if pos_after is None else str(pos_after))

    # ── Step 10: Final Balance ───────────────────────────────
    logger.info("\n--- Step 10: Final Balance ---")
    final_balance = fetcher.get_account_value(config["account_address"])
    logger.info(f"  Starting:  ${balance:,.2f}")
    logger.info(f"  Final:     ${final_balance:,.2f}")
    logger.info(f"  Diff:      ${final_balance - balance:+,.2f} (fees + slippage)")

    show_results()


def show_results():
    logger.info("\n" + "=" * 60)
    logger.info("  TEST RESULTS")
    logger.info("=" * 60)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        logger.info(f"  {PASS if ok else FAIL} {name}")
    logger.info("-" * 60)
    logger.info(f"  {passed}/{total} tests passed")
    if passed == total:
        logger.info("  ALL FUNCTIONS WORKING!")
    else:
        logger.info(f"  {total - passed} test(s) FAILED")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
