"""Step 4: align DEX swaps with Binance prices and compute the pilot metrics around a fork.

Metrics (per pool, per regime and per day):
  * block interval (ms), swaps per block, share of blocks with >=1 swap
  * arbitrage identification: swap moves the pool price toward the Binance mid from outside the
    fee band (|dev_pre| > fee) and lands closer to it; "strict" arbs land inside the band
  * LP economics vs. Binance mid (quote units):  lp_gain = dQ + dB * P_cex  (pool perspective),
    fee_income = fee * input value, arb_loss (LVR proxy) = fee_income - lp_gain,
    markout_{5s,30s} = dQ + dB * P_cex(t + delta)
  * price efficiency at 1s: mean |dev|, share of seconds with |dev| > fee, AR(1) half-life of dev
  * price discovery: Hasbrouck information-share bounds from a bivariate VECM on 1s log prices

Usage:
    python analyze_pilot.py --blocks data/blocks_Maxwell.parquet \
        --swaps data/swaps_WBNB-USDT-500_*.parquet --binance data/binance_BNBUSDT_1s.parquet \
        --fork-block 52000000 --out results/WBNB-USDT-500
"""
from __future__ import annotations
import argparse, glob, os, sys, json
import numpy as np, pandas as pd

Q96 = 2 ** 96


# ---------------------------------------------------------------- price helpers
def to_f64(s: pd.Series) -> np.ndarray:
    """uint256/int256 columns are stored as decimal strings (or Python ints / already floats); convert to float64
    (exact to ~16 significant digits — ample for prices and token amounts)."""
    if pd.api.types.is_numeric_dtype(s.dtype):
        return s.to_numpy(dtype=np.float64)
    return s.to_numpy().astype(np.float64)


def pool_price_quote_per_base(sqrt_price_x96, dec0: int, dec1: int, base_is_token0: bool):
    p10 = (np.asarray(sqrt_price_x96, dtype=np.float64) / Q96) ** 2 * 10.0 ** (dec0 - dec1)  # token1 per token0
    return p10 if base_is_token0 else 1.0 / p10


RAW_INT_COLS = ("amount0", "amount1", "sqrt_price_x96", "protocol_fee0", "protocol_fee1")


def prepare_swaps(swaps: pd.DataFrame, blocks: pd.DataFrame, p_prev: float | None = None) -> pd.DataFrame:
    """Pool prices, LP-side token flows and block timestamps per swap.  `blocks` needs columns number/milli_ts;
    when it is a contiguous block table the lookup is a direct index (no merge).  The raw uint256 columns are
    dropped afterwards (dB/dQ/p_post carry their information); `liquidity` is kept as float64."""
    blk, li = swaps["block"].to_numpy(), swaps["log_index"].to_numpy()
    already_sorted = len(swaps) < 2 or bool(((np.diff(blk) > 0) | ((np.diff(blk) == 0) & (np.diff(li) > 0))).all())
    df = swaps.reset_index(drop=True) if already_sorted else swaps.sort_values(["block", "log_index"], kind="stable").reset_index(drop=True)
    m = df.iloc[0]
    dec0, dec1, b0 = int(m["dec0"]), int(m["dec1"]), bool(m["base_is_token0"])
    fee = float(m["fee"]) / 1e6
    df["p_post"] = pool_price_quote_per_base(to_f64(df["sqrt_price_x96"]), dec0, dec1, b0)
    df["p_pre"] = df["p_post"].shift(1)
    if p_prev is not None:                 # streaming: the pool price before this chunk's first swap
        df.iloc[0, df.columns.get_loc("p_pre")] = p_prev
    a0 = to_f64(df["amount0"]) / 10 ** dec0
    a1 = to_f64(df["amount1"]) / 10 ** dec1
    if "liquidity" in df:
        df["liquidity"] = to_f64(df["liquidity"])
    df = df.drop(columns=[c for c in RAW_INT_COLS if c in df])
    df["dB"] = a0 if b0 else a1          # base received by the pool (+) / paid out (-)
    df["dQ"] = a1 if b0 else a0          # quote received by the pool (+) / paid out (-)
    df["fee_rate"] = fee
    num = blocks["number"].to_numpy()
    contiguous = len(num) > 0 and num[-1] - num[0] + 1 == len(num) and (np.diff(num[: min(len(num), 1000)]) == 1).all()
    if contiguous:
        idx = df["block"].to_numpy().astype(np.int64) - int(num[0])
        ok = (idx >= 0) & (idx < len(num))
        mts = np.full(len(df), np.nan)
        mts[ok] = blocks["milli_ts"].to_numpy(dtype=np.float64)[idx[ok]]
        df["milli_ts"] = mts
    else:
        df = df.merge(blocks[["number", "milli_ts"]].rename(columns={"number": "block"}), on="block", how="left")
    if "block_ts" in df:                                   # provider-supplied block timestamp (seconds) as fallback
        fb = df["block_ts"].astype("float64") * 1000.0
        df["milli_ts"] = df["milli_ts"].where(df["milli_ts"].notna(), fb.where(df["block_ts"] > 0))
    df = df.dropna(subset=["milli_ts"])
    df["ts_ms"] = df["milli_ts"].astype("int64")
    return df


def _asof_backward(keys: np.ndarray, vals: np.ndarray, q: np.ndarray) -> np.ndarray:
    """vals at the last key <= q (NaN when none), i.e. pandas.merge_asof(direction='backward')."""
    i = np.searchsorted(keys, q, side="right") - 1
    out = np.full(len(q), np.nan)
    ok = i >= 0
    out[ok] = vals[i[ok]]
    return out


class AggTradeRef:
    """Tick-level reference price from Binance aggTrades: the last trade at or before a query time (millisecond
    resolution), read day by day from <dir>/<YYYY-MM-DD>.parquet files (ts_ms, price) so that memory stays at a
    few days of trades.  Two directories = cross rate (base symbol / quote symbol, e.g. CAKEUSDT / BNBUSDT)."""

    DAY_MS = 86_400_000

    def __init__(self, dirs, lag_ms: int = 0, cache_days: int = 4):
        self.dirs = list(dirs) if isinstance(dirs, (list, tuple)) else [dirs]
        self.lag = int(lag_ms)
        self.cache_days = cache_days
        self._cache = {}          # (dir, day) -> (keys, vals)
        self._order = []

    def _load(self, d: str, day: int):
        key = (d, day)
        if key not in self._cache:
            path = os.path.join(d, pd.Timestamp(day * self.DAY_MS, unit="ms", tz="UTC").strftime("%Y-%m-%d") + ".parquet")
            if os.path.exists(path):
                t = pd.read_parquet(path)
                self._cache[key] = (t["ts_ms"].to_numpy(dtype=np.int64), t["price"].to_numpy(dtype=np.float64))
            else:
                self._cache[key] = (np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float64))
            self._order.append(key)
            while len(self._order) > self.cache_days * len(self.dirs):
                self._cache.pop(self._order.pop(0), None)
        return self._cache[key]

    def _series(self, d: str, q: np.ndarray):
        days = range(int(q.min() // self.DAY_MS) - 1, int(q.max() // self.DAY_MS) + 1)   # previous day for early-morning queries
        parts = [self._load(d, day) for day in days]
        keys = np.concatenate([p[0] for p in parts]); vals = np.concatenate([p[1] for p in parts])
        return keys, vals

    def lookup(self, q: np.ndarray) -> np.ndarray:
        """Last traded price at or before each query time (already lag-adjusted by the caller)."""
        q = np.asarray(q, dtype=np.int64)
        if len(q) == 0:
            return np.empty(0)
        out = None
        for d in self.dirs:
            keys, vals = self._series(d, q)
            v = _asof_backward(keys, vals, q)
            out = v if out is None else out / v
        return out


def attach_cex(df: pd.DataFrame, cex: pd.DataFrame, horizons=(5, 30), ref: "AggTradeRef | None" = None) -> pd.DataFrame:
    """Reference price for every swap.  Default: close of the last COMPLETED 1s kline before the block timestamp
    (no look-ahead; up to 1 s stale).  With `ref` (tick-level aggTrades): the last Binance trade at or before the
    block timestamp minus ref.lag ms; the kline reference is kept as p_cex_1s for the noise diagnostic.
    Vectorised searchsorted lookups (no merge copies)."""
    cex = cex.sort_values("ts_ms")
    keys = cex["ts_ms"].to_numpy(dtype=np.int64)
    vals = cex["close"].to_numpy(dtype=np.float64)
    if not (np.diff(df["ts_ms"].to_numpy()) >= 0).all():
        df = df.sort_values("ts_ms", kind="stable").reset_index(drop=True)
    ts = df["ts_ms"].to_numpy(dtype=np.int64)
    if ref is None:
        df["ts_ref"] = ts - 1000
        df["p_cex"] = _asof_backward(keys, vals, ts - 1000)
        for h in horizons:
            df[f"p_cex_h{h}"] = _asof_backward(keys, vals, ts + h * 1000)
    else:
        df["ts_ref"] = ts - ref.lag
        df["p_cex"] = ref.lookup(ts - ref.lag)
        df["p_cex_1s"] = _asof_backward(keys, vals, ts - 1000)
        for h in horizons:
            df[f"p_cex_h{h}"] = ref.lookup(ts + h * 1000)
    return df


def swap_metrics(df: pd.DataFrame) -> pd.DataFrame:
    fee = df["fee_rate"]
    df["dev_pre"] = df["p_pre"] / df["p_cex"] - 1
    df["dev_post"] = df["p_post"] / df["p_cex"] - 1
    toward = (np.sign(df["dev_post"] - df["dev_pre"]) == -np.sign(df["dev_pre"])) & (df["dev_post"].abs() < df["dev_pre"].abs())
    df["is_arb"] = (df["dev_pre"].abs() > fee) & toward
    df["is_arb_strict"] = df["is_arb"] & (df["dev_post"].abs() <= fee)
    df["volume_q"] = np.where(df["dB"] > 0, df["dB"] * df["p_cex"], df["dQ"].clip(lower=0))
    df["fee_income"] = fee * df["volume_q"]
    df["lp_gain"] = df["dQ"] + df["dB"] * df["p_cex"]
    df["arb_loss"] = df["fee_income"] - df["lp_gain"]          # LVR proxy (>= 0 on average)
    for h in (5, 30):
        if f"p_cex_h{h}" in df:
            df[f"markout_{h}s"] = df["dQ"] + df["dB"] * df[f"p_cex_h{h}"]
    return df


# ---------------------------------------------------------------- 1s price series
def one_second_series(last_by_sec: pd.Series, cex: pd.DataFrame, t0_ms: int, t1_ms: int) -> pd.DataFrame:
    """1-second panel of pool price (last swap price of the second, carried forward) and Binance close.
    `last_by_sec`: Series indexed by second (ms) -> last p_post in that second (from Accumulator)."""
    sec = pd.DataFrame({"ts_ms": np.arange(t0_ms // 1000 * 1000, t1_ms // 1000 * 1000 + 1000, 1000)})
    last = last_by_sec.rename("p_pool").rename_axis("ts_ms").reset_index()
    s = sec.merge(last, on="ts_ms", how="left").merge(cex[["ts_ms", "close"]].rename(columns={"close": "p_cex"}), on="ts_ms", how="left")
    s["p_pool"] = s["p_pool"].ffill()
    s["p_cex"] = s["p_cex"].astype(np.float64).ffill()
    s["dev"] = s["p_pool"] / s["p_cex"] - 1
    return s.dropna()


def outside_band_episode_length(dev: pd.Series, fee: float) -> float:
    """Mean duration (seconds) of episodes during which |dev| stays above the fee band: how long a
    profitable-for-arbitrageurs mispricing survives before being corrected."""
    out = (dev.abs() > fee).values
    if out.sum() == 0:
        return np.nan
    edges = np.diff(np.concatenate([[0], out.astype(int), [0]]))
    starts, ends = np.where(edges == 1)[0], np.where(edges == -1)[0]
    return float(np.mean(ends - starts))


def half_life(dev: pd.Series) -> float:
    x = dev.values[:-1]; y = dev.values[1:]
    if len(x) < 100 or np.nanstd(x) == 0:
        return np.nan
    rho = np.cov(x, y)[0, 1] / np.var(x)
    return np.log(0.5) / np.log(rho) if 0 < rho < 1 else np.nan


def _mat_sqrt(a: np.ndarray) -> np.ndarray:
    u, s, v = np.linalg.svd(a, full_matrices=False)
    return u.dot(np.sqrt(s)[:, None] * v)


def vecm_ml(y: np.ndarray, diff_lags: int = 10, rank: int = 1) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Johansen ML estimate of a VECM without deterministic terms — the same estimator as
    statsmodels.tsa.vector_ar.vecm.VECM(y, k_ar_diff=diff_lags, coint_rank=rank, deterministic="n").fit()
    (alpha, beta normalised to an identity top block, sigma_u), but the residualisation on the lagged
    differences is done through the normal equations instead of an explicit (T x T) projection matrix,
    which statsmodels <= 0.14 builds and which needs terabytes for a million observations.
    y: (nobs, K).  Returns (alpha K x r, beta K x r, sigma_u K x K)."""
    inv = np.linalg.inv
    yT = np.asarray(y, dtype=np.float64).T
    K = yT.shape[0]
    p = diff_lags + 1
    y_1_T = yT[:, p:]
    T = y_1_T.shape[1]
    delta_y = np.diff(yT)
    delta_y_1_T = delta_y[:, p - 1:]
    y_lag1 = yT[:, p - 1:-1]
    delta_x = np.empty((diff_lags * K, T))
    for i in range(1, diff_lags + 1):                       # block i-1 holds lag i of the differences
        delta_x[(i - 1) * K:i * K, :] = delta_y[:, p - 1 - i:p - 1 - i + T]
    xx_inv = inv(delta_x.dot(delta_x.T))

    def residualise(mat):
        return mat - mat.dot(delta_x.T).dot(xx_inv).dot(delta_x)

    r0, r1 = residualise(delta_y_1_T), residualise(y_lag1)
    s00, s01, s11 = r0.dot(r0.T) / T, r0.dot(r1.T) / T, r1.dot(r1.T) / T
    s11_ = inv(_mat_sqrt(s11))
    s01_s11_ = s01.dot(s11_)
    lambd, v = np.linalg.eig(s01_s11_.T @ inv(s00) @ s01_s11_)
    order = np.argsort(lambd)[::-1]
    v = v[:, order]
    beta = np.real_if_close((v[:, :rank].T.dot(s11_)).T)
    beta = beta.dot(inv(beta[:rank]))
    alpha = s01.dot(beta).dot(inv(beta.T.dot(s11).dot(beta)))
    gamma = (delta_y_1_T - alpha.dot(beta.T).dot(y_lag1)).dot(delta_x.T).dot(xx_inv)
    temp = delta_y_1_T - alpha.dot(beta.T).dot(y_lag1) - gamma.dot(delta_x)
    sigma_u = temp.dot(temp.T) / T
    return np.real(alpha), np.real(beta), np.real(sigma_u)


def information_share(p_pool: np.ndarray, p_cex: np.ndarray, lags: int = 10) -> dict:
    """Hasbrouck (1995) information-share bounds for the DEX price from a bivariate VECM."""
    y = np.column_stack([np.log(p_pool), np.log(p_cex)])
    alpha_m, _, sigma = vecm_ml(y, diff_lags=lags, rank=1)
    alpha = alpha_m.ravel()                   # adjustment coefficients (2,)
    psi = np.array([alpha[1], -alpha[0]])     # alpha_perp' (common-trend loadings up to scale)
    out = {}
    for order, idx in (("dex_first", [0, 1]), ("cex_first", [1, 0])):
        P = np.eye(2)[idx]
        F = np.linalg.cholesky(P @ sigma @ P.T)
        c = (psi @ P.T) @ F
        share = c ** 2 / (c ** 2).sum()
        s = share[idx.index(0)]               # share attributed to the DEX price
        out[order] = float(s)
    return {"IS_dex_upper": max(out.values()), "IS_dex_lower": min(out.values()),
            "alpha_dex": float(alpha[0]), "alpha_cex": float(alpha[1])}


# ---------------------------------------------------------------- streaming aggregation
IS_MAX_SECONDS = 14 * 86400      # VECM information-share window per regime (see regime_table)
DAILY_COLS = ["volume_q", "is_arb", "fee_income", "arb_loss", "lp_gain"]
HOD_COLS = ["volume_q", "is_arb", "arb_loss", "fee_income"]


class Accumulator:
    """Running sums over enriched swap chunks (processed in block order) for the regime, daily and
    hour-of-day tables, plus the last pool price of every second.  Chunks cover disjoint block ranges, so
    per-chunk distinct-block counts add up and per-second 'last' values only need a final keep-last merge."""

    def __init__(self, fork_block: int):
        self.fb = fork_block
        self.sums = {"pre": {}, "post": {}}
        self.arb_sizes = {"pre": [], "post": []}
        self.daily = None
        self.hod = None
        self.sec_last = []
        self.n = 0
        self.last_block = None

    def _bump(self, name: str, key: str, v: float):
        self.sums[name][key] = self.sums[name].get(key, 0.0) + float(v)

    def add(self, d: pd.DataFrame) -> None:
        k = int(np.searchsorted(d["block"].to_numpy(), self.fb, side="left"))
        for name, part in (("pre", d.iloc[:k]), ("post", d.iloc[k:])):
            if len(part) == 0:
                continue
            arb = part["is_arb"].to_numpy()
            self._bump(name, "swaps", len(part))
            n_blocks = part["block"].nunique()
            if self.last_block is not None and int(part["block"].iloc[0]) == self.last_block:
                n_blocks -= 1                      # a block split across two chunks must not be counted twice
            self.last_block = int(part["block"].iloc[-1])
            self._bump(name, "blocks_with_swap", n_blocks)
            self._bump(name, "volume_q", part["volume_q"].sum())
            self._bump(name, "n_arb", arb.sum())
            self._bump(name, "n_arb_strict", part["is_arb_strict"].sum())
            self._bump(name, "arb_volume", part["volume_q"].to_numpy()[arb].sum())
            self._bump(name, "fee_income", part["fee_income"].sum())
            self._bump(name, "arb_loss", part["arb_loss"].sum())
            self._bump(name, "lp_gain", part["lp_gain"].sum())
            self._bump(name, "arb_loss_arbs", part["arb_loss"].to_numpy()[arb].sum())
            if "markout_30s" in part:
                self._bump(name, "markout_30s", part["markout_30s"].sum())
                self.sums[name]["has_markout"] = 1.0
            if "p_cex_1s" in part:                 # tick reference in use: how far is the 1s-kline reference from it?
                gap = (part["p_cex_1s"].to_numpy() / part["p_cex"].to_numpy() - 1.0)
                gap = gap[np.isfinite(gap)]
                self._bump(name, "ref_gap_n", len(gap)); self._bump(name, "ref_gap_abs", np.abs(gap).sum()); self._bump(name, "ref_gap_sq", (gap ** 2).sum())
            self.arb_sizes[name].append(part["volume_q"].to_numpy()[arb])
        t = pd.to_datetime(d["ts_ms"], unit="ms", utc=True)
        g = d[DAILY_COLS].groupby(t.dt.floor("D"))
        day = g.sum(); day["swaps"] = g.size()
        self.daily = day if self.daily is None else self.daily.add(day, fill_value=0)
        keys = [t.dt.hour.rename("hour"), pd.Series(np.where(d["block"] < self.fb, "pre", "post"), index=d.index, name="regime")]
        g = d[HOD_COLS].groupby(keys)
        hod = g.sum(); hod["swaps"] = g.size()
        self.hod = hod if self.hod is None else self.hod.add(hod, fill_value=0)
        self.sec_last.append(d.groupby(d["ts_ms"] // 1000 * 1000)["p_post"].last())
        self.n += len(d)

    def last_by_sec(self) -> pd.Series:
        if not self.sec_last:
            return pd.Series(dtype=float)
        s = pd.concat(self.sec_last)
        return s.groupby(level=0).last()

    def daily_table(self) -> pd.DataFrame:
        d = self.daily
        out = pd.DataFrame({"swaps": d["swaps"].astype(int), "volume_quote": d["volume_q"], "arb_share": d["is_arb"] / d["swaps"],
                            "fee_income": d["fee_income"], "arb_loss": d["arb_loss"], "lp_gain": d["lp_gain"]})
        out["arb_loss_bps"] = 1e4 * out["arb_loss"] / out["volume_quote"]
        out["fee_bps"] = 1e4 * out["fee_income"] / out["volume_quote"]
        out.index.name = "ts_ms"
        return out

    def hour_of_day_table(self) -> pd.DataFrame:
        h = self.hod
        out = pd.DataFrame({"swaps": h["swaps"].astype(int), "volume_quote": h["volume_q"], "arb_share": h["is_arb"] / h["swaps"],
                            "arb_loss": h["arb_loss"], "fee_income": h["fee_income"]})
        out["arb_loss_bps"] = 1e4 * out["arb_loss"] / out["volume_quote"]
        return out.unstack("regime")


def regime_table(acc: Accumulator, blocks: pd.DataFrame, s1: pd.DataFrame, fork_block: int, fee: float,
                 block_range: tuple[int, int] | None = None, log=None) -> pd.DataFrame:
    """Pre/post comparison from the accumulated swap statistics and the 1s series.  `blocks` is the complete
    block table (number, milli_ts, interval); block counts come from `block_range` when given."""
    b0 = block_range[0] if block_range else int(blocks["number"].min())
    b1 = block_range[1] if block_range else int(blocks["number"].max())
    t_fork = blocks.loc[blocks.number >= fork_block, "milli_ts"].min()
    kb = int(np.searchsorted(blocks["number"].to_numpy(), fork_block, side="left"))
    ks = int(np.searchsorted(s1["ts_ms"].to_numpy(), t_fork, side="left"))
    rows = []
    for name, b, s, n_blocks in (("pre", blocks.iloc[:kb], s1.iloc[:ks], fork_block - b0),
                                 ("post", blocks.iloc[kb:], s1.iloc[ks:], b1 - fork_block + 1)):
        m = acc.sums[name]
        swaps, vol, n_arb = m.get("swaps", 0.0), m.get("volume_q", 0.0), m.get("n_arb", 0.0)
        sizes = np.concatenate(acc.arb_sizes[name]) if acc.arb_sizes[name] else np.array([])
        hours = (b["milli_ts"].max() - b["milli_ts"].min()) / 3.6e6
        r = {"regime": name, "hours": round(hours, 1), "n_blocks": n_blocks, "n_headers": len(b),
             "block_interval_ms": b["interval"].mean() * 1000, "n_intervals": int(b["interval"].count()),
             "swaps": int(swaps), "swaps_per_block": swaps / max(n_blocks, 1),
             "share_blocks_with_swap": m.get("blocks_with_swap", 0.0) / max(n_blocks, 1),
             "volume_quote_per_hour": vol / max(hours, 1e-9),
             "arb_swaps_share": n_arb / swaps if swaps else np.nan,
             "arb_strict_share": m.get("n_arb_strict", 0.0) / swaps if swaps else np.nan,
             "arb_volume_share": m.get("arb_volume", 0.0) / max(vol, 1e-9),
             "arb_swaps_per_hour": n_arb / max(hours, 1e-9),
             "median_arb_size_quote": float(np.median(sizes)) if len(sizes) else np.nan,
             "fee_bps_of_volume": 1e4 * m.get("fee_income", 0.0) / max(vol, 1e-9),
             "arb_loss_bps_of_volume": 1e4 * m.get("arb_loss", 0.0) / max(vol, 1e-9),
             "lp_net_bps_of_volume": 1e4 * m.get("lp_gain", 0.0) / max(vol, 1e-9),
             "arb_loss_over_fee": m.get("arb_loss", 0.0) / max(m.get("fee_income", 0.0), 1e-9),
             "arb_loss_per_hour_quote": m.get("arb_loss", 0.0) / max(hours, 1e-9),
             "arb_loss_per_arb_quote": m.get("arb_loss_arbs", 0.0) / max(n_arb, 1),
             "mean_abs_dev_bps": 1e4 * s["dev"].abs().mean(),
             "share_sec_outside_band": (s["dev"].abs() > fee).mean() if swaps else np.nan,
             "dev_half_life_s": half_life(s["dev"]),
             "outside_band_episode_mean_s": outside_band_episode_length(s["dev"], fee) if swaps else np.nan,
             "cex_vol_1s_bps": 1e4 * np.log(s["p_cex"]).diff().std(),
             # 1-minute realised volatility expressed per second (less microstructure noise than the 1s std)
             "cex_vol_1m_per_s_bps": 1e4 * np.log(s["p_cex"].iloc[::60]).diff().std() / np.sqrt(60)}
        # theory-normalised loss rates: LVR per unit time scales with sigma^2 (no-fee model) and, in the
        # fast-block regime with fees, roughly with sigma^3 * sqrt(block time)  -> compare these across regimes
        sig = r["cex_vol_1m_per_s_bps"] / 1e4        # use the 1-minute-based estimate
        r["arb_loss_rate_over_sigma2"] = r["arb_loss_per_hour_quote"] / max(sig ** 2, 1e-18)
        r["arb_loss_rate_over_sigma3"] = r["arb_loss_per_hour_quote"] / max(sig ** 3, 1e-18)
        if m.get("has_markout"):
            r["markout_30s_bps_of_volume"] = 1e4 * m.get("markout_30s", 0.0) / max(vol, 1e-9)
        if m.get("ref_gap_n"):            # tick-level reference in use: distance of the 1s-kline reference from it
            r["ref_kline_vs_tick_mean_abs_bps"] = 1e4 * m["ref_gap_abs"] / m["ref_gap_n"]
            r["ref_kline_vs_tick_rms_bps"] = 1e4 * np.sqrt(m["ref_gap_sq"] / m["ref_gap_n"])
        # information shares: bivariate VECM on the 1s series of the 14 days adjacent to the fork (bounded memory
        # for long windows; identical to the full series when the regime is shorter than 14 days)
        s_is = s.iloc[-IS_MAX_SECONDS:] if name == "pre" else s.iloc[:IS_MAX_SECONDS]
        r["IS_window_hours"] = round(len(s_is) / 3600.0, 1)
        if log:
            log(f"    {name}: descriptive statistics done, VECM on {len(s_is):,} seconds… (peak mem {_peak_gb():.1f} GB)")
        try:
            r.update(information_share(s_is["p_pool"].values, s_is["p_cex"].values))
        except Exception as e:  # noqa
            r["IS_error"] = str(e)[:80]
        rows.append(r)
    return pd.DataFrame(rows).set_index("regime").T


class ParquetChunkWriter:
    """Append enriched chunks to one parquet file (one row group per chunk).  Categorical columns are stored as
    plain strings so every chunk shares the same schema; parquet dictionary-encodes them on disk anyway."""

    def __init__(self, path: str):
        self.path, self.tmp, self.writer, self.schema = path, path + ".part", None, None

    def write(self, df: pd.DataFrame) -> None:
        import pyarrow as pa, pyarrow.parquet as pq
        t = pa.Table.from_pandas(df, preserve_index=False)
        if self.schema is None:
            self.schema = pa.schema([pa.field(f.name, f.type.value_type if pa.types.is_dictionary(f.type) else f.type)
                                     for f in t.schema])
            self.writer = pq.ParquetWriter(self.tmp, self.schema)
        self.writer.write_table(t.cast(self.schema))

    def close(self) -> None:
        if self.writer is not None:
            self.writer.close()
            os.replace(self.tmp, self.path)


def _peak_gb() -> float:
    import resource
    v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return v / 1e9 if sys.platform == "darwin" else v / 1e6


def run_chunks(blocks: pd.DataFrame, chunks, cex: pd.DataFrame, fork_block: int, out: str,
               block_range: tuple[int, int] | None = None, log=None, ref: "AggTradeRef | None" = None):
    """Streaming version of the per-pool analysis: `chunks` yields raw swap frames in increasing block order
    (e.g. one per 250k-block segment file).  Each chunk is enriched, appended to swaps_enriched.parquet and
    folded into the running statistics, so memory is bounded by the largest chunk, not by the pool.
    Returns (regime_table, daily_table, n_swaps)."""
    os.makedirs(out, exist_ok=True)
    cex = cex.sort_values("ts_ms")[["ts_ms", "close"]].reset_index(drop=True)
    acc = Accumulator(fork_block)
    writer = ParquetChunkWriter(os.path.join(out, "swaps_enriched.parquet"))
    p_prev, fee = None, None
    for chunk in chunks:
        if chunk is None or len(chunk) == 0:
            continue
        df = prepare_swaps(chunk, blocks, p_prev)
        del chunk
        p_prev = float(df["p_post"].iloc[-1])
        df = attach_cex(df, cex, ref=ref)
        df = swap_metrics(df)
        bad = (df["p_pre"].isna() | df["p_cex"].isna()).to_numpy()
        if bad.any():
            n_bad = int(bad.sum())
            df = df.iloc[n_bad:] if bad[:n_bad].all() else df[~bad]      # head slice is a view; otherwise one copy
        if len(df) == 0:
            continue
        if fee is None:
            fee = float(df["fee_rate"].iloc[0])
        acc.add(df)
        writer.write(df)
        del df
    writer.close()
    if acc.n == 0:
        raise ValueError("no swaps left after alignment with the Binance series")
    log = log or (lambda m: print(m, file=sys.stderr, flush=True))
    log(f"  aggregating {acc.n:,} swaps: 1s series… (peak mem {_peak_gb():.1f} GB)")
    s1 = one_second_series(acc.last_by_sec(), cex, int(blocks["milli_ts"].min()), int(blocks["milli_ts"].max()))
    log(f"  regime statistics + VECM information shares on {len(s1):,} seconds… (peak mem {_peak_gb():.1f} GB)")
    reg = regime_table(acc, blocks, s1, fork_block, fee, block_range, log=log)
    log(f"  daily / hour-of-day tables… (peak mem {_peak_gb():.1f} GB)")
    day = acc.daily_table()
    reg.to_csv(os.path.join(out, "regime_table.csv")); day.to_csv(os.path.join(out, "daily_table.csv"))
    acc.hour_of_day_table().to_csv(os.path.join(out, "hour_of_day_table.csv"))
    with open(os.path.join(out, "regime_table.md"), "w") as f:
        f.write(reg.to_markdown(floatfmt=".4g"))
    print(reg.to_string(float_format=lambda v: f"{v:,.4g}"))
    return reg, day, acc.n


def run(blocks: pd.DataFrame, swaps: pd.DataFrame, cex: pd.DataFrame, fork_block: int, out: str,
        block_range: tuple[int, int] | None = None):
    """Whole-frame convenience wrapper around run_chunks (single chunk).  Returns (regime, daily, n_swaps)."""
    return run_chunks(blocks, [swaps], cex, fork_block, out, block_range)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", required=True); ap.add_argument("--swaps", required=True)
    ap.add_argument("--binance", required=True); ap.add_argument("--fork-block", type=int, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    blocks = pd.read_parquet(a.blocks)
    cex = pd.read_parquet(a.binance)
    files = sorted(glob.glob(a.swaps))
    run_chunks(blocks, (pd.read_parquet(p) for p in files), cex, a.fork_block, a.out)


if __name__ == "__main__":
    main()
