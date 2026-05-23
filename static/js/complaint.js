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
