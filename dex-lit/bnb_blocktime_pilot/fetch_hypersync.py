"""Bulk Swap logs from Envio HyperSync (https://docs.envio.dev/docs/HyperSync) — a free, indexed log source that
returns tens of thousands of logs per request, so a 30-day window of a busy pool costs a few hundred requests
instead of tens of thousands of eth_getLogs calls (which is what exhausted the NodeReal free quota).

Setup (once):
    pip install hypersync
    export ENVIO_API_TOKEN="<token from https://envio.dev/app/api-tokens — free account>"
Run:
    python run_pilot.py ... --hypersync https://bsc.hypersync.xyz

The logs are converted to the eth_getLogs JSON shape that fetch_swaps.decode_swap expects (hex blockNumber /
logIndex, topics list, data, plus blockTimestamp from the joined block), so the rest of the pipeline is unchanged.
Block timestamps returned here are cross-checked against the reconstructed timestamp table like NodeReal's.
"""
from __future__ import annotations
import asyncio, os, sys, time

DEFAULT_URL = "https://bsc.hypersync.xyz"
LOG_FIELDS = ("block_number", "log_index", "transaction_hash", "address", "data", "topic0", "topic1", "topic2", "topic3")


def available() -> bool:
    try:
        import hypersync  # noqa
        return True
    except ImportError:
        return False


def _to_int(x) -> int:
    if x is None:
        return -1
    if isinstance(x, int):
        return x
    s = str(x)
    return int(s, 16) if s.startswith("0x") else int(s)


def _topics(l) -> list[str]:
    t = getattr(l, "topics", None)
    if isinstance(t, (list, tuple)):
        return [x for x in t if x]
    out = []
    for i in range(4):
        v = getattr(l, f"topic{i}", None)
        if v:
            out.append(v)
    return out


def to_rpc_log(l, ts_by_block: dict) -> dict:
    """HyperSync Log object -> eth_getLogs-style dict (what decode_swap consumes)."""
    bn = _to_int(l.block_number)
    topics = _topics(l)
    if len(topics) < 3 or not (l.data or "").startswith("0x"):
        raise RuntimeError(f"unexpected HyperSync log format: topics={getattr(l, 'topics', None)!r} data={str(l.data)[:20]!r} "
                           f"(client attributes: {[a for a in dir(l) if not a.startswith('_')]})")
    return {"blockNumber": hex(bn), "logIndex": hex(_to_int(l.log_index)), "transactionHash": l.transaction_hash,
            "address": l.address, "data": l.data, "topics": topics, "blockTimestamp": ts_by_block.get(bn)}


class HyperSyncLogs:
    """Thin synchronous wrapper: fetch all logs of one contract/topic over a block range, page by page."""

    def __init__(self, url: str = DEFAULT_URL, token: str | None = None, max_logs_per_request: int = 100_000):
        import hypersync as hs
        self.hs = hs
        self.url = url
        self.token = token or os.environ.get("ENVIO_API_TOKEN") or None
        self.max_logs = max_logs_per_request
        self._client = None

    def client(self):
        """A fresh client per asyncio.run() scope (the client binds to the running event loop)."""
        cfg = self.hs.ClientConfig(url=self.url, api_token=self.token, http_req_timeout_millis=180_000,
                                   max_num_retries=8, retry_backoff_ms=1_000, retry_ceiling_ms=30_000)
        return self.hs.HypersyncClient(cfg)

    def probe(self, need_height: int | None = None) -> tuple[int, int]:
        """(chain_id, archive height); raises if the endpoint is unreachable or the token is rejected."""
        async def _p():
            c = self.client()
            return await c.get_chain_id(), await c.get_height()
        cid, h = asyncio.run(_p())
        if need_height is not None and h < need_height:
            raise RuntimeError(f"HyperSync archive height {h:,} is below the needed block {need_height:,}")
        return cid, h

    def fetch_range(self, address: str, topic0: str, b0: int, b1: int, on_chunk, log=print) -> int:
        """All logs of `address` with `topic0` in [b0, b1] (inclusive).  on_chunk(logs, from, to) is called once
        per page with the eth_getLogs-shaped dicts covering exactly [from, to].  Returns the log count."""
        hs = self.hs
        fsel = hs.FieldSelection(block=[hs.BlockField.NUMBER, hs.BlockField.TIMESTAMP],
                                 log=[getattr(hs.LogField, f.upper()) for f in LOG_FIELDS])

        async def _run():
            c = self.client()
            cur, total, pages, t0 = b0, 0, 0, time.time()
            while cur <= b1:
                q = hs.Query(from_block=cur, to_block=b1 + 1, field_selection=fsel,
                             logs=[hs.LogSelection(address=[address], topics=[[topic0]])], max_num_logs=self.max_logs)
                res = await c.get(q)
                nb = int(res.next_block)
                if nb <= cur:
                    raise RuntimeError(f"HyperSync made no progress at block {cur:,} (next_block={nb})")
                ts = {}
                for b in (res.data.blocks or []):
                    ts[_to_int(b.number)] = _to_int(b.timestamp)
                logs = [to_rpc_log(l, ts) for l in (res.data.logs or [])]
                hi = min(nb - 1, b1)
                on_chunk(logs, cur, hi)
                total += len(logs); pages += 1
                if pages % 5 == 1 or hi >= b1:
                    log(f"  hypersync: blocks {cur:,}..{hi:,} -> {len(logs):,} logs (page {pages}, {total:,} so far, "
                        f"{time.time() - t0:.0f}s)")
                cur = nb
                await asyncio.sleep(0.05)
            return total
        return asyncio.run(_run())


def fetch_range(address: str, topic0: str, b0: int, b1: int, on_chunk, log=None, url: str = DEFAULT_URL,
                token: str | None = None) -> int:
    return HyperSyncLogs(url, token).fetch_range(address, topic0, b0, b1, on_chunk, log or (lambda m: print(m, file=sys.stderr)))
