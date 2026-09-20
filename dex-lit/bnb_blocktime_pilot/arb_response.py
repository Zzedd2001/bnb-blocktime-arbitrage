"""Address-level arbitrageur response times — a direct test of the latency floor ℓ (paper §3.2).

For every arbitrage swap the pipeline identified (results_agg/<pool>/swaps_enriched.parquet, tick reference), the
script reconstructs WHEN the opportunity opened and how long the arbitrageur took to close it:

  trigger "cex"          the Binance price left the pool's no-arbitrage band [p_pre·(1−γ), p_pre·(1+γ)] at t_open
                         (last crossing before the block) and stayed outside until the arb block t_b:
                         response time τ = t_b − t_open (ms), from the millisecond tick series
  trigger "onchain"      the previous swap of the pool (an earlier block) pushed the price OUT of the band; the
                         opportunity opened when that block was published: τ = t_b − t_prev (block times only, so
                         no Binance/BSC clock offset enters)
  "continuation"         the previous swap (earlier block) was itself an arb that left the price outside the band
                         (partial arbitrage) or a trade that pushed an already-open opportunity further out
  "same_block"           previous swap in the same block (back-run / bundle): τ = 0 by construction
  "long"                 no crossing found within --max-search seconds before the block (opportunity older than that)

Latency model: the arbitrageur reacts with a fixed delay ℓ and lands in the first block sealed after t_open + ℓ, so
τ = ℓ + wait with wait ~ U(0, Δt).  Direct tests produced here:
  (1) quantiles       Q_q(τ) = ℓ + q·Δt  ->  ℓ̂_q = Q_q(τ) − q·Δt should not depend on q nor on the regime
  (2) intervals       the tx was not in the block before b, so ℓ ∈ (t_{b−1} − t_open, t_b − t_open]; the Turnbull
                      NPMLE and a log-normal MLE of the ℓ distribution use exactly these interval-censored data
  (3) blocks skipped  k = number of blocks in (t_open, t_b];  P(k = 1) = E[max(0, 1 − ℓ/Δt)]
  (4) implied effect  log(E[√τ]_post / E[√τ]_pre) is the fork effect on overshoot implied by the response times,
                      to be compared with the tick-reference estimates and with the √Δt law ½·ln(Δt₁/Δt₀); the
                      fixed-latency counterfactual (pre-fork ℓ distribution + post-fork Δt) separates the
                      mechanical block-wait effect from any change in the arbitrageurs' own latency
  (5) decomposition   |dev_pre| − γ = excess at the crossing tick (a jump the block interval cannot remove)
                      + CEX move during τ (the part that shrinks with faster blocks)

Address level: `sender` (the contract that called the pool) identifies the arbitrageur.  Per regime: concentration
(HHI, top shares, entrants/exits), the top senders' response times, and for senders active before AND after the
fork the change in their median / 10th-percentile τ against the mechanical shifts (Δt/2, 0.1·Δt) of the model.

    python arb_response.py --out full_fermi --fork Fermi                       # all pools with a Binance reference
    python arb_response.py --out full_fermi --fork Fermi --pools WBNB-USDT-500 ETH-USDT-500 BTCB-USDT-500
    python arb_response.py --out full_fermi --fork Fermi --reuse --exclude-senders public_contracts_Fermi.csv
        # bots only: reuse the openings of the first run, drop arbs sent through public routers -> arb_response_bots/, arb_response_bots_Fermi.zip

Outputs in <out>/arb_response/:  <pool>/arbs.parquet (per-arb table, kept locally), <pool>/regime_stats.json,
<pool>/top_senders.csv, <pool>/paired_senders.csv, <pool>/turnbull.csv, fig_<pool>.png, tables.md, summary.json,
fig_quantiles.png, and arb_response_<fork>.zip (everything except the full per-arb tables, replaced by a random
sample of 100k arbs per pool) for upload.  Rerunning reuses nothing but is fast (minutes per pool).
"""
from __future__ import annotations
import argparse, glob, json, os, sys, time, zipfile
import numpy as np, pandas as pd
import pyarrow.parquet as pq
import config as C

DAY_MS = 86_400_000
ARB_COLS = ["block", "log_index", "sender", "ts_ms", "p_pre", "p_post", "p_cex", "dev_pre", "dev_post",
            "is_arb", "is_arb_strict", "volume_q", "arb_loss", "fee_rate"]
QS = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90)


def log(m: str) -> None:
    print(time.strftime("%H:%M:%S"), m, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- inputs
def load_summary(out: str, subdir: str) -> dict:
    tag = subdir[len("results"):]
    p = os.path.join(out, f"summary{tag}.json")
    if not os.path.exists(p):
        raise SystemExit(f"{p} not found: run run_pilot.py --reference aggtrades first")
    return json.load(open(p))


def block_timestamps(out: str, fork: str, b0: int, b1: int) -> np.ndarray:
    p = os.path.join(out, f"timestamps_{fork}_{b0}_{b1}.parquet")
    t = pd.read_parquet(p, columns=["number", "milli_ts"]).sort_values("number")
    num = t["number"].to_numpy(np.int64)
    if num[0] != b0 or num[-1] != b1 or len(num) != b1 - b0 + 1:
        raise SystemExit(f"{p}: expected a contiguous table {b0}..{b1}")
    return t["milli_ts"].to_numpy(np.int64)


def count_swaps_by_sender(path: str, fork_block: int) -> dict:
    """{"pre"/"post": swaps per sender} from swaps_enriched.parquet (block and sender columns only; for --reuse)."""
    pf = pq.ParquetFile(path)
    n_by_sender = {"pre": {}, "post": {}}
    for batch in pf.iter_batches(batch_size=2_000_000, columns=["block", "sender"]):
        d = batch.to_pandas()
        pre = d["block"].to_numpy() < fork_block
        for name, m in (("pre", pre), ("post", ~pre)):
            for k, v in d.loc[m, "sender"].value_counts().items():
                if v:
                    n_by_sender[name][str(k)] = n_by_sender[name].get(str(k), 0) + int(v)
    return n_by_sender


def load_excluded_senders(path: str) -> set:
    """Sender contracts to drop (CSV with a `sender` column, e.g. public_contracts_<fork>.csv or arb_operators.py's
    contracts_<fork>.csv; when a `public` column exists only rows with public == True are used)."""
    d = pd.read_csv(path)
    if "sender" not in d.columns:
        d = d.rename(columns={d.columns[0]: "sender"})
    if "public" in d.columns:
        d = d[d["public"].astype(str).str.lower().isin(("true", "1"))]
    return set(d["sender"].astype(str).str.lower())


def stream_arbs(path: str, fork_block: int):
    """Arb rows of swaps_enriched.parquet with the previous swap's state attached (streamed; memory bounded by one
    batch).  Returns (arbs DataFrame, {"pre"/"post": swaps per sender})."""
    pf = pq.ParquetFile(path)
    cols = [c for c in ARB_COLS if c in pf.schema_arrow.names]
    keep, prev = [], None
    n_by_sender = {"pre": {}, "post": {}}
    for batch in pf.iter_batches(batch_size=1_000_000, columns=cols):
        d = batch.to_pandas()
        if len(d) == 0:
            continue
        if not d["sender"].dtype.name.startswith("category"):
            d["sender"] = d["sender"].astype("category")
        # previous swap of the pool (block order == file order)
        for c in ("ts_ms", "block", "dev_pre", "dev_post", "is_arb"):
            s = d[c].shift(1)
            if prev is not None:
                s.iloc[0] = prev[c]
            d[f"prev_{c}"] = s
        prev = {c: d[c].iloc[-1] for c in ("ts_ms", "block", "dev_pre", "dev_post", "is_arb")}
        pre = d["block"].to_numpy() < fork_block
        for name, m in (("pre", pre), ("post", ~pre)):
            for k, v in d.loc[m, "sender"].value_counts().items():
                if v:
                    n_by_sender[name][str(k)] = n_by_sender[name].get(str(k), 0) + int(v)
        keep.append(d[d["is_arb"].to_numpy()].copy())
        del d
    if not keep:
        return pd.DataFrame(columns=cols), n_by_sender
    a = pd.concat(keep, ignore_index=True)
    a["sender"] = a["sender"].astype(str).astype("category")
    a = a.dropna(subset=["prev_ts_ms"]).reset_index(drop=True)
    for c in ("prev_ts_ms", "prev_block"):
        a[c] = a[c].astype(np.int64)
    return a, n_by_sender


# ---------------------------------------------------------------- tick series
def _asof(keys, vals, q):
    i = np.searchsorted(keys, q, side="right") - 1
    out = np.full(len(q), np.nan)
    ok = i >= 0
    out[ok] = vals[i[ok]]
    return out


def load_ticks(dirs: list[str], day0: int, day1: int):
    """(ts, price) for days day0..day1 (day index = ms // DAY_MS).  Cross rate (two directories): union of the
    timestamps, price = base as-of / quote as-of."""
    series = []
    for d in dirs:
        parts = []
        for day in range(day0, day1 + 1):
            p = os.path.join(d, pd.Timestamp(day * DAY_MS, unit="ms", tz="UTC").strftime("%Y-%m-%d") + ".parquet")
            if os.path.exists(p):
                t = pd.read_parquet(p)
                parts.append((t["ts_ms"].to_numpy(np.int64), t["price"].to_numpy(np.float64)))
        if not parts:
            return np.empty(0, np.int64), np.empty(0)
        series.append((np.concatenate([a for a, _ in parts]), np.concatenate([b for _, b in parts])))
    if len(series) == 1:
        return series[0]
    (t1, p1), (t2, p2) = series
    ts = np.union1d(t1, t2)
    a, b = _asof(t1, p1, ts), _asof(t2, p2, ts)
    ok = ~np.isnan(a) & ~np.isnan(b)
    return ts[ok], a[ok] / b[ok]


def last_inside(px: np.ndarray, lo_idx: np.ndarray, hi_idx: np.ndarray, lo_p: np.ndarray, hi_p: np.ndarray,
                slab: int = 5_000) -> np.ndarray:
    """For each query: the largest j in [lo_idx, hi_idx] with lo_p <= px[j] <= hi_p, or −1.  Vectorised backward
    exponential search (windows of 32, 64, … 2048 ticks) over slabs of queries."""
    n = len(hi_idx)
    res = np.full(n, -1, dtype=np.int64)
    for s in range(0, n, slab):
        ids = np.arange(s, min(s + slab, n))
        cur = hi_idx[ids].copy()
        active = (cur >= lo_idx[ids])
        W = 32
        while active.any():
            a = np.where(active)[0]
            starts = np.maximum(cur[a] - W + 1, lo_idx[ids[a]])
            idx = starts[:, None] + np.arange(W)[None, :]
            valid = idx <= cur[a][:, None]
            p = px[np.minimum(idx, len(px) - 1)]
            inside = valid & (p >= lo_p[ids[a]][:, None]) & (p <= hi_p[ids[a]][:, None])
            has = inside.any(axis=1)
            last = W - 1 - np.argmax(inside[:, ::-1], axis=1)
            res[ids[a[has]]] = idx[np.arange(len(a)), last][has]
            exhausted = (~has) & (starts <= lo_idx[ids[a]])
            active[a[has | exhausted]] = False
            cont = a[~has & ~exhausted]
            cur[cont] = starts[~has & ~exhausted] - 1
            W = min(W * 2, 2048)
    return res


def find_openings(a: pd.DataFrame, dirs: list[str], gamma: float, mults=(1.0, 1.5, 2.0), max_search_ms: int = 120_000):
    """t_open / trigger type / crossing price per arb, for each band multiplier.  Ticks are loaded two days at a
    time (the arb's day and the day before)."""
    n = len(a)
    tb = a["ts_ms"].to_numpy(np.int64); tp = a["prev_ts_ms"].to_numpy(np.int64)
    p_pre = a["p_pre"].to_numpy(np.float64)
    prev_in = np.abs(a["prev_dev_post"].to_numpy(np.float64)) <= gamma
    prev_pre_in = np.abs(a["prev_dev_pre"].to_numpy(np.float64)) <= gamma
    same_block = tp == tb
    out = {}
    for m in mults:
        out[m] = {"t_open": np.full(n, -1, np.int64), "trigger": np.full(n, "", dtype=object), "p_open": np.full(n, np.nan)}
    days = tb // DAY_MS
    for day in np.unique(days):
        sel = np.where(days == day)[0]
        ts, px = load_ticks(dirs, int(day) - 1, int(day))
        if len(ts) == 0:
            for m in mults:
                out[m]["trigger"][sel] = "no_ticks"
            continue
        hi = np.searchsorted(ts, tb[sel], side="right") - 1                  # last tick <= t_b (the reference used)
        floor = np.maximum(tp[sel], tb[sel] - max_search_ms)
        lo = np.searchsorted(ts, floor, side="right")                          # first tick > max(t_prev, t_b − max_search)
        dev_abs = np.abs(a["dev_pre"].to_numpy(np.float64)[sel])
        for m in mults:
            band = m * gamma
            # inside the band in the pipeline's metric: |p_pre / price − 1| <= band  <=>  p_pre/(1+band) <= price <= p_pre/(1−band)
            lo_p = p_pre[sel] / (1 + band); hi_p = p_pre[sel] / (1 - band)
            j = last_inside(px, lo, hi, lo_p, hi_p)
            found = j >= 0
            t_open = np.full(len(sel), -1, np.int64); trig = np.full(len(sel), "", dtype=object); p_open = np.full(len(sel), np.nan)
            # (i) crossing found: opportunity opened at the first tick after the last inside tick
            jo = np.minimum(j + 1, len(ts) - 1)
            t_open[found] = ts[jo[found]]; p_open[found] = px[jo[found]]; trig[found] = "cex"
            # (ii) nothing inside within the search range
            nf = ~found
            sb = nf & same_block[sel]
            trig[sb] = "same_block"; t_open[sb] = tb[sel][sb]
            rest = nf & ~sb
            prev_inside = prev_in[sel] if m == 1.0 else (np.abs(a["prev_dev_post"].to_numpy(np.float64)[sel]) <= band)
            first_tick_ok = rest & prev_inside & (lo <= hi)                  # crossed with the first tick after t_prev
            t_open[first_tick_ok] = ts[lo[first_tick_ok]]; p_open[first_tick_ok] = px[lo[first_tick_ok]]; trig[first_tick_ok] = "cex"
            rest = rest & ~first_tick_ok
            long = rest & (floor > tp[sel])                                    # search window did not reach t_prev
            trig[long] = "long"
            rest = rest & ~long
            onchain = rest & (~prev_inside) & (prev_pre_in[sel] if m == 1.0 else (np.abs(a["prev_dev_pre"].to_numpy(np.float64)[sel]) <= band))
            trig[onchain] = "onchain"; t_open[onchain] = tp[sel][onchain]
            rest = rest & ~onchain
            trig[rest] = "continuation"; t_open[rest] = tp[sel][rest]
            if m != 1.0:                                                   # the wider band never opened for these arbs
                below = dev_abs <= band
                trig[below] = "below_threshold"; t_open[below] = -1; p_open[below] = np.nan
            out[m]["t_open"][sel] = t_open; out[m]["trigger"][sel] = trig; out[m]["p_open"][sel] = p_open
    return out


# ---------------------------------------------------------------- latency estimators
def turnbull(L: np.ndarray, R: np.ndarray, grid: np.ndarray, iters: int = 300):
    """NPMLE (Turnbull EM) of the distribution of ℓ from interval-censored observations ℓ ∈ (L, R]; mass on `grid`.
    Returns the probability mass on the grid (sums to 1)."""
    G = len(grid)
    lo = np.searchsorted(grid, L, side="right"); hi = np.searchsorted(grid, R, side="right")
    ok = hi > lo
    lo, hi = lo[ok], hi[ok]
    n = len(lo)
    if n == 0:
        return np.full(G, np.nan)
    p = np.full(G, 1.0 / G)
    for _ in range(iters):
        c = np.concatenate([[0.0], np.cumsum(p)])
        w = 1.0 / np.maximum(c[hi] - c[lo], 1e-300)
        diff = np.zeros(G + 1)
        np.add.at(diff, lo, w); np.add.at(diff, hi, -w)
        p_new = np.cumsum(diff)[:G] * p / n
        p_new /= p_new.sum()
        done = np.abs(p_new - p).max() < 1e-10
        p = p_new
        if done:
            break
    return p


def lognormal_interval_mle(L: np.ndarray, R: np.ndarray):
    """ℓ ~ log-normal fitted to interval-censored data (L, R] (ms).  Returns (median_ms, sigma, mean_ms)."""
    from scipy import optimize, stats
    L = np.maximum(L, 0.0); R = np.maximum(R, L + 1.0)

    def nll(th):
        mu, ls = th; s = np.exp(ls)
        FR = stats.norm.cdf((np.log(R) - mu) / s)
        FL = np.where(L > 0, stats.norm.cdf((np.log(np.maximum(L, 1e-9)) - mu) / s), 0.0)
        return -np.sum(np.log(np.maximum(FR - FL, 1e-300)))
    r = optimize.minimize(nll, x0=[np.log(np.median(R)), 0.0], method="Nelder-Mead", options={"maxiter": 2000, "xatol": 1e-6, "fatol": 1e-6})
    mu, s = r.x[0], float(np.exp(r.x[1]))
    return float(np.exp(mu)), s, float(np.exp(mu + s * s / 2))


def mean_sqrt_counterfactual(mass: np.ndarray, grid: np.ndarray, dt_ms: float, n_u: int = 200) -> float:
    """E[√τ] when τ = ℓ + U(0, Δt) and ℓ has the given mass on `grid` (ms)."""
    u = (np.arange(n_u) + 0.5) / n_u * dt_ms
    return float(np.nansum(mass[:, None] * np.sqrt(grid[:, None] + u[None, :]) / n_u))


def p_first_block_counterfactual(mass: np.ndarray, grid: np.ndarray, dt_ms: float) -> float:
    return float(np.nansum(mass * np.maximum(0.0, 1 - grid / dt_ms)))


# ---------------------------------------------------------------- statistics
def regime_stats(a: pd.DataFrame, mask: np.ndarray, dt_ms: float, max_tau_ms: int, grid: np.ndarray) -> dict:
    d = a[mask]
    n = len(d)
    r = {"n_arb": int(n), "n_arb_strict": int(d["is_arb_strict"].sum()), "dt_ms": float(dt_ms)}
    if n == 0:
        return r
    tt = d["trigger"].value_counts()
    r["trigger_share"] = {k: float(v / n) for k, v in tt.items()}
    for trig in ("cex", "onchain", "continuation", "same_block", "long"):
        s = d[d["trigger"] == trig]
        if len(s):
            r[f"overshoot_bps_mean_{trig}"] = float(s["overshoot_bps"].mean())
    cex = d[(d["trigger"] == "cex") & (d["tau_ms"] <= max_tau_ms)]
    r["n_cex"] = int(len(cex)); r["share_cex_tau_le_max"] = float(len(cex) / max(int((d["trigger"] == "cex").sum()), 1))
    if len(cex) >= 30:
        tau = cex["tau_ms"].to_numpy(np.float64)
        q = {f"p{int(x * 100)}": float(np.quantile(tau, x)) for x in QS}
        r["tau_ms"] = {**q, "mean": float(tau.mean()), "share_lt_100ms": float((tau < 100).mean()),
                       "share_lt_dt": float((tau < dt_ms).mean()), "mean_sqrt_s": float(np.sqrt(tau / 1000).mean())}
        r["ell_quantile_ms"] = {f"q{int(x * 100)}": float(np.quantile(tau, x) - x * dt_ms) for x in (0.10, 0.25, 0.50)}
        k = cex["k_blocks"].to_numpy(np.int64)
        r["k_blocks"] = {"p_k1": float((k == 1).mean()), "p_k2": float((k == 2).mean()), "p_k3plus": float((k >= 3).mean()), "mean": float(k.mean())}
        L = np.maximum(cex["tau_lo_ms"].to_numpy(np.float64), 0.0); R = tau
        mass = turnbull(L, R, grid)
        cdf = np.cumsum(mass)
        r["turnbull_ms"] = {"p25": float(grid[np.searchsorted(cdf, 0.25)]), "median": float(grid[np.searchsorted(cdf, 0.5)]),
                            "p75": float(grid[np.searchsorted(cdf, 0.75)]), "mean": float(np.nansum(mass * grid)),
                            "p_le_dt": float(cdf[min(np.searchsorted(grid, dt_ms), len(cdf) - 1)])}
        r["_turnbull_mass"] = mass
        med, sig, mean = lognormal_interval_mle(L, R)
        r["lognormal_ms"] = {"median": med, "sigma": sig, "mean": mean}
        r["decomposition_bps"] = {"overshoot": float(cex["overshoot_bps"].mean()), "jump": float(cex["jump_bps"].mean()),
                                  "move": float(cex["move_bps"].mean()), "median_overshoot": float(cex["overshoot_bps"].median()),
                                  "median_jump": float(cex["jump_bps"].median()), "share_jump_gt_half": float((cex["jump_bps"] > 0.5 * cex["overshoot_bps"]).mean())}
        # sensitivity: response time with wider bands (opening = crossing of 1.5γ / 2γ)
        for m in (1.5, 2.0):
            c = f"tau_ms_m{m}"
            if c in cex:
                v = cex.loc[cex[f"trigger_m{m}"] == "cex", c].to_numpy(np.float64)
                v = v[v <= max_tau_ms]
                if len(v) >= 30:
                    r[f"tau_ms_band{m}"] = {"p10": float(np.quantile(v, 0.10)), "p50": float(np.quantile(v, 0.50)), "mean": float(v.mean()),
                                            "n": int(len(v)), "ell_q10_ms": float(np.quantile(v, 0.10) - 0.10 * dt_ms), "ell_q50_ms": float(np.quantile(v, 0.5) - 0.5 * dt_ms)}
    on = d[(d["trigger"] == "onchain") & (d["tau_ms"] <= max_tau_ms)]
    r["n_onchain"] = int(len(on))
    if len(on) >= 30:
        # the trigger block is on the block grid, so the arb lands k = ceil(ℓ/Δt) blocks later: P(k <= j) = P(ℓ <= j·Δt)
        # (a lower bound for ℓ's CDF if some bots react to the pending trade in the mempool)
        k = on["k_blocks"].to_numpy(np.int64); tau = on["tau_ms"].to_numpy(np.float64)
        r["onchain"] = {"p_k1": float((k == 1).mean()), "p_k2": float((k == 2).mean()), "p_k3plus": float((k >= 3).mean()), "mean_k": float(k.mean()),
                        "tau_p50": float(np.median(tau)), "tau_mean": float(tau.mean()), "mean_sqrt_s": float(np.sqrt(tau / 1000).mean()),
                        "cdf_ell_at_j_dt": {f"{j}": float((k <= j).mean()) for j in (1, 2, 3, 4)}, "dt_ms": float(dt_ms)}
    # sharp openings: the crossing tick jumped at least half a fee band beyond the edge (t_open unambiguous)
    if len(cex) >= 30:
        sh = cex[cex["jump_bps"] >= 0.5 * cex["fee_rate"] * 1e4]
        if len(sh) >= 30:
            v = sh["tau_ms"].to_numpy(np.float64)
            r["tau_ms_sharp"] = {"n": int(len(sh)), "p10": float(np.quantile(v, .1)), "p50": float(np.median(v)), "mean": float(v.mean()),
                                 "p_k1": float((sh["k_blocks"] == 1).mean()), "ell_q10_ms": float(np.quantile(v, .1) - 0.1 * dt_ms), "ell_q50_ms": float(np.median(v) - 0.5 * dt_ms)}
    return r


def hhi(counts: pd.Series) -> float:
    s = counts / counts.sum()
    return float((s ** 2).sum())


def address_stats(a: pd.DataFrame, mask: np.ndarray, n_by_sender: dict, min_arbs: int, max_tau_ms: int) -> tuple[dict, pd.DataFrame]:
    d = a[mask & a["is_arb_strict"].to_numpy()]
    out = {}
    if len(d) == 0:
        return out, pd.DataFrame()
    cnt = d["sender"].value_counts()
    cnt = cnt[cnt > 0]
    vol = d.groupby("sender", observed=True)["volume_q"].sum().reindex(cnt.index).fillna(0)
    out["n_senders"] = int(len(cnt)); out["hhi_count"] = hhi(cnt); out["hhi_volume"] = hhi(vol[vol > 0])
    sh = cnt / cnt.sum()
    out["top1_share"] = float(sh.iloc[0]); out["top3_share"] = float(sh.iloc[:3].sum()); out["top5_share"] = float(sh.iloc[:5].sum())
    out["n_senders_90pct"] = int((sh.cumsum() < 0.9).sum() + 1)
    big = cnt[cnt >= min_arbs]
    bots = [s for s in big.index if big[s] / max(n_by_sender.get(s, big[s]), 1) >= 0.5]
    out["n_active_ge_min"] = int(len(big)); out["n_bots"] = int(len(bots)); out["bots_share_of_arbs"] = float(cnt[bots].sum() / cnt.sum()) if bots else 0.0
    rows = []
    for s in cnt.index[:15]:
        x = d[d["sender"] == s]
        c = x[(x["trigger"] == "cex") & (x["tau_ms"] <= max_tau_ms)]
        rows.append({"sender": s, "n_arb_strict": int(cnt[s]), "share": float(sh[s]), "arb_share_of_own_swaps": float(cnt[s] / max(n_by_sender.get(s, cnt[s]), 1)),
                     "n_cex": int(len(c)), "tau_p10_ms": float(np.quantile(c["tau_ms"], 0.1)) if len(c) >= 20 else np.nan,
                     "tau_p50_ms": float(np.median(c["tau_ms"])) if len(c) >= 20 else np.nan,
                     "p_k1": float((c["k_blocks"] == 1).mean()) if len(c) >= 20 else np.nan,
                     "overshoot_bps": float(x["overshoot_bps"].mean()), "arb_loss_sum_quote": float(x["arb_loss"].sum()), "volume_quote": float(x["volume_q"].sum()),
                     "share_same_block": float((x["trigger"] == "same_block").mean())})
    return out, pd.DataFrame(rows)


def paired_senders(a: pd.DataFrame, pre: np.ndarray, post: np.ndarray, dt_pre: float, dt_post: float, min_pair: int, max_tau_ms: int) -> pd.DataFrame:
    rows = []
    c = a[(a["trigger"] == "cex") & (a["tau_ms"] <= max_tau_ms) & a["is_arb_strict"].to_numpy()]
    cp, cq = c[pre[c.index]], c[post[c.index]]
    common = set(cp["sender"].value_counts().loc[lambda s: s >= min_pair].index) & set(cq["sender"].value_counts().loc[lambda s: s >= min_pair].index)
    for s in common:
        x, y = cp[cp["sender"] == s]["tau_ms"].to_numpy(np.float64), cq[cq["sender"] == s]["tau_ms"].to_numpy(np.float64)
        kx, ky = cp[cp["sender"] == s]["k_blocks"].to_numpy(), cq[cq["sender"] == s]["k_blocks"].to_numpy()
        rows.append({"sender": s, "n_pre": len(x), "n_post": len(y), "p10_pre": np.quantile(x, .1), "p10_post": np.quantile(y, .1),
                     "p50_pre": np.median(x), "p50_post": np.median(y), "d_p10_ms": np.quantile(y, .1) - np.quantile(x, .1),
                     "d_p50_ms": np.median(y) - np.median(x), "mechanical_d_p10_ms": 0.1 * (dt_post - dt_pre), "mechanical_d_p50_ms": 0.5 * (dt_post - dt_pre),
                     "ell_q10_pre_ms": np.quantile(x, .1) - 0.1 * dt_pre, "ell_q10_post_ms": np.quantile(y, .1) - 0.1 * dt_post,
                     "ell_q50_pre_ms": np.median(x) - 0.5 * dt_pre, "ell_q50_post_ms": np.median(y) - 0.5 * dt_post,
                     "p_k1_pre": (kx == 1).mean(), "p_k1_post": (ky == 1).mean()})
    return pd.DataFrame(rows).sort_values("n_post", ascending=False) if rows else pd.DataFrame()


# ---------------------------------------------------------------- per pool
def run_pool(a: pd.DataFrame, n_by_sender: dict, dirs: list[str], mts: np.ndarray, b0: int, fork_block: int, fork_ms: int,
             args, out_dir: str, pool: str, precomputed: bool = False) -> dict:
    """n_by_sender: {"pre": {sender: swaps}, "post": {...}} (all swaps, for the arb share of each sender's activity).
    precomputed: `a` already carries the opening/response columns (from an earlier run's arbs.parquet, possibly filtered
    by sender); only the statistics are redone and the filtered table is saved to out_dir."""
    os.makedirs(out_dir, exist_ok=True)
    gamma = float(a["fee_rate"].iloc[0])
    if precomputed:
        log(f"{pool}: {len(a):,} arbs ({int(a['is_arb_strict'].sum()):,} strict) reused with the earlier openings")
        a = a.reset_index(drop=True)
        a.to_parquet(os.path.join(out_dir, "arbs.parquet"), index=False)
        return pool_stats(a, n_by_sender, mts, b0, fork_block, args, out_dir, pool, gamma)
    log(f"{pool}: {len(a):,} arbs ({int(a['is_arb_strict'].sum()):,} strict), γ = {gamma * 1e4:.0f} bp; locating openings…")
    op = find_openings(a, dirs, gamma, mults=(1.0, 1.5, 2.0), max_search_ms=args.max_search * 1000)
    a["t_open"] = op[1.0]["t_open"]; a["trigger"] = pd.Categorical(op[1.0]["trigger"]); a["p_open"] = op[1.0]["p_open"]
    for m in (1.5, 2.0):
        a[f"t_open_m{m}"] = op[m]["t_open"]; a[f"trigger_m{m}"] = pd.Categorical(op[m]["trigger"])
        a[f"tau_ms_m{m}"] = np.where(op[m]["t_open"] >= 0, a["ts_ms"].to_numpy(np.int64) - op[m]["t_open"], -1)
    tb = a["ts_ms"].to_numpy(np.int64); to = a["t_open"].to_numpy(np.int64)
    a["tau_ms"] = np.where(to >= 0, tb - to, -1)
    idx_b = a["block"].to_numpy(np.int64) - b0
    if not np.array_equal(mts[idx_b], tb):
        log(f"  WARNING: {int((mts[idx_b] != tb).sum()):,} arb timestamps differ from the block table (using the table)")
        tb = mts[idx_b]; a["ts_ms"] = tb; a["tau_ms"] = np.where(to >= 0, tb - to, -1)
    first_after = np.searchsorted(mts, np.where(to >= 0, to, tb), side="right")     # index of the first block > t_open
    a["k_blocks"] = np.where(to >= 0, idx_b - first_after + 1, 0)
    prev_block_ts = mts[np.maximum(idx_b - 1, 0)]
    a["tau_lo_ms"] = np.where(to >= 0, prev_block_ts - to, -1)                         # ℓ > t_{b−1} − t_open
    dev = np.abs(a["dev_pre"].to_numpy(np.float64))
    a["overshoot_bps"] = (dev - gamma) * 1e4
    p_open = a["p_open"].to_numpy(np.float64); p_pre = a["p_pre"].to_numpy(np.float64)
    jump = (np.abs(p_pre / p_open - 1) - gamma) * 1e4
    a["jump_bps"] = np.where(a["trigger"] == "cex", np.maximum(jump, 0.0), np.nan)
    a["move_bps"] = a["overshoot_bps"] - a["jump_bps"]
    a["regime"] = np.where(a["block"].to_numpy(np.int64) < fork_block, "pre", "post")
    a["days_from_fork"] = (tb - fork_ms) / DAY_MS
    a.to_parquet(os.path.join(out_dir, "arbs.parquet"), index=False)
    return pool_stats(a, n_by_sender, mts, b0, fork_block, args, out_dir, pool, gamma)


def pool_stats(a: pd.DataFrame, n_by_sender: dict, mts: np.ndarray, b0: int, fork_block: int, args, out_dir: str, pool: str, gamma: float) -> dict:
    """Regime statistics, implied effects, paired senders, entrants and the figure for one pool (after the openings)."""
    # block intervals per regime (exact, from the timestamp table)
    dt = {"pre": float(np.diff(mts[: fork_block - b0]).mean()), "post": float(np.diff(mts[fork_block - b0:]).mean())}
    grid = np.arange(0.0, args.grid_max * 1000.0 + 1, args.grid_step)
    res = {"pool": pool, "gamma": gamma, "n_arb": int(len(a)), "dt_ms": dt, "windows": {}}
    ind = a.index.to_numpy()
    for w in (args.days, 14):
        if w > args.days:
            continue
        inw = np.abs(a["days_from_fork"].to_numpy()) <= w
        pre = inw & (a["regime"].to_numpy() == "pre"); post = inw & (a["regime"].to_numpy() == "post")
        R = {}
        for name, mask in (("pre", pre), ("post", post)):
            R[name] = regime_stats(a, mask, dt[name], args.max_tau * 1000, grid)
            R[name]["addresses"], top = address_stats(a, mask, n_by_sender[name], args.min_arbs, args.max_tau * 1000)
            if w == args.days:
                top.to_csv(os.path.join(out_dir, f"top_senders_{name}.csv"), index=False)
        # implied fork effects and counterfactuals
        eff = {"sqrt_law": 0.5 * np.log(dt["post"] / dt["pre"])}
        if "tau_ms" in R["pre"] and "tau_ms" in R["post"]:
            eff["implied_from_tau"] = float(np.log(R["post"]["tau_ms"]["mean_sqrt_s"] / R["pre"]["tau_ms"]["mean_sqrt_s"]))
            x = eff["implied_from_tau"]; e2 = np.exp(2 * x)
            eff["ell_paper_equiv_s"] = float(max((dt["post"] - e2 * dt["pre"]) / (e2 - 1), 0.0) / 1000)
            mass = R["pre"]["_turnbull_mass"]
            cf = mean_sqrt_counterfactual(mass, grid / 1000, dt["post"] / 1000)
            eff["counterfactual_fixed_latency"] = float(np.log(cf / R["pre"]["tau_ms"]["mean_sqrt_s"]))
            eff["latency_change_component"] = eff["implied_from_tau"] - eff["counterfactual_fixed_latency"]
            eff["p_k1_post_counterfactual"] = p_first_block_counterfactual(mass, grid, dt["post"])
            eff["p_k1_post_actual"] = R["post"]["k_blocks"]["p_k1"]
            eff["d_median_tau_ms"] = R["post"]["tau_ms"]["p50"] - R["pre"]["tau_ms"]["p50"]; eff["mechanical_d_median_ms"] = 0.5 * (dt["post"] - dt["pre"])
            eff["d_p10_tau_ms"] = R["post"]["tau_ms"]["p10"] - R["pre"]["tau_ms"]["p10"]; eff["mechanical_d_p10_ms"] = 0.1 * (dt["post"] - dt["pre"])
            eff["d_log_overshoot_cex"] = float(np.log(R["post"]["decomposition_bps"]["overshoot"] / R["pre"]["decomposition_bps"]["overshoot"]))
            for part in ("move", "jump"):
                x0, x1 = R["pre"]["decomposition_bps"][part], R["post"]["decomposition_bps"][part]
                eff[f"d_log_{part}_cex"] = float(np.log(x1 / x0)) if x0 > 0 and x1 > 0 else float("nan")
        if "onchain" in R["pre"] and "onchain" in R["post"]:
            eff["implied_from_tau_onchain"] = float(np.log(R["post"]["onchain"]["mean_sqrt_s"] / R["pre"]["onchain"]["mean_sqrt_s"]))
        if w == args.days:
            tb_ = pd.DataFrame({"grid_ms": grid, **{f"mass_{k}": R[k].get("_turnbull_mass", np.full(len(grid), np.nan)) for k in ("pre", "post")}})
            tb_.to_csv(os.path.join(out_dir, "turnbull.csv"), index=False)
            pr = paired_senders(a, pre, post, dt["pre"], dt["post"], args.min_pair, args.max_tau * 1000)
            pr.to_csv(os.path.join(out_dir, "paired_senders.csv"), index=False)
            eff["paired_senders"] = {"n": int(len(pr)),
                                     "median_d_p10_ms": float(pr["d_p10_ms"].median()) if len(pr) else np.nan,
                                     "median_d_p50_ms": float(pr["d_p50_ms"].median()) if len(pr) else np.nan,
                                     "share_faster_than_mechanical_p10": float((pr["d_p10_ms"] < pr["mechanical_d_p10_ms"] - 50).mean()) if len(pr) else np.nan}
            A0, A1 = set(), set()
            for name, mask, S in (("pre", pre, A0), ("post", post, A1)):
                c = a[mask & a["is_arb_strict"].to_numpy()]["sender"].value_counts()
                S.update(c[c >= args.min_arbs].index)
            post_cnt = a[post & a["is_arb_strict"].to_numpy()]["sender"].value_counts()
            eff["entrants"] = {"n_entrants": len(A1 - A0), "n_exits": len(A0 - A1), "n_stayers": len(A0 & A1),
                               "entrants_share_of_post_arbs": float(post_cnt[list(A1 - A0)].sum() / post_cnt.sum()) if len(post_cnt) else np.nan}
        for name in ("pre", "post"):
            R[name].pop("_turnbull_mass", None)
        res["windows"][f"{w}d"] = {"pre": R["pre"], "post": R["post"], "effects": eff}
    json.dump(res, open(os.path.join(out_dir, "regime_stats.json"), "w"), indent=1, default=float)
    try:
        plot_pool(a, res, grid, os.path.join(out_dir, f"fig_{pool}.png"), pool, args)
    except Exception as e:  # noqa
        log(f"  figure failed: {e}")
    return res


def plot_pool(a: pd.DataFrame, res: dict, grid: np.ndarray, path: str, pool: str, args) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    w = f"{args.days}d"
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.8))
    col = {"pre": "#2a78d6", "post": "#eb6834"}
    c = a[(a["trigger"] == "cex") & (a["tau_ms"] <= args.max_tau * 1000) & (np.abs(a["days_from_fork"]) <= args.days)]
    bins = np.logspace(np.log10(20), np.log10(args.max_tau * 1000), 60)
    for name in ("pre", "post"):
        x = c[c["regime"] == name]["tau_ms"].to_numpy(np.float64)
        if len(x):
            ax[0].hist(np.maximum(x, 20), bins=bins, density=True, histtype="step", color=col[name], lw=1.4,
                       label=f"{name}: Δt = {res['dt_ms'][name] / 1000:.2f} s, n = {len(x):,}")
            ax[0].axvline(res["dt_ms"][name], color=col[name], ls=":", lw=0.9)
    ax[0].set_xscale("log"); ax[0].set_xlabel("response time τ = t_block − t_open (ms, log scale)"); ax[0].set_ylabel("density")
    ax[0].set_title(f"{pool}: CEX-triggered arbs", fontsize=9, loc="left"); ax[0].legend(fontsize=7, frameon=False)
    kk = np.arange(1, 8)
    for i, name in enumerate(("pre", "post")):
        k = c[c["regime"] == name]["k_blocks"].to_numpy()
        if len(k):
            ax[1].bar(kk + (i - 0.5) * 0.4, [(k == j).mean() if j < 7 else (k >= 7).mean() for j in kk], width=0.4, color=col[name], label=name)
    ax[1].set_xticks(kk); ax[1].set_xticklabels([str(j) for j in kk[:-1]] + ["7+"]); ax[1].set_xlabel("blocks from opening to the arb (k)")
    ax[1].set_ylabel("share"); ax[1].set_title("blocks skipped", fontsize=9, loc="left"); ax[1].legend(fontsize=7, frameon=False)
    tb = pd.read_csv(os.path.join(os.path.dirname(path), "turnbull.csv"))
    for name in ("pre", "post"):
        m = tb[f"mass_{name}"].to_numpy()
        if np.isfinite(m).any():
            ax[2].plot(tb["grid_ms"] / 1000, np.cumsum(m), color=col[name], lw=1.4, label=f"{name} (CEX trigger)")
        o = res["windows"][w][name].get("onchain")
        if o:
            js = np.array([1, 2, 3, 4]); ax[2].plot(js * o["dt_ms"] / 1000, [o["cdf_ell_at_j_dt"][str(j)] for j in js], "s", color=col[name], ms=4,
                                                   mfc="none", label=f"{name}: P(k ≤ j) after on-chain triggers")
    ax[2].set_xlim(0, min(args.grid_max, 5)); ax[2].set_ylim(0, 1); ax[2].set_xlabel("latency ℓ (s)"); ax[2].set_ylabel("CDF (Turnbull NPMLE)")
    ax[2].set_title("interval-censored latency distribution", fontsize=9, loc="left"); ax[2].legend(fontsize=7, frameon=False)
    for x in ax:
        x.grid(color="#e6e6e3", lw=0.6)
        for s in ("top", "right"):
            x.spines[s].set_visible(False)
    fig.tight_layout(); fig.savefig(path, dpi=160); plt.close(fig)


# ---------------------------------------------------------------- fork-level tables
def fmt(v, d=0):
    return "" if v is None or (isinstance(v, float) and not np.isfinite(v)) else (f"{v:,.{d}f}" if isinstance(v, (int, float, np.floating)) else str(v))


def write_tables(results: dict, fork: str, out: str, args) -> str:
    w = f"{args.days}d"
    L = [f"# Arbitrageur response times — {fork} (±{args.days} d, tick reference, strict + non-strict arbs; CEX-triggered openings unless noted)\n"]
    L.append("## T1. Response time τ = block time − opening time (CEX-triggered arbs, τ ≤ %d s)\n" % args.max_tau)
    L.append("| pool | regime | Δt (s) | n | p10 (ms) | p25 | p50 | mean | E[√τ] (√s) | share τ<Δt | P(k=1) | P(k=2) | mean k | share τ<100 ms |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for pool, r in results.items():
        for name in ("pre", "post"):
            R = r["windows"][w][name]
            if "tau_ms" not in R:
                L.append(f"| {pool} | {name} | {R['dt_ms'] / 1000:.2f} | {R.get('n_cex', 0)} | | | | | | | | | | |"); continue
            t = R["tau_ms"]; k = R["k_blocks"]
            L.append(f"| {pool} | {name} | {R['dt_ms'] / 1000:.2f} | {R['n_cex']:,} | {t['p10']:.0f} | {t['p25']:.0f} | {t['p50']:.0f} | {t['mean']:.0f} | {t['mean_sqrt_s']:.3f} | "
                     f"{t['share_lt_dt']:.2f} | {k['p_k1']:.2f} | {k['p_k2']:.2f} | {k['mean']:.2f} | {t['share_lt_100ms']:.3f} |")
    L.append("\n## T2. Latency ℓ: quantile intercepts Q_q(τ) − q·Δt, Turnbull NPMLE and log-normal MLE from the intervals (t_{b−1} − t_open, t_b − t_open]\n")
    L.append("| pool | regime | ℓ̂ q10 (ms) | ℓ̂ q25 | ℓ̂ q50 | Turnbull p25 | median | p75 | mean | P(ℓ ≤ Δt) | lognormal median | mean | on-chain triggers: P(ℓ ≤ Δt) | P(ℓ ≤ 2Δt) | P(ℓ ≤ 3Δt) | n on-chain |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for pool, r in results.items():
        for name in ("pre", "post"):
            R = r["windows"][w][name]
            if "ell_quantile_ms" not in R:
                continue
            e, t, ln = R["ell_quantile_ms"], R["turnbull_ms"], R["lognormal_ms"]; o = R.get("onchain", {})
            L.append(f"| {pool} | {name} | {e['q10']:.0f} | {e['q25']:.0f} | {e['q50']:.0f} | {t['p25']:.0f} | {t['median']:.0f} | {t['p75']:.0f} | {t['mean']:.0f} | {t['p_le_dt']:.2f} | "
                     f"{ln['median']:.0f} | {ln['mean']:.0f} | {fmt(o.get('cdf_ell_at_j_dt', {}).get('1'), 2)} | {fmt(o.get('cdf_ell_at_j_dt', {}).get('2'), 2)} | "
                     f"{fmt(o.get('cdf_ell_at_j_dt', {}).get('3'), 2)} | {R.get('n_onchain', 0):,} |")
    L.append("\n## T3. Fork effects implied by the response times vs the √Δt law (log points)\n")
    L.append("| pool | √Δt law ½ln(Δt₁/Δt₀) | implied log(E√τ₁/E√τ₀) | fixed-latency counterfactual | latency-change component | ℓ (paper convention, s) | Δ median τ (ms) | mechanical Δt/2 | Δ p10 τ | mechanical 0.1Δt | P(k=1) post actual / counterfactual | on-chain implied | Δlog overshoot (cex) | Δlog move | Δlog jump |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for pool, r in results.items():
        e = r["windows"][w]["effects"]
        if "implied_from_tau" not in e:
            L.append(f"| {pool} | {e['sqrt_law']:+.3f} | | | | | | | | | | | | | |"); continue
        L.append(f"| {pool} | {e['sqrt_law']:+.3f} | {e['implied_from_tau']:+.3f} | {e['counterfactual_fixed_latency']:+.3f} | {e['latency_change_component']:+.3f} | {e['ell_paper_equiv_s']:.2f} | "
                 f"{e['d_median_tau_ms']:+.0f} | {e['mechanical_d_median_ms']:+.0f} | {e['d_p10_tau_ms']:+.0f} | {e['mechanical_d_p10_ms']:+.0f} | {e['p_k1_post_actual']:.2f} / {e['p_k1_post_counterfactual']:.2f} | "
                 f"{fmt(e.get('implied_from_tau_onchain'), 3)} | {e['d_log_overshoot_cex']:+.3f} | {e['d_log_move_cex']:+.3f} | {e['d_log_jump_cex']:+.3f} |")
    L.append("\n## T4. Opening types and overshoot decomposition (bp; overshoot = |dev_pre| − γ)\n")
    L.append("| pool | regime | n arbs | cex | onchain | continuation | same_block | long | overshoot: cex | jump at crossing | move during τ | share jump > ½ overshoot | overshoot: same_block | continuation | onchain |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for pool, r in results.items():
        for name in ("pre", "post"):
            R = r["windows"][w][name]
            if "trigger_share" not in R:
                continue
            s = R["trigger_share"]; d = R.get("decomposition_bps", {})
            L.append(f"| {pool} | {name} | {R['n_arb']:,} | {s.get('cex', 0):.2f} | {s.get('onchain', 0):.2f} | {s.get('continuation', 0):.2f} | {s.get('same_block', 0):.2f} | {s.get('long', 0):.2f} | "
                     f"{fmt(d.get('overshoot'), 2)} | {fmt(d.get('jump'), 2)} | {fmt(d.get('move'), 2)} | {fmt(d.get('share_jump_gt_half'), 2)} | "
                     f"{fmt(R.get('overshoot_bps_mean_same_block'), 2)} | {fmt(R.get('overshoot_bps_mean_continuation'), 2)} | {fmt(R.get('overshoot_bps_mean_onchain'), 2)} |")
    L.append("\n## T5. Sensitivity: opening defined by a wider band (1.5γ, 2γ; arbs with |dev_pre| above it) and sharp openings (crossing tick ≥ ½γ beyond the edge)\n")
    L.append("| pool | regime | opening | n | p10 (ms) | p50 | mean | ℓ̂ q10 | ℓ̂ q50 | P(k=1) |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for pool, r in results.items():
        for name in ("pre", "post"):
            R = r["windows"][w][name]
            for m in (1.5, 2.0):
                t = R.get(f"tau_ms_band{m}")
                if t:
                    L.append(f"| {pool} | {name} | {m}γ band | {t['n']:,} | {t['p10']:.0f} | {t['p50']:.0f} | {t['mean']:.0f} | {t['ell_q10_ms']:.0f} | {t['ell_q50_ms']:.0f} | |")
            t = R.get("tau_ms_sharp")
            if t:
                L.append(f"| {pool} | {name} | sharp (jump ≥ ½γ) | {t['n']:,} | {t['p10']:.0f} | {t['p50']:.0f} | {t['mean']:.0f} | {t['ell_q10_ms']:.0f} | {t['ell_q50_ms']:.0f} | {t['p_k1']:.2f} |")
    L.append("\n## T6. Arbitrageur addresses (sender contracts; strict arbs)\n")
    L.append("| pool | regime | senders | active (≥%d arbs) | bots (arb share ≥ 0.5) | bots' share of arbs | HHI (count) | HHI (volume) | top-1 | top-3 | top-5 | senders for 90%% |" % args.min_arbs)
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for pool, r in results.items():
        for name in ("pre", "post"):
            A = r["windows"][w][name].get("addresses", {})
            if not A:
                continue
            L.append(f"| {pool} | {name} | {A['n_senders']:,} | {A['n_active_ge_min']} | {A['n_bots']} | {A['bots_share_of_arbs']:.2f} | {A['hhi_count']:.3f} | {A['hhi_volume']:.3f} | "
                     f"{A['top1_share']:.2f} | {A['top3_share']:.2f} | {A['top5_share']:.2f} | {A['n_senders_90pct']} |")
    L.append("\n## T7. Entry, exit and adaptation at the fork (senders with ≥%d strict arbs; paired: ≥%d CEX-triggered arbs in both regimes)\n" % (args.min_arbs, args.min_pair))
    L.append("| pool | stayers | entrants | exits | entrants' share of post arbs | paired senders | median Δp10 τ (ms) | mechanical | median Δp50 τ | mechanical | share faster than mechanical (p10) |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for pool, r in results.items():
        e = r["windows"][w]["effects"]
        if "entrants" not in e:
            continue
        n_, p_ = e["entrants"], e["paired_senders"]
        L.append(f"| {pool} | {n_['n_stayers']} | {n_['n_entrants']} | {n_['n_exits']} | {fmt(n_['entrants_share_of_post_arbs'], 2)} | {p_['n']} | {fmt(p_['median_d_p10_ms'], 0)} | "
                 f"{fmt(e.get('mechanical_d_p10_ms'), 0)} | {fmt(p_['median_d_p50_ms'], 0)} | {fmt(e.get('mechanical_d_median_ms'), 0)} | {fmt(p_['share_faster_than_mechanical_p10'], 2)} |")
    L.append("\n## T8. Top senders (per pool and regime: see <pool>/top_senders_{pre,post}.csv; first three shown)\n")
    L.append("| pool | regime | sender | strict arbs | share | arb share of own swaps | τ p10 (ms) | τ p50 | P(k=1) | overshoot (bp) | same-block share |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for pool in results:
        for name in ("pre", "post"):
            p = os.path.join(out, pool, f"top_senders_{name}.csv")
            if os.path.exists(p):
                t = pd.read_csv(p)
                for _, x in t.head(3).iterrows():
                    L.append(f"| {pool} | {name} | {x['sender']} | {x['n_arb_strict']:,} | {x['share']:.2f} | {x['arb_share_of_own_swaps']:.2f} | {fmt(x['tau_p10_ms'], 0)} | {fmt(x['tau_p50_ms'], 0)} | "
                             f"{fmt(x['p_k1'], 2)} | {x['overshoot_bps']:.2f} | {x['share_same_block']:.2f} |")
    txt = "\n".join(L) + "\n"
    open(os.path.join(out, "tables.md"), "w").write(txt)
    return txt


def plot_quantiles(results: dict, out: str, args) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    w = f"{args.days}d"
    pools = [p for p in results if "tau_ms" in results[p]["windows"][w]["pre"] and "tau_ms" in results[p]["windows"][w]["post"]]
    if not pools:
        return
    fig, axes = plt.subplots(1, len(pools), figsize=(max(3.2 * len(pools), 7.5), 3.6), squeeze=False)
    col = {"pre": "#2a78d6", "post": "#eb6834"}
    for ax, pool in zip(axes[0], pools):
        for name in ("pre", "post"):
            R = results[pool]["windows"][w][name]; t = R["tau_ms"]; dt = R["dt_ms"]
            qs = np.array(QS); v = np.array([t[f"p{int(q * 100)}"] for q in qs])
            ax.plot(qs * dt, v, "o-", color=col[name], ms=3.5, lw=1.2, label=f"{name} (Δt {dt / 1000:.2f} s)")
        lim = max(results[pool]["windows"][w]["pre"]["dt_ms"], 1) * 0.95
        ax.plot([0, lim], [0, lim], color="#999", lw=0.8, ls="--", label="slope 1 (ℓ = 0)")
        ax.set_xlabel("q · Δt (ms)"); ax.set_ylabel("Q_q(τ) (ms)"); ax.set_title(pool, fontsize=9, loc="left"); ax.legend(fontsize=6.5, frameon=False)
        ax.grid(color="#e6e6e3", lw=0.6)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    fig.suptitle("Response-time quantiles Q_q(τ) against q·Δt — one line with intercept ℓ ⇔ fixed latency", fontsize=9)
    fig.tight_layout(); fig.savefig(os.path.join(out, "fig_quantiles.png"), dpi=160); plt.close(fig)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="pipeline output folder (e.g. full_fermi)")
    ap.add_argument("--fork", required=True, choices=list(C.FORKS))
    ap.add_argument("--subdir", default="results_agg", help="results folder with the tick reference (results_agg or results_agg_lag<N>)")
    ap.add_argument("--pools", nargs="+", default=["all"])
    ap.add_argument("--days", type=int, default=30, help="window ±days around the fork (statistics also for ±14 d)")
    ap.add_argument("--max-tau", type=int, default=60, help="responses longer than this (s) are excluded from the distributions")
    ap.add_argument("--max-search", type=int, default=120, help="seconds before the block searched for the band crossing")
    ap.add_argument("--min-arbs", type=int, default=20, help="strict arbs for a sender to count as active")
    ap.add_argument("--min-pair", type=int, default=50, help="CEX-triggered arbs in BOTH regimes for the paired sender table")
    ap.add_argument("--grid-step", type=float, default=10.0, help="Turnbull grid step (ms)")
    ap.add_argument("--grid-max", type=float, default=10.0, help="Turnbull grid maximum (s)")
    ap.add_argument("--sample", type=int, default=100_000, help="arbs per pool in the upload sample")
    ap.add_argument("--reuse", action="store_true", help="skip the opening search: reload arb_response/<pool>/arbs.parquet of an earlier run")
    ap.add_argument("--exclude-senders", default=None, help="CSV of sender contracts to drop (e.g. public_contracts_<fork>.csv: public routers)")
    ap.add_argument("--tag", default=None, help="output folder suffix arb_response_<tag> (default 'bots' when --exclude-senders is given)")
    args = ap.parse_args()
    if args.exclude_senders and args.tag is None:
        args.tag = "bots"
    S = load_summary(args.out, args.subdir)
    if S.get("reference") != "aggtrades":
        raise SystemExit("the response-time analysis needs the tick reference: run run_pilot.py --reference aggtrades")
    fork = args.fork; fork_block = int(S["fork_block"]); b0, b1 = map(int, S["blocks"])
    mts = block_timestamps(args.out, fork, b0, b1)
    fork_ms = int(mts[fork_block - b0])
    base = os.path.join(args.out, "arb_response" + ("" if args.subdir == "results_agg" else args.subdir[len("results_agg"):]))
    out = base + (f"_{args.tag}" if args.tag else "")
    os.makedirs(out, exist_ok=True)
    excluded = load_excluded_senders(args.exclude_senders) if args.exclude_senders else set()
    if excluded:
        log(f"excluding {len(excluded)} sender contracts listed in {args.exclude_senders}")
    pools = [p for p in C.PILOT_POOLS if p["binance"] and (args.pools == ["all"] or p["name"] in args.pools)]
    results = {}
    for p in pools:
        path = os.path.join(args.out, args.subdir, p["name"], "swaps_enriched.parquet")
        if not os.path.exists(path):
            log(f"{p['name']}: {path} missing, skipped"); continue
        sym = p["binance"] if isinstance(p["binance"], list) else [p["binance"]]
        dirs = [os.path.join(args.out, "binance_agg", s) for s in sym]
        if not all(os.path.isdir(d) for d in dirs):
            log(f"{p['name']}: tick data {dirs} missing, skipped"); continue
        t0 = time.time()
        if args.reuse:
            fa = os.path.join(base, p["name"], "arbs.parquet")
            if not os.path.exists(fa):
                log(f"{p['name']}: {fa} missing (run without --reuse first), skipped"); continue
            a = pd.read_parquet(fa)
            n_by_sender = count_swaps_by_sender(path, fork_block)
        else:
            a, n_by_sender = stream_arbs(path, fork_block)
        if excluded:
            drop = a["sender"].astype(str).str.lower().isin(excluded).to_numpy()
            log(f"{p['name']}: dropping {int(drop.sum()):,} of {len(a):,} arbs sent through excluded contracts "
                f"({int((drop & a['is_arb_strict'].to_numpy()).sum()):,} strict)")
            a = a[~drop].reset_index(drop=True)
            if a["sender"].dtype.name == "category":
                a["sender"] = a["sender"].cat.remove_unused_categories()
        if len(a) < 100:
            log(f"{p['name']}: only {len(a)} arbs, skipped"); continue
        try:
            results[p["name"]] = run_pool(a, n_by_sender, dirs, mts, b0, fork_block, fork_ms, args, os.path.join(out, p["name"]), p["name"], precomputed=args.reuse)
            e = results[p["name"]]["windows"][f"{args.days}d"]["effects"]
            log(f"{p['name']}: done in {time.time() - t0:.0f}s; implied fork effect from τ {e.get('implied_from_tau', float('nan')):+.3f} "
                f"(√Δt law {e['sqrt_law']:+.3f}); ℓ paper-equivalent {e.get('ell_paper_equiv_s', float('nan')):.2f} s")
        except Exception as ex:  # noqa
            import traceback; traceback.print_exc()
            log(f"{p['name']}: FAILED ({str(ex)[:200]})")
        del a
    if not results:
        raise SystemExit("no pool produced results")
    txt = write_tables(results, fork, out, args)
    print(txt)
    try:
        plot_quantiles(results, out, args)
    except Exception as e:  # noqa
        log(f"quantile figure failed: {e}")
    json.dump({"fork": fork, "fork_block": fork_block, "blocks": [b0, b1], "args": vars(args), "pools": results},
              open(os.path.join(out, "summary.json"), "w"), indent=1, default=float)
    # upload bundle: everything except the full per-arb tables (replaced by a random sample)
    zpath = os.path.join(args.out, f"arb_response_{args.tag + '_' if args.tag else ''}{fork}.zip")
    rng = np.random.default_rng(0)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in glob.glob(os.path.join(out, "**", "*"), recursive=True):
            if os.path.isdir(f) or f.endswith("arbs.parquet"):
                continue
            z.write(f, os.path.relpath(f, args.out))
        for pool in results:
            f = os.path.join(out, pool, "arbs.parquet")
            d = pd.read_parquet(f)
            if len(d) > args.sample:
                d = d.iloc[np.sort(rng.choice(len(d), args.sample, replace=False))]
            sp = os.path.join(out, pool, "arbs_sample.parquet")
            d.to_parquet(sp, index=False); z.write(sp, os.path.relpath(sp, args.out))
    log(f"done -> {zpath}")


if __name__ == "__main__":
    main()
