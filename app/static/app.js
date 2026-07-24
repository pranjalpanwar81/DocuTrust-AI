const list = document.querySelector('#documentList');
const count = document.querySelector('#documentCount');
const uploadStatus = document.querySelector('#uploadStatus');
const answerSection = document.querySelector('#answerSection');
const sourceScope = document.querySelector('#sourceScope');
const voiceButton = document.querySelector('#voiceButton');
const voiceStatus = document.querySelector('#voiceStatus');
const readAnswerButton = document.querySelector('#readAnswerButton');
let recognition;

async function loadDocuments() {
  const response = await fetch('/api/v1/documents');
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
    const response = await fetch('/api/v1/documents', { method: 'POST', body: formData });
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
    const response = await fetch('/api/v1/query', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
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
  document.querySelector('#answerText').textContent = result.answer;
  if (result.corrections?.length) {
    const correctionText = result.corrections.map(item => `“${item.original}” to “${item.corrected}”`).join(', ');
    voiceStatus.textContent = `Spelling corrected automatically: ${correctionText}.`;
  }
  readAnswerButton.disabled = !result.answer;
  const badge = document.querySelector('#confidenceBadge');
  badge.textContent = `${Math.round(result.confidence * 100)}% confidence`;
  badge.className = `confidence ${result.answer_status === 'grounded' ? 'good' : 'low'}`;
  document.querySelector('#citations').innerHTML = result.citations.length ? result.citations.map((citation, index) => `
    <article class="citation"><span>[${index + 1}]</span><div><b>${escapeHtml(citation.document_name)} · Page ${citation.page}</b><p>“${escapeHtml(citation.supporting_quote)}”</p></div></article>`).join('') : '<p class="empty">No source citation was found. Upload a relevant document or ask a more specific question.</p>';
  answerSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

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
    const response = await fetch(url, { method: 'DELETE' });
    if (!response.ok) throw new Error('Delete request failed.');
    uploadStatus.textContent = `✓ ${message}`;
    answerSection.classList.add('hidden');
    await loadDocuments();
    await loadAnalytics();
  } catch (error) { uploadStatus.textContent = `Unable to delete document: ${error.message}`; }
}

async function loadAnalytics() {
  const response = await fetch('/api/v1/analytics');
  if (!response.ok) return;
  const stats = await response.json();
  document.querySelector('#metricDocuments').textContent = stats.document_count;
  document.querySelector('#metricChunks').textContent = stats.chunk_count;
  document.querySelector('#metricGrounded').textContent = `${Math.round(stats.grounded_rate * 100)}%`;
  document.querySelector('#metricConfidence').textContent = `${Math.round(stats.average_confidence * 100)}%`;
}

async function loadHistory() {
  const response = await fetch('/api/v1/query-history');
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
    const response = await fetch(`/api/v1/query-history/${eventId}`, { method: 'DELETE' });
    if (!response.ok) throw new Error('Delete request failed.');
    uploadStatus.textContent = '✓ Audit trail entry deleted.';
    await loadHistory();
  } catch (error) { uploadStatus.textContent = `Unable to delete audit entry: ${error.message}`; }
}
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
