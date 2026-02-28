"""Quick integration test — verifies all modules work together."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from indicators import compute_rsi, compute_macd, compute_mas
from strategy import Strategy
from paper_trader import PaperTrader
from position_manager import PositionManager
from risk import RiskManager
import pandas as pd
import numpy as np

def test():
    ok = 0

    # 1. Indicators
    np.random.seed(42)
    close = pd.Series(np.random.randn(200).cumsum() + 100)
    rsi = compute_rsi(close, 14)
    macd, sig = compute_macd(close, 12, 26, 9)
    mas = compute_mas(close, [7, 14, 28, 111])
    assert not np.isnan(rsi.iloc[-1]), "RSI is NaN"
    assert not np.isnan(macd.iloc[-1]), "MACD is NaN"
    assert 111 in mas, "MA111 missing"
    print(f"[OK] Indicators: RSI={rsi.iloc[-1]:.2f}, MACD={macd.iloc[-1]:.4f}")
    ok += 1

    # 2. Strategy TP/SL calc
    cfg = {"tp_pct": 0.18, "sl_pct": 0.10, "capital_pct": 0.3,
           "regime_rsi": 55, "entry_rsi": 55, "fc_rsi": 45}
    strat = Strategy("ETH", cfg)
    tp, sl = strat.calc_tp_sl(3000.0)
    assert tp == 3540.0, f"TP wrong: {tp}"
    assert sl == 2700.0, f"SL wrong: {sl}"
    print(f"[OK] Strategy TP/SL: TP={tp}, SL={sl}")
    ok += 1

    # 3. Paper trader
    pt = PaperTrader(10000.0)
    res = pt.market_open_long("ETH", 3000.0, 3000.0)
    assert res is not None, "Paper open failed"
    assert pt.has_position("ETH"), "No paper position"
    pt.place_tp_sl("ETH", 1.0, 3540.0, 2700.0)
    assert pt.check_tp_sl("ETH", 3100.0) is None, "Should not trigger"
    assert pt.check_tp_sl("ETH", 3600.0) == "tp", "Should trigger TP"
    res2 = pt.market_close_long("ETH", 3540.0)
    assert res2 is not None, "Paper close failed"
    assert not pt.has_position("ETH"), "Position should be closed"
    print(f"[OK] Paper trader: open/close/TP-SL check works")
    ok += 1

    # 4. Risk manager
    rm = RiskManager({"risk": {"max_daily_loss_pct": 5.0, "max_open_positions": 2, "min_trade_interval_min": 0}})
    allowed, reason = rm.can_open_trade(10000, 0)
    assert allowed, f"Should be allowed: {reason}"
    size = rm.calculate_position_size(10000, 0.3)
    assert size == 3000.0, f"Size wrong: {size}"
    # Test max positions
    allowed2, _ = rm.can_open_trade(10000, 2)
    assert not allowed2, "Should block at max positions"
    print(f"[OK] Risk manager: sizing and limits work")
    ok += 1

    # 5. Position manager
    pm = PositionManager()
    pm.open_position("ETH", 3000.0, 3000.0, 3540.0, 2700.0)
    assert pm.has_position("ETH"), "Should have position"
    trade = pm.close_position("ETH", 3200.0, "Take Profit")
    assert trade is not None, "Trade log missing"
    assert trade["pnl_pct"] > 0, "Should be profitable"
    assert not pm.has_position("ETH"), "Position should be closed"
    print(f"[OK] Position manager: open/close/log works, PnL={trade['pnl_pct']:.2f}%")
    ok += 1

    print(f"\n=== ALL {ok}/5 TESTS PASSED ===")

if __name__ == "__main__":
    test()
