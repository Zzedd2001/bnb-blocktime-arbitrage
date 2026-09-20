#!/bin/bash
# build main.pdf (pdflatex + bibtex); prints errors, page count and the largest overfull boxes
cd "$(dirname "$0")"
pdflatex -interaction=nonstopmode -halt-on-error main.tex > build1.log 2>&1 || { grep -n '^!' -A8 build1.log | head -40; exit 1; }
bibtex main > bib.log 2>&1
pdflatex -interaction=nonstopmode -halt-on-error main.tex > build2.log 2>&1
pdflatex -interaction=nonstopmode -halt-on-error main.tex > build3.log 2>&1 || { grep -n '^!' -A8 build3.log | head -40; exit 1; }
grep -i 'warning.*undefined\|multiply defined' build3.log | head -5
grep -i 'warning\|error' bib.log | head -5
echo "overfull hboxes: $(grep -c 'Overfull \\hbox' build3.log)"
grep 'Overfull \\hbox' build3.log | sort -t'(' -k2 -rn | head -6
tail -2 build3.log | head -1
