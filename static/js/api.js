const API_BASE = '/api';

/* ──────────────────────────────────────────────
 *  AuthSession — client-side session manager
 *  Stores session data + JWT token in sessionStorage (default)
 *  or localStorage ("로그인 유지" checked).
 * ────────────────────────────────────────────── */
const AUTH_KEY = 'acc_auth_session';
const TOKEN_KEY = 'acc_auth_token';

const AuthSession = {
    /**
     * Save session data and JWT token returned from server.
     * @param {object} session  - {user_id, company_id, company_name, email, full_name, role, ...}
     * @param {string} token    - JWT access token
     * @param {boolean} persist - true = localStorage (remember me)
     */
    save(session, token, persist) {
        const data = {
            isLoggedIn: true,
            userId: session.user_id,
            username: session.username,
            companyId: session.company_id,
            companyName: session.company_name,
            email: session.email,
            fullName: session.full_name,
            role: session.role,
            permissions: session.permissions,
            subscriptionPlan: session.subscription_plan,
            billingActive: session.billing_active,
            loginTime: session.login_time,
            expiryTime: session.expiry_time,
        };
        const store = persist ? localStorage : sessionStorage;
        // Clear the other store to avoid stale data
        localStorage.removeItem(AUTH_KEY);
        sessionStorage.removeItem(AUTH_KEY);
        localStorage.removeItem(TOKEN_KEY);
        sessionStorage.removeItem(TOKEN_KEY);
        store.setItem(AUTH_KEY, JSON.stringify(data));
        if (token) {
            store.setItem(TOKEN_KEY, token);
        }
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

    /** Return stored JWT token or null. */
    getToken() {
        return sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY);
    },

    /** Remove session and token from both stores. */
    clear() {
        sessionStorage.removeItem(AUTH_KEY);
        localStorage.removeItem(AUTH_KEY);
        sessionStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(TOKEN_KEY);
    },

    /** True if a session and token exist. */
    isValid() {
        const s = this.get();
        const t = this.getToken();
        if (!s || !s.isLoggedIn || !t) return false;
        return true;
    },

    /** Redirect to login and clear session. */
    redirectToLogin() {
        this.clear();
        if (!window.location.pathname.includes('login')) {
            window.location.href = '/login.html';
        }
    },
};

/* ──────────────────────────────────────────────
 *  API fetch wrapper (JWT Bearer auth)
 * ────────────────────────────────────────────── */
async function apiFetch(path, options = {}) {
    const url = `${API_BASE}${path}`;
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };

    // Attach JWT token as Authorization header
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
        const data = await response.json();

        if (!response.ok) {
            if (response.status === 401) {
                AuthSession.redirectToLogin();
            }
            throw new Error(data.detail || '요청 처리 중 오류가 발생했습니다.');
        }
        return data;
    } catch (err) {
        if (err.message === 'Failed to fetch') {
            throw new Error('서버에 연결할 수 없습니다.');
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
