/* 민원게시판 공통 JS */

const COMPLAINT_API = '/api/complaints';

// ── 관리자 세션 ──────────────────────────────────────────────────────────────

const ComplaintAuth = {
    getSession() {
        const raw = sessionStorage.getItem('acc_auth_session') || localStorage.getItem('acc_auth_session');
        if (!raw) return null;
        try { return JSON.parse(raw); } catch { return null; }
    },
    isAdmin() {
        const s = this.getSession();
        return s && s.isLoggedIn && (s.role === 'admin' || s.role === 'super_admin');
    },
    getToken() {
        const s = this.getSession();
        return s ? s.token : null;
    },
    getCompanyId() {
        const s = this.getSession();
        return s ? s.companyId : null;
    },
};

// ── company 파라미터 ──────────────────────────────────────────────────────────

function getCompanyParam() {
    return new URLSearchParams(location.search).get('company') ||
           sessionStorage.getItem('complaint_company_id');
}

function setCompanyParam(id) {
    sessionStorage.setItem('complaint_company_id', id);
}

// 회사명 → 동 기본값
function getDefaultDong(companyName) {
    if (!companyName) return '';
    const name = companyName.trim();
    if (name.includes('세종푸르지오시티') && name.includes('2차')) return '1동';
    if (name.includes('세종푸르지오2차')) return '1동';
    return '';
}

// ── fetch helper ──────────────────────────────────────────────────────────────

async function cpFetch(path, opts = {}) {
    const headers = { ...(opts.headers || {}) };
    const token = ComplaintAuth.getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    if (opts.body && typeof opts.body === 'object') {
        headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(opts.body);
    }
    const res = await fetch(COMPLAINT_API + path, { ...opts, headers });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: '오류가 발생했습니다.' }));
        throw new Error(err.detail || '오류가 발생했습니다.');
    }
    return res.json();
}

// ── 토스트 ────────────────────────────────────────────────────────────────────

function showCpToast(msg) {
    let t = document.querySelector('.cp-toast');
    if (!t) {
        t = document.createElement('div');
        t.className = 'cp-toast';
        document.body.appendChild(t);
    }
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2500);
}

// ── 시간 표시 ─────────────────────────────────────────────────────────────────

function cpTimeAgo(iso) {
    const diff = (Date.now() - new Date(iso)) / 1000;
    if (diff < 60) return '방금 전';
    if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
    return `${Math.floor(diff / 86400)}일 전`;
}

// ── HTML escape ───────────────────────────────────────────────────────────────

function escHtml(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── 공통 헤더 초기화 ──────────────────────────────────────────────────────────

function initCpHeader() {
    const companyId   = sessionStorage.getItem('complaint_company_id');
    const companyName = sessionStorage.getItem('market_company_name') || '';
    const sess        = ComplaintAuth.getSession();

    // 회사 이름 표시
    const labelEl = document.getElementById('cpCompanyLabel');
    if (labelEl && companyName) {
        labelEl.textContent = companyName;
        labelEl.style.display = '';
    }

    // 민원게시판 링크에 company 파라미터 삽입
    const cpNav = document.getElementById('cpComplaintNav');
    if (cpNav && companyId) cpNav.href = `/complaint.html?company=${companyId}`;

    // 당근 링크 — 부과내역서 완성 전까지 비활성화
    // const daangnNav = document.getElementById('cpDaangnNav');
    // if (daangnNav) daangnNav.style.display = companyName || companyId ? '' : 'none';

    // 관리자 버튼 처리
    const loginBtn = document.getElementById('cpHeaderLoginLink');
    const adminBtn = document.getElementById('cpAdminLink');
    if (sess && sess.isLoggedIn && sess.token) {
        if (loginBtn) loginBtn.style.display = 'none';
        if (adminBtn) {
            adminBtn.style.display = '';
            adminBtn.textContent = '관리자 (' + (sess.fullName || sess.username || '') + ')';
        }
    } else {
        if (loginBtn) loginBtn.style.display = '';
        if (adminBtn) adminBtn.style.display = 'none';
    }
}
