"""Check all possible API balance endpoints for unified account."""
import json
from hyperliquid.info import Info
from hyperliquid.utils import constants

info = Info(constants.TESTNET_API_URL, skip_ws=True)
addr = "0xCfA19d8b0Fbf3FFe2a848f9576845Bba6a275839"

print("=== 1. user_state (perps) ===")
s = info.user_state(addr)
print(f"  accountValue: {s['marginSummary']['accountValue']}")
print(f"  crossAccountValue: {s['crossMarginSummary']['accountValue']}")
print(f"  positions: {len(s['assetPositions'])}")

print("\n=== 2. spot_user_state ===")
spot = info.spot_user_state(addr)
usdc = [b for b in spot['balances'] if b['coin'] == 'USDC'][0]
print(f"  USDC total: {usdc['total']}")

# Try different API calls
endpoints = [
    ("portfolioState", {"type": "portfolioState", "user": addr}),
    ("multiAssetAccountSummary", {"type": "multiAssetAccountSummary", "user": addr}),
    ("unifiedAccountSummary", {"type": "unifiedAccountSummary", "user": addr}),
    ("clearinghouseState", {"type": "clearinghouseState", "user": addr}),
    ("spotClearinghouseState", {"type": "spotClearinghouseState", "user": addr}),
]

for name, payload in endpoints:
    print(f"\n=== 3. {name} ===")
    try:
        r = info.post("/info", payload)
        if isinstance(r, dict):
            # Print just the interesting fields
            for k, v in r.items():
                if isinstance(v, (str, int, float, bool)):
                    print(f"  {k}: {v}")
                elif isinstance(v, dict):
                    print(f"  {k}: {json.dumps(v)}")
                elif isinstance(v, list) and len(v) > 0:
                    print(f"  {k}: [{len(v)} items] first={json.dumps(v[0])}")
                else:
                    print(f"  {k}: {v}")
        else:
            print(f"  {r}")
    except Exception as e:
        print(f"  Error: {e}")
