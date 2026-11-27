/**
 * nAI Web Interface
 * Modern client-side JavaScript for the nAI document Q&A system
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

function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span></span>
    <button>
      ${icon('close')}
    </button>
  `;
  // textContent: messages can contain server-provided text (e.g. filenames)
  toast.querySelector('span').textContent = message;
  toast.querySelector('button').addEventListener('click', () => toast.remove());
  elements.toastContainer.appendChild(toast);
  setTimeout(() => toast.remove(), 5000);
}

function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatDate(isoString) {
  if (!isoString) return 'Unknown';
  const date = new Date(isoString);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
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

function renderCitations(citations) {
  return citations.map((cit, i) => `
    <div class="citation-item">
      <div class="citation-rank">${i + 1}</div>
      <div class="citation-content">
        <div class="citation-source">
          <span>${escapeHtml(citationLocation(cit))}</span>
          <button class="btn btn-ghost btn-sm" data-open-doc="${escapeHtml(cit.doc_id)}">Open</button>
        </div>
        <div class="citation-text">${escapeHtml(cit.text.slice(0, 300))}${cit.text.length > 300 ? '...' : ''}</div>
      </div>
    </div>
  `).join('');
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

function renderMarkdown(text) {
  // Simple markdown rendering
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>');
}

// =============================================================================
// Health Check
// =============================================================================

async function checkHealth() {
  const statusDot = elements.statusIndicator.querySelector('.status-dot');
  const statusText = elements.statusIndicator.querySelector('.status-text');
  
  try {
    const data = await apiCall('/health');
    elements.appVersion.textContent = `v${data.version}`;
    statusDot.className = 'status-dot online';
    statusText.textContent = `Online (v${data.version})`;
    return true;
  } catch (e) {
    statusDot.className = 'status-dot offline';
    statusText.textContent = 'Offline';
    return false;
  }
}

// =============================================================================
// Tab Navigation
// =============================================================================

function switchTab(tabName) {
  elements.tabs.forEach(tab => {
    tab.classList.toggle('active', tab.dataset.tab === tabName);
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
  elements.askBtn.innerHTML = '<span>Thinking...</span>';
  elements.resultMethod.textContent = 'searching…';
  elements.answerContent.innerHTML = '<div class="answer-text loading">Searching your files…</div>';
  elements.citationsList.innerHTML = '';
  elements.resultsArea.classList.remove('hidden');

  let answer = '';
  const answerEl = () => elements.answerContent.querySelector('.answer-text');
  try {
    await streamCall('/ask/stream', {
      question,
      top_k: parseInt(elements.topK.value),
      use_llm: elements.useLlm.checked,
    }, (event, data) => {
      if (event === 'citations') {
        elements.citationsList.innerHTML = data.length
          ? renderCitations(data)
          : '<div class="empty-state"><p>No matching passages.</p></div>';
        elements.resultMethod.textContent = 'answering…';
      } else if (event === 'token') {
        answer += data.text;
        const el = answerEl();
        el.classList.remove('loading');
        el.innerHTML = renderMarkdown(escapeHtml(answer));
      } else if (event === 'error') {
        showToast(data.message, 'warning');
      } else if (event === 'done') {
        const model = data.model ? ` · ${data.model}` : '';
        elements.resultMethod.textContent = `${data.method}${model}`;
      }
    });
  } catch (e) {
    elements.resultsArea.classList.add('hidden');
    showToast(`Error: ${e.message}`, 'error');
  } finally {
    STATE.isLoading = false;
    elements.askBtn.disabled = false;
    elements.askBtn.innerHTML = '<span>Ask</span>' + icon('arrow-right');
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
  
  elements.fileList.innerHTML = STATE.files.map((file, i) => `
    <div class="file-item">
      <span class="file-icon">${icon('file')}</span>
      <span class="file-name">${escapeHtml(file.name)}</span>
      <span class="file-size">${formatBytes(file.size)}</span>
      <button class="file-remove" data-index="${i}">
        ${icon('close')}
      </button>
    </div>
  `).join('');
  
  elements.uploadActions.classList.remove('hidden');
  
  // Add remove handlers
  elements.fileList.querySelectorAll('.file-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      STATE.files.splice(parseInt(btn.dataset.index), 1);
      updateFileList();
    });
  });
}

function handleFiles(files) {
  STATE.files.push(...Array.from(files));
  updateFileList();
}

async function ingestFiles() {
  if (STATE.files.length === 0) {
    showToast('No files selected', 'warning');
    return;
  }
  
  elements.ingestBtn.disabled = true;
  elements.ingestBtn.innerHTML = '<span>Uploading...</span>';
  
  const formData = new FormData();
  STATE.files.forEach(file => formData.append('files', file));
  
  try {
    const data = await apiCall('/ingest', {
      method: 'POST',
      body: formData,
    });
    
    // Show results
    elements.ingestResults.innerHTML = `
      <div class="card">
        <h3>Ingest Results</h3>
        <p>Successfully indexed ${data.total_files} file(s) with ${data.total_chunks} chunks.</p>
        ${data.added.map(item => `
          <div class="ingest-result-item ${item.status}">
            <strong>${escapeHtml(item.filename)}</strong>
            <span>${item.chunks} chunks</span>
            <span class="status-badge">${item.status}</span>
            ${item.message ? `<small>${escapeHtml(item.message)}</small>` : ''}
          </div>
        `).join('')}
      </div>
    `;
    elements.ingestResults.classList.remove('hidden');
    
    // Clear files
    STATE.files = [];
    updateFileList();
    
    showToast(`Indexed ${data.total_files} file(s)`, 'success');
  } catch (e) {
    showToast(`Upload failed: ${e.message}`, 'error');
  } finally {
    elements.ingestBtn.disabled = false;
    elements.ingestBtn.innerHTML = icon('upload-arrow') + 'Upload & Index';
  }
}

// =============================================================================
// Documents Functionality
// =============================================================================

async function loadDocuments() {
  try {
    const data = await apiCall('/documents');
    STATE.documents = data.documents;
    
    // Stats
    const totalChunks = data.documents.reduce((sum, d) => sum + d.chunk_count, 0);
    elements.documentsStats.innerHTML = `
      <div class="stat-card">
        <div class="stat-value">${data.total}</div>
        <div class="stat-label">Documents</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">${totalChunks}</div>
        <div class="stat-label">Chunks</div>
      </div>
    `;
    
    // Document list
    if (data.documents.length === 0) {
      elements.documentsList.innerHTML = `
        <div class="empty-state">
          <p>No documents indexed yet. Upload files, or ask an admin to add a NAS folder under Sources.</p>
        </div>
      `;
      return;
    }
    
    elements.documentsList.innerHTML = data.documents.map(doc => `
      <div class="document-item">
        <div class="document-icon">
          ${icon('file')}
        </div>
        <div class="document-info">
          <div class="document-name">${escapeHtml(doc.source_name ? `${doc.source_name}/${doc.path}` : doc.filename)}</div>
          <div class="document-meta">
            <span>${doc.source_name ? 'NAS folder' : 'Upload'}</span>
            <span>${doc.chunk_count} chunks</span>
            <span>${formatBytes(doc.file_size || doc.total_chars)}</span>
            <span>${formatDate(doc.indexed_at)}</span>
          </div>
        </div>
        <div class="document-actions">
          <button class="btn btn-ghost btn-sm" data-open-doc="${escapeHtml(doc.doc_id)}">Open</button>
          ${!doc.source_id && isAdmin() ? `
          <button class="btn btn-ghost btn-sm" data-action="delete" data-id="${escapeHtml(doc.doc_id)}" title="Delete upload">
            ${icon('trash')}
          </button>` : ''}
        </div>
      </div>
    `).join('');
    
    // Add delete handlers
    elements.documentsList.querySelectorAll('[data-action="delete"]').forEach(btn => {
      btn.addEventListener('click', () => deleteDocument(btn.dataset.id));
    });
    
  } catch (e) {
    showToast(`Failed to load documents: ${e.message}`, 'error');
  }
}

async function deleteDocument(docId) {
  if (!confirm('Are you sure you want to delete this document?')) return;
  
  try {
    await apiCall(`/documents/${docId}`, { method: 'DELETE' });
    showToast('Document deleted', 'success');
    loadDocuments();
  } catch (e) {
    showToast(`Delete failed: ${e.message}`, 'error');
  }
}

// =============================================================================
// Chat Functionality
// =============================================================================

function addChatMessage(role, content) {
  const welcome = elements.chatMessages.querySelector('.chat-welcome');
  if (welcome) welcome.remove();
  
  const avatar = role === 'user' ? '👤' : '🤖';
  const messageEl = document.createElement('div');
  messageEl.className = `chat-message ${role}`;
  messageEl.innerHTML = `
    <div class="chat-avatar">${avatar}</div>
    <div class="chat-bubble">${renderMarkdown(escapeHtml(content))}</div>
  `;
  elements.chatMessages.appendChild(messageEl);
  elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
  return messageEl.querySelector('.chat-bubble');
}

function chatSources(citations) {
  if (!citations.length) return '';
  const seen = new Set();
  const chips = citations.filter(c => !seen.has(c.doc_id) && seen.add(c.doc_id)).slice(0, 5).map(c => `
    <button class="source-chip" data-open-doc="${escapeHtml(c.doc_id)}" title="${escapeHtml(citationLocation(c))}">
      ${escapeHtml(c.filename || c.doc_path)}${c.page != null ? ` · p.${c.page}` : ''}
    </button>`).join('');
  return `<div class="chat-sources">${chips}</div>`;
}

async function sendChatMessage() {
  const message = elements.chatInput.value.trim();
  if (!message) return;
  
  addChatMessage('user', message);
  elements.chatInput.value = '';
  elements.chatSendBtn.disabled = true;
  const bubble = addChatMessage('assistant', '…');
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
        bubble.innerHTML = renderMarkdown(escapeHtml(reply));
        elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
      } else if (event === 'error') {
        showToast(data.message, 'warning');
      } else if (event === 'done') {
        bubble.innerHTML = renderMarkdown(escapeHtml(reply)) + chatSources(citations);
      }
    });
  } catch (e) {
    bubble.textContent = `Error: ${e.message}`;
  } finally {
    elements.chatSendBtn.disabled = false;
  }
}

function newChat() {
  STATE.chatConversationId = null;
  elements.chatMessages.innerHTML = `
    <div class="chat-welcome">
      <h3>Start a conversation</h3>
      <p>Ask questions about your documents in a multi-turn conversation.</p>
    </div>
  `;
  elements.chatInput.focus();
}

// =============================================================================
// Sources (admin): NAS folders indexed in place
// =============================================================================

function splitList(value) {
  return value.split(',').map(v => v.trim()).filter(Boolean);
}

function sourceStatus(src) {
  if (src.scanning) return '<span class="status-badge scanning">scanning…</span>';
  if (!src.enabled) return '<span class="status-badge">paused</span>';
  if (src.last_scan_status === 'error') return '<span class="status-badge error">error</span>';
  if (src.last_scan_status === 'ok') return '<span class="status-badge success">in sync</span>';
  return `<span class="status-badge">${escapeHtml(src.last_scan_status)}</span>`;
}

async function loadSources() {
  try {
    const sources = await apiCall('/sources');
    if (!sources.length) {
      elements.sourcesList.innerHTML = '<div class="empty-state"><p>No folders yet. Add one below.</p></div>';
      return;
    }
    elements.sourcesList.innerHTML = sources.map(src => `
      <div class="document-item">
        <div class="document-icon">
          ${icon('folder')}
        </div>
        <div class="document-info">
          <div class="document-name">${escapeHtml(src.name)} ${sourceStatus(src)}</div>
          <div class="document-meta">
            <span>${escapeHtml(src.path || '')}</span>
            <span>${src.document_count} files</span>
            <span>${src.allowed_groups.length ? 'groups: ' + escapeHtml(src.allowed_groups.join(', ')) : 'all users'}</span>
            ${src.last_scan_finished ? `<span>synced ${formatDate(src.last_scan_finished)}</span>` : ''}
          </div>
          ${src.last_error ? `<div class="form-error">${escapeHtml(src.last_error)}</div>` : ''}
        </div>
        <div class="document-actions">
          <button class="btn btn-ghost btn-sm" data-source-action="scan" data-id="${src.id}" ${src.scanning ? 'disabled' : ''}>Rescan</button>
          <button class="btn btn-ghost btn-sm" data-source-action="toggle" data-id="${src.id}" data-enabled="${src.enabled}">${src.enabled ? 'Pause' : 'Resume'}</button>
          <button class="btn btn-ghost btn-sm" data-source-action="delete" data-id="${src.id}" data-name="${escapeHtml(src.name)}">Remove</button>
        </div>
      </div>
    `).join('');
    if (sources.some(s => s.scanning)) setTimeout(loadSources, 3000);
  } catch (e) {
    showToast(`Failed to load sources: ${e.message}`, 'error');
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
      if (!confirm(`Remove "${btn.dataset.name}" from nAI? Its files stay on the NAS; only the index is removed.`)) return;
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
    <div class="reindex-notice" role="alert">
      <strong>Semantic search is paused:</strong> the embedding model changed to
      ${escapeHtml(emb.model || 'a new model')}. The index still holds vectors from ${previous || 'an older model'}.
      Searches use keywords only until everything is re-embedded with the new model, which can take a while on
      large folders.
      <button id="reindexBtn" class="btn btn-primary">Re-index now</button>
    </div>`;
}

// NAI_EMBEDDINGS=auto turned semantic search off: the box has too little memory for the embedding model.
function keywordOnlyNotice(emb) {
  if (!emb || emb.mode !== 'auto-off') return '';
  return `
    <div class="reindex-notice" role="status">
      <strong>Keyword-only mode:</strong> this box has too little memory for semantic search
      (${escapeHtml(emb.reason || '')}). Searches match the words in your files. To turn semantic search on,
      give nAI at least 2.5 GB of memory (3 GB recommended) or set <code>NAI_EMBEDDINGS=on</code>.
    </div>`;
}

async function confirmReindex() {
  const btn = document.getElementById('reindexBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Starting…'; }
  try {
    const r = await apiCall('/system/embeddings/reindex', { method: 'POST' });
    showToast(r.reindexing ? `Re-indexing ${r.pending} passages in the background` : 'Nothing to re-index', 'success');
  } catch (e) {
    showToast(`Could not start the re-index: ${e.message}`, 'error');
  }
  loadSystemInfo();
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
      : emb.state === 'loading' ? 'downloading/loading model…'
      : emb.mode === 'auto-off' ? 'off (keyword-only: not enough memory)' : emb.state;
    const rows = [
      ['Hardware', `${hw.cpu_count} CPUs · ${hw.memory_gb} GB RAM · GPU: ${gpu} · tier: ${hw.tier}`],
      ['Semantic search', `${semantic}${emb.error ? ` (${emb.error})` : ''}`],
      ['Reranker', sys.features.reranker.active ? 'on' : 'off'],
      ['OCR', sys.features.ocr ? 'available' : 'not available'],
      ['Answer model', llm.enabled ? (llm.active_model ? `${llm.provider}/${llm.active_model}` : 'no model available') : 'off (extractive answers)'],
    ];
    elements.systemInfo.innerHTML = keywordOnlyNotice(emb) + reindexNotice(emb) + rows.map(([k, v]) => `
      <div class="system-row"><span class="system-key">${k}</span><span>${escapeHtml(v)}</span></div>
    `).join('') + `<ul class="system-tips">${sys.recommendations.map(r => `<li>${escapeHtml(r)}</li>`).join('')}</ul>`;
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
    elements.loginError.textContent = e.message;
    elements.loginError.classList.remove('hidden');
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
    elements.apiKeysList.innerHTML = keys.length ? keys.map(k => `
      <div class="document-item">
        <div class="document-info">
          <div class="document-name">${escapeHtml(k.name)}</div>
          <div class="document-meta">
            <span><code>${escapeHtml(k.prefix)}…</code></span>
            <span>created ${formatDate(k.created_at)}</span>
            <span>${k.last_used_at ? `used ${formatDate(k.last_used_at)}` : 'never used'}</span>
          </div>
        </div>
        <div class="document-actions">
          <button class="btn btn-ghost btn-sm" type="button" data-revoke-key="${escapeHtml(k.id)}">Revoke</button>
        </div>
      </div>`).join('') : '<p class="form-hint">No API keys yet.</p>';
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
    elements.apiKeyNew.innerHTML = `New key (copy it now, it won't be shown again):<br><code class="key-secret"></code>`;
    elements.apiKeyNew.querySelector('code').textContent = created.key;
    elements.apiKeyNew.classList.remove('hidden');
  } catch (e) {
    showToast(e.message, 'error');
  }
}

async function revokeApiKey(id) {
  if (!confirm('Revoke this API key? Apps using it will stop working.')) return;
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
  if (e.target === elements.uploadZone || e.target.closest('.upload-icon, .upload-title, .upload-subtitle')) {
    elements.fileInput.click();
  }
});
elements.fileInput.addEventListener('change', (e) => handleFiles(e.target.files));
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

// =============================================================================
// Initialization
// =============================================================================

applyTheme();
checkHealth();
initAuth();
setInterval(checkHealth, 30000); // Check health every 30 seconds
