/* ── Site Intro slide-up ───────────────────── */
setTimeout(() => {
    const intro = document.querySelector('.site-intro');
    if (!intro) return;
    const inner = intro.querySelector('.site-intro-inner');
    const totalH = intro.offsetHeight;
    const isMobile = window.innerWidth <= 767;

    if (isMobile) {
        // 모바일: 컨테이너도 함께 줄어들며 아래 컨텐츠가 따라 올라감
        intro.style.height = totalH + 'px';
        intro.style.transition = 'height 24s cubic-bezier(0.4, 0, 0.2, 1)';
        requestAnimationFrame(() => {
            inner.style.transform = 'translateY(-' + totalH + 'px)';
            intro.style.height = '0px';
            intro.style.overflow = 'hidden';
            intro.style.paddingTop = '0';
            intro.style.paddingBottom = '0';
            intro.style.borderBottom = 'none';
        });
    } else {
        // 태블릿/데스크탑: 높이 고정, 레이아웃 변동 없음
        intro.style.height = totalH + 'px';
        requestAnimationFrame(() => {
            inner.style.transform = 'translateY(-' + totalH + 'px)';
        });
    }

    // 슬라이드(24초) 끝난 뒤 남은 글자 fade out
    setTimeout(() => {
        inner.classList.add('fade');
    }, 24000);
}, 5000);

/* ── State ──────────────────────────────────── */
let currentCompanyCode = null;
let sessionId = sessionStorage.getItem('chatSessionId');
if (!sessionId) {
    sessionId = generateSessionId();
    sessionStorage.setItem('chatSessionId', sessionId);
}
let selectedCategory = '전체';

/* ── DOM refs (chat section — may not exist until shown) ── */
const chatSection     = document.getElementById('chatSection');
const companySelection = document.getElementById('companySelection');
const companyGrid     = document.getElementById('companyGrid');
const companyLoading  = document.getElementById('companyLoading');
const companyError    = document.getElementById('companyError');
const companyErrorMsg = document.getElementById('companyErrorMsg');
const companyLabel    = document.getElementById('companyLabel');

/* ── Initialization ────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('company');

    if (code) {
        // Validate company code and start chat
        validateAndStartChat(code);
    } else {
        // Show company selection
        showCompanySelection();
    }
});

/* ── Company Selection ─────────────────────── */
function showCompanySelection() {
    companySelection.style.display = '';
    chatSection.style.display = 'none';
    loadCompanies();
}

async function loadCompanies() {
    companyLoading.style.display = '';
    companyError.style.display = 'none';
    companyGrid.innerHTML = '';

    try {
        const result = await apiGet('/companies/public');
        const companies = result.companies || result;

        companyLoading.style.display = 'none';

        if (!companies || companies.length === 0) {
            companyErrorMsg.textContent = '등록된 회사가 없습니다.';
            companyError.style.display = '';
            return;
        }

        companies.forEach(c => {
            const card = document.createElement('button');
            card.className = 'company-card' + (c.is_active ? '' : ' company-card-disabled');
            card.setAttribute('type', 'button');

            const icon = document.createElement('div');
            icon.className = 'company-card-icon';
            icon.innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>';

            const info = document.createElement('div');
            info.className = 'company-card-info';

            const name = document.createElement('h3');
            name.textContent = c.company_name;

            const code = document.createElement('span');
            code.className = 'company-card-code';
            code.textContent = c.company_code;

            info.appendChild(name);
            info.appendChild(code);
            card.appendChild(icon);
            card.appendChild(info);

            if (!c.is_active) {
                const badge = document.createElement('span');
                badge.className = 'company-card-badge';
                badge.textContent = '준비중';
                card.appendChild(badge);
                card.disabled = true;
            } else {
                card.addEventListener('click', () => {
                    window.location.href = `/?company=${encodeURIComponent(c.company_code)}`;
                });
            }

            companyGrid.appendChild(card);
        });
    } catch (err) {
        companyLoading.style.display = 'none';
        companyErrorMsg.textContent = err.message || '회사 목록을 불러올 수 없습니다.';
        companyError.style.display = '';
    }
}

/* ── Validate company & start chat ─────────── */
async function validateAndStartChat(code) {
    companySelection.style.display = 'none';
    chatSection.style.display = 'none';

    try {
        const company = await apiGet(`/companies/public/${encodeURIComponent(code)}`);
        currentCompanyCode = company.company_code;

        // Show company name in header
        companyLabel.textContent = company.company_name;
        companyLabel.style.display = '';

        // Show chat
        showChat();
    } catch (err) {
        // Invalid company code — show selection with error
        showCompanySelection();
        companyLoading.style.display = 'none';
        companyErrorMsg.textContent = `회사 코드 "${code}"를 찾을 수 없습니다.`;
        companyError.style.display = '';
    }
}

/* ── Show Chat ─────────────────────────────── */
function showChat() {
    chatSection.style.display = '';
    companySelection.style.display = 'none';

    const chatMessages   = document.getElementById('chatMessages');
    const chatInput      = document.getElementById('chatInput');
    const sendBtn        = document.getElementById('sendBtn');
    const typingIndicator = document.getElementById('typingIndicator');
    const quickQuestions  = document.getElementById('quickQuestions');

    // Category filter handling
    document.querySelectorAll('.category-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.category-btn').forEach(b => {
                b.classList.remove('active');
                b.setAttribute('aria-pressed', 'false');
            });
            btn.classList.add('active');
            btn.setAttribute('aria-pressed', 'true');
            selectedCategory = btn.dataset.category;
        });
    });

    // Quick question buttons
    document.querySelectorAll('.quick-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            sendMessage(btn.dataset.question);
        });
    });

    // Send button
    sendBtn.addEventListener('click', () => {
        const text = chatInput.value.trim();
        if (text) sendMessage(text);
    });

    // Enter key
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.isComposing) {
            e.preventDefault();
            const text = chatInput.value.trim();
            if (text) sendMessage(text);
        }
    });

    async function sendMessage(text) {
        appendMessage('user', text);
        chatInput.value = '';
        chatInput.disabled = true;
        sendBtn.disabled = true;

        typingIndicator.classList.add('show');
        scrollToBottom();

        try {
            const body = {
                question: text,
                session_id: sessionId,
                category: selectedCategory === '전체' ? null : selectedCategory,
            };
            if (currentCompanyCode) {
                body.company_code = currentCompanyCode;
            }

            const result = await apiPost('/chat', body);
            typingIndicator.classList.remove('show');
            appendMessage('bot', result.answer, result.category);
        } catch (err) {
            typingIndicator.classList.remove('show');
            appendMessage('bot', '죄송합니다. 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
        }

        chatInput.disabled = false;
        sendBtn.disabled = false;
        chatInput.focus();
    }

    function appendMessage(type, text, category) {
        const msg = document.createElement('div');
        msg.className = `message ${type}`;
        msg.setAttribute('role', 'article');

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.setAttribute('aria-hidden', 'true');

        if (type === 'bot') {
            avatar.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
        } else {
            avatar.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>';
        }

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';

        if (type === 'bot' && category) {
            const catBadge = document.createElement('div');
            catBadge.className = 'message-category';
            catBadge.textContent = category;
            bubble.appendChild(catBadge);
        }

        const textNode = document.createElement('div');
        textNode.textContent = text;
        bubble.appendChild(textNode);

        msg.appendChild(avatar);
        msg.appendChild(bubble);
        chatMessages.appendChild(msg);

        scrollToBottom();
    }

    function scrollToBottom() {
        setTimeout(() => {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }, 50);
    }

    // Load chat history
    async function loadHistory() {
        try {
            let url = `/chat/history/${sessionId}`;
            if (currentCompanyCode) {
                url += `?company_code=${encodeURIComponent(currentCompanyCode)}`;
            }
            const history = await apiGet(url);
            history.forEach(item => {
                appendMessage('user', item.user_question);
                appendMessage('bot', item.bot_answer, item.category);
            });
            if (history.length > 0) {
                quickQuestions.style.display = 'none';
            }
        } catch (e) {
            // ignore history load errors
        }
    }

    // Check admin status
    async function checkAdmin() {
        try {
            const auth = await apiGet('/auth/check');
            if (auth.authenticated && auth.session) {
                const label = auth.session.full_name || auth.session.username || '';
                document.getElementById('adminLink').textContent = `관리자 (${label})`;
            }
        } catch (e) { /* not logged in */ }
    }

    loadHistory();
    checkAdmin();
    chatInput.focus();
}
