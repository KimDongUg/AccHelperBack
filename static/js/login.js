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

        const companyCode = document.getElementById('companyCode').value.trim();
        const email = document.getElementById('email').value.trim();
        const password = document.getElementById('password').value;
        const remember = document.getElementById('remember').checked;

        if (!companyCode) {
            showError('회사 ID를 입력해 주세요.');
            return;
        }
        if (!email) {
            showError('이메일을 입력해 주세요.');
            return;
        }
        if (!password) {
            showError('비밀번호를 입력해 주세요.');
            return;
        }

        setLoading(true);

        try {
            const result = await apiPost('/auth/login', {
                company_id: parseInt(companyCode, 10),
                email,
                password,
                remember,
            });

            if (result.success && result.session) {
                // Persist session and JWT token client-side
                console.log('[LOGIN] success → result.token:', result.token ? 'exists(' + result.token.substring(0, 20) + ')' : 'NULL',
                    '| remember:', remember, '| role:', result.session.role,
                    '| billing_active:', result.session.billing_active);
                AuthSession.save(result.session, result.token, remember);
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

    // Focus company code field
    document.getElementById('companyCode').focus();
});
