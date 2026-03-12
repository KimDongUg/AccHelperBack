let currentPage = 1;
const PAGE_SIZE = 10;
let deleteTargetId = null;
let deleteTargetType = null; // 'qa' or 'admin'
let sessionCheckTimer = null;
let currentSearchTerm = '';
let currentRole = 'viewer';
let logPage = 1;
let unansweredPage = 1;
let feedbackPage = 1;
let companiesList = [];
let companyMap = {};  // id → name

/* ═══════════════════════════════════════════════
 *  INIT
 * ═══════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', async () => {
    // Auth guard
    if (!AuthSession.isValid()) { AuthSession.redirectToLogin(); return; }

    // Keep local session as fallback if server auth check fails
    const localSess = AuthSession.get();
    let sess = null;

    try {
        const auth = await apiGet('/auth/check');
        if (!auth.authenticated) { AuthSession.redirectToLogin(); return; }
        if (auth.session) {
            sess = auth.session;
            const persist = !!localStorage.getItem('acc_auth_session');
            AuthSession.save(auth.session, persist, AuthSession.getToken());
        }
    } catch (err) {
        // 401/403 → token invalid, must re-login
        if (err.status === 401 || err.status === 403) {
            AuthSession.redirectToLogin();
            return;
        }
        // Other errors (500, network) → use local session as fallback
        console.warn('[ADMIN] auth check failed:', err.message, '— using local session');
    }

    // Build session — prefer server data, fallback to local storage
    if (!sess && localSess) {
        sess = {
            role: localSess.role,
            company_name: localSess.companyName,
            full_name: localSess.fullName,
            email: localSess.email,
            username: localSess.username,
        };
    }
    if (!sess) { AuthSession.redirectToLogin(); return; }

    currentRole = sess.role || 'viewer';

    // Header display
    document.getElementById('headerCompanyName').textContent = sess.company_name || '';
    const displayName = sess.full_name || sess.email || sess.username || '';
    document.getElementById('adminUsername').textContent = displayName + '님';

    // 챗봇 버튼 → 해당 업체 챗봇으로 이동
    var chatBotLink = document.getElementById('chatBotLink');
    if (chatBotLink && sess.company_id) {
        chatBotLink.href = '/?company=' + sess.company_id;
    }

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

            // Auto-select company if ?company= query parameter is present
            const urlParams = new URLSearchParams(window.location.search);
            const targetCompanyId = urlParams.get('company');
            if (targetCompanyId) {
                companyFilter.value = targetCompanyId;
                // Update header to show the selected company name
                const targetCompany = companies.find(c => String(c.company_id) === String(targetCompanyId));
                if (targetCompany) {
                    document.getElementById('headerCompanyName').textContent = targetCompany.company_name;
                    document.title = targetCompany.company_name + ' 관리자 - AI Helper 경리도우미';
                }
                // Also pre-select in modal company select
                modalCompany.value = targetCompanyId;
            }

        } catch (e) {
            console.error('Companies load error:', e);
        }

        // Show Excel export button for super_admin
        const exportBtn = document.getElementById('exportQaExcelBtn');
        if (exportBtn) exportBtn.style.display = '';
    }

    // Hide edit buttons for viewer
    if (currentRole === 'viewer') {
        const addQaBtn = document.getElementById('addQaBtn');
        if (addQaBtn) addQaBtn.style.display = 'none';
        const csSection = document.getElementById('companySettingsSection');
        if (csSection) csSection.style.display = 'none';
    }

    // super_admin viewing another company → hide company settings
    if (currentRole === 'super_admin') {
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('company')) {
            const csSection = document.getElementById('companySettingsSection');
            if (csSection) csSection.style.display = 'none';
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
    loadCompanySettings();
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
    document.getElementById('createdByFilter').addEventListener('change', () => { currentPage = 1; loadQaList(); });
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

    // Feedback filters
    document.getElementById('feedbackRatingFilter').addEventListener('change', () => { feedbackPage = 1; loadFeedbackList(); });
    document.getElementById('feedbackStatusFilter').addEventListener('change', () => { feedbackPage = 1; loadFeedbackList(); });

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
    if (tab === 'feedback') { feedbackPage = 1; loadFeedbackList(); }
    if (tab === 'unanswered') { unansweredPage = 1; loadUnansweredList(); }
    if (tab === 'logs') { logPage = 1; loadActivityLogs(); }
    if (tab === 'statistics') initStatistics();
    if (tab === 'subscription') loadSubscriptionTab();
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
    // 불만족 피드백 건수 로드
    try {
        const fc = await apiGet('/feedback/count');
        document.getElementById('statFeedback').textContent = fc.count ?? 0;
    } catch (e) {
        document.getElementById('statFeedback').textContent = '-';
    }
    // 미답변 질문 건수 로드
    try {
        const uc = await apiGet('/unanswered-questions/count');
        document.getElementById('statUnanswered').textContent = uc.count ?? 0;
    } catch (e) {
        document.getElementById('statUnanswered').textContent = '-';
    }
    // 구독 상태 로드
    try {
        const sess = AuthSession.get();
        const data = await apiGet('/billing/status?company_id=' + sess.companyId);
        const el = document.getElementById('statSubscription');
        const plan = data.subscription_plan;
        if (plan === 'enterprise' && data.active) {
            el.innerHTML = '<span style="color:var(--success);cursor:pointer" onclick="switchTab(\'subscription\')" title="구독 관리로 이동">유료 구독중</span>';
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
    const createdBy = document.getElementById('createdByFilter').value;
    currentSearchTerm = search;

    const companyFilterVal = document.getElementById('companyFilter').value;

    const params = new URLSearchParams({ page: currentPage, size: PAGE_SIZE });
    if (search) params.append('search', search);
    if (category) params.append('category', category);
    if (status) params.append('status', status);
    if (createdBy) params.append('created_by', createdBy);
    if (companyFilterVal) params.append('company_id', companyFilterVal);

    document.getElementById('tableLoading').classList.add('show');
    try {
        const data = await apiGet(`/qa?${params}`);
        lastQaTotal = data.total || 0;
        renderTable(data.items);
        renderPagination(data.page, data.pages, data.total);
        updateCreatedByFilter(data.items);
    } catch (e) {
        console.error('QA list error:', e);
    } finally {
        document.getElementById('tableLoading').classList.remove('show');
    }
}

/* ── 작성자 필터 드롭다운 업데이트 ── */
let knownCreators = new Set();

function updateCreatedByFilter(items) {
    items.forEach(qa => {
        if (qa.created_by) knownCreators.add(qa.created_by);
    });

    const select = document.getElementById('createdByFilter');
    const current = select.value;
    const options = Array.from(knownCreators).sort();

    select.innerHTML = '<option value="">전체 작성자</option>';
    options.forEach(name => {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        select.appendChild(opt);
    });
    select.value = current;
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
            <td style="font-size:var(--text-xs);color:var(--gray-500)">${escapeHtml(qa.created_by || '-')}</td>
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
    // Reset preview state
    document.getElementById('answerPreview').style.display = 'none';
    document.getElementById('modalAnswer').style.display = '';
    document.getElementById('previewToggleBtn').classList.remove('active');
}

async function saveQa() {
    if (!validateModal()) return;
    const saveBtn = document.getElementById('modalSaveBtn');
    saveBtn.classList.add('loading');
    saveBtn.disabled = true;

    const qaId = document.getElementById('editQaId').value;
    // Get current user name from session
    const sess = AuthSession.get();
    const creatorName = sess?.fullName || sess?.email || sess?.username || '';

    const data = {
        category: document.getElementById('modalCategory').value,
        question: document.getElementById('modalQuestion').value.trim(),
        answer: document.getElementById('modalAnswer').value.trim(),
        keywords: document.getElementById('modalKeywords').value.trim(),
        is_active: document.getElementById('modalActive').checked,
        created_by: creatorName,
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
 *  FEEDBACK MANAGEMENT
 * ═══════════════════════════════════════════════ */
let feedbackItems = [];

async function loadFeedbackList() {
    const rating = document.getElementById('feedbackRatingFilter').value;
    const status = document.getElementById('feedbackStatusFilter').value;
    const params = new URLSearchParams({ page: feedbackPage, size: PAGE_SIZE });
    if (rating) params.append('rating', rating);
    if (status) params.append('status', status);

    const loading = document.getElementById('feedbackTableLoading');
    loading.classList.add('show');
    try {
        const data = await apiGet(`/feedback?${params}`);
        feedbackItems = data.items || [];
        renderFeedbackTable(feedbackItems);
        renderFeedbackPagination(data.page, data.pages);
    } catch (e) {
        console.error('Feedback list error:', e);
    } finally {
        loading.classList.remove('show');
    }
}

function renderFeedbackTable(items) {
    const tbody = document.getElementById('feedbackTableBody');
    const empty = document.getElementById('feedbackEmptyState');

    if (!items || items.length === 0) {
        tbody.innerHTML = '';
        empty.style.display = 'block';
        return;
    }

    empty.style.display = 'none';
    tbody.innerHTML = items.map((item, idx) => {
        const ratingIcon = item.rating === 'like'
            ? '<span style="color:var(--success);font-size:1.2rem" title="만족">&#x1F44D;</span>'
            : '<span style="color:var(--danger);font-size:1.2rem" title="불만족">&#x1F44E;</span>';
        const statusLabel = item.status === 'pending'
            ? '<span style="color:#FF9800">미처리</span>'
            : '<span style="color:var(--success)">처리완료</span>';
        const feedbackId = item.feedback_id || item.id;
        return `
        <tr>
            <td style="text-align:center">${ratingIcon}</td>
            <td class="question-cell" title="${escapeHtml(item.question)}">${escapeHtml(item.question)}</td>
            <td class="answer-cell" title="${escapeHtml(item.answer || '')}">${escapeHtml((item.answer || '').substring(0, 100))}</td>
            <td>${statusLabel}</td>
            <td>${item.created_at ? formatDateTime(item.created_at) : '-'}</td>
            <td>
                <div class="actions">
                    ${item.status === 'pending' ? `
                        <button class="btn btn-primary btn-sm" onclick="onFeedbackEdit(${idx})">Q&A 수정</button>
                        <button class="btn btn-outline btn-sm" onclick="resolveFeedback(${feedbackId})">처리완료</button>
                    ` : ''}
                </div>
            </td>
        </tr>`;
    }).join('');
}

function renderFeedbackPagination(page, pages) {
    const container = document.getElementById('feedbackPagination');
    if (pages <= 1) { container.innerHTML = ''; return; }

    let html = `<button ${page <= 1 ? 'disabled' : ''} onclick="goToFeedbackPage(${page - 1})">&laquo;</button>`;
    const start = Math.max(1, page - 2);
    const end = Math.min(pages, page + 2);
    if (start > 1) {
        html += `<button onclick="goToFeedbackPage(1)">1</button>`;
        if (start > 2) html += `<button disabled>...</button>`;
    }
    for (let i = start; i <= end; i++) {
        html += `<button class="${i === page ? 'active' : ''}" onclick="goToFeedbackPage(${i})">${i}</button>`;
    }
    if (end < pages) {
        if (end < pages - 1) html += `<button disabled>...</button>`;
        html += `<button onclick="goToFeedbackPage(${pages})">${pages}</button>`;
    }
    html += `<button ${page >= pages ? 'disabled' : ''} onclick="goToFeedbackPage(${page + 1})">&raquo;</button>`;
    container.innerHTML = html;
}

function goToFeedbackPage(page) { feedbackPage = page; loadFeedbackList(); }

function onFeedbackEdit(idx) {
    const item = feedbackItems[idx];
    if (!item) return;
    const feedbackId = item.feedback_id || item.id;
    const qaId = (item.qa_ids && item.qa_ids.length > 0) ? item.qa_ids[0] : null;
    editQaFromFeedback(qaId, feedbackId, item.question || '');
}

async function editQaFromFeedback(qaId, feedbackId, question) {
    try {
        if (qaId) {
            await openEditModal(qaId);
        } else {
            openCreateModal();
            if (question) {
                document.getElementById('modalQuestion').value = question;
                onQuestionInput();
            }
        }
    } catch (e) {
        // openEditModal 실패 시 새 Q&A 생성으로 전환
        openCreateModal();
        if (question) {
            document.getElementById('modalQuestion').value = question;
            onQuestionInput();
        }
    }

    // 저장 후 피드백도 resolved 처리하도록 오버라이드
    const origSave = window._origSaveQaFb || saveQa;
    if (!window._origSaveQaFb) window._origSaveQaFb = saveQa;

    window.saveQa = async function () {
        if (!validateModal()) return;
        const saveBtn = document.getElementById('modalSaveBtn');
        saveBtn.classList.add('loading');
        saveBtn.disabled = true;

        const editId = document.getElementById('editQaId').value;
        const data = {
            category: document.getElementById('modalCategory').value,
            question: document.getElementById('modalQuestion').value.trim(),
            answer: document.getElementById('modalAnswer').value.trim(),
            keywords: document.getElementById('modalKeywords').value.trim(),
            is_active: document.getElementById('modalActive').checked,
        };
        if (currentRole === 'super_admin' && companiesList.length > 0) {
            data.company_id = parseInt(document.getElementById('modalCompany').value, 10);
        }

        try {
            if (editId) {
                await apiPut(`/qa/${editId}`, data);
            } else {
                await apiPost('/qa', data);
            }
            await apiPatch(`/feedback/${feedbackId}`, { status: 'resolved' });
            showToast('Q&A가 저장되고 피드백이 처리되었습니다.', 'success');
            markQaModified();
            closeModal();
            loadQaList();
            loadStats();
            loadFeedbackList();
        } catch (e) {
            saveBtn.classList.remove('loading');
            saveBtn.disabled = false;
            showToast('저장에 실패했습니다: ' + e.message, 'error');
        }
        window.saveQa = origSave;
    };
}

async function resolveFeedback(id) {
    try {
        await apiPatch(`/feedback/${id}`, { status: 'resolved' });
        showToast('피드백이 처리완료되었습니다.', 'success');
        loadFeedbackList();
        loadStats();
    } catch (e) {
        showToast('처리에 실패했습니다: ' + e.message, 'error');
    }
}

/* ═══════════════════════════════════════════════
 *  UNANSWERED QUESTIONS
 * ═══════════════════════════════════════════════ */
async function loadUnansweredList() {
    const params = new URLSearchParams({ page: unansweredPage, size: PAGE_SIZE });
    const loading = document.getElementById('unansweredTableLoading');
    loading.classList.add('show');
    try {
        const data = await apiGet(`/unanswered-questions?${params}`);
        renderUnansweredTable(data.items);
        renderUnansweredPagination(data.page, data.pages);
    } catch (e) {
        console.error('Unanswered list error:', e);
    } finally {
        loading.classList.remove('show');
    }
}

function renderUnansweredTable(items) {
    const tbody = document.getElementById('unansweredTableBody');
    const empty = document.getElementById('unansweredEmptyState');

    if (!items || items.length === 0) {
        tbody.innerHTML = '';
        empty.style.display = 'block';
        return;
    }

    empty.style.display = 'none';
    tbody.innerHTML = items.map(item => {
        const statusLabel = item.status === 'pending' ? '<span style="color:#FF9800">대기</span>'
            : item.status === 'resolved' ? '<span style="color:var(--success)">등록됨</span>'
            : '<span style="color:var(--gray-400)">무시</span>';
        return `
        <tr>
            <td title="${escapeHtml(item.question)}">${escapeHtml(item.question)}</td>
            <td>${item.created_at ? formatDateTime(item.created_at) : '-'}</td>
            <td>${statusLabel}</td>
            <td>
                <div class="actions">
                    ${item.status === 'pending' ? `
                        <button class="btn btn-primary btn-sm" onclick="resolveUnanswered(${item.id}, '${escapeHtml(item.question).replace(/'/g, "\\'")}')">Q&A 등록</button>
                        <button class="btn btn-outline btn-sm" onclick="dismissUnanswered(${item.id})">무시</button>
                    ` : ''}
                </div>
            </td>
        </tr>`;
    }).join('');
}

function renderUnansweredPagination(page, pages) {
    const container = document.getElementById('unansweredPagination');
    if (pages <= 1) { container.innerHTML = ''; return; }

    let html = `<button ${page <= 1 ? 'disabled' : ''} onclick="goToUnansweredPage(${page - 1})">&laquo;</button>`;
    const start = Math.max(1, page - 2);
    const end = Math.min(pages, page + 2);
    if (start > 1) {
        html += `<button onclick="goToUnansweredPage(1)">1</button>`;
        if (start > 2) html += `<button disabled>...</button>`;
    }
    for (let i = start; i <= end; i++) {
        html += `<button class="${i === page ? 'active' : ''}" onclick="goToUnansweredPage(${i})">${i}</button>`;
    }
    if (end < pages) {
        if (end < pages - 1) html += `<button disabled>...</button>`;
        html += `<button onclick="goToUnansweredPage(${pages})">${pages}</button>`;
    }
    html += `<button ${page >= pages ? 'disabled' : ''} onclick="goToUnansweredPage(${page + 1})">&raquo;</button>`;
    container.innerHTML = html;
}

function goToUnansweredPage(page) { unansweredPage = page; loadUnansweredList(); }

function resolveUnanswered(id, question) {
    // Open Q&A create modal with question pre-filled
    openCreateModal();
    document.getElementById('modalQuestion').value = question;
    onQuestionInput();

    // Override save to also resolve the unanswered question
    const origSave = window._origSaveQa || saveQa;
    if (!window._origSaveQa) window._origSaveQa = saveQa;

    window.saveQa = async function () {
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
        if (currentRole === 'super_admin' && companiesList.length > 0) {
            data.company_id = parseInt(document.getElementById('modalCompany').value, 10);
        }

        try {
            if (qaId) {
                await apiPut(`/qa/${qaId}`, data);
            } else {
                await apiPost('/qa', data);
            }
            // Mark unanswered as resolved
            await apiPatch(`/unanswered-questions/${id}`, { status: 'resolved' });
            showToast('Q&A가 등록되고 미답변이 처리되었습니다.', 'success');
            markQaModified();
            closeModal();
            loadQaList();
            loadStats();
            loadUnansweredList();
        } catch (e) {
            saveBtn.classList.remove('loading');
            saveBtn.disabled = false;
            showToast('저장에 실패했습니다: ' + e.message, 'error');
        }

        // Restore original saveQa
        window.saveQa = origSave;
    };
}

async function dismissUnanswered(id) {
    try {
        await apiPatch(`/unanswered-questions/${id}`, { status: 'dismissed' });
        showToast('미답변 질문이 무시 처리되었습니다.', 'success');
        loadUnansweredList();
        loadStats();
    } catch (e) {
        showToast('처리에 실패했습니다: ' + e.message, 'error');
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

        document.getElementById('profileModal').classList.add('show');
    } catch (e) {
        showToast('내 정보를 불러올 수 없습니다.', 'error');
    }
}

function closeProfileModal() {
    document.getElementById('profileModal').classList.remove('show');
}

async function saveProfile() {
    const fullName = document.getElementById('profileFullName').value.trim();
    const phone = document.getElementById('profilePhone').value.trim();
    const currentPw = document.getElementById('profileCurrentPw').value;
    const newPw = document.getElementById('profileNewPw').value;
    const newPwConfirm = document.getElementById('profileNewPwConfirm').value;

    const saveBtn = document.getElementById('profileSaveBtn');
    saveBtn.disabled = true;

    try {
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
 *  COMPANY SETTINGS (Dashboard)
 * ═══════════════════════════════════════════════ */
async function loadCompanySettings() {
    try {
        const company = await apiGet('/companies/me');
        document.getElementById('dashCompanyName').value = company.company_name || '';
        document.getElementById('dashCompanyAddress').value = company.address || '';
        document.getElementById('dashChatbotUrl').value = getCompanyChatbotUrl() || '';
        document.getElementById('dashGreeting').value = company.greeting_text || '';

        // Load categories
        const wrap = document.getElementById('categoryItemsWrap');
        wrap.innerHTML = '';
        const categories = company.categories || [];
        categories.forEach(cat => addCategoryItem(cat.label, cat.question));

        // Sync category dropdowns
        syncCategoryDropdowns(categories);
    } catch (e) {
        const sess = AuthSession.get();
        document.getElementById('dashCompanyName').value = sess?.companyName || '';
    }
}

function syncCategoryDropdowns(categories) {
    if (!categories || categories.length === 0) return;
    const labels = categories.map(c => c.label);

    const filterEl = document.getElementById('categoryFilter');
    const filterVal = filterEl.value;
    filterEl.innerHTML = '<option value="">전체 카테고리</option>';
    labels.forEach(label => {
        const opt = document.createElement('option');
        opt.value = label;
        opt.textContent = label;
        filterEl.appendChild(opt);
    });
    filterEl.value = filterVal;

    const modalEl = document.getElementById('modalCategory');
    const modalVal = modalEl.value;
    modalEl.innerHTML = '';
    labels.forEach(label => {
        const opt = document.createElement('option');
        opt.value = label;
        opt.textContent = label;
        modalEl.appendChild(opt);
    });
    if (modalVal && labels.includes(modalVal)) modalEl.value = modalVal;
}

async function saveCompanySettings() {
    const companyName = document.getElementById('dashCompanyName').value.trim();
    const companyAddress = document.getElementById('dashCompanyAddress').value.trim();
    const greetingText = document.getElementById('dashGreeting').value.trim();
    const categories = getCategoryItems();

    const saveBtn = document.getElementById('companySettingsSaveBtn');
    saveBtn.disabled = true;

    try {
        await apiPut('/companies/me', {
            company_name: companyName || null,
            address: companyAddress || null,
            greeting_text: greetingText || null,
            categories: categories.length > 0 ? categories : null,
        });

        if (companyName) {
            document.getElementById('headerCompanyName').textContent = companyName;
        }

        showToast('회사 설정이 저장되었습니다.', 'success');
        syncCategoryDropdowns(categories);
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

/* ═══════════════════════════════════════════════
 *  ANSWER EDITOR (Image / Link / Preview)
 * ═══════════════════════════════════════════════ */
async function handleImageUpload(input) {
    const file = input.files[0];
    if (!file) return;

    // 파일 크기 제한 (5MB)
    if (file.size > 5 * 1024 * 1024) {
        showToast('이미지는 5MB 이하만 업로드 가능합니다.', 'error');
        input.value = '';
        return;
    }

    const btn = document.getElementById('imageUploadBtn');
    const origHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="btn-spinner" style="display:inline-block;width:14px;height:14px;border:2px solid var(--gray-300);border-top-color:var(--primary);border-radius:50%;animation:tableSpin 0.6s linear infinite"></span> 업로드중...';

    try {
        const formData = new FormData();
        formData.append('file', file);

        const result = await apiFetch('/upload/image', {
            method: 'POST',
            body: formData,
        });

        const url = result.url;
        const alt = file.name.replace(/\.[^.]+$/, '');
        insertAtCursor('modalAnswer', `![${alt}](${url})`);
        showToast('이미지가 업로드되었습니다.', 'success');
    } catch (e) {
        showToast('이미지 업로드에 실패했습니다: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = origHtml;
        input.value = '';
    }
}

function insertLinkToAnswer() {
    const url = prompt('웹사이트 URL을 입력하세요:', 'https://');
    if (!url || url === 'https://') return;
    const text = prompt('링크 텍스트를 입력하세요:', '') || url;
    const markdown = `[${text}](${url})`;
    insertAtCursor('modalAnswer', markdown);
}

function insertAtCursor(textareaId, text) {
    const ta = document.getElementById(textareaId);
    ta.focus();
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const before = ta.value.substring(0, start);
    const after = ta.value.substring(end);
    ta.value = before + text + after;
    ta.selectionStart = ta.selectionEnd = start + text.length;
    // Trigger input event for validation
    ta.dispatchEvent(new Event('input'));
}

function toggleAnswerPreview() {
    const ta = document.getElementById('modalAnswer');
    const preview = document.getElementById('answerPreview');
    const btn = document.getElementById('previewToggleBtn');

    if (preview.style.display === 'none') {
        // Show preview
        const raw = ta.value || '';
        if (typeof marked !== 'undefined' && marked.parse) {
            preview.innerHTML = marked.parse(raw);
        } else {
            preview.textContent = raw;
        }
        // Make links open in new tab
        preview.querySelectorAll('a').forEach(a => {
            a.setAttribute('target', '_blank');
            a.setAttribute('rel', 'noopener noreferrer');
        });
        preview.style.display = '';
        ta.style.display = 'none';
        btn.classList.add('active');
    } else {
        // Show editor
        preview.style.display = 'none';
        ta.style.display = '';
        btn.classList.remove('active');
        ta.focus();
    }
}

/* ═══════════════════════════════════════════════
 *  CATEGORY ITEMS (Dashboard)
 * ═══════════════════════════════════════════════ */
function addCategoryItem(label, question) {
    const wrap = document.getElementById('categoryItemsWrap');
    const isEtc = (label || '').trim() === '기타';

    const row = document.createElement('div');
    row.className = 'category-item';
    row.innerHTML =
        '<div class="cat-order-btns">' +
            '<button type="button" class="cat-up" title="위로">&uarr;</button>' +
            '<button type="button" class="cat-down" title="아래로">&darr;</button>' +
        '</div>' +
        '<input type="text" class="form-control cat-label" placeholder="버튼 텍스트 (예: 입주신고)" value="' + escapeHtml(label || '') + '">' +
        '<input type="text" class="form-control cat-question" placeholder="질문 (예: 입주신고 시 필요한 서류는?)" value="' + escapeHtml(question || '') + '">' +
        '<button type="button" class="btn-category-remove' + (isEtc ? ' disabled' : '') + '" title="삭제">&times;</button>';

    row.querySelector('.cat-up').addEventListener('click', function () {
        const prev = row.previousElementSibling;
        if (prev) { wrap.insertBefore(row, prev); updateCategoryOrderBtns(); }
    });

    row.querySelector('.cat-down').addEventListener('click', function () {
        const next = row.nextElementSibling;
        if (next) { wrap.insertBefore(next, row); updateCategoryOrderBtns(); }
    });

    if (!isEtc) {
        row.querySelector('.btn-category-remove').addEventListener('click', function () {
            const catLabel = row.querySelector('.cat-label').value.trim();
            if (!confirm('삭제하시겠습니까?\n카테고리 이하 데이터가 보이지 않을 수 있습니다.')) return;

            // Move Q&A data from this category to "기타"
            if (catLabel) {
                apiPatch('/qa/move-category', { from_category: catLabel, to_category: '기타' })
                    .then(() => showToast('"' + catLabel + '" Q&A가 "기타"로 이동되었습니다.', 'success'))
                    .catch(() => showToast('Q&A 카테고리 이동에 실패했습니다.', 'error'));
            }

            row.remove();
            updateCategoryOrderBtns();
        });
    }

    wrap.appendChild(row);
    updateCategoryOrderBtns();
}

function updateCategoryOrderBtns() {
    const wrap = document.getElementById('categoryItemsWrap');
    const items = wrap.querySelectorAll('.category-item');
    items.forEach((item, i) => {
        item.querySelector('.cat-up').disabled = (i === 0);
        item.querySelector('.cat-down').disabled = (i === items.length - 1);
    });
}

function getCategoryItems() {
    const wrap = document.getElementById('categoryItemsWrap');
    const items = wrap.querySelectorAll('.category-item');
    const result = [];
    items.forEach(item => {
        const label = item.querySelector('.cat-label').value.trim();
        const question = item.querySelector('.cat-question').value.trim();
        if (label && question) {
            result.push({ label, question });
        }
    });
    return result;
}

/* loadCompanyCategories → replaced by loadCompanySettings + syncCategoryDropdowns */

/* ═══════════════════════════════════════════════
 *  QR CODE
 * ═══════════════════════════════════════════════ */
function getCompanyChatbotUrl() {
    const sess = AuthSession.get();
    let companyId = sess?.companyId || sess?.company_id;
    if (!companyId) {
        const filter = document.getElementById('companyFilter');
        if (filter && filter.value) companyId = filter.value;
    }
    if (!companyId) return null;
    return 'https://acchelper.kr/?company=' + companyId;
}

function copyChatbotUrl() {
    const url = document.getElementById('dashChatbotUrl').value;
    if (!url) { showToast('챗봇 주소를 불러올 수 없습니다.', 'error'); return; }
    navigator.clipboard.writeText(url).then(() => {
        showToast('챗봇 주소가 복사되었습니다.', 'success');
    }).catch(() => {
        showToast('복사에 실패했습니다.', 'error');
    });
}

function showQrModal() {
    const url = getCompanyChatbotUrl();
    if (!url) {
        showToast('회사 정보를 불러올 수 없습니다.', 'error');
        return;
    }

    document.getElementById('qrUrlDisplay').textContent = url;
    const container = document.getElementById('qrCanvas');
    container.innerHTML = '';

    // Generate QR using qrcode-generator library
    var qr = qrcode(0, 'M');
    qr.addData(url);
    qr.make();

    // Create high-res canvas
    var moduleCount = qr.getModuleCount();
    var cellSize = 8;
    var margin = cellSize * 2;
    var size = moduleCount * cellSize + margin * 2;
    var canvas = document.createElement('canvas');
    canvas.id = 'qrCodeCanvas';
    canvas.width = size;
    canvas.height = size;
    canvas.style.width = (size / 2) + 'px';
    canvas.style.height = (size / 2) + 'px';

    var ctx = canvas.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, size, size);
    ctx.fillStyle = '#000000';

    for (var r = 0; r < moduleCount; r++) {
        for (var c = 0; c < moduleCount; c++) {
            if (qr.isDark(r, c)) {
                ctx.fillRect(c * cellSize + margin, r * cellSize + margin, cellSize, cellSize);
            }
        }
    }

    container.appendChild(canvas);
    document.getElementById('qrModal').classList.add('show');
}

function closeQrModal() {
    document.getElementById('qrModal').classList.remove('show');
}

function downloadQrCode() {
    var canvas = document.getElementById('qrCodeCanvas');
    if (!canvas) return;

    var link = document.createElement('a');
    link.download = 'chatbot-qrcode.png';
    link.href = canvas.toDataURL('image/png');
    link.click();
    showToast('QR코드가 다운로드되었습니다.', 'success');
}

/* ═══════════════════════════════════════════════
 *  공고문 (NOTICE)
 * ═══════════════════════════════════════════════ */
function generateNoticeQrDataUrl() {
    var url = getCompanyChatbotUrl();
    if (!url) return null;

    var qr = qrcode(0, 'M');
    qr.addData(url);
    qr.make();

    var moduleCount = qr.getModuleCount();
    var cellSize = 10;
    var margin = cellSize * 2;
    var size = moduleCount * cellSize + margin * 2;
    var canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;

    var ctx = canvas.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, size, size);
    ctx.fillStyle = '#000000';

    for (var r = 0; r < moduleCount; r++) {
        for (var c = 0; c < moduleCount; c++) {
            if (qr.isDark(r, c)) {
                ctx.fillRect(c * cellSize + margin, r * cellSize + margin, cellSize, cellSize);
            }
        }
    }
    return canvas.toDataURL('image/png');
}

function getNoticeCompanyName() {
    return document.getElementById('dashCompanyName')?.value
        || document.getElementById('headerCompanyName')?.textContent
        || '관리사무소';
}

function generateNoticeHtml(chatbotUrl, qrDataUrl, companyName) {
    return '<!DOCTYPE html>\n<html lang="ko">\n<head>\n'
+ '  <meta charset="UTF-8" />\n'
+ '  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>\n'
+ '  <title>AI 챗봇 도입 안내 - ' + companyName + '</title>\n'
+ '  <style>\n'
+ "    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap');\n"
+ '    * { margin: 0; padding: 0; box-sizing: border-box; }\n'
+ '    body {\n'
+ "      font-family: 'Noto Sans KR', sans-serif;\n"
+ '      background: #f0f4f0;\n'
+ '      display: flex;\n'
+ '      justify-content: center;\n'
+ '      align-items: center;\n'
+ '      min-height: 100vh;\n'
+ '      padding: 20px;\n'
+ '    }\n'
+ '    .page {\n'
+ '      width: 231mm;\n'
+ '      min-height: 297mm;\n'
+ '      background: white;\n'
+ '      position: relative;\n'
+ '      overflow: hidden;\n'
+ '      box-shadow: 0 8px 40px rgba(0,0,0,0.18);\n'
+ '      border-radius: 4px;\n'
+ '    }\n'
+ '    .header {\n'
+ '      background: linear-gradient(135deg, #1b5e20 0%, #2e7d32 40%, #43a047 100%);\n'
+ '      padding: 40px 40px 34px;\n'
+ '      position: relative;\n'
+ '      overflow: hidden;\n'
+ '    }\n'
+ "    .header::before {\n      content: '';\n      position: absolute;\n      top: -60px; right: -60px;\n      width: 220px; height: 220px;\n      background: rgba(255,255,255,0.07);\n      border-radius: 50%;\n    }\n"
+ "    .header::after {\n      content: '';\n      position: absolute;\n      bottom: -80px; left: -40px;\n      width: 260px; height: 260px;\n      background: rgba(255,255,255,0.05);\n      border-radius: 50%;\n    }\n"
+ '    .header-inner {\n      display: flex;\n      align-items: center;\n      gap: 18px;\n      position: relative;\n      z-index: 2;\n    }\n'
+ '    .logo-area { display: flex; align-items: center; gap: 10px; }\n'
+ '    .logo-icon {\n      width: 64px; height: 64px;\n      background: white;\n      border-radius: 16px;\n      display: flex; align-items: center; justify-content: center;\n      box-shadow: 0 4px 16px rgba(0,0,0,0.2);\n      flex-shrink: 0;\n    }\n'
+ '    .logo-icon svg { width: 44px; height: 44px; }\n'
+ '    .header-text { color: white; }\n'
+ '    .header-label { font-size: 14px; font-weight: 500; letter-spacing: 3px; opacity: 0.85; text-transform: uppercase; margin-bottom: 4px; }\n'
+ '    .header-title { font-size: 39px; font-weight: 900; line-height: 1.15; letter-spacing: -0.5px; }\n'
+ '    .header-title span { color: #a5d6a7; }\n'
+ '    .header-sub { font-size: 17px; opacity: 0.82; margin-top: 6px; font-weight: 400; }\n'
+ '    .badge-row {\n      background: #e8f5e9; border-left: 5px solid #2e7d32;\n      margin: 30px 36px 0; padding: 14px 22px;\n      border-radius: 0 8px 8px 0;\n      display: flex; align-items: center; gap: 10px;\n    }\n'
+ '    .badge-row .icon { font-size: 26px; }\n'
+ '    .badge-row p { font-size: 17.5px; color: #1b5e20; font-weight: 600; line-height: 1.5; }\n'
+ '    .badge-row p span { font-weight: 400; color: #388e3c; }\n'
+ '    .body { padding: 30px 36px 36px; }\n'
+ '    .intro-box {\n      background: linear-gradient(135deg, #f1f8e9, #e8f5e9);\n      border: 1.5px solid #a5d6a7; border-radius: 14px;\n      padding: 24px 26px; display: flex; gap: 18px;\n      align-items: flex-start; margin-bottom: 28px;\n    }\n'
+ '    .intro-box .emoji { font-size: 47px; flex-shrink: 0; margin-top: 2px; }\n'
+ '    .intro-box-text h3 { font-size: 20px; font-weight: 800; color: #1b5e20; margin-bottom: 6px; }\n'
+ '    .intro-box-text p { font-size: 17px; color: #444; line-height: 1.75; }\n'
+ '    .section-title {\n      font-size: 17px; font-weight: 700; color: #2e7d32;\n      letter-spacing: 1.5px; text-transform: uppercase;\n      margin-bottom: 12px; display: flex; align-items: center; gap: 6px;\n    }\n'
+ "    .section-title::after { content: ''; flex: 1; height: 1.5px; background: #c8e6c9; border-radius: 2px; }\n"
+ '    .features-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 28px; }\n'
+ '    .feature-card {\n      background: #fafafa; border: 1.5px solid #e0e0e0;\n      border-radius: 12px; padding: 18px 20px;\n      display: flex; align-items: flex-start; gap: 12px;\n    }\n'
+ '    .feat-icon {\n      width: 49px; height: 49px; border-radius: 10px;\n      display: flex; align-items: center; justify-content: center;\n      font-size: 23px; flex-shrink: 0;\n    }\n'
+ '    .feat-icon.green { background: #e8f5e9; }\n'
+ '    .feat-icon.blue { background: #e3f2fd; }\n'
+ '    .feat-icon.orange { background: #fff3e0; }\n'
+ '    .feat-icon.purple { background: #f3e5f5; }\n'
+ '    .feat-text h4 { font-size: 17px; font-weight: 700; color: #222; margin-bottom: 3px; }\n'
+ '    .feat-text p { font-size: 15px; color: #666; line-height: 1.55; }\n'
+ '    .how-section { margin-bottom: 28px; }\n'
+ '    .steps { display: flex; align-items: center; gap: 0; justify-content: space-between; }\n'
+ '    .step { flex: 1; text-align: center; }\n'
+ '    .step-num {\n      width: 47px; height: 47px;\n      background: linear-gradient(135deg, #2e7d32, #66bb6a);\n      color: white; border-radius: 50%;\n      font-size: 21px; font-weight: 900;\n      display: flex; align-items: center; justify-content: center;\n      margin: 0 auto 8px;\n      box-shadow: 0 3px 10px rgba(46,125,50,0.3);\n    }\n'
+ '    .step p { font-size: 15px; color: #333; font-weight: 600; line-height: 1.5; }\n'
+ '    .step-arrow { font-size: 26px; color: #81c784; flex-shrink: 0; padding-bottom: 28px; }\n'
+ '    .qr-section {\n      background: linear-gradient(135deg, #1b5e20, #2e7d32);\n      border-radius: 16px; padding: 28px 30px;\n      display: flex; align-items: center; gap: 28px;\n      position: relative; overflow: hidden;\n    }\n'
+ "    .qr-section::before {\n      content: ''; position: absolute;\n      top: -40px; right: -40px;\n      width: 150px; height: 150px;\n      background: rgba(255,255,255,0.06); border-radius: 50%;\n    }\n"
+ '    .qr-wrap {\n      background: white; border-radius: 12px; padding: 8px;\n      flex-shrink: 0; box-shadow: 0 4px 16px rgba(0,0,0,0.25);\n    }\n'
+ '    .qr-wrap img { width: 120px; height: 120px; display: block; border-radius: 6px; }\n'
+ '    .qr-info { flex: 1; position: relative; z-index: 2; }\n'
+ '    .qr-info h3 { font-size: 22px; font-weight: 900; color: white; margin-bottom: 6px; }\n'
+ '    .qr-info p { font-size: 16px; color: #a5d6a7; line-height: 1.6; margin-bottom: 10px; }\n'
+ '    .url-chip {\n      display: inline-block; background: rgba(255,255,255,0.15);\n      border: 1px solid rgba(255,255,255,0.3); color: white;\n      font-size: 15px; padding: 6px 15px; border-radius: 20px;\n      font-weight: 600; letter-spacing: 0.3px;\n    }\n'
+ '    @media print {\n      body { background: white; padding: 0; }\n      .page { box-shadow: none; border-radius: 0; }\n    }\n'
+ '  </style>\n</head>\n<body>\n<div class="page">\n'
+ '  <div class="header">\n    <div class="header-inner">\n      <div class="logo-area">\n        <div class="logo-icon">\n'
+ '          <svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">\n'
+ '            <circle cx="40" cy="32" r="22" fill="#2e7d32"/>\n'
+ '            <circle cx="40" cy="32" r="18" fill="#66bb6a"/>\n'
+ '            <ellipse cx="33" cy="31" rx="3.5" ry="4" fill="white"/>\n'
+ '            <ellipse cx="47" cy="31" rx="3.5" ry="4" fill="white"/>\n'
+ '            <ellipse cx="33" cy="32" rx="2" ry="2.5" fill="#1b5e20"/>\n'
+ '            <ellipse cx="47" cy="32" rx="2" ry="2.5" fill="#1b5e20"/>\n'
+ '            <path d="M33 41 Q40 47 47 41" stroke="white" stroke-width="2.5" stroke-linecap="round" fill="none"/>\n'
+ '            <ellipse cx="40" cy="54" rx="16" ry="10" fill="#2e7d32"/>\n'
+ '            <rect x="30" y="52" width="20" height="8" rx="4" fill="#388e3c"/>\n'
+ '            <ellipse cx="18" cy="32" rx="4" ry="5" fill="#2e7d32"/>\n'
+ '            <ellipse cx="62" cy="32" rx="4" ry="5" fill="#2e7d32"/>\n'
+ '            <path d="M18 32 Q18 14 40 14 Q62 14 62 32" stroke="#1b5e20" stroke-width="4" fill="none" stroke-linecap="round"/>\n'
+ '          </svg>\n'
+ '        </div>\n      </div>\n'
+ '      <div class="header-text">\n'
+ '        <div class="header-label">\uacf5 \uace0 \ubb38 \xb7 Notice</div>\n'
+ '        <div class="header-title">AI <span>\ucc57\ubd07</span> \ub3c4\uc785 \uc548\ub0b4</div>\n'
+ '        <div class="header-sub">' + escapeHtml(companyName) + ' - AI Helper \uc11c\ube44\uc2a4\ub97c \ub3c4\uc785\ud558\uc5ec \uc785\uc8fc\ubbfc \uc5ec\ub7ec\ubd84\uaed8 \ub354 \ud3b8\ub9ac\ud55c \uc11c\ube44\uc2a4\ub97c \uc81c\uacf5\ud569\ub2c8\ub2e4</div>\n'
+ '      </div>\n    </div>\n  </div>\n'
+ '  <div class="badge-row">\n    <div class="icon">\ud83d\udce2</div>\n'
+ '    <p>\uc774\uc81c <strong>\uc2a4\ub9c8\ud2b8\ud3f0 \ud558\ub098</strong>\ub85c \uad00\ub9ac\uc0ac\ubb34\uc18c\uc5d0 \uc9c1\uc811 \ubc29\ubb38\ud558\uc9c0 \uc54a\uc544\ub3c4 \uac01\uc885 \ubb38\uc758\ub97c \ud574\uacb0\ud558\uc2e4 \uc218 \uc788\uc2b5\ub2c8\ub2e4.'
+ '      <br/><span>AI \ucc57\ubd07\uc774 24\uc2dc\uac04 365\uc77c \uc5ec\ub7ec\ubd84\uc758 \uad81\uae08\uc99d\uc5d0 \ub2f5\ubcc0\ud574 \ub4dc\ub9bd\ub2c8\ub2e4.</span></p>\n  </div>\n'
+ '  <div class="body">\n'
+ '    <div class="intro-box">\n      <div class="emoji">\ud83e\udd16</div>\n'
+ '      <div class="intro-box-text">\n        <h3>AI Helper\ub780?</h3>\n'
+ '        <p>\uc911\uac04\uad00\ub9ac\ube44 \uc815\uc0b0, \uc785\uc8fc\uc2e0\uace0, \uac01\uc885 \uc2dc\uc124\ubb3c AS \ub4f1 \ub2e8\uc9c0 \uc6b4\uc601\uacfc \uad00\ub828\ub41c \ub2e4\uc591\ud55c \uc815\ubcf4\ub97c'
+ '          <strong>AI \ucc57\ubd07\uc774 \uc989\uc2dc \uc548\ub0b4</strong>\ud574 \ub4dc\ub9ac\ub294 \uc2a4\ub9c8\ud2b8 \uc11c\ube44\uc2a4\uc785\ub2c8\ub2e4.'
+ '          \ubcc4\ub3c4 \uc571 \uc124\uce58 \uc5c6\uc774 <strong>QR \ucf54\ub4dc</strong> \ub610\ub294 <strong>\ub9c1\ud06c \uc811\uc18d</strong>\ub9cc\uc73c\ub85c \ubc14\ub85c \uc774\uc6a9\ud558\uc2e4 \uc218 \uc788\uc2b5\ub2c8\ub2e4.</p>\n'
+ '      </div>\n    </div>\n'
+ '    <div class="section-title">\u2726 \uc8fc\uc694 \uae30\ub2a5</div>\n'
+ '    <div class="features-grid">\n'
+ '      <div class="feature-card"><div class="feat-icon green">\ud83d\udcac</div><div class="feat-text"><h4>24\uc2dc\uac04 \uc2e4\uc2dc\uac04 \ubb38\uc758</h4><p>\uacf5\ud734\uc77c\xb7\uc57c\uac04\uc5d0\ub3c4 \uad00\ub9ac\ube44, \uc2dc\uc124, \uc0dd\ud65c\ud3b8\uc758 \uad00\ub828 \uc9c8\ubb38\uc5d0 \uc989\uc2dc \ub2f5\ubcc0</p></div></div>\n'
+ '      <div class="feature-card"><div class="feat-icon blue">\ud83d\udccb</div><div class="feat-text"><h4>\uacf5\uc9c0\uc0ac\ud56d \uc989\uc2dc \ud655\uc778</h4><p>\ub2e8\uc9c0 \ub0b4 \uacf5\uc9c0\xb7\uc548\ub0b4\uc0ac\ud56d\uc744 \ucc57\ubd07\uc744 \ud1b5\ud574 \ube60\ub974\uac8c \uac80\uc0c9\xb7\ud655\uc778 \uac00\ub2a5</p></div></div>\n'
+ '      <div class="feature-card"><div class="feat-icon orange">\ud83d\udca1</div><div class="feat-text"><h4>\uad00\ub9ac\ube44 \uc548\ub0b4</h4><p>\uad00\ub9ac\ube44 \ud56d\ubaa9\ubcc4 \uc124\uba85, \ub0a9\ubd80 \ubc29\ubc95, \uc5f0\uccb4 \uc548\ub0b4 \ub4f1\uc744 \uc27d\uac8c \ubb38\uc758</p></div></div>\n'
+ '      <div class="feature-card"><div class="feat-icon purple">\ud83c\udfe2</div><div class="feat-text"><h4>\uc2dc\uc124 \uc774\uc6a9 \uc548\ub0b4</h4><p>\uc8fc\ucc28\uc7a5, \ucee4\ubba4\ub2c8\ud2f0\uc13c\ud130, \ud0dd\ubc30\ud568 \ub4f1 \ud3b8\uc758\uc2dc\uc124 \uc774\uc6a9 \uc815\ubcf4 \uc81c\uacf5</p></div></div>\n'
+ '    </div>\n'
+ '    <div class="how-section">\n      <div class="section-title">\u2726 \uc774\uc6a9 \ubc29\ubc95</div>\n'
+ '      <div class="steps">\n'
+ '        <div class="step"><div class="step-num">1</div><p>\uc544\ub798 QR \ucf54\ub4dc<br/>\ub610\ub294<br/>\ub9c1\ud06c \uc811\uc18d</p></div>\n'
+ '        <div class="step-arrow">\u203a</div>\n'
+ '        <div class="step"><div class="step-num">2</div><p>\ucc44\ud305\ucc3d\uc5d0<br/>\uad81\uae08\ud55c \ub0b4\uc6a9<br/>\uc785\ub825</p></div>\n'
+ '        <div class="step-arrow">\u203a</div>\n'
+ '        <div class="step"><div class="step-num">3</div><p>AI\uac00 \uc989\uc2dc<br/>\ub2f5\ubcc0 \uc81c\uacf5</p></div>\n'
+ '        <div class="step-arrow">\u203a</div>\n'
+ '        <div class="step"><div class="step-num">4</div><p>\ucd94\uac00 \ubb38\uc758 \uc2dc<br/>\uad00\ub9ac\uc0ac\ubb34\uc18c<br/>\uc5f0\uacb0 \uc548\ub0b4</p></div>\n'
+ '      </div>\n    </div>\n'
+ '    <div class="qr-section">\n'
+ '      <div class="qr-wrap"><img src="' + qrDataUrl + '" alt="QR \ucf54\ub4dc" /></div>\n'
+ '      <div class="qr-info">\n'
+ '        <h3>\ud83d\udcf1 \uc9c0\uae08 \ubc14\ub85c \uc811\uc18d\ud558\uc138\uc694!</h3>\n'
+ '        <p>QR \ucf54\ub4dc \ub610\ub294 \uc544\ub798 \uc8fc\uc18c\ub85c \uc9c1\uc811 \uc811\uc18d\ud558\uc2dc\uba74<br/>AI \ucc57\ubd07\uacfc \ubc14\ub85c \ub300\ud654\ub97c \uc2dc\uc791\ud558\uc2e4 \uc218 \uc788\uc2b5\ub2c8\ub2e4.</p>\n'
+ '        <div class="url-chip">\ud83d\udd17 ' + escapeHtml(chatbotUrl.replace('https://', '')) + '</div>\n'
+ '      </div>\n    </div>\n'
+ '  </div>\n'
+ '</div>\n</body>\n</html>';
}

function escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}

function showNoticeModal() {
    var url = getCompanyChatbotUrl();
    if (!url) {
        showToast('회사 정보를 불러올 수 없습니다.', 'error');
        return;
    }
    document.getElementById('noticeModal').classList.add('show');
}

function closeNoticeModal() {
    document.getElementById('noticeModal').classList.remove('show');
}

function previewNotice() {
    var url = getCompanyChatbotUrl();
    if (!url) {
        showToast('회사 정보를 불러올 수 없습니다.', 'error');
        return;
    }
    var qrDataUrl = generateNoticeQrDataUrl();
    var companyName = getNoticeCompanyName();
    var html = generateNoticeHtml(url, qrDataUrl, companyName);

    var win = window.open('', '_blank');
    win.document.write(html);
    win.document.close();
    showToast('공고문이 새 창에 열렸습니다. 인쇄(Ctrl+P)하여 사용하세요.', 'success');
}

function downloadNoticePng() {
    var url = getCompanyChatbotUrl();
    if (!url) {
        showToast('회사 정보를 불러올 수 없습니다.', 'error');
        return;
    }
    var qrDataUrl = generateNoticeQrDataUrl();
    var companyName = getNoticeCompanyName();
    var html = generateNoticeHtml(url, qrDataUrl, companyName);

    // Create hidden iframe to render the notice
    var iframe = document.createElement('iframe');
    iframe.style.cssText = 'position:fixed;left:-9999px;top:0;width:210mm;height:297mm;border:none;';
    document.body.appendChild(iframe);

    iframe.contentDocument.open();
    iframe.contentDocument.write(html);
    iframe.contentDocument.close();

    // Wait for fonts and content to load, then capture
    setTimeout(function() {
        var page = iframe.contentDocument.querySelector('.page');
        if (!page) {
            document.body.removeChild(iframe);
            showToast('공고문 생성에 실패했습니다.', 'error');
            return;
        }
        html2canvas(page, {
            scale: 2,
            useCORS: true,
            backgroundColor: '#ffffff',
            width: page.scrollWidth,
            height: page.scrollHeight
        }).then(function(canvas) {
            var link = document.createElement('a');
            link.download = 'AI챗봇_도입_공고문.png';
            link.href = canvas.toDataURL('image/png');
            link.click();
            document.body.removeChild(iframe);
            showToast('공고문 PNG가 다운로드되었습니다.', 'success');
        }).catch(function() {
            document.body.removeChild(iframe);
            showToast('PNG 생성에 실패했습니다. 인쇄 미리보기를 이용해주세요.', 'error');
        });
    }, 1500);

    showToast('PNG 생성 중입니다. 잠시만 기다려주세요...', 'success');
}

function downloadNoticeFile() {
    var url = getCompanyChatbotUrl();
    if (!url) {
        showToast('회사 정보를 불러올 수 없습니다.', 'error');
        return;
    }
    var qrDataUrl = generateNoticeQrDataUrl();
    var companyName = getNoticeCompanyName();
    var html = generateNoticeHtml(url, qrDataUrl, companyName);

    var blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    var link = document.createElement('a');
    link.download = 'AI챗봇_도입_공고문.html';
    link.href = URL.createObjectURL(blob);
    link.click();
    URL.revokeObjectURL(link.href);
    showToast('공고문이 다운로드되었습니다.', 'success');
}

/* ═══════════════════════════════════════════════
 *  Q&A 엑셀 다운로드 (super_admin 전용)
 * ═══════════════════════════════════════════════ */
async function exportQaToExcel() {
    if (currentRole !== 'super_admin') return;

    const btn = document.getElementById('exportQaExcelBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="btn-spinner" style="display:inline-block"></span> 다운로드 중...';

    try {
        // 현재 필터 값 가져오기
        const search = document.getElementById('searchInput').value.trim();
        const category = document.getElementById('categoryFilter').value;
        const status = document.getElementById('statusFilter').value;
        const createdBy = document.getElementById('createdByFilter').value;
        const companyFilterVal = document.getElementById('companyFilter').value;

        // 전체 데이터를 가져오기 위해 큰 size 사용
        const params = new URLSearchParams({ page: 1, size: 10000 });
        if (search) params.append('search', search);
        if (category) params.append('category', category);
        if (status) params.append('status', status);
        if (createdBy) params.append('created_by', createdBy);
        if (companyFilterVal) params.append('company_id', companyFilterVal);

        const data = await apiGet(`/qa?${params}`);
        const items = data.items || [];

        if (items.length === 0) {
            showToast('다운로드할 Q&A 데이터가 없습니다.', 'warning');
            return;
        }

        // 엑셀 데이터 구성
        const rows = items.map(qa => ({
            'ID': qa.qa_id,
            '회사명': qa.company_name || companyMap[qa.company_id] || '-',
            '카테고리': qa.category || '-',
            '질문': qa.question,
            '답변': qa.answer,
            '키워드': qa.keywords || '',
            '상태': qa.is_active ? '활성' : '비활성',
            '작성자': qa.created_by || '-',
            '수정일': qa.updated_at ? new Date(qa.updated_at).toLocaleString('ko-KR') : '-',
        }));

        const ws = XLSX.utils.json_to_sheet(rows);

        // 열 너비 설정
        ws['!cols'] = [
            { wch: 6 },   // ID
            { wch: 20 },  // 회사명
            { wch: 12 },  // 카테고리
            { wch: 50 },  // 질문
            { wch: 60 },  // 답변
            { wch: 20 },  // 키워드
            { wch: 8 },   // 상태
            { wch: 12 },  // 작성자
            { wch: 20 },  // 수정일
        ];

        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, 'Q&A 데이터');

        // 파일명에 날짜 포함
        const today = new Date().toISOString().slice(0, 10).replace(/-/g, '');
        const companyLabel = companyFilterVal
            ? (companyMap[companyFilterVal] || companyFilterVal)
            : '전체';
        const filename = `QA_데이터_${companyLabel}_${today}.xlsx`;

        XLSX.writeFile(wb, filename);
        showToast(`${items.length}건의 Q&A 데이터를 다운로드했습니다.`, 'success');
    } catch (e) {
        console.error('Excel export error:', e);
        showToast('엑셀 다운로드에 실패했습니다: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> 엑셀 다운로드';
    }
}

/* ═══════════════════════════════════════════════
 *  STATISTICS (통계)
 * ═══════════════════════════════════════════════ */
let visitorsChartInstance = null;
let qaViewsChartInstance = null;
let statsInitialized = false;

function initStatistics() {
    if (!statsInitialized) {
        // Set default date range: last 30 days
        const today = new Date();
        const thirtyDaysAgo = new Date(today);
        thirtyDaysAgo.setDate(today.getDate() - 30);
        document.getElementById('statsDateTo').value = formatDateISO(today);
        document.getElementById('statsDateFrom').value = formatDateISO(thirtyDaysAgo);

        // Period type change handler
        document.getElementById('statsPeriodType').addEventListener('change', function () {
            adjustStatsDateRange(this.value);
            loadStatistics();
        });

        statsInitialized = true;
    }
    loadStatistics();
}

function formatDateISO(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

function adjustStatsDateRange(periodType) {
    const today = new Date();
    const toEl = document.getElementById('statsDateTo');
    const fromEl = document.getElementById('statsDateFrom');
    toEl.value = formatDateISO(today);

    if (periodType === 'daily') {
        const d = new Date(today);
        d.setDate(today.getDate() - 30);
        fromEl.value = formatDateISO(d);
    } else if (periodType === 'monthly') {
        const d = new Date(today);
        d.setMonth(today.getMonth() - 12);
        fromEl.value = formatDateISO(d);
    } else if (periodType === 'quarterly') {
        const d = new Date(today);
        d.setFullYear(today.getFullYear() - 2);
        fromEl.value = formatDateISO(d);
    } else if (periodType === 'yearly') {
        const d = new Date(today);
        d.setFullYear(today.getFullYear() - 5);
        fromEl.value = formatDateISO(d);
    }
}

async function loadStatistics() {
    const periodType = document.getElementById('statsPeriodType').value;
    const dateFrom = document.getElementById('statsDateFrom').value;
    const dateTo = document.getElementById('statsDateTo').value;

    if (!dateFrom || !dateTo) {
        showToast('조회 기간을 선택해주세요.', 'warning');
        return;
    }

    // Build query params — company_id is resolved server-side from JWT
    // For super_admin viewing a specific company, pass company filter
    let companyParam = '';
    if (currentRole === 'super_admin') {
        const companyFilter = document.getElementById('companyFilter');
        if (companyFilter && companyFilter.value) {
            companyParam = '&company_id=' + companyFilter.value;
        }
    }

    const query = `?period=${periodType}&from=${dateFrom}&to=${dateTo}${companyParam}`;

    try {
        const data = await apiGet('/stats/usage' + query);
        renderStatsSummary(data);
        renderStatsCharts(data, periodType);
        renderStatsTable(data, periodType);
    } catch (e) {
        console.error('Statistics load error:', e);
        showToast('통계 데이터를 불러오는데 실패했습니다.', 'error');
        // Show empty state
        document.getElementById('statsTableBody').innerHTML = '';
        document.getElementById('statsEmptyState').style.display = '';
    }
}

function renderStatsSummary(data) {
    const items = data.items || [];
    let totalVisitors = 0, totalQuestions = 0, totalAnswers = 0;

    items.forEach(item => {
        totalVisitors += item.visitors || 0;
        totalQuestions += item.question_views || 0;
        totalAnswers += item.answer_views || 0;
    });

    const avgVisitors = items.length > 0 ? Math.round(totalVisitors / items.length) : 0;

    document.getElementById('statsTotalVisitors').textContent = totalVisitors.toLocaleString();
    document.getElementById('statsTotalQuestions').textContent = totalQuestions.toLocaleString();
    document.getElementById('statsTotalAnswers').textContent = totalAnswers.toLocaleString();
    document.getElementById('statsAvgVisitors').textContent = avgVisitors.toLocaleString();
}

function renderStatsCharts(data, periodType) {
    const items = data.items || [];
    const labels = items.map(item => formatStatLabel(item.period, periodType));
    const visitorsData = items.map(item => item.visitors || 0);
    const questionData = items.map(item => item.question_views || 0);
    const answerData = items.map(item => item.answer_views || 0);

    // Destroy previous charts
    if (visitorsChartInstance) { visitorsChartInstance.destroy(); visitorsChartInstance = null; }
    if (qaViewsChartInstance) { qaViewsChartInstance.destroy(); qaViewsChartInstance = null; }

    const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
            legend: { position: 'bottom', labels: { usePointStyle: true, padding: 16, font: { size: 12 } } },
            tooltip: { backgroundColor: 'rgba(0,0,0,0.8)', padding: 10, cornerRadius: 8 },
        },
        scales: {
            x: { grid: { display: false }, ticks: { font: { size: 11 }, maxRotation: 45 } },
            y: { beginAtZero: true, grid: { color: '#f0f0f0' }, ticks: { font: { size: 11 }, precision: 0 } },
        },
    };

    // Visitors chart
    const visitorsCtx = document.getElementById('visitorsChart').getContext('2d');
    visitorsChartInstance = new Chart(visitorsCtx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: '접속자 수',
                data: visitorsData,
                backgroundColor: 'rgba(125, 194, 66, 0.6)',
                borderColor: '#7DC242',
                borderWidth: 1,
                borderRadius: 4,
                maxBarThickness: 40,
            }],
        },
        options: commonOptions,
    });

    // Q&A Views chart
    const qaCtx = document.getElementById('qaViewsChart').getContext('2d');
    qaViewsChartInstance = new Chart(qaCtx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: '질문 조회',
                    data: questionData,
                    borderColor: '#4A90D9',
                    backgroundColor: 'rgba(74, 144, 217, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                },
                {
                    label: '답변 조회',
                    data: answerData,
                    borderColor: '#FF9800',
                    backgroundColor: 'rgba(255, 152, 0, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                },
            ],
        },
        options: commonOptions,
    });
}

function formatStatLabel(period, periodType) {
    if (!period) return '';
    if (periodType === 'daily') {
        // "2026-03-12" → "3/12"
        const parts = period.split('-');
        return parseInt(parts[1]) + '/' + parseInt(parts[2]);
    } else if (periodType === 'monthly') {
        // "2026-03" → "2026.03"
        return period.replace('-', '.');
    } else if (periodType === 'quarterly') {
        // "2026-Q1" → "2026 Q1"
        return period.replace('-', ' ');
    } else if (periodType === 'yearly') {
        // "2026" → "2026년"
        return period + '년';
    }
    return period;
}

function renderStatsTable(data, periodType) {
    const items = data.items || [];
    const tbody = document.getElementById('statsTableBody');
    const emptyState = document.getElementById('statsEmptyState');

    // Update column header
    const colHeader = document.getElementById('statsColPeriod');
    const periodLabels = { daily: '날짜', monthly: '월', quarterly: '분기', yearly: '연도' };
    colHeader.textContent = periodLabels[periodType] || '기간';

    if (!items.length) {
        tbody.innerHTML = '';
        emptyState.style.display = '';
        return;
    }

    emptyState.style.display = 'none';
    tbody.innerHTML = items.map(item => `
        <tr>
            <td>${formatStatLabel(item.period, periodType)}</td>
            <td style="text-align:right">${(item.visitors || 0).toLocaleString()}</td>
            <td style="text-align:right">${(item.question_views || 0).toLocaleString()}</td>
            <td style="text-align:right">${(item.answer_views || 0).toLocaleString()}</td>
        </tr>
    `).join('');
}


/* ═══════════════════════════════════════════════
 *  SUBSCRIPTION MANAGEMENT
 * ═══════════════════════════════════════════════ */

let tossPayments = null;
let subStatus = null;

async function loadSubscriptionTab() {
    const sess = AuthSession.get();
    if (!sess) return;

    try {
        // 상태 + 내역 병렬 로드
        const [status, history] = await Promise.all([
            apiGet('/billing/status?company_id=' + sess.companyId),
            apiGet('/billing/history?company_id=' + sess.companyId),
        ]);

        subStatus = status;
        renderSubscriptionStatus(status);
        renderPaymentHistory(history.payments || []);
    } catch (e) {
        document.getElementById('subPlanLabel').textContent = '구독 정보를 불러올 수 없습니다.';
        document.getElementById('subPlanDetail').textContent = e.message || '';
    }
}

function renderSubscriptionStatus(data) {
    const iconEl = document.getElementById('subStatusIcon');
    const labelEl = document.getElementById('subPlanLabel');
    const detailEl = document.getElementById('subPlanDetail');
    const cardInfo = document.getElementById('subCardInfo');
    const cardBadge = document.getElementById('subCardBadge');
    const datesEl = document.getElementById('subDates');
    const payBtn = document.getElementById('subPayBtn');
    const rePayBtn = document.getElementById('subRePayBtn');
    const cancelBtn = document.getElementById('subCancelBtn');

    const plan = data.subscription_plan;
    const active = data.active;

    if (plan === 'enterprise' && active) {
        iconEl.textContent = '✅';
        iconEl.style.background = '#f0fdf4';
        labelEl.textContent = '유료 구독중';
        labelEl.style.color = 'var(--success)';
        detailEl.textContent = 'Enterprise 플랜 — Q&A 1,000건, 관리자 50명';
        payBtn.textContent = '카드 변경';
        payBtn.style.display = '';
        rePayBtn.style.display = '';
        cancelBtn.style.display = '';
    } else if (plan === 'trial' && active) {
        iconEl.textContent = '⏳';
        iconEl.style.background = '#fffbeb';
        labelEl.textContent = '무료 체험중';
        labelEl.style.color = '#f59e0b';
        let daysLeft = '';
        if (data.trial_ends_at) {
            const diff = Math.ceil((new Date(data.trial_ends_at) - new Date()) / 86400000);
            daysLeft = ' (' + Math.max(diff, 0) + '일 남음)';
        }
        detailEl.textContent = 'Trial 플랜' + daysLeft + ' — 카드 등록 시 유료 전환';
        payBtn.textContent = '카드 등록 및 결제';
        payBtn.style.display = '';
        rePayBtn.style.display = 'none';
        cancelBtn.style.display = 'none';
    } else {
        iconEl.textContent = '💳';
        iconEl.style.background = 'var(--gray-50)';
        labelEl.textContent = '무료 플랜';
        labelEl.style.color = 'var(--gray-700)';
        detailEl.textContent = 'Free 플랜 — Q&A 100건, 관리자 5명';
        payBtn.textContent = '카드 등록 및 결제';
        payBtn.style.display = '';
        rePayBtn.style.display = 'none';
        cancelBtn.style.display = 'none';
    }

    // 카드 정보
    if (data.has_billing_key && data.card_company) {
        cardInfo.style.display = '';
        cardBadge.textContent = '💳 ' + data.card_company + ' ' + (data.card_number || '');
    } else {
        cardInfo.style.display = 'none';
    }

    // 결제 날짜 정보 (결제 내역에서 가져옴 — 비동기로 업데이트)
    loadPaymentDates();
}

async function loadPaymentDates() {
    const sess = AuthSession.get();
    if (!sess) return;

    try {
        const history = await apiGet('/billing/history?company_id=' + sess.companyId);
        const payments = (history.payments || []).filter(p => p.status === 'success');

        const datesEl = document.getElementById('subDates');
        const lastPaidEl = document.getElementById('subLastPaid');
        const nextPayEl = document.getElementById('subNextPay');
        const amountEl = document.getElementById('subAmount');

        if (payments.length > 0) {
            datesEl.style.display = '';
            const lastPayment = payments[0]; // most recent
            const lastDate = new Date(lastPayment.paid_at);
            lastPaidEl.textContent = lastDate.toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' });

            // 다음 결제일 = 마지막 결제일 + 30일
            const nextDate = new Date(lastDate);
            nextDate.setDate(nextDate.getDate() + 30);
            nextPayEl.textContent = nextDate.toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' });

            amountEl.textContent = lastPayment.amount.toLocaleString() + '원';
        } else {
            datesEl.style.display = 'none';
        }
    } catch (e) {
        // 무시
    }
}

function renderPaymentHistory(payments) {
    const tbody = document.getElementById('subHistoryBody');
    const empty = document.getElementById('subHistoryEmpty');

    if (!payments.length) {
        tbody.innerHTML = '';
        empty.style.display = '';
        return;
    }

    empty.style.display = 'none';
    tbody.innerHTML = payments.map(p => {
        const date = new Date(p.paid_at).toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
        const statusClass = p.status === 'success' ? 'sub-status-active' : 'sub-status-failed';
        const statusText = p.status === 'success' ? '성공' : '실패';
        return `<tr>
            <td>${date}</td>
            <td>${p.order_name || '-'}</td>
            <td style="text-align:right">${p.amount.toLocaleString()}원</td>
            <td><span class="${statusClass}">${statusText}</span></td>
            <td style="font-size:0.8rem;color:var(--gray-500)">${p.failure_reason || ''}</td>
        </tr>`;
    }).join('');
}

async function initSubscriptionPayment() {
    const sess = AuthSession.get();
    if (!sess) { showToast('로그인이 필요합니다.', 'error'); return; }

    try {
        // 토스 Client Key 가져오기
        const keyData = await apiGet('/billing/client-key');
        if (!keyData.clientKey) {
            showToast('결제 설정이 되어 있지 않습니다.', 'error');
            return;
        }

        // Toss Payments SDK v2 초기화
        tossPayments = TossPayments(keyData.clientKey);
        const payment = tossPayments.payment();
        const customerKey = 'company_' + sess.companyId;
        const origin = window.location.origin;

        // 카드 등록 (빌링키 발급) 페이지로 리다이렉트
        await payment.requestBillingAuth({
            method: 'CARD',
            customerKey: customerKey,
            successUrl: origin + '/api/billing/success',
            failUrl: origin + '/api/billing/fail',
        });
    } catch (e) {
        if (e.code === 'USER_CANCEL') return;
        showToast('결제 초기화 실패: ' + (e.message || e), 'error');
    }
}

async function executeRePayment() {
    const sess = AuthSession.get();
    if (!sess) return;

    if (!confirm('구독을 갱신 결제하시겠습니까?\n마지막 결제일이 새 구독 기준일이 됩니다.')) return;

    try {
        const result = await apiPost('/billing/pay', {
            company_id: sess.companyId,
            order_name: '보듬누리 구독 갱신',
        });

        if (result.success) {
            showToast('결제가 완료되었습니다! (' + (result.amount || 0).toLocaleString() + '원)', 'success');
            loadSubscriptionTab(); // 새로고침
        } else {
            showToast('결제 실패: ' + result.message, 'error');
        }
    } catch (e) {
        showToast('결제 오류: ' + (e.message || e), 'error');
    }
}

async function cancelSubscription() {
    const sess = AuthSession.get();
    if (!sess) return;

    if (!confirm('구독을 해지하시겠습니까?\nFree 플랜으로 전환되며, Q&A 100건 / 관리자 5명으로 제한됩니다.')) return;

    try {
        const result = await apiPost('/billing/cancel?company_id=' + sess.companyId);
        if (result.success) {
            showToast('구독이 해지되었습니다.', 'warning');
            loadSubscriptionTab();
            loadStats(); // 대시보드 구독 상태 갱신
        } else {
            showToast(result.message, 'error');
        }
    } catch (e) {
        showToast('해지 오류: ' + (e.message || e), 'error');
    }
}
