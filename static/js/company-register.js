document.addEventListener('DOMContentLoaded', () => {
    const companyForm = document.getElementById('companyForm');
    const userForm = document.getElementById('userForm');
    const errorDiv = document.getElementById('registerError');
    const errorMsg = document.getElementById('registerErrorMsg');
    const successDiv = document.getElementById('registerSuccess');
    const successMsg = document.getElementById('registerSuccessMsg');
    const nextBtn = document.getElementById('nextBtn');
    const registerBtn = document.getElementById('registerBtn');
    const prevBtn = document.getElementById('prevBtn');

    const step1 = document.getElementById('step1');
    const step2 = document.getElementById('step2');
    const step1Indicator = document.getElementById('step1Indicator');
    const step2Indicator = document.getElementById('step2Indicator');
    const companySummary = document.getElementById('companySummary');

    // Step 1에서 수집한 회사 정보 보관
    let companyData = {};

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

    function setLoading(btn, loading) {
        btn.disabled = loading;
        btn.classList.toggle('loading', loading);
    }

    function goToStep2() {
        step1.style.display = 'none';
        step2.style.display = '';
        step1Indicator.classList.remove('active');
        step1Indicator.classList.add('completed');
        step2Indicator.classList.add('active');
        companySummary.textContent = companyData.company_name;
        hideError();
        document.getElementById('email').focus();
    }

    function goToStep1() {
        step2.style.display = 'none';
        step1.style.display = '';
        step2Indicator.classList.remove('active');
        step1Indicator.classList.remove('completed');
        step1Indicator.classList.add('active');
        hideError();
    }

    // Step 1: 회사 정보 수집 + 사업자등록번호 중복 체크 → Step 2로 이동
    companyForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        hideError();

        const buildingTypeEl = document.querySelector('input[name="buildingType"]:checked');
        const companyName = document.getElementById('companyName').value.trim();
        const businessNumber = document.getElementById('businessNumber').value.trim();
        const companyAddress = document.getElementById('companyAddress').value.trim();
        const companyPhone = document.getElementById('companyPhone').value.trim();

        if (!buildingTypeEl) { showError('건물 유형을 선택해 주세요.'); return; }
        if (!companyName) { showError('회사명을 입력해 주세요.'); return; }
        if (!businessNumber) { showError('사업자등록번호를 입력해 주세요.'); return; }
        if (!companyAddress) { showError('회사 주소를 입력해 주세요.'); return; }
        if (!companyPhone) { showError('전화번호를 입력해 주세요.'); return; }

        // 사업자등록번호 중복 체크 (항상 최신 데이터 조회)
        const normalize = (v) => (v || '').replace(/[^0-9]/g, '');
        const inputNum = normalize(businessNumber);
        setLoading(nextBtn, true);
        try {
            const freshResult = await apiGet('/companies/public');
            const companies = Array.isArray(freshResult) ? freshResult : (freshResult.companies || []);
            if (companies.length > 0) {
                const duplicate = companies.find(c => normalize(c.business_number) === inputNum);
                if (duplicate) {
                    setLoading(nextBtn, false);
                    alert('이미 등록된 회사입니다.\n\n사업자등록번호 [' + businessNumber + ']는 이미 등록되어 있습니다.\n기존 회사로 로그인하시거나, 다른 사업자등록번호를 입력해 주세요.');
                    return;
                }
            }
        } catch (err) {
            console.error('사업자등록번호 중복 체크 실패:', err);
        }
        setLoading(nextBtn, false);

        companyData = {
            building_type: buildingTypeEl.value,
            company_name: companyName,
            business_number: businessNumber,
            address: companyAddress,
            phone: companyPhone,
        };

        goToStep2();
    });

    // Previous button
    prevBtn.addEventListener('click', () => {
        goToStep1();
    });

    // Step 2: 관리자 계정 입력 → 회사+관리자 한번에 등록
    userForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        hideError();

        const email = document.getElementById('email').value.trim();
        const password = document.getElementById('password').value;
        const passwordConfirm = document.getElementById('passwordConfirm').value;
        const fullName = document.getElementById('fullName').value.trim();
        const phone = document.getElementById('userPhone').value.trim();

        if (!email) { showError('이메일을 입력해 주세요.'); return; }
        if (!password) { showError('비밀번호를 입력해 주세요.'); return; }
        if (password.length < 6) { showError('비밀번호는 6자 이상이어야 합니다.'); return; }
        if (password !== passwordConfirm) { showError('비밀번호가 일치하지 않습니다.'); return; }
        if (!fullName) { showError('이름을 입력해 주세요.'); return; }

        setLoading(registerBtn, true);

        try {
            const result = await apiPost('/companies/register', {
                ...companyData,
                admin_email: email,
                admin_password: password,
                admin_name: fullName,
                admin_phone: phone || null,
            });

            if (result.success === false) {
                alert(result.message || '등록에 실패했습니다.');
                return;
            }

            const companyId = result.company_id || '';
            userForm.reset();
            alert('🎉 회사 등록이 완료되었습니다!\n\n📌 회사번호: ' + companyId + '\n\n이 번호는 로그인 시 반드시 필요합니다.\n꼭 기억해 주세요!\n\n관리자 승인 후 서비스 이용이 가능합니다.');
            window.location.href = '/login.html';
        } catch (err) {
            showError(err.message);
        } finally {
            setLoading(registerBtn, false);
        }
    });

    document.getElementById('companyName').focus();
});
