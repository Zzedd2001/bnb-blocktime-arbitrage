"""
Pilot configuration for "block time and DEX arbitrage/LVR on BNB Chain" (direction 1b).

All addresses are BNB Smart Chain (BSC) mainnet.  Pool addresses are NOT hard-coded:
they are resolved on the fly from the PancakeSwap v3 factory with getPool(tokenA, tokenB, fee)
and cross-checked with token0()/token1()/fee() calls (see rpc.py:resolve_pool).
"""

# ---- Public JSON-RPC endpoints (free, rate limited).  The client rotates on errors. ----
# Official bsc-dataseed nodes are fast for headers/eth_call but reject eth_getLogs ("limit exceeded", -32005);
# the others are probed for eth_getLogs at run time and only capable ones are used for logs.
RPC_ENDPOINTS = [
    "https://bsc-dataseed.bnbchain.org",
    "https://bsc-dataseed1.binance.org",
    "https://bsc-dataseed2.bnbchain.org",
    "https://bsc-rpc.publicnode.com",
    "https://bsc.drpc.org",
    "https://1rpc.io/bnb",
    "https://bsc-mainnet.public.blastapi.io",
    "https://bsc.meowrpc.com",
    "https://bsc.blockrazor.xyz",
    "https://rpc-bsc.48.club",
    "https://endpoints.omniatech.io/v1/bsc/mainnet/public",
    "https://api.zan.top/bsc-mainnet",
    "https://bsc-pokt.nodies.app",
    "https://bnb.rpc.subquery.network/public",
    "https://binance.llamarpc.com",
]
CHAIN_ID = 0x38                   # every endpoint is checked with eth_chainId before use; others are dropped
HISTORY_PROBE_BLOCK = 48_000_000  # ~April 2025: endpoints that return null for this block have pruned history -> dropped
# Endpoints used ONLY for eth_getLogs (historical logs need a provider with full history).  Free-tier block
# ranges per query (2026-09): NodeReal up to 50,000 blocks / 50k records (best), Alchemy 10 blocks, QuickNode 5.
# Also settable with --logs-rpc or the BSC_LOGS_RPC environment variable.
LOGS_RPC_ENDPOINTS: list[str] = []
# Max block span per eth_getLogs call on public nodes (most cap at 5,000; we stay well below
# and halve automatically on "limit exceeded" errors).
LOGS_CHUNK_BLOCKS = 1000
# Dedicated (keyed) log endpoints allow much larger ranges (NodeReal: 50,000 blocks / 50k records per call) and
# charge per CALL (NodeReal: 50 CU), so they start larger and may probe up further; still halved on any limit error.
LOGS_CHUNK_BLOCKS_KEYED = 8000
LOGS_CHUNK_MAX_KEYED = 50000      # NodeReal's documented maximum range; sparse pools then need ~100 calls per 5M blocks
REQUEST_SLEEP_SEC = 0.15          # be polite to public nodes
BATCH_SIZE = 100                  # JSON-RPC batch size for header fetches (halved automatically on rejection)
FORK_DETECT_HOURS = 2.0           # dense header window around the announced fork time (for exact fork block)
FORK_SCAN_RANGE_H = (-6.0, 30.0)  # if not found there: coarse scan (30-block samples every 20 min) over this range
FORK_SCAN_STEP_MIN = 20
SAMPLE_RUN_BLOCKS = 120           # (legacy) consecutive blocks per hourly run when headers were the only timestamp source
ANCHOR_RUN_BLOCKS = 2             # consecutive headers fetched at each anchor (2 -> one measured interval per anchor)
ANCHORS_PER_HOUR = 6              # anchors per hour (every 10 min); every other block's timestamp is reconstructed and
                                  # verified span by span from BSC's fixed block period (find_blocks.fill_timestamps)
MAX_RETRIES = 6

# ---- PancakeSwap v3 (BSC) ----
PCS_V3_FACTORY = "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865"
# keccak256("Swap(address,address,int256,int256,uint160,uint128,int24,uint128,uint128)")
TOPIC_SWAP_PCS_V3 = "0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83"
# keccak256("Swap(address,address,int256,int256,uint160,uint128,int24)")  (Uniswap v3 layout, for controls)
TOPIC_SWAP_UNI_V3 = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
TOPIC_MINT_V3 = "0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde"
TOPIC_BURN_V3 = "0x0c396cd989a39f4459b5fa1aed6a9a8dcdbc45908acfd67e028cd568da98982c"
SEL_GET_POOL = "0x1698ee82"   # getPool(address,address,uint24)
SEL_TOKEN0 = "0x0dfe1681"
SEL_TOKEN1 = "0xd21220a7"
SEL_FEE = "0xddca3f43"
SEL_SYMBOL = "0x95d89b41"     # ERC-20 symbol()
SEL_DECIMALS = "0x313ce567"   # ERC-20 decimals()

# ---- Tokens (BSC) ----
# (address, decimals, expected on-chain symbol).  run_pilot.py verifies symbol()/decimals() on chain at
# start-up and stops if anything differs, so a wrong address can never silently produce wrong data.
TOKENS = {
    "WBNB": ("0xbb4CdB9CBd36B01bD1cBaEbf2De08d9173bc095c", 18, "WBNB"),
    "USDT": ("0x55d398326f99059fF775485246999027B3197955", 18, "USDT"),
    "USDC": ("0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", 18, "USDC"),
    "ETH":  ("0x2170Ed0880ac9A755fd29B2688956BD959F933F8", 18, "ETH"),
    "BTCB": ("0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c", 18, "BTCB"),
    "CAKE": ("0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82", 18, "Cake"),
}

# ---- Fallback pool addresses (used only if factory.getPool fails; verified on chain via token0/token1/fee) ----
KNOWN_POOLS = {
    "WBNB-USDT-500": "0x36696169C63e42cd08ce11f5deeBbCeBae652050",
    "WBNB-USDT-100": "0x172fcD41E0913e95784454622d1c3724f546f849",
}

# ---- Pools: (base, quote, fee in hundredths of a bip; 500 = 0.05%), Binance symbol ----
# "binance" is either one spot symbol (quote = USDT) or [base_symbol, quote_symbol] for a cross-rate
# (e.g. CAKE/WBNB = CAKEUSDT / BNBUSDT).  Pools that do not exist on chain are skipped with a warning.
# The pool's token0/token1 order is resolved on chain; "base" is the asset whose price we track.
PILOT_POOLS = [
    {"name": "WBNB-USDT-500",   "base": "WBNB", "quote": "USDT", "fee": 500,   "binance": "BNBUSDT"},
    {"name": "WBNB-USDT-100",   "base": "WBNB", "quote": "USDT", "fee": 100,   "binance": "BNBUSDT"},   # gamma = 1 bp: largest predicted effect
    {"name": "ETH-USDT-500",    "base": "ETH",  "quote": "USDT", "fee": 500,   "binance": "ETHUSDT"},
    {"name": "BTCB-USDT-500",   "base": "BTCB", "quote": "USDT", "fee": 500,   "binance": "BTCUSDT"},
    {"name": "USDC-USDT-100",   "base": "USDC", "quote": "USDT", "fee": 100,   "binance": "USDCUSDT"},  # sigma ~ 0: placebo pair
    {"name": "CAKE-WBNB-2500",  "base": "CAKE", "quote": "WBNB", "fee": 2500,  "binance": ["CAKEUSDT", "BNBUSDT"]},  # gamma = 25 bp
    {"name": "WBNB-USDT-10000", "base": "WBNB", "quote": "USDT", "fee": 10000, "binance": "BNBUSDT"},   # gamma = 100 bp: placebo fee tier
]
FULL_SAMPLE_POOLS = [p["name"] for p in PILOT_POOLS]

# ---- Block-time regime changes on BSC mainnet (UTC).  Exact fork blocks are detected from timestamps
# by find_blocks.py (the detector looks for the first block after which the median interval halves). ----
FORKS = {
    # name: (announced activation time UTC, block interval before, after)
    "Lorentz": ("2025-04-29T05:05:00Z", 3.0, 1.5),
    "Maxwell": ("2025-06-30T02:30:00Z", 1.5, 0.75),    # located on chain 2026-09-10: block 52,337,091 at 02:30:01 UTC
    "Fermi":   ("2026-01-14T02:30:00Z", 0.75, 0.45),
}

# ---- Binance public bulk data ----
BINANCE_VISION = "https://data.binance.vision/data/spot/daily"
