/* ═══════════════════════════════════════════════════════════════
   Recurring Expense Management — JavaScript Module
   Handles CRUD operations, filtering, pagination, and modals
   Dependencies: auth.js (Auth.apiFetch), app.js (showToast, openModal, closeModal)
   ═══════════════════════════════════════════════════════════════ */

let state = {
  currentPage: 1,
  pageSize: 10,
  totalItems: 0,
  currentData: [],
  filters: { search: '', category: '', frequency: '', status: '', sort: '-next_due_date' },
  historyPage: 1,
  historyPageSize: 10,
  selectedId: null,
};

/* ───── Helpers ───── */
function getStatus(re) {
  if (!re.isActive) return 'paused';
  const today = new Date().toISOString().split('T')[0];
  if (re.endDate && re.endDate < today) return 'completed';
  if (re.nextDueDate < today) return 'overdue';
  return 'active';
}

function formatDate(dateStr) {
  if (!dateStr) return '—';
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatCurrency(n) {
  return '$' + parseFloat(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function getCategoryColor(cat) {
  const colors = { '#10b981': '#10b981', '#06b6d4': '#06b6d4', '#8b5cf6': '#8b5cf6', '#f59e0b': '#f59e0b', '#ef4444': '#ef4444', '#ec4899': '#ec4899', '#6366f1': '#6366f1' };
  return cat && cat.color ? cat.color : '#447D9B';
}

function getCategoryIcon(cat) {
  return cat && cat.icon ? cat.icon : 'ph-package';
}

/* ───── Toast Notifications ───── */
function notify(message, type) {
  if (typeof showToast === 'function') showToast(message, type);
  else alert(message);
}

/* ───── API Calls ───── */
async function apiGet(url) {
  if (typeof Auth !== 'undefined' && Auth.apiFetch) {
    const res = await Auth.apiFetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.message || `HTTP ${res.status}`);
    }
    return res.json();
  }
  const res = await fetch(url, { credentials: 'include', headers: { 'X-CSRFToken': getCSRF() } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function apiPost(url, data) {
  if (typeof Auth !== 'undefined' && Auth.apiFetch) {
    const res = await Auth.apiFetch(url, { method: 'POST', body: JSON.stringify(data), headers: { 'Content-Type': 'application/json' } });
    const json = await res.json();
    if (!res.ok) throw json;
    return json;
  }
  const res = await fetch(url, { method: 'POST', credentials: 'include', headers: { 'X-CSRFToken': getCSRF(), 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
  const json = await res.json();
  if (!res.ok) throw json;
  return json;
}

async function apiPut(url, data) {
  if (typeof Auth !== 'undefined' && Auth.apiFetch) {
    const res = await Auth.apiFetch(url, { method: 'PUT', body: JSON.stringify(data), headers: { 'Content-Type': 'application/json' } });
    const json = await res.json();
    if (!res.ok) throw json;
    return json;
  }
  const res = await fetch(url, { method: 'PUT', credentials: 'include', headers: { 'X-CSRFToken': getCSRF(), 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
  const json = await res.json();
  if (!res.ok) throw json;
  return json;
}

async function apiPatch(url, data) {
  if (typeof Auth !== 'undefined' && Auth.apiFetch) {
    const res = await Auth.apiFetch(url, { method: 'PATCH', body: JSON.stringify(data), headers: { 'Content-Type': 'application/json' } });
    const json = await res.json();
    if (!res.ok) throw json;
    return json;
  }
  const res = await fetch(url, { method: 'PATCH', credentials: 'include', headers: { 'X-CSRFToken': getCSRF(), 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
  const json = await res.json();
  if (!res.ok) throw json;
  return json;
}

async function apiDelete(url) {
  if (typeof Auth !== 'undefined' && Auth.apiFetch) {
    const res = await Auth.apiFetch(url, { method: 'DELETE' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json().catch(() => ({}));
  }
  const res = await fetch(url, { method: 'DELETE', credentials: 'include', headers: { 'X-CSRFToken': getCSRF() } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json().catch(() => ({}));
}

function getCSRF() {
  const m = document.cookie.match(/csrftoken=([^;]+)/);
  return m ? m[1] : document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
}

/* ═══════════════════════════════════════════════════════════════
   LIST PAGE
   ═══════════════════════════════════════════════════════════════ */
async function loadRecurringExpenses() {
  const { listUrl, analyticsUrl } = window._recurringConfig || {};
  const tbody = document.getElementById('recurringTableBody');
  const emptyState = document.getElementById('emptyState');
  const errorState = document.getElementById('errorState');
  const pagination = document.getElementById('recurringPagination');

  try {
    if (analyticsUrl) {
      apiGet(analyticsUrl).then(data => {
        if (data.success && data.data) renderKPIs(data.data);
      }).catch(() => {});
    }

    const params = new URLSearchParams({
      page: state.currentPage,
      limit: state.pageSize,
      ordering: state.filters.sort,
    });
    if (state.filters.search) params.set('search', state.filters.search);
    if (state.filters.frequency) params.set('frequency', state.filters.frequency);
    if (state.filters.status === 'active') params.set('isActive', 'true');
    if (state.filters.status === 'paused') params.set('isActive', 'false');

    const json = await apiGet(`${listUrl}?${params}`);
    const records = json.data || [];
    const meta = json.meta || {};
    state.totalItems = meta.total || records.length;

    if (records.length === 0) {
      tbody.innerHTML = '';
      emptyState.style.display = 'block';
      errorState.style.display = 'none';
      pagination.style.display = 'none';
      return;
    }

    emptyState.style.display = 'none';
    errorState.style.display = 'none';
    state.currentData = records;
    renderTable(records);
    renderPagination(meta);
  } catch (err) {
    tbody.innerHTML = '';
    emptyState.style.display = 'none';
    errorState.style.display = 'block';
    pagination.style.display = 'none';
    document.getElementById('errorMessage').textContent = err.message || 'Unable to load recurring expenses.';
  }
}

function renderKPIs(data) {
  const animate = (id, val, prefix, suffix) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (typeof animateCounter === 'function') animateCounter(el, val, prefix || '', suffix || '', 800);
    else el.textContent = (prefix || '') + (val ?? '—') + (suffix || '');
  };
  animate('totalRecurring', data.totalRecurring);
  animate('monthlyRecurringCost', data.monthlyRecurringCost, '$');
  animate('upcomingCount', data.upcomingPayments?.length || 0);
  animate('overdueCount', data.overduePayments?.length || 0);
}

function renderTable(records) {
  const tbody = document.getElementById('recurringTableBody');
  tbody.innerHTML = records.map(re => {
    const status = getStatus(re);
    const cat = re.categoryDetails || {};
    const icon = getCategoryIcon(cat);
    const color = getCategoryColor(cat);
    const catName = cat.name || re.category || 'Uncategorized';
    const freqIcon = { daily: 'ph-clock', weekly: 'ph-calendar-week', monthly: 'ph-calendar', quarterly: 'ph-calendar', yearly: 'ph-calendar' }[re.frequency] || 'ph-clock';

    return `<tr>
      <td data-label="Category">
        <div class="category-cell">
          <div class="category-icon" style="background:${color}"><i class="ph ${icon}"></i></div>
          <span class="category-name">${escHtml(catName)}</span>
        </div>
      </td>
      <td data-label="Name"><strong>${escHtml(re.title)}</strong></td>
      <td data-label="Amount" class="amount-cell">${formatCurrency(re.amount)}</td>
      <td data-label="Frequency">
        <span class="freq-badge"><i class="ph ${freqIcon}"></i> ${re.frequencyDisplay || re.frequency}</span>
      </td>
      <td data-label="Next Due">${formatDate(re.nextDueDate)}</td>
      <td data-label="Status">
        <span class="status-badge ${status}"><span class="dot"></span>${status}</span>
      </td>
      <td data-label="Created">${formatDate(re.createdAt?.split('T')[0])}</td>
      <td data-label="Actions" class="actions-col">
        <div class="actions-cell">
          <a href="/recurring-expenses/${re.id}/" class="btn btn-sm btn-secondary" title="View details"><i class="ph ph-eye"></i></a>
          <a href="/recurring-expenses/${re.id}/edit/" class="btn btn-sm btn-secondary" title="Edit"><i class="ph ph-pencil"></i></a>
          ${status === 'paused'
            ? `<button class="btn btn-sm btn-secondary" onclick="openResumeModal(${re.id},'${escHtml(re.title)}')" title="Resume"><i class="ph ph-play"></i></button>`
            : `<button class="btn btn-sm btn-secondary" onclick="openPauseModal(${re.id},'${escHtml(re.title)}')" title="Pause"><i class="ph ph-pause"></i></button>`
          }
          <button class="btn btn-sm btn-danger-ghost" onclick="openDeleteModal(${re.id},'${escHtml(re.title)}')" title="Delete"><i class="ph ph-trash"></i></button>
        </div>
      </td>
    </tr>`;
  }).join('');
}

function escHtml(s) {
  if (!s) return '';
  return String(s).replace(/[&<>"']/g, function(m) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m];
  });
}

function renderPagination(meta) {
  const wrap = document.getElementById('recurringPagination');
  if (!wrap) return;
  const total = meta.total || state.currentData.length;
  const page = meta.page || state.currentPage;
  const limit = meta.limit || state.pageSize;
  const totalPages = meta.totalPages || Math.ceil(total / limit) || 1;

  document.getElementById('showingStart').textContent = total === 0 ? 0 : (page - 1) * limit + 1;
  document.getElementById('showingEnd').textContent = Math.min(page * limit, total);
  document.getElementById('totalResults').textContent = total;

  document.getElementById('prevPageBtn').disabled = page <= 1;
  document.getElementById('nextPageBtn').disabled = page >= totalPages;

  const nums = document.getElementById('pageNumbers');
  let html = '';
  const start = Math.max(1, page - 2);
  const end = Math.min(totalPages, page + 2);
  if (start > 1) { html += `<button class="page-num" data-p="1">1</button>`; if (start > 2) html += `<span class="page-num" style="border:none;cursor:default">…</span>`; }
  for (let i = start; i <= end; i++) html += `<button class="page-num ${i === page ? 'active' : ''}" data-p="${i}">${i}</button>`;
  if (end < totalPages) { if (end < totalPages - 1) html += `<span class="page-num" style="border:none;cursor:default">…</span>`; html += `<button class="page-num" data-p="${totalPages}">${totalPages}</button>`; }
  nums.innerHTML = html;
  nums.querySelectorAll('.page-num[data-p]').forEach(el => el.addEventListener('click', () => { state.currentPage = parseInt(el.dataset.p); loadRecurringExpenses(); }));

  wrap.style.display = 'flex';
}

function initFilters() {
  ['searchInput', 'categoryFilter', 'frequencyFilter', 'statusFilter', 'sortFilter'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('change', () => {
      state.filters.search = document.getElementById('searchInput')?.value || '';
      state.filters.frequency = document.getElementById('frequencyFilter')?.value || '';
      state.filters.status = document.getElementById('statusFilter')?.value || '';
      state.filters.sort = document.getElementById('sortFilter')?.value || '-next_due_date';
      state.currentPage = 1;
      loadRecurringExpenses();
    });
  });

  const searchInput = document.getElementById('searchInput');
  if (searchInput) {
    let timer;
    searchInput.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        state.filters.search = searchInput.value;
        state.currentPage = 1;
        loadRecurringExpenses();
      }, 300);
    });
  }

  document.getElementById('prevPageBtn')?.addEventListener('click', () => {
    if (state.currentPage > 1) { state.currentPage--; loadRecurringExpenses(); }
  });
  document.getElementById('nextPageBtn')?.addEventListener('click', () => {
    state.currentPage++; loadRecurringExpenses();
  });
}

/* ───── Modal Actions ───── */
function openDeleteModal(id, title) {
  state.selectedId = id;
  document.getElementById('deleteItemName').textContent = title || 'this recurring expense';
  document.getElementById('confirmDeleteBtn').dataset.id = id;
  if (typeof openModal === 'function') openModal('deleteModal');
  else document.getElementById('deleteModal').classList.add('active');
}

openDeleteModal = openDeleteModal; // hoist

document.addEventListener('click', function(e) {
  if (e.target.id === 'confirmDeleteBtn') {
    const id = e.target.dataset.id;
    if (!id) return;
    if (typeof closeModal === 'function') closeModal('deleteModal');
    else document.getElementById('deleteModal').classList.remove('active');
    performDelete(id);
  }
  if (e.target.id === 'confirmPauseBtn') {
    const id = e.target.dataset.id;
    if (!id) return;
    if (typeof closeModal === 'function') closeModal('pauseModal');
    else document.getElementById('pauseModal').classList.remove('active');
    performPause(id);
  }
  if (e.target.id === 'confirmResumeBtn') {
    const id = e.target.dataset.id;
    if (!id) return;
    if (typeof closeModal === 'function') closeModal('resumeModal');
    else document.getElementById('resumeModal').classList.remove('active');
    performResume(id);
  }
});

function openPauseModal(id, title) {
  state.selectedId = id;
  document.getElementById('pauseItemName').textContent = title || 'this recurring expense';
  document.getElementById('confirmPauseBtn').dataset.id = id;
  if (typeof openModal === 'function') openModal('pauseModal');
  else document.getElementById('pauseModal').classList.add('active');
}

function openResumeModal(id, title) {
  state.selectedId = id;
  document.getElementById('resumeItemName').textContent = title || 'this recurring expense';
  document.getElementById('confirmResumeBtn').dataset.id = id;
  if (typeof openModal === 'function') openModal('resumeModal');
  else document.getElementById('resumeModal').classList.add('active');
}

async function performDelete(id) {
  try {
    await apiDelete(`/api/v1/recurring-expenses/${id}/`);
    notify('Recurring expense deleted successfully', 'success');
    loadRecurringExpenses();
  } catch (err) {
    notify(err.message || 'Failed to delete', 'error');
  }
}

async function performPause(id) {
  try {
    await apiPatch(`/api/v1/recurring-expenses/${id}/`, { isActive: false });
    notify('Recurring expense paused successfully', 'success');
    loadRecurringExpenses();
  } catch (err) {
    notify(err.message || 'Failed to pause', 'error');
  }
}

async function performResume(id) {
  try {
    await apiPatch(`/api/v1/recurring-expenses/${id}/`, { isActive: true });
    notify('Recurring expense resumed successfully', 'success');
    loadRecurringExpenses();
  } catch (err) {
    notify(err.message || 'Failed to resume', 'error');
  }
}

/* ═══════════════════════════════════════════════════════════════
   DETAIL PAGE
   ═══════════════════════════════════════════════════════════════ */
async function initDetailPage(config) {
  window._detailConfig = config;
  try {
    const json = await apiGet(`${config.listUrl}${config.recurringId}/`);
    if (!json.success) throw new Error(json.message || 'Not found');
    renderDetail(json.data);
    loadHistory(config.recurringId, config.expenseUrl);
  } catch (err) {
    document.getElementById('detailLoading').style.display = 'none';
    document.getElementById('detailError').style.display = 'block';
    document.getElementById('detailErrorMessage').textContent = err.message || 'Recurring expense not found';
  }
}

function renderDetail(re) {
  document.getElementById('detailLoading').style.display = 'none';
  document.getElementById('detailContent').style.display = 'block';

  document.getElementById('detailBreadcrumb').textContent = re.title;
  document.getElementById('detailTitle').textContent = re.title;
  const cat = re.categoryDetails || {};
  const color = getCategoryColor(cat);
  const icon = getCategoryIcon(cat);
  document.getElementById('detailCategory').innerHTML = `<span class="category-icon" style="background:${color};display:inline-flex;width:28px;height:28px;font-size:14px;margin-right:8px;vertical-align:middle"><i class="ph ${icon}"></i></span> ${escHtml(cat.name || 'Uncategorized')}`;
  document.getElementById('detailAmount').textContent = formatCurrency(re.amount);
  document.getElementById('detailFrequency').textContent = re.frequencyDisplay || re.frequency;
  document.getElementById('detailNextDue').textContent = formatDate(re.nextDueDate);
  document.getElementById('detailStartDate').textContent = formatDate(re.startDate);
  document.getElementById('detailEndDate').textContent = re.endDate ? formatDate(re.endDate) : 'No end date';
  document.getElementById('detailNotes').textContent = re.notes || 'No notes';

  const status = getStatus(re);
  document.getElementById('detailStatus').innerHTML = `<span class="status-badge ${status}"><span class="dot"></span>${status}</span>`;

  const editBtn = document.getElementById('editRecurringBtn');
  if (editBtn) editBtn.href = `/recurring-expenses/${re.id}/edit/`;

  const pauseBtn = document.getElementById('pauseResumeBtn');
  if (pauseBtn) {
    if (status === 'paused') {
      pauseBtn.innerHTML = '<i class="ph ph-play"></i> Resume';
      pauseBtn.className = 'btn btn-secondary';
      pauseBtn.onclick = () => openResumeModal(re.id, re.title);
    } else {
      pauseBtn.innerHTML = '<i class="ph ph-pause"></i> Pause';
      pauseBtn.className = 'btn btn-secondary';
      pauseBtn.onclick = () => openPauseModal(re.id, re.title);
    }
  }

  // Stats
  document.getElementById('statUpcomingDue').textContent = formatDate(re.nextDueDate);
}

function openDeleteModal() {
  const config = window._detailConfig;
  openDeleteModal(config.recurringId, document.getElementById('detailTitle').textContent);
}

async function loadHistory(recurringId, expenseUrl) {
  try {
    const params = new URLSearchParams({
      page: state.historyPage,
      limit: state.historyPageSize,
      recurringExpense: recurringId,
    });
    const json = await apiGet(`${expenseUrl}?${params}`);
    const records = json.data || [];
    const meta = json.meta || {};

    const tbody = document.getElementById('historyTableBody');
    if (records.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4"><div class="table-loader">No generated expenses found.</div></td></tr>';
      document.getElementById('historyPagination').style.display = 'none';
      return;
    }

    tbody.innerHTML = records.map(e => {
      const d = e.expenseDate ? new Date(e.expenseDate) : null;
      const dateStr = d ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—';
      const month = d ? d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' }) : '—';
      return `<tr>
        <td data-label="Date">${dateStr}</td>
        <td data-label="Amount" class="amount-cell">${formatCurrency(e.amount)}</td>
        <td data-label="Category">${escHtml(e.category)}</td>
        <td data-label="Budget Month">${month}</td>
      </tr>`;
    }).join('');

    document.getElementById('historyPagination').style.display = 'flex';
    document.getElementById('histShowingStart').textContent = records.length > 0 ? (state.historyPage - 1) * state.historyPageSize + 1 : 0;
    document.getElementById('histShowingEnd').textContent = Math.min(state.historyPage * state.historyPageSize, meta.total || records.length);
    document.getElementById('histTotal').textContent = meta.total || records.length;

    const totalPages = meta.totalPages || Math.ceil((meta.total || records.length) / state.historyPageSize) || 1;
    document.getElementById('histPrevBtn').disabled = state.historyPage <= 1;
    document.getElementById('histNextBtn').disabled = state.historyPage >= totalPages;

    // Stats
    const totalAmount = records.reduce((s, e) => s + parseFloat(e.amount || 0), 0);
    document.getElementById('statTotalGenerated').textContent = meta.total || records.length;
    document.getElementById('statTotalAmount').textContent = formatCurrency(totalAmount);
    document.getElementById('statLastGenerated').textContent = records.length > 0 ? formatDate(records[0].expenseDate?.split('T')[0]) : '—';
  } catch (err) {
    document.getElementById('historyTableBody').innerHTML = '<tr><td colspan="4"><div class="table-loader">Failed to load history.</div></td></tr>';
  }
}

/* ═══════════════════════════════════════════════════════════════
   FORM PAGE (Create / Update)
   ═══════════════════════════════════════════════════════════════ */
async function initFormPage(config) {
  const form = document.getElementById('recurringForm');
  if (!form) return;

  const submitBtn = document.getElementById('submitBtn');

  // Update mode: pre-fill form
  if (config.mode === 'update' && config.recurringId) {
    try {
      const json = await apiGet(`${config.apiUrl}${config.recurringId}/`);
      if (!json.success) throw new Error(json.message || 'Not found');
      fillForm(json.data);
      document.getElementById('loadState').style.display = 'none';
      document.getElementById('formCard').style.display = 'block';
    } catch (err) {
      document.getElementById('loadState').style.display = 'none';
      document.getElementById('loadError').style.display = 'block';
      return;
    }
  } else {
    document.getElementById('loadState')?.style.remove();
    document.getElementById('formCard').style.display = 'block';
  }

  // Form validation and submit
  form.addEventListener('submit', async function(e) {
    e.preventDefault();
    clearErrors();

    const title = document.getElementById('title').value.trim();
    const category = document.getElementById('category').value;
    const amount = document.getElementById('amount').value;
    const frequency = document.getElementById('frequency').value;
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    const notes = document.getElementById('notes').value.trim();
    const isActive = document.getElementById('activeToggle')?.classList.contains('active') ?? true;

    // Client-side validation
    let valid = true;
    if (!title) { showError('titleError', 'Title is required'); valid = false; }
    if (!category) { showError('categoryError', 'Please select a category'); valid = false; }
    if (!amount || parseFloat(amount) <= 0) { showError('amountError', 'Amount must be greater than 0'); valid = false; }
    if (!frequency) { showError('frequencyError', 'Please select a frequency'); valid = false; }
    if (!startDate) { showError('startDateError', 'Start date is required'); valid = false; }
    if (endDate && startDate && endDate <= startDate) { showError('endDateError', 'End date must be after start date'); valid = false; }
    if (!valid) return;

    const payload = { title, category: parseInt(category), amount: parseFloat(amount), frequency, startDate, notes, isActive };
    if (endDate) payload.endDate = endDate;

    submitBtn.disabled = true;
    document.getElementById('formLoading').style.display = 'flex';

    try {
      let json;
      if (config.mode === 'update') {
        json = await apiPut(`${config.apiUrl}${config.recurringId}/`, payload);
      } else {
        json = await apiPost(config.apiUrl, payload);
      }

      if (json.success) {
        notify(config.mode === 'update' ? 'Recurring expense updated successfully' : 'Recurring expense created successfully', 'success');
        window.location.href = config.mode === 'update' ? (config.detailUrl || '/recurring-expenses/') : '/recurring-expenses/';
      } else {
        handleApiErrors(json);
      }
    } catch (err) {
      if (err.errors) handleApiErrors(err);
      else {
        notify(err.message || 'An error occurred. Please try again.', 'error');
      }
    } finally {
      submitBtn.disabled = false;
      document.getElementById('formLoading').style.display = 'none';
    }
  });
}

function fillForm(data) {
  document.getElementById('title').value = data.title || '';
  if (data.category) document.getElementById('category').value = data.category;
  document.getElementById('amount').value = data.amount || '';
  if (data.frequency) document.getElementById('frequency').value = data.frequency;
  document.getElementById('startDate').value = data.startDate || '';
  document.getElementById('endDate').value = data.endDate || '';
  document.getElementById('notes').value = data.notes || '';
  const toggle = document.getElementById('activeToggle');
  if (toggle) {
    if (data.isActive) toggle.classList.add('active');
    else toggle.classList.remove('active');
  }
}

function showError(id, msg) {
  const el = document.getElementById(id);
  if (el) { el.textContent = msg; el.style.display = 'block'; }
}

function clearErrors() {
  document.querySelectorAll('.form-error-text').forEach(el => {
    el.textContent = '';
    el.style.display = 'none';
  });
  document.querySelectorAll('.form-input, .form-select').forEach(el => el.classList.remove('input-error'));
}

function handleApiErrors(json) {
  const errors = json.errors || {};
  const map = {
    title: 'titleError', category: 'categoryError', amount: 'amountError',
    frequency: 'frequencyError', startDate: 'startDateError', endDate: 'endDateError',
    notes: 'titleError', isActive: 'titleError',
  };
  let first = true;
  for (const [field, msg] of Object.entries(errors)) {
    const errId = map[field];
    const message = Array.isArray(msg) ? msg[0] : msg;
    if (errId) { showError(errId, message); const input = document.getElementById(field); if (input) input.classList.add('input-error'); }
    else if (first) { notify(message, 'error'); first = false; }
  }
  if (!Object.keys(errors).length && json.message) notify(json.message, 'error');
}

/* ═══════════════════════════════════════════════════════════════
   INITIALIZATION
   ═══════════════════════════════════════════════════════════════ */
function initRecurringPage(config) {
  window._recurringConfig = config;
  initFilters();
  loadRecurringExpenses();
}
