"""Minimal JSON-RPC client for public BSC nodes: endpoint rotation, retries, batching, and a few
ABI helpers (no web3 dependency).  Everything here is plain `requests`."""
from __future__ import annotations
import time, random, json, threading, itertools
from dataclasses import dataclass
import requests
import config as C


class RpcError(Exception):
    pass


def clean_url(u: str) -> str:
    """Strip whitespace, quotes and the <…> placeholder brackets people copy from instructions."""
    return u.strip().strip("'\"").replace("<", "").replace(">", "")


def suggested_chunk(msg: str) -> int | None:
    """Parse a provider's stated block-range limit out of an error message, e.g.
    Alchemy: 'Under the Free tier plan, eth_getLogs is limited to a 10 block range'
    QuickNode: '... block range limit ... 5 blocks'  NodeReal/BSC: 'exceed maximum block range: 5000'."""
    import re
    m = re.search(r"(\d[\d,]*)\s*[- ]?block", msg, re.I) or re.search(r"block range[^\d]{0,20}(\d[\d,]*)", msg, re.I)
    if m:
        n = int(m.group(1).replace(",", ""))
        return n if 1 <= n <= 1_000_000 else None
    return None


def redact(url: str) -> str:
    """Hide API keys in log output: any path/query segment of 20+ chars is replaced by '…'."""
    import re
    return re.sub(r"[A-Za-z0-9_\-]{20,}", "…", url)


@dataclass
class Rpc:
    endpoints: list[str] | None = None
    timeout: int = 30

    def __post_init__(self):
        self.endpoints = [clean_url(u) for u in (self.endpoints or C.RPC_ENDPOINTS)]
        import os
        if os.environ.get("BSC_RPC_TIMEOUT"):          # mainly for tests (eth_getLogs uses 2x this)
            self.timeout = int(os.environ["BSC_RPC_TIMEOUT"])
        self.pruned = set()
        self._i = random.randrange(len(self.endpoints))
        self._id = 0
        self._ids = itertools.count(1)
        self.session = requests.Session()
        self._tls = threading.local()          # one requests.Session per thread for the parallel fetchers
        self._lock = threading.Lock()

    def _session(self) -> requests.Session:
        s = getattr(self._tls, "session", None)
        if s is None:
            s = self._tls.session = requests.Session()
        return s

    @property
    def url(self):
        return self.endpoints[self._i % len(self.endpoints)]

    def rotate(self):
        self._i += 1
        for _ in range(len(self.endpoints)):          # skip endpoints known to lack history
            if self.url not in self.pruned:
                break
            self._i += 1

    def call(self, method: str, params: list, retries: int | None = None):
        retries = C.MAX_RETRIES if retries is None else retries
        last = None
        for attempt in range(retries):
            self._id += 1
            body = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
            try:
                r = self.session.post(self.url, json=body, timeout=self.timeout)
                if r.status_code == 429 or r.status_code >= 500:
                    raise RpcError(f"HTTP {r.status_code}")
                j = r.json()
                if "error" in j:
                    msg = str(j["error"])
                    # range/limit errors must be handled by the caller (chunk halving); surface them
                    if any(k in msg.lower() for k in self.LIMIT_WORDS):
                        raise RpcError("LIMIT:" + msg[:200])
                    raise RpcError(msg)
                time.sleep(C.REQUEST_SLEEP_SEC)
                return j["result"]
            except (requests.RequestException, RpcError, ValueError) as e:
                last = e
                if isinstance(e, RpcError) and str(e).startswith("LIMIT:"):
                    raise
                self.rotate()
                time.sleep(min(2 ** attempt * 0.5, 8))
        raise RpcError(f"{method} failed after {retries} retries: {last}")

    LIMIT_WORDS = ("limit", "range", "too many", "exceed", "batch", "too large", "payload", "more than", "response size", "results")
    # rate limiting / quota messages (NodeReal CUPS, Alchemy compute units, generic 429s): these must NOT shrink the
    # block range — the endpoint just needs to cool down for a moment
    RATE_WORDS = ("429", "rate limit", "ratelimit", "rate-limit", "too many requests", "compute unit", "cups", "quota",
                  "throttl", "daily", "per second", "capacity", "overloaded", "credits")

    @classmethod
    def classify_error(cls, msg: str) -> str:
        """'RATE:' for rate limiting / quota, 'LIMIT:' for block-range / result-size limits, else '' (transport/other)."""
        low = msg.lower()
        if any(k in low for k in cls.RATE_WORDS):
            return "RATE:"
        if any(k in low for k in cls.LIMIT_WORDS):
            return "LIMIT:"
        return ""

    def call_batch(self, calls: list[tuple[str, list]], retries: int | None = None) -> list:
        """JSON-RPC batch (one HTTP request, many calls).
        Raises RpcError("LIMIT:...") when the node rejects/truncates the batch (caller shrinks the batch),
        RpcError("ITEM:...") for a per-item error, and retries transport errors with endpoint rotation."""
        retries = C.MAX_RETRIES if retries is None else retries
        last = None
        for attempt in range(retries):
            body = []
            for m, p in calls:
                self._id += 1
                body.append({"jsonrpc": "2.0", "id": self._id, "method": m, "params": p})
            try:
                r = self.session.post(self.url, json=body, timeout=self.timeout * 2)
                if r.status_code == 413:
                    raise RpcError("LIMIT:HTTP 413 payload too large")
                if r.status_code == 429 or r.status_code >= 500:
                    raise RpcError(f"HTTP {r.status_code}")
                j = r.json()
                if isinstance(j, dict):                       # whole batch rejected with a single object
                    raise RpcError("LIMIT:" + str(j.get("error", j))[:200])
                items = [x for x in j if isinstance(x, dict)]
                by_id = {x.get("id"): x for x in items}
                if any(x.get("id") is None for x in items) or len(by_id) < len(body):
                    errs = [x.get("error") for x in items if "error" in x]
                    raise RpcError("LIMIT:batch rejected/truncated: " + str(errs[:1])[:200])
                out = []
                for x in body:
                    res = by_id[x["id"]]
                    if "error" in res:
                        msg = str(res["error"])
                        if any(k in msg.lower() for k in self.LIMIT_WORDS):
                            raise RpcError("LIMIT:" + msg[:200])
                        raise RpcError("ITEM:" + msg[:200])
                    out.append(res["result"])
                time.sleep(C.REQUEST_SLEEP_SEC)
                return out
            except RpcError as e:
                if str(e).startswith(("LIMIT:", "ITEM:")):
                    raise
                last = e
                self.rotate()
                time.sleep(min(2 ** attempt * 0.5, 8))
            except (requests.RequestException, ValueError) as e:
                last = e
                self.rotate()
                time.sleep(min(2 ** attempt * 0.5, 8))
        raise RpcError(f"batch failed after {retries} retries: {last}")

    def _chain_ok(self, url: str, log, history: bool = True) -> bool:
        try:
            r = self.session.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}, timeout=10)
            j = r.json()
            if "result" not in j:
                log(f"  dropping {redact(url)}: {str(j.get('error', j))[:80]}")
                return False
            cid = int(j["result"], 16)
            if cid != C.CHAIN_ID:
                log(f"  dropping {redact(url)}: chain id {cid} != {C.CHAIN_ID}")
                return False
            if history:   # does the node still have 2025 blocks?  pruned nodes answer null (or an error)
                r = self.session.post(url, json={"jsonrpc": "2.0", "id": 2, "method": "eth_getBlockByNumber",
                                                 "params": [hex(C.HISTORY_PROBE_BLOCK), False]}, timeout=15)
                j = r.json()
                if not isinstance(j.get("result"), dict) or "timestamp" not in j["result"]:
                    log(f"  dropping {redact(url)}: no history for block {C.HISTORY_PROBE_BLOCK} ({str(j.get('error', 'null'))[:50]})")
                    return False
            return True
        except Exception as e:  # noqa
            log(f"  dropping {redact(url)}: {str(e)[:80]}")
            return False

    def check_endpoints(self, log=print) -> list[str]:
        """Keep only endpoints that answer eth_chainId with the expected chain (drops misconfigured/dead ones).
        Dedicated log endpoints (self.logs_endpoints) are checked the same way."""
        good = [u for u in list(self.endpoints) if self._chain_ok(u, log)]
        if not good:
            raise RpcError("no working BSC endpoint; check your network or edit config.RPC_ENDPOINTS")
        self.endpoints = good
        self._i = random.randrange(len(good))
        self.logs_endpoints = [u for u in getattr(self, "logs_endpoints", []) if self._chain_ok(clean_url(u), log, history=False)]
        self.logs_endpoints = [clean_url(u) for u in self.logs_endpoints]
        return good

    # ---- convenience ----
    def block_number(self) -> int:
        return int(self.call("eth_blockNumber", []), 16)

    def block(self, n: int, full_tx: bool = False) -> dict:
        """Block by number; a null answer means this endpoint pruned that block -> mark it and try another."""
        for _ in range(len(self.endpoints)):
            url = self.url
            b = self.call("eth_getBlockByNumber", [hex(n), full_tx])
            if isinstance(b, dict) and "timestamp" in b:
                return b
            self.pruned.add(url)
            self.rotate()
        raise RpcError(f"block {n} unavailable on every endpoint (pruned history?)")

    def block_ts(self, n: int) -> int:
        return int(self.block(n)["timestamp"], 16)

    HEADER_UNSUPPORTED_WORDS = ("does not exist", "not found", "not available", "unsupported", "not supported", "-32601", "header unsupported")

    def _batch_call_url(self, url: str, calls: list[tuple[str, list]]) -> list:
        """One JSON-RPC batch request to ONE endpoint (single attempt, thread-safe).  Raises
        RpcError("LIMIT:...") when the node rejects/truncates the batch, RpcError("ITEM:...") for a
        per-item error, and requests exceptions / RpcError("HTTP n") for transport problems."""
        body = [{"jsonrpc": "2.0", "id": next(self._ids), "method": m, "params": p} for m, p in calls]
        r = self._session().post(url, json=body, timeout=self.timeout * 2)
        if r.status_code == 413:
            raise RpcError("LIMIT:HTTP 413 payload too large")
        if r.status_code == 429:
            raise RpcError("RATE:HTTP 429")
        if r.status_code >= 500:
            raise RpcError(f"HTTP {r.status_code}")
        j = r.json()
        if isinstance(j, dict):                       # whole batch rejected with a single object
            msg = str(j.get("error", j))
            raise RpcError((self.classify_error(msg) or "LIMIT:") + msg[:200])
        items = [x for x in j if isinstance(x, dict)]
        by_id = {x.get("id"): x for x in items}
        if any(x.get("id") is None for x in items) or len(by_id) < len(body):
            errs = [x.get("error") for x in items if "error" in x]
            raise RpcError("LIMIT:batch rejected/truncated: " + str(errs[:1])[:200])
        out = []
        for x in body:
            res = by_id[x["id"]]
            if "error" in res:
                msg = str(res["error"])
                kind = self.classify_error(msg)
                raise RpcError((kind or "ITEM:") + msg[:200])
            out.append(res["result"])
        return out

    def headers_parallel(self, numbers: list[int], workers: int = 4, log=print) -> list[dict]:
        """Headers for many block numbers, fetched concurrently across the (public) endpoints.  Each endpoint
        keeps its own adaptive batch size and header-method flag; endpoints that answer null for a block
        are marked pruned and skipped; failures put the batch back on the queue for another endpoint."""
        if not hasattr(self, "_hdr_ok"):
            self._hdr_ok = {}
        if not hasattr(self, "_hdr_batch"):
            self._hdr_batch = {}
        numbers = list(numbers)
        result: dict[int, dict] = {}
        lock = threading.Lock()
        st = {"cursor": 0, "retry": [], "inflight": 0, "fails": 0, "k": 0, "err": None, "stop": False,
              "cooldown": {}, "efails": {}, "t0": time.time(), "t_last": time.time(), "calls": 0}
        usable = [u for u in self.endpoints if u not in self.pruned]

        def take():
            now = time.time()
            ready = [u for u in usable if u not in self.pruned and st["cooldown"].get(u, 0) <= now]
            if not ready:
                if all(u in self.pruned for u in usable):
                    st["err"] = RpcError("every endpoint returned null for historical blocks (pruned history)")
                    return None, 0.2
                return None, max(min(st["cooldown"].get(u, 0) for u in usable if u not in self.pruned) - now, 0.2)
            url = ready[st["k"] % len(ready)]
            st["k"] += 1
            bs = self._hdr_batch.get(url, C.BATCH_SIZE)
            if st["retry"]:
                chunk = st["retry"].pop()
                if len(chunk) > bs:                       # re-split with this endpoint's (smaller) batch size
                    st["retry"].append(chunk[bs:])
                    chunk = chunk[:bs]
            elif st["cursor"] < len(numbers):
                chunk = numbers[st["cursor"]:st["cursor"] + bs]
                st["cursor"] += len(chunk)
            else:
                return None, 0.2
            return url, chunk

        def progress(force=False):
            if force or time.time() - st["t_last"] >= 60:
                el = time.time() - st["t0"]
                rate = len(result) / max(el, 1e-9)
                eta = (len(numbers) - len(result)) / max(rate, 1e-9)
                log(f"  headers progress: {len(result):,}/{len(numbers):,} ({100 * len(result) / max(len(numbers), 1):.1f}%), "
                    f"{st['calls']} calls, {workers} workers, ETA {eta / 60:.0f} min")
                st["t_last"] = time.time()

        def worker():
            while True:
                with lock:
                    if st["err"] is not None or st["stop"]:
                        return
                    if not st["retry"] and st["cursor"] >= len(numbers) and st["inflight"] == 0:
                        return
                    url, chunk = take()
                    if url is not None:
                        st["inflight"] += 1
                if url is None:
                    time.sleep(min(chunk, 5.0))
                    continue
                use_hdr = self._hdr_ok.get(url, True)
                method = "eth_getHeaderByNumber" if use_hdr else "eth_getBlockByNumber"
                params = (lambda n: [hex(n)]) if use_hdr else (lambda n: [hex(n), False])
                try:
                    res = self._batch_call_url(url, [(method, params(n)) for n in chunk])
                    if any((x is None) or ("timestamp" not in x) for x in res):
                        if use_hdr and all(x is None for x in res):
                            raise RpcError("ITEM:header unsupported")
                        raise RpcError("ITEM:pruned")
                    with lock:
                        st["inflight"] -= 1
                        for n, b in zip(chunk, res):
                            result[n] = b
                        st["calls"] += 1
                        st["fails"] = 0
                        st["efails"][url] = 0
                        progress()
                    time.sleep(C.REQUEST_SLEEP_SEC)
                except (RpcError, requests.RequestException, ValueError) as ex:
                    msg = str(ex)
                    low = msg.lower()
                    with lock:
                        st["inflight"] -= 1
                        st["retry"].append(chunk)
                        st["calls"] += 1
                        bs = self._hdr_batch.get(url, C.BATCH_SIZE)
                        if low == "item:pruned":
                            self.pruned.add(url)
                            log(f"  {redact(url)[:40]}: no history for these blocks -> skipped for headers")
                        elif use_hdr and low.startswith("item:") and any(k in low for k in self.HEADER_UNSUPPORTED_WORDS):
                            self._hdr_ok[url] = False        # retry with eth_getBlockByNumber
                        elif low.startswith("limit:"):
                            if bs > 10 and len(chunk) <= bs:
                                self._hdr_batch[url] = max(min(bs, len(chunk)) // 2, 10)
                                log(f"  {redact(url)[:40]}: batch limit at {bs} -> {self._hdr_batch[url]}")
                            # else: another worker already shrank the batch; the chunk is simply re-split and retried
                        elif low.startswith("rate:"):                       # rate limited: short pause on this endpoint
                            st["fails"] += 1
                            st["cooldown"][url] = time.time() + min(1.0 * st["fails"], 10)
                        else:                                               # transport / 5xx / garbage: back off this
                            st["fails"] += 1                                # endpoint progressively (up to 5 min)
                            ef = st["efails"][url] = st["efails"].get(url, 0) + 1
                            st["cooldown"][url] = time.time() + min(3.0 * ef, 300)
                            if ef in (1, 5, 20) or ef % 100 == 0:
                                log(f"  {redact(url)[:40]}: {msg[:60]} -> cooling down ({ef} in a row)")
                        if st["fails"] >= 200:
                            st["err"] = RpcError(f"header fetch keeps failing on every endpoint (last: {msg[:120]})")

        threads = [threading.Thread(target=worker, daemon=True, name=f"hdr-{i}") for i in range(max(1, workers))]
        for t in threads:
            t.start()
        try:
            while any(t.is_alive() for t in threads):
                for t in threads:
                    t.join(0.5)
        except KeyboardInterrupt:
            with lock:
                st["stop"] = True
            raise
        if st["err"] is not None:
            raise st["err"]
        missing = [n for n in numbers if n not in result]
        if missing:
            raise RpcError(f"headers incomplete: {len(missing)} of {len(numbers)} blocks not fetched")
        return [result[n] for n in numbers]

    def headers(self, numbers: list[int], batch: int | None = None, workers: int = 1, log=print) -> list[dict]:
        """Block headers for a list of block numbers.  Uses eth_getHeaderByNumber (header only, ~1 KB)
        when the endpoint supports it, else eth_getBlockByNumber(n, false).  Batch size adapts to the
        node's limits (public BSC nodes accept ~100); last resort is one call per block.
        workers > 1 -> headers_parallel (concurrent across endpoints)."""
        if workers and workers > 1 and len(numbers) > 2 * C.BATCH_SIZE:
            return self.headers_parallel(numbers, workers, log)
        if not hasattr(self, "_hdr_ok"):
            self._hdr_ok = {}
        batch = batch or C.BATCH_SIZE
        out, i = [], 0
        while i < len(numbers):
            chunk = numbers[i:i + batch]
            use_hdr = self._hdr_ok.get(self.url, True)
            method = "eth_getHeaderByNumber" if use_hdr else "eth_getBlockByNumber"
            params = (lambda n: [hex(n)]) if use_hdr else (lambda n: [hex(n), False])
            try:
                url = self.url
                res = self.call_batch([(method, params(n)) for n in chunk])
                if any((x is None) or ("timestamp" not in x) for x in res):
                    if use_hdr and all(x is None for x in res):
                        raise RpcError("ITEM:header unsupported")
                    raise RpcError("ITEM:pruned")
            except RpcError as e:
                msg = str(e).lower()
                if msg == "item:pruned":
                    self.pruned.add(url)                     # this endpoint lacks (some of) these blocks
                    self.rotate()
                    if all(u in self.pruned for u in self.endpoints):
                        raise RpcError("every endpoint returned null for historical blocks (pruned history)")
                    continue
                if use_hdr and msg.startswith("item:") and any(k in msg for k in self.HEADER_UNSUPPORTED_WORDS):
                    self._hdr_ok[self.url] = False          # this endpoint has no header method: retry chunk with blocks
                    continue
                if batch > 10:
                    batch //= 2
                    self.rotate()
                    continue
                res = []                                     # last resort: sequential single calls
                for n in chunk:
                    b = self.call(method, params(n))
                    if use_hdr and (b is None or "timestamp" not in b):
                        self._hdr_ok[self.url] = False
                        b = self.call("eth_getBlockByNumber", [hex(n), False])
                    res.append(b)
            out.extend(res)
            i += len(chunk)
        return out

    def get_logs(self, address: str | list[str], topics: list, from_block: int, to_block: int) -> list:
        return self.call("eth_getLogs", [{"address": address, "topics": topics,
                                          "fromBlock": hex(from_block), "toBlock": hex(to_block)}])

    # ---- eth_getLogs with per-endpoint capability, chunk size and cool-down ----
    def _logs_call(self, url: str, address, topics, b0: int, b1: int) -> list:
        body = {"jsonrpc": "2.0", "id": next(self._ids), "method": "eth_getLogs",
                "params": [{"address": address, "topics": topics, "fromBlock": hex(b0), "toBlock": hex(b1)}]}
        r = self._session().post(url, json=body, timeout=self.timeout * 2)
        if r.status_code == 429:
            raise RpcError("RATE:HTTP 429")
        if r.status_code >= 500:
            raise RpcError(f"HTTP {r.status_code}")
        j = r.json()
        if "error" in j:
            msg = str(j["error"])
            raise RpcError(self.classify_error(msg) + msg[:200])
        res = j.get("result")
        if not isinstance(res, list):
            raise RpcError(f"unexpected result {str(res)[:80]}")
        return res

    def probe_logs(self, address: str, topics: list, block: int, log=print) -> list[str]:
        """Which endpoints answer eth_getLogs for a HISTORICAL block?  Dedicated log endpoints (keyed) are
        probed first, then the general ones.  Official bsc-dataseed nodes reject eth_getLogs outright."""
        self.log_ok, self.log_chunk, self.log_cooldown, self.log_success, self.log_pinned = {}, {}, {}, {}, {}
        self.log_timeout_at = {}
        candidates = list(dict.fromkeys(list(getattr(self, "logs_endpoints", [])) + list(self.endpoints)))
        keyed = set(getattr(self, "logs_endpoints", []))
        self.log_chunk_max = {}
        for url in candidates:
            try:
                self._logs_call(url, address, topics, block, block)
                self.log_ok[url] = True
                self.log_chunk[url] = C.LOGS_CHUNK_BLOCKS_KEYED if url in keyed else C.LOGS_CHUNK_BLOCKS
                self.log_chunk_max[url] = C.LOGS_CHUNK_MAX_KEYED if url in keyed else C.LOGS_CHUNK_BLOCKS
                log(f"  logs OK   {redact(url)}")
            except Exception as e:  # noqa
                self.log_ok[url] = False
                log(f"  logs NO   {redact(url)}: {str(e)[:70]}")
            time.sleep(0.2)
        keyed_ok = [u for u in getattr(self, "logs_endpoints", []) if self.log_ok.get(u)]
        if keyed_ok:                       # a dedicated endpoint works: use only those for logs
            for u in list(self.log_ok):
                if u not in keyed_ok:
                    self.log_ok[u] = False
        return [u for u, ok in self.log_ok.items() if ok]

    def get_logs_adaptive(self, address: str, topics: list, b0: int, b1: int, log=print,
                          workers: int = 1, on_chunk=None) -> list:
        """Fetch logs over [b0, b1] using only log-capable endpoints, each with its own adaptive chunk size.
        'limit exceeded' at a small chunk is treated as rate limiting: the endpoint cools down for a while.
        workers > 1 fetches several block chunks concurrently (see _get_logs_parallel).  If `on_chunk`
        is given it is called as on_chunk(logs, from_block, to_block) for each fetched block range (from worker
        threads, so it must be thread-safe) instead of accumulating the logs, and the returned list is empty
        (lets the caller decode/compact immediately and record which ranges are done)."""
        if not getattr(self, "log_ok", None):
            self.probe_logs(address, topics, b0, log)
        capable = [u for u, ok in self.log_ok.items() if ok]
        if not capable:
            raise RpcError("no endpoint accepts eth_getLogs; add a log-capable RPC URL to config.RPC_ENDPOINTS "
                           "(e.g. a free NodeReal/Alchemy/dRPC key URL) or pass --rpc <url>")
        if workers and workers > 1:
            return self._get_logs_parallel(address, topics, b0, b1, log, workers, on_chunk, capable)
        out, cur, k, fails, rate_fails, n_logs = [], b0, 0, 0, 0, 0
        t_start, t_last, calls, last_url = time.time(), time.time(), 0, None
        while cur <= b1:
            if time.time() - t_last >= 60:                                       # progress + ETA once a minute
                done = cur - b0
                rate = done / max(time.time() - t_start, 1e-9)
                eta = (b1 - cur + 1) / max(rate, 1e-9)
                log(f"  logs progress: block {cur:,}/{b1:,} ({100 * done / max(b1 - b0 + 1, 1):.1f}%), {n_logs:,} logs, "
                    f"{calls} calls, chunk {self.log_chunk.get(last_url, 0)}, ETA {eta / 60:.0f} min")
                t_last = time.time()
            now = time.time()
            ready = [u for u in capable if self.log_cooldown.get(u, 0) <= now]
            if not ready:
                wait = min(self.log_cooldown[u] for u in capable) - now
                time.sleep(max(wait, 0.5))
                continue
            url = ready[k % len(ready)]
            last_url = url
            k += 1
            chunk = self.log_chunk.get(url, C.LOGS_CHUNK_BLOCKS)
            end = min(cur + chunk - 1, b1)
            try:
                calls += 1
                res = self._logs_call(url, address, topics, cur, end)
                n_logs += len(res)
                if on_chunk is not None:
                    on_chunk(res, cur, end)
                else:
                    out.extend(res)
                cur = end + 1
                fails = rate_fails = 0
                time.sleep(C.REQUEST_SLEEP_SEC)
                self.log_success[url] = self.log_success.get(url, 0) + 1
                cmax = self.log_chunk_max.get(url, C.LOGS_CHUNK_BLOCKS)
                if (chunk < cmax and self.log_success[url] % 40 == 0 and not self.log_pinned.get(url)
                        and chunk * 2 < self.log_timeout_at.get(url, 10 ** 9)):
                    self.log_chunk[url] = min(chunk * 2, cmax)                    # probe back up rarely (unless pinned)
            except (RpcError, requests.RequestException, ValueError) as e:
                fails += 1
                msg = str(e)
                if msg.startswith("LIMIT:") and chunk > 5:
                    hint = suggested_chunk(msg)
                    new = hint if (hint and hint < chunk) else chunk // 2
                    self.log_chunk[url] = max(new, 5)
                    self.log_success[url] = 0
                    if hint and hint < chunk:
                        self.log_pinned[url] = True                               # provider stated its limit: don't probe up
                    log(f"  {redact(url)[:40]}: limit at {chunk} blocks -> {self.log_chunk[url]}"
                        + (f" (provider says {hint}-block range)" if hint else ""))
                elif self._is_timeout(e) and chunk > 50:                          # slow for this range: halve, no cool-down
                    self.log_chunk[url] = max(chunk // 2, 5)
                    self.log_success[url] = 0
                    self.log_timeout_at[url] = min(chunk, self.log_timeout_at.get(url, 10 ** 9))
                    log(f"  {redact(url)[:40]}: time-out at {chunk} blocks -> {self.log_chunk[url]}")
                elif msg.startswith("RATE:"):                                    # rate limit / quota: back off
                    rate_fails += 1
                    self.log_cooldown[url] = time.time() + self.rate_backoff(rate_fails)
                    self.rate_log(log, url, msg, rate_fails)
                else:                                                            # transport: cool down
                    self.log_cooldown[url] = time.time() + min(5 * fails, 60)
                    log(f"  {redact(url)[:40]}: {msg[:60]} -> cooling down")
                if fails - rate_fails >= 80:
                    raise RpcError(f"eth_getLogs keeps failing on all capable endpoints (last: {msg[:120]})")
        return out

    @staticmethod
    def rate_backoff(n: int) -> float:
        """Seconds to wait after the n-th consecutive rate-limit answer: 1 s .. 15 s for a per-second limit,
        1 min after 20 in a row, 5 min after 40 (an exhausted daily/monthly quota) — and never give up:
        quotas reset, and everything fetched so far is already on disk."""
        if n >= 40:
            return 300.0
        if n >= 20:
            return 60.0
        return min(1.0 * n, 15.0)

    @staticmethod
    def rate_log(log, url: str, msg: str, n: int) -> None:
        if n in (1, 5, 10, 20) or (n < 40 and n % 5 == 0) or n % 6 == 0:      # every ~30 min once in the 5-min regime
            hint = "" if n < 20 else "  (looks like an exhausted daily/monthly quota: waiting for it to reset, Ctrl-C to stop; completed segments are saved)"
            log(f"  {redact(url)[:40]}: {msg[5:65]} -> pausing ({n}, next wait {Rpc.rate_backoff(n):.0f}s){hint}")

    @staticmethod
    def _is_timeout(e: Exception) -> bool:
        m = str(e).lower()
        return isinstance(e, requests.Timeout) or "timed out" in m or "timeout" in m

    def _get_logs_parallel(self, address, topics, b0: int, b1: int, log, workers: int, on_chunk, capable: list[str]) -> list:
        """Concurrent eth_getLogs: `workers` threads take consecutive block chunks from a shared stack.  Each
        endpoint keeps ONE adaptive chunk size (halved on range/limit errors and on read time-outs at the
        current size, probed back up after 40 successes unless the provider stated its limit), and cools
        down on rate limiting / transport errors.  A failed range goes back on the stack and is re-split
        with the reduced chunk size, so nothing is lost or duplicated.  Results are returned in block order."""
        lock = threading.Lock()
        pending = [(b0, b1)]                      # LIFO stack of (from, to) still to fetch
        out, total = [], b1 - b0 + 1
        st = {"done": 0, "calls": 0, "fails": 0, "rate_fails": 0, "k": 0, "inflight": 0, "n_logs": 0, "err": None,
              "stop": False, "t0": time.time(), "t_last": time.time()}

        def take():
            """Under lock: (url, (from, to)) or (None, seconds_to_wait)."""
            now = time.time()
            ready = [u for u in capable if self.log_cooldown.get(u, 0) <= now]
            if not ready:
                return None, max(min(self.log_cooldown[u] for u in capable) - now, 0.2)
            if not pending:
                return None, 0.2
            url = ready[st["k"] % len(ready)]
            st["k"] += 1
            s, e = pending.pop()
            chunk = self.log_chunk.get(url, C.LOGS_CHUNK_BLOCKS)
            end = min(s + chunk - 1, e)
            if end < e:
                pending.append((end + 1, e))
            return url, (s, end)

        def progress(force=False):
            if force or time.time() - st["t_last"] >= 60:
                el = time.time() - st["t0"]
                rate = st["done"] / max(el, 1e-9)
                eta = (total - st["done"]) / max(rate, 1e-9)
                chunks = ",".join(str(self.log_chunk.get(u, 0)) for u in capable)
                log(f"  logs progress: {st['done']:,}/{total:,} blocks ({100 * st['done'] / total:.1f}%), {st['n_logs']:,} logs, "
                    f"{st['calls']} calls, chunk {chunks}, {workers} workers, ETA {eta / 60:.0f} min")
                st["t_last"] = time.time()

        def worker():
            while True:
                with lock:
                    if st["err"] is not None or st["stop"]:
                        return
                    if not pending and st["inflight"] == 0:
                        return
                    url, rng = take()
                    if url is not None:
                        st["inflight"] += 1
                if url is None:
                    time.sleep(min(rng, 5.0))
                    continue
                s, e = rng
                try:
                    res = self._logs_call(url, address, topics, s, e)
                    if on_chunk is not None:
                        on_chunk(res, s, e)        # outside the lock: the callback must be thread-safe
                    with lock:
                        st["inflight"] -= 1
                        st["n_logs"] += len(res)
                        if on_chunk is None:
                            out.extend(res)
                        st["done"] += e - s + 1
                        st["calls"] += 1
                        st["fails"] = st["rate_fails"] = 0
                        self.log_success[url] = self.log_success.get(url, 0) + 1
                        cur = self.log_chunk.get(url, C.LOGS_CHUNK_BLOCKS)
                        cmax = self.log_chunk_max.get(url, C.LOGS_CHUNK_BLOCKS)
                        if (cur < cmax and self.log_success[url] % 40 == 0 and not self.log_pinned.get(url)
                                and cur * 2 < self.log_timeout_at.get(url, 10 ** 9)):
                            self.log_chunk[url] = min(cur * 2, cmax)
                        progress()
                    time.sleep(C.REQUEST_SLEEP_SEC)
                except (RpcError, requests.RequestException, ValueError) as ex:
                    with lock:
                        st["inflight"] -= 1
                        pending.append((s, e))
                        st["fails"] += 1
                        st["calls"] += 1
                        msg = str(ex)
                        size = e - s + 1
                        cur = self.log_chunk.get(url, C.LOGS_CHUNK_BLOCKS)
                        # only shrink if this request was not larger than the endpoint's CURRENT chunk size
                        # (a larger size means another worker already reduced it since the request was made)
                        if msg.startswith("LIMIT:"):
                            if cur > 5 and size <= cur:
                                hint = suggested_chunk(msg)
                                new = hint if (hint and hint < cur) else min(cur, size) // 2
                                self.log_chunk[url] = max(new, 5)
                                self.log_success[url] = 0
                                if hint and hint < cur:
                                    self.log_pinned[url] = True
                                log(f"  {redact(url)[:40]}: limit at {cur} blocks -> {self.log_chunk[url]}"
                                    + (f" (provider says {hint}-block range)" if hint else ""))
                            st["fails"] -= 1                             # not a failure of the endpoint: just re-split
                        elif self._is_timeout(ex) and size > cur:
                            st["fails"] -= 1                             # already reduced by another worker: retry
                        elif self._is_timeout(ex) and cur > 50:
                            self.log_chunk[url] = max(min(cur, size) // 2, 5)
                            self.log_success[url] = 0
                            self.log_timeout_at[url] = min(cur, self.log_timeout_at.get(url, 10 ** 9))
                            st["fails"] -= 1
                            log(f"  {redact(url)[:40]}: time-out at {cur} blocks -> {self.log_chunk[url]}")
                        elif msg.startswith("RATE:"):                    # rate limit / quota: back off, keep the chunk
                            st["rate_fails"] += 1
                            self.log_cooldown[url] = time.time() + self.rate_backoff(st["rate_fails"])
                            self.rate_log(log, url, msg, st["rate_fails"])
                        else:
                            self.log_cooldown[url] = time.time() + min(5 * st["fails"], 60)
                            log(f"  {redact(url)[:40]}: {msg[:60]} -> cooling down")
                        if st["fails"] - st["rate_fails"] >= 80:
                            st["err"] = RpcError(f"eth_getLogs keeps failing on all capable endpoints (last: {msg[:120]})")

        threads = [threading.Thread(target=worker, daemon=True, name=f"logs-{i}") for i in range(workers)]
        for t in threads:
            t.start()
        try:
            while any(t.is_alive() for t in threads):
                for t in threads:
                    t.join(0.5)
        except KeyboardInterrupt:
            with lock:
                st["stop"] = True
            raise
        if st["err"] is not None:
            raise st["err"]
        if pending or st["done"] != total:
            raise RpcError(f"eth_getLogs incomplete: {st['done']}/{total} blocks fetched")
        if on_chunk is None:
            out.sort(key=lambda l: (int(l["blockNumber"], 16), int(l["logIndex"], 16)))
        return out

    def eth_call(self, to: str, data: str) -> str:
        return self.call("eth_call", [{"to": to, "data": data}, "latest"])

    def get_code(self, addr: str) -> str:
        return self.call("eth_getCode", [addr, "latest"])


# ---------------- ABI helpers ----------------
def pad_addr(a: str) -> str:
    return a.lower().replace("0x", "").rjust(64, "0")


def pad_uint(x: int) -> str:
    return hex(x)[2:].rjust(64, "0")


def word_to_int(h: str, signed: bool) -> int:
    v = int(h, 16)
    if signed and v >= 2 ** 255:
        v -= 2 ** 256
    return v


def decode_words(data: str) -> list[str]:
    d = data[2:] if data.startswith("0x") else data
    return [d[i:i + 64] for i in range(0, len(d), 64)]


def decode_string(res: str) -> str:
    """ABI-decode a `string` return value (also tolerates bytes32-style symbols)."""
    w = decode_words(res)
    if len(w) >= 3 and int(w[0], 16) == 32:
        n = int(w[1], 16)
        return bytes.fromhex("".join(w[2:]))[:n].decode("utf-8", "replace")
    if len(w) == 1:
        return bytes.fromhex(w[0]).rstrip(b"\x00").decode("utf-8", "replace")
    return ""


def verify_tokens(rpc: Rpc, tokens: dict, log=print) -> None:
    """Check symbol()/decimals() of every configured token on chain; raise on any mismatch."""
    bad = []
    for name, (addr, dec, sym) in tokens.items():
        try:
            got_sym = decode_string(rpc.eth_call(addr, C.SEL_SYMBOL))
            got_dec = int(rpc.eth_call(addr, C.SEL_DECIMALS), 16)
        except Exception as e:  # noqa
            bad.append(f"{name} {addr}: call failed ({str(e)[:60]})"); continue
        ok = got_sym.lower() == sym.lower() and got_dec == dec
        log(f"  token {name:5s} {addr} -> symbol={got_sym!r} decimals={got_dec} {'OK' if ok else 'MISMATCH'}")
        if not ok:
            bad.append(f"{name}: expected {sym}/{dec}, chain says {got_sym}/{got_dec}")
    if bad:
        raise RpcError("token verification failed: " + "; ".join(bad))


def pool_meta(rpc: Rpc, pool: str) -> dict:
    t0 = "0x" + rpc.eth_call(pool, C.SEL_TOKEN0)[-40:]
    t1 = "0x" + rpc.eth_call(pool, C.SEL_TOKEN1)[-40:]
    f = int(rpc.eth_call(pool, C.SEL_FEE), 16)
    return {"pool": pool, "token0": t0, "token1": t1, "fee": f}


def resolve_pool(rpc: Rpc, tokenA: str, tokenB: str, fee: int, factory: str = C.PCS_V3_FACTORY,
                 fallback: str | None = None) -> dict:
    """Ask the factory for the pool (trying every healthy endpoint), else verify a known address."""
    data = C.SEL_GET_POOL + pad_addr(tokenA) + pad_addr(tokenB) + pad_uint(fee)
    want = {tokenA.lower(), tokenB.lower()}
    for _ in range(len(rpc.endpoints)):
        try:
            res = rpc.eth_call(factory, data)
            pool = "0x" + res[-40:]
            if len(res) >= 42 and int(pool, 16) != 0:
                m = pool_meta(rpc, pool)
                if {m["token0"].lower(), m["token1"].lower()} == want and m["fee"] == fee:
                    return m
        except (RpcError, ValueError):
            pass
        rpc.rotate()
    if fallback:
        m = pool_meta(rpc, fallback)
        if {m["token0"].lower(), m["token1"].lower()} == want and m["fee"] == fee:
            return m
        raise RpcError(f"fallback pool {fallback} does not match {tokenA}/{tokenB} fee={fee}: {m}")
    raise RpcError(f"factory returned no pool for {tokenA}/{tokenB} fee={fee} on any endpoint; "
                   f"add the pool address to config.KNOWN_POOLS (see pancakeswap.finance/info/v3)")


def find_block_by_time(rpc: Rpc, ts: int, lo: int | None = None, hi: int | None = None) -> int:
    """First block with timestamp >= ts (binary search over block headers)."""
    hi = hi or rpc.block_number()
    lo = lo or 0
    while lo < hi:
        mid = (lo + hi) // 2
        if rpc.block_ts(mid) < ts:
            lo = mid + 1
        else:
            hi = mid
    return lo
