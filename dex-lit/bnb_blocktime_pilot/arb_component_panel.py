"""Hourly panels of the overshoot COMPONENTS from the full per-arb tables (arb_response/<pool>/arbs.parquet), and the
fork-effect regressions of each component with the paper's specification.

For every strict arb the overshoot |dev_pre| − γ is split by how the opportunity opened (arb_response.py):
  CEX-triggered: jump at the crossing tick + CEX move during the response time τ;  continuation;  same block;  on-chain.
Per pool and hour the script records the share of each type, the mean overshoot of each type and the jump/move parts,
joins the pipeline's hourly panel (σ, liquidity, volume, hour of day, post, t_days from analysis_agg/hourly_panel.parquet)
and runs, for ±14 d and ±30 d:   log(y) ~ post + log σ + log L + log volume + hour-of-day FE,  SE clustered by day,
for y ∈ {all strict arbs, CEX overshoot, CEX jump, CEX move, continuation, same block} and the linear share equations.

    python arb_component_panel.py --out full_fermi --fork Fermi          # -> full_fermi/arb_response/component_panels/, arb_component_Fermi.zip
    python arb_component_panel.py --out full_fermi --fork Fermi --tag bots   # same on arb_response_bots/ (routers excluded) -> arb_component_bots_Fermi.zip
Needs: arb_response.py already run (arbs.parquet per pool) and full_analysis.py on results_agg (analysis_agg/hourly_panel.parquet).
"""
from __future__ import annotations
import argparse, glob, json, os, sys, time, zipfile
import numpy as np, pandas as pd
import config as CFG

HOUR_MS = 3_600_000
TYPES = ("cex", "continuation", "same_block", "onchain", "long")


def log(m):
    print(time.strftime("%H:%M:%S"), m, file=sys.stderr, flush=True)


def hourly_components(a: pd.DataFrame) -> pd.DataFrame:
    """a: strict arbs of one pool with columns ts_ms, trigger, overshoot_bps, jump_bps, move_bps, tau_ms, k_blocks, volume_q, arb_loss."""
    a = a.copy(); a["hour_ms"] = (a["ts_ms"] // HOUR_MS) * HOUR_MS
    g = a.groupby("hour_ms")
    out = pd.DataFrame({"n": g.size(), "overshoot_all": g["overshoot_bps"].mean(), "arb_loss_sum": g["arb_loss"].sum(), "arb_volume": g["volume_q"].sum()})
    for t in TYPES:
        x = a[a["trigger"] == t]; gx = x.groupby("hour_ms")
        out[f"{t}"] = gx["overshoot_bps"].mean(); out[f"{t}_n"] = gx.size()
        out[f"share_{t}"] = (out[f"{t}_n"].fillna(0) / out["n"])
    cex = a[a["trigger"] == "cex"]; gc = cex.groupby("hour_ms")
    out["cex_jump"] = gc["jump_bps"].mean(); out["cex_move"] = gc["move_bps"].mean(); out["cex_jump_n"] = gc.size(); out["cex_move_n"] = gc.size()
    c2 = cex[cex["tau_ms"] <= 60_000]; g2 = c2.groupby("hour_ms")
    out["cex_tau_mean_ms"] = g2["tau_ms"].mean(); out["cex_tau_median_ms"] = g2["tau_ms"].median()
    out["cex_sqrt_tau_mean"] = g2["tau_ms"].apply(lambda s: float(np.sqrt(s / 1000).mean())); out["cex_p_k1"] = g2["k_blocks"].apply(lambda s: float((s == 1).mean()))
    return out.reset_index()


def weights(a: pd.DataFrame, days: int) -> dict:
    """Pre-fork weights of each component in the mean strict overshoot (±days)."""
    d = a[(a["regime"] == "pre") & (a["days_from_fork"].abs() <= days)]
    n = len(d); tot = d["overshoot_bps"].mean()
    w = {"n": int(n), "mean_overshoot_bps": float(tot)}
    cex = d[d["trigger"] == "cex"]
    w["w_cex_jump"] = float(cex["jump_bps"].sum() / n / tot); w["w_cex_move"] = float(cex["move_bps"].sum() / n / tot)
    for t in TYPES[1:]:
        w[f"w_{t}"] = float(d[d["trigger"] == t]["overshoot_bps"].sum() / n / tot)
    for t in TYPES:
        w[f"share_{t}"] = float((d["trigger"] == t).mean()); w[f"mean_{t}"] = float(d[d["trigger"] == t]["overshoot_bps"].mean()) if (d["trigger"] == t).any() else np.nan
    w["mean_cex_jump"] = float(cex["jump_bps"].mean()); w["mean_cex_move"] = float(cex["move_bps"].mean())
    return w


def beta(panel: pd.DataFrame, y: str, days: int, min_n: int = 5, controls: str = "np.log(sigma_ps) + np.log(liq_mean) + np.log(volume)"):
    import statsmodels.formula.api as smf
    d = panel[(panel["t_days"].abs() <= days) & panel[y].notna() & (panel[y] > 0) & (panel["sigma_ps"] > 0) & (panel["volume"] > 0) & (panel["liq_mean"] > 0)]
    if y + "_n" in d:
        d = d[d[y + "_n"] >= min_n]
    if len(d) < 60 or d["post"].nunique() < 2:
        return np.nan, np.nan, int(len(d))
    m = smf.ols(f"np.log({y}) ~ post + {controls} + C(hod)", data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"]})
    return float(m.params["post"]), float(m.bse["post"]), int(len(d))


def share_beta(panel: pd.DataFrame, y: str, days: int, min_n: int = 5):
    import statsmodels.formula.api as smf
    d = panel[(panel["t_days"].abs() <= days) & (panel["n"] >= min_n) & (panel["sigma_ps"] > 0)]
    if len(d) < 60 or d["post"].nunique() < 2:
        return np.nan, np.nan, int(len(d))
    m = smf.ols(f"{y} ~ post + np.log(sigma_ps) + C(hod)", data=d).fit(cov_type="cluster", cov_kwds={"groups": d["day"]})
    return float(m.params["post"]), float(m.bse["post"]), int(len(d))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--fork", required=True, choices=list(CFG.FORKS))
    ap.add_argument("--subdir", default="results_agg"); ap.add_argument("--pools", nargs="+", default=["all"])
    ap.add_argument("--analysis-dir", default=None, help="folder with hourly_panel.parquet (default analysis<tag>)")
    ap.add_argument("--tag", default=None, help="read arb_response_<tag>/ (e.g. 'bots' from arb_response.py --exclude-senders) and write arb_component_<tag>_<fork>.zip")
    a = ap.parse_args()
    tag = a.subdir[len("results"):]
    adir = a.analysis_dir or os.path.join(a.out, "analysis" + tag)
    ppath = os.path.join(adir, "hourly_panel.parquet")
    if not os.path.exists(ppath):
        raise SystemExit(f"{ppath} not found: run full_analysis.py --results {a.out} --subdir {a.subdir} first")
    H = pd.read_parquet(ppath)
    H["hour_ms"] = (pd.to_datetime(H["hour"], utc=True).astype("datetime64[ns, UTC]").astype("int64") // 10 ** 6).astype("int64")
    rdir = os.path.join(a.out, "arb_response" + ("" if a.subdir == "results_agg" else tag) + (f"_{a.tag}" if a.tag else ""))
    odir = os.path.join(rdir, "component_panels"); os.makedirs(odir, exist_ok=True)
    pools = [p["name"] for p in CFG.PILOT_POOLS if a.pools == ["all"] or p["name"] in a.pools]
    cols = ["ts_ms", "trigger", "is_arb_strict", "overshoot_bps", "jump_bps", "move_bps", "tau_ms", "k_blocks", "volume_q", "arb_loss", "regime", "days_from_fork"]
    rows, W, R = [], {}, {}
    for pool in pools:
        f = os.path.join(rdir, pool, "arbs.parquet")
        if not os.path.exists(f):
            log(f"{pool}: no arbs.parquet, skipped"); continue
        t0 = time.time()
        d = pd.read_parquet(f, columns=cols)
        d = d[d["is_arb_strict"]].copy()
        d["trigger"] = d["trigger"].astype(str)
        if len(d) < 200:
            log(f"{pool}: only {len(d)} strict arbs, skipped"); continue
        pan = hourly_components(d)
        h = H[H["pool"] == pool][["hour_ms", "sigma_ps", "liq_mean", "volume", "hod", "day", "post", "t_days"]]
        pan = pan.merge(h, on="hour_ms", how="inner")
        pan.to_csv(os.path.join(odir, f"{pool}.csv"), index=False)
        W[pool] = {"14d": weights(d, 14), "30d": weights(d, 30), "n_strict": int(len(d))}
        R[pool] = {}
        for days in (14, 30):
            r = {"fork": a.fork, "pool": pool, "window": f"±{days} d"}
            for y, lab in (("overshoot_all", "all strict arbs"), ("cex", "CEX-triggered"), ("cex_jump", "CEX: jump"), ("cex_move", "CEX: move"),
                           ("continuation", "continuation"), ("same_block", "same block"), ("onchain", "on-chain")):
                b, s, n = beta(pan, y, days)
                R[pool][f"{days}|{y}"] = [b, s, n]; r[lab] = f"{b:+.3f} ({s:.3f}) [{n}]" if np.isfinite(b) else ""
            for y, lab in (("share_cex", "Δ share CEX"), ("share_same_block", "Δ share same-block"), ("share_continuation", "Δ share continuation")):
                b, s, n = share_beta(pan, y, days)
                R[pool][f"{days}|{y}"] = [b, s, n]; r[lab] = f"{b:+.3f} ({s:.3f})" if np.isfinite(b) else ""
            rows.append(r)
        log(f"{pool}: {len(d):,} strict arbs, {len(pan):,} hours, done in {time.time() - t0:.0f}s")
    if not rows:
        raise SystemExit("nothing produced")
    T = pd.DataFrame(rows)
    md = f"# Component regressions — {a.fork} (full per-arb tables; log(y) ~ post + log σ + log L + log volume + hour FE, day-clustered SE; [hours])\n\n" + T.to_markdown(index=False)
    open(os.path.join(odir, "component_regressions.md"), "w").write(md); print(md)
    json.dump({"fork": a.fork, "weights": W, "regressions": R}, open(os.path.join(odir, "component_summary.json"), "w"), indent=1, default=float)
    zpath = os.path.join(a.out, f"arb_component_{a.tag + '_' if a.tag else ''}{a.fork}.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in glob.glob(os.path.join(odir, "*")):
            z.write(f, os.path.relpath(f, a.out))
    log(f"done -> {zpath}")


if __name__ == "__main__":
    main()
