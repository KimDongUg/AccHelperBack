document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('registerForm');
    const errorDiv = document.getElementById('registerError');
    const errorMsg = document.getElementById('registerErrorMsg');
    const successDiv = document.getElementById('registerSuccess');
    const successMsg = document.getElementById('registerSuccessMsg');
    const registerBtn = document.getElementById('registerBtn');

    function showError(msg) {
        successDiv.classList.remove('show');
        errorMsg.textContent = msg;
        errorDiv.classList.add('show');
    }

    function hideError() {
        errorDiv.classList.remove('show');
    }

    function showSuccess(msg) {
        errorDiv.classList.remove('show');
        successMsg.textContent = msg;
        successDiv.classList.add('show');
    }

    function setLoading(loading) {
        registerBtn.disabled = loading;
        registerBtn.classList.toggle('loading', loading);
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        hideError();

        const companyId = document.getElementById('companyId').value.trim();
        const email = document.getElementById('email').value.trim();
        const password = document.getElementById('password').value;
        const passwordConfirm = document.getElementById('passwordConfirm').value;
        const fullName = document.getElementById('fullName').value.trim();
        const phone = document.getElementById('phone').value.trim();

        if (!companyId) { showError('회사 ID를 입력해 주세요.'); return; }
        if (!email) { showError('이메일을 입력해 주세요.'); return; }
        if (!password) { showError('비밀번호를 입력해 주세요.'); return; }
        if (password.length < 6) { showError('비밀번호는 6자 이상이어야 합니다.'); return; }
        if (password !== passwordConfirm) { showError('비밀번호가 일치하지 않습니다.'); return; }
        if (!fullName) { showError('이름을 입력해 주세요.'); return; }

        setLoading(true);

        try {
            const result = await apiPost('/auth/register', {
                company_id: parseInt(companyId),
                email,
                password,
                full_name: fullName,
                phone: phone || null,
            });

            if (result.success) {
                showSuccess(result.message);
                form.reset();
                setTimeout(() => {
                    window.location.href = '/login.html';
                }, 1500);
            } else {
                showError(result.message);
            }
        } catch (err) {
            showError(err.message);
        } finally {
            setLoading(false);
        }
    });

    document.getElementById('companyId').focus();
});
