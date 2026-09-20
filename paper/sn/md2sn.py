#!/usr/bin/env python3
"""md2sn.py — convert the journal markdown (paper_df.md) into a Springer Nature (sn-jnl, sn-apa) LaTeX file for Digital Finance.

Usage: python3 md2lipics.py <src.md> <out_dir> [--anonymous|--named]

The markdown conventions handled here are those of the paper drafts produced in this project:
  # Title                                   -> \\title
  ## Abstract ... **Keywords:** ...          -> abstract + \\keywords
  ## N. Title / ### N.M Title               -> \\section / \\subsection (numbers stripped, labels sec:N, sec:N.M)
  ## References                              -> dropped (BibTeX: refs.bib, plainurl)
  ## Appendix X. Title                       -> \\appendix + \\section (label app:X)
  **Table X. Title.** notes  + pipe table    -> table float (manuscript numbering kept via \\thetable)
  **Figure X. Title.** notes + ![..](path)   -> figure float
  - item                                     -> itemize
  author-year citations                      -> \\cite{key}
  Unicode math (σ√Δt, Δt₁, ℓ̂, χ², ...)        -> $...$
"""
import os as _os
ROOT = _os.environ.get("REPL_ROOT", _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..")))

import math
import os
import re
import shutil
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else ROOT + "/paper/paper_df.md"
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else ROOT + "/paper/sn"

# title page (single-blind journal): fill in before submission
AUTHOR = {"given": "[Given name]", "family": "[Family name]", "email": "[email address]",
          "affil": r"\orgname{Independent researcher}, \orgaddress{\city{[City]}, \country{[Country]}}",
          "orcid": ""}
SHORT_TITLE = "Faster Blocks Fall Short of the Square-Root Law"

SRC_DIR = os.path.dirname(os.path.abspath(SRC))

# --------------------------------------------------------------------------------------
# placeholders (private-use characters) so that later passes never touch protected text
# --------------------------------------------------------------------------------------
_PH = []


def protect(latex):
    _PH.append(latex)
    return "\ue000%d\ue001" % (len(_PH) - 1)


def restore(s):
    def rep(m):
        return _PH[int(m.group(1))]
    while re.search(r"\ue000(\d+)\ue001", s):
        s = re.sub(r"\ue000(\d+)\ue001", rep, s)
    return s


# --------------------------------------------------------------------------------------
# citations
# --------------------------------------------------------------------------------------
AUTH = {
    "Milionis, Moallemi, Roughgarden and Zhang": {"2022": "milionis2022lvr"},
    "Milionis, Moallemi and Roughgarden": {"2024": "milionis2024fees", "2025": "milionis2024fees"},
    "Milionis et al.": {"2022": "milionis2022lvr", "2024": "milionis2024fees", "2025": "milionis2024fees"},
    "Capponi and Jia": {"2021": "capponi2025adoption", "2025": "capponi2025adoption"},
    "Capponi, Jia and Yu": {"2026": "capponi2026discovery"},
    "Hasbrouck, Rivera and Saleh": {"2026a": "hasbrouck2026model", "2026b": "hasbrouck2026fees"},
    "Adams et al.": {"2025": "adams2025amamm", "2026": "adams2025amamm"},
    "Adams, Moallemi, Reynolds and Robinson": {"2025": "adams2025amamm", "2026": "adams2025amamm"},
    "Lehar and Parlour": {"2025": "lehar2025uniswap"},
    "Lehar, Parlour and Zoican": {"2024": "lehar2024fragmentation"},
    "Barbon and Ranaldo": {"2026": "barbon2026quality"},
    "Alexander et al.": {"2025": "alexander2025price"},
    "Fritsch and Canidio": {"2024": "fritsch2024measuring"},
    "Canidio and Fritsch": {"2023": "canidio2023batch"},
    "Zhou et al.": {"2021": "zhou2021hft"},
    "Qin et al.": {"2022": "qin2022bev"},
    "Qin, Zhou and Gervais": {"2022": "qin2022bev"},
    "Öz et al.": {"2025": "oz2025crosschain"},
    "BNB Chain": {"2025a": "bnbchain2025bep520", "2025b": "bnbchain2025maxwell", "2026": "bnbchain2026fermi"},
    "Heimbach, Schertenleib and Wattenhofer": {"2022": "heimbach2022risks"},
    "Heimbach et al.": {"2022": "heimbach2022risks"},
    "Campbell et al.": {"2025": "campbell2025fees"},
    "Budish, Cramton and Shim": {"2015": "budish2015hft"},
    "Cartea, Drissi and Monga": {"2024": "cartea2024predictable"},
    "Di Nosse et al.": {"2025": "dinosse2025stylized"},
    "He, Yang and Zhou": {"2025": "he2025arbitrage"},
    "Park": {"2023": "park2023flaws"},
    "Singh et al.": {"2025": "singh2025lvr"},
    "Turnbull": {"1976": "turnbull1976empirical"},
    "Urusov et al.": {"2026": "urusov2026clmm"},
    "Xu et al.": {"2023": "xu2023sok"},
}
AUTH_ALT = "|".join(re.escape(a) for a in sorted(AUTH, key=len, reverse=True))
YEAR = r"(?:19|20)\d\d[a-c]?"
UNRESOLVED = []


def keys_for(auth, years):
    out = []
    for y in re.split(r",\s*", years):
        k = AUTH.get(auth, {}).get(y)
        if k is None:
            UNRESOLVED.append((auth, y))
        else:
            out.append(k)
    return out


def convert_citations(text):
    # textual: Author (year[, year]) -> \citet{keys}
    def textual(m):
        auth, years = m.group(1), m.group(2)
        ks = keys_for(auth, years)
        if not ks:
            return m.group(0)
        return protect("\\citet{%s}" % ",".join(ks))
    text = re.sub(r"(%s) \((%s(?:, %s)*)\)" % (AUTH_ALT, YEAR, YEAR), textual, text)

    # parenthetical groups: ( item; item; ... ) where items end with "Author, year[, year]"
    def paren(m):
        inner = m.group(1)
        items = [it.strip() for it in inner.split(";")]
        out, allcite, changed = [], True, False
        for it in items:
            mm = re.match(r"^(.*?)(%s), (%s(?:, %s)*)$" % (AUTH_ALT, YEAR, YEAR), it)
            if mm:
                pre, auth, years = mm.group(1), mm.group(2), mm.group(3)
                ks = keys_for(auth, years)
                if ks:
                    changed = True
                    if pre.strip():
                        allcite = False
                        out.append("%s%s" % (pre, protect("\\citealp{%s}" % ",".join(ks))))
                    else:
                        out.append(protect("\\citealp{%s}" % ",".join(ks)))
                    continue
            allcite = False
            out.append(it)
        if not changed:
            return m.group(0)
        if allcite:
            keys = []
            for o in out:
                keys += re.findall(r"\\citealp\{([^}]*)\}", _PH[int(o[1:-1])])
            return protect("\\citep{%s}" % ",".join(keys))
        return "(" + "; ".join(out) + ")"
    text = re.sub(r"\(([^()]*?%s[^()]*?)\)" % YEAR, paren, text)
    return text


# --------------------------------------------------------------------------------------
# cross references
# --------------------------------------------------------------------------------------
LABELS = set()   # filled in the first pass: tab:4, tab:15b, tab:E4b, fig:6, fig:E1, sec:6.9, app:E


def convert_xrefs(text):
    kinds = {"Table": "tab", "Tables": "tab", "Figure": "fig", "Figures": "fig",
             "Section": "sec", "Sections": "sec", "Appendix": "app", "Appendices": "app"}
    idpat = {"tab": r"[A-F]?\d+b?", "fig": r"[A-F]?\d+", "sec": r"\d+(?:\.\d+)?", "app": r"[A-F]"}

    def rep(m):
        word = m.group(1)
        k = kinds[word]
        rest = m.group(2)
        # sequence: ID ( (–|, |, and | and | or ) ID )*
        pat = re.compile(r"^(%s)(?![\d.])" % idpat[k])
        seps = re.compile(r"^(–|, and |, or |, | and | or | to )")
        out = {"Figure": "Fig.", "Figures": "Figs."}.get(word, word) + protect("~")
        pos = 0
        first = True
        while True:
            mm = pat.match(rest[pos:])
            if not mm:
                if first:
                    return m.group(0)
                break
            ident = mm.group(1)
            lab = "%s:%s" % (k, ident)
            if lab in LABELS:
                out += protect("\\ref{%s}" % lab)
            else:
                out += ident
            pos += mm.end()
            first = False
            ms = seps.match(rest[pos:])
            if not ms:
                break
            # only continue if an ID follows
            if not pat.match(rest[pos + ms.end():]):
                break
            out += ms.group(1)
            pos += ms.end()
        return out + rest[pos:]
    return re.sub(r"\b(Tables?|Figures?|Sections?|Appendix|Appendices) ((?:[A-F]?\d+(?:\.\d+)?b?|[A-F])(?:[^A-Za-z]{0,7}(?:[A-F]?\d+(?:\.\d+)?b?|[A-F])\b)*)", rep, text)


# --------------------------------------------------------------------------------------
# math
# --------------------------------------------------------------------------------------
GREEK = {"α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta", "ε": r"\varepsilon", "η": r"\eta",
         "θ": r"\theta", "κ": r"\kappa", "σ": r"\sigma", "τ": r"\tau", "χ": r"\chi", "ρ": r"\rho",
         "Π": r"\Pi", "Σ": r"\Sigma", "Δ": r"\Delta"}
SYMS = {"∝": r"\propto", "≈": r"\approx", "≤": r"\le", "≥": r"\ge", "≪": r"\ll", "≫": r"\gg",
        "≲": r"\lesssim", "≳": r"\gtrsim", "⌈": r"\lceil", "⌉": r"\rceil", "±": r"\pm", "→": r"\to", "×": r"\times",
        "−": "-", "ℓ": r"\ell", "½": r"\tfrac{1}{2}", "…": r"\dots"}
MATH_CHARS = set(GREEK) | set("√∝≈≤≥≪≫≲≳⌈⌉ℓ½²³·×₀₁") | {"\u0302"}
FUNCS = {"log": r"\log", "ln": r"\ln", "max": r"\max", "min": r"\min", "exp": r"\exp"}
ROMAN_WORDS = {"pre", "post", "open", "block", "prev", "arbitrages", "wait", "second", "price", "volume",
               "overshoot", "arbitrage", "bp", "dev", "first"}
ITALIC_WORDS = {"Post"}
CODE_IDS = {"lp_gain", "fee_income", "arb_loss", "arb_profit"}
SUB_ROMAN = {"pre", "post", "open", "block", "prev", "arbitrages", "first"}
VARS = {"L", "M", "J", "F", "P", "Q", "k", "q"}


def math_inner(s):
    """Convert a math run (Unicode) to LaTeX math (without the $ delimiters)."""
    out = []
    i = 0
    n = len(s)

    def word_at(j):
        m = re.match(r"[A-Za-z]+(?:_[A-Za-z]+)*", s[j:])
        if m and m.group(0) in CODE_IDS:
            return m.group(0)
        m = re.match(r"[A-Za-z]+", s[j:])
        return m.group(0) if m else ""

    while i < n:
        c = s[i]
        if c == "√":
            i += 1
            if i < n and s[i] == "(":
                depth, j = 0, i
                while j < n:
                    if s[j] == "(":
                        depth += 1
                    elif s[j] == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    j += 1
                out.append(r"\sqrt{%s}" % math_inner(s[i + 1:j]))
                i = j + 1
            else:
                # atom: Δt (+subscript), Greek (+sub/sup), number, or word
                m = re.match(r"(Δt[₀₁]?|[α-ωΠΣ][₀₁]?[²³]?|\d+(?:\.\d+)?|[A-Za-z]+)", s[i:])
                if m:
                    out.append(r"\sqrt{%s}" % math_inner(m.group(1)))
                    i += m.end()
                else:
                    out.append(r"\surd ")
            continue
        if c == "Δ":
            m = re.match(r"Δ(log|ln)", s[i:])
            if m:
                out.append(r"\Delta" + FUNCS[m.group(1)])
                i += m.end()
                continue
            out.append(r"\Delta ")
            i += 1
            continue
        if c in GREEK:
            out.append(GREEK[c])
            i += 1
            # ℓ-like hats handled below; Greek followed by letters needs a space
            if i < n and s[i].isalpha():
                out.append(" ")
            continue
        if c == "ℓ":
            if i + 1 < n and s[i + 1] == "\u0302":
                out.append(r"\hat{\ell}")
                i += 2
            else:
                out.append(r"\ell ")
                i += 1
            continue
        if c == "\u0302":
            i += 1
            continue
        if c in "₀₁":
            out.append("_%d" % "₀₁".index(c))
            i += 1
            continue
        if c == "²":
            out.append("^2")
            i += 1
            continue
        if c == "³":
            out.append("^3")
            i += 1
            continue
        if c == "·":
            prev = "".join(out).rstrip()
            nxt = s[i + 1:i + 4]
            if prev.endswith(r"\tfrac{1}{2}") or nxt.startswith(("ln", "log", "(")):
                out.append(r"\,")
            else:
                out.append(r"\cdot ")
            i += 1
            continue
        if c == "_":
            i += 1
            if i < n and s[i] == "{":
                j = s.index("}", i)
                out.append("_{%s}" % math_inner(s[i + 1:j]))
                i = j + 1
                continue
            m = re.match(r"([A-Za-z0-9]+)", s[i:])
            if m:
                w = m.group(1)
                i += m.end()
                if w in SUB_ROMAN:
                    out.append(r"_{\mathrm{%s}}" % w)
                elif len(w) == 1:
                    # η_h(t) -> _{h(t)}
                    if s[i:i + 3] == "(t)":
                        out.append("_{%s(t)}" % w)
                        i += 3
                    else:
                        out.append("_%s" % w)
                else:
                    out.append("_{%s}" % w)
            else:
                out.append(r"\_")
            continue
        if c in SYMS:
            out.append(SYMS[c] + (" " if SYMS[c].startswith("\\") else ""))
            i += 1
            continue
        if c == "|" and s[i - 1:i] == " " and s[i + 1:i + 2] == " ":
            out.append(r"\mid ")
            i += 1
            continue
        if c.isalpha():
            w = word_at(i)
            if not w:
                out.append(c)
                i += 1
                continue
            i += len(w)
            if w in CODE_IDS:
                out.append(r"\texttt{%s}" % w.replace("_", r"\_"))
            elif w in FUNCS:
                out.append(FUNCS[w] + " ")
            elif w in ITALIC_WORDS:
                out.append(r"\mathit{%s}" % w)
            elif w in ROMAN_WORDS or len(w) > 2:
                out.append(r"\mathrm{%s}" % w)
            else:
                out.append(w)
            continue
        if c == "'":
            out.append("'")
            i += 1
            continue
        if c in "–—":
            out.append(r"\text{–}")
            i += 1
            continue
        out.append(c)
        i += 1
    res = "".join(out)
    res = re.sub(r"\s+", " ", res).strip()
    res = res.replace(" )", ")").replace("( ", "(")
    return res


# explicit formula overrides applied before generic detection (longest first)
OVERRIDES = [
    ("E[overshoot | arbitrage] ∝ σ√Δt", r"$E[\mathrm{overshoot} \mid \mathrm{arbitrage}] \propto \sigma\sqrt{\Delta t}$"),
    ("∝ [L·(σ√Δt)²] × [σ√Δt/γ] / Δt ∝ L·σ³√Δt/γ", r"$\propto [L\,(\sigma\sqrt{\Delta t})^2]\times[\sigma\sqrt{\Delta t}/\gamma]/\Delta t \propto L\,\sigma^3\sqrt{\Delta t}/\gamma$"),
    ("½σ²·L", r"$\tfrac{1}{2}\sigma^2 L$"),
    ("E[max(0, 1 − ℓ/Δt)]", r"$E[\max(0,\,1-\ell/\Delta t)]$"),
    ("(t_{b−1} − t_open, t_b − t_open]", r"$(t_{b-1}-t_{\mathrm{open}},\, t_b-t_{\mathrm{open}}]$"),
    ("t_{b−1} − t_open", r"$t_{b-1}-t_{\mathrm{open}}$"),
    ("dev_pre = p_pre/P − 1", r"$\mathrm{dev}_{\mathrm{pre}} = p_{\mathrm{pre}}/P - 1$"),
    ("(|dev_pre| − γ) − J", r"$(|\mathrm{dev}_{\mathrm{pre}}| - \gamma) - J$"),
    ("|dev_pre| > γ", r"$|\mathrm{dev}_{\mathrm{pre}}| > \gamma$"),
    ("|dev_pre| − γ", r"$|\mathrm{dev}_{\mathrm{pre}}| - \gamma$"),
    ("|dev_pre|", r"$|\mathrm{dev}_{\mathrm{pre}}|$"),
    ("|p_pre/P − 1| ≤ γ", r"$|p_{\mathrm{pre}}/P - 1| \le \gamma$"),
    ("|p_pre/P_open − 1| − γ", r"$|p_{\mathrm{pre}}/P_{\mathrm{open}} - 1| - \gamma$"),
    ("[p_pre/(1+γ), p_pre/(1−γ)]", r"$[p_{\mathrm{pre}}/(1+\gamma),\, p_{\mathrm{pre}}/(1-\gamma)]$"),
    ("`lp_gain` = ΔQ + ΔB·P", r"\texttt{lp\_gain} $= \Delta Q + \Delta B\,P$"),
    ("`fee_income` = γ × input value", r"\texttt{fee\_income} $= \gamma\times$ input value"),
    ("`arb_loss` = fee_income − lp_gain", r"\texttt{arb\_loss} = \texttt{fee\_income} $-$ \texttt{lp\_gain}"),
    ("`arb_profit` = Σ_arbitrages (arb_loss − fee_income)", r"\texttt{arb\_profit} $= \sum_{\mathrm{arbitrages}} (\texttt{arb\_loss} - \texttt{fee\_income})$"),
    ("lp_gain/volume", r"\texttt{lp\_gain}/volume"),
    ("Σ w·β", r"$\sum w\,\beta$"),
    ("2.2–2.3·ℓ_t", r"2.2–2.3$\,\ell_t$"),
    ("X_pt'κ", r"$X_{pt}'\kappa$"),
    ("bp/√s", r"$\mathrm{bp}/\sqrt{\mathrm{s}}$"),
    ("√second", r"$\sqrt{\text{second}}$"),
    ("√price", r"$\sqrt{\text{price}}$"),
    ("P(ℓ ≤ Δt)", r"$P(\ell \le \Delta t)$"),
    ("P(ℓ≤Δt)", r"$P(\ell \le \Delta t)$"),
    ("log(E[√τ]_post / E[√τ]_pre)", r"$\log(E[\sqrt{\tau}]_{\mathrm{post}}/E[\sqrt{\tau}]_{\mathrm{pre}})$"),
    ("E[√τ]_post", r"$E[\sqrt{\tau}]_{\mathrm{post}}$"),
    ("E[√τ]_pre", r"$E[\sqrt{\tau}]_{\mathrm{pre}}$"),
    ("E[√τ]", r"$E[\sqrt{\tau}]$"),
]
DISPLAY = {
    "Δlog(Π + F) ≈ −s·(1 − √(Δt₁/Δt₀)),": r"\[\Delta\log(\Pi + F) \approx -s\,\bigl(1 - \sqrt{\Delta t_1/\Delta t_0}\bigr),\]",
    "log y_pt = β·Post_t + δ·log σ_pt + X_pt'κ + α_p + η_h(t) + ε_pt,": r"\[\log y_{pt} = \beta\,\mathit{Post}_t + \delta\log\sigma_{pt} + X_{pt}'\kappa + \alpha_p + \eta_{h(t)} + \varepsilon_{pt},\]",
}

OPS = {"=", "+", "−", "×", "/", "≈", "∝", "≤", "≥", "≪", "≫", ">", "<", "-"}
OPERAND = re.compile(r"^[+−-]?(?:\d[\d.,]*|[A-Za-z](?:_[A-Za-z0-9]+)?'?|\(.*\)|\[.*\]|\|.*\|)[.,;:)\]]*$")
NOVAR_PREV = {"Appendix", "Table", "Figure", "Panel", "Section", "Sections", "Tables", "Figures", "regime", "set", "sets", "Set", "column", "Column", "row", "Row", "pool", "Pool", "type", "Type"}


def is_math_token(tok, prev):
    core = tok.strip("()[],.;:")
    if any(ch in MATH_CHARS for ch in tok):
        return True
    if "_" in core and not core.startswith("`"):
        return True
    if core in VARS and prev not in NOVAR_PREV and not re.match(r"^[\d.,]+$", prev.strip("()[],.;:")):
        return True
    return False


def apply_overrides(text):
    for k, v in sorted(OVERRIDES, key=lambda kv: -len(kv[0])):
        if k in text:
            text = text.replace(k, protect(v))
    return text


def convert_math(text):
    text = apply_overrides(text)
    # word-hyphen-symbol compounds such as "high-σ", "sub-Δt": keep the word in text
    text = re.sub(r"\b([A-Za-z]{2,})-(σ|γ|τ|ℓ|Δt)\b",
                  lambda m: m.group(1) + "-" + protect("$" + math_inner(m.group(2)) + "$"), text)
    # tokens with positions
    toks = [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"\S+", text)]
    pieces = []
    last = 0
    i = 0
    while i < len(toks):
        s, e, w = toks[i]
        prev = toks[i - 1][2] if i > 0 else ""
        if "\ue000" in w or not is_math_token(w, prev):
            i += 1
            continue
        j = i
        while j + 1 < len(toks):
            nw = toks[j + 1][2]
            if "\ue000" in nw:
                break
            if is_math_token(nw, toks[j][2]) and not nw.startswith("("):
                j += 1
                continue
            if nw in OPS and j + 2 < len(toks) and "\ue000" not in toks[j + 2][2] and (
                    is_math_token(toks[j + 2][2], nw) or OPERAND.match(toks[j + 2][2])):
                j += 2
                continue
            break
        run = text[toks[i][0]:toks[j][1]]
        # split prefix / suffix punctuation
        pre, suf = "", ""
        while run and run[0] in "([" and run.count(run[0]) > run.count({"(": ")", "[": "]"}[run[0]]):
            pre += run[0]
            run = run[1:]
        while run and run[-1] in ".,;:":
            suf = run[-1] + suf
            run = run[:-1]
        while run and run[-1] in ")]" and run.count(run[-1]) > run.count({")": "(", "]": "["}[run[-1]]):
            suf = run[-1] + suf
            run = run[:-1]
        if not run:
            i = j + 1
            continue
        latex = "$" + math_inner(run) + "$"
        pieces.append(text[last:toks[i][0]])
        pieces.append(pre + protect(latex) + suf)
        last = toks[j][1]
        i = j + 1
    pieces.append(text[last:])
    return "".join(pieces)


# --------------------------------------------------------------------------------------
# inline text
# --------------------------------------------------------------------------------------
def escape_text(s):
    s = s.replace("\\", "\ue002")
    for a, b in [("&", r"\&"), ("%", r"\%"), ("#", r"\#"), ("$", r"\$"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
                 ("~", r"\textasciitilde{}"), ("^", r"\^{}")]:
        s = s.replace(a, b)
    s = s.replace("\ue002", r"\textbackslash{}")
    # symbols that are simplest as math in text
    s = s.replace("−", "$-$").replace("±", "$\\pm$").replace("→", "$\\to$").replace("×", "$\\times$")
    s = s.replace("≈", "$\\approx$").replace("≥", "$\\ge$").replace("≤", "$\\le$").replace("…", r"\dots{}")
    s = s.replace("½", r"\textonehalf{}").replace("²", r"\textsuperscript{2}")
    s = s.replace("√", "$\\surd$").replace("|", "$|$").replace("<", "$<$").replace(">", "$>$")
    s = re.sub("∗{1,3}", lambda m: "$^{%s}$" % ("*" * len(m.group(0))), s)
    for g, l in GREEK.items():
        s = s.replace(g, "$%s$" % l)
    s = s.replace("ℓ\u0302", r"$\hat{\ell}$").replace("ℓ", r"$\ell$")
    s = s.replace("\u0302", "")
    return s


def inline(text, cell=False):
    """Full inline conversion of a piece of markdown prose to LaTeX."""
    text = apply_overrides(text)
    # code spans
    text = re.sub(r"`([^`]+)`", lambda m: protect(r"\texttt{%s}" % m.group(1).replace("_", r"\_")), text)
    if not cell:
        text = convert_citations(text)
        text = convert_xrefs(text)
    text = convert_math(text)
    # bold / italic
    text = re.sub(r"\*\*([^*]+)\*\*", lambda m: protect(r"\textbf{%s}" % inline_plain(m.group(1))), text)
    text = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", lambda m: protect(r"\emph{%s}" % inline_plain(m.group(1))), text)
    if cell:
        text = re.sub(r"(?<=[\d)\]])(\*{1,3})(?![*\w])", lambda m: protect("$^{%s}$" % m.group(1)), text)
    # quotes
    text = re.sub(r'"([^"]*)"', lambda m: "``" + m.group(1) + "''", text)
    text = escape_text(text)
    return restore(text)


def inline_plain(text):
    """Inline conversion for text that is already inside a protected construct (bold, emph)."""
    text = convert_math(text)
    text = re.sub(r'"([^"]*)"', lambda m: "``" + m.group(1) + "''", text)
    return restore(escape_text(text))


# --------------------------------------------------------------------------------------
# tables
# --------------------------------------------------------------------------------------
TEXTWIDTH = 372.0   # pt (sn-jnl text width)
TEXTHEIGHT = 553.0  # pt (sn-jnl text height; width available to a sideways table)
CW = {"small": 4.6, "footnotesize": 4.1, "scriptsize": 3.6}


def parse_pipe_table(rows):
    cells = []
    align = None
    for r in rows:
        r = r.strip()
        if r.startswith("|"):
            r = r[1:]
        if r.endswith("|"):
            r = r[:-1]
        parts = [c.strip() for c in r.split("|")]
        if re.fullmatch(r"[\s:\-|]+", "|".join(parts)) and align is None and cells:
            align = []
            for p in parts:
                p = p.strip()
                if p.startswith(":") and p.endswith(":"):
                    align.append("c")
                elif p.endswith(":"):
                    align.append("r")
                else:
                    align.append("l")
            continue
        cells.append(parts)
    ncol = max(len(r) for r in cells)
    cells = [r + [""] * (ncol - len(r)) for r in cells]
    if align is None:
        align = ["l"] * ncol
    align = (align + ["l"] * ncol)[:ncol]
    return cells[0], cells[1:], align


def wrap_words(s, width):
    words = s.split()
    lines, cur = [], ""
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def cell_tex(c):
    return inline(c, cell=True)


# approximate glyph widths in em (Latin Modern), used only to choose the table layout
_W = {"digit": 0.50, "upper": 0.68, "lower": 0.50, " ": 0.33, ".": 0.28, ",": 0.28, "(": 0.39, ")": 0.39,
      "[": 0.28, "]": 0.28, "*": 0.35, "−": 0.78, "+": 0.78, "-": 0.33, "/": 0.50, "→": 1.0, "%": 0.83,
      ":": 0.28, "–": 0.50, "±": 0.78, "√": 0.83, "≥": 0.78, "≤": 0.78, "×": 0.78, "|": 0.28, "'": 0.28,
      "…": 1.0, "Δ": 0.83, "σ": 0.57, "β": 0.57, "τ": 0.44, "ℓ": 0.42, "χ": 0.63, "γ": 0.52, "ρ": 0.52}
FONT_PT = {"small": 9.0, "footnotesize": 8.0, "scriptsize": 7.0}
FONT_CMD = {"small": "\\small", "footnotesize": "\\tablebodyfont", "scriptsize": "\\scriptsize"}


def width_em(s):
    s = re.sub(r"\*\*", "", s)
    w = 0.0
    for ch in s:
        if ch.isdigit():
            w += _W["digit"]
        elif ch.isupper():
            w += _W["upper"]
        elif ch.islower():
            w += _W["lower"]
        else:
            w += _W.get(ch, 0.5)
    return w


COEF_RE = re.compile(r"^([+−-]?\d[\d.,]*\*{0,3})\s+(\(.+?\))(\s+\[.*\])?$")


def split_cell(c, maxem, level=1):
    """Return the lines of a cell, breaking coefficient/se cells and long compound cells when needed.
    level 1: two lines (coef / (se) [share]); level 2: three lines and every ' / ' part on its own line."""
    if width_em(c) <= maxem:
        return [c]
    m = COEF_RE.match(c)
    if m:
        if level >= 2 and m.group(3):
            return [m.group(1), m.group(2), m.group(3).strip()]
        return [m.group(1), m.group(2) + (m.group(3) or "")]
    if " / " in c:
        parts = c.split(" / ")
        if level >= 2:
            return parts
        lines, cur = [], ""
        for p in parts:
            cand = p if not cur else cur + " / " + p
            if cur and width_em(cand) > maxem:
                lines.append(cur)
                cur = p
            else:
                cur = cand
        lines.append(cur)
        return lines
    if " " in c:
        target = max(12, int(len(c) / 2) + 2)
        return wrap_words(c, target)
    return [c]


def tabular_tex(rows, split, font):
    """The tabular for one pipe table. split: break coefficient/long cells; font: footnotesize/scriptsize.
    Returns (lines, transpose)."""
    header, body, align = parse_pipe_table(rows)
    ncol = len(header)
    transpose = len(body) <= 3 and (ncol >= 8 or sum(width_em(max([r[k] for r in [header] + body], key=len)) for k in range(ncol)) > 110)
    if transpose:
        newh = [header[0]] + [r[0] for r in body]
        newb = [[header[k]] + [r[k] for r in body] for k in range(1, ncol)]
        header, body = newh, newb
        ncol = len(header)
        align = ["l"] * ncol
        font = "footnotesize"
    prose = (not transpose) and ncol <= 5 and any(max(len(r[k]) for r in [header] + body) > 70 for k in range(ncol))
    if prose:
        font = "footnotesize"
    maxem = 6.5 if split else 999
    level = min(split, 2)
    bcells = []
    # split every coefficient cell of the table if any of them needs splitting (consistent look)
    force = split and any(width_em(c) > maxem and COEF_RE.match(c) for r in body for c in r)
    for k in range(ncol):
        col = [r[k] for r in body]
        bcells.append([split_cell(c, 0 if (force and COEF_RE.match(c)) else maxem, level) for c in col])
    bw = [max([width_em(l) for lines in bcells[k] for l in lines] + [0.5]) for k in range(ncol)]
    hl = []
    for k in range(ncol):
        target = max(int(bw[k] / 0.5), 14 if split < 3 else 9)
        hl.append(wrap_words(header[k], target))
    lines = ["%s\\setlength{\\tabcolsep}{%s}\\renewcommand{\\arraystretch}{1.08}" % (FONT_CMD[font], "3pt" if split < 2 else "2.5pt" if split < 3 else "2pt")]
    if transpose:
        first = 78.0
        rest = (TEXTWIDTH - first - ncol * 6.0) / (ncol - 1)
        colspec = ">{\\raggedright\\arraybackslash}p{%.0fpt}" % first + (">{\\raggedright\\arraybackslash}p{%.0fpt}" % rest) * (ncol - 1)
    elif prose:
        lens = [max(len(r[k]) for r in [header] + body) for k in range(ncol)]
        raw = [max(l, 10) ** 0.75 for l in lens]
        total = TEXTWIDTH - ncol * 6.0
        widths = [total * x / sum(raw) for x in raw]
        colspec = "".join(">{\\raggedright\\arraybackslash}p{%.0fpt}" % w for w in widths)
    else:
        colspec = "".join("l" if k == 0 else ("r" if align[k] == "r" else "c") for k in range(ncol))
    lines.append("\\begin{tabular}{%s}" % colspec)
    lines.append("\\toprule")
    hcells = []
    for k in range(ncol):
        al = "l" if k == 0 else ("r" if align[k] == "r" else "c")
        ls = [cell_tex(l) for l in hl[k]]
        if transpose or prose:
            hcells.append("\\textbf{%s}" % cell_tex(header[k]))
        elif len(ls) > 1:
            hcells.append("\\mcell[%s]{%s}" % (al, " \\\\{} ".join(ls)))
        else:
            hcells.append(ls[0] if ls else "")
    lines.append(" & ".join(hcells) + " \\\\")
    lines.append("\\midrule")
    for ri, r in enumerate(body):
        if r[0].startswith("**") and all(c == "" for c in r[1:]):
            lines.append("\\multicolumn{%d}{l}{%s} \\\\" % (ncol, cell_tex(r[0])))
            continue
        cells = []
        for k in range(ncol):
            if transpose or prose:
                cells.append(cell_tex(r[k]))
                continue
            ls = bcells[k][ri]
            al = "l" if k == 0 else ("r" if align[k] == "r" else "c")
            if len(ls) > 1:
                cells.append("\\mcell[%s]{%s}" % (al, " \\\\{} ".join(cell_tex(l) for l in ls)))
            else:
                cells.append(cell_tex(ls[0]))
        lines.append(" & ".join(cells) + " \\\\")
    lines.append("\\botrule")
    lines.append("\\end{tabular}")
    return lines, transpose


MEASURED = {}   # (ident, panel_index, split, font) -> width in pt
PANEL_REGISTRY = []  # (ident, panel_index, rows)


def measure_widths():
    """Typeset every tabular variant once in a scratch document and record its natural width."""
    variants = [(0, "footnotesize"), (1, "footnotesize"), (1, "scriptsize"), (2, "footnotesize"), (2, "scriptsize"), (3, "footnotesize"), (3, "scriptsize")]
    doc = [PREAMBLE_HEAD, "\\begin{document}"]
    for ident, pi, rows in PANEL_REGISTRY:
        for split, font in variants:
            lines, transpose = tabular_tex(rows, split, font)
            if transpose:
                MEASURED[(ident, pi, split, font)] = (TEXTWIDTH, 200.0)
                continue
            doc.append("\\setbox0=\\hbox{%s}" % "\n".join(lines))
            doc.append("\\typeout{WIDTH %s|%d|%d|%s|\\the\\wd0|\\the\\ht0|\\the\\dp0}" % (ident, pi, split, font))
    doc.append("\\end{document}")
    mdir = os.path.join(OUT_DIR, "measure")
    os.makedirs(mdir, exist_ok=True)
    for f in ("sn-jnl.cls", "sn-apacite.bst"):
        if os.path.exists(os.path.join(OUT_DIR, f)) and not os.path.exists(os.path.join(mdir, f)):
            shutil.copy(os.path.join(OUT_DIR, f), mdir)
    open(os.path.join(mdir, "measure.tex"), "w", encoding="utf-8").write("\n".join(doc))
    os.system("cd %s && pdflatex -interaction=nonstopmode measure.tex > measure.out 2>&1" % mdir)
    log = open(os.path.join(mdir, "measure.log"), encoding="utf-8", errors="replace").read()
    for m in re.finditer(r"WIDTH ([^|]+)\|(\d+)\|(\d)\|(\w+)\|([\d.]+)pt\|([\d.]+)pt\|([\d.]+)pt", log):
        MEASURED[(m.group(1), int(m.group(2)), int(m.group(3)), m.group(4))] = (float(m.group(5)), float(m.group(6)) + float(m.group(7)))
    missing = [k for k in [(i, p, sp, f) for i, p, _ in PANEL_REGISTRY for sp, f in variants] if k not in MEASURED]
    if missing:
        print("WARNING: widths not measured for", missing[:10])


AVAIL = {"portrait": (TEXTWIDTH, TEXTHEIGHT), "rotate": (TEXTHEIGHT, TEXTWIDTH)}
VARIANT_ORDER = [(0, "footnotesize"), (1, "footnotesize"), (2, "footnotesize"), (1, "scriptsize"), (2, "scriptsize"),
                 (3, "footnotesize"), (3, "scriptsize")]


def choose_layout(ident, npanels, title="", notes=""):
    """Choose one variant per panel and a common orientation/scale for the table.
    Returns (variants, rotate, scale) with variants = [(split, font), ...]."""
    def size(pi, split, font):
        return MEASURED.get((ident, pi, split, font), (1e9, 1e9))
    best = None
    for orient in ("portrait", "rotate"):
        aw = AVAIL[orient][0]
        cpl = 95.0 if orient == "portrait" else 145.0          # caption characters per line
        capnotes = 12.0 * math.ceil(len(title) / cpl) + 9.5 * math.ceil(len(notes) / (cpl * 1.25)) + 30.0
        ah = (TEXTHEIGHT if orient == "portrait" else TEXTWIDTH) * 0.92 - capnotes
        # per panel: the first variant whose width fits; else the narrowest
        chosen = []
        for pi in range(npanels):
            pick = None
            for split, font in VARIANT_ORDER:
                if size(pi, split, font)[0] <= aw:
                    pick = (split, font)
                    break
            if pick is None:
                pick = min(VARIANT_ORDER, key=lambda v: size(pi, v[0], v[1])[0])
            chosen.append(pick)
        w = max(size(pi, *chosen[pi])[0] for pi in range(npanels))
        h = sum(size(pi, *chosen[pi])[1] for pi in range(npanels)) + 14.0 * (npanels - 1)
        scale = min(1.0, aw / w, ah / h)
        # if the height is the binding constraint, an unsplit variant may be better: try each variant set uniformly
        for split, font in VARIANT_ORDER:
            ws = max(size(pi, split, font)[0] for pi in range(npanels))
            hs = sum(size(pi, split, font)[1] for pi in range(npanels)) + 14.0 * (npanels - 1)
            sc = min(1.0, aw / ws, ah / hs)
            if sc > scale + 1e-6:
                scale, chosen = sc, [(split, font)] * npanels
        cand = (scale, orient == "portrait", chosen, orient)
        if best is None or cand[0] > best[0] + 1e-6 or (abs(cand[0] - best[0]) <= 1e-6 and cand[1]):
            best = cand
    scale, _, chosen, orient = best
    if scale < 0.75:
        print("NOTE: table %s scaled to %.2f (%s)" % (ident, scale, orient))
    return chosen, orient == "rotate", scale


def strip_period(t):
    t = t.strip()
    return t[:-1] if t.endswith(".") else t


def table_tex(ident, title, notes, panels, label):
    """panels: list of (panel_title or None, rows). Springer/threeparttable layout: one outer tabular holds the
    panels (and any \\resizebox), so that the class measures a single table width for the caption and the notes."""
    if not MEASURED:
        for pi, (pt, rows) in enumerate(panels):
            PANEL_REGISTRY.append((ident, pi, rows))
        return "%%TABLE %s" % ident
    variants, rotate, scale = choose_layout(ident, len(panels), title, notes)
    built = []
    for pi, (pt, rows) in enumerate(panels):
        split, font = variants[pi]
        lines, transpose = tabular_tex(rows, split, font)
        built.append((pt, lines, font))
    env = "sidewaystable" if rotate else "table"
    lines = ["\\begin{%s}[htbp]" % env]
    lines.append("\\caption{%s}\\label{%s}" % (inline(strip_period(title)), label))
    lines.append("\\begin{tabular}{@{}c@{}}")
    for n, (pt, plines, font) in enumerate(built):
        if n > 0:
            lines.append("\\\\[6pt]")
        if pt:
            lines.append("\\multicolumn{1}{@{}l@{}}{%s\\emph{%s}} \\\\[2pt]" % (FONT_CMD[font], inline(pt)))
        if scale < 0.999:
            lines.append("\\scalebox{%.3f}{%%" % scale)
        lines.extend(plines)
        if scale < 0.999:
            lines.append("}")
        if n < len(built) - 1:
            lines.append("\\\\")
    lines.append("\\end{tabular}")
    if notes:
        lines.append("\\footnotetext{%s}" % inline(notes))
    lines.append("\\end{%s}" % env)
    return "\n".join(lines)


def figure_tex(ident, title, notes, path, label):
    src = os.path.join(SRC_DIR, path)
    fname = os.path.basename(path)
    os.makedirs(os.path.join(OUT_DIR, "figures"), exist_ok=True)
    if os.path.exists(src):
        shutil.copy(src, os.path.join(OUT_DIR, "figures", fname))
    cap = inline(strip_period(title))
    if notes:
        cap += ". " + inline(notes)
    return "\n".join([
        "\\begin{figure}[htbp]",
        "\\centering",
        "\\includegraphics[width=\\textwidth,height=0.45\\textheight,keepaspectratio]{figures/%s}" % fname,
        "\\caption{%s}\\label{%s}" % (cap, label),
        "\\end{figure}",
    ])


# --------------------------------------------------------------------------------------
# document assembly
# --------------------------------------------------------------------------------------
CAP_RE = re.compile(r"^\*\*(Table|Figure) ([A-Z]?\d+b?)\. (.*?)\*\*\s*(.*)$")


def split_caption(line):
    m = CAP_RE.match(line)
    if not m:
        return None
    kind, ident, title, notes = m.groups()
    return kind, ident, title.strip(), notes.strip()


def first_pass(lines):
    for l in lines:
        m = re.match(r"^## (\d+)\. ", l)
        if m:
            LABELS.add("sec:%s" % m.group(1))
        m = re.match(r"^### (\d+\.\d+) ", l)
        if m:
            LABELS.add("sec:%s" % m.group(1))
        m = re.match(r"^## Appendix ([A-Z])\. ", l)
        if m:
            LABELS.add("app:%s" % m.group(1))
        c = split_caption(l)
        if c:
            LABELS.add(("tab:" if c[0] == "Table" else "fig:") + c[1])


def build(md):
    lines = md.split("\n")
    first_pass(lines)
    title = lines[0].lstrip("# ").strip()
    body = []
    abstract = []
    keywords = ""
    jel = ""
    in_abstract = False
    in_refs = False
    in_decl = False
    appendix_started = False
    i = 1
    pending_caption = None
    list_open = False

    def close_list():
        nonlocal list_open
        if list_open:
            body.append("\\end{itemize}")
            list_open = False

    while i < len(lines):
        l = lines[i]
        if l.startswith("## Abstract"):
            in_abstract = True
            i += 1
            continue
        if l.startswith("**Keywords:**"):
            keywords = l.replace("**Keywords:**", "").strip()
            in_abstract = False
            i += 1
            continue
        if l.startswith("**JEL classification:**"):
            jel = l.replace("**JEL classification:**", "").strip()
            i += 1
            continue
        if l.startswith("## Statements and Declarations"):
            close_list()
            in_decl = True
            body.append("\\backmatter")
            body.append("\\section*{Declarations}")
            i += 1
            continue
        if in_decl and re.match(r"^\*\*[^*]+\.\*\* ", l):
            m = re.match(r"^\*\*([^*]+)\.\*\* (.*)$", l)
            body.append("\\bmhead{%s}" % inline(m.group(1)))
            body.append(inline(m.group(2).strip()))
            i += 1
            continue
        if in_abstract:
            if l.strip():
                abstract.append(inline(l.strip()))
            i += 1
            continue
        if l.startswith("## References"):
            in_refs = True
            in_decl = False
            i += 1
            continue
        if l.startswith("## Appendix "):
            in_refs = False
            close_list()
            m = re.match(r"^## Appendix ([A-Z])\. (.*)$", l)
            if not appendix_started:
                body.append("\\begin{appendices}")
                appendix_started = True
            body.append("\\section{%s}\\label{app:%s}" % (inline(m.group(2).strip()), m.group(1)))
            body.append("\\setcounter{table}{0}\\setcounter{figure}{0}")
            i += 1
            continue
        if in_refs:
            i += 1
            continue
        if l.startswith("## "):
            close_list()
            m = re.match(r"^## (\d+)\. (.*)$", l)
            body.append("\\section{%s}\\label{sec:%s}" % (inline(m.group(2).strip()), m.group(1)))
            i += 1
            continue
        if l.startswith("### "):
            close_list()
            m = re.match(r"^### (\d+\.\d+) (.*)$", l)
            body.append("\\subsection{%s}\\label{sec:%s}" % (inline(m.group(2).strip()), m.group(1)))
            i += 1
            continue
        if l.startswith("*") and l.endswith("*") and ("Anonymous submission" in l or "Submission to Digital Finance" in l):
            i += 1
            continue
        cap = split_caption(l)
        if cap:
            close_list()
            pending_caption = cap
            i += 1
            continue
        italic_only = re.fullmatch(r"\*[^*]+\*", l.strip())
        if (l.startswith("|") or (italic_only and pending_caption)):
            panels = []
            while True:
                ptitle = None
                if i < len(lines) and re.fullmatch(r"\*[^*]+\*", lines[i].strip()):
                    ptitle = lines[i].strip()[1:-1]
                    i += 1
                    while i < len(lines) and not lines[i].strip():
                        i += 1
                rows = []
                while i < len(lines) and lines[i].startswith("|"):
                    rows.append(lines[i])
                    i += 1
                if rows:
                    panels.append((ptitle, rows))
                # look ahead: blank lines, then an italic-only line followed by a table?
                j = i
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines) and re.fullmatch(r"\*[^*]+\*", lines[j].strip()):
                    k2 = j + 1
                    while k2 < len(lines) and not lines[k2].strip():
                        k2 += 1
                    if k2 < len(lines) and lines[k2].startswith("|"):
                        i = j
                        continue
                break
            if pending_caption and pending_caption[0] == "Table":
                kind, ident, ttl, notes = pending_caption
                body.append(table_tex(ident, ttl, notes, panels, "tab:%s" % ident))
                pending_caption = None
            else:
                print("WARNING: table without caption near line", i)
                body.append(table_tex("?", "Untitled", "", panels, "tab:x%d" % i))
            continue
        m = re.match(r"^!\[[^\]]*\]\(([^)]+)\)", l)
        if m:
            if pending_caption and pending_caption[0] == "Figure":
                kind, ident, ttl, notes = pending_caption
                body.append(figure_tex(ident, ttl, notes, m.group(1), "fig:%s" % ident))
                pending_caption = None
            i += 1
            continue
        if l.startswith("- "):
            if not list_open:
                body.append("\\begin{itemize}")
                list_open = True
            body.append("\\item " + inline(l[2:].strip()))
            i += 1
            continue
        if not l.strip():
            close_list()
            body.append("")
            i += 1
            continue
        if l.strip() in DISPLAY:
            body.append(DISPLAY[l.strip()])
            i += 1
            continue
        body.append(inline(l.strip()))
        i += 1
    close_list()
    if appendix_started:
        body.append("\\end{appendices}")
    if pending_caption:
        print("WARNING: dangling caption", pending_caption[:2])
    return title, abstract, keywords, jel, body


PREAMBLE_HEAD = r"""\documentclass[pdflatex,sn-apa]{sn-jnl}
\usepackage{graphicx}\usepackage{multirow}\usepackage{amsmath,amssymb,amsfonts}\usepackage{amsthm}
\usepackage[title]{appendix}\usepackage{xcolor}\usepackage{textcomp}\usepackage{manyfoot}\usepackage{booktabs}\usepackage{array}
\newcommand{\mcell}[2][c]{\begin{tabular}[t]{@{}#1@{}}#2\end{tabular}}
\raggedbottom
\title{m}\author*[1]{\fnm{A} \sur{B}}\affil*[1]{\orgname{I}}\abstract{a}\keywords{k}
"""

PREAMBLE = r"""\documentclass[pdflatex,sn-apa]{sn-jnl}
\usepackage{graphicx}\usepackage{multirow}\usepackage{amsmath,amssymb,amsfonts}\usepackage{amsthm}
\usepackage[title]{appendix}\usepackage{xcolor}\usepackage{textcomp}\usepackage{manyfoot}\usepackage{booktabs}\usepackage{array}
\newcommand{\mcell}[2][c]{\begin{tabular}[t]{@{}#1@{}}#2\end{tabular}}
\renewcommand\topfraction{.95}\renewcommand\bottomfraction{.5}\renewcommand\textfraction{.05}\renewcommand\floatpagefraction{.8}
\setcounter{totalnumber}{4}\setcounter{topnumber}{3}
\raggedbottom

\begin{document}

\title[%(short)s]{%(title)s}

\author*[1]{\fnm{%(given)s} \sur{%(family)s}}\email{%(email)s}
\affil*[1]{%(affil)s}

\abstract{%(abstract)s}

\keywords{%(keywords)s}

\pacs[JEL Classification]{%(jel)s}

\maketitle
"""


def main():
    md = open(SRC, encoding="utf-8").read()
    os.makedirs(OUT_DIR, exist_ok=True)
    build(md)                 # pass 1: register tables
    measure_widths()          # typeset the variants once, read back their widths
    _PH.clear(); LABELS.clear()
    title, abstract, keywords, jel, body = build(md)   # pass 2: final layout
    tex = PREAMBLE % {"short": SHORT_TITLE, "title": inline(title), "given": AUTHOR["given"], "family": AUTHOR["family"],
                      "email": AUTHOR["email"], "affil": AUTHOR["affil"], "abstract": "\n\n".join(abstract),
                      "keywords": inline(keywords).replace(";", ","), "jel": inline(jel)}
    tex += "\n".join(body) + "\n\n\\bibliography{refs}\n\n\\end{document}\n"
    tex = re.sub(r"\n{3,}", "\n\n", tex)
    open(os.path.join(OUT_DIR, "main.tex"), "w", encoding="utf-8").write(tex)
    if UNRESOLVED:
        print("UNRESOLVED CITATIONS:", sorted(set(UNRESOLVED)))
    leftover = re.findall(r"\([^()]*?(?:19|20)\d\d[a-c]?\)", tex)
    print("year-in-parens left:", [x for x in leftover if re.search(r"[A-Z][a-z]+", x)][:20])
    print("wrote", os.path.join(OUT_DIR, "main.tex"), len(tex.split("\n")), "lines")


if __name__ == "__main__":
    main()
