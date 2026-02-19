const API_BASE = '/api';

/* ──────────────────────────────────────────────
 *  ApiError — structured error with HTTP status
 * ────────────────────────────────────────────── */
class ApiError extends Error {
    constructor(message, status, data) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.data = data;
    }
}

/* ──────────────────────────────────────────────
 *  AuthSession — client-side session manager
 *  Stores session data in sessionStorage (default)
 *  or localStorage ("로그인 유지" checked).
 * ────────────────────────────────────────────── */
const AUTH_KEY = 'acc_auth_session';

const AuthSession = {
    /**
     * Save session data returned from server.
     * @param {object} session  - {user_id, company_id, company_name, email, full_name, role, ...}
     * @param {boolean} persist - true = localStorage (remember me)
     * @param {string} [token]  - JWT token string
     */
    save(session, persist, token) {
        const data = {
            isLoggedIn: true,
            userId: session.user_id,
            username: session.username,
            companyId: session.company_id,
            companyCode: session.company_id,
            companyName: session.company_name,
            email: session.email,
            fullName: session.full_name,
            role: session.role,
            permissions: session.permissions,
            loginTime: session.login_time,
            expiryTime: session.expiry_time,
            billingActive: session.billing_active || false,
            subscriptionPlan: session.subscription_plan || null,
            token: token || session.token || null,
        };
        const store = persist ? localStorage : sessionStorage;
        // Clear the other store to avoid stale data
        localStorage.removeItem(AUTH_KEY);
        sessionStorage.removeItem(AUTH_KEY);
        store.setItem(AUTH_KEY, JSON.stringify(data));
    },

    /** Return parsed session object or null. */
    get() {
        const raw = sessionStorage.getItem(AUTH_KEY) || localStorage.getItem(AUTH_KEY);
        if (!raw) return null;
        try {
            return JSON.parse(raw);
        } catch {
            return null;
        }
    },

    /** Return JWT token string or null. */
    getToken() {
        const s = this.get();
        return s ? s.token : null;
    },

    /** Remove session from both stores. */
    clear() {
        sessionStorage.removeItem(AUTH_KEY);
        localStorage.removeItem(AUTH_KEY);
    },

    /** True if a session exists and has not expired client-side. */
    isValid() {
        const s = this.get();
        if (!s || !s.isLoggedIn) return false;
        if (new Date(s.expiryTime) <= new Date()) {
            this.clear();
            return false;
        }
        return true;
    },

    /** Redirect to login and clear session. */
    redirectToLogin(returnUrl) {
        this.clear();
        if (!window.location.pathname.includes('login')) {
            const url = returnUrl || '/login.html';
            window.location.href = url;
        }
    },
};

/* ──────────────────────────────────────────────
 *  API fetch wrapper
 * ────────────────────────────────────────────── */
async function apiFetch(path, options = {}) {
    // Client-side expiry guard (skip for auth endpoints)
    if (!path.startsWith('/auth/')) {
        const sess = AuthSession.get();
        if (sess && sess.expiryTime && new Date(sess.expiryTime) <= new Date()) {
            AuthSession.clear();
            if (!window.location.pathname.includes('login')) {
                window.location.href = '/login.html';
            }
            throw new ApiError('세션이 만료되었습니다. 다시 로그인해 주세요.', 401);
        }
    }

    const url = `${API_BASE}${path}`;
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };

    // Attach JWT Authorization header if available
    const token = AuthSession.getToken();
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const config = {
        ...options,
        headers,
        credentials: 'same-origin',
    };

    try {
        const response = await fetch(url, config);

        let data;
        try {
            data = await response.json();
        } catch {
            if (!response.ok) {
                throw new ApiError('서버 오류가 발생했습니다. (HTTP ' + response.status + ')', response.status);
            }
            throw new ApiError('서버 응답을 처리할 수 없습니다.', response.status);
        }

        if (!response.ok) {
            let message = '요청 처리 중 오류가 발생했습니다.';
            if (typeof data.detail === 'string') {
                message = data.detail;
            } else if (Array.isArray(data.detail)) {
                message = data.detail.map(e => e.msg || JSON.stringify(e)).join(', ');
            } else if (typeof data.message === 'string') {
                message = data.message;
            }

            if (response.status === 401 && !path.startsWith('/auth/')) {
                AuthSession.redirectToLogin();
            }

            throw new ApiError(message, response.status, data);
        }
        return data;
    } catch (err) {
        if (err instanceof ApiError) throw err;
        if (err.message === 'Failed to fetch') {
            throw new ApiError('서버에 연결할 수 없습니다.', 0);
        }
        throw err;
    }
}

async function apiGet(path) {
    return apiFetch(path, { method: 'GET' });
}

async function apiPost(path, body) {
    return apiFetch(path, {
        method: 'POST',
        body: JSON.stringify(body),
    });
}

async function apiPut(path, body) {
    return apiFetch(path, {
        method: 'PUT',
        body: JSON.stringify(body),
    });
}

async function apiDelete(path) {
    return apiFetch(path, { method: 'DELETE' });
}

async function apiPatch(path, body) {
    return apiFetch(path, {
        method: 'PATCH',
        body: body ? JSON.stringify(body) : undefined,
    });
}

function generateSessionId() {
    return 'sess_' + Date.now() + '_' + Math.random().toString(36).substring(2, 9);
}
