// Minimal Markdown -> DOCX converter for the paper draft (headings, paragraphs, inline bold/italic/code,
// pipe tables, images with captions, bullet lists, references with hanging indent, page numbers).
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell, WidthType,
  ImageRun, Footer, PageNumber, LevelFormat, BorderStyle, ShadingType, TableLayoutType,
} = require("docx");

const SRC = process.argv[2] || "paper_draft_v1.md";
const OUT = process.argv[3] || "paper_draft_v1.docx";
const BASE = path.dirname(path.resolve(SRC));
const PAGE_W = 12240, MARGIN = 1080;               // US Letter, 0.75" margins
const USABLE = PAGE_W - 2 * MARGIN;                 // 10080 DXA = 7.0"
const FONT = "Times New Roman";

function pngSize(buf) {
  return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) };
}

// ---------- inline markdown -> TextRuns
// Escapes: "\*" and "\_" stand for literal characters. Subscript "~x~" and superscript "^x^" (pandoc style).
// Straight quotes become typographic quotes outside code spans.
const ESC = { "*": "\uE000", "_": "\uE001", "~": "\uE002", "^": "\uE003" };
const UNESC = s => s.replace(/\uE000/g, "*").replace(/\uE001/g, "_").replace(/\uE002/g, "~").replace(/\uE003/g, "^");
function smartQuotes(s) {
  return s
    .replace(/(^|[\s(\[—–-])"/g, "$1\u201C")   // opening double quote
    .replace(/"/g, "\u201D")                     // closing double quote
    .replace(/(^|[\s(\[—–-])'(?=\S)/g, "$1\u2018")   // opening single quote
    .replace(/'/g, "\u2019");                    // apostrophe / closing single quote
}
function inline(text, base = {}) {
  text = text.replace(/\\([*_~^])/g, (m, c) => ESC[c]);
  const runs = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|~[^~\s]+~|\^[^^\s]+\^)/g;
  let last = 0, m;
  const plain = (s) => new TextRun({ text: UNESC(smartQuotes(s)), ...base });
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) runs.push(plain(text.slice(last, m.index)));
    const tok = m[0];
    if (tok.startsWith("**")) runs.push(new TextRun({ text: UNESC(smartQuotes(tok.slice(2, -2))), bold: true, ...base }));
    else if (tok.startsWith("`")) runs.push(new TextRun({ text: UNESC(tok.slice(1, -1)), font: "Consolas", ...base }));
    else if (tok.startsWith("~")) runs.push(new TextRun({ text: UNESC(tok.slice(1, -1)), subScript: true, ...base }));
    else if (tok.startsWith("^")) runs.push(new TextRun({ text: UNESC(tok.slice(1, -1)), superScript: true, ...base }));
    else runs.push(new TextRun({ text: UNESC(smartQuotes(tok.slice(1, -1))), italics: true, ...base }));
    last = m.index + tok.length;
  }
  if (last < text.length) runs.push(plain(text.slice(last)));
  return runs;
}

function para(text, opts = {}) {
  return new Paragraph({ children: inline(text, opts.run || {}), spacing: { after: 120, line: 276 }, alignment: AlignmentType.JUSTIFIED, ...opts.p });
}

// ---------- tables
function makeTable(lines) {
  const rows = lines.filter(l => !/^\|\s*:?-+/.test(l)).map(l => l.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim()));
  const ncol = Math.max(...rows.map(r => r.length));
  const size = ncol <= 6 ? 17 : ncol <= 9 ? 15 : ncol <= 12 ? 13 : 12;   // half-points
  // content-proportional widths: longest token per column (headers can wrap), clipped
  const need = Array(ncol).fill(0).map((_, j) => {
    let m = 0;
    rows.forEach((r, i) => {
      const cell = (r[j] || "").replace(/\*/g, "");
      const len = i === 0 ? Math.max(...cell.split(/\s+/).map(t => t.length), Math.ceil(cell.length / 2)) : cell.length;
      m = Math.max(m, len);
    });
    return Math.min(Math.max(m, 5), 34) + 3;   // +3: cell padding so short columns (fork names, windows) do not wrap
  });
  const total = need.reduce((a, b) => a + b, 0);
  const widths = need.map(n => Math.floor(USABLE * n / total));
  widths[ncol - 1] += USABLE - widths.reduce((a, b) => a + b, 0);
  const border = { style: BorderStyle.SINGLE, size: 4, color: "999999" };
  const none = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
  const trows = rows.map((r, i) => new TableRow({
    tableHeader: i === 0,
    children: widths.map((w, j) => new TableCell({
      width: { size: w, type: WidthType.DXA },
      borders: { top: i === 0 ? border : none, bottom: i === 0 || i === rows.length - 1 ? border : none, left: none, right: none },
      shading: i === 0 ? { type: ShadingType.CLEAR, fill: "F2F2F2", color: "auto" } : undefined,
      margins: { top: 30, bottom: 30, left: 50, right: 50 },
      children: [new Paragraph({
        children: inline(r[j] || "", { size, bold: i === 0 }),
        alignment: j === 0 ? AlignmentType.LEFT : AlignmentType.CENTER, spacing: { after: 0, line: 240 },
      })],
    })),
  }));
  return new Table({ rows: trows, columnWidths: widths, width: { size: USABLE, type: WidthType.DXA }, layout: TableLayoutType.FIXED });
}

// ---------- images
function makeImage(rel) {
  const file = path.resolve(BASE, rel);
  const buf = fs.readFileSync(file);
  const { w, h } = pngSize(buf);
  let widthIn = 7.0, heightIn = widthIn * h / w;
  if (heightIn > 8.2) { heightIn = 8.2; widthIn = heightIn * w / h; }   // keep a tall figure on one page with its caption
  return new Paragraph({
    children: [new ImageRun({ type: "png", data: buf, transformation: { width: Math.round(widthIn * 96), height: Math.round(heightIn * 96) } })],
    alignment: AlignmentType.CENTER, spacing: { before: 120, after: 120 },
  });
}

// ---------- parse
const lines = fs.readFileSync(SRC, "utf8").split("\n");
const children = [];
let i = 0, inRefs = false;
while (i < lines.length) {
  const line = lines[i];
  if (line.startsWith("# ")) {
    children.push(new Paragraph({ children: [new TextRun({ text: line.slice(2), bold: true, size: 34 })], alignment: AlignmentType.CENTER, spacing: { after: 200 } }));
    i++; continue;
  }
  if (line.startsWith("## ")) {
    const t = line.slice(3);
    inRefs = t.trim() === "References";
    children.push(new Paragraph({ children: [new TextRun({ text: t, bold: true, size: 26, color: "000000" })], heading: HeadingLevel.HEADING_1, spacing: { before: 280, after: 120 } }));
    i++; continue;
  }
  if (line.startsWith("### ")) {
    children.push(new Paragraph({ children: [new TextRun({ text: line.slice(4), bold: true, italics: true, size: 23, color: "000000" })], heading: HeadingLevel.HEADING_2, spacing: { before: 200, after: 100 } }));
    i++; continue;
  }
  if (line.startsWith("|")) {
    const block = [];
    while (i < lines.length && lines[i].startsWith("|")) block.push(lines[i++]);
    children.push(makeTable(block));
    children.push(new Paragraph({ text: "", spacing: { after: 120 } }));
    continue;
  }
  const img = line.match(/^!\[[^\]]*\]\(([^)]+)\)/);
  if (img) { children.push(makeImage(img[1])); i++; continue; }
  if (line.startsWith("- ")) {
    while (i < lines.length && lines[i].startsWith("- ")) {
      children.push(new Paragraph({ children: inline(lines[i].slice(2)), numbering: { reference: "bullets", level: 0 }, spacing: { after: 60, line: 264 }, alignment: AlignmentType.JUSTIFIED }));
      i++;
    }
    continue;
  }
  if (line.trim() === "<<<pagebreak>>>") { children.push(new Paragraph({ children: [], pageBreakBefore: true })); i++; continue; }
  if (line.trim() === "") { i++; continue; }
  // paragraph (possibly multi-line)
  let text = line;
  while (i + 1 < lines.length && lines[i + 1].trim() !== "" && !/^(#|\||!\[|- )/.test(lines[i + 1])) { text += " " + lines[++i]; }
  if (/^\*Anonymous/.test(text)) {
    children.push(new Paragraph({ children: inline(text), alignment: AlignmentType.CENTER, spacing: { after: 240 } }));
  } else if (/^\*\*(Supplementary )?(Table|Figure) [A-Z]?\d+\./.test(text)) {
    children.push(new Paragraph({ children: inline(text, { size: 19 }), spacing: { before: 120, after: 80 }, alignment: AlignmentType.JUSTIFIED, keepNext: true, keepLines: true }));
  } else if (inRefs) {
    children.push(new Paragraph({ children: inline(text, { size: 19 }), indent: { left: 400, hanging: 400 }, spacing: { after: 80, line: 240 } }));
  } else if (/^log y[_~]pt/.test(text)) {
    children.push(new Paragraph({ children: inline(text, { italics: true }), alignment: AlignmentType.CENTER, spacing: { before: 80, after: 160 } }));
  } else {
    children.push(para(text));
  }
  i++;
}

const doc = new Document({
  styles: { default: { document: { run: { font: FONT, size: 21 } } } },
  numbering: { config: [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: PAGE_W, height: 15840 }, margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], size: 18 })] })] }) },
    children,
  }],
});
Packer.toBuffer(doc).then(buf => { fs.writeFileSync(OUT, buf); console.log("written", OUT, buf.length, "bytes"); });
