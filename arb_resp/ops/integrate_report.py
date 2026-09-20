import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..")))

import re
p = ROOT + "/arb_resp/ops/section5_operators.md"; s = open(p).read()
rep = [('''（样本对全样本的复现误差约 ±5 ms；只用严格套利的表 R1 给出同方向、略小的变化。）''', '''（样本对全样本"全部"一列的复现误差多在 ±5 ms 内，WBNB 池个别格子差 10–20 ms；只用严格套利的表 R1 给出同方向、幅度较小的变化。）'''),
       ('''| ETH 5 bp | 六个区制 | 变化 +3 至 +94 ms（Lorentz 前 686 → 780，其余 ≤ +28） | ≤ +26 |''', '''| ETH 5 bp | 六个区制 | 变化 +1 至 +94 ms（Lorentz 前 686 → 780，其余 ≤ +28） | ≤ +26 |''')]
for a, b in rep:
    if a in s:
        s = s.replace(a, b)
open(p, "w").write(s)

rp = ROOT + "/arb_resp/全样本报告_地址级响应时间_三次分叉.md"
R = open(rp).read()
i0 = R.index("## 5. 地址层面"); i1 = R.index("## 6. 对论文 v3 的含义与修改建议")
R = R[:i0] + s.rstrip() + "\n\n" + R[i1:]

old = '''表 R1–R8、图 F1–F5 在 `cmp/`；§4 的全样本分解在 `comp/out/`（表 C1–C5、图 F5）。'''
new = '''表 R1–R8、图 F1–F5 在 `cmp/`；§4 的全样本分解在 `comp/out/`（表 C1–C5、图 F5）；§5 的运营者归并用 `fetch_tx_from.py`（v2.14.3）取回的 `tx.from` 数据与 `arb_operators.py`、`ops_analysis.py`，表 O1–O6 在 `ops/out/`、表 R1–R6（运营者版）在 `ops/out2/`。'''
assert old in R; R = R.replace(old, new)

old = '''对下一次减半的预测不变（−0.09 至 −0.14），但机制表述要改。'''
new = old + '''**运营者归并（`tx.from`）**没有改变地址层面的结论：头部机器人是"一个合约 + 一批固定大小的钱包池"（20 / 41 / 50 / 100–177 个 EOA 轮换签名），合约级与运营者级的集中度几乎相同，进入/退出更少，同一批运营者贯穿三次分叉；Fermi 窗口钱包越多的运营者越快。但它揭示了一个需要修正的问题：WBNB 两个池在 Lorentz/Maxwell 窗口内 20%–50% 的"严格套利"是经公共路由由一次性账户发出的普通订单流，把这两个池的响应时间截距拉低（Lorentz 后 WBNB 5 bp 池 q10 45 → 239 ms），ETH/BTCB 池与 Fermi 窗口不受影响；论文表 18–21 与 §4 的分解将改用剔除路由流量的 bots-only 口径重算（管线 v2.15）。'''
assert old in R; R = R.replace(old, new)

old = '''（措辞待定），避免读者把 0.59 s 当成网络延迟。'''
new = old + '''
7. **§6.9 "Arbitrageurs" 段与附录 E**：加入运营者层面的证据（§5.1–5.5）：合约级集中度在运营者级几乎不变（top-1 相同、HHI +0.00–0.04）；多合约运营者份额 3%–42%；进入者在运营者级只占分叉后套利的 1%–3%（ETH/BTCB）；头部机器人用固定大小的钱包池、Fermi 窗口 ≥30 个 EOA 的合约做了 52%–53% 的机器人套利、钱包数与 ℓ̂ q10 负相关（ρ −0.6）；gas 成本每笔 0.15 → 0.013 USDT、占毛利 3%–13%，抢位置的高价 gas 在减少。附录 E 加一张"合约 vs 运营者"表（表 R6）与一张 gas/位置表（表 R5）。
8. **表 18–21、§4 与图 7 改用 bots-only 口径**（§5.6）：剔除公共路由合约后重算六区制截距、τ 推出的效应、分解回归与地址表；主要变化在 WBNB 两个池的 Lorentz/Maxwell 窗口（q10 截距上调 100–200 ms），ETH/BTCB 与 Fermi 基本不变；§6.9 与附录 E 需说明"严格套利"里有多少是路由流量、如何识别。'''
assert old in R; R = R.replace(old, new)

old = '''是"等偏离变大"而非延迟。'''
new = old + '''
- 公共 / 私有合约的判定（≥30 个 EOA 且中位每账户 ≤2 笔）只用严格套利的交易；v2.14–2.14.2 的 `fetch_tx_from.py` 没有解析出 `sender`，"合约全部 swap"口径的 EOA 表为空（v2.14.3 修正，可离线 `--rebuild-contracts`），但判定只依赖严格套利的 EOA 结构，不受影响。经公共路由但持续活跃（≥20 笔）的账户被当作运营者，其剖面（过冲 0.04–0.27 bp、同区块占比 0.37–0.64）介于机器人与一次性账户之间，可能是小型机器人也可能是持续的交易机器人用户；bots-only 口径把经路由的流量整体剔除，会连带去掉少量直接经 SmartRouter 下单的机器人（Fermi：约 2% 的严格套利，3 个 EOA 占了 SmartRouter 严格套利的 92%）。
- 运营者归并只能合并共用签名钱包的合约；用一次性钱包的操作（每笔换一个 EOA）无法归并，只能作为"匿名流量"报告占比。'''
assert R.count(old) == 1, R.count(old); R = R.replace(old, new)

old = '''1. 把本报告 §2、§4、§5 写进论文 v4：§3.2 改述、新增 §6.9 与表 18–19、图 7（F1）、图 8（F5），摘要/引言/§7 措辞相应修改。
2. 可选：`tx.from`（EOA）关联，把多个合约归并到同一运营者，看集中度是否更高；以及对 same_block back-run 的单独研究（它与 §7.2 的 "MEV supply chain" 讨论直接相关）。'''
new = '''1. （已完成）本报告 §2、§4、§5 已写进论文 v4：§3.2 改述、新增 §4.5、§6.9 与表 18–21、图 7–8、附录 E。
2. （已完成）`tx.from` 归并：见 §5.1–5.5。
3. **bots-only 重算**（v2.15，本地约 10–15 分钟/分叉）：`arb_response.py --reuse --exclude-senders public_contracts_<fork>.csv` 与 `arb_component_panel.py --tag bots`，发回 `arb_response_bots_<Fork>.zip`、`arb_component_bots_<Fork>.zip`；据此更新论文表 18–21、§4.5、§6.9、附录 E 为 v4.1，并把运营者证据（§6 第 7 条）写入。
4. 可选：对 same_block back-run 的单独研究（§5.5 表明它由另一批机器人在做，与 §7.2 的 "MEV supply chain" 讨论直接相关）；用一次性钱包的路由流量能否通过资金来源（首笔转入的地址）归并。'''
assert old in R; R = R.replace(old, new)

old = '''每池原始图 `<Fork>/arb_response/<pool>/fig_<pool>.png` 与 `fig_quantiles.png`；脚本 `compare.py`。'''
new = old + '''运营者层面：`ops/out/O1_concentration.md`（合约 vs 运营者，含匿名与钱包轮换占比）、`O2_entry_exit_paired.md`、`O3_top_operators.md`、`O4_gas_position.md`、`O5_operator_trajectories.md`、`O6_wallet_rotation.md`、`contracts_<Fork>.csv`、`operators_<Fork>.csv`、`key_numbers.json`；`ops/out2/R1_latency_router_robustness.md`（严格套利）、`R1b_sample_all_arbs_router_robustness.csv`（10 万笔样本、全部套利）、`R2_flow_profiles.md`、`R3_wallet_rotation.md`、`R4_top_operators_six_regimes.md`、`R5_gas.md`、`R6_contracts_vs_operators_bots.md`、`key_numbers.json`；`ops/public_lists/public_contracts_<Fork>.csv`；脚本 `arb_operators.py`（管线 v2.14.3）、`ops_analysis.py`。'''
assert old in R; R = R.replace(old, new)
open(rp, "w").write(R)
print(len(R.splitlines()), "lines")
