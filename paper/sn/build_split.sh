#!/bin/bash
# build main_body.pdf (article without appendices) and supplement.pdf (Appendices A-E) from main.tex
cd "$(dirname "$0")"
python3 "$(dirname "$0")/../sn/split_supplement.py" . 2>/dev/null || python3 ../sn/split_supplement.py .
for f in main_body supplement; do
  pdflatex -interaction=nonstopmode -halt-on-error $f.tex > ${f}_1.log 2>&1 || { grep -n '^!' -A8 ${f}_1.log | head -30; exit 1; }
  bibtex $f > ${f}_bib.log 2>&1
  pdflatex -interaction=nonstopmode -halt-on-error $f.tex > ${f}_2.log 2>&1
  pdflatex -interaction=nonstopmode -halt-on-error $f.tex > ${f}_3.log 2>&1 || { grep -n '^!' -A8 ${f}_3.log | head -30; exit 1; }
  echo "$f: $(grep -ci 'warning.*undefined' ${f}_3.log) undefined-reference warnings; $(tail -2 ${f}_3.log | head -1)"
done
