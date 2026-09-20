#!/usr/bin/env python3
"""recheck_untraced.py — recompute the handful of manuscript numbers that the fact-check could not trace to a
table or an output file, and write recheck_untraced.md next to this script.

  1. weekly signing-wallet counts of the 0x7cda… contract around Fermi (Section 6.9: "58–156 a week (189 in all)")
  2. Table D9: share of core-pool arbitrages attributed to the top operators, with and without router flow
  3. the conversion between the fitted latency ℓ (overshoot ∝ σ√(Δt+ℓ)) and the response-time latency ℓ_t
     (Section 7.2: "about 2.2–2.4·ℓ_t", "0.59 s ↔ ℓ_t ≈ 0.25 s (0.11–0.52 s)")
  4. fake-fork placebos at lag 0 versus lag 250 (Section 6.8: "the placebo results are unchanged …")
  5. the simulation validation numbers of Appendix D (re-run simulate_response_test.py with seed 3 and --post-scale 0.5)
"""
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")))

import glob
import os
import re
import subprocess
import sys

import numpy as np
import pandas as pd
from scipy.optimize import brentq

sys.path.insert(0, ROOT + "/dex-lit/bnb_blocktime_pilot")
from arb_operators import build_operators  # noqa: E402

OPS = ROOT + "/arb_resp/ops"
CORE = ["WBNB-USDT-500", "ETH-USDT-500", "BTCB-USDT-500"]
out = ["# Recheck of the numbers that were not traceable to an output file\n"]

# ---------------------------------------------------------------- 1. weekly wallets of 0x7cda… (core pools)
fs = [f for f in glob.glob(f"{OPS}/Fermi/arb_response/operators/*_arbs_tx.parquet") if "-500_" in f]
df = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
d = df[df["sender"] == "0x7cda585e917fecb3a33c6d5a8f8a15dd956694dc"].copy()
fork = pd.Timestamp("2026-01-14 02:30:00")
d["week"] = ((pd.to_datetime(d["ts_ms"], unit="ms") - fork).dt.total_seconds() // (7 * 86400)).astype(int)
wk = d.groupby("week")["tx_from"].nunique()
reg = d.groupby("regime")["tx_from"].nunique()
out.append("## 1. Weekly distinct signing wallets of 0x7cda…94dc, three core pools, Fermi ±5 weeks\n")
out.append(", ".join(f"week {k:+d}: {v}" for k, v in wk.items()))
out.append(f"\n\nDistinct wallets: pre {reg.get('pre')}, post {reg.get('post')}. Post-fork weeks range {wk[wk.index >= 0].min()}–{wk[wk.index >= 0].max()}.\n")

# ---------------------------------------------------------------- 2. Table D9 shares with / without router flow
tops = ["c:0x32564234df89", "c:0xaf30736465de", "c:0x802b65b5d901", "c:0xba53da030f35", "c:0x6777c00839fe"]
rows = []
for fk in ["Lorentz", "Maxwell", "Fermi"]:
    A = pd.concat([pd.read_parquet(f).assign(pool=os.path.basename(f).replace("_arbs_tx.parquet", ""))
                   for f in sorted(glob.glob(f"{OPS}/{fk}/arb_response/operators/*_arbs_tx.parquet"))], ignore_index=True)
    A["sender"] = A["sender"].astype(str)
    A, C, ops = build_operators(A, 30, 2, 20)
    A = A[A["days_from_fork"].abs() <= 30]
    for rg in ("pre", "post"):
        x = A[(A["regime"] == rg) & A["pool"].isin(CORE) & (A["operator"] != "anon")]
        xb = x[~x["via_public"]]
        vc, vb = x["operator"].value_counts(), xb["operator"].value_counts()
        for op in tops:
            m = [o for o in vc.index if o.startswith(op)]
            if m:
                o = m[0]
                rows.append({"regime": f"{fk} {rg}", "operator": op[2:14] + "…", "share, operators incl. attributed router flow": vc[o] / vc.sum(),
                             "share, bot flow only": vb.get(o, 0) / vb.sum()})
T = pd.DataFrame(rows)
T["difference"] = T.iloc[:, 2] - T.iloc[:, 3]
out.append("## 2. Table D9 shares: operators including attributed router flow versus bot flow only\n")
out.append(T.to_markdown(index=False, floatfmt=".3f"))
out.append(f"\n\nMax |difference| = {T['difference'].abs().max():.3f}; outside the Lorentz post regime max = "
           f"{T[T['regime'] != 'Lorentz post']['difference'].abs().max():.3f}.\n")

# ---------------------------------------------------------------- 3. ℓ (fit convention) versus ℓ_t (response time)
def esqrt(lt, dt, n=20001):
    u = np.linspace(0, dt, n)
    return np.sqrt(lt + u).mean()


def paper_l(lt, dt0, dt1):
    target = np.log(esqrt(lt, dt1) / esqrt(lt, dt0))
    return brentq(lambda l: 0.5 * np.log((dt1 + l) / (dt0 + l)) - target, 1e-6, 50)


forks = {"Lorentz": (3.0, 1.5), "Maxwell": (1.5, 0.75), "Fermi": (0.75, 0.45)}
out.append("## 3. Fitted ℓ implied by a response-time latency ℓ_t (τ = ℓ_t + U(0, Δt); ℓ solves ½ln((Δt₁+ℓ)/(Δt₀+ℓ)) = ln(E√τ₁/E√τ₀))\n")
out.append("| ℓ_t (s) | " + " | ".join(f"ℓ {k} (s)" for k in forks) + " | ℓ/ℓ_t |")
out.append("|---|" + "---|" * (len(forks) + 1))
for lt in [0.05, 0.10, 0.20, 0.25, 0.30, 0.40, 0.50, 0.80]:
    ls = [paper_l(lt, *v) for v in forks.values()]
    out.append(f"| {lt:.2f} | " + " | ".join(f"{l:.2f}" for l in ls) + f" | {min(ls)/lt:.2f}–{max(ls)/lt:.2f} |")
inv = {L: [brentq(lambda lt: paper_l(lt, *v) - L, 1e-4, 5) for v in forks.values()] for L in (0.59, 0.27, 1.13, 1.0)}
out.append("\nInverse: " + "; ".join(f"ℓ = {L} s → ℓ_t = {min(v):.2f}–{max(v):.2f} s" for L, v in inv.items()) + "\n")

# ---------------------------------------------------------------- 4. placebos at lag 0 vs lag 250
def parse(path):
    rows = {}
    for l in open(path, encoding="utf-8"):
        if not l.startswith("|") or "---" in l or "窗口" in l:
            continue
        c = [x.strip() for x in l.strip().strip("|").split("|")]
        rows[(c[0], c[2])] = c[3:]
    return rows


out.append("## 4. Fake-fork placebos, lag 0 → lag 250 (overshoot | arbitrageur profit | total LP loss)\n")
out.append("| fork | window | controls | overshoot | profit | LP loss |")
out.append("|---|---|---|---|---|---|")
for fk in ["maxwell", "fermi"]:
    a = parse(ROOT + f"/{fk}_tick/bundle/extra_agg/placebo_core.md")
    b = parse(ROOT + f"/{fk}_lag250/bundle/extra_agg_lag250/placebo_core.md")
    for k, va in a.items():
        vb = b[k]
        out.append(f"| {fk} | {k[0]} | {k[1]} | " + " | ".join(f"{va[c]} → {vb[c]}" for c in (0, 1, 3)) + " |")
out.append("")

# ---------------------------------------------------------------- 5. simulation validation (Appendix D)
scr = os.environ.get("SIM_DIR", "/tmp/claude-0/-home-claude/75858e62-ab6f-53b9-8ae1-5dbf258e45c5/scratchpad/sim")
for name, args in [("sim_response", []), ("sim_half", ["--post-scale", "0.5"])]:
    tab = f"{scr}/{name}/arb_response/tables.md"
    if not os.path.exists(tab):
        os.makedirs(scr, exist_ok=True)
        subprocess.run([sys.executable, ROOT + "/dex-lit/bnb_blocktime_pilot/simulate_response_test.py", "--out", f"{scr}/{name}"] + args,
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t = open(tab, encoding="utf-8").read()
    t2 = re.search(r"## T2.*?\n\n(.*?)\n\n", t, re.S).group(1)
    t3 = re.search(r"## T3.*?\n\n(.*?)\n\n", t, re.S).group(1)
    t4 = re.search(r"## T4.*?\n\n(.*?)\n\n", t, re.S).group(1)
    t7 = re.search(r"## T7.*?\n\n(.*?)\n\n", t, re.S).group(1)
    out.append(f"## 5. Simulation validation — {name} ({' '.join(args) or 'latencies unchanged'}; seed 3)\n")
    out.append("T2 latency estimates:\n\n" + t2 + "\n\nT3 fork effects:\n\n" + t3 + "\n\nT4 decomposition (jump / move):\n\n" + t4 + "\n\nT7 paired senders:\n\n" + t7 + "\n")

open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "recheck_untraced.md"), "w", encoding="utf-8").write("\n".join(out))
print("written recheck_untraced.md")
