document.addEventListener('DOMContentLoaded', async () => {
    // Parse redirect params from URL (e.g., ?redirect=chat&company=X)
    const urlParams = new URLSearchParams(window.location.search);
    const redirectTarget = urlParams.get('redirect');
    const redirectCompany = urlParams.get('company');

    // Already logged in? — check client-side first, then verify with server
    if (AuthSession.isValid()) {
        try {
            const res = await apiGet('/auth/check');
            if (res.authenticated) {
                // If redirecting to chat, go there instead of admin
                if (redirectTarget === 'chat') {
                    const chatUrl = redirectCompany ? `/?company=${encodeURIComponent(redirectCompany)}` : '/';
                    window.location.href = chatUrl;
                    return;
                }
                if (res.session && res.session.role === 'super_admin') {
                    window.location.href = '/super-admin.html';
                    return;
                }
                const billingActive = (res.session && res.session.billing_active);
                window.location.href = billingActive ? '/admin.html' : '/billing.html';
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

        const companyId = document.getElementById('companyId').value.trim();
        const email = document.getElementById('email').value.trim();
        const password = document.getElementById('password').value;
        const remember = document.getElementById('remember').checked;

        if (!companyId) {
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
                company_id: parseInt(companyId),
                email,
                password,
                remember,
            });

            if (result.success && result.session) {
                // Persist session client-side (with JWT token)
                const jwtToken = result.token || result.session.token || null;
                AuthSession.save(result.session, remember, jwtToken);
                loginCard.classList.add('success');
                const role = result.session.role;
                const billingActive = result.session.billing_active;
                setTimeout(() => {
                    // Redirect to chat if requested via URL params
                    if (redirectTarget === 'chat') {
                        const chatUrl = redirectCompany ? `/?company=${encodeURIComponent(redirectCompany)}` : '/';
                        window.location.href = chatUrl;
                        return;
                    }
                    if (role === 'super_admin') {
                        window.location.href = '/super-admin.html';
                    } else {
                        window.location.href = billingActive ? '/admin.html' : '/billing.html';
                    }
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

    // ── Find Email Modal ──
    const findEmailModal = document.getElementById('findEmailModal');
    const findEmailResult = document.getElementById('findEmailResult');

    function openFindEmail() {
        document.getElementById('findCompanyId').value = document.getElementById('companyId').value || '';
        document.getElementById('findFullName').value = '';
        findEmailResult.className = 'modal-result';
        findEmailResult.innerHTML = '';
        findEmailModal.classList.add('show');
        document.getElementById('findFullName').focus();
    }

    function closeFindEmail() {
        findEmailModal.classList.remove('show');
    }

    document.getElementById('findEmailLink').addEventListener('click', (e) => { e.preventDefault(); openFindEmail(); });
    document.getElementById('findEmailClose').addEventListener('click', closeFindEmail);
    document.getElementById('findEmailCancelBtn').addEventListener('click', closeFindEmail);
    findEmailModal.addEventListener('click', (e) => { if (e.target === findEmailModal) closeFindEmail(); });

    document.getElementById('findEmailBtn').addEventListener('click', async () => {
        const companyId = document.getElementById('findCompanyId').value.trim();
        const fullName = document.getElementById('findFullName').value.trim();
        if (!companyId || !fullName) {
            findEmailResult.className = 'modal-result show error';
            findEmailResult.textContent = '회사 ID와 이름을 모두 입력해 주세요.';
            return;
        }

        const btn = document.getElementById('findEmailBtn');
        btn.disabled = true;
        btn.classList.add('loading');

        try {
            const res = await apiPost('/auth/find-email', { company_id: parseInt(companyId), full_name: fullName });
            if (res.success && res.masked_email) {
                findEmailResult.className = 'modal-result show success';
                findEmailResult.innerHTML = '가입된 이메일:<span class="result-email">' + escapeHtmlSimple(res.masked_email) + '</span>';
            } else {
                findEmailResult.className = 'modal-result show error';
                findEmailResult.textContent = res.message || '일치하는 정보를 찾을 수 없습니다.';
            }
        } catch (err) {
            findEmailResult.className = 'modal-result show error';
            findEmailResult.textContent = err.message || '요청 처리 중 오류가 발생했습니다.';
        } finally {
            btn.disabled = false;
            btn.classList.remove('loading');
        }
    });

    // ── Reset Password Modal ──
    const resetPwModal = document.getElementById('resetPwModal');
    const resetPwResult = document.getElementById('resetPwResult');

    function openResetPw() {
        document.getElementById('resetCompanyId').value = document.getElementById('companyId').value || '';
        document.getElementById('resetEmail').value = document.getElementById('email').value || '';
        resetPwResult.className = 'modal-result';
        resetPwResult.innerHTML = '';
        resetPwModal.classList.add('show');
        document.getElementById('resetEmail').focus();
    }

    function closeResetPw() {
        resetPwModal.classList.remove('show');
    }

    document.getElementById('resetPwLink').addEventListener('click', (e) => { e.preventDefault(); openResetPw(); });
    document.getElementById('resetPwClose').addEventListener('click', closeResetPw);
    document.getElementById('resetPwCancelBtn').addEventListener('click', closeResetPw);
    resetPwModal.addEventListener('click', (e) => { if (e.target === resetPwModal) closeResetPw(); });

    document.getElementById('resetPwBtn').addEventListener('click', async () => {
        const companyId = document.getElementById('resetCompanyId').value.trim();
        const email = document.getElementById('resetEmail').value.trim();
        if (!companyId || !email) {
            resetPwResult.className = 'modal-result show error';
            resetPwResult.textContent = '회사 ID와 이메일을 모두 입력해 주세요.';
            return;
        }

        const btn = document.getElementById('resetPwBtn');
        btn.disabled = true;
        btn.classList.add('loading');

        try {
            const res = await apiPost('/auth/reset-password', { company_id: parseInt(companyId), email });
            if (res.success) {
                resetPwResult.className = 'modal-result show success';
                resetPwResult.textContent = res.message;
            } else {
                resetPwResult.className = 'modal-result show error';
                resetPwResult.textContent = res.message;
            }
        } catch (err) {
            resetPwResult.className = 'modal-result show error';
            resetPwResult.textContent = err.message || '요청 처리 중 오류가 발생했습니다.';
        } finally {
            btn.disabled = false;
            btn.classList.remove('loading');
        }
    });

    // Simple HTML escape for login page (no DOM dependency on admin.js escapeHtml)
    function escapeHtmlSimple(str) {
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // Focus company ID field
    document.getElementById('companyId').focus();
});
