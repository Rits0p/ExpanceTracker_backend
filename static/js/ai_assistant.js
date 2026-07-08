/**
 * AI Assistant — Premium Chat Interface
 * Django Expense Tracker
 */

const AI_API = '/api/v1/ai/assistant';
const EXPENSE_API = '/api/v1/expenses/';

// ── State ───────────────────────────────────────────────────────────
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let recordingTimer = null;
let recordingSeconds = 0;
let activeChatId = null;
let allChats = [];
let searchQuery = '';

const CHATS_API = '/api/chats/';

// ── DOM Refs ─────────────────────────────────────────────────────────
const feed = document.getElementById('aiFeed');
const welcome = document.getElementById('aiWelcome');
const textarea = document.getElementById('aiTextarea');
const sendBtn = document.getElementById('aiSendBtn');
const newChatBtn = document.getElementById('newChatBtn');
const uploadInput = document.getElementById('aiUploadInput');
const voiceOverlay = document.getElementById('aiVoiceOverlay');
const voiceTimer = document.getElementById('aiVoiceTimer');
const voiceStatus = document.getElementById('aiVoiceStatus');
const historyList = document.getElementById('aiHistoryList');

// ── Auto-grow textarea ────────────────────────────────────────────────
if (textarea) {
  textarea.addEventListener('input', () => {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 160) + 'px';
  });

  textarea.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
}

// ── Suggestions ───────────────────────────────────────────────────────
document.querySelectorAll('.ai-suggestion').forEach(card => {
  card.addEventListener('click', () => {
    const text = card.dataset.prompt;
    if (textarea) {
      textarea.value = text;
      textarea.style.height = 'auto';
      textarea.style.height = textarea.scrollHeight + 'px';
    }
    sendMessage();
  });
});

// ── Send Message ──────────────────────────────────────────────────────
if (sendBtn) {
  sendBtn.addEventListener('click', () => sendMessage());
}
if (newChatBtn) {
  newChatBtn.addEventListener('click', startNewChat);
}

async function sendMessage(overrideText) {
  const text = overrideText || (textarea ? textarea.value.trim() : '');
  if (!text) return;

  // If no active chat, create one first!
  if (!activeChatId) {
    try {
      const res = await fetch(CHATS_API, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCsrf() }
      });
      const data = await res.json();
      if (data.success && data.data) {
        const newChat = data.data;
        allChats.unshift(newChat);
        activeChatId = newChat.id;
        renderChatsList();
      } else {
        return;
      }
    } catch (err) {
      console.error('Failed to auto-create chat:', err);
      return;
    }
  }

  hideWelcome();
  appendUserMessage(text);
  if (textarea) {
    textarea.value = '';
    textarea.style.height = 'auto';
  }

  const typingEl = showTyping();
  scrollToBottom();

  const formData = new FormData();
  formData.append('text', text);

  try {
    const res = await fetch(`${CHATS_API}${activeChatId}/messages/`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf() },
      body: formData,
    });
    const data = await res.json();
    typingEl.remove();

    if (data.success && data.data) {
      const d = data.data;
      if (text === '📊 Show me my dashboard') {
        showDashboard(false);
      } else {
        appendAiMessage(d.message, d.crud_type || 'none', d.crud_record || null);
        if (d.crud_type === 'change_theme' && d.crud_record && d.crud_record.theme) {
          if (typeof Settings !== 'undefined') {
            Settings.set('theme', d.crud_record.theme);
          } else {
            // Fallback UI change
            if (d.crud_record.theme === 'light') {
              document.body.classList.add('light-mode');
            } else {
              document.body.classList.remove('light-mode');
            }
            if (typeof updateThemeIcon === 'function') updateThemeIcon();
            if (typeof updateChartsTheme === 'function') updateChartsTheme();
          }
        } else if (d.crud_type && d.crud_type !== 'none') {
          dispatchFinanceEvent(d.crud_type, d.crud_record || {});
          refreshExpenseList();
        }
      }

      // Auto-update chat title in list if it was a new chat
      const activeChat = allChats.find(c => c.id === activeChatId);
      if (activeChat && (activeChat.title === 'New Chat' || activeChat.title === '')) {
        let cleanTitle = text.slice(0, 40);
        if (text.length > 40) cleanTitle += '...';
        activeChat.title = cleanTitle;
        
        // update header title
        const titleEl = document.getElementById('activeChatTitle');
        if (titleEl) titleEl.textContent = cleanTitle;
        
        renderChatsList();
      }
    } else {
      appendAiMessage(data.message || 'Sorry, I could not process that. Please try again.', 'none', null);
    }
  } catch (err) {
    typingEl.remove();
    appendAiMessage('⚠️ Network error. Please check your connection and try again.', 'none', null);
  }

  scrollToBottom();
}

// Dispatch a custom event so any page component (expense list, dashboard) can listen & refresh
function dispatchFinanceEvent(action, record) {
  try {
    window.dispatchEvent(new CustomEvent('ai:finance:changed', {
      detail: { action, record }
    }));
  } catch (e) { }
}

// Refresh any visible expense table/list on the current page
async function refreshExpenseList() {
  try {
    const res = await fetch('/api/v1/expenses/?limit=10&page=1', {
      headers: { 'X-CSRFToken': getCsrf() }
    });
    const data = await res.json();
    if (!data.success) return;
    const expenses = data.data?.expenses || data.data || [];

    // Try to update a visible table body (id="expenseTableBody" or class="expense-list")
    const tableBody = document.getElementById('expenseTableBody') ||
      document.querySelector('.expense-table tbody') ||
      document.querySelector('[data-expense-list]');
    if (tableBody && expenses.length) {
      tableBody.innerHTML = expenses.slice(0, 10).map(e => `
        <tr>
          <td>${escapeHtml(e.title || '')}</td>
          <td>\u20b9${parseFloat(e.amount || 0).toLocaleString('en-IN')}</td>
          <td>${escapeHtml(e.category || '')}</td>
          <td>${escapeHtml(e.paymentMethod || e.payment_method || '')}</td>
          <td>${e.expenseDate ? new Date(e.expenseDate).toLocaleDateString('en-IN') : ''}</td>
        </tr>`).join('');
    }
  } catch (e) {
    // Silently fail if no expense list on page
  }
}


// ── Message Rendering ────────────────────────────────────────────────
function hideWelcome() {
  if (welcome) {
    welcome.style.opacity = '0';
    welcome.style.transition = 'opacity 0.3s';
    setTimeout(() => { welcome.style.display = 'none'; }, 300);
  }
}

function appendUserMessage(text) {
  const now = formatTime(new Date());
  const el = document.createElement('div');
  el.className = 'ai-msg user';
  el.innerHTML = `
    <div class="ai-msg-avatar">${getUserInitials()}</div>
    <div class="ai-msg-content">
      <div class="ai-bubble">${escapeHtml(text)}</div>
      <div class="ai-msg-meta">
        <span class="ai-msg-time">${now}</span>
      </div>
    </div>`;
  feed.appendChild(el);
}

function appendAiMessage(text, crudType = 'none', crudRecord = null) {
  const now = formatTime(new Date());
  const el = document.createElement('div');
  el.className = 'ai-msg assistant';

  const displayText = text || '';
  const bubbleContent = renderMarkdown(displayText);

  // CRUD badge
  const crudBadges = {
    created: { label: '✅ Created', color: '#10b981' },
    updated: { label: '✏️ Updated', color: '#3b82f6' },
    deleted: { label: '🗑️ Deleted', color: '#ef4444' },
  };
  const badge = crudBadges[crudType];
  const badgeHtml = badge
    ? `<span style="display:inline-block;margin-bottom:6px;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700;letter-spacing:.3px;background:${badge.color}22;color:${badge.color};border:1px solid ${badge.color}44">${badge.label}</span><br>`
    : '';

  // Inline record card for created/updated records
  let recordHtml = '';
  if (crudRecord && (crudType === 'created' || crudType === 'updated')) {

    // ── BUDGET card ──────────────────────────────────────────────────
    if (crudRecord.type === 'budget') {
      const fmt = v => parseFloat(v || 0).toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
      recordHtml = `
        <div style="margin-top:12px;background:var(--glass-bg,rgba(255,255,255,.04));border:1px solid rgba(255,255,255,.1);border-radius:14px;padding:14px 16px;">
          <div style="font-size:11px;font-weight:700;letter-spacing:.5px;opacity:.5;margin-bottom:10px;text-transform:uppercase;">💸 Budget — ${escapeHtml(crudRecord.month || '')}</div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;text-align:center;">
            <div style="background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.2);border-radius:10px;padding:10px 6px;">
              <div style="font-size:18px;font-weight:800;color:#10b981;">₹${fmt(crudRecord.daily)}</div>
              <div style="font-size:11px;opacity:.6;margin-top:3px;">Daily</div>
            </div>
            <div style="background:rgba(59,130,246,.08);border:1px solid rgba(59,130,246,.2);border-radius:10px;padding:10px 6px;">
              <div style="font-size:18px;font-weight:800;color:#3b82f6;">₹${fmt(crudRecord.weekly)}</div>
              <div style="font-size:11px;opacity:.6;margin-top:3px;">Weekly</div>
            </div>
            <div style="background:rgba(139,92,246,.08);border:1px solid rgba(139,92,246,.2);border-radius:10px;padding:10px 6px;">
              <div style="font-size:18px;font-weight:800;color:#8b5cf6;">₹${fmt(crudRecord.total)}</div>
              <div style="font-size:11px;opacity:.6;margin-top:3px;">Monthly</div>
            </div>
          </div>
          <div style="margin-top:10px;font-size:12px;">
            <a href="/budget" style="color:#10b981;font-weight:600;text-decoration:none;">View budget details →</a>
          </div>
        </div>`;

      // ── EXPENSE card ─────────────────────────────────────────────────
    } else if (crudRecord.title) {
      const amt = parseFloat(crudRecord.amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 });
      const date = crudRecord.expense_date ? new Date(crudRecord.expense_date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '';
      const catColors = { Food: '#f97316', Transport: '#3b82f6', Shopping: '#8b5cf6', Entertainment: '#ec4899', Utilities: '#14b8a6', Health: '#ef4444', Education: '#f59e0b', Other: '#6b7280' };
      const catColor = catColors[crudRecord.category] || '#10b981';
      recordHtml = `
        <div style="margin-top:10px;background:var(--glass-bg,rgba(255,255,255,.04));border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:12px 14px;display:flex;align-items:center;gap:12px;">
          <div style="width:40px;height:40px;border-radius:10px;background:${catColor}22;border:1px solid ${catColor}44;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:18px;">💸</div>
          <div style="flex:1;min-width:0;">
            <div style="font-weight:700;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(crudRecord.title)}</div>
            <div style="font-size:12px;opacity:.6;margin-top:2px;">${escapeHtml(crudRecord.category)} &bull; ${escapeHtml(crudRecord.payment_method || '')} &bull; ${date}</div>
          </div>
          <div style="font-weight:800;font-size:16px;color:${catColor};white-space:nowrap;">₹${amt}</div>
        </div>
        <div style="margin-top:8px;">
          <a href="/expenses" style="font-size:12px;color:#10b981;font-weight:600;text-decoration:none;">View all expenses →</a>
        </div>`;
    }
  }


  el.innerHTML = `
    <div class="ai-msg-avatar">
      <svg class="ai-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <path d="M12 2a5 5 0 0 0-5 5v2H6a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-6a2 2 0 0 0-2-2h-1V7a5 5 0 0 0-5-5Z"/>
        <path d="M9 10V7a3 3 0 0 1 6 0v3"/>
      </svg>
    </div>
    <div class="ai-msg-content">
      <div class="ai-bubble">${badgeHtml}${bubbleContent}${recordHtml}</div>
      <div class="ai-msg-meta">
        <span class="ai-msg-time">${now}</span>
        <button class="ai-copy-btn" onclick="copyText(this, '${escapeAttr(displayText)}')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          Copy
        </button>
      </div>
    </div>`;
  feed.appendChild(el);
}


function buildExpenseCard(d) {
  const id = 'ec_' + Date.now();
  return `
  <div class="expense-card" id="${id}">
    <div class="expense-card-header">
      <span class="ai-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18"/></svg></span>
      <h4>Expense Detected</h4>
      <span class="expense-card-badge">Review Required</span>
    </div>
    <div class="expense-card-body">
      <div class="expense-field">
        <label>Expense Title</label>
        <input type="text" id="${id}_title" value="${escapeAttr(d.title || '')}" placeholder="e.g. Grocery Shopping">
      </div>
      <div class="expense-field-row">
        <div class="expense-field">
          <label>Amount (₹)</label>
          <input type="number" id="${id}_amount" value="${d.amount || ''}" placeholder="0.00">
        </div>
        <div class="expense-field">
          <label>Category</label>
          <select id="${id}_category">
            ${['Food', 'Transport', 'Shopping', 'Entertainment', 'Utilities', 'Health', 'Education', 'Other']
      .map(c => `<option value="${c}" ${c === d.category ? 'selected' : ''}>${c}</option>`).join('')}
          </select>
        </div>
      </div>
      <div class="expense-field-row">
        <div class="expense-field">
          <label>Date</label>
          <input type="date" id="${id}_date" value="${(d.expense_date || '').slice(0, 10) || today()}">
        </div>
        <div class="expense-field">
          <label>Payment Method</label>
          <select id="${id}_method">
            ${['Cash', 'Credit Card', 'Debit Card', 'UPI', 'Bank Transfer', 'Auto Pay', 'Other']
      .map(m => `<option value="${m}" ${m === d.payment_method ? 'selected' : ''}>${m}</option>`).join('')}
          </select>
        </div>
      </div>
      ${d.notes ? `<div class="expense-field"><label>Notes</label><input type="text" id="${id}_notes" value="${escapeAttr(d.notes)}"></div>` : ''}
    </div>
    <div class="expense-card-actions">
      <button class="btn-save" onclick="saveExpenseCard('${id}')"><span class="ai-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 12.5 10.5 16 17 8"/><path d="M5 5h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z"/></svg></span> Save Expense</button>
      <button class="btn-cancel" onclick="document.getElementById('${id}').remove()">Cancel</button>
    </div>
  </div>`;
}

async function saveExpenseCard(id) {
  const title = document.getElementById(`${id}_title`).value.trim();
  const amount = document.getElementById(`${id}_amount`).value;
  const category = document.getElementById(`${id}_category`).value;
  const date = document.getElementById(`${id}_date`).value;
  const method = document.getElementById(`${id}_method`).value;
  const notesEl = document.getElementById(`${id}_notes`);
  const notes = notesEl ? notesEl.value : '';

  if (!title || !amount) {
    alert('Please fill in Title and Amount.');
    return;
  }

  const btn = document.querySelector(`#${id} .btn-save`);
  btn.textContent = 'Saving...';
  btn.disabled = true;

  const payload = {
    title, amount: parseFloat(amount),
    category, payment_method: method,
    expense_date: new Date(date).toISOString(),
    notes
  };

  try {
    const res = await fetch(EXPENSE_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body: JSON.stringify({
        title: payload.title,
        amount: payload.amount,
        category: payload.category,
        paymentMethod: payload.payment_method,
        expenseDate: payload.expense_date,
        notes: payload.notes
      })
    });
    const data = await res.json();
    if (data.success || res.ok) {
      document.getElementById(id).innerHTML = `
        <div style="padding:16px 18px; display:flex; align-items:center; gap:10px; color:var(--accent-success); font-weight:700;">
          <span class="ai-icon" style="width:20px;height:20px;"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6 9 17l-5-5"/></svg></span>
          Expense "<strong>${escapeHtml(title)}</strong>" saved successfully!
        </div>`;
    } else {
      btn.textContent = '💾 Save Expense';
      btn.disabled = false;
      alert(data.message || 'Failed to save expense. Please try again.');
    }
  } catch (err) {
    btn.textContent = '💾 Save Expense';
    btn.disabled = false;
    alert('Network error. Please try again.');
  }
}

// ── Receipt Upload ────────────────────────────────────────────────────
if (document.getElementById('aiUploadBtn')) {
  document.getElementById('aiUploadBtn').addEventListener('click', () => {
    document.getElementById('aiUploadInput').click();
  });
}
if (document.getElementById('aiHeaderUploadBtn')) {
  document.getElementById('aiHeaderUploadBtn').addEventListener('click', () => {
    document.getElementById('aiUploadInput').click();
  });
}

if (uploadInput) {
  uploadInput.addEventListener('change', async () => {
    const file = uploadInput.files[0];
    if (!file) return;

    // If no active chat, create one first!
    if (!activeChatId) {
      await startNewChatSilent();
    }

    hideWelcome();
    uploadInput.value = '';

    appendUserMessage(`📎 Uploading receipt: ${file.name}`);
    const typingEl = showTyping();
    scrollToBottom();

    const formData = new FormData();
    formData.append('image', file);
    formData.append('text', `📎 Uploading receipt: ${file.name}`);

    try {
      const res = await fetch(`${CHATS_API}${activeChatId}/messages/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCsrf() },
        body: formData,
      });
      const data = await res.json();
      typingEl.remove();

      if (data.success && data.data) {
        const d = data.data;
        appendAiMessage(d.message, d.crud_type || 'none', d.crud_record || null);
        
        // Auto-update chat title in list if it was a new chat
        const activeChat = allChats.find(c => c.id === activeChatId);
        if (activeChat && (activeChat.title === 'New Chat' || activeChat.title === '')) {
          const cleanTitle = `Receipt: ${file.name}`;
          activeChat.title = cleanTitle;
          const titleEl = document.getElementById('activeChatTitle');
          if (titleEl) titleEl.textContent = cleanTitle;
          renderChatsList();
        }
      } else {
        appendAiMessage(data.message || 'Could not read this receipt. Please try a clearer image.');
      }
    } catch (err) {
      typingEl.remove();
      appendAiMessage('⚠️ Network error. Please try again.');
    }
    scrollToBottom();
  });
}

function appendReceiptMessage(file, d) {
  const now = formatTime(new Date());
  const id = 'rc_' + Date.now();
  const imgUrl = URL.createObjectURL(file);
  const el = document.createElement('div');
  el.className = 'ai-msg assistant';
  el.innerHTML = `
    <div class="ai-msg-avatar">🤖</div>
    <div class="ai-msg-content">
      <div class="ai-bubble">📄 I've analyzed your receipt. Here's what I found:</div>
      <div class="ai-msg-extra">
        <div class="receipt-card" id="${id}">
          <div class="receipt-header">
            <div class="receipt-icon">🧾</div>
            <div class="receipt-header-info">
              <h4>${escapeHtml(d.title || 'Receipt')}</h4>
              <p>Detected from uploaded image</p>
            </div>
            <div class="receipt-confidence">~90% confidence</div>
          </div>
          <img class="receipt-img-preview" src="${imgUrl}" alt="Receipt">
          <div class="receipt-body">
            <div class="receipt-item"><span class="receipt-item-name">Category</span><span class="receipt-item-price">${escapeHtml(d.category || 'Other')}</span></div>
            <div class="receipt-item"><span class="receipt-item-name">Payment</span><span class="receipt-item-price">${escapeHtml(d.payment_method || 'Cash')}</span></div>
            <div class="receipt-total"><span>Total Amount</span><span>₹${d.amount || '0.00'}</span></div>
          </div>
          <div class="receipt-actions">
            <button class="btn-save" onclick="confirmReceiptExpense('${id}', ${JSON.stringify(d).replace(/'/g, '&#39;')})">💾 Save Expense</button>
            <button class="btn-discard" onclick="document.getElementById('${id}').remove()">Discard</button>
          </div>
        </div>
      </div>
      <div class="ai-msg-meta"><span class="ai-msg-time">${now}</span></div>
    </div>`;
  feed.appendChild(el);
}

function confirmReceiptExpense(id, d) {
  // Replace receipt card with expense confirmation card
  const card = document.getElementById(id);
  if (card) {
    const wrapper = card.parentElement;
    wrapper.innerHTML = buildExpenseCard(d);
  }
}

// ── Voice Recording ───────────────────────────────────────────────────
function openVoice() {
  if (voiceOverlay) voiceOverlay.classList.add('active');
  startRecording();
}

function closeVoice() {
  if (voiceOverlay) voiceOverlay.classList.remove('active');
  stopRecording(true);
}

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      if (!isRecording) return; // Cancelled
      const mimeType = mediaRecorder.mimeType || 'audio/webm';
      const blob = new Blob(audioChunks, { type: mimeType });
      closeVoice();
      processAudio(blob, mimeType);
    };
    mediaRecorder.start();
    isRecording = true;
    recordingSeconds = 0;
    if (voiceTimer) voiceTimer.textContent = '0:00';
    if (voiceStatus) voiceStatus.textContent = 'Listening...';
    recordingTimer = setInterval(() => {
      recordingSeconds++;
      const m = Math.floor(recordingSeconds / 60);
      const s = recordingSeconds % 60;
      if (voiceTimer) voiceTimer.textContent = `${m}:${s.toString().padStart(2, '0')}`;
      if (recordingSeconds >= 60) stopRecording(false);
    }, 1000);
  } catch (err) {
    closeVoice();
    alert('Microphone access denied. Please enable it in your browser settings.');
  }
}

function stopRecording(cancel) {
  clearInterval(recordingTimer);
  if (cancel) {
    isRecording = false;
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      const origOnStop = mediaRecorder.onstop;
      mediaRecorder.onstop = null;
      mediaRecorder.stop();
    }
    return;
  }
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
  }
}

async function processAudio(blob, mimeType) {
  // If no active chat, create one first!
  if (!activeChatId) {
    await startNewChatSilent();
  }

  hideWelcome();
  appendUserMessage('🎤 Voice message recorded');
  const typingEl = showTyping();
  scrollToBottom();

  const formData = new FormData();
  let ext = 'webm';
  if (mimeType && mimeType.includes('mp4')) ext = 'mp4';
  else if (mimeType && mimeType.includes('ogg')) ext = 'ogg';

  formData.append('audio', blob, `recording.${ext}`);
  formData.append('text', '🎤 Voice message recorded');

  try {
    const res = await fetch(`${CHATS_API}${activeChatId}/messages/`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf() },
      body: formData,
    });
    const data = await res.json();
    typingEl.remove();

    if (data.success && data.data) {
      const d = data.data;
      appendAiMessage(d.message, d.crud_type || 'none', d.crud_record || null);
      
      // Auto-update chat title in list if it was a new chat
      const activeChat = allChats.find(c => c.id === activeChatId);
      if (activeChat && (activeChat.title === 'New Chat' || activeChat.title === '')) {
        const cleanTitle = 'Voice Message';
        activeChat.title = cleanTitle;
        const titleEl = document.getElementById('activeChatTitle');
        if (titleEl) titleEl.textContent = cleanTitle;
        renderChatsList();
      }
    } else {
      appendAiMessage(data.message || 'Could not process voice input. Please try again.');
    }
  } catch (err) {
    typingEl.remove();
    appendAiMessage('⚠️ Network error. Please try again.');
  }
  scrollToBottom();
}



// ── Typing Indicator ─────────────────────────────────────────────────
function showTyping() {
  const wrap = document.createElement('div');
  wrap.className = 'ai-msg assistant';
  wrap.innerHTML = `
    <div class="ai-msg-avatar">🤖</div>
    <div class="ai-msg-content">
      <div class="ai-typing">
        <span></span><span></span><span></span>
      </div>
    </div>`;
  feed.appendChild(wrap);
  return wrap;
}

// ── Dashboard Preview ─────────────────────────────────────────────────
async function showDashboard(saveToHistory = true) {
  if (saveToHistory) {
    sendMessage('📊 Show me my dashboard');
    return;
  }
  const typingEl = showTyping();
  scrollToBottom();

  // Fetch real KPI data
  let kpiData = null;
  try {
    const r = await fetch('/api/v1/analytics/kpis');
    const j = await r.json();
    if (j.success) kpiData = j.data;
  } catch (e) { }

  typingEl.remove();

  const now = formatTime(new Date());
  const total = kpiData ? formatCurrency(kpiData.totalExpenses || 0) : '₹0';
  const budget = kpiData ? formatCurrency(kpiData.totalBudget || 0) : '₹0';
  const remaining = kpiData ? formatCurrency((kpiData.totalBudget || 0) - (kpiData.totalExpenses || 0)) : '₹0';
  const topCat = kpiData ? (kpiData.topCategory || 'N/A') : 'N/A';

  const el = document.createElement('div');
  el.className = 'ai-msg assistant';
  el.innerHTML = `
    <div class="ai-msg-avatar">🤖</div>
    <div class="ai-msg-content">
      <div class="ai-bubble">📊 Here's your financial overview for this month:</div>
      <div class="ai-msg-extra">
        <div class="ai-dashboard-cards">
          <div class="ai-dash-card">
            <div class="ai-dash-card-label">Total Expenses</div>
            <div class="ai-dash-card-value">${total}</div>
            <div class="ai-dash-card-sub">This month</div>
          </div>
          <div class="ai-dash-card emerald">
            <div class="ai-dash-card-label">Remaining Budget</div>
            <div class="ai-dash-card-value">${remaining}</div>
            <div class="ai-dash-card-sub">of ${budget} budget</div>
          </div>
          <div class="ai-dash-card">
            <div class="ai-dash-card-label">Monthly Budget</div>
            <div class="ai-dash-card-value">${budget}</div>
            <div class="ai-dash-card-sub">Configured</div>
          </div>
          <div class="ai-dash-card">
            <div class="ai-dash-card-label">Top Category</div>
            <div class="ai-dash-card-value" style="font-size:16px;">${topCat}</div>
            <div class="ai-dash-card-sub">Highest spending</div>
          </div>
        </div>
        <div style="margin-top:10px;">
          <a href="/" style="display:inline-flex;align-items:center;gap:6px;color:var(--ai-emerald);font-size:13px;font-weight:600;text-decoration:none;">
            View full dashboard →
          </a>
        </div>
      </div>
      <div class="ai-msg-meta"><span class="ai-msg-time">${now}</span></div>
    </div>`;
  feed.appendChild(el);
  scrollToBottom();
}

// ── Utilities ─────────────────────────────────────────────────────────
function getUserInitials() {
  const name = document.body.dataset.username || 'U';
  return name.charAt(0).toUpperCase();
}

function scrollToBottom() {
  if (feed) {
    setTimeout(() => { feed.scrollTop = feed.scrollHeight; }, 50);
  }
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function formatTime(d) {
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatCurrency(n) {
  return '₹' + parseFloat(n).toLocaleString('en-IN', { minimumFractionDigits: 0 });
}

function escapeHtml(t) {
  return String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function escapeAttr(t) {
  return String(t || '').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function renderMarkdown(text) {
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/^### (.*)/gm, '<h3>$1</h3>')
    .replace(/^## (.*)/gm, '<h3>$1</h3>')
    .replace(/^- (.*)/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>');
}

function copyText(btn, text) {
  navigator.clipboard.writeText(text).then(() => {
    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> Copied!`;
    setTimeout(() => {
      btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy`;
    }, 1500);
  });
}

// ── ChatGPT-style History Module Functions ───────────────────────────
async function loadChats() {
  try {
    const res = await fetch(CHATS_API, {
      headers: { 'X-CSRFToken': getCsrf() }
    });
    const data = await res.json();
    if (data.success) {
      allChats = data.data || [];
      renderChatsList();
      
      // Open active chat or the first chat if none is active
      if (allChats.length > 0) {
        if (!activeChatId || !allChats.some(c => c.id === activeChatId)) {
          openChat(allChats[0].id);
        } else {
          renderActiveChatState();
        }
      } else {
        activeChatId = null;
        showWelcome();
        if (feed) feed.innerHTML = '';
      }
    }
  } catch (err) {
    console.error('Error loading chats:', err);
  }
}

function groupChatsByDate(chats) {
  const groups = {
    today: [],
    yesterday: [],
    week: [],
    older: []
  };

  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  
  const yesterdayStart = new Date(todayStart);
  yesterdayStart.setDate(yesterdayStart.getDate() - 1);
  
  const weekStart = new Date(todayStart);
  weekStart.setDate(weekStart.getDate() - 7);

  chats.forEach(chat => {
    const updated = new Date(chat.updatedAt || chat.createdAt || new Date());
    if (updated >= todayStart) {
      groups.today.push(chat);
    } else if (updated >= yesterdayStart) {
      groups.yesterday.push(chat);
    } else if (updated >= weekStart) {
      groups.week.push(chat);
    } else {
      groups.older.push(chat);
    }
  });

  return groups;
}

function renderChatsList() {
  if (!historyList) return;
  historyList.innerHTML = '';

  const filtered = allChats.filter(chat =>
    chat.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const groups = groupChatsByDate(filtered);
  const groupLabels = {
    today: 'Today',
    yesterday: 'Yesterday',
    week: 'Previous 7 Days',
    older: 'Older'
  };

  Object.keys(groups).forEach(key => {
    const list = groups[key];
    if (list.length === 0) return;

    const header = document.createElement('div');
    header.className = 'ai-history-group-header';
    header.textContent = groupLabels[key];
    historyList.appendChild(header);

    list.forEach(chat => {
      const isActive = chat.id === activeChatId;
      const item = document.createElement('div');
      item.className = `ai-history-item${isActive ? ' active' : ''}`;
      item.dataset.id = chat.id;

      item.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        <span class="ai-history-item-text" id="chat-title-text-${chat.id}">${escapeHtml(chat.title)}</span>
        <input type="text" class="ai-history-item-input" id="chat-title-input-${chat.id}" value="${escapeHtml(chat.title)}" style="display: none;">
        <div class="ai-history-actions">
          <button class="ai-history-act-btn edit-btn" onclick="startRenameChat(event, ${chat.id})" title="Rename">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          </button>
          <button class="ai-history-act-btn delete-btn" onclick="triggerDeleteChat(event, ${chat.id})" title="Delete">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        </div>
      `;

      item.addEventListener('click', (e) => {
        if (e.target.closest('.ai-history-actions') || e.target.closest('input')) return;
        openChat(chat.id);
      });

      const input = item.querySelector('input');
      if (input) {
        input.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            saveRenameChat(chat.id, input.value);
          } else if (e.key === 'Escape') {
            cancelRenameChat(chat.id);
          }
        });
        input.addEventListener('blur', () => {
          saveRenameChat(chat.id, input.value);
        });
      }

      historyList.appendChild(item);
    });
  });
}

function startRenameChat(event, chatId) {
  event.stopPropagation();
  const textSpan = document.getElementById(`chat-title-text-${chatId}`);
  const inputEl = document.getElementById(`chat-title-input-${chatId}`);
  if (textSpan && inputEl) {
    textSpan.style.display = 'none';
    inputEl.style.display = 'block';
    inputEl.focus();
    inputEl.select();
  }
}

async function saveRenameChat(chatId, newTitle) {
  const textSpan = document.getElementById(`chat-title-text-${chatId}`);
  const inputEl = document.getElementById(`chat-title-input-${chatId}`);
  const title = newTitle.trim();
  
  if (!title) {
    cancelRenameChat(chatId);
    return;
  }

  if (textSpan && inputEl) {
    textSpan.textContent = title;
    textSpan.style.display = 'block';
    inputEl.style.display = 'none';
  }

  try {
    const res = await fetch(`${CHATS_API}${chatId}/`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrf()
      },
      body: JSON.stringify({ title })
    });
    const data = await res.json();
    if (data.success) {
      const chat = allChats.find(c => c.id === chatId);
      if (chat) chat.title = title;
      
      if (chatId === activeChatId) {
        const titleEl = document.getElementById('activeChatTitle');
        if (titleEl) titleEl.textContent = title;
      }
    } else {
      loadChats();
    }
  } catch (err) {
    loadChats();
  }
}

function cancelRenameChat(chatId) {
  const textSpan = document.getElementById(`chat-title-text-${chatId}`);
  const inputEl = document.getElementById(`chat-title-input-${chatId}`);
  if (textSpan && inputEl) {
    inputEl.value = textSpan.textContent;
    textSpan.style.display = 'block';
    inputEl.style.display = 'none';
  }
}

async function triggerDeleteChat(event, chatId) {
  event.stopPropagation();
  if (!confirm('Are you sure you want to delete this conversation?')) return;

  try {
    const res = await fetch(`${CHATS_API}${chatId}/`, {
      method: 'DELETE',
      headers: { 'X-CSRFToken': getCsrf() }
    });
    const data = await res.json();
    if (data.success) {
      allChats = allChats.filter(c => c.id !== chatId);
      if (activeChatId === chatId) {
        activeChatId = allChats.length > 0 ? allChats[0].id : null;
      }
      renderChatsList();
      if (activeChatId) {
        openChat(activeChatId);
      } else {
        showWelcome();
        if (feed) feed.innerHTML = '';
        const titleEl = document.getElementById('activeChatTitle');
        if (titleEl) titleEl.textContent = 'AI Expense Assistant';
      }
    }
  } catch (err) {
    console.error('Error deleting chat:', err);
  }
}

async function startNewChat() {
  try {
    const res = await fetch(CHATS_API, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf() }
    });
    const data = await res.json();
    if (data.success && data.data) {
      const newChat = data.data;
      allChats.unshift(newChat);
      activeChatId = newChat.id;
      renderChatsList();
      openChat(newChat.id);
    }
  } catch (err) {
    console.error('Error creating new chat:', err);
  }
}

async function startNewChatSilent() {
  try {
    const res = await fetch(CHATS_API, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf() }
    });
    const data = await res.json();
    if (data.success && data.data) {
      const newChat = data.data;
      allChats.unshift(newChat);
      activeChatId = newChat.id;
      renderChatsList();
    }
  } catch (e) {}
}

async function openChat(chatId) {
  activeChatId = chatId;
  renderActiveChatState();

  if (feed) feed.innerHTML = '';
  hideWelcome();

  const typingEl = showTyping();
  scrollToBottom();

  try {
    const res = await fetch(`${CHATS_API}${chatId}/`, {
      headers: { 'X-CSRFToken': getCsrf() }
    });
    const data = await res.json();
    typingEl.remove();

    if (data.success && data.data) {
      const chat = data.data;
      
      const titleEl = document.getElementById('activeChatTitle');
      if (titleEl) titleEl.textContent = chat.title;

      const messages = chat.messages || [];
      if (messages.length === 0) {
        showWelcome();
      } else {
        messages.forEach(msg => {
          if (msg.role === 'user') {
            appendUserMessage(msg.content);
          } else if (msg.isDashboard) {
            showDashboard(false);
          } else {
            appendAiMessage(msg.content, msg.crudType || 'none', msg.crudRecord || null);
          }
        });
        scrollToBottom();
      }
    }
  } catch (err) {
    typingEl.remove();
    console.error('Error opening chat:', err);
  }
}

function renderActiveChatState() {
  document.querySelectorAll('.ai-history-item').forEach(item => {
    const id = parseInt(item.dataset.id);
    if (id === activeChatId) {
      item.classList.add('active');
    } else {
      item.classList.remove('active');
    }
  });
}

function handleSearch(query) {
  searchQuery = query;
  renderChatsList();
}

function getCsrf() {
  const name = 'csrftoken';
  for (const c of document.cookie.split(';')) {
    const [k, v] = c.trim().split('=');
    if (k === name) return decodeURIComponent(v);
  }
  const el = document.querySelector('[name=csrfmiddlewaretoken]');
  return el ? el.value : '';
}

// Load chat history from database on load
document.addEventListener('DOMContentLoaded', async () => {
  await loadChats();
});
