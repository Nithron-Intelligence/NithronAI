// Markdown for answers and chat replies, rendered as type (DESIGN-APPS.md, "Reading").
//
// renderMarkdown(raw) escapes the text itself, so callers pass the model's text as it came. It knows the subset
// answers use: paragraphs, headings, lists, quotations, rules, fenced code, pipe tables, inline code, bold,
// italics and links (http and https only). Anything else stays as text.

function escapeMarkdownHtml(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderInline(raw) {
  const codeSpans = [];
  let text = escapeMarkdownHtml(raw).replace(/`([^`]+)`/g, (_, code) => {
    codeSpans.push(code);
    return `\u0000${codeSpans.length - 1}\u0000`;
  });
  text = text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*\w])\*(?!\s)(.+?)\*(?!\w)/g, '$1<em>$2</em>')
    .replace(/(^|[^_\w])_(?!\s)(.+?)_(?!\w)/g, '$1<em>$2</em>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  return text.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codeSpans[Number(i)]}</code>`);
}

const MD_RULE = /^\s{0,3}([-*_])(\s*\1){2,}\s*$/;
const MD_HEADING = /^\s{0,3}(#{1,4})\s+(.*?)\s*#*\s*$/;
const MD_BULLET = /^\s{0,3}[-*+]\s+(.*)$/;
const MD_NUMBER = /^\s{0,3}\d{1,3}[.)]\s+(.*)$/;
const MD_QUOTE = /^\s{0,3}>\s?(.*)$/;
const MD_FENCE = /^\s{0,3}```/;
const MD_TABLE_ROW = /^\s*\|.*\|\s*$/;
const MD_TABLE_SEPARATOR = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;

function tableCells(line) {
  return line.trim().replace(/^\||\|$/g, '').split('|').map((cell) => renderInline(cell.trim()));
}

function renderMarkdown(raw) {
  const lines = String(raw ?? '').replace(/\r\n?/g, '\n').split('\n');
  const html = [];
  let i = 0;
  const isBlockStart = (line) =>
    MD_RULE.test(line) || MD_HEADING.test(line) || MD_BULLET.test(line) || MD_NUMBER.test(line) ||
    MD_QUOTE.test(line) || MD_FENCE.test(line) || MD_TABLE_ROW.test(line);

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
    } else if (MD_FENCE.test(line)) {
      const code = [];
      i += 1;
      while (i < lines.length && !MD_FENCE.test(lines[i])) code.push(lines[i++]);
      i += 1; // closing fence (or the end of a streaming answer)
      html.push(`<pre><code>${escapeMarkdownHtml(code.join('\n'))}</code></pre>`);
    } else if (MD_RULE.test(line)) {
      html.push('<hr>');
      i += 1;
    } else if (MD_HEADING.test(line)) {
      const [, hashes, title] = line.match(MD_HEADING);
      const level = Math.min(hashes.length + 2, 6); // answers sit under the screen's own headings
      html.push(`<h${level}>${renderInline(title)}</h${level}>`);
      i += 1;
    } else if (MD_QUOTE.test(line)) {
      const quoted = [];
      while (i < lines.length && MD_QUOTE.test(lines[i])) quoted.push(lines[i++].match(MD_QUOTE)[1]);
      html.push(`<blockquote>${renderMarkdown(quoted.join('\n'))}</blockquote>`);
    } else if (MD_BULLET.test(line) || MD_NUMBER.test(line)) {
      const ordered = MD_NUMBER.test(line);
      const pattern = ordered ? MD_NUMBER : MD_BULLET;
      const items = [];
      while (i < lines.length && pattern.test(lines[i])) items.push(renderInline(lines[i++].match(pattern)[1]));
      const tag = ordered ? 'ol' : 'ul';
      html.push(`<${tag}>${items.map((item) => `<li>${item}</li>`).join('')}</${tag}>`);
    } else if (MD_TABLE_ROW.test(line) && i + 1 < lines.length && MD_TABLE_SEPARATOR.test(lines[i + 1])) {
      const head = tableCells(line);
      i += 2;
      const rows = [];
      while (i < lines.length && MD_TABLE_ROW.test(lines[i])) rows.push(tableCells(lines[i++]));
      html.push(
        `<div class="table-wrap"><table class="table"><thead><tr>${head.map((c) => `<th>${c}</th>`).join('')}</tr></thead>` +
        `<tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`,
      );
    } else {
      const paragraph = [];
      while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i])) paragraph.push(lines[i++]);
      if (!paragraph.length) paragraph.push(lines[i++]); // a table row without a separator: plain text
      html.push(`<p>${paragraph.map(renderInline).join('<br>')}</p>`);
    }
  }
  return html.join('');
}
