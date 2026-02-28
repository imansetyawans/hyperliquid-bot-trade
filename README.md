# Hyperliquid Trading Bot

A Python-based algorithmic trading bot designed for [Hyperliquid](https://hyperliquid.xyz/). It supports automated **Long** and **Short** strategies based on technical indicators such as Moving Averages, MACD, and RSI across multiple timeframes.

## Features

- **Long & Short Capabilities**: Run multiple strategies simultaneously targeting different market directions with dedicated sizing and independent logic loops.
- **Direction-Agnostic Execution**: The execution and data collection engines are perfectly decoupled, guaranteeing zero cross-contamination between Long and Short logic.
- **Paper Trading Engine**: A robust built-in simulation environment for forward-testing strategies safely.
- **Dynamic TP/SL**: Calculates and deploys Take Profit and Stop Loss limits accurately based on your percentage offsets automatically upon trade entry.
- **Strict Size Parity**: Safely operates without accidentally liquidating un-associated positions or manual trades by strictly interacting only with the sizes logged by its own engine.
- **Risk Management**: Enforces maximum daily drawdowns, cooldown windows between trades, and maximum open position limit checks.

---

## Installation

1. Clone or clone this repository.
2. Install dependencies:
   ```bash
   pip install pandas numpy hyperliquid eth_account
   ```
3. Copy the configuration template:
   ```bash
   cp config.example.json config.json
   ```
4. Enter your Hyperliquid EVM wallet address and Secret Key in `config.json`. **Never commit `config.json` to version control.**

---

## Configuration (`config.json`)

Settings are decoupled by `strategy key` (e.g., `ETH` vs `ETH_SHORT`).

```json
{
  "secret_key": "YOUR_PRIVATE_KEY",
  "account_address": "YOUR_WALLET_ADDRESS",
  "use_testnet": true,
  "paper_trade": true,
  "log_level": "INFO",
  "risk": {
      "max_daily_loss_pct": 5.0,
      "max_open_positions": 2,
      "min_trade_interval_min": 5
  },
  "strategies": {
      "ETH_LONG": {
          "symbol": "ETH",
          "direction": "long",
          "enabled": true,
          "capital_pct": 0.3,
          "leverage": 20,
          "tp_pct": 0.04,
          "sl_pct": 0.06,
          "regime_rsi": 55,
          "entry_rsi": 55,
          "fc_rsi": 40
      },
      "ETH_SHORT": {
          "symbol": "ETH",
          "direction": "short",
          "enabled": true,
          "capital_pct": 0.3,
          "leverage": 20,
          "tp_pct": 0.04,
          "sl_pct": 0.06,
          "regime_rsi": 40,
          "entry_rsi": 45,
          "fc_rsi": 55
      }
  }
}
```

### Key Parameters
- `direction`: Set to `"long"` or `"short"`. 
- `capital_pct`: The % of your total account balance to use as margin per trade (0.3 = 30%).
- `leverage`: Cross leverage applied to the margin.
- `tp_pct` / `sl_pct`: Distance from entry price to trigger Take Profit / Stop Loss.
- `use_testnet`: `true` routes to the testnet API, `false` targets Mainnet.
- `paper_trade`: `true` executes trades against a simulated wallet, `false` sends live API orders.

---

## Running the Bot

Always ensure you only have **one** instance of python running to avoid ghost instances double-submitting sizes. 

1. Navigate to the bot directory:
```bash
cd hyperliquid-bot
```

2. Run the bot:
```bash
python bot.py
```

### Logging
Logs are saved in the `/logs/` directory and stamped by date (e.g. `bot_2026-02-28.log`). 

---

## Trading Logic Breakdown

### Regime Detection (Trend Filter)
Checks the 4-Hour chart before evaluating lower timeframes:
* **Longs (`BULL`)**: 4H MACD > MACD Signal line **AND** 4H RSI > `regime_rsi`.
* **Shorts (`BEAR`)**: 4H MACD < MACD Signal line **AND** 4H RSI < `regime_rsi`.

### Entry Conditions (30 Min Chart)
If the 4H Regime is valid, the 30-minute chart evaluates for entry:
* **Longs**: Price > all Moving Averages (7, 14, 28, 111) **AND** 30m RSI > `entry_rsi`.
* **Shorts**: Price < all Moving Averages (7, 14, 28, 111) **AND** 30m RSI < `entry_rsi`.

### Force Close Conditions (30 Min Chart)
Sometimes trends reverse before hitting the TP or SL boundaries. 
* **Longs**: Force Closes if Price drops < all Moving Averages **AND** RSI drops < `fc_rsi`.
* **Shorts**: Force Closes if Price rises > all Moving Averages **AND** RSI rises > `fc_rsi`.

---

## Disclaimer
Algorithmic trading carries significant risk. Always utilize Testnet branches (`use_testnet: true`) and Paper Trading Simulators (`paper_trade: true`) to thoroughly validate any new configurations before putting live capital at risk.
