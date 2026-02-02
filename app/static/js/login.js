document.addEventListener('DOMContentLoaded', async () => {
    // Already logged in? — check client-side first, then verify with server
    if (AuthSession.isValid()) {
        try {
            const res = await apiGet('/auth/check');
            if (res.authenticated) {
                window.location.href = '/admin.html';
                return;
            }
            // Server says no — clear stale client session
            AuthSession.clear();
        } catch {
            AuthSession.clear();
        }
    }

    const form = document.getElementById('loginForm');
    const errorDiv = document.getElementById('loginError');
    const errorMsg = document.getElementById('loginErrorMsg');
    const loginBtn = document.getElementById('loginBtn');
    const loginCard = document.getElementById('loginCard');

    function showError(msg) {
        errorMsg.textContent = msg;
        errorDiv.classList.add('show');
    }

    function hideError() {
        errorDiv.classList.remove('show');
    }

    function setLoading(loading) {
        loginBtn.disabled = loading;
        loginBtn.classList.toggle('loading', loading);
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        hideError();

        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value;
        const remember = document.getElementById('remember').checked;

        if (!username || !password) {
            showError('아이디와 비밀번호를 입력해 주세요.');
            return;
        }

        setLoading(true);

        try {
            const result = await apiPost('/auth/login', {
                username,
                password,
                remember,
            });

            if (result.success && result.session) {
                // Persist session client-side
                AuthSession.save(result.session, remember);
                loginCard.classList.add('success');
                setTimeout(() => {
                    window.location.href = '/admin.html';
                }, 300);
            } else {
                setLoading(false);
                showError(result.message);
            }
        } catch (err) {
            setLoading(false);
            showError(err.message);
        }
    });

    // Focus username field
    document.getElementById('username').focus();
});
