/* ═══════════════════════════════════════════════
 *  Super Admin Dashboard
 * ═══════════════════════════════════════════════ */

let sessionCheckTimer = null;
let subscriberCache = {}; // company_id → SubscriberItem

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
        const role = sess.role || 'viewer';

        // Role guard — only super_admin allowed
        if (role !== 'super_admin') {
            window.location.href = '/admin.html';
            return;
        }

        // Header display
        document.getElementById('headerCompanyName').textContent = sess.company_name || '';
        const displayName = sess.full_name || sess.email || sess.username || '';
        document.getElementById('headerUsername').textContent = displayName + '님';

        // Role badge
        const roleBadge = document.getElementById('roleBadge');
        roleBadge.textContent = '최고관리자';
        roleBadge.className = 'role-badge role-super_admin';
        roleBadge.style.display = 'inline-block';

    } catch { AuthSession.redirectToLogin(); return; }

    // Session watcher
    sessionCheckTimer = setInterval(() => {
        if (!AuthSession.isValid()) {
            clearInterval(sessionCheckTimer);
            showToast('세션이 만료되었습니다.', 'warning');
            setTimeout(() => AuthSession.redirectToLogin(), 1500);
        }
    }, 60_000);

    // Logout
    document.getElementById('logoutBtn').addEventListener('click', async () => {
        clearInterval(sessionCheckTimer);
        try { await apiPost('/auth/logout', {}); } catch {}
        AuthSession.clear();
        window.location.href = '/login.html';
    });

    // Load all data
    loadOverview();
    loadSubscribers();
    loadPayments();

    // Payment filters
    document.getElementById('paymentCompanyFilter').addEventListener('change', () => loadPayments());
    document.getElementById('paymentStatusFilter').addEventListener('change', () => loadPayments());
});

/* ═══════════════════════════════════════════════
 *  OVERVIEW — 6 stat cards
 * ═══════════════════════════════════════════════ */
async function loadOverview() {
    try {
        const data = await apiGet('/admin-dashboard/overview');
        document.getElementById('statTotalCompanies').textContent = data.total_companies ?? 0;
        document.getElementById('statActiveSubscribers').textContent = data.active_subscribers ?? 0;
        document.getElementById('statTrialSubscribers').textContent = data.trial_subscribers ?? 0;
        document.getElementById('statFreeCompanies').textContent = data.free_companies ?? 0;
        document.getElementById('statTotalRevenue').textContent = formatMoney(data.total_revenue ?? 0);
        document.getElementById('statTotalPayments').textContent = data.total_payments ?? 0;
    } catch (e) {
        console.error('Overview load error:', e);
        showToast('현황 데이터를 불러올 수 없습니다.', 'error');
    }
}

/* ═══════════════════════════════════════════════
 *  SUBSCRIBERS TABLE
 * ═══════════════════════════════════════════════ */
async function loadSubscribers() {
    const loading = document.getElementById('subscribersLoading');
    loading.classList.add('show');

    try {
        const data = await apiGet('/admin-dashboard/subscribers');
        const items = data.subscribers || data.items || data;
        const list = Array.isArray(items) ? items : [];

        // Build cache for modal lookup
        subscriberCache = {};
        list.forEach(s => { subscriberCache[s.company_id] = s; });

        renderSubscribers(list);

        // Populate company filter for payments & upload modal
        if (Array.isArray(items) && items.length > 0) {
            const select = document.getElementById('paymentCompanyFilter');
            const uploadSelect = document.getElementById('uploadCompany');
            items.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s.company_id;
                opt.textContent = s.company_name;
                select.appendChild(opt);

                const opt2 = document.createElement('option');
                opt2.value = s.company_id;
                opt2.textContent = s.company_name;
                uploadSelect.appendChild(opt2);
            });
        }
    } catch (e) {
        console.error('Subscribers load error:', e);
        showToast('구독 현황을 불러올 수 없습니다.', 'error');
    } finally {
        loading.classList.remove('show');
    }
}

function renderSubscribers(items) {
    const tbody = document.getElementById('subscribersTableBody');
    const empty = document.getElementById('subscribersEmpty');

    if (items.length === 0) {
        tbody.innerHTML = '';
        empty.style.display = 'block';
        return;
    }

    empty.style.display = 'none';
    tbody.innerHTML = items.map(s => {
        const approvalStatus = s.approval_status || 'approved';
        const showActions = approvalStatus === 'pending' || approvalStatus === 'rejected';
        return `
        <tr>
            <td>${s.company_id ?? '-'}</td>
            <td><a href="#" class="cell-link" onclick="openCompanyModal(${s.company_id});return false">${escapeHtml(s.company_name || '-')}</a></td>
            <td>${renderApprovalBadge(approvalStatus)}</td>
            <td>${escapeHtml(s.plan || s.subscription_plan || '-')}</td>
            <td>${renderStatusBadge(s.subscription_status || s.status || (s.subscription_plan === 'trial' && s.billing_active ? 'trial' : (s.billing_active ? 'active' : 'free')), s.trial_ends_at)}</td>
            <td class="col-card">${escapeHtml(s.card_number ? (s.card_company ? s.card_company + ' ' : '') + s.card_number : (s.has_billing_key ? '카드 등록됨' : '-'))}</td>
            <td>${s.total_paid != null ? formatMoney(s.total_paid) : '-'}</td>
            <td class="col-date" style="white-space:nowrap">${s.last_paid_at || s.last_payment_date ? formatDate(s.last_paid_at || s.last_payment_date) : '-'}</td>
            <td><div class="action-btn-group">
                <button class="btn-admin-view" onclick="goToCompanyAdmin(${s.company_id})" title="${escapeHtml(s.company_name)} 관리자 화면으로 이동">관리자화면</button>
                ${showActions ? `<button class="btn-validate" onclick="validateCompanyData(${s.company_id}, '${escapeHtml(s.company_name)}')">검증</button>
                <button class="btn-approve" onclick="approveCompany(${s.company_id}, '${escapeHtml(s.company_name)}')">승인</button>
                <button class="btn-reject" onclick="openRejectModal(${s.company_id}, '${escapeHtml(s.company_name)}')">반려</button>` : ''}
                ${approvalStatus === 'rejected' ? `<button class="btn-delete" onclick="deleteCompany(${s.company_id}, '${escapeHtml(s.company_name)}')">삭제</button>` : ''}
                ${approvalStatus === 'approved' ? (s.billing_active ? `<button class="btn-sub-deactivate" onclick="toggleSubscription(${s.company_id}, '${escapeHtml(s.company_name)}', false)">구독 해제</button>` : `<button class="btn-sub-activate" onclick="toggleSubscription(${s.company_id}, '${escapeHtml(s.company_name)}', true)">구독 활성</button>`) : ''}
            </div></td>
        </tr>`;
    }).join('');
}

/* ═══════════════════════════════════════════════
 *  COMPANY DETAIL MODAL
 * ═══════════════════════════════════════════════ */
async function openCompanyModal(companyId) {
    const s = subscriberCache[companyId];
    if (!s) return;

    document.getElementById('companyModalTitle').textContent = s.company_name;

    const planLabel = { enterprise: '유료(Enterprise)', trial: '체험(Trial)', free: '무료' }[s.subscription_plan] || s.subscription_plan;
    let statusLabel = s.billing_active
        ? (s.subscription_plan === 'trial' ? '체험중' : '활성')
        : '비활성';
    if (s.subscription_plan === 'trial' && s.trial_ends_at) {
        const diff = Math.ceil((new Date(s.trial_ends_at) - new Date()) / 86400000);
        statusLabel += ` (${diff > 0 ? diff : 0}일)`;
    }

    let cardInfo = '-';
    if (s.card_number) {
        cardInfo = (s.card_company || '') + ' ' + s.card_number;
    } else if (s.has_billing_key) {
        cardInfo = '카드 등록됨';
    }

    const approvalStatus = s.approval_status || 'approved';
    const showApprovalActions = approvalStatus === 'pending' || approvalStatus === 'rejected';

    const body = document.getElementById('companyModalBody');
    body.innerHTML = `
        <div class="detail-grid">
            <div class="detail-row"><span class="detail-label">회사번호</span><span class="detail-value">${s.company_id}</span></div>
            <div class="detail-row"><span class="detail-label">사업자등록번호</span><span class="detail-value">${escapeHtml(s.business_number || '-')}</span></div>
            <div class="detail-row" style="grid-column:1/-1"><span class="detail-label">회사 주소</span><span class="detail-value">${escapeHtml(s.address || '-')}</span></div>
            <div class="detail-row"><span class="detail-label">승인 상태</span><span class="detail-value">${renderApprovalBadge(approvalStatus)}</span></div>
            <div class="detail-row"><span class="detail-label">승인일</span><span class="detail-value">${s.approved_at ? formatDate(s.approved_at) : '-'}</span></div>
            ${approvalStatus === 'rejected' && s.rejection_reason ? `<div class="detail-row" style="grid-column:1/-1"><span class="detail-label">반려 사유</span><span class="detail-value" style="color:var(--danger)">${escapeHtml(s.rejection_reason)}</span></div>` : ''}
            <div class="detail-row"><span class="detail-label">플랜</span><span class="detail-value">${escapeHtml(planLabel)}</span></div>
            <div class="detail-row"><span class="detail-label">구독 상태</span><span class="detail-value">${statusLabel}</span></div>
            <div class="detail-row"><span class="detail-label">카드 정보</span><span class="detail-value">${escapeHtml(cardInfo)}</span></div>
            <div class="detail-row"><span class="detail-label">결제 합계</span><span class="detail-value">${formatMoney(s.total_paid)}</span></div>
            <div class="detail-row"><span class="detail-label">결제 건수</span><span class="detail-value">${s.payment_count ?? 0}건</span></div>
            <div class="detail-row"><span class="detail-label">최종 결제일</span><span class="detail-value">${s.last_paid_at ? formatDate(s.last_paid_at) : '-'}</span></div>
            <div class="detail-row"><span class="detail-label">체험 종료일</span><span class="detail-value">${s.trial_ends_at ? formatDate(s.trial_ends_at) : '-'}</span></div>
            <div class="detail-row"><span class="detail-label">등록일</span><span class="detail-value">${s.created_at ? formatDate(s.created_at) : '-'}</span></div>
        </div>
        <h4 class="admin-list-title">관리자 목록</h4>
        <div id="adminListArea" class="admin-list-area"><span class="stat-loading"></span> 로딩 중...</div>
    `;

    // Update modal footer with approval buttons if needed
    const modalFooter = document.querySelector('#companyModal .modal-footer');
    if (showApprovalActions) {
        modalFooter.innerHTML = `
            <button class="btn btn-outline" onclick="closeCompanyModal()">닫기</button>
            <button class="btn-approve" style="padding:0.5rem 1rem;font-size:var(--text-sm)" onclick="closeCompanyModal();approveCompany(${s.company_id}, '${escapeHtml(s.company_name)}')">승인</button>
            <button class="btn-reject" style="padding:0.5rem 1rem;font-size:var(--text-sm)" onclick="closeCompanyModal();openRejectModal(${s.company_id}, '${escapeHtml(s.company_name)}')">반려</button>
        `;
    } else {
        modalFooter.innerHTML = '<button class="btn btn-outline" onclick="closeCompanyModal()">닫기</button>';
    }

    document.getElementById('companyModal').classList.add('show');

    // Fetch admin list
    try {
        const data = await apiGet('/admin-dashboard/companies/' + companyId + '/admins');
        const admins = data.items || [];
        const area = document.getElementById('adminListArea');
        if (admins.length === 0) {
            area.innerHTML = '<p style="color:var(--gray-500);font-size:var(--text-sm)">등록된 관리자가 없습니다.</p>';
        } else {
            const roleLabels = { super_admin: '최고관리자', admin: '관리자', viewer: '뷰어' };
            area.innerHTML = `<table class="admin-list-table">
                <thead><tr><th>이메일</th><th>이름</th><th>역할</th><th>상태</th><th>최근 로그인</th><th>관리</th></tr></thead>
                <tbody>${admins.map(a => `<tr>
                    <td>${escapeHtml(a.email)}</td>
                    <td>${escapeHtml(a.full_name || '-')}</td>
                    <td>${escapeHtml(roleLabels[a.role] || a.role)}</td>
                    <td>${a.is_active ? '<span style="color:var(--success)">활성</span>' : '<span style="color:var(--gray-400)">비활성</span>'}</td>
                    <td style="white-space:nowrap">${a.last_login ? formatDate(a.last_login) : '-'}</td>
                    <td><button class="btn btn-sm btn-outline" onclick="resetAdminPassword(${a.user_id}, '${escapeHtml(a.email)}')">비밀번호 초기화</button></td>
                </tr>`).join('')}</tbody>
            </table>`;
        }
    } catch (e) {
        const area = document.getElementById('adminListArea');
        if (area) area.innerHTML = '<p style="color:var(--danger);font-size:var(--text-sm)">관리자 목록을 불러올 수 없습니다.</p>';
    }
}

async function resetAdminPassword(userId, email) {
    if (!confirm(`[${email}] 의 비밀번호를 "admin1234"로 초기화하시겠습니까?`)) return;
    try {
        const result = await apiPatch('/admins/' + userId + '/reset-password', { new_password: 'admin1234' });
        if (result.success) {
            alert('비밀번호가 초기화되었습니다.\n\n이메일: ' + email + '\n새 비밀번호: admin1234');
        } else {
            alert('비밀번호 초기화 실패: ' + (result.message || '알 수 없는 오류'));
        }
    } catch (err) {
        alert('비밀번호 초기화 실패: ' + (err.message || '알 수 없는 오류'));
    }
}

function closeCompanyModal() {
    document.getElementById('companyModal').classList.remove('show');
}

/* ═══════════════════════════════════════════════
 *  GO TO COMPANY ADMIN
 * ═══════════════════════════════════════════════ */
function goToCompanyAdmin(companyId) {
    window.location.href = '/admin.html?company=' + companyId;
}

/* ═══════════════════════════════════════════════
 *  PAYMENTS TABLE
 * ═══════════════════════════════════════════════ */
async function loadPayments() {
    const loading = document.getElementById('paymentsLoading');
    loading.classList.add('show');

    const companyId = document.getElementById('paymentCompanyFilter').value;
    const status = document.getElementById('paymentStatusFilter').value;

    const params = new URLSearchParams();
    if (companyId) params.append('company_id', companyId);
    if (status) params.append('status', status);

    const qs = params.toString();
    const url = '/admin-dashboard/payments' + (qs ? '?' + qs : '');

    try {
        const data = await apiGet(url);
        const items = data.payments || data.items || data;
        renderPayments(Array.isArray(items) ? items : []);
    } catch (e) {
        console.error('Payments load error:', e);
        showToast('결제 내역을 불러올 수 없습니다.', 'error');
    } finally {
        loading.classList.remove('show');
    }
}

function renderPayments(items) {
    const tbody = document.getElementById('paymentsTableBody');
    const empty = document.getElementById('paymentsEmpty');

    if (items.length === 0) {
        tbody.innerHTML = '';
        empty.style.display = 'block';
        return;
    }

    empty.style.display = 'none';
    tbody.innerHTML = items.map(p => `
        <tr>
            <td>${p.company_id ?? '-'}</td>
            <td>${escapeHtml(p.company_name || '-')}</td>
            <td>${escapeHtml(p.admin_email || '-')}</td>
            <td>${escapeHtml(p.order_id || p.order_no || '-')}</td>
            <td>${p.amount != null ? formatMoney(p.amount) : '-'}</td>
            <td>${renderPaymentBadge(p.status)}</td>
            <td>${p.paid_at || p.payment_date ? formatDate(p.paid_at || p.payment_date) : '-'}</td>
        </tr>
    `).join('');
}

/* ═══════════════════════════════════════════════
 *  APPROVAL SYSTEM
 * ═══════════════════════════════════════════════ */

function renderApprovalBadge(status) {
    if (!status || status === 'approved') return '<span class="badge-approved">승인됨</span>';
    if (status === 'pending') return '<span class="badge-pending">승인 대기</span>';
    if (status === 'rejected') return '<span class="badge-rejected">반려됨</span>';
    return '<span class="badge-inactive">' + escapeHtml(status) + '</span>';
}

/* ── Validate Company Data ─────────────────── */
async function validateCompanyData(companyId, companyName) {
    document.getElementById('validateModalTitle').textContent = '데이터 검증 결과 - ' + companyName;
    const body = document.getElementById('validateModalBody');
    body.innerHTML = '<div style="text-align:center;padding:2rem"><span class="stat-loading"></span> 검증 중...</div>';
    document.getElementById('validateModalFooter').innerHTML = '<button class="btn btn-outline" onclick="closeValidateModal()">닫기</button>';
    document.getElementById('validateModal').classList.add('show');

    try {
        const result = await apiGet('/admin-dashboard/companies/' + companyId + '/validate-data');
        const warnings = result.warnings || [];

        if (warnings.length === 0) {
            body.innerHTML = '<div class="validation-result"><div class="validation-pass">검증 통과 (경고 없음)</div></div>';
        } else {
            body.innerHTML = `
                <div class="validation-result">
                    <div class="validation-warn-header">${warnings.length}건의 경고 발견</div>
                    <ul class="validation-warn-list">
                        ${warnings.map(w => `<li class="validation-warn-item">
                            <span class="warn-type">[${escapeHtml(w.type || '경고')}]</span>
                            ${escapeHtml(w.message || w.detail || '')}
                            ${w.context ? '<span class="warn-detail">' + escapeHtml(w.context) + '</span>' : ''}
                        </li>`).join('')}
                    </ul>
                </div>
            `;
        }

        // Add approve button in footer
        const approvalStatus = (subscriberCache[companyId] || {}).approval_status || 'pending';
        if (approvalStatus === 'pending' || approvalStatus === 'rejected') {
            document.getElementById('validateModalFooter').innerHTML = `
                <button class="btn btn-outline" onclick="closeValidateModal()">닫기</button>
                <button class="btn-approve" style="padding:0.5rem 1rem;font-size:var(--text-sm)" onclick="closeValidateModal();approveCompany(${companyId}, '${escapeHtml(companyName)}')">승인 진행</button>
            `;
        }
    } catch (e) {
        body.innerHTML = '<div style="color:var(--danger);padding:1rem">검증에 실패했습니다: ' + escapeHtml(e.message) + '</div>';
    }
}

function closeValidateModal() {
    document.getElementById('validateModal').classList.remove('show');
}

/* ── Approve Company ───────────────────────── */
async function approveCompany(companyId, companyName) {
    if (!confirm('[' + companyName + '] 을(를) 승인하시겠습니까?')) return;

    try {
        await apiPatch('/admin-dashboard/companies/' + companyId + '/approve', { status: 'approved' });
        showToast(companyName + ' 승인 완료', 'success');
        loadSubscribers();
    } catch (e) {
        showToast('승인 실패: ' + e.message, 'error');
    }
}

/* ── Reject Company ────────────────────────── */
let rejectTargetCompanyId = null;
let rejectTargetCompanyName = '';

function openRejectModal(companyId, companyName) {
    rejectTargetCompanyId = companyId;
    rejectTargetCompanyName = companyName;
    document.getElementById('rejectModalTitle').textContent = '회사 반려 - ' + companyName;
    document.getElementById('rejectReason').value = '';
    document.getElementById('rejectModal').classList.add('show');
    document.getElementById('rejectReason').focus();
}

function closeRejectModal() {
    document.getElementById('rejectModal').classList.remove('show');
    rejectTargetCompanyId = null;
    rejectTargetCompanyName = '';
}

async function confirmReject() {
    const reason = document.getElementById('rejectReason').value.trim();
    if (!reason) {
        showToast('반려 사유를 입력해 주세요.', 'error');
        return;
    }

    try {
        await apiPatch('/admin-dashboard/companies/' + rejectTargetCompanyId + '/approve', {
            status: 'rejected',
            rejection_reason: reason,
        });
        showToast(rejectTargetCompanyName + ' 반려 완료', 'success');
        closeRejectModal();
        loadSubscribers();
    } catch (e) {
        showToast('반려 실패: ' + e.message, 'error');
    }
}

/* ═══════════════════════════════════════════════
 *  TOGGLE SUBSCRIPTION (수동 활성/해제)
 * ═══════════════════════════════════════════════ */
async function toggleSubscription(companyId, companyName, activate) {
    const action = activate ? '구독 활성화' : '구독 해제';
    if (!confirm('[' + companyName + '] ' + action + '하시겠습니까?' + (activate ? '\n\n오프라인 자동이체 등 수동 결제 업체에 사용합니다.' : ''))) return;

    try {
        await apiPatch('/admin-dashboard/companies/' + companyId + '/subscription', {
            billing_active: activate,
            subscription_plan: activate ? 'enterprise' : 'free',
        });
        showToast(companyName + ' ' + action + ' 완료', 'success');
        loadSubscribers();
        loadOverview();
    } catch (e) {
        showToast(action + ' 실패: ' + e.message, 'error');
    }
}

/* ═══════════════════════════════════════════════
 *  DELETE REJECTED COMPANY
 * ═══════════════════════════════════════════════ */
async function deleteCompany(companyId, companyName) {
    if (!confirm('[' + companyName + '] 회사를 삭제하시겠습니까?\n\n이 작업은 되돌릴 수 없습니다.')) return;

    try {
        await apiDelete('/companies/' + companyId);
        showToast(companyName + ' 삭제 완료', 'success');
        loadSubscribers();
    } catch (e) {
        showToast('삭제 실패: ' + e.message, 'error');
    }
}

/* ═══════════════════════════════════════════════
 *  BADGE RENDERERS
 * ═══════════════════════════════════════════════ */
function renderStatusBadge(status, trialEndsAt) {
    if (!status) return '<span class="badge-inactive">-</span>';
    const s = status.toLowerCase();
    if (s === 'active' || s === 'paid')       return `<span class="badge-active">활성</span>`;
    if (s === 'trial') {
        let daysLeft = '';
        if (trialEndsAt) {
            const diff = Math.ceil((new Date(trialEndsAt) - new Date()) / 86400000);
            daysLeft = ` (${diff > 0 ? diff : 0}일)`;
        }
        return `<span class="badge-trial">체험중${daysLeft}</span>`;
    }
    if (s === 'expired' || s === 'cancelled') return `<span class="badge-expired">${s === 'expired' ? '만료' : '해지'}</span>`;
    if (s === 'free')                         return `<span class="badge-inactive">무료</span>`;
    return `<span class="badge-inactive">${escapeHtml(status)}</span>`;
}

function renderPaymentBadge(status) {
    if (!status) return '<span class="badge-inactive">-</span>';
    const s = status.toUpperCase();
    if (s === 'DONE' || s === 'SUCCESS' || s === 'PAID') return `<span class="badge-success">성공</span>`;
    if (s === 'FAILED')                                   return `<span class="badge-failed">실패</span>`;
    if (s === 'CANCELED' || s === 'CANCELLED')             return `<span class="badge-cancelled">취소</span>`;
    return `<span class="badge-inactive">${escapeHtml(status)}</span>`;
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
 *  EXCEL UPLOAD
 * ═══════════════════════════════════════════════ */
function openUploadModal() {
    const uploadCompany = document.getElementById('uploadCompany');
    if (uploadCompany.options.length > 0) uploadCompany.selectedIndex = 0;
    document.getElementById('uploadFile').value = '';
    document.getElementById('uploadFileName').style.display = 'none';
    document.getElementById('uploadFileName').textContent = '';
    document.getElementById('uploadResult').style.display = 'none';
    document.getElementById('uploadBtn').classList.remove('loading');
    document.getElementById('uploadBtn').disabled = false;
    document.getElementById('uploadModal').classList.add('show');

    const fileArea = document.getElementById('uploadFileArea');
    const fileInput = document.getElementById('uploadFile');
    fileArea.onclick = () => fileInput.click();

    fileArea.ondragover = (e) => { e.preventDefault(); fileArea.classList.add('dragover'); };
    fileArea.ondragleave = () => fileArea.classList.remove('dragover');
    fileArea.ondrop = (e) => {
        e.preventDefault();
        fileArea.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file && file.name.endsWith('.xlsx')) {
            const dt = new DataTransfer();
            dt.items.add(file);
            fileInput.files = dt.files;
            showSelectedFile(file.name);
        } else {
            showToast('.xlsx 파일만 업로드 가능합니다.', 'error');
        }
    };

    fileInput.onchange = () => {
        if (fileInput.files.length > 0) showSelectedFile(fileInput.files[0].name);
    };
}

function showSelectedFile(name) {
    const el = document.getElementById('uploadFileName');
    el.textContent = name;
    el.style.display = 'block';
}

function closeUploadModal() {
    document.getElementById('uploadModal').classList.remove('show');
}

async function downloadTemplate() {
    try {
        await apiDownload('/super/qa/upload-template', 'qa_upload_template.xlsx');
    } catch (e) {
        showToast('양식 다운로드에 실패했습니다: ' + e.message, 'error');
    }
}

async function uploadExcel() {
    const companyId = document.getElementById('uploadCompany').value;
    if (!companyId) { showToast('회사를 선택해 주세요.', 'error'); return; }

    const fileInput = document.getElementById('uploadFile');
    if (!fileInput.files || fileInput.files.length === 0) { showToast('엑셀 파일을 선택해 주세요.', 'error'); return; }

    const uploadBtn = document.getElementById('uploadBtn');
    uploadBtn.classList.add('loading');
    uploadBtn.disabled = true;

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
        const result = await apiFetch('/super/qa/upload?company_id=' + companyId, {
            method: 'POST',
            body: formData,
        });

        const resultDiv = document.getElementById('uploadResult');
        resultDiv.style.display = 'block';

        document.getElementById('uploadResultStats').innerHTML = `
            <div class="upload-stat-item total"><span class="upload-stat-label">전체 행</span><span class="upload-stat-value">${result.total_rows || 0}</span></div>
            <div class="upload-stat-item success"><span class="upload-stat-label">등록 성공</span><span class="upload-stat-value">${result.created || 0}</span></div>
            <div class="upload-stat-item skipped"><span class="upload-stat-label">건너뜀</span><span class="upload-stat-value">${result.skipped || 0}</span></div>
            <div class="upload-stat-item failed"><span class="upload-stat-label">실패</span><span class="upload-stat-value">${result.failed || 0}</span></div>
        `;

        const errorsDiv = document.getElementById('uploadResultErrors');
        if (result.errors && result.errors.length > 0) {
            errorsDiv.style.display = 'block';
            errorsDiv.innerHTML = '<h5>오류 상세</h5><ul>' +
                result.errors.map(e => `<li>${escapeHtml(typeof e === 'string' ? e : (e.row ? '행 ' + e.row + ': ' : '') + (e.message || e.error || JSON.stringify(e)))}</li>`).join('') +
                '</ul>';
        } else {
            errorsDiv.style.display = 'none';
        }

        if ((result.created || 0) > 0) {
            showToast(`${result.created}건의 Q&A가 등록되었습니다.`, 'success');
        }
    } catch (e) {
        showToast('업로드에 실패했습니다: ' + e.message, 'error');
    } finally {
        uploadBtn.classList.remove('loading');
        uploadBtn.disabled = false;
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

function formatMoney(n) {
    if (n == null || isNaN(n)) return '0원';
    return Number(n).toLocaleString() + '원';
}

function formatDate(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '-';
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const h = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');
    return `${y}-${m}-${day} ${h}:${min}`;
}
