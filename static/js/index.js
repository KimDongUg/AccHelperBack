/* ── Site Intro (처음 방문 시에만 표시, 팝업 닫힌 후 시작) ── */
(function () {
    const intro = document.querySelector('.site-intro');
    if (!intro) return;

    // 이미 본 적 있으면 즉시 제거
    if (sessionStorage.getItem('introSeen')) {
        intro.remove();
        return;
    }

    // 팝업이 열려있으면 숨겨두고, 닫힌 후 표시
    var promoOverlay = document.getElementById('promoPopup');
    if (promoOverlay && promoOverlay.classList.contains('show')) {
        intro.style.display = 'none';
        document.addEventListener('promoPopupClosed', function onClose() {
            intro.style.display = '';
            startIntroAnimation();
            document.removeEventListener('promoPopupClosed', onClose);
        });
    } else {
        startIntroAnimation();
    }

    function startIntroAnimation() {
        sessionStorage.setItem('introSeen', '1');

        var isMobile = window.innerWidth <= 400 && window.innerHeight <= 900;

        if (isMobile) {
            // 모바일: 15초 후 3초간 fade out
            setTimeout(function () {
                intro.style.transition = 'opacity 3s ease';
                intro.style.opacity = '0';
                setTimeout(function () { intro.remove(); }, 3000);
            }, 15000);
        } else {
            // 태블릿/데스크탑: 5초 후 슬라이드업
            setTimeout(function () {
                var inner = intro.querySelector('.site-intro-inner');
                var totalH = intro.offsetHeight;

                intro.style.height = totalH + 'px';
                requestAnimationFrame(function () {
                    inner.style.transform = 'translateY(-' + totalH + 'px)';
                });

                setTimeout(function () {
                    inner.classList.add('fade');
                }, 24000);
            }, 5000);
        }
    }
})();

/* ── State ──────────────────────────────────── */
let currentCompanyId = null;
let currentCompanyCode = null;
let sessionId = sessionStorage.getItem('chatSessionId');
if (!sessionId) {
    sessionId = generateSessionId();
    sessionStorage.setItem('chatSessionId', sessionId);
}
let selectedCategory = '전체';
let quotaRemaining = null;

/* ── DOM refs (chat section — may not exist until shown) ── */
const chatSection     = document.getElementById('chatSection');
const companySelection = document.getElementById('companySelection');
const companyGrid     = document.getElementById('companyGrid');
const companyLoading  = document.getElementById('companyLoading');
const companyError    = document.getElementById('companyError');
const companyErrorMsg = document.getElementById('companyErrorMsg');
const companyLabel    = document.getElementById('companyLabel');

/* ── Toast notification ────────────────────── */
function showToast(message, duration) {
    if (duration === undefined) duration = 3000;
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    container.appendChild(toast);
    // Trigger animation
    requestAnimationFrame(function () {
        toast.classList.add('show');
    });
    setTimeout(function () {
        toast.classList.remove('show');
        setTimeout(function () { toast.remove(); }, 300);
    }, duration);
}

/* ── Initialization ────────────────────────── */
document.addEventListener('DOMContentLoaded', function () {
    var params = new URLSearchParams(window.location.search);
    var code = params.get('company');

    if (code) {
        validateAndStartChat(code);
    } else {
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
            code.textContent = c.address || '';

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
                    window.location.href = `/?company=${c.company_id}`;
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
        currentCompanyId = company.company_id;
        currentCompanyCode = code;

        // Show company name in header
        companyLabel.textContent = company.company_name;
        companyLabel.style.display = '';

        // Show chat (로그인 없이 누구나 이용 가능)
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

    // Track last question for feedback
    let lastQuestion = null;

    async function sendMessage(text) {
        appendMessage('user', text);
        chatInput.value = '';
        chatInput.disabled = true;
        sendBtn.disabled = true;
        lastQuestion = text;

        // Hide quick questions after first message
        if (quickQuestions) quickQuestions.style.display = 'none';

        typingIndicator.classList.add('show');
        scrollToBottom();

        try {
            const body = {
                question: text,
                session_id: sessionId,
                category: selectedCategory === '전체' ? null : selectedCategory,
            };
            if (currentCompanyId) {
                body.company_id = currentCompanyId;
            }

            const result = await apiPost('/chat', body);
            typingIndicator.classList.remove('show');

            // Store quota if provided
            if (result.quota_remaining !== undefined) {
                quotaRemaining = result.quota_remaining;
            }

            // Render bot answer with RAG data
            appendBotMessage(result, text);
        } catch (err) {
            typingIndicator.classList.remove('show');

            if (err instanceof ApiError) {
                if (err.status === 429) {
                    appendSystemMessage(
                        '이번 달 질문 횟수를 모두 사용했습니다.',
                        { label: '요금제 업그레이드', href: '/billing.html' }
                    );
                } else if (err.status === 403) {
                    var detail = (err.data && err.data.reason) || '';
                    if (detail === 'trial_expired') {
                        appendSystemMessage(
                            '무료체험이 종료되었습니다.',
                            { label: '요금제 확인', href: '/billing.html' }
                        );
                    } else {
                        appendSystemMessage(
                            '서비스가 일시 정지되었습니다. 관리자에게 문의해 주세요.'
                        );
                    }
                } else if (err.status >= 500) {
                    appendSystemMessage(
                        '일시적 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.',
                        null,
                        function () { sendMessage(text); }
                    );
                } else {
                    appendMessage('bot', '죄송합니다. 오류가 발생했습니다: ' + err.message);
                }
            } else {
                appendSystemMessage(
                    '일시적 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.',
                    null,
                    function () { sendMessage(text); }
                );
            }
        }

        chatInput.disabled = false;
        sendBtn.disabled = false;
        chatInput.focus();
    }

    /* ── Render bot message with RAG response ── */
    function appendBotMessage(result, question) {
        var msg = document.createElement('div');
        msg.className = 'message bot';
        msg.setAttribute('role', 'article');

        var avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.setAttribute('aria-hidden', 'true');
        avatar.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';

        var bubble = document.createElement('div');
        bubble.className = 'message-bubble';

        // Category badge (from legacy format or evidences)
        if (result.category) {
            var catBadge = document.createElement('div');
            catBadge.className = 'message-category';
            catBadge.textContent = result.category;
            bubble.appendChild(catBadge);
        }

        // RAG warning: used_rag === false
        if (result.used_rag === false) {
            var warning = document.createElement('div');
            warning.className = 'rag-warning';
            warning.textContent = '\u26A0 등록된 근거 없이 생성된 답변입니다. 확인이 필요합니다.';
            bubble.appendChild(warning);
        }

        // Markdown-rendered answer
        var answerDiv = document.createElement('div');
        answerDiv.className = 'message-answer';
        if (typeof marked !== 'undefined' && marked.parse) {
            answerDiv.innerHTML = marked.parse(result.answer || '');
        } else {
            answerDiv.textContent = result.answer || '';
        }
        bubble.appendChild(answerDiv);

        // Evidence section (if evidences exist in response)
        if (result.evidences && result.evidences.length > 0) {
            bubble.appendChild(buildEvidenceSection(result.evidences));
        } else if (result.evidences && result.evidences.length === 0) {
            var noEvidence = document.createElement('div');
            noEvidence.className = 'evidence-empty';
            noEvidence.textContent = '등록된 정보에서 답변을 찾지 못했습니다. 관리실에 문의해 주세요.';
            bubble.appendChild(noEvidence);
        }

        // Feedback buttons
        var qaIds = [];
        if (result.evidences) {
            result.evidences.forEach(function (e) {
                if (e.qa_id) qaIds.push(e.qa_id);
            });
        }
        bubble.appendChild(buildFeedbackButtons(question, result.answer, qaIds));

        msg.appendChild(avatar);
        msg.appendChild(bubble);
        chatMessages.appendChild(msg);
        scrollToBottom();
    }

    /* ── Build evidence collapse section ── */
    function buildEvidenceSection(evidences) {
        var section = document.createElement('div');
        section.className = 'evidence-section';

        var toggle = document.createElement('button');
        toggle.className = 'evidence-toggle';
        toggle.type = 'button';
        toggle.innerHTML = '\uD83D\uDCCB 참고한 답변 (' + evidences.length + '건) \u25BC';

        var list = document.createElement('div');
        list.className = 'evidence-list';
        list.style.display = 'none';

        evidences.forEach(function (ev) {
            var item = document.createElement('div');
            item.className = 'evidence-item';

            if (ev.category) {
                var badge = document.createElement('span');
                badge.className = 'badge-category';
                badge.textContent = ev.category;
                item.appendChild(badge);
            }

            if (ev.question) {
                var q = document.createElement('strong');
                q.textContent = ev.question;
                item.appendChild(q);
            }

            if (ev.answer) {
                var a = document.createElement('p');
                // Show first 200 chars as summary
                a.textContent = ev.answer.length > 200 ? ev.answer.substring(0, 200) + '...' : ev.answer;
                item.appendChild(a);
            }

            list.appendChild(item);
        });

        toggle.addEventListener('click', function () {
            var isHidden = list.style.display === 'none';
            list.style.display = isHidden ? '' : 'none';
            toggle.innerHTML = '\uD83D\uDCCB 참고한 답변 (' + evidences.length + '건) ' + (isHidden ? '\u25B2' : '\u25BC');
        });

        section.appendChild(toggle);
        section.appendChild(list);
        return section;
    }

    /* ── Build feedback buttons ── */
    function buildFeedbackButtons(question, answer, qaIds) {
        var wrapper = document.createElement('div');
        wrapper.className = 'feedback-buttons';

        var likeBtn = document.createElement('button');
        likeBtn.className = 'feedback-btn';
        likeBtn.type = 'button';
        likeBtn.setAttribute('data-rating', 'like');
        likeBtn.textContent = '\uD83D\uDC4D';

        var dislikeBtn = document.createElement('button');
        dislikeBtn.className = 'feedback-btn';
        dislikeBtn.type = 'button';
        dislikeBtn.setAttribute('data-rating', 'dislike');
        dislikeBtn.textContent = '\uD83D\uDC4E';

        function handleFeedback(rating) {
            likeBtn.disabled = true;
            dislikeBtn.disabled = true;

            if (rating === 'like') {
                likeBtn.classList.add('selected');
            } else {
                dislikeBtn.classList.add('selected');
            }

            apiPost('/feedback', {
                question: question,
                answer: answer,
                qa_ids: qaIds,
                rating: rating,
            }).then(function () {
                showToast('피드백 감사합니다');
            }).catch(function () {
                showToast('피드백 전송에 실패했습니다');
                likeBtn.disabled = false;
                dislikeBtn.disabled = false;
                likeBtn.classList.remove('selected');
                dislikeBtn.classList.remove('selected');
            });
        }

        likeBtn.addEventListener('click', function () { handleFeedback('like'); });
        dislikeBtn.addEventListener('click', function () { handleFeedback('dislike'); });

        wrapper.appendChild(likeBtn);
        wrapper.appendChild(dislikeBtn);
        return wrapper;
    }

    /* ── System message (errors, quota, etc.) ── */
    function appendSystemMessage(text, cta, retryFn) {
        var msg = document.createElement('div');
        msg.className = 'message system';
        msg.setAttribute('role', 'alert');

        var bubble = document.createElement('div');
        bubble.className = 'system-message';

        var textEl = document.createElement('p');
        textEl.textContent = text;
        bubble.appendChild(textEl);

        if (cta) {
            var ctaBtn = document.createElement('a');
            ctaBtn.className = 'btn btn-primary btn-sm';
            ctaBtn.href = cta.href;
            ctaBtn.textContent = cta.label;
            bubble.appendChild(ctaBtn);
        }

        if (retryFn) {
            var retryBtn = document.createElement('button');
            retryBtn.className = 'btn btn-outline btn-sm';
            retryBtn.type = 'button';
            retryBtn.textContent = '다시 시도';
            retryBtn.addEventListener('click', function () {
                msg.remove();
                retryFn();
            });
            bubble.appendChild(retryBtn);
        }

        msg.appendChild(bubble);
        chatMessages.appendChild(msg);
        scrollToBottom();
    }

    /* ── Plain text message (user / simple bot) ── */
    function appendMessage(type, text, category) {
        var msg = document.createElement('div');
        msg.className = 'message ' + type;
        msg.setAttribute('role', 'article');

        var avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.setAttribute('aria-hidden', 'true');

        if (type === 'bot') {
            avatar.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
        } else {
            avatar.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>';
        }

        var bubble = document.createElement('div');
        bubble.className = 'message-bubble';

        if (type === 'bot' && category) {
            var catBadge = document.createElement('div');
            catBadge.className = 'message-category';
            catBadge.textContent = category;
            bubble.appendChild(catBadge);
        }

        var textNode = document.createElement('div');
        if (type === 'bot' && typeof marked !== 'undefined' && marked.parse) {
            textNode.innerHTML = marked.parse(text);
        } else {
            textNode.textContent = text;
        }
        bubble.appendChild(textNode);

        msg.appendChild(avatar);
        msg.appendChild(bubble);
        chatMessages.appendChild(msg);

        scrollToBottom();
    }

    function scrollToBottom() {
        setTimeout(function () {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }, 50);
    }

    // Load chat history
    async function loadHistory() {
        try {
            var url = `/chat/history/${sessionId}`;
            if (currentCompanyId) {
                url += `?company_id=${currentCompanyId}`;
            }
            var history = await apiGet(url);
            history.forEach(function (item) {
                appendMessage('user', item.user_question);
                if (item.evidences !== undefined) {
                    appendBotMessage({
                        answer: item.bot_answer,
                        category: item.category,
                        evidences: item.evidences || [],
                        used_rag: item.used_rag,
                    }, item.user_question);
                } else {
                    appendMessage('bot', item.bot_answer, item.category);
                }
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
            var auth = await apiGet('/auth/check');
            if (auth.authenticated && auth.session) {
                var label = auth.session.full_name || auth.session.username || '';
                document.getElementById('adminLink').textContent = '관리자 (' + label + ')';
                var billingLink = document.getElementById('billingLink');
                if (billingLink) billingLink.style.display = '';
                if (auth.session.role === 'super_admin') {
                    var saLink = document.getElementById('superAdminLink');
                    if (saLink) saLink.style.display = '';
                }
            }
        } catch (e) { /* not logged in */ }
    }

    if (AuthSession.isValid()) {
        loadHistory();
    }
    checkAdmin();
    chatInput.focus();
}
