let currentPage = 1;
const PAGE_SIZE = 10;
let deleteTargetId = null;
let deleteTargetType = null; // 'qa' or 'admin'
let sessionCheckTimer = null;
let currentSearchTerm = '';
let currentRole = 'viewer';
let logPage = 1;
let companiesList = [];
let companyMap = {};  // id → name

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
            AuthSession.save(auth.session, persist, AuthSession.getToken());
        }

        const sess = auth.session;
        currentRole = sess.role || 'viewer';

        // Header display
        document.getElementById('headerCompanyName').textContent = sess.company_name || '';
        const displayName = sess.full_name || sess.email || sess.username || '';
        document.getElementById('adminUsername').textContent = displayName + '님';

        // Role badge
        const roleBadge = document.getElementById('roleBadge');
        const roleLabels = { super_admin: '최고관리자', admin: '관리자', viewer: '뷰어' };
        roleBadge.textContent = roleLabels[currentRole] || currentRole;
        roleBadge.className = 'role-badge role-' + currentRole;
        roleBadge.style.display = 'inline-block';

        // Show admin tab for admin/super_admin
        if (currentRole === 'admin' || currentRole === 'super_admin') {
            document.getElementById('tabAdmins').style.display = '';
        }

        // Show super admin link for super_admin
        if (currentRole === 'super_admin') {
            const saLink = document.getElementById('superAdminLink');
            if (saLink) saLink.style.display = '';
        }

        // super_admin: load companies for filter & modal
        if (currentRole === 'super_admin') {
            try {
                const companies = await apiGet('/companies/public');
                companiesList = companies;
                companyMap = {};
                companies.forEach(c => { companyMap[c.company_id] = c.company_name; });

                // Show company column header
                document.getElementById('companyColHeader').style.display = '';

                // Populate company filter dropdown
                const companyFilter = document.getElementById('companyFilter');
                companyFilter.style.display = '';
                companies.forEach(c => {
                    const opt = document.createElement('option');
                    opt.value = c.company_id;
                    opt.textContent = c.company_name;
                    companyFilter.appendChild(opt);
                });

                // Populate modal company select
                const modalCompany = document.getElementById('modalCompany');
                companies.forEach(c => {
                    const opt = document.createElement('option');
                    opt.value = c.company_id;
                    opt.textContent = c.company_name;
                    modalCompany.appendChild(opt);
                });
            } catch (e) {
                console.error('Companies load error:', e);
            }
        }

        // Hide edit buttons for viewer
        if (currentRole === 'viewer') {
            const addQaBtn = document.getElementById('addQaBtn');
            if (addQaBtn) addQaBtn.style.display = 'none';
        }
    } catch (err) {
        // 401/403 → 인증 실패, 로그인으로 이동
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
            AuthSession.redirectToLogin();
            return;
        }
        // 500/네트워크 에러 → 로컬 세션으로 폴백 시도
        const localSess = AuthSession.get();
        if (localSess) {
            currentRole = localSess.role || 'viewer';
            document.getElementById('headerCompanyName').textContent = localSess.companyName || '';
            const displayName = localSess.fullName || localSess.email || localSess.username || '';
            document.getElementById('adminUsername').textContent = displayName + '님';
            const roleBadge = document.getElementById('roleBadge');
            const roleLabels = { super_admin: '최고관리자', admin: '관리자', viewer: '뷰어' };
            roleBadge.textContent = roleLabels[currentRole] || currentRole;
            roleBadge.className = 'role-badge role-' + currentRole;
            roleBadge.style.display = 'inline-block';
            if (currentRole === 'admin' || currentRole === 'super_admin') {
                document.getElementById('tabAdmins').style.display = '';
            }
            console.warn('[ADMIN] auth check failed, using local session:', err.message);
        } else {
            AuthSession.redirectToLogin();
            return;
        }
    }

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
    loadQaList().then(checkTemplateData);

    // Search debounce
    let searchTimer;
    document.getElementById('searchInput').addEventListener('input', () => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => { currentPage = 1; loadQaList(); }, 300);
    });

    document.getElementById('categoryFilter').addEventListener('change', () => { currentPage = 1; loadQaList(); });
    document.getElementById('statusFilter').addEventListener('change', () => { currentPage = 1; loadQaList(); });
    document.getElementById('companyFilter').addEventListener('change', () => { currentPage = 1; loadQaList(); });

    // Profile button
    document.getElementById('profileBtn').addEventListener('click', () => openProfileModal());

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

    // Tab switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });
});

/* ═══════════════════════════════════════════════
 *  TABS
 * ═══════════════════════════════════════════════ */
function switchTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-selected', 'false');
    });
    document.querySelectorAll('.tab-content').forEach(c => {
        c.classList.remove('active');
        c.style.display = 'none';
    });

    const btn = document.querySelector(`.tab-btn[data-tab="${tab}"]`);
    if (btn) {
        btn.classList.add('active');
        btn.setAttribute('aria-selected', 'true');
    }

    const content = document.getElementById('tabContent' + tab.charAt(0).toUpperCase() + tab.slice(1));
    if (content) {
        content.classList.add('active');
        content.style.display = '';
    }

    if (tab === 'admins') loadAdminList();
    if (tab === 'logs') { logPage = 1; loadActivityLogs(); }
}

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
    // 구독 상태 로드
    try {
        const sess = AuthSession.get();
        const data = await apiGet('/billing/status?company_id=' + sess.companyId);
        const el = document.getElementById('statSubscription');
        const plan = data.subscription_plan;
        if (plan === 'enterprise' && data.active) {
            el.innerHTML = '<span style="color:var(--success)">유료 구독중</span>';
        } else if (plan === 'trial' && data.active) {
            let daysText = '';
            if (data.trial_ends_at) {
                const diff = Math.ceil((new Date(data.trial_ends_at) - new Date()) / 86400000);
                daysText = ' (' + (diff > 0 ? diff : 0) + '일)';
            }
            el.innerHTML = '<span style="color:#FF9800">체험중' + daysText + '</span><br><a href="/billing.html" class="btn btn-primary btn-sm" style="margin-top:0.25rem;font-size:0.75rem;padding:0.2rem 0.6rem">구독하기</a>';
        } else {
            el.innerHTML = '<a href="/billing.html" class="btn btn-primary btn-sm" style="font-size:0.75rem;padding:0.2rem 0.6rem">구독하기</a>';
        }
    } catch (e) {
        document.getElementById('statSubscription').innerHTML = '<a href="/billing.html" style="color:var(--primary);font-weight:600;text-decoration:underline">구독하기</a>';
    }
}

/* ═══════════════════════════════════════════════
 *  QA LIST
 * ═══════════════════════════════════════════════ */
let lastQaTotal = 0;

async function loadQaList() {
    const search = document.getElementById('searchInput').value.trim();
    const category = document.getElementById('categoryFilter').value;
    const status = document.getElementById('statusFilter').value;
    currentSearchTerm = search;

    const companyFilterVal = document.getElementById('companyFilter').value;

    const params = new URLSearchParams({ page: currentPage, size: PAGE_SIZE });
    if (search) params.append('search', search);
    if (category) params.append('category', category);
    if (status) params.append('status', status);
    if (companyFilterVal) params.append('company_id', companyFilterVal);

    document.getElementById('tableLoading').classList.add('show');
    try {
        const data = await apiGet(`/qa?${params}`);
        lastQaTotal = data.total || 0;
        renderTable(data.items);
        renderPagination(data.page, data.pages, data.total);
    } catch (e) {
        console.error('QA list error:', e);
    } finally {
        document.getElementById('tableLoading').classList.remove('show');
    }
}

/* ── 템플릿 데이터 안내 팝업 ── */
function checkTemplateData() {
    if (currentRole === 'super_admin') return;
    const sess = AuthSession.get();
    if (!sess) return;
    const key = 'qa_modified_' + sess.companyId;
    if (localStorage.getItem(key)) return;
    if (lastQaTotal === 0) return;

    // Q&A가 있지만 관리자가 아직 수정한 적 없으면 안내
    showTemplatePopup();
}

function markQaModified() {
    const sess = AuthSession.get();
    if (sess) localStorage.setItem('qa_modified_' + sess.companyId, '1');
}

function showTemplatePopup() {
    const overlay = document.getElementById('templatePopup');
    if (overlay) { overlay.classList.add('show'); return; }

    const popup = document.createElement('div');
    popup.id = 'templatePopup';
    popup.className = 'confirm-overlay show';
    popup.innerHTML = `
        <div class="confirm-dialog">
            <div class="confirm-icon" style="background:#FFF3E0;color:#FF9800">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            </div>
            <h3>Q&A 데이터 안내</h3>
            <p>현재 데이터는 최근 등록한 회사의 데이터입니다.<br>우리 회사에 맞게 수정이 필요합니다.</p>
            <div class="actions">
                <button class="btn btn-outline" onclick="closeTemplatePopup()">나중에</button>
                <button class="btn btn-primary" onclick="closeTemplatePopup(); openCreateModal();">+ 새 Q&A 추가</button>
            </div>
        </div>
    `;
    document.body.appendChild(popup);
}

function closeTemplatePopup() {
    const popup = document.getElementById('templatePopup');
    if (popup) popup.classList.remove('show');
}

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
    const isViewer = currentRole === 'viewer';
    const isSuperAdmin = currentRole === 'super_admin';

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
            ${isSuperAdmin ? `<td>${escapeHtml(qa.company_name || '-')}</td>` : ''}
            <td class="question-cell" title="${escapeHtml(qa.question)}"><a href="#" class="cell-link" onclick="openEditModal(${qa.qa_id});return false">${highlightText(qa.question, 100)}</a></td>
            <td class="answer-cell" title="${escapeHtml(qa.answer)}"><a href="#" class="cell-link" onclick="openEditModal(${qa.qa_id});return false">${highlightText(qa.answer, 150)}</a></td>
            <td>
                <button class="toggle-btn ${qa.is_active ? 'active' : ''}" onclick="toggleActive(${qa.qa_id})" role="switch" aria-checked="${qa.is_active}" ${isViewer ? 'disabled' : ''} title="${qa.is_active ? '활성' : '비활성'}"></button>
            </td>
            <td>${formatDate(qa.updated_at)}</td>
            <td>
                <div class="actions">
                    ${isViewer ? '' : `<button class="btn btn-outline btn-sm" onclick="openEditModal(${qa.qa_id})">수정</button>
                    <button class="btn btn-danger btn-sm" onclick="openDeleteConfirm(${qa.qa_id}, 'qa')">삭제</button>`}
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

function goToPage(page) { currentPage = page; loadQaList(); }

async function toggleActive(qaId) {
    if (currentRole === 'viewer') return;
    try {
        const qa = await apiPatch(`/qa/${qaId}/toggle`);
        showToast(qa.is_active ? 'Q&A가 활성화되었습니다.' : 'Q&A가 비활성화되었습니다.', 'success');
        markQaModified();
        loadQaList();
        loadStats();
    } catch (e) {
        showToast('상태 변경에 실패했습니다: ' + e.message, 'error');
    }
}

/* ═══════════════════════════════════════════════
 *  QA MODAL
 * ═══════════════════════════════════════════════ */
function onQuestionInput() {
    const val = document.getElementById('modalQuestion').value.trim();
    const hint = document.getElementById('questionHint');
    if (val.length === 0) { hint.textContent = ''; hint.className = 'field-hint'; }
    else if (val.length < 5) { hint.textContent = `${val.length}/5자 (최소 5자)`; hint.className = 'field-hint error'; }
    else { hint.textContent = `${val.length}자`; hint.className = 'field-hint ok'; checkDuplicate(val); }
}

function onAnswerInput() {
    const val = document.getElementById('modalAnswer').value.trim();
    const hint = document.getElementById('answerHint');
    if (val.length === 0) { hint.textContent = ''; hint.className = 'field-hint'; }
    else if (val.length < 10) { hint.textContent = `${val.length}/10자 (최소 10자)`; hint.className = 'field-hint error'; }
    else { hint.textContent = `${val.length}자`; hint.className = 'field-hint ok'; }
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
        } catch { warn.style.display = 'none'; }
    }, 500);
}

function validateModal() {
    const question = document.getElementById('modalQuestion').value.trim();
    const answer = document.getElementById('modalAnswer').value.trim();
    const errors = [];
    if (question.length < 5) errors.push('질문은 최소 5자 이상 입력해 주세요.');
    if (answer.length < 10) errors.push('답변은 최소 10자 이상 입력해 주세요.');
    if (errors.length > 0) { showToast(errors[0], 'error'); onQuestionInput(); onAnswerInput(); return false; }
    return true;
}

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
    document.getElementById('modalCategory').value = '이주정산';
    document.getElementById('modalQuestion').value = '';
    document.getElementById('modalAnswer').value = '';
    document.getElementById('modalKeywords').value = '';
    document.getElementById('modalActive').checked = true;
    resetModalHints();

    // super_admin: show company selector
    const companyGroup = document.getElementById('modalCompanyGroup');
    if (currentRole === 'super_admin' && companiesList.length > 0) {
        companyGroup.style.display = '';
        document.getElementById('modalCompany').value = companiesList[0].company_id;
    } else {
        companyGroup.style.display = 'none';
    }

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

        // super_admin: show company selector with current value
        const companyGroup = document.getElementById('modalCompanyGroup');
        if (currentRole === 'super_admin' && companiesList.length > 0) {
            companyGroup.style.display = '';
            document.getElementById('modalCompany').value = qa.company_id;
        } else {
            companyGroup.style.display = 'none';
        }

        document.getElementById('qaModal').classList.add('show');
    } catch (e) { showToast('Q&A를 불러올 수 없습니다.', 'error'); }
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

    // super_admin: include selected company_id
    if (currentRole === 'super_admin' && companiesList.length > 0) {
        data.company_id = parseInt(document.getElementById('modalCompany').value, 10);
    }

    try {
        if (qaId) {
            await apiPut(`/qa/${qaId}`, data);
            showToast('Q&A가 수정되었습니다.', 'success');
            markQaModified();
        } else {
            await apiPost('/qa', data);
            showToast('새 Q&A가 등록되었습니다.', 'success');
            markQaModified();
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
 *  ADMIN MANAGEMENT
 * ═══════════════════════════════════════════════ */
async function loadAdminList() {
    try {
        const data = await apiGet('/admins');
        const tbody = document.getElementById('adminTableBody');
        const roleLabels = { super_admin: '최고관리자', admin: '관리자', viewer: '뷰어' };

        tbody.innerHTML = data.items.map(admin => `
            <tr>
                <td>${admin.user_id}</td>
                <td>${escapeHtml(admin.email)}</td>
                <td>${escapeHtml(admin.full_name || '-')}</td>
                <td><span class="role-badge role-${admin.role}">${roleLabels[admin.role] || admin.role}</span></td>
                <td>${admin.is_active ? '<span style="color:var(--success)">활성</span>' : '<span style="color:var(--gray-400)">비활성</span>'}</td>
                <td>
                    <div class="actions">
                        <button class="btn btn-outline btn-sm" onclick="openEditAdminModal(${admin.user_id})">수정</button>
                        <button class="btn btn-danger btn-sm" onclick="openDeleteConfirm(${admin.user_id}, 'admin')">삭제</button>
                    </div>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Admin list error:', e);
    }
}

function openAdminModal() {
    document.getElementById('adminModalTitle').textContent = '관리자 추가';
    document.getElementById('editAdminId').value = '';
    document.getElementById('adminEmail').value = '';
    document.getElementById('adminPassword').value = '';
    document.getElementById('adminFullName').value = '';
    document.getElementById('adminPhone').value = '';
    document.getElementById('adminDepartment').value = '';
    document.getElementById('adminPosition').value = '';
    document.getElementById('adminPasswordGroup').style.display = '';
    document.getElementById('adminModal').classList.add('show');
}

async function openEditAdminModal(userId) {
    try {
        const admin = await apiGet(`/admins/${userId}`);
        document.getElementById('adminModalTitle').textContent = '관리자 수정';
        document.getElementById('editAdminId').value = admin.user_id;
        document.getElementById('adminEmail').value = admin.email;
        document.getElementById('adminPassword').value = '';
        document.getElementById('adminFullName').value = admin.full_name || '';
        document.getElementById('adminPhone').value = admin.phone || '';
        document.getElementById('adminDepartment').value = admin.department || '';
        document.getElementById('adminPosition').value = admin.position || '';
        document.getElementById('adminPasswordGroup').style.display = 'none';
        document.getElementById('adminModal').classList.add('show');
    } catch (e) {
        showToast('관리자 정보를 불러올 수 없습니다.', 'error');
    }
}

function closeAdminModal() {
    document.getElementById('adminModal').classList.remove('show');
}

async function saveAdmin() {
    const adminId = document.getElementById('editAdminId').value;
    const email = document.getElementById('adminEmail').value.trim();
    if (!email) { showToast('이메일을 입력해 주세요.', 'error'); return; }

    try {
        if (adminId) {
            // Update
            const data = {
                email,
                full_name: document.getElementById('adminFullName').value.trim() || null,
                phone: document.getElementById('adminPhone').value.trim() || null,
                department: document.getElementById('adminDepartment').value.trim() || null,
                position: document.getElementById('adminPosition').value.trim() || null,
                role: 'admin',
            };
            await apiPut(`/admins/${adminId}`, data);
            showToast('관리자가 수정되었습니다.', 'success');
        } else {
            // Create
            const password = document.getElementById('adminPassword').value;
            if (!password) { showToast('비밀번호를 입력해 주세요.', 'error'); return; }
            const data = {
                email,
                password,
                full_name: document.getElementById('adminFullName').value.trim() || null,
                phone: document.getElementById('adminPhone').value.trim() || null,
                department: document.getElementById('adminDepartment').value.trim() || null,
                position: document.getElementById('adminPosition').value.trim() || null,
                role: 'admin',
            };
            await apiPost('/admins', data);
            showToast('관리자가 추가되었습니다.', 'success');
        }
        closeAdminModal();
        loadAdminList();
    } catch (e) {
        showToast('저장에 실패했습니다: ' + e.message, 'error');
    }
}

/* ═══════════════════════════════════════════════
 *  ACTIVITY LOGS
 * ═══════════════════════════════════════════════ */
async function loadActivityLogs() {
    try {
        const params = new URLSearchParams({ page: logPage, size: 20 });
        const data = await apiGet(`/activity-logs?${params}`);
        const tbody = document.getElementById('logTableBody');
        const empty = document.getElementById('logEmptyState');

        if (data.items.length === 0) {
            tbody.innerHTML = '';
            empty.style.display = 'block';
            return;
        }
        empty.style.display = 'none';

        tbody.innerHTML = data.items.map(log => `
            <tr>
                <td>${log.activity_id}</td>
                <td><span class="badge badge-category">${escapeHtml(log.action_type)}</span></td>
                <td>${log.target_type ? escapeHtml(log.target_type) + (log.target_id ? ' #' + log.target_id : '') : '-'}</td>
                <td>${log.details ? escapeHtml(log.details).substring(0, 100) : '-'}</td>
                <td>${log.timestamp ? formatDateTime(log.timestamp) : '-'}</td>
            </tr>
        `).join('');

        // Log pagination
        const container = document.getElementById('logPagination');
        if (data.pages <= 1) { container.innerHTML = ''; return; }
        let html = `<button ${logPage <= 1 ? 'disabled' : ''} onclick="goToLogPage(${logPage - 1})">&laquo;</button>`;
        for (let i = Math.max(1, logPage - 2); i <= Math.min(data.pages, logPage + 2); i++) {
            html += `<button class="${i === logPage ? 'active' : ''}" onclick="goToLogPage(${i})">${i}</button>`;
        }
        html += `<button ${logPage >= data.pages ? 'disabled' : ''} onclick="goToLogPage(${logPage + 1})">&raquo;</button>`;
        container.innerHTML = html;
    } catch (e) {
        console.error('Activity logs error:', e);
    }
}

function goToLogPage(page) { logPage = page; loadActivityLogs(); }

/* ═══════════════════════════════════════════════
 *  DELETE (shared for QA and Admin)
 * ═══════════════════════════════════════════════ */
function openDeleteConfirm(id, type) {
    deleteTargetId = id;
    deleteTargetType = type;
    const title = type === 'admin' ? '관리자 삭제' : 'Q&A 삭제';
    document.getElementById('deleteConfirmTitle').textContent = title;
    document.getElementById('deleteConfirm').classList.add('show');
    document.getElementById('confirmDeleteBtn').onclick = confirmDelete;
}

function closeDeleteConfirm() {
    document.getElementById('deleteConfirm').classList.remove('show');
    deleteTargetId = null;
    deleteTargetType = null;
}

async function confirmDelete() {
    if (!deleteTargetId) return;
    try {
        if (deleteTargetType === 'admin') {
            await apiDelete(`/admins/${deleteTargetId}`);
            closeDeleteConfirm();
            showToast('관리자가 삭제되었습니다.', 'success');
            loadAdminList();
        } else {
            await apiDelete(`/qa/${deleteTargetId}`);
            closeDeleteConfirm();
            showToast('Q&A가 삭제되었습니다.', 'success');
            markQaModified();
            loadQaList();
            loadStats();
        }
    } catch (e) {
        closeDeleteConfirm();
        showToast('삭제에 실패했습니다: ' + e.message, 'error');
    }
}

/* ═══════════════════════════════════════════════
 *  PROFILE MODAL
 * ═══════════════════════════════════════════════ */
async function openProfileModal() {
    try {
        const me = await apiGet('/admins/me');
        document.getElementById('profileEmail').value = me.email || '';
        document.getElementById('profileFullName').value = me.full_name || '';
        document.getElementById('profilePhone').value = me.phone || '';
        document.getElementById('profileCurrentPw').value = '';
        document.getElementById('profileNewPw').value = '';
        document.getElementById('profileNewPwConfirm').value = '';

        // Load company info via /companies/me
        try {
            const company = await apiGet('/companies/me');
            document.getElementById('profileCompanyName').value = company.company_name || '';
            document.getElementById('profileCompanyAddress').value = company.address || '';
        } catch (e) {
            const sess = AuthSession.get();
            document.getElementById('profileCompanyName').value = sess?.companyName || '';
            document.getElementById('profileCompanyAddress').value = '';
        }

        document.getElementById('profileModal').classList.add('show');
    } catch (e) {
        showToast('내 정보를 불러올 수 없습니다.', 'error');
    }
}

function closeProfileModal() {
    document.getElementById('profileModal').classList.remove('show');
}

async function saveProfile() {
    const companyName = document.getElementById('profileCompanyName').value.trim();
    const companyAddress = document.getElementById('profileCompanyAddress').value.trim();
    const fullName = document.getElementById('profileFullName').value.trim();
    const phone = document.getElementById('profilePhone').value.trim();
    const currentPw = document.getElementById('profileCurrentPw').value;
    const newPw = document.getElementById('profileNewPw').value;
    const newPwConfirm = document.getElementById('profileNewPwConfirm').value;

    const saveBtn = document.getElementById('profileSaveBtn');
    saveBtn.disabled = true;

    try {
        // Update company info via /companies/me
        await apiPut('/companies/me', {
            company_name: companyName || null,
            address: companyAddress || null,
        });
        if (companyName) {
            document.getElementById('headerCompanyName').textContent = companyName;
        }

        // Update profile info (name, phone)
        await apiPatch('/admins/me', {
            full_name: fullName || null,
            phone: phone || null,
        });

        // Change password if fields are filled
        if (currentPw || newPw || newPwConfirm) {
            if (!currentPw) {
                showToast('현재 비밀번호를 입력해 주세요.', 'error');
                saveBtn.disabled = false;
                return;
            }
            if (!newPw) {
                showToast('새 비밀번호를 입력해 주세요.', 'error');
                saveBtn.disabled = false;
                return;
            }
            if (newPw.length < 8) {
                showToast('새 비밀번호는 8자 이상이어야 합니다.', 'error');
                saveBtn.disabled = false;
                return;
            }
            if (newPw !== newPwConfirm) {
                showToast('새 비밀번호가 일치하지 않습니다.', 'error');
                saveBtn.disabled = false;
                return;
            }
            await apiPatch('/admins/me/password', {
                current_password: currentPw,
                new_password: newPw,
            });
        }

        // Update header display name
        if (fullName) {
            document.getElementById('adminUsername').textContent = fullName + '님';
        }

        showToast('내 정보가 수정되었습니다.', 'success');
        closeProfileModal();
    } catch (e) {
        showToast(e.message || '저장에 실패했습니다.', 'error');
    } finally {
        saveBtn.disabled = false;
    }
}

/* ═══════════════════════════════════════════════
 *  HELPERS
 * ═══════════════════════════════════════════════ */
function escapeHtml(str) {
    if (!str) return '';
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

function formatDateTime(dateStr) {
    const d = new Date(dateStr);
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const h = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');
    return `${d.getFullYear()}-${m}-${day} ${h}:${min}`;
}
