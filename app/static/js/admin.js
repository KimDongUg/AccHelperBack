let currentPage = 1;
const PAGE_SIZE = 10;
let deleteTargetId = null;
let sessionCheckTimer = null;
let currentSearchTerm = '';

/* ═══════════════════════════════════════════════
 *  INIT
 * ═══════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', async () => {
    // Auth guard
    if (!AuthSession.isValid()) { AuthSession.redirectToLogin(); return; }
    try {
        const auth = await apiGet('/auth/check');
        if (!auth.authenticated) { AuthSession.redirectToLogin(); return; }
        if (auth.session) {
            const persist = !!localStorage.getItem('acc_auth_session');
            AuthSession.save(auth.session, persist);
        }
        document.getElementById('adminUsername').textContent = auth.session.username + '님';
    } catch { AuthSession.redirectToLogin(); return; }

    // Session watcher
    sessionCheckTimer = setInterval(() => {
        if (!AuthSession.isValid()) {
            clearInterval(sessionCheckTimer);
            showToast('세션이 만료되었습니다.', 'warning');
            setTimeout(() => AuthSession.redirectToLogin(), 1500);
        }
    }, 60_000);

    // Load data
    loadStats();
    loadQaList();

    // Search debounce
    let searchTimer;
    document.getElementById('searchInput').addEventListener('input', () => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => { currentPage = 1; loadQaList(); }, 300);
    });

    document.getElementById('categoryFilter').addEventListener('change', () => { currentPage = 1; loadQaList(); });
    document.getElementById('statusFilter').addEventListener('change', () => { currentPage = 1; loadQaList(); });

    // Logout
    document.getElementById('logoutBtn').addEventListener('click', async () => {
        clearInterval(sessionCheckTimer);
        try { await apiPost('/auth/logout', {}); } catch {}
        AuthSession.clear();
        window.location.href = '/login.html';
    });

    // Modal field validation
    document.getElementById('modalQuestion').addEventListener('input', onQuestionInput);
    document.getElementById('modalAnswer').addEventListener('input', onAnswerInput);
});

/* ═══════════════════════════════════════════════
 *  TOAST
 * ═══════════════════════════════════════════════ */
function showToast(message, type = 'success') {
    const container = document.getElementById('toastContainer');
    const icons = {
        success: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
        error: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        warning: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
    };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.success}</span>
        <span class="toast-msg">${escapeHtml(message)}</span>
        <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
    `;
    container.appendChild(toast);
    setTimeout(() => {
        toast.classList.add('removing');
        setTimeout(() => toast.remove(), 250);
    }, 3500);
}

/* ═══════════════════════════════════════════════
 *  STATS
 * ═══════════════════════════════════════════════ */
async function loadStats() {
    try {
        const s = await apiGet('/stats');
        document.getElementById('statTotal').textContent = s.total_qa;
        document.getElementById('statActive').textContent = s.active_qa;
        document.getElementById('statToday').textContent = s.today_chats;
    } catch (e) {
        console.error('Stats load error:', e);
    }
}

/* ═══════════════════════════════════════════════
 *  QA LIST
 * ═══════════════════════════════════════════════ */
async function loadQaList() {
    const search = document.getElementById('searchInput').value.trim();
    const category = document.getElementById('categoryFilter').value;
    const status = document.getElementById('statusFilter').value;
    currentSearchTerm = search;

    const params = new URLSearchParams({ page: currentPage, size: PAGE_SIZE });
    if (search) params.append('search', search);
    if (category) params.append('category', category);
    if (status) params.append('status', status);

    document.getElementById('tableLoading').classList.add('show');
    try {
        const data = await apiGet(`/qa?${params}`);
        renderTable(data.items);
        renderPagination(data.page, data.pages, data.total);
    } catch (e) {
        console.error('QA list error:', e);
    } finally {
        document.getElementById('tableLoading').classList.remove('show');
    }
}

/* ── Highlight helper ─────────────────────────── */
function highlightText(text, maxLen) {
    let safe = escapeHtml(text);
    if (maxLen && text.length > maxLen) {
        safe = escapeHtml(text.substring(0, maxLen)) + '&hellip;';
    }
    if (!currentSearchTerm) return safe;
    const escaped = escapeHtml(currentSearchTerm).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return safe.replace(new RegExp(`(${escaped})`, 'gi'), '<mark>$1</mark>');
}

function renderTable(items) {
    const tbody = document.getElementById('qaTableBody');
    const empty = document.getElementById('emptyState');

    if (items.length === 0) {
        tbody.innerHTML = '';
        empty.style.display = 'block';
        return;
    }

    empty.style.display = 'none';
    tbody.innerHTML = items.map(qa => `
        <tr>
            <td>${qa.qa_id}</td>
            <td><span class="badge badge-category">${qa.category}</span></td>
            <td class="question-cell" title="${escapeHtml(qa.question)}">${highlightText(qa.question, 100)}</td>
            <td class="answer-cell" title="${escapeHtml(qa.answer)}">${highlightText(qa.answer, 150)}</td>
            <td>
                <button class="toggle-btn ${qa.is_active ? 'active' : ''}" onclick="toggleActive(${qa.qa_id})" role="switch" aria-checked="${qa.is_active}" aria-label="Q&A ${qa.qa_id} ${qa.is_active ? '활성' : '비활성'}" title="${qa.is_active ? '활성' : '비활성'}"></button>
            </td>
            <td>${formatDate(qa.updated_at)}</td>
            <td>
                <div class="actions">
                    <button class="btn btn-outline btn-sm" onclick="openEditModal(${qa.qa_id})" aria-label="Q&A ${qa.qa_id} 수정">수정</button>
                    <button class="btn btn-danger btn-sm" onclick="openDeleteConfirm(${qa.qa_id})" aria-label="Q&A ${qa.qa_id} 삭제">삭제</button>
                </div>
            </td>
        </tr>
    `).join('');
}

function renderPagination(page, pages, total) {
    const container = document.getElementById('pagination');
    if (pages <= 1) { container.innerHTML = ''; return; }

    let html = `<button ${page <= 1 ? 'disabled' : ''} onclick="goToPage(${page - 1})">&laquo;</button>`;
    const start = Math.max(1, page - 2);
    const end = Math.min(pages, page + 2);

    if (start > 1) {
        html += `<button onclick="goToPage(1)">1</button>`;
        if (start > 2) html += `<button disabled>...</button>`;
    }
    for (let i = start; i <= end; i++) {
        html += `<button class="${i === page ? 'active' : ''}" onclick="goToPage(${i})">${i}</button>`;
    }
    if (end < pages) {
        if (end < pages - 1) html += `<button disabled>...</button>`;
        html += `<button onclick="goToPage(${pages})">${pages}</button>`;
    }
    html += `<button ${page >= pages ? 'disabled' : ''} onclick="goToPage(${page + 1})">&raquo;</button>`;
    container.innerHTML = html;
}

function goToPage(page) {
    currentPage = page;
    loadQaList();
}

async function toggleActive(qaId) {
    try {
        const qa = await apiPatch(`/qa/${qaId}/toggle`);
        showToast(qa.is_active ? 'Q&A가 활성화되었습니다.' : 'Q&A가 비활성화되었습니다.', 'success');
        loadQaList();
        loadStats();
    } catch (e) {
        showToast('상태 변경에 실패했습니다: ' + e.message, 'error');
    }
}

/* ═══════════════════════════════════════════════
 *  MODAL — validation helpers
 * ═══════════════════════════════════════════════ */
function onQuestionInput() {
    const val = document.getElementById('modalQuestion').value.trim();
    const hint = document.getElementById('questionHint');
    if (val.length === 0) {
        hint.textContent = '';
        hint.className = 'field-hint';
    } else if (val.length < 5) {
        hint.textContent = `${val.length}/5자 (최소 5자)`;
        hint.className = 'field-hint error';
    } else {
        hint.textContent = `${val.length}자`;
        hint.className = 'field-hint ok';
        checkDuplicate(val);
    }
}

function onAnswerInput() {
    const val = document.getElementById('modalAnswer').value.trim();
    const hint = document.getElementById('answerHint');
    if (val.length === 0) {
        hint.textContent = '';
        hint.className = 'field-hint';
    } else if (val.length < 10) {
        hint.textContent = `${val.length}/10자 (최소 10자)`;
        hint.className = 'field-hint error';
    } else {
        hint.textContent = `${val.length}자`;
        hint.className = 'field-hint ok';
    }
}

let dupTimer = null;
async function checkDuplicate(question) {
    clearTimeout(dupTimer);
    dupTimer = setTimeout(async () => {
        const warn = document.getElementById('duplicateWarn');
        try {
            const excludeId = document.getElementById('editQaId').value || '';
            const params = new URLSearchParams({ question });
            if (excludeId) params.append('exclude_id', excludeId);
            const res = await apiGet(`/qa/check-duplicate?${params}`);
            if (res.duplicates && res.duplicates.length > 0) {
                const items = res.duplicates.map(d =>
                    `• [ID ${d.qa_id}] ${escapeHtml(d.question.substring(0, 60))} (유사도 ${d.similarity}%)`
                ).join('<br>');
                warn.innerHTML = `<strong>유사한 질문이 있습니다:</strong><br>${items}`;
                warn.style.display = 'block';
            } else {
                warn.style.display = 'none';
            }
        } catch {
            warn.style.display = 'none';
        }
    }, 500);
}

function validateModal() {
    const question = document.getElementById('modalQuestion').value.trim();
    const answer = document.getElementById('modalAnswer').value.trim();
    const errors = [];

    if (question.length < 5) errors.push('질문은 최소 5자 이상 입력해 주세요.');
    if (answer.length < 10) errors.push('답변은 최소 10자 이상 입력해 주세요.');

    if (errors.length > 0) {
        showToast(errors[0], 'error');
        // Trigger hints
        onQuestionInput();
        onAnswerInput();
        return false;
    }
    return true;
}

/* ═══════════════════════════════════════════════
 *  MODAL — open / close / save
 * ═══════════════════════════════════════════════ */
function resetModalHints() {
    document.getElementById('questionHint').textContent = '';
    document.getElementById('questionHint').className = 'field-hint';
    document.getElementById('answerHint').textContent = '';
    document.getElementById('answerHint').className = 'field-hint';
    document.getElementById('duplicateWarn').style.display = 'none';
}

function openCreateModal() {
    document.getElementById('modalTitle').textContent = '새 Q&A 추가';
    document.getElementById('editQaId').value = '';
    document.getElementById('modalCategory').value = '세금';
    document.getElementById('modalQuestion').value = '';
    document.getElementById('modalAnswer').value = '';
    document.getElementById('modalKeywords').value = '';
    document.getElementById('modalActive').checked = true;
    resetModalHints();
    document.getElementById('qaModal').classList.add('show');
}

async function openEditModal(qaId) {
    try {
        const qa = await apiGet(`/qa/${qaId}`);
        document.getElementById('modalTitle').textContent = 'Q&A 수정';
        document.getElementById('editQaId').value = qa.qa_id;
        document.getElementById('modalCategory').value = qa.category;
        document.getElementById('modalQuestion').value = qa.question;
        document.getElementById('modalAnswer').value = qa.answer;
        document.getElementById('modalKeywords').value = qa.keywords;
        document.getElementById('modalActive').checked = qa.is_active;
        resetModalHints();
        document.getElementById('qaModal').classList.add('show');
    } catch (e) {
        showToast('Q&A를 불러올 수 없습니다.', 'error');
    }
}

function closeModal() {
    document.getElementById('qaModal').classList.remove('show');
    document.getElementById('modalSaveBtn').classList.remove('loading');
    document.getElementById('modalSaveBtn').disabled = false;
}

async function saveQa() {
    if (!validateModal()) return;

    const saveBtn = document.getElementById('modalSaveBtn');
    saveBtn.classList.add('loading');
    saveBtn.disabled = true;

    const qaId = document.getElementById('editQaId').value;
    const data = {
        category: document.getElementById('modalCategory').value,
        question: document.getElementById('modalQuestion').value.trim(),
        answer: document.getElementById('modalAnswer').value.trim(),
        keywords: document.getElementById('modalKeywords').value.trim(),
        is_active: document.getElementById('modalActive').checked,
    };

    try {
        if (qaId) {
            await apiPut(`/qa/${qaId}`, data);
            showToast('Q&A가 수정되었습니다.', 'success');
        } else {
            await apiPost('/qa', data);
            showToast('새 Q&A가 등록되었습니다.', 'success');
        }
        closeModal();
        loadQaList();
        loadStats();
    } catch (e) {
        saveBtn.classList.remove('loading');
        saveBtn.disabled = false;
        showToast('저장에 실패했습니다: ' + e.message, 'error');
    }
}

/* ═══════════════════════════════════════════════
 *  DELETE
 * ═══════════════════════════════════════════════ */
function openDeleteConfirm(qaId) {
    deleteTargetId = qaId;
    document.getElementById('deleteConfirm').classList.add('show');
    document.getElementById('confirmDeleteBtn').onclick = confirmDelete;
}

function closeDeleteConfirm() {
    document.getElementById('deleteConfirm').classList.remove('show');
    deleteTargetId = null;
}

async function confirmDelete() {
    if (!deleteTargetId) return;
    try {
        await apiDelete(`/qa/${deleteTargetId}`);
        closeDeleteConfirm();
        showToast('Q&A가 삭제되었습니다.', 'success');
        loadQaList();
        loadStats();
    } catch (e) {
        closeDeleteConfirm();
        showToast('삭제에 실패했습니다: ' + e.message, 'error');
    }
}

/* ═══════════════════════════════════════════════
 *  HELPERS
 * ═══════════════════════════════════════════════ */
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatDate(dateStr) {
    const d = new Date(dateStr);
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${d.getFullYear()}-${m}-${day}`;
}
