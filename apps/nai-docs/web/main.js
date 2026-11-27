/**
 * nAI web interface: plain JavaScript, no build step. Icons come from icons.js, Markdown from markdown.js and
 * confirmations from dialog.js (loaded before this file).
 */

// =============================================================================
// Configuration & State
// =============================================================================

function storageGet(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

function storageSet(key, value) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch { /* storage unavailable (private mode) */ }
}

function defaultApiBase() {
  // Served by nAI itself (also behind a reverse-proxy prefix such as /apps/nai/): same origin.
  // The dev server on :5173 talks to a backend on :8000.
  if (location.protocol.startsWith('http') && location.port !== '5173') {
    return location.origin + location.pathname.replace(/[^/]*$/, '').replace(/\/$/, '');
  }
  return 'http://localhost:8000';
}

const CONFIG = {
  apiBase: storageGet('nai_api_base') || defaultApiBase(),
  theme: storageGet('nai_theme') || 'system',
};

const AUTH = {
  enabled: false,
  token: storageGet('nai_token'),
  user: null,
  setupMode: false,
};

const STATE = {
  files: [],
  documents: [],
  sources: [],
  apiKeys: [],
  chatConversationId: null,
  isLoading: false,
};

// =============================================================================
// DOM Elements
// =============================================================================

const elements = {
  // Status
  statusIndicator: document.getElementById('statusIndicator'),
  
  // Tabs
  tabs: document.querySelectorAll('.tab'),
  tabPanels: document.querySelectorAll('.tab-panel'),
  
  // Ask
  questionInput: document.getElementById('questionInput'),
  askBtn: document.getElementById('askBtn'),
  useLlm: document.getElementById('useLlm'),
  topK: document.getElementById('topK'),
  resultsArea: document.getElementById('resultsArea'),
  resultMethod: document.getElementById('resultMethod'),
  answerContent: document.getElementById('answerContent'),
  citationsList: document.getElementById('citationsList'),
  
  // Ingest
  uploadZone: document.getElementById('uploadZone'),
  fileInput: document.getElementById('fileInput'),
  browseBtn: document.getElementById('browseBtn'),
  fileList: document.getElementById('fileList'),
  uploadActions: document.getElementById('uploadActions'),
  ingestBtn: document.getElementById('ingestBtn'),
  clearFilesBtn: document.getElementById('clearFilesBtn'),
  ingestResults: document.getElementById('ingestResults'),
  uploadProgress: document.getElementById('uploadProgress'),
  
  // Documents
  documentsStats: document.getElementById('documentsStats'),
  documentsList: document.getElementById('documentsList'),
  refreshDocsBtn: document.getElementById('refreshDocsBtn'),
  
  // Chat
  chatMessages: document.getElementById('chatMessages'),
  chatInput: document.getElementById('chatInput'),
  chatSendBtn: document.getElementById('chatSendBtn'),
  
  // Settings
  settingsBtn: document.getElementById('settingsBtn'),
  settingsModal: document.getElementById('settingsModal'),
  closeSettingsBtn: document.getElementById('closeSettingsBtn'),
  cancelSettingsBtn: document.getElementById('cancelSettingsBtn'),
  saveSettingsBtn: document.getElementById('saveSettingsBtn'),
  apiBaseInput: document.getElementById('apiBaseInput'),
  openaiUrl: document.getElementById('openaiUrl'),
  mcpUrl: document.getElementById('mcpUrl'),
  apiKeysArea: document.getElementById('apiKeysArea'),
  apiKeysList: document.getElementById('apiKeysList'),
  apiKeyName: document.getElementById('apiKeyName'),
  apiKeyCreateBtn: document.getElementById('apiKeyCreateBtn'),
  apiKeyNew: document.getElementById('apiKeyNew'),
  themeSelect: document.getElementById('themeSelect'),
  
  // Chat (new conversation)
  chatNewBtn: document.getElementById('chatNewBtn'),

  // Auth
  userChip: document.getElementById('userChip'),
  userName: document.getElementById('userName'),
  logoutBtn: document.getElementById('logoutBtn'),
  loginModal: document.getElementById('loginModal'),
  loginForm: document.getElementById('loginForm'),
  loginTitle: document.getElementById('loginTitle'),
  loginHint: document.getElementById('loginHint'),
  loginUsername: document.getElementById('loginUsername'),
  loginEmail: document.getElementById('loginEmail'),
  loginEmailGroup: document.getElementById('loginEmailGroup'),
  loginPassword: document.getElementById('loginPassword'),
  loginError: document.getElementById('loginError'),
  loginSubmitBtn: document.getElementById('loginSubmitBtn'),

  // Sources (admin)
  sourcesTab: document.getElementById('sourcesTab'),
  sourcesList: document.getElementById('sourcesList'),
  refreshSourcesBtn: document.getElementById('refreshSourcesBtn'),
  sourceForm: document.getElementById('sourceForm'),
  sourceName: document.getElementById('sourceName'),
  sourcePath: document.getElementById('sourcePath'),
  sourceGroups: document.getElementById('sourceGroups'),
  sourceExclude: document.getElementById('sourceExclude'),
  sourceAddBtn: document.getElementById('sourceAddBtn'),
  sourceRootsHint: document.getElementById('sourceRootsHint'),
  systemInfo: document.getElementById('systemInfo'),
  appVersion: document.getElementById('appVersion'),

  // Toast
  toastContainer: document.getElementById('toastContainer'),
};

// =============================================================================
// Utility Functions
// =============================================================================

// The pixel set's six state icons: ok (pass), warning, failed, running, notice, off.
const STATE_ICONS = { success: 'ok', warning: 'warning', error: 'failed', info: 'notice', off: 'off', running: 'running' };

/** The state icon for a kind of status, coloured by its own class (only ok, warning and failed carry a hue). */
function stateIcon(kind) {
  const name = STATE_ICONS[kind] || 'notice';
  return `<span class="state state-${name}">${icon(name)}</span>`;
}

/** A status as a state icon and a word (the word carries the meaning; the icon only repeats it). */
function statusLabel(kind, word) {
  return `<span class="status">${stateIcon(kind)}${escapeHtml(word)}</span>`;
}

/** A field's error: the failed icon and the sentence. */
function fieldError(element, message) {
  element.innerHTML = `${stateIcon('error')}<span></span>`;
  element.querySelector('span:last-child').textContent = message;
}

function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
  toast.innerHTML = `
    ${stateIcon(type)}
    <span class="toast-text"></span>
    <button class="btn btn-ghost btn-sm" type="button" aria-label="Dismiss">${icon('close')}</button>
  `;
  toast.querySelector('.toast-text').textContent = message;
  toast.querySelector('button').addEventListener('click', () => toast.remove());
  elements.toastContainer.appendChild(toast);
  if (type !== 'error') setTimeout(() => toast.remove(), 5000); // failures stay until dismissed
}

/** "1 chunk", "2 chunks". */
function plural(count, word) {
  return `${count} ${word}${count === 1 ? '' : 's'}`;
}

function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

/** "2026-11-27 22:40" in the reader's own time zone: the same in every locale, never a US-only form. */
function formatDate(isoString) {
  if (!isoString) return 'unknown';
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return 'unknown';
  const two = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${two(date.getMonth() + 1)}-${two(date.getDate())} ${two(date.getHours())}:${two(date.getMinutes())}`;
}

function authHeaders() {
  return AUTH.token ? { Authorization: `Bearer ${AUTH.token}` } : {};
}

function errorDetail(body, status) {
  const detail = body && body.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) return detail.map(d => d.msg).join('; ');
  return `HTTP ${status}`;
}

async function apiCall(endpoint, options = {}) {
  const url = `${CONFIG.apiBase}${endpoint}`;
  const isForm = options.body instanceof FormData;
  const response = await fetch(url, {
    ...options,
    headers: {
      ...(isForm ? {} : { 'Content-Type': 'application/json' }),
      ...authHeaders(),
      ...options.headers,
    },
  });
  
  if (response.status === 401 && AUTH.enabled && !endpoint.startsWith('/auth/login')) {
    setToken(null);
    openLogin();
    throw new Error('Please sign in');
  }
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(errorDetail(error, response.status));
  }
  
  return response.json();
}

/**
 * POST a form with XMLHttpRequest, which (unlike fetch) reports upload progress: onProgress(sent, total).
 */
function uploadWithProgress(endpoint, formData, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${CONFIG.apiBase}${endpoint}`);
    Object.entries(authHeaders()).forEach(([name, value]) => xhr.setRequestHeader(name, value));
    xhr.upload.addEventListener('progress', (e) => { if (e.lengthComputable) onProgress(e.loaded, e.total); });
    xhr.addEventListener('load', () => {
      let body = {};
      try { body = JSON.parse(xhr.responseText); } catch { /* not JSON */ }
      if (xhr.status === 401 && AUTH.enabled) {
        setToken(null);
        openLogin();
        reject(new Error('Please sign in'));
      } else if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body);
      } else {
        reject(new Error(errorDetail(body, xhr.status)));
      }
    });
    xhr.addEventListener('error', () => reject(new Error('the server could not be reached')));
    xhr.send(formData);
  });
}

const METER_BLOCKS = 20;

/** A meter as a row of square blocks that fill one by one (never a smooth bar). */
function meter(fraction, label, role = 'progressbar') {
  const share = Math.max(0, Math.min(1, fraction));
  const filled = Math.round(share * METER_BLOCKS);
  const blocks = Array.from({ length: METER_BLOCKS }, (_, i) => `<span class="block${i < filled ? ' on' : ''}"></span>`).join('');
  return `<span class="meter" role="${role}" aria-label="${escapeHtml(label)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(share * 100)}">${blocks}</span>`;
}

/**
 * POST to a Server-Sent Events endpoint and call onEvent(name, data) per event.
 * (EventSource can't POST or send an Authorization header, so this reads the stream by hand.)
 */
async function streamCall(endpoint, body, onEvent) {
  const response = await fetch(`${CONFIG.apiBase}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (response.status === 401 && AUTH.enabled) {
    setToken(null);
    openLogin();
    throw new Error('Please sign in');
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(errorDetail(error, response.status));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary;
    while ((boundary = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let name = 'message';
      let data = '';
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) name = line.slice(7);
        else if (line.startsWith('data: ')) data += line.slice(6);
      }
      if (data) onEvent(name, JSON.parse(data));
    }
  }
}

/** Open a document's original file (fetched with the auth header, shown in a new tab). */
async function openDocument(docId) {
  const win = window.open('', '_blank'); // open synchronously so popup blockers allow it
  try {
    const response = await fetch(`${CONFIG.apiBase}/documents/${encodeURIComponent(docId)}/file`, {
      headers: authHeaders(),
    });
    if (!response.ok) throw new Error(response.status === 404 ? 'File is no longer available' : `HTTP ${response.status}`);
    const url = URL.createObjectURL(await response.blob());
    if (win) win.location = url;
    else window.location = url;
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (e) {
    if (win) win.close();
    showToast(`Could not open file: ${e.message}`, 'error');
  }
}

function isAdmin() {
  return !AUTH.enabled || Boolean(AUTH.user && AUTH.user.is_admin);
}

/** Where a citation comes from, e.g. "Documents/Insurance/car.pdf · page 3 · Coverage". */
function citationLocation(cit) {
  const path = cit.source_name ? `${cit.source_name}/${cit.doc_path}` : (cit.filename || cit.doc_path);
  const parts = [path];
  if (cit.page !== null && cit.page !== undefined) parts.push(`page ${cit.page}`);
  if (cit.heading) parts.push(cit.heading);
  return parts.join(' · ');
}

const MATCH_STOPWORDS = new Set(['the', 'and', 'for', 'was', 'what', 'when', 'where', 'which', 'who', 'how',
  'does', 'did', 'are', 'is', 'my', 'our', 'der', 'die', 'das', 'und', 'ist', 'wann', 'wie', 'och', 'det', 'att',
  'les', 'des', 'une', 'est', 'que', 'qui', 'para', 'com', 'uma', 'por', 'como', 'quando']);

/** The excerpt, escaped, with the question's words marked. */
function markMatches(text, question) {
  const words = [...new Set((question || '').toLowerCase().match(/[\p{L}\p{N}]{3,}/gu) || [])]
    .filter((w) => !MATCH_STOPWORDS.has(w));
  const escaped = escapeHtml(text);
  if (!words.length) return escaped;
  const pattern = new RegExp(`(?<![\\p{L}\\p{N}&])(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})(?![\\p{L}\\p{N}])`, 'giu');
  return escaped.replace(pattern, '<mark>$1</mark>');
}

function renderCitations(citations, question = '') {
  return citations.map((cit, i) => {
    const excerpt = cit.text.length > 300 ? `${cit.text.slice(0, 300)}…` : cit.text;
    return `
    <li class="citation">
      <span class="citation-rank mono">${i + 1}</span>
      <div class="citation-body">
        <div class="citation-head">
          ${icon('file')}
          <span class="citation-source mono">${escapeHtml(citationLocation(cit))}</span>
          <span class="citation-score mono" title="Relevance score">${Number(cit.score).toFixed(2)}</span>
          <button class="btn btn-secondary btn-sm" type="button" data-open-doc="${escapeHtml(cit.doc_id)}">${icon('external-link')}Open</button>
        </div>
        <p class="citation-text">${markMatches(excerpt, question)}</p>
      </div>
    </li>`;
  }).join('');
}

// One delegated handler for every "Open" button (citations, documents, chat sources)
document.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-open-doc]');
  if (btn) openDocument(btn.dataset.openDoc);
});

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// =============================================================================
// Health Check
// =============================================================================

async function checkHealth() {
  const state = elements.statusIndicator.querySelector('.state');
  const word = elements.statusIndicator.querySelector('.status-text');
  const show = (kind, text) => { state.outerHTML = stateIcon(kind); word.textContent = text; };
  try {
    const data = await apiCall('/health');
    elements.appVersion.textContent = `v${data.version}`;
    show('success', 'Online');
    return true;
  } catch (e) {
    show('error', 'Offline');
    return false;
  }
}

// =============================================================================
// Tab Navigation
// =============================================================================

function switchTab(tabName) {
  elements.tabs.forEach(tab => {
    const current = tab.dataset.tab === tabName;
    tab.classList.toggle('active', current);
    if (current) tab.setAttribute('aria-current', 'page');
    else tab.removeAttribute('aria-current');
  });
  
  elements.tabPanels.forEach(panel => {
    panel.classList.toggle('active', panel.dataset.panel === tabName);
  });
  
  // Load data when switching to certain tabs
  if (tabName === 'documents') {
    loadDocuments();
  } else if (tabName === 'sources') {
    loadSources();
    loadSystemInfo();
  }
}

// The streaming cursor: a block at the end of the text while a reply arrives (still under reduced motion).
const CURSOR = '<span class="cursor" aria-hidden="true"></span>';

/** Put the cursor at the end of the last block of rendered Markdown. */
function withCursor(html) {
  const lastClose = html.lastIndexOf('</');
  return lastClose === -1 ? html + CURSOR : html.slice(0, lastClose) + CURSOR + html.slice(lastClose);
}

// =============================================================================
// Ask Functionality
// =============================================================================

async function askQuestion() {
  const question = elements.questionInput.value.trim();
  if (!question) {
    showToast('Please enter a question', 'warning');
    return;
  }
  
  STATE.isLoading = true;
  elements.askBtn.disabled = true;
  elements.askBtn.textContent = 'Asking';
  elements.resultMethod.textContent = 'searching';
  elements.answerContent.setAttribute('aria-busy', 'true');
  elements.answerContent.innerHTML = `<p class="pixel pixel-16 muted">Searching your files${CURSOR}</p>`;
  elements.citationsList.innerHTML = '';
  elements.resultsArea.classList.remove('hidden');

  let answer = '';
  try {
    await streamCall('/ask/stream', {
      question,
      top_k: parseInt(elements.topK.value),
      use_llm: elements.useLlm.checked,
    }, (event, data) => {
      if (event === 'citations') {
        elements.citationsList.innerHTML = data.length
          ? renderCitations(data, question)
          : '<li class="empty"><p class="pixel pixel-16">No matching passage.</p><p>Try other words, or check that the file is indexed under Documents.</p></li>';
        elements.resultMethod.textContent = 'answering';
      } else if (event === 'token') {
        answer += data.text;
        elements.answerContent.innerHTML = withCursor(renderMarkdown(answer));
      } else if (event === 'error') {
        showToast(data.message, 'warning');
      } else if (event === 'done') {
        const model = data.model ? ` · ${data.model}` : '';
        elements.resultMethod.textContent = `${data.method}${model}`;
      }
    });
    elements.answerContent.innerHTML = renderMarkdown(answer);
  } catch (e) {
    elements.resultsArea.classList.add('hidden');
    showToast(`The question could not be answered: ${e.message}`, 'error');
  } finally {
    elements.answerContent.removeAttribute('aria-busy');
    STATE.isLoading = false;
    elements.askBtn.disabled = false;
    elements.askBtn.textContent = 'Ask';
  }
}

// =============================================================================
// Ingest Functionality
// =============================================================================

function updateFileList() {
  if (STATE.files.length === 0) {
    elements.fileList.innerHTML = '';
    elements.uploadActions.classList.add('hidden');
    return;
  }
  elements.fileList.innerHTML = `
    <table class="table">
      <thead><tr><th scope="col">File</th><th scope="col" class="num">Size</th><th scope="col"><span class="visually-hidden">Actions</span></th></tr></thead>
      <tbody>${STATE.files.map((file, i) => `
        <tr>
          <td class="mono">${escapeHtml(file.name)}</td>
          <td class="num mono">${formatBytes(file.size)}</td>
          <td class="row-actions"><button class="btn btn-secondary btn-sm" type="button" data-remove-file="${i}">${icon('remove')}Remove</button></td>
        </tr>`).join('')}
      </tbody>
    </table>`;
  elements.uploadActions.classList.remove('hidden');
}

function handleFiles(files) {
  STATE.files.push(...Array.from(files));
  updateFileList();
}

async function ingestFiles() {
  if (STATE.files.length === 0) {
    showToast('Choose files first', 'warning');
    return;
  }
  elements.ingestBtn.disabled = true;
  elements.ingestBtn.textContent = 'Uploading';

  const formData = new FormData();
  STATE.files.forEach(file => formData.append('files', file));

  const total = STATE.files.reduce((sum, file) => sum + file.size, 0);
  const showProgress = (sent, size) => {
    elements.uploadProgress.innerHTML = `${meter(sent / size, 'Upload')}<span class="pixel pixel-16">${formatBytes(sent)} of ${formatBytes(size)}</span>`;
  };
  elements.uploadProgress.classList.remove('hidden');
  showProgress(0, total || 1);

  try {
    const data = await uploadWithProgress('/ingest', formData, showProgress);
    showProgress(total || 1, total || 1);
    const ok = data.added.filter((item) => item.status === 'success').length;
    elements.ingestResults.innerHTML = `
      <div class="region-head">
        <h2 class="region-title" id="ingestResultsTitle">Indexed ${plural(ok, 'file')} of ${data.added.length}</h2>
      </div>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th scope="col">File</th><th scope="col" class="num">Chunks</th><th scope="col">Status</th></tr></thead>
          <tbody>${data.added.map((item) => `
            <tr>
              <td class="mono">${escapeHtml(item.filename)}</td>
              <td class="num mono">${item.chunks}</td>
              <td>${item.status === 'success' ? statusLabel('success', 'Indexed')
                : statusLabel('error', item.message ? `Failed: ${item.message}` : 'Failed')}</td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
    elements.ingestResults.classList.remove('hidden');
    STATE.files = [];
    updateFileList();
    const failed = data.added.length - ok;
    if (!failed) showToast(`Indexed ${plural(ok, 'file')}`, 'success');
    else if (!ok) showToast(`No file was indexed; ${failed} failed`, 'error');
    else showToast(`Indexed ${ok} of ${plural(data.added.length, 'file')}; ${failed} failed`, 'warning');
  } catch (e) {
    showToast(`The upload failed: ${e.message}`, 'error');
  } finally {
    elements.ingestBtn.disabled = false;
    elements.ingestBtn.innerHTML = `${icon('upload')}Upload and index`;
  }
}

// =============================================================================
// Documents Functionality
// =============================================================================

function documentName(doc) {
  return doc.source_name ? `${doc.source_name}/${doc.path}` : doc.filename;
}

async function loadDocuments() {
  try {
    const data = await apiCall('/documents');
    STATE.documents = data.documents;
    const totalChunks = data.documents.reduce((sum, d) => sum + d.chunk_count, 0);
    elements.documentsStats.innerHTML = `<p class="stat-line"><span class="pixel pixel-48">${data.total}</span>`
      + `<span class="stat-word">${data.total === 1 ? 'document' : 'documents'}</span></p>`
      + `<p class="stat-fine">${plural(totalChunks, 'chunk')}</p>`;

    if (data.documents.length === 0) {
      elements.documentsList.innerHTML = `
        <div class="empty">
          <p class="pixel pixel-24">No documents yet.</p>
          <button class="btn btn-primary" type="button" data-go-tab="${isAdmin() ? 'sources' : 'ingest'}">${isAdmin() ? 'Add a folder' : 'Upload files'}</button>
        </div>`;
      return;
    }

    elements.documentsList.innerHTML = `
      <div class="table-wrap">
        <table class="table">
          <thead><tr>
            <th scope="col">Name</th><th scope="col">From</th><th scope="col" class="num">Chunks</th>
            <th scope="col" class="num">Size</th><th scope="col">Indexed</th>
            <th scope="col"><span class="visually-hidden">Actions</span></th>
          </tr></thead>
          <tbody>${data.documents.map(doc => `
            <tr>
              <td><span class="name-cell">${icon('file')}<span class="mono">${escapeHtml(documentName(doc))}</span></span></td>
              <td>${doc.source_name ? 'NAS folder' : 'Upload'}</td>
              <td class="num mono">${doc.chunk_count}</td>
              <td class="num mono">${formatBytes(doc.file_size || doc.total_chars)}</td>
              <td class="mono nowrap">${formatDate(doc.indexed_at)}</td>
              <td class="row-actions">
                <button class="btn btn-secondary btn-sm" type="button" data-open-doc="${escapeHtml(doc.doc_id)}">${icon('external-link')}Open</button>
                ${!doc.source_id && isAdmin() ? `<button class="btn btn-secondary btn-sm btn-icon" type="button" data-delete-doc="${escapeHtml(doc.doc_id)}" aria-label="Delete ${escapeHtml(documentName(doc))}" title="Delete ${escapeHtml(documentName(doc))}">${icon('delete')}</button>` : ''}
              </td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
  } catch (e) {
    showToast(`The documents could not be loaded: ${e.message}`, 'error');
  }
}

async function deleteDocument(docId) {
  const doc = STATE.documents.find((d) => d.doc_id === docId);
  const name = doc ? documentName(doc) : 'this document';
  const confirmed = await confirmDialog({
    title: `Delete ${name}?`,
    body: 'The uploaded file and its place in the index are removed. Answers will no longer cite it.',
    confirmLabel: 'Delete document',
  });
  if (!confirmed) return;
  try {
    await apiCall(`/documents/${docId}`, { method: 'DELETE' });
    showToast(`Deleted ${name}`, 'success');
    loadDocuments();
  } catch (e) {
    showToast(`The document could not be deleted: ${e.message}`, 'error');
  }
}

// =============================================================================
// Chat Functionality
// =============================================================================

const CHAT_ROLES = { user: 'You', assistant: 'nAI' };

function chatEmpty() {
  return '<li class="empty"><p class="pixel pixel-24">No messages yet.</p><p>Ask a question below; nAI answers from your files.</p></li>';
}

/** One turn of the transcript: a mono role label, then the text. Returns the element that holds the text. */
function addChatMessage(role, content) {
  const empty = elements.chatMessages.querySelector('.empty');
  if (empty) empty.remove();
  const turn = document.createElement('li');
  turn.className = `turn ${role}`;
  turn.innerHTML = `<span class="turn-role mono">${CHAT_ROLES[role]}</span><div class="turn-text prose"></div>`;
  turn.querySelector('.turn-text').innerHTML = content ? renderMarkdown(content) : '';
  elements.chatMessages.appendChild(turn);
  turn.scrollIntoView({ block: 'nearest' });
  return turn.querySelector('.turn-text');
}

function chatSources(citations) {
  if (!citations.length) return '';
  const seen = new Set();
  const chips = citations.filter(c => !seen.has(c.doc_id) && seen.add(c.doc_id)).slice(0, 5).map(c => `
    <button class="chip" type="button" data-open-doc="${escapeHtml(c.doc_id)}" title="${escapeHtml(citationLocation(c))}">
      ${icon('file')}${escapeHtml(c.filename || c.doc_path)}${c.page != null ? ` · page ${c.page}` : ''}
    </button>`).join('');
  return `<div class="chips" aria-label="Sources">${chips}</div>`;
}

async function sendChatMessage() {
  const message = elements.chatInput.value.trim();
  if (!message) return;
  
  addChatMessage('user', message);
  elements.chatInput.value = '';
  elements.chatSendBtn.disabled = true;
  const bubble = addChatMessage('assistant', '');
  bubble.innerHTML = `<p class="pixel pixel-16 muted">Reading your files${CURSOR}</p>`;
  bubble.setAttribute('aria-busy', 'true');
  let reply = '';
  let citations = [];
  
  try {
    await streamCall('/chat/stream', {
      messages: [{ role: 'user', content: message }],
      top_k: 5,
      use_context: true,
      conversation_id: STATE.chatConversationId,
    }, (event, data) => {
      if (event === 'conversation') {
        STATE.chatConversationId = data.conversation_id;
      } else if (event === 'citations') {
        citations = data;
      } else if (event === 'token') {
        reply += data.text;
        bubble.innerHTML = withCursor(renderMarkdown(reply));
        bubble.scrollIntoView({ block: 'nearest' });
      } else if (event === 'error') {
        showToast(data.message, 'warning');
      } else if (event === 'done') {
        bubble.innerHTML = renderMarkdown(reply) + chatSources(citations);
      }
    });
  } catch (e) {
    bubble.innerHTML = `<p>${statusLabel('error', `No reply: ${e.message}`)}</p>`;
  } finally {
    bubble.removeAttribute('aria-busy');
    elements.chatSendBtn.disabled = false;
  }
}

function newChat() {
  STATE.chatConversationId = null;
  elements.chatMessages.innerHTML = chatEmpty();
  elements.chatInput.focus();
}

// =============================================================================
// Sources (admin): NAS folders indexed in place
// =============================================================================

function splitList(value) {
  return value.split(',').map(v => v.trim()).filter(Boolean);
}

function sourceStatus(src) {
  if (src.scanning) return statusLabel('running', 'Scanning');
  if (!src.enabled) return statusLabel('off', 'Paused');
  if (src.last_scan_status === 'error') return statusLabel('error', 'Failed');
  if (src.last_scan_status === 'ok') return statusLabel('success', 'In sync');
  if (src.last_scan_status === 'never') return statusLabel('info', 'Not scanned yet');
  return statusLabel('info', src.last_scan_status);
}

async function loadSources() {
  try {
    const sources = await apiCall('/sources');
    STATE.sources = sources;
    if (!sources.length) {
      elements.sourcesList.innerHTML = `
        <div class="empty">
          <p class="pixel pixel-24">No NAS folders yet.</p>
          <button class="btn btn-primary" type="button" data-focus="sourceName">Add a folder</button>
        </div>`;
      return;
    }
    elements.sourcesList.innerHTML = `
      <div class="table-wrap">
        <table class="table">
          <thead><tr>
            <th scope="col">Folder</th><th scope="col">Path</th><th scope="col" class="num">Files</th>
            <th scope="col">Visible to</th><th scope="col">Synced</th><th scope="col">Status</th>
            <th scope="col"><span class="visually-hidden">Actions</span></th>
          </tr></thead>
          <tbody>${sources.map(src => `
            <tr>
              <td><span class="name-cell">${icon('folder')}<span>${escapeHtml(src.name)}</span></span></td>
              <td class="mono">${escapeHtml(src.path || '')}</td>
              <td class="num mono">${src.document_count}</td>
              <td>${src.allowed_groups.length ? escapeHtml(src.allowed_groups.join(', ')) : 'Everyone'}</td>
              <td class="mono nowrap">${src.last_scan_finished ? formatDate(src.last_scan_finished) : '–'}</td>
              <td>${sourceStatus(src)}${src.last_error ? `<p class="form-error">${stateIcon('error')}<span>${escapeHtml(src.last_error)}</span></p>` : ''}</td>
              <td class="row-actions">
                <button class="btn btn-secondary btn-sm" type="button" data-source-action="scan" data-id="${src.id}" ${src.scanning ? 'disabled' : ''}>${icon('sync')}Rescan</button>
                <button class="btn btn-secondary btn-sm" type="button" data-source-action="toggle" data-id="${src.id}" data-enabled="${src.enabled}">${src.enabled ? 'Pause' : 'Resume'}</button>
                <button class="btn btn-secondary btn-sm" type="button" data-source-action="delete" data-id="${src.id}" data-name="${escapeHtml(src.name)}">Remove</button>
              </td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
    if (sources.some(s => s.scanning)) setTimeout(loadSources, 3000);
  } catch (e) {
    showToast(`The folders could not be loaded: ${e.message}`, 'error');
  }
}

async function sourceAction(btn) {
  const id = btn.dataset.id;
  try {
    if (btn.dataset.sourceAction === 'scan') {
      await apiCall(`/sources/${id}/scan`, { method: 'POST' });
      showToast('Rescan started', 'success');
    } else if (btn.dataset.sourceAction === 'toggle') {
      await apiCall(`/sources/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ enabled: btn.dataset.enabled !== 'true' }),
      });
    } else if (btn.dataset.sourceAction === 'delete') {
      const confirmed = await confirmDialog({
        title: `Remove ${btn.dataset.name} from nAI?`,
        body: 'Its files stay on the NAS; only nAI\'s index of them is removed. You can add the folder again later.',
        confirmLabel: 'Remove folder',
      });
      if (!confirmed) return;
      await apiCall(`/sources/${id}`, { method: 'DELETE' });
      showToast('Source removed', 'success');
    }
  } catch (e) {
    showToast(e.message, 'error');
  }
  setTimeout(loadSources, 300);
}

async function addSource(event) {
  event.preventDefault();
  elements.sourceAddBtn.disabled = true;
  try {
    await apiCall('/sources', {
      method: 'POST',
      body: JSON.stringify({
        name: elements.sourceName.value.trim(),
        path: elements.sourcePath.value.trim(),
        allowed_groups: splitList(elements.sourceGroups.value),
        exclude_patterns: splitList(elements.sourceExclude.value),
      }),
    });
    elements.sourceForm.reset();
    showToast('Folder added; indexing has started', 'success');
    loadSources();
  } catch (e) {
    showToast(e.message, 'error');
  } finally {
    elements.sourceAddBtn.disabled = false;
  }
}

// The embedding model changed: semantic search is paused until an admin confirms the re-index.
function reindexNotice(emb) {
  if (!emb || !emb.reindex_required) return '';
  const previous = Object.entries(emb.previous_models || {})
    .map(([model, count]) => `${escapeHtml(model)} (${count} vectors)`).join(', ');
  return `
    <div class="notice" role="alert">
      <p>${statusLabel('warning', 'Reindex needed')}</p>
      <p>The embedding model changed to <span class="mono">${escapeHtml(emb.model || 'a new model')}</span>, and the index
        still holds vectors from ${previous || 'an older model'}. Searches use keywords only until everything is
        embedded again, which can take a while on large folders.</p>
      <button id="reindexBtn" class="btn btn-primary" type="button">Reindex now</button>
    </div>`;
}

// NAI_EMBEDDINGS=auto turned semantic search off: the box has too little memory for the embedding model.
// A notice that something is off, not that something failed: no hue.
function keywordOnlyNotice(emb) {
  if (!emb || emb.mode !== 'auto-off') return '';
  return `
    <div class="notice" role="status">
      <p>${statusLabel('off', 'Keyword-only search')}</p>
      <p>This machine has too little memory for semantic search (${escapeHtml(emb.reason || '')}). Searches match the
        words in your files. To turn semantic search on, give nAI at least 2.5 GB of memory (3 GB recommended) or
        set <code>NAI_EMBEDDINGS=on</code>.</p>
    </div>`;
}

async function confirmReindex() {
  const btn = document.getElementById('reindexBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Starting'; }
  try {
    const r = await apiCall('/system/embeddings/reindex', { method: 'POST' });
    showToast(r.reindexing ? `Re-indexing ${r.pending} passages in the background` : 'Nothing to re-index', 'success');
  } catch (e) {
    showToast(`Could not start the re-index: ${e.message}`, 'error');
  }
  loadSystemInfo();
}

const GIB = 1024 ** 3;

/** "This machine" as block meters: memory in use, the data disk, and how much of the index is embedded. */
function systemMeters(sys) {
  const rows = [];
  const hw = sys.hardware;
  if (hw.memory_gb && hw.memory_available_gb != null) {
    const used = Math.max(0, hw.memory_gb - hw.memory_available_gb);
    rows.push(['Memory in use', used / hw.memory_gb, `${used.toFixed(1)} of ${hw.memory_gb} GB`]);
  }
  if (sys.storage && sys.storage.total_bytes) {
    const { used_bytes: used, total_bytes: total } = sys.storage;
    rows.push(['Data disk', used / total, `${(used / GIB).toFixed(0)} of ${(total / GIB).toFixed(0)} GB`]);
  }
  const emb = sys.features.embeddings;
  if (emb.available && emb.pending != null && emb.vectors + emb.pending > 0) {
    const done = emb.vectors / (emb.vectors + emb.pending);
    rows.push(['Semantic index', done, `${Math.floor(done * 100)}%`]);
  }
  if (!rows.length) return '';
  return `<dl class="meters">${rows.map(([label, share, value]) => `
    <dt>${label}</dt>
    <dd>${meter(share, label, label === 'Semantic index' ? 'progressbar' : 'meter')}<span class="pixel pixel-16">${value}</span></dd>`).join('')}
  </dl>`;
}

async function loadSystemInfo() {
  try {
    const sys = await apiCall('/system');
    const hw = sys.hardware;
    const emb = sys.features.embeddings;
    const llm = sys.features.llm;
    const gpu = hw.gpus.length
      ? hw.gpus.map(g => `${g.vendor} ${g.name}${g.memory_gb ? ` (${g.memory_gb} GB)` : ''}`).join(', ')
      : 'none detected';
    const semantic = emb.state === 'ready'
      ? `ready${emb.pending ? ` · ${emb.pending} passages still being processed` : ''}`
      : emb.state === 'loading' ? 'loading the model'
      : emb.mode === 'auto-off' ? 'off (keyword-only: not enough memory)' : emb.state;
    const rows = [
      ['Hardware', `${hw.cpu_count} CPUs · ${hw.memory_gb} GB RAM · GPU: ${gpu} · tier: ${hw.tier}`],
      ['Semantic search', `${semantic}${emb.error ? ` (${emb.error})` : ''}`],
      ['Reranker', sys.features.reranker.active ? 'on' : 'off'],
      ['OCR', sys.features.ocr ? 'available' : 'not available'],
      ['Answer model', llm.enabled ? (llm.active_model ? `${llm.provider}/${llm.active_model}` : 'no model available') : 'off (extractive answers)'],
    ];
    elements.systemInfo.innerHTML = keywordOnlyNotice(emb) + reindexNotice(emb) + systemMeters(sys)
      + `<dl class="facts">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${escapeHtml(v)}</dd>`).join('')}</dl>`
      + (sys.recommendations.length ? `<ul class="tips">${sys.recommendations.map(r => `<li>${escapeHtml(r)}</li>`).join('')}</ul>` : '');
    const reindexBtn = document.getElementById('reindexBtn');
    if (reindexBtn) reindexBtn.addEventListener('click', confirmReindex);
    elements.sourceRootsHint.textContent = `Must be inside: ${sys.sources.allowed_roots.join(', ')}`;
  } catch (e) {
    elements.systemInfo.textContent = `Could not load system info: ${e.message}`;
  }
}

// =============================================================================
// Authentication
// =============================================================================

function setToken(token) {
  AUTH.token = token;
  storageSet('nai_token', token);
  if (!token) {
    AUTH.user = null;
    renderUser();
  }
}

function renderUser() {
  elements.sourcesTab.classList.toggle('hidden', !isAdmin());
  if (!isAdmin() && elements.sourcesTab.classList.contains('active')) switchTab('ask');
  if (AUTH.enabled && AUTH.user) {
    elements.userName.textContent = AUTH.user.username + (AUTH.user.is_admin ? ' (admin)' : '');
    elements.userChip.classList.remove('hidden');
  } else {
    elements.userChip.classList.add('hidden');
  }
}

function openLogin() {
  const setup = AUTH.setupMode;
  elements.loginTitle.textContent = setup ? 'Create admin account' : 'Sign in';
  elements.loginHint.textContent = setup
    ? 'No accounts exist yet. The first account becomes the administrator.'
    : 'Sign in to your nAI account.';
  elements.loginSubmitBtn.textContent = setup ? 'Create account' : 'Sign in';
  elements.loginEmailGroup.classList.toggle('hidden', !setup);
  elements.loginEmail.required = setup;
  elements.loginPassword.autocomplete = setup ? 'new-password' : 'current-password';
  elements.loginError.classList.add('hidden');
  elements.loginModal.classList.remove('hidden');
  elements.loginUsername.focus();
}

function closeLogin() {
  elements.loginModal.classList.add('hidden');
  elements.loginPassword.value = '';
}

async function submitLogin(event) {
  event.preventDefault();
  const username = elements.loginUsername.value.trim();
  const password = elements.loginPassword.value;
  elements.loginSubmitBtn.disabled = true;
  elements.loginError.classList.add('hidden');
  elements.loginPassword.removeAttribute('aria-invalid');
  
  try {
    if (AUTH.setupMode) {
      await apiCall('/auth/register', {
        method: 'POST',
        body: JSON.stringify({ username, email: elements.loginEmail.value.trim(), password }),
      });
      AUTH.setupMode = false;
    }
    const token = await apiCall('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    setToken(token.access_token);
    AUTH.user = await apiCall('/auth/me');
    renderUser();
    closeLogin();
    showToast(`Signed in as ${AUTH.user.username}`, 'success');
  } catch (e) {
    fieldError(elements.loginError, e.message);
    elements.loginError.classList.remove('hidden');
    elements.loginPassword.setAttribute('aria-invalid', 'true');
    elements.loginPassword.focus();
  } finally {
    elements.loginSubmitBtn.disabled = false;
  }
}

function logout() {
  setToken(null);
  newChat();
  openLogin();
}

async function initAuth() {
  try {
    const status = await apiCall('/auth/status');
    AUTH.enabled = status.auth_enabled;
    AUTH.setupMode = status.setup_required;
  } catch {
    return; // backend offline; health indicator shows it
  }
  
  if (!AUTH.enabled) {
    renderUser();
    return;
  }
  
  if (AUTH.token && !AUTH.setupMode) {
    try {
      AUTH.user = await apiCall('/auth/me');
      renderUser();
      return;
    } catch {
      setToken(null);
    }
  }
  openLogin();
}

// =============================================================================
// Settings
// =============================================================================

function openSettings() {
  elements.apiBaseInput.value = storageGet('nai_api_base') || '';
  elements.themeSelect.value = CONFIG.theme;
  elements.settingsModal.classList.remove('hidden');
  loadApiKeys();
}

// API keys + connection info for other apps (OpenAI-compatible API, MCP)
async function loadApiKeys() {
  elements.openaiUrl.textContent = `${CONFIG.apiBase}/v1`;
  elements.mcpUrl.textContent = `${CONFIG.apiBase}/mcp`;
  elements.apiKeyNew.classList.add('hidden');
  const signedIn = AUTH.enabled && AUTH.user;
  elements.apiKeysArea.classList.toggle('hidden', !signedIn);
  if (!signedIn) return;
  try {
    const keys = await apiCall('/auth/keys');
    STATE.apiKeys = keys;
    elements.apiKeysList.innerHTML = keys.length ? `
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th scope="col">Key</th><th scope="col">Starts with</th><th scope="col">Last used</th>
            <th scope="col"><span class="visually-hidden">Actions</span></th></tr></thead>
          <tbody>${keys.map(k => `
            <tr>
              <td>${escapeHtml(k.name)}</td>
              <td class="mono">${escapeHtml(k.prefix)}…</td>
              <td class="mono nowrap">${k.last_used_at ? formatDate(k.last_used_at) : 'never'}</td>
              <td class="row-actions"><button class="btn btn-secondary btn-sm" type="button" data-revoke-key="${escapeHtml(k.id)}">Revoke</button></td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>` : '<p class="form-hint">No API keys yet.</p>';
  } catch (e) {
    elements.apiKeysList.textContent = `Could not load API keys: ${e.message}`;
  }
}

async function createApiKey() {
  const name = elements.apiKeyName.value.trim();
  if (!name) {
    showToast('Give the key a name first', 'warning');
    return;
  }
  try {
    const created = await apiCall('/auth/keys', { method: 'POST', body: JSON.stringify({ name }) });
    elements.apiKeyName.value = '';
    await loadApiKeys();
    // Shown once, in a field, never in a toast.
    elements.apiKeyNew.innerHTML = `
      <label class="form-label" for="apiKeySecret">New key: ${escapeHtml(created.name || name)}</label>
      <div class="key-row">
        <input type="text" id="apiKeySecret" class="form-input mono" readonly />
        <button class="btn btn-secondary" type="button" id="apiKeyCopyBtn">${icon('copy')}Copy</button>
      </div>
      <p class="form-hint">Copy it now. nAI keeps only a fingerprint and won't show this key again.</p>`;
    const secret = elements.apiKeyNew.querySelector('#apiKeySecret');
    secret.value = created.key;
    const copyBtn = elements.apiKeyNew.querySelector('#apiKeyCopyBtn');
    copyBtn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(created.key);
      } catch {
        secret.select(); // no clipboard access (plain http): select it for Ctrl+C
        document.execCommand('copy');
      }
      copyBtn.innerHTML = `${icon('ok')}Copied`;
    });
    elements.apiKeyNew.classList.remove('hidden');
    secret.focus();
    secret.select();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

async function revokeApiKey(id) {
  const key = STATE.apiKeys.find((k) => k.id === id);
  const confirmed = await confirmDialog({
    title: `Revoke ${key ? key.name : 'this key'}?`,
    body: 'Apps that use this key stop working at once. A revoked key cannot be restored.',
    confirmLabel: 'Revoke key',
  });
  if (!confirmed) return;
  try {
    await apiCall(`/auth/keys/${encodeURIComponent(id)}`, { method: 'DELETE' });
    loadApiKeys();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

function closeSettings() {
  elements.settingsModal.classList.add('hidden');
}

function saveSettings() {
  const customBase = elements.apiBaseInput.value.trim().replace(/\/$/, '');
  CONFIG.apiBase = customBase || defaultApiBase();
  CONFIG.theme = elements.themeSelect.value;
  
  storageSet('nai_api_base', customBase || null);
  storageSet('nai_theme', CONFIG.theme);
  
  applyTheme();
  closeSettings();
  checkHealth();
  initAuth();
  showToast('Settings saved', 'success');
}

// System (the default) leaves data-theme unset, so the tokens follow the system, also when it changes.
function applyTheme() {
  if (CONFIG.theme === 'dark' || CONFIG.theme === 'light') {
    document.documentElement.dataset.theme = CONFIG.theme;
  } else {
    delete document.documentElement.dataset.theme;
  }
}

// =============================================================================
// Event Listeners
// =============================================================================

// Tabs
elements.tabs.forEach(tab => {
  tab.addEventListener('click', () => switchTab(tab.dataset.tab));
});

// Ask
elements.askBtn.addEventListener('click', askQuestion);
elements.questionInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    askQuestion();
  }
});

// Ingest
elements.browseBtn.addEventListener('click', () => elements.fileInput.click());
elements.uploadZone.addEventListener('click', (e) => {
  if (e.target === elements.uploadZone || e.target.tagName === 'P') elements.fileInput.click();
});
elements.fileList.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-remove-file]');
  if (!btn) return;
  STATE.files.splice(parseInt(btn.dataset.removeFile), 1);
  updateFileList();
});
elements.fileInput.addEventListener('change', (e) => {
  handleFiles(e.target.files);
  e.target.value = ''; // the same file can be chosen again
});
elements.ingestBtn.addEventListener('click', ingestFiles);
elements.clearFilesBtn.addEventListener('click', () => {
  STATE.files = [];
  updateFileList();
});

// Drag and drop
elements.uploadZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  elements.uploadZone.classList.add('dragover');
});
elements.uploadZone.addEventListener('dragleave', () => {
  elements.uploadZone.classList.remove('dragover');
});
elements.uploadZone.addEventListener('drop', (e) => {
  e.preventDefault();
  elements.uploadZone.classList.remove('dragover');
  handleFiles(e.dataTransfer.files);
});

// Documents
elements.refreshDocsBtn.addEventListener('click', loadDocuments);
elements.documentsList.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-delete-doc]');
  if (btn) deleteDocument(btn.dataset.deleteDoc);
});

// Empty screens: their one action
document.addEventListener('click', (e) => {
  const go = e.target.closest('[data-go-tab]');
  if (go) switchTab(go.dataset.goTab);
  const focus = e.target.closest('[data-focus]');
  if (focus) document.getElementById(focus.dataset.focus).focus();
});

// Chat
elements.chatSendBtn.addEventListener('click', sendChatMessage);
elements.chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendChatMessage();
  }
});
elements.chatInput.addEventListener('input', function() {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 150) + 'px';
});

elements.chatNewBtn.addEventListener('click', newChat);

// Sources
elements.refreshSourcesBtn.addEventListener('click', () => { loadSources(); loadSystemInfo(); });
elements.sourceForm.addEventListener('submit', addSource);
elements.sourcesList.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-source-action]');
  if (btn) sourceAction(btn);
});

// Auth
elements.loginForm.addEventListener('submit', submitLogin);
elements.logoutBtn.addEventListener('click', logout);

// Settings
elements.settingsBtn.addEventListener('click', openSettings);
elements.closeSettingsBtn.addEventListener('click', closeSettings);
elements.cancelSettingsBtn.addEventListener('click', closeSettings);
elements.saveSettingsBtn.addEventListener('click', saveSettings);
elements.apiKeyCreateBtn.addEventListener('click', createApiKey);
elements.apiKeysList.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-revoke-key]');
  if (btn) revokeApiKey(btn.dataset.revokeKey);
});
elements.settingsModal.querySelector('.modal-backdrop').addEventListener('click', closeSettings);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !elements.settingsModal.classList.contains('hidden')) closeSettings();
});

// =============================================================================
// Initialization
// =============================================================================

applyTheme();
elements.chatMessages.innerHTML = chatEmpty();
checkHealth();
initAuth();
setInterval(checkHealth, 30000); // Check health every 30 seconds
