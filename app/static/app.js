const list = document.querySelector('#documentList');
const count = document.querySelector('#documentCount');
const uploadStatus = document.querySelector('#uploadStatus');
const answerSection = document.querySelector('#answerSection');
const sourceScope = document.querySelector('#sourceScope');
const voiceButton = document.querySelector('#voiceButton');
const voiceStatus = document.querySelector('#voiceStatus');
const readAnswerButton = document.querySelector('#readAnswerButton');
let recognition;

// Authentication state
let authToken = localStorage.getItem('authToken');
let currentUser = JSON.parse(localStorage.getItem('currentUser') || 'null');

// Authentication helper functions
function getAuthHeaders() {
  const headers = {};
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }
  return headers;
}

function updateAuthUI() {
  const userInfo = document.querySelector('#userInfo');
  const userName = document.querySelector('#userName');
  const loginButton = document.querySelector('#loginButton');
  
  if (currentUser) {
    userInfo.classList.remove('hidden');
    userName.textContent = `${currentUser.username} (${currentUser.role})`;
    loginButton.classList.add('hidden');
  } else {
    userInfo.classList.add('hidden');
    loginButton.classList.remove('hidden');
  }
}

function handleAuthError(response) {
  if (response.status === 401 || response.status === 403) {
    logout();
    return true;
  }
  return false;
}

function logout() {
  authToken = null;
  currentUser = null;
  localStorage.removeItem('authToken');
  localStorage.removeItem('currentUser');
  updateAuthUI();
  loadDocuments(); // Will fail and show appropriate message
}

async function login(username, password) {
  try {
    const response = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Login failed');
    }
    
    const data = await response.json();
    authToken = data.access_token;
    currentUser = data.user;
    
    localStorage.setItem('authToken', authToken);
    localStorage.setItem('currentUser', JSON.stringify(currentUser));
    
    updateAuthUI();
    closeModal('loginModal');
    loadDocuments();
    loadAnalytics();
    
    return { success: true };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

async function register(username, email, password, role) {
  try {
    const response = await fetch('/api/v1/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, email, password, role })
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Registration failed');
    }
    
    return { success: true };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

// Modal functions
function openModal(modalId) {
  document.getElementById(modalId).classList.remove('hidden');
}

function closeModal(modalId) {
  document.getElementById(modalId).classList.add('hidden');
}

async function loadDocuments() {
  const response = await fetch('/api/v1/documents', {
    headers: getAuthHeaders()
  });
  
  if (handleAuthError(response)) {
    list.innerHTML = '<p class="empty">Please login to view documents.</p>';
    return;
  }
  
  const documents = await response.json();
  count.textContent = documents.length;
  const selectedScope = sourceScope.value;
  sourceScope.innerHTML = '<option value="all">All indexed documents</option>' + documents.map(document => `<option value="${document.id}">${escapeHtml(document.filename)}</option>`).join('');
  sourceScope.value = [...sourceScope.options].some(option => option.value === selectedScope) ? selectedScope : 'all';
  if (!documents.length) {
    list.innerHTML = '<p class="empty">No documents uploaded yet. Add a source document to begin.</p>';
    return;
  }
  list.innerHTML = documents.map(document => `
    <article class="document-row">
      <span class="file-icon">▤</span>
      <div><b>${escapeHtml(document.filename)}</b><small>${document.page_count} page${document.page_count === 1 ? '' : 's'} · ${escapeHtml(document.extraction_method.replace('_', ' '))}</small></div>
      <span class="indexed">● Indexed</span>
      <button class="delete-button" type="button" data-document-id="${document.id}" data-document-name="${escapeHtml(document.filename)}" aria-label="Delete ${escapeHtml(document.filename)}" title="Delete document"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 3h6l1 2h4v2H4V5h4l1-2Zm-3 6h12l-1 12H7L6 9Zm4 3v6h2v-6h-2Zm4 0v6h2v-6h-2Z"/></svg></button>
    </article>`).join('');
}

document.querySelector('#fileInput').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  uploadStatus.textContent = `Uploading ${file.name}…`;
  const formData = new FormData(); formData.append('file', file);
  try {
    const response = await fetch('/api/v1/documents', { 
      method: 'POST', 
      headers: getAuthHeaders(),
      body: formData 
    });
    
    if (handleAuthError(response)) {
      uploadStatus.textContent = 'Please login to upload documents.';
      return;
    }
    
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || 'Upload failed.');
    uploadStatus.textContent = `✓ ${body.filename} indexed successfully — ${body.chunk_count} evidence chunks created.`;
    event.target.value = '';
    await loadDocuments();
    await loadAnalytics();
  } catch (error) { uploadStatus.textContent = `Upload failed: ${error.message}`; }
});

document.querySelector('#queryForm').addEventListener('submit', async event => {
  event.preventDefault();
  const question = document.querySelector('#question').value.trim();
  const button = document.querySelector('#askButton');
  button.disabled = true; button.innerHTML = 'Finding evidence…';
  try {
    const selectedDocument = sourceScope.value;
    const payload = { question, ...(selectedDocument !== 'all' ? { document_ids: [selectedDocument] } : {}) };
    const response = await fetch('/api/v1/query', { 
      method: 'POST', 
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() }, 
      body: JSON.stringify(payload) 
    });
    
    if (handleAuthError(response)) {
      renderAnswer({ answer_status: 'insufficient_evidence', answer: 'Please login to ask questions.', confidence: 0, citations: [] });
      return;
    }
    
    const contentType = response.headers.get('content-type') || '';
    const body = contentType.includes('application/json') ? await response.json() : { detail: 'The server returned an unexpected response. Check the terminal and restart the server.' };
    if (!response.ok) throw new Error(body.detail || 'Unable to answer the question.');
    renderAnswer(body);
    await Promise.all([loadAnalytics(), loadHistory()]);
  } catch (error) {
    renderAnswer({ answer_status: 'insufficient_evidence', answer: error.message, confidence: 0, citations: [] });
  } finally { button.disabled = false; button.innerHTML = 'Ask DocuTrust <span>→</span>'; }
});

function renderAnswer(result) {
  answerSection.classList.remove('hidden');
  document.querySelector('#answerTitle').textContent = result.answer_status === 'grounded' ? 'Evidence-backed response' : 'More evidence needed';
  renderAnswerText(result.answer, result.answer_source);
  renderAnswerSource(result);
  if (result.corrections?.length) {
    const correctionText = result.corrections.map(item => `“${item.original}” to “${item.corrected}”`).join(', ');
    voiceStatus.textContent = `Spelling corrected automatically: ${correctionText}.`;
  }
  readAnswerButton.disabled = !result.answer;
  const badge = document.querySelector('#confidenceBadge');
  badge.textContent = `${Math.round(result.confidence * 100)}% confidence`;
  badge.className = `confidence ${result.answer_status === 'grounded' ? 'good' : 'low'}`;
  renderSourceVerification(result);
  answerSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderAnswerText(answer, answerSource) {
  const answerNode = document.querySelector('#answerText');
  if (answerSource === 'llm' && /\[(S\d+)\]/.test(answer || '')) {
    answerNode.innerHTML = escapeHtml(answer).replace(/\[(S\d+)\]/g, '<a class="source-ref" href="#$1" data-source-ref="$1">[$1]</a>');
    return;
  }
  answerNode.textContent = answer;
}

function renderAnswerSource(result) {
  const badge = document.querySelector('#answerSourceBadge');
  const meta = document.querySelector('#answerSourceMeta');
  badge.classList.remove('hidden', 'llm', 'deterministic', 'fallback', 'abstained');
  meta.classList.add('hidden');
  meta.textContent = '';

  if (result.answer_status !== 'grounded') {
    badge.textContent = 'No verified source';
    badge.classList.add('abstained');
    return;
  }

  if (result.answer_source === 'llm') {
    badge.textContent = 'LLM synthesized · cited';
    badge.classList.add('llm');
    return;
  }

  badge.textContent = 'Retrieved excerpt';
  badge.classList.add('deterministic');
  if (result.synthesis_error) {
    badge.classList.add('fallback');
    meta.classList.remove('hidden');
    meta.textContent = synthesisFallbackMessage(result.synthesis_error);
  }
}

function synthesisFallbackMessage(errorCode) {
  const messages = {
    api_key_missing: 'LLM synthesis is disabled — answer copied from retrieved evidence only.',
    timeout: 'LLM request timed out — answer copied from retrieved evidence only.',
    network_error: 'LLM provider unreachable — answer copied from retrieved evidence only.',
    malformed_response: 'LLM returned an unexpected response — answer copied from retrieved evidence only.',
    llm_abstained: 'LLM could not verify the claim from sources — answer copied from retrieved evidence only.',
  };
  if (messages[errorCode]) return messages[errorCode];
  if (errorCode?.startsWith('http_')) return `LLM API error (${errorCode.replace('http_', 'HTTP ')}) — answer copied from retrieved evidence only.`;
  return 'LLM synthesis unavailable — answer copied from retrieved evidence only.';
}

function renderSourceVerification(result) {
  const summary = document.querySelector('#sourceVerificationSummary');
  const citationsNode = document.querySelector('#citations');
  if (!result.citations.length) {
    summary.textContent = 'No indexed passage supported this question. Upload a relevant document or narrow your search scope.';
    citationsNode.innerHTML = '<p class="empty">No source citation was found. Upload a relevant document or ask a more specific question.</p>';
    return;
  }

  const documents = [...new Set(result.citations.map(citation => citation.document_name))];
  summary.textContent = documents.length === 1
    ? `Answer verified against 1 document: ${documents[0]}.`
    : `Answer verified against ${documents.length} documents: ${documents.join(', ')}.`;

  citationsNode.innerHTML = result.citations.map((citation, index) => {
    const sourceRef = `S${index + 1}`;
    const section = citation.section ? `<span class="citation-meta">Section · ${escapeHtml(citation.section)}</span>` : '';
    return `
      <article class="citation" id="${sourceRef}">
        <span class="citation-index">[${index + 1}]</span>
        <div class="citation-body">
          <div class="citation-title-row">
            <b>${escapeHtml(citation.document_name)} · Page ${citation.page}</b>
            <span class="citation-score">${Math.round(citation.relevance_score * 1000) / 10}% match</span>
          </div>
          <div class="citation-meta-row">
            ${section}
            <span class="citation-meta">Chunk · ${escapeHtml(citation.chunk_id)}</span>
          </div>
          <p class="citation-quote">“${escapeHtml(citation.supporting_quote)}”</p>
          <button class="scope-from-source" type="button" data-document-id="${citation.document_id}" data-document-name="${escapeHtml(citation.document_name)}">
            Search only this document ↗
          </button>
        </div>
      </article>`;
  }).join('');
}

document.querySelector('#citations').addEventListener('click', event => {
  const button = event.target.closest('.scope-from-source');
  if (!button) return;
  sourceScope.value = button.dataset.documentId;
  voiceStatus.textContent = `Search scope set to “${button.dataset.documentName}”. Ask your question again to verify against that source.`;
  document.querySelector('#ask').scrollIntoView({ behavior: 'smooth', block: 'center' });
});

document.querySelector('#answerText').addEventListener('click', event => {
  const link = event.target.closest('.source-ref');
  if (!link) return;
  event.preventDefault();
  const target = document.getElementById(link.dataset.sourceRef);
  if (!target) return;
  target.classList.add('citation-highlight');
  target.scrollIntoView({ behavior: 'smooth', block: 'center' });
  window.setTimeout(() => target.classList.remove('citation-highlight'), 1800);
});

function setupVoiceInput() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    voiceButton.disabled = true;
    voiceStatus.textContent = 'Voice input is not available in this browser. Try Chrome or Edge.';
    return;
  }
  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;
  recognition.onstart = () => {
    voiceButton.classList.add('listening');
    document.querySelector('#voiceButtonText').textContent = 'Listening...';
    voiceStatus.textContent = 'Speak your question in Hinglish or English.';
  };
  recognition.onresult = event => {
    let transcript = '';
    for (let index = event.resultIndex; index < event.results.length; index += 1) transcript += event.results[index][0].transcript;
    document.querySelector('#question').value = transcript.trim();
    if (event.results[event.results.length - 1].isFinal) voiceStatus.textContent = 'Voice question captured. Review it, then ask DocuTrust.';
  };
  recognition.onerror = event => {
    voiceStatus.textContent = event.error === 'not-allowed' ? 'Microphone permission was blocked. Allow it in your browser settings.' : `Voice input error: ${event.error}. Please try again.`;
  };
  recognition.onend = () => {
    voiceButton.classList.remove('listening');
    document.querySelector('#voiceButtonText').textContent = 'Speak question';
  };
}

voiceButton.addEventListener('click', () => {
  if (!recognition) return;
  recognition.lang = document.querySelector('#voiceLanguage').value;
  try { recognition.start(); } catch (error) { voiceStatus.textContent = 'Voice input is already listening. Please finish your question.'; }
});

readAnswerButton.addEventListener('click', () => {
  const text = document.querySelector('#answerText').textContent.trim();
  if (!text || !('speechSynthesis' in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = document.querySelector('#voiceLanguage').value;
  window.speechSynthesis.speak(utterance);
});

function escapeHtml(value) { const node = document.createElement('div'); node.textContent = value; return node.innerHTML; }
document.querySelector('#refreshButton').addEventListener('click', loadDocuments);
document.querySelector('#documentsNav').addEventListener('click', () => document.querySelector('#documentsSection').scrollIntoView({ behavior: 'smooth' }));
document.querySelector('#analyticsNav').addEventListener('click', () => document.querySelector('#analyticsSection').scrollIntoView({ behavior: 'smooth' }));
document.querySelector('#analyticsRefresh').addEventListener('click', loadAnalytics);
document.querySelector('#historyRefresh').addEventListener('click', loadHistory);
const themeToggle = document.querySelector('#themeToggle');
function setTheme(theme) {
  document.body.dataset.theme = theme;
  const isDark = theme === 'dark';
  document.querySelector('#themeIcon').textContent = isDark ? '☀' : '☾';
  themeToggle.setAttribute('aria-label', `Switch to ${isDark ? 'light' : 'dark'} theme`);
  themeToggle.title = themeToggle.getAttribute('aria-label');
  localStorage.setItem('docutrust-theme-v2', theme);
}
themeToggle.addEventListener('click', () => setTheme(document.body.dataset.theme === 'dark' ? 'light' : 'dark'));
setTheme(localStorage.getItem('docutrust-theme-v2') || 'dark');
list.addEventListener('click', async event => {
  const button = event.target.closest('.delete-button');
  if (!button || !confirm(`Delete “${button.dataset.documentName}”? This cannot be undone.`)) return;
  await deleteSources(`/api/v1/documents/${button.dataset.documentId}`, 'Document deleted.');
});
document.querySelector('#clearAllButton').addEventListener('click', async () => {
  if (!confirm('Delete every uploaded source document? This cannot be undone.')) return;
  await deleteSources('/api/v1/documents', 'All source documents deleted.');
});

async function deleteSources(url, message) {
  try {
    const response = await fetch(url, { 
      method: 'DELETE',
      headers: getAuthHeaders()
    });
    
    if (handleAuthError(response)) {
      uploadStatus.textContent = 'Please login to delete documents.';
      return;
    }
    
    if (!response.ok) throw new Error('Delete request failed.');
    uploadStatus.textContent = `✓ ${message}`;
    await loadDocuments();
    await loadAnalytics();
  } catch (error) { uploadStatus.textContent = `Delete failed: ${error.message}`; }
}

async function loadAnalytics() {
  const response = await fetch('/api/v1/analytics', {
    headers: getAuthHeaders()
  });
  
  if (handleAuthError(response)) {
    return;
  }
  
  if (!response.ok) return;
  const stats = await response.json();
  document.querySelector('#metricDocuments').textContent = stats.document_count;
  document.querySelector('#metricChunks').textContent = stats.chunk_count;
  document.querySelector('#metricGrounded').textContent = `${Math.round(stats.grounded_rate * 100)}%`;
  document.querySelector('#metricConfidence').textContent = `${Math.round(stats.average_confidence * 100)}%`;
}

async function loadHistory() {
  const response = await fetch('/api/v1/query-history', {
    headers: getAuthHeaders()
  });
  
  if (handleAuthError(response)) {
    return;
  }
  
  if (!response.ok) return;
  const events = await response.json();
  const history = document.querySelector('#historyList');
  if (!events.length) { history.innerHTML = '<p class="empty">Your recent questions will appear here.</p>'; return; }
  history.innerHTML = events.map(event => `<article class="history-row"><button class="history-question" type="button" data-question="${escapeHtml(event.question)}" title="Reuse this question">${escapeHtml(event.question)}</button><span class="history-meta ${event.answer_status === 'grounded' ? 'grounded' : 'ungrounded'}">${event.answer_status === 'grounded' ? 'Grounded' : 'Needs evidence'} · ${Math.round(event.confidence * 100)}%</span><button class="history-delete" type="button" data-event-id="${event.id}" aria-label="Delete audit event" title="Delete audit event"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 3h6l1 2h4v2H4V5h4l1-2Zm-3 6h12l-1 12H7L6 9Zm4 3v6h2v-6h-2Zm4 0v6h2v-6h-2Z"/></svg></button></article>`).join('');
}
document.querySelector('#historyList').addEventListener('click', event => {
  const deleteButton = event.target.closest('.history-delete');
  if (deleteButton) { deleteHistoryEvent(deleteButton.dataset.eventId); return; }
  const questionButton = event.target.closest('.history-question');
  if (!questionButton) return;
  document.querySelector('#question').value = questionButton.dataset.question;
  document.querySelector('#question').focus();
  document.querySelector('.ask-card').scrollIntoView({ behavior: 'smooth', block: 'center' });
});

async function deleteHistoryEvent(eventId) {
  if (!confirm('Delete this audit trail entry? This cannot be undone.')) return;
  try {
    const response = await fetch(`/api/v1/query-history/${eventId}`, { 
      method: 'DELETE',
      headers: getAuthHeaders()
    });
    
    if (handleAuthError(response)) {
      uploadStatus.textContent = 'Please login to delete audit entries.';
      return;
    }
    
    if (!response.ok) throw new Error('Delete request failed.');
    uploadStatus.textContent = '✓ Audit trail entry deleted.';
    await loadHistory();
  } catch (error) { uploadStatus.textContent = `Unable to delete audit entry: ${error.message}`; }
}

// Authentication event listeners
document.querySelector('#loginButton').addEventListener('click', () => {
  openModal('loginModal');
});

document.querySelector('#closeLoginModal').addEventListener('click', () => {
  closeModal('loginModal');
});

document.querySelector('#closeRegisterModal').addEventListener('click', () => {
  closeModal('registerModal');
});

document.querySelector('#showRegister').addEventListener('click', (e) => {
  e.preventDefault();
  closeModal('loginModal');
  openModal('registerModal');
});

document.querySelector('#showLogin').addEventListener('click', (e) => {
  e.preventDefault();
  closeModal('registerModal');
  openModal('loginModal');
});

document.querySelector('#logoutButton').addEventListener('click', () => {
  if (confirm('Are you sure you want to logout?')) {
    logout();
  }
});

document.querySelector('#loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const username = document.querySelector('#loginUsername').value;
  const password = document.querySelector('#loginPassword').value;
  
  const result = await login(username, password);
  if (!result.success) {
    alert(result.error);
  }
});

document.querySelector('#registerForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const username = document.querySelector('#registerUsername').value;
  const email = document.querySelector('#registerEmail').value;
  const password = document.querySelector('#registerPassword').value;
  const role = document.querySelector('#registerRole').value;
  
  const result = await register(username, email, password, role);
  if (result.success) {
    alert('Registration successful! Please login.');
    closeModal('registerModal');
    openModal('loginModal');
  } else {
    alert(result.error);
  }
});

// Close modals when clicking outside
document.querySelectorAll('.modal').forEach(modal => {
  modal.addEventListener('click', (e) => {
    if (e.target === modal) {
      modal.classList.add('hidden');
    }
  });
});

// Initialize auth UI
updateAuthUI();

Promise.all([loadDocuments(), loadAnalytics(), loadHistory()]);
setupVoiceInput();

document.querySelector('#heroUpload').addEventListener('click', () => document.querySelector('#fileInput').click());
document.querySelectorAll('[data-scroll-target]').forEach(button => {
  button.addEventListener('click', () => document.querySelector(`#${button.dataset.scrollTarget}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
});

const revealObserver = new IntersectionObserver(entries => {
  entries.forEach(entry => { if (entry.isIntersecting) { entry.target.classList.add('is-visible'); revealObserver.unobserve(entry.target); } });
}, { threshold: 0.12 });
document.querySelectorAll('.reveal').forEach(section => revealObserver.observe(section));
