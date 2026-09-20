#!/usr/bin/env python3
"""build_srep.py — Scientific Reports version of the manuscript from srep_v1.md.

  * numbers the [@key; @key] citations in order of first appearance and replaces them by [n,m];
  * formats the reference list from sn/refs.bib in Nature style (numbered, "&" before the last author,
    journal in italics, volume bold);
  * counts the words of Introduction + Results + Discussion (prose only; captions, tables and figure lines
    excluded) and of the abstract;
  * writes srep_v1_numbered.md and builds srep_v1.docx with md2docx.js.
"""
import os
import re
import subprocess

import bibtexparser

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "srep_v1.md")
OUT_MD = os.path.join(HERE, "srep_v1_numbered.md")
BIB = os.path.join(HERE, "sn", "refs.bib")

md = open(SRC, encoding="utf-8").read()

# ---- citations -> numbers (order of first appearance)
order = []
def repl(m):
    keys = [k.strip().lstrip("@") for k in m.group(1).split(";")]
    nums = []
    for k in keys:
        if k not in order:
            order.append(k)
        nums.append(order.index(k) + 1)
    nums = sorted(set(nums))
    # compress runs: 1,2,3 -> 1–3
    parts, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        parts.append(str(nums[i]) if j == i else f"{nums[i]}–{nums[j]}" if j > i + 1 else f"{nums[i]},{nums[j]}")
        i = j + 1
    return "[" + ",".join(parts) + "]"
md = re.sub(r"\[(@[^\]]+)\]", repl, md)

# ---- reference list in Nature style
lib = bibtexparser.parse_file(BIB)
entries = {e.key: e for e in lib.entries}

def clean(s):
    s = s.replace('{\\"O}', "Ö").replace('\\"O', "Ö").replace('{\\"o}', "ö").replace('\\"o', "ö").replace("{\\'e}", "é").replace("\\'e", "é")
    s = s.replace("{", "").replace("}", "").replace("\\&", "&").replace("--", "–").replace("\\url", "").replace("\\ ", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def initials(name):
    # "C. C. Moallemi" or "Moallemi, C. C." -> "Moallemi, C. C."
    name = clean(name)
    if "," in name:
        last, first = [x.strip() for x in name.split(",", 1)]
    else:
        parts = name.split()
        last, first = parts[-1], " ".join(parts[:-1])
    ini = " ".join(p[0] + "." for p in re.split(r"[\s.]+", first) if p)
    return f"{last}, {ini}" if ini else last

def authors(e):
    raw = clean(e.fields_dict["author"].value) if "author" in e.fields_dict else ""
    names = [n.strip() for n in re.split(r"\s+and\s+", raw) if n.strip()]
    if len(names) == 1 and names[0] in ("BNB Chain",):
        return names[0] + "."
    fmt = [initials(n) for n in names]
    if len(fmt) > 6:
        return fmt[0] + " et al."
    if len(fmt) == 1:
        return fmt[0]
    return ", ".join(fmt[:-1]) + " & " + fmt[-1]

def field(e, k):
    return clean(e.fields_dict[k].value) if k in e.fields_dict else ""

JABBR = {"Journal of Finance": "J. Finance", "Review of Financial Studies": "Rev. Financ. Stud.", "Management Science": "Manage. Sci.",
         "Journal of Futures Markets": "J. Futures Mark.", "Journal of the Royal Statistical Society: Series B": "J. R. Stat. Soc. B",
         "Proceedings of the ACM on Measurement and Analysis of Computing Systems": "Proc. ACM Meas. Anal. Comput. Syst.",
         "Quarterly Journal of Economics": "Q. J. Econ.", "Journal of Financial Economics": "J. Financ. Econ.",
         "Mathematical Finance": "Math. Finance", "SIAM Journal on Financial Mathematics": "SIAM J. Financ. Math."}


def fmt_entry(e):
    t = e.entry_type.lower()
    title = field(e, "title")
    year = field(e, "year")
    a = authors(e)
    if t == "article":
        j, v, p = field(e, "journal"), field(e, "volume"), field(e, "pages")
        j = JABBR.get(j, j)
        s = f"{a} {title}. *{j}*"
        if v:
            s += f" **{v}**"
        if p:
            s += f", {p}"
        elif field(e, "note"):
            s += f", {field(e, 'note').lower()}"
        s += f" ({year})."
        doi = field(e, "doi")
        if doi and not p:
            s += f" https://doi.org/{doi}"
        return s
    if t == "inproceedings":
        bt, ed, pg, pub = field(e, "booktitle"), field(e, "editor"), field(e, "pages"), field(e, "publisher")
        s = f"{a} {title}" + ("" if title.endswith("?") else ".") + f" In *{bt}*"
        if ed:
            eds = [initials(n) for n in re.split(r"\s+and\s+", ed)]
            s += " (eds " + (", ".join(eds[:-1]) + " & " + eds[-1] if len(eds) > 1 else eds[0]) + ")"
        if pg:
            s += f" {pg}"
        s += f" ({pub}, {year})." if pub else f" ({year})."
        return s
    # misc: working papers, blog posts, BEPs
    how, url, note = field(e, "howpublished"), field(e, "url"), field(e, "note")
    s = f"{a} {title}" + ("" if title.endswith("?") else ".")
    if "arxiv" in (how + url + note).lower():
        m = re.search(r"arXiv:?\s*(\d{4}\.\d{4,5})", how + " " + note + " " + url)
        s += f" Preprint at https://arxiv.org/abs/{m.group(1)}" if m else f" Preprint, {how}"
        s += f" ({year})."
    elif "ssrn" in (how + url).lower():
        s += f" {how}" if how else ""
        s += f" {url} ({year})." if url else f" ({year})."
    else:
        s += f" {how}." if how else ""
        s += f" {url} ({year})." if url else f" ({year})."
    return s.replace("..", ".")

refs = "\n\n".join(f"{i + 1}. {fmt_entry(entries[k])}" for i, k in enumerate(order))
md = md.replace("[[REFERENCES]]", refs)
open(OUT_MD, "w", encoding="utf-8").write(md)          # review layout: tables, legends and figures inline


def submission_layout(md):
    """Scientific Reports order: main text, References, Acknowledgements, Author contributions, Data availability,
    Code availability, Competing interests, Additional information, Figure legends, Tables (figures as separate files)."""
    paras = md.split("\n\n")
    kept, tables, legends = [], [], []
    i = 0
    while i < len(paras):
        p = paras[i].strip()
        if p.startswith("**Table "):
            blk = [p]
            i += 1
            while i < len(paras) and (paras[i].strip().startswith("|") or paras[i].strip().startswith("*Panel")):
                blk.append(paras[i].strip()); i += 1
            tables.append("\n\n".join(blk))
            continue
        if p.startswith("**Figure "):
            legends.append(p); i += 1
            if i < len(paras) and paras[i].strip().startswith("!["):
                i += 1
            continue
        if p.startswith("!["):
            i += 1; continue
        kept.append(paras[i]); i += 1
    out = "\n\n".join(kept).rstrip() + "\n\n## Figure legends\n\n" + "\n\n".join(legends) + "\n\n## Tables\n\n" + "\n\n".join(tables) + "\n"
    return out


sub = submission_layout(md)
open(os.path.join(HERE, "srep_v1_submission.md"), "w", encoding="utf-8").write(sub)

# ---- word counts
def section(md, start, end):
    i = md.index(start)
    j = md.index(end, i + 1)
    return md[i:j]

def prose_words(txt):
    out = []
    for para in txt.split("\n\n"):
        p = para.strip()
        if not p or p.startswith("|") or p.startswith("![") or p.startswith("**Table") or p.startswith("**Figure") or p.startswith("*Panel") or p.startswith("#"):
            continue
        out.append(p)
    return len(" ".join(out).split())

body = prose_words(section(md, "## Introduction", "## Methods"))
abstract = len(section(md, "## Abstract", "## Introduction").split("\n\n")[1].split())
methods = prose_words(section(md, "## Methods", "## References"))
n_tables = md.count("**Table ")
n_figs = md.count("**Figure ")
title = md.split("\n")[0].lstrip("# ").strip()
print(f"title words: {len(title.split())}; abstract: {abstract}; Intro+Results+Discussion: {body}; Methods: {methods}; display items: {n_tables} tables + {n_figs} figures; references: {len(order)}")

subprocess.run(["node", os.path.join(HERE, "md2docx.js"), OUT_MD, os.path.join(HERE, "srep_v1_review.docx")], check=True, cwd=HERE)
subprocess.run(["node", os.path.join(HERE, "md2docx.js"), os.path.join(HERE, "srep_v1_submission.md"), os.path.join(HERE, "srep_v1.docx")], check=True, cwd=HERE)
