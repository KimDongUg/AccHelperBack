const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const sendBtn = document.getElementById('sendBtn');
const typingIndicator = document.getElementById('typingIndicator');
const quickQuestions = document.getElementById('quickQuestions');

let sessionId = sessionStorage.getItem('chatSessionId');
if (!sessionId) {
    sessionId = generateSessionId();
    sessionStorage.setItem('chatSessionId', sessionId);
}

let selectedCategory = '전체';

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
    // Add user message
    appendMessage('user', text);
    chatInput.value = '';
    chatInput.disabled = true;
    sendBtn.disabled = true;

    // Show typing
    typingIndicator.classList.add('show');
    scrollToBottom();

    try {
        const result = await apiPost('/chat', {
            question: text,
            session_id: sessionId,
            category: selectedCategory === '전체' ? null : selectedCategory,
        });

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

// Load chat history on page load
async function loadHistory() {
    try {
        const history = await apiGet(`/chat/history/${sessionId}`);
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

// Check admin status for link
async function checkAdmin() {
    try {
        const auth = await apiGet('/auth/check');
        if (auth.authenticated) {
            document.getElementById('adminLink').textContent = `관리자 (${auth.username})`;
        }
    } catch (e) { /* not logged in */ }
}

document.addEventListener('DOMContentLoaded', () => {
    loadHistory();
    checkAdmin();
    chatInput.focus();
});
