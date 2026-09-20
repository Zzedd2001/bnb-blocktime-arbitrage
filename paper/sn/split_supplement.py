#!/usr/bin/env python3
"""split_supplement.py — split the single-document main.tex written by md2sn.py into
  main_body.tex   : title page, body, declarations, references (appendices removed; appendix cross-references
                    become literal numbers, e.g. Table~\\ref{tab:B1} -> Table~B1)
  supplement.tex  : "Supplementary Material to ..." with the same author block, Appendices A-E and their references
                    (body cross-references become literal numbers)

    python3 split_supplement.py <build_dir>      (expects <build_dir>/main.tex; writes the two files next to it)
"""
import os
import re
import sys

D = sys.argv[1] if len(sys.argv) > 1 else "."
tex = open(os.path.join(D, "main.tex"), encoding="utf-8").read()

i = tex.index("\\begin{appendices}")
j = tex.index("\\end{appendices}") + len("\\end{appendices}")
appendices = tex[i:j]
body = tex[:i] + tex[j:]

# ---- main body: appendix references -> literal
body = re.sub(r"\\ref\{tab:([A-E]\d+b?)\}", r"\1", body)
body = re.sub(r"\\ref\{fig:([A-E]\d+)\}", r"\1", body)
body = re.sub(r"\\ref\{app:([A-E])\}", r"\1", body)
body = re.sub(r"\n{3,}", "\n\n", body)
open(os.path.join(D, "main_body.tex"), "w", encoding="utf-8").write(body)

# ---- supplement: preamble up to \begin{document}, new title/abstract, appendices, references
pre_end = tex.index("\\begin{document}") + len("\\begin{document}")
preamble = tex[:pre_end]
m_title = re.search(r"\\title\[[^\]]*\]\{(.*)\}\n", tex[pre_end:])
title = m_title.group(1)
author_block = re.search(r"(\\author\*.*?\n\\affil\*.*?\n)", tex[pre_end:], re.S).group(1)
front = ("\n\n\\title[Supplementary Material]{Supplementary Material to ``%s''}\n\n%s\n"
         "\\abstract{This Supplementary Material contains Appendices A--E of the article: descriptive statistics and data validation (A), "
         "the full grid of specifications and additional estimates (B), the reference-price comparison (C), opening times, operators and "
         "simulations (D) and the replication package (E). Table, figure and section numbers without a letter prefix refer to the article.}\n\n"
         "\\maketitle\n\n") % (title, author_block)
supp = appendices
supp = re.sub(r"\\ref\{tab:(\d+)\}", r"\1", supp)
supp = re.sub(r"\\ref\{fig:(\d+)\}", r"\1", supp)
supp = re.sub(r"\\ref\{sec:([\d.]+)\}", r"\1", supp)
bib = "\n\n\\bibliography{refs}" if re.search(r"\\cite[a-z]*\{", supp) else ""   # no reference list when nothing is cited
supp_tex = preamble + front + supp + bib + "\n\n\\end{document}\n"
supp_tex = re.sub(r"\n{3,}", "\n\n", supp_tex)
open(os.path.join(D, "supplement.tex"), "w", encoding="utf-8").write(supp_tex)
print("wrote main_body.tex (%d lines) and supplement.tex (%d lines)" % (body.count("\n"), supp_tex.count("\n")))
