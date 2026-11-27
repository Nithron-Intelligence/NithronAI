// Markdown for answers and chat replies, rendered as type (DESIGN-APPS.md, "Reading").
//
// renderMarkdown(raw) escapes the text itself, so callers pass the model's text as it came. It knows the subset
// answers use: paragraphs, headings, lists, quotations, rules, fenced code (comments, strings and numbers in the
// syntax palette), pipe tables, inline code, bold,
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

// Code in answers: a small, language-blind scanner (no third-party highlighter, no keyword lists). It colours only
// comments, strings and numbers with the tokens' syntax palette. The fence's language picks the comment marks;
// a language that is not listed stays plain, because a wrong colour is worse than none.
const CODE_FAMILIES = {
  hash: { line: ['#'], block: null, quotes: ['"', "'"] },
  yaml: { line: ['#'], block: null, quotes: ['"'] },
  slash: { line: ['//'], block: ['/*', '*/'], quotes: ['"', "'", '`'] },
  rust: { line: ['//'], block: ['/*', '*/'], quotes: ['"'] }, // ' starts lifetimes as well as characters
  css: { line: [], block: ['/*', '*/'], quotes: ['"', "'"] },
  dash: { line: ['--'], block: null, quotes: ["'", '"'] },
  data: { line: [], block: null, quotes: ['"'] }, // untagged, text, logs, JSON: apostrophes are prose
};
const CODE_LANGUAGES = {
  '': 'data', text: 'data', txt: 'data', plain: 'data', log: 'data', json: 'data',
  python: 'hash', py: 'hash', sh: 'hash', bash: 'hash', shell: 'hash', zsh: 'hash', console: 'hash',
  ruby: 'hash', rb: 'hash', perl: 'hash', r: 'hash', toml: 'hash', dockerfile: 'hash', makefile: 'hash',
  powershell: 'hash', ps1: 'hash', conf: 'hash',
  yaml: 'yaml', yml: 'yaml',
  javascript: 'slash', js: 'slash', jsx: 'slash', typescript: 'slash', ts: 'slash', tsx: 'slash', json5: 'slash',
  java: 'slash', c: 'slash', h: 'slash', cpp: 'slash', 'c++': 'slash', cs: 'slash', csharp: 'slash', go: 'slash',
  kotlin: 'slash', kt: 'slash', swift: 'slash', php: 'slash', scala: 'slash', dart: 'slash', scss: 'slash',
  less: 'slash',
  rust: 'rust', rs: 'rust',
  css: 'css',
  sql: 'dash', lua: 'dash', haskell: 'dash', hs: 'dash',
};
const CODE_NUMBER = /^(?:0x[0-9a-fA-F]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/;

function codeSpan(kind, text) {
  return `<span class="tok-${kind}">${escapeMarkdownHtml(text)}</span>`;
}

/** Highlighted HTML for a fenced block, or null when its language is not one the scanner can read safely. */
function scanCode(code, language) {
  const family = CODE_FAMILIES[CODE_LANGUAGES[language.toLowerCase()]];
  if (!family) return null;
  let html = '';
  let plain = '';
  const flush = () => { html += escapeMarkdownHtml(plain); plain = ''; };
  let i = 0;
  while (i < code.length) {
    const rest = code.slice(i);
    const prev = i === 0 ? '\n' : code[i - 1];
    if (family.block && rest.startsWith(family.block[0])) {
      const end = code.indexOf(family.block[1], i + family.block[0].length);
      const stop = end === -1 ? code.length : end + family.block[1].length;
      flush(); html += codeSpan('comment', code.slice(i, stop)); i = stop; continue;
    }
    const lineMark = family.line.find((mark) => rest.startsWith(mark));
    if (lineMark && /\s/.test(prev)) {
      const end = code.indexOf('\n', i);
      const stop = end === -1 ? code.length : end;
      flush(); html += codeSpan('comment', code.slice(i, stop)); i = stop; continue;
    }
    const quote = family.quotes.find((q) => rest[0] === q);
    if (quote && !/[\w]/.test(prev)) {
      let j = i + 1;
      while (j < code.length && code[j] !== quote && (quote === '`' || code[j] !== '\n')) j += code[j] === '\\' ? 2 : 1;
      if (j < code.length && code[j] === quote) {
        flush(); html += codeSpan('string', code.slice(i, j + 1)); i = j + 1; continue;
      }
    }
    const number = !/[\w.]/.test(prev) && rest.match(CODE_NUMBER);
    if (number && !/[\w]/.test(code[i + number[0].length] || '')) {
      flush(); html += codeSpan('number', number[0]); i += number[0].length; continue;
    }
    plain += code[i];
    i += 1;
  }
  flush();
  return html;
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
      const language = (line.match(/^\s{0,3}```\s*([\w+#.-]*)/) || ['', ''])[1];
      const code = [];
      i += 1;
      while (i < lines.length && !MD_FENCE.test(lines[i])) code.push(lines[i++]);
      i += 1; // closing fence (or the end of a streaming answer)
      const text = code.join('\n');
      html.push(`<pre><code>${scanCode(text, language) ?? escapeMarkdownHtml(text)}</code></pre>`);
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
