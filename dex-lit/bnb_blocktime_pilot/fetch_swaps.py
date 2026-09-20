"""Step 2: pull PancakeSwap v3 Swap (and optionally Mint/Burn) events for the pilot pools via
eth_getLogs on public nodes, decode them, and save one parquet per pool.

Usage:
    python fetch_swaps.py --from-block 51000000 --to-block 51500000 --pools WBNB-USDT-500 ETH-USDT-500 --out data/
    python fetch_swaps.py --from-block ... --to-block ... --all --liquidity   # also Mint/Burn

Throughput on public nodes: ~2,000 blocks per call, ~3-6 calls/s -> a 30-day window at 0.45s blocks
(~5.8M blocks) is ~3,000 calls per pool, i.e. 10-20 minutes per pool.  Split long windows into
several --from-block/--to-block runs; analyze_pilot.py globs all files of a pool.
"""
from __future__ import annotations
import argparse, os, sys, time
import pandas as pd
import config as C
from rpc import Rpc, RpcError, resolve_pool, decode_words, word_to_int

Q96 = 2 ** 96


def decode_swap(log: dict, layout: str = "pcs") -> dict:
    """Decode a v3 Swap log.  PancakeSwap v3 appends protocolFeesToken0/1 to the Uniswap layout."""
    w = decode_words(log["data"])
    amount0 = word_to_int(w[0], True)
    amount1 = word_to_int(w[1], True)
    sqrt_p = word_to_int(w[2], False)
    liq = word_to_int(w[3], False)
    tick = word_to_int(w[4], True)
    # int24 tick is sign-extended to 256 bits in the ABI; word_to_int handles that.
    # uint256/int256 values exceed int64: store them as decimal STRINGS (parquet-safe, lossless);
    # analyze_pilot.to_f64() converts them to float64 when needed.
    rec = {"block": int(log["blockNumber"], 16), "tx": log["transactionHash"],
           "log_index": int(log["logIndex"], 16),
           "sender": "0x" + log["topics"][1][-40:], "recipient": "0x" + log["topics"][2][-40:],
           "amount0": str(amount0), "amount1": str(amount1), "sqrt_price_x96": str(sqrt_p),
           "liquidity": str(liq), "tick": tick}
    if layout == "pcs" and len(w) >= 7:
        rec["protocol_fee0"] = str(word_to_int(w[5], False))
        rec["protocol_fee1"] = str(word_to_int(w[6], False))
    bt = log.get("blockTimestamp")                       # Alchemy/NodeReal-style extension field (seconds, hex)
    rec["block_ts"] = int(bt, 16) if isinstance(bt, str) and bt.startswith("0x") else (int(bt) if bt else -1)
    return rec


def decode_mint_burn(log: dict, kind: str) -> dict:
    w = decode_words(log["data"])
    if kind == "mint":   # Mint(sender, owner idx, tickLower idx, tickUpper idx, amount, amount0, amount1)
        return {"block": int(log["blockNumber"], 16), "tx": log["transactionHash"], "kind": "mint",
                "owner": "0x" + log["topics"][1][-40:],
                "tick_lower": word_to_int(log["topics"][2], True), "tick_upper": word_to_int(log["topics"][3], True),
                "liquidity_delta": str(word_to_int(w[1], False)), "amount0": str(word_to_int(w[2], False)),
                "amount1": str(word_to_int(w[3], False))}
    return {"block": int(log["blockNumber"], 16), "tx": log["transactionHash"], "kind": "burn",
            "owner": "0x" + log["topics"][1][-40:],
            "tick_lower": word_to_int(log["topics"][2], True), "tick_upper": word_to_int(log["topics"][3], True),
            "liquidity_delta": str(-word_to_int(w[0], False)), "amount0": str(word_to_int(w[1], False)),
            "amount1": str(word_to_int(w[2], False))}


def fetch_range(rpc: Rpc, pool: str, topics: list, b0: int, b1: int, chunk: int | None = None, log=None,
                workers: int = 1, on_chunk=None) -> list:
    """eth_getLogs over [b0, b1] on log-capable endpoints with adaptive chunking (see Rpc.get_logs_adaptive);
    workers > 1 fetches chunks concurrently; on_chunk(logs) consumes each chunk as it arrives (then [] is returned)."""
    return rpc.get_logs_adaptive(pool, topics, b0, b1, log or (lambda m: print(m, file=sys.stderr)),
                                 workers=workers, on_chunk=on_chunk)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-block", type=int, required=True)
    ap.add_argument("--to-block", type=int, required=True)
    ap.add_argument("--pools", nargs="*", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--liquidity", action="store_true", help="also fetch Mint/Burn events")
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rpc = Rpc()
    wanted = [p for p in C.PILOT_POOLS if a.all or p["name"] in a.pools]
    for p in wanted:
        base, quote = C.TOKENS[p["base"]], C.TOKENS[p["quote"]]
        info = resolve_pool(rpc, base[0], quote[0], p["fee"])
        print(f"{p['name']}: pool {info['pool']} token0={info['token0']} token1={info['token1']}", file=sys.stderr)
        t0 = time.time()
        logs = fetch_range(rpc, info["pool"], [C.TOPIC_SWAP_PCS_V3], a.from_block, a.to_block, C.LOGS_CHUNK_BLOCKS)
        df = pd.DataFrame([decode_swap(l) for l in logs])
        meta = {"pool": info["pool"], "token0": info["token0"], "token1": info["token1"], "fee": info["fee"],
                "base_is_token0": info["token0"].lower() == base[0].lower(),
                "dec0": base[1] if info["token0"].lower() == base[0].lower() else quote[1],
                "dec1": quote[1] if info["token0"].lower() == base[0].lower() else base[1]}
        for k, v in meta.items():
            df[k] = v
        path = os.path.join(a.out, f"swaps_{p['name']}_{a.from_block}_{a.to_block}.parquet")
        df.to_parquet(path, index=False)
        print(f"  -> {len(df)} swaps in {time.time() - t0:.0f}s -> {path}", file=sys.stderr)
        if a.liquidity:
            ml = fetch_range(rpc, info["pool"], [[C.TOPIC_MINT_V3, C.TOPIC_BURN_V3]], a.from_block, a.to_block, C.LOGS_CHUNK_BLOCKS)
            rows = [decode_mint_burn(l, "mint" if l["topics"][0] == C.TOPIC_MINT_V3 else "burn") for l in ml]
            pd.DataFrame(rows).to_parquet(os.path.join(a.out, f"liq_{p['name']}_{a.from_block}_{a.to_block}.parquet"), index=False)


if __name__ == "__main__":
    main()
