"""Local mock of (a) a BSC JSON-RPC node and (b) the Binance bulk-data host, fed by simulate_test.simulate().

Purpose: integration-test the REAL fetch/decode code paths (hex logs, batch RPC, eth_call ABI, zip/CSV
parsing) without network access.  Not needed for the real pilot.

    python mock_server.py --hours 6 &          # serves RPC on :8545 and Binance files on :8546
    python run_pilot.py --fork Maxwell --hours 3 --pools WBNB-USDT-500 --out /tmp/pilot_mock \
        --rpc http://127.0.0.1:8545 --binance-base http://127.0.0.1:8546/data/spot/daily
"""
from __future__ import annotations
import argparse, io, json, threading, time, zipfile, datetime as dt
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
import config as C
from simulate_test import simulate

Q96 = 2 ** 96
FORK_TS_MS = int(dt.datetime(2025, 6, 30, 5, 10, tzinfo=dt.timezone.utc).timestamp() * 1000)   # 2h40 after the configured guess (02:30): exercises the coarse scan


def to_word_signed(v: int) -> str:
    return hex(v % 2 ** 256)[2:].rjust(64, "0")


def build_world(hours: float, irregular: int = 0, seed: int = 7):
    blocks, swaps, cex, fork_block = simulate(hours=hours)
    # shift the relative simulation clock so that the regime switch lands on FORK_TS_MS
    switch_ms = int(blocks.loc[blocks.number == fork_block, "milli_ts"].iloc[0])
    shift = FORK_TS_MS - switch_ms
    blocks = blocks.copy(); blocks["milli_ts"] += shift
    if irregular:
        # emulate the chain falling behind schedule: `irregular` random blocks come 250 ms .. 4 periods late, and
        # every later block inherits the delay (timestamps never run ahead of the nominal schedule)
        rng = np.random.default_rng(seed)
        idx = rng.choice(np.arange(5, len(blocks) - 5), size=irregular, replace=False)
        delay = np.zeros(len(blocks), dtype=np.int64)
        for i in idx:
            delay[i:] += int(rng.choice([250, 500, 1500, 3000, 6000]))
        blocks["milli_ts"] = blocks["milli_ts"].to_numpy() + delay
        blocks["interval"] = blocks["milli_ts"].diff() / 1000
    blocks["timestamp"] = blocks["milli_ts"] // 1000
    cex = cex.copy(); cex["ts_ms"] += shift
    # real BSC orientation for WBNB/USDT: token0 = USDT (quote), token1 = WBNB (base)
    pool = C.KNOWN_POOLS["WBNB-USDT-500"].lower()   # same address as the fallback table, so the fallback path can be tested
    usdt, wbnb = C.TOKENS["USDT"][0].lower(), C.TOKENS["WBNB"][0].lower()
    logs_by_block: dict[int, list] = {}
    for r in swaps.itertuples():
        p = (int(r.sqrt_price_x96) / Q96) ** 2                     # quote per base in the simulator
        sqrt_p10 = int(np.sqrt(1.0 / p) * Q96)                     # token1/token0 = WBNB per USDT
        a0, a1 = int(r.amount1), int(r.amount0)                    # amount0 = USDT (quote), amount1 = WBNB (base)
        data = "0x" + "".join([to_word_signed(a0), to_word_signed(a1), to_word_signed(sqrt_p10),
                               to_word_signed(int(r.liquidity)), to_word_signed(0), to_word_signed(0), to_word_signed(0)])
        log = {"address": pool, "blockNumber": hex(r.block), "transactionHash": "0x" + f"{r.block:x}{r.log_index:x}".rjust(64, "0"),
               "logIndex": hex(r.log_index), "data": data,
               "topics": [C.TOPIC_SWAP_PCS_V3, "0x" + "ab".rjust(64, "0"), "0x" + "cd".rjust(64, "0")]}
        logs_by_block.setdefault(int(r.block), []).append(log)
    block_map = {int(b.number): b for b in blocks.itertuples()}
    return {"blocks": block_map, "logs": logs_by_block, "cex": cex, "pool": pool, "token0": usdt, "token1": wbnb,
            "fork_block": fork_block, "min": int(blocks.number.min()), "max": int(blocks.number.max())}


class RpcHandler(BaseHTTPRequestHandler):
    world = None
    batch_limit = 100        # public BSC nodes reject larger batches (the error the user hit with 200)
    header_method = True     # set False to emulate a gateway without eth_getHeaderByNumber
    chain_id = 0x38          # set to something else to emulate a misconfigured endpoint (must be dropped)
    factory_ok = True        # set False to emulate factory.getPool returning the zero address
    logs_policy = "ok"       # "ok" | "deny" (always -32005 limit exceeded, like bsc-dataseed) | "range:N" (max N blocks)
    history_from = 0         # blocks below this number answer null (emulates a pruned node)
    log_timestamps = False   # add a blockTimestamp field to logs (as Alchemy/NodeReal do)
    latency_ms = 0           # artificial delay per request (to see the effect of parallel workers)
    max_inflight = 0         # >0: answer HTTP 429 when more requests than this are in flight (rate limiting)
    slow_above = 0           # >0: eth_getLogs over more than this many blocks takes 3 s (tests time-out handling)
    _inflight = 0
    _lock = threading.Lock()

    def log_message(self, *a):  # silence
        pass

    def _block(self, n: int):
        if n < self.history_from:
            return None
        b = self.world["blocks"].get(n)
        if b is None:   # outside the simulated window: extrapolate like a real chain (3s before, 0.75s after)
            if n < self.world["min"]:
                ref = self.world["blocks"][self.world["min"]]; mts = int(ref.milli_ts) - (self.world["min"] - n) * 3000
            elif n > self.world["max"]:
                ref = self.world["blocks"][self.world["max"]]; mts = int(ref.milli_ts) + (n - self.world["max"]) * 750
            else:
                return None
            ms = mts % 1000
            return {"number": hex(n), "timestamp": hex(mts // 1000), "mixHash": "0x" + hex(ms)[2:].rjust(64, "0"),
                    "gasUsed": hex(0), "gasLimit": hex(70_000_000), "transactions": [], "miner": "0x" + "1" * 40}
        ms = int(b.milli_ts % 1000)
        return {"number": hex(n), "timestamp": hex(int(b.timestamp)), "mixHash": "0x" + hex(ms)[2:].rjust(64, "0"),
                "gasUsed": hex(1_000_000), "gasLimit": hex(70_000_000), "transactions": [], "miner": "0x" + "1" * 40}

    def _handle(self, req: dict):
        m, p = req["method"], req.get("params", [])
        if m == "eth_chainId":
            return hex(self.chain_id)
        if m == "eth_blockNumber":
            return hex(self.world["max"] + 10_000_000)   # pretend the chain continued
        if m == "eth_getBlockByNumber":
            return self._block(int(p[0], 16))
        if m == "eth_getHeaderByNumber":
            if not self.header_method:
                raise ValueError("the method eth_getHeaderByNumber does not exist/is not available")
            b = self._block(int(p[0], 16))
            if b is not None:
                b = {k: v for k, v in b.items() if k != "transactions"}
            return b
        if m == "eth_call":
            data = p[0]["data"]
            sel = data[:10]
            if sel == C.SEL_GET_POOL:
                return "0x" + (self.world["pool"][2:] if self.factory_ok else "").rjust(64, "0")
            if sel == C.SEL_TOKEN0:
                return "0x" + self.world["token0"][2:].rjust(64, "0")
            if sel == C.SEL_TOKEN1:
                return "0x" + self.world["token1"][2:].rjust(64, "0")
            if sel == C.SEL_FEE:
                return "0x" + hex(500)[2:].rjust(64, "0")
            if sel == C.SEL_SYMBOL:
                to = p[0]["to"].lower()
                sym = next((v[2] for v in C.TOKENS.values() if v[0].lower() == to), "???").encode()
                return "0x" + hex(32)[2:].rjust(64, "0") + hex(len(sym))[2:].rjust(64, "0") + sym.hex().ljust(64, "0")
            if sel == C.SEL_DECIMALS:
                return "0x" + hex(18)[2:].rjust(64, "0")
            return "0x"
        if m == "eth_getLogs":
            f = p[0]
            b0, b1 = int(f["fromBlock"], 16), int(f["toBlock"], 16)
            if self.logs_policy == "deny":
                raise ValueError("limit exceeded")
            if self.logs_policy.startswith("range:") and b1 - b0 + 1 > int(self.logs_policy.split(":")[1]):
                raise ValueError("limit exceeded")
            if self.logs_policy == "alchemy" and b1 - b0 + 1 > 10:
                raise ValueError("Under the Free tier plan, eth_getLogs is limited to a 10 block range. Based on your parameters and the response size limit, this block range should work: [0x0, 0x9]")
            if b1 - b0 > 5000:
                raise ValueError("exceed maximum block range: 5000")
            if self.slow_above and b1 - b0 + 1 > self.slow_above:
                time.sleep(3.0)
            t0 = f["topics"][0]
            out = []
            for n in range(b0, b1 + 1):
                for lg in self.world["logs"].get(n, []):
                    if lg["address"] == f["address"].lower() and lg["topics"][0] == t0:
                        if self.log_timestamps:
                            lg = dict(lg, blockTimestamp=hex(int(self.world["blocks"][n].timestamp)))
                        out.append(lg)
            return out
        raise ValueError(f"unknown method {m}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n))
        if self.latency_ms:
            time.sleep(self.latency_ms / 1000.0)
        if self.max_inflight:
            with RpcHandler._lock:
                busy = RpcHandler._inflight >= self.max_inflight
                if not busy:
                    RpcHandler._inflight += 1
            if busy:
                self.send_response(429); self.send_header("Content-Length", "0"); self.end_headers(); return
            try:
                return self._do_post_body(body)
            finally:
                with RpcHandler._lock:
                    RpcHandler._inflight -= 1
        return self._do_post_body(body)

    def _do_post_body(self, body):
        if isinstance(body, list) and len(body) > self.batch_limit:
            out = json.dumps([{"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "batch too large"}}]).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out)))
            self.end_headers(); self.wfile.write(out); return
        def one(req):
            try:
                return {"jsonrpc": "2.0", "id": req["id"], "result": self._handle(req)}
            except Exception as e:  # noqa
                return {"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32000, "message": str(e)}}
        resp = [one(r) for r in body] if isinstance(body, list) else one(body)
        out = json.dumps(resp).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out)))
        self.end_headers(); self.wfile.write(out)


class BinanceHandler(BaseHTTPRequestHandler):
    world = None

    def log_message(self, *a):
        pass

    def do_GET(self):
        # /data/spot/daily/klines/BNBUSDT/1s/BNBUSDT-1s-2025-06-30.zip
        # /data/spot/daily/aggTrades/BNBUSDT/BNBUSDT-aggTrades-2025-06-30.zip
        parts = self.path.strip("/").split("/")
        agg = "-aggTrades-" in parts[-1]
        try:
            day = parts[-1].split("-aggTrades-" if agg else "-1s-")[1].replace(".zip", "")
            d0 = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp() * 1000)
        except Exception:  # noqa
            self.send_response(404); self.end_headers(); return
        cex = self.world["cex"]
        sel = cex[(cex.ts_ms >= d0) & (cex.ts_ms < d0 + 86_400_000)]
        if len(sel) == 0:
            self.send_response(404); self.end_headers(); return
        buf = io.StringIO()
        if agg:
            # synthetic trades inside each second: three trades at 120 / 480 / 999 ms, prices interpolated between the
            # previous and the current 1s close (the last trade of the second equals the close), MICROsecond stamps
            prev = None; aid = 0
            for r in sel.itertuples():
                c = float(r.close); p0 = c if prev is None else prev
                for off in (120, 480, 999):
                    px = p0 + (c - p0) * off / 999.0
                    ts_us = (int(r.ts_ms) + off) * 1000
                    buf.write(f"{aid},{px:.8f},0.5,{aid},{aid},{ts_us},{aid % 2 == 0},True\n"); aid += 1
                prev = c
        else:
          for r in sel.itertuples():
            # open_time in MICROseconds (as in 2025+ Binance files), 12 columns
            buf.write(f"{int(r.ts_ms) * 1000},{r.close},{r.close},{r.close},{r.close},1,{int(r.ts_ms) * 1000 + 999999},1,1,0.5,0.5,0\n")
        zb = io.BytesIO()
        with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(parts[-1].replace(".zip", ".csv"), buf.getvalue())
        out = zb.getvalue()
        self.send_response(200); self.send_header("Content-Type", "application/zip"); self.send_header("Content-Length", str(len(out)))
        self.end_headers(); self.wfile.write(out)

    def do_HEAD(self):
        self.send_response(200); self.end_headers()


def serve(world, rpc_port=8545, bin_port=8546):
    RpcHandler.world = world; BinanceHandler.world = world
    s1 = ThreadingHTTPServer(("127.0.0.1", rpc_port), RpcHandler)
    s2 = ThreadingHTTPServer(("127.0.0.1", bin_port), BinanceHandler)
    threading.Thread(target=s1.serve_forever, daemon=True).start()
    threading.Thread(target=s2.serve_forever, daemon=True).start()
    return s1, s2


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--hours", type=float, default=6); ap.add_argument("--rpc-port", type=int, default=8545); ap.add_argument("--bin-port", type=int, default=8546)
    ap.add_argument("--batch-limit", type=int, default=100); ap.add_argument("--no-header", action="store_true")
    ap.add_argument("--chain-id", type=lambda x: int(x, 0), default=0x38); ap.add_argument("--no-factory", action="store_true")
    ap.add_argument("--logs-policy", default="ok"); ap.add_argument("--history-from", type=int, default=0)
    ap.add_argument("--log-timestamps", action="store_true")
    ap.add_argument("--irregular", type=int, default=0, help="inject N late blocks (tests timestamp bisection)")
    ap.add_argument("--latency-ms", type=int, default=0, help="artificial delay per RPC request")
    ap.add_argument("--max-inflight", type=int, default=0, help="HTTP 429 beyond this many concurrent requests")
    ap.add_argument("--slow-above", type=int, default=0, help="eth_getLogs over more blocks than this takes 3 s")
    a = ap.parse_args()
    RpcHandler.latency_ms = a.latency_ms; RpcHandler.max_inflight = a.max_inflight; RpcHandler.slow_above = a.slow_above
    RpcHandler.logs_policy = a.logs_policy; RpcHandler.history_from = a.history_from; RpcHandler.log_timestamps = a.log_timestamps
    RpcHandler.batch_limit = a.batch_limit; RpcHandler.header_method = not a.no_header
    RpcHandler.chain_id = a.chain_id; RpcHandler.factory_ok = not a.no_factory
    w = build_world(a.hours, a.irregular)
    print(f"mock world: blocks {w['min']}..{w['max']}, fork block {w['fork_block']}, pool {w['pool']}")
    serve(w, a.rpc_port, a.bin_port)
    print(f"RPC on http://127.0.0.1:{a.rpc_port}  Binance on http://127.0.0.1:{a.bin_port}/data/spot/daily  (Ctrl-C to stop)")
    threading.Event().wait()
