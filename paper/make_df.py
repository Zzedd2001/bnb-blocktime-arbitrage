#!/usr/bin/env python3
"""make_df.py — build the Digital Finance (Springer) submission version of the manuscript, paper_df.md,
from paper_draft_v41.md.

Changes relative to v4.1 (content unchanged; structure and front/back matter adapted to the journal):
  * abstract cut to <= 250 words, six keywords, JEL codes;
  * secondary tables moved from the main text to appendices (main text keeps 12 tables and 7 figures);
  * appendices reorganised: A data validation (+ volatility figure), B additional estimates, C reference price
    (candle vs trade, lag 250), D opening times / address-level statistics, E reproducibility;
  * all tables and figures renumbered consecutively in order of appearance (main text 1..n, appendix A1.., B1..),
    every cross-reference updated ("Table 15b" -> "Table B5", "Tables 18–21 and E1–E3" -> "Tables 10, 11 and D1–D5");
  * Statements and Declarations section added before the references.
"""
import re

SRC = "paper_draft_v41.md"
OUT = "paper_df.md"

s = open(SRC, encoding="utf-8").read()
lines = s.split("\n")

CAP = re.compile(r"^\*\*(Table|Figure) ([A-F]?\d+b?)\. ")
ITALIC = re.compile(r"^\*[^*]+\*$")


def float_block(start):
    """Return (start, end) of the float block whose caption is at line `start` (end exclusive)."""
    assert CAP.match(lines[start]), lines[start][:60]
    i = start + 1
    last = start + 1
    while i < len(lines):
        l = lines[i]
        if l.strip() == "":
            i += 1
            continue
        if l.startswith("|") or l.startswith("![") or ITALIC.match(l.strip()):
            i += 1
            last = i
            continue
        break
    return start, last


def find_caption(kind, ident):
    for i, l in enumerate(lines):
        m = CAP.match(l)
        if m and m.group(1) == kind and m.group(2) == ident:
            return i
    raise KeyError((kind, ident))


def cut_block(kind, ident):
    a, b = float_block(find_caption(kind, ident))
    blk = lines[a:b]
    del lines[a:b]
    # remove a blank line left behind if two blanks now meet
    if a < len(lines) and a > 0 and lines[a].strip() == "" and lines[a - 1].strip() == "":
        del lines[a]
    while blk and blk[-1].strip() == "":
        blk.pop()
    return blk


# ----------------------------------------------------------------------------------------------
# 1. cut the tables that move to the appendices (before touching anything else)
# ----------------------------------------------------------------------------------------------
moved = {ident: cut_block("Table", ident) for ident in ["6", "7", "8", "10", "13", "15", "15b", "17", "19", "21"]}
fig4 = cut_block("Figure", "4")


def section_index(prefix):
    for i, l in enumerate(lines):
        if l.startswith(prefix):
            return i
    raise KeyError(prefix)


def replace_section(prefix, new_lines):
    """Replace the whole '## ...' section starting with `prefix` (up to the next '## ') by new_lines."""
    i = section_index(prefix)
    j = i + 1
    while j < len(lines) and not lines[j].startswith("## "):
        j += 1
    lines[i:j] = new_lines


# ----------------------------------------------------------------------------------------------
# 2. appendices
# ----------------------------------------------------------------------------------------------
# A: keep, then append the volatility figure (old Appendix B)
iA = section_index("## Appendix A.")
iB = section_index("## Appendix B.")
appA = lines[iA:iB]
while appA and appA[-1].strip() == "":
    appA.pop()
appA += ["", "**Volatility and raw overshoot around the forks.** Figure 4 plots daily Binance realised volatility and the daily mean strict "
         "overshoot of the three core pools around each fork; it documents the volatility regimes that motivate the choice of windows "
         "and controls in Section 5.", ""] + fig4 + [""]

# old C and D -> new C (reference price), with Tables 6, 7 and 17 moved in
iC = section_index("## Appendix C.")
iD = section_index("## Appendix D.")
iE = section_index("## Appendix E.")
oldC = lines[iC + 1:iD]
oldD = lines[iD + 1:iE]
while oldC and oldC[-1].strip() == "":
    oldC.pop()
while oldD and oldD[-1].strip() == "":
    oldD.pop()
appC = ["## Appendix C. The reference price: candle versus trade, and the reference lag", "",
        "This appendix collects the estimates that compare the two reference prices (Section 6.2) and the two alignments of the "
        "trade reference (Section 6.8). Table 6 places the candle-reference estimates next to the trade-reference estimates for the "
        "placebo-clean specifications and Table 7 measures the wedge between the two references at each fork; Table C1 reproduces "
        "the full set of candle-reference estimates; Tables 17, D1 and D2 report the estimates with the reference taken 250 ms "
        "before the block timestamp.", ""] + moved["6"] + [""] + moved["7"] + [""] + oldC + ["", ""] + moved["17"] + [""] + oldD + [""]

# new B: additional estimates
appB = ["## Appendix B. Additional estimates", "",
        "This appendix collects the pool-by-pool estimates (Table 8), the decomposition of the LPs' loss (Table 10), the heterogeneity "
        "of the overshoot effect (Table 13), the matched-pair estimates (Table 15) and the estimates on bot flow with public routers "
        "excluded (Table 15b) that Sections 6.3–6.7 discuss.", ""]
for k in ["8", "10", "13", "15", "15b"]:
    appB += moved[k] + [""]

# old E -> new D with Tables 19 and 21 inserted; old F -> new E
iE = section_index("## Appendix E.")
iF = section_index("## Appendix F.")
oldE = lines[iE:iF]
oldF = lines[iF:]
# insert Table 19 before Figure E2's caption and Table 21 after Figure E2's image line
k = next(i for i, l in enumerate(oldE) if l.startswith("**Figure E2."))
oldE[k:k] = moved["19"] + [""]
k = next(i for i, l in enumerate(oldE) if l.startswith("![Figure E2]"))
oldE[k + 1:k + 1] = [""] + moved["21"]
appD = ["## Appendix D." + oldE[0][len("## Appendix E."):]] + oldE[1:]
appE = ["## Appendix E." + oldF[0][len("## Appendix F."):]] + oldF[1:]

lines[iA:] = appA + appB + appC + appD + appE

# ----------------------------------------------------------------------------------------------
# 2b. figure order in Section 6.1 (the estimates figure is cited first, in Section 5.3) and the
#     definition of the significance stars in every table that uses them
# ----------------------------------------------------------------------------------------------
fig3 = cut_block("Figure", "3")
k = find_caption("Figure", "2")
lines[k:k] = fig3 + [""]

STARS = " Standard errors in parentheses; ∗, ∗∗ and ∗∗∗ denote significance at the 10%, 5% and 1% levels."
i = 0
while i < len(lines):
    m = CAP.match(lines[i])
    if m and m.group(1) == "Table":
        a, b = float_block(i)
        has_stars = any(re.search(r"\d\*{1,3}(?![*\w])", l) for l in lines[a + 1:b] if l.startswith("|"))
        if has_stars and "denote significance" not in lines[i]:
            lines[i] = lines[i].rstrip() + STARS
        i = b
        continue
    i += 1

# ----------------------------------------------------------------------------------------------
# 3. renumber floats in order of appearance and rewrite every reference
# ----------------------------------------------------------------------------------------------
tab_map, fig_map = {}, {}
appendix = None
tcount = fcount = 0
for l in lines:
    m = re.match(r"^## Appendix ([A-F])\.", l)
    if m:
        appendix = m.group(1)
        tcount = fcount = 0
        continue
    m = CAP.match(l)
    if m:
        kind, ident = m.group(1), m.group(2)
        if kind == "Table":
            tcount += 1
            tab_map[ident] = (appendix or "") + str(tcount)
        else:
            fcount += 1
            fig_map[ident] = (appendix or "") + str(fcount)
print("tables:", tab_map)
print("figures:", fig_map)
app_map = {"A": "A", "B": "A", "C": "C", "D": "C", "E": "D", "F": "E"}

ID_T = r"[A-F]?\d+b?"
ID_F = r"[A-F]?\d+"
SEP = r"(?:–|, and |, or |, | and | or | to )"


def split_id(x):
    m = re.match(r"([A-F]?)(\d+)(b?)$", x)
    return m.group(1), int(m.group(2)), m.group(3)


def render(ids, word):
    """ids: list of new ids in the order found; returns 'Table(s) ...' with sorted, grouped ids."""
    seen = []
    for x in ids:
        if x not in seen:
            seen.append(x)
    order = {"": 0, "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}
    seen.sort(key=lambda x: (order[split_id(x)[0]], split_id(x)[1]))
    # group consecutive numbers with the same prefix
    runs = []
    for x in seen:
        p, n, _ = split_id(x)
        if runs and runs[-1][0] == p and runs[-1][2] == n - 1:
            runs[-1][2] = n
        else:
            runs.append([p, n, n])
    items = []
    for p, a, b in runs:
        if a == b:
            items.append("%s%d" % (p, a))
        elif b == a + 1:
            items.append("%s%d, %s%d" % (p, a, p, b) if len(runs) > 1 else "%s%d and %s%d" % (p, a, p, b))
        else:
            items.append("%s%d–%s%d" % (p, a, p, b))
    single = len(seen) == 1
    w = word.rstrip("s") if single else word.rstrip("s") + "s"
    if len(items) == 1:
        return w + " " + items[0]
    return w + " " + ", ".join(items[:-1]) + " and " + items[-1]


def renumber(text, word_re, idpat, mapping):
    pat = re.compile(r"\b(%s) (%s(?:%s%s)*)(?![\dA-Za-z])" % (word_re, idpat, SEP, idpat))

    def rep(m):
        word, seq = m.group(1), m.group(2)
        toks = re.findall(idpat, seq)
        seps = re.findall(SEP, seq)
        # expand numeric ranges "a–b" with the same prefix
        ids = []
        k = 0
        while k < len(toks):
            if k + 1 < len(toks) and seps[k] == "–" and split_id(toks[k])[0] == split_id(toks[k + 1])[0] and not toks[k].endswith("b"):
                p, a, _ = split_id(toks[k])
                _, b, _ = split_id(toks[k + 1])
                for n in range(a, b + 1):
                    ids.append("%s%d" % (p, n))
                k += 2
                continue
            ids.append(toks[k])
            k += 1
        new = []
        for x in ids:
            if x not in mapping:
                raise KeyError("no mapping for %s %s in: %s" % (word, x, m.group(0)))
            new.append(mapping[x])
        return render(new, word)
    return pat.sub(rep, text)


text = "\n".join(lines)
text = renumber(text, "Tables?", ID_T, tab_map)
text = renumber(text, "Figures?", ID_F, fig_map)
lines = [l if l.startswith("## Appendix") else re.sub(r"\bAppendix ([A-F])\b", lambda m: "Appendix " + app_map[m.group(1)], l)
         for l in text.split("\n")]

# ----------------------------------------------------------------------------------------------
# 4. front matter: title page line, abstract (<= 250 words), keywords (6), JEL codes
# ----------------------------------------------------------------------------------------------
text = "\n".join(lines)
text = text.replace("*Anonymous submission — draft v4.1 (September 2026)*",
                    "*Submission to Digital Finance — manuscript v5.0 (September 2026)*")

ABSTRACT = """## Abstract

Automated market makers quote stale prices between blocks, and the fee-band model of arbitrage predicts that the mispricing at which arbitrageurs trade — the source of liquidity providers' (LPs') adverse-selection cost — scales with the square root of the block interval. We test this on three pre-announced reductions of BNB Chain's block interval, from 3 s to 1.5, 0.75 and 0.45 s, on seven PancakeSwap v3 pools, with 49 million swaps aligned to Binance trades at millisecond resolution. The mispricing falls at every fork, but by a diminishing fraction of the prediction: 84% at the first halving, 28–59% and 44–51% at the two sub-second reductions. Reconstructing when each of 6.5 million arbitrage opportunities opened shows why: arbitrageurs respond with a fixed latency of 0.1–0.35 s, and only the mispricing that accumulates while they wait for a block shrinks by the law; the jump of the reference price that opens an opportunity and the overshoot of same-block back-runs do not respond to the clock, and their share rises from 32% at 3-second blocks to 44% at 0.75 s. The diminishing returns are a composition effect; a further halving would remove roughly a tenth of the remaining mispricing. Arbitrageurs' profits fall by 8–22% per fork and mispricing episodes shorten by 20–35%, but LPs' gross adverse-selection loss does not fall and, in the 5 bp pools, equals their fee income: the block interval is a lever over price efficiency and arbitrage rents, not over the cost of liquidity provision.

**Keywords:** automated market makers; loss-versus-rebalancing; block time; arbitrage latency; decentralized exchanges; natural experiment

**JEL classification:** D47; G12; G14; G23; O33

"""
i = text.index("## Abstract")
j = text.index("## 1. Introduction")
text = text[:i] + ABSTRACT + text[j:]

# ----------------------------------------------------------------------------------------------
# 5. Statements and Declarations before the references
# ----------------------------------------------------------------------------------------------
DECL = """## Statements and Declarations

**Funding.** The author received no financial support for the research, authorship or publication of this article.

**Competing interests.** The author has no relevant financial or non-financial interests to disclose.

**Ethics approval and consent.** Not applicable: the study uses public blockchain and exchange data and involves no human participants.

**Data availability.** All data are public: BNB Chain block headers and swap events (public JSON-RPC nodes, Envio HyperSync and `eth_getLogs`) and Binance's public market-data archive (1-second candles and aggregate trades, data.binance.vision). The processed data underlying the results — the reconstructed block timestamps, the hourly pool panels, the arbitrage-level tables with opening and response times, and the operator tables — together with the scripts that generate every table and figure, are deposited in a public repository ([repository URL / DOI to be inserted at submission]) and are also available from the author on request.

**Code availability.** The data pipeline and the estimation code are released in the same repository under an open-source licence (Appendix E).

**Author contributions.** Single-authored article: the author designed the study, built the data pipeline, performed the analysis and wrote the manuscript.

**Use of generative AI.** A large language model (Claude, Anthropic) was used to assist with writing and debugging the data-pipeline and estimation code and with language editing of the manuscript. All analyses, results and interpretations were verified by the author, who takes full responsibility for the content.

"""
i = text.index("## References")
text = text[:i] + DECL + text[i:]

# wording that assumed the table sat in the section
text = text.replace("excluding it (Table B5 in Section 6.7)", "excluding it (Table B5)")

# Appendix E (reproducibility): the "anonymised repository" wording of the conference version
text = text.replace("is released as an anonymised repository with the submission;",
                    "is released as a public repository (see Code availability);")

open(OUT, "w", encoding="utf-8").write(text)
print("written", OUT, len(text.split("\n")), "lines; abstract words:",
      len(ABSTRACT.split("## Abstract")[1].split("**Keywords")[0].split()))
