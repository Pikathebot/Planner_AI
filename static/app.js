/* ═══════════════════════════════════════════════════════════
   PLANNER AGENT — MODERN AI CHAT LOGIC
   ═══════════════════════════════════════════════════════════ */

// ─── State ───────────────────────────────────────────────────
let chatHistory = [];
let chatCurrentPlan = "";
let chatAbortController = null;
let currentMode = "chat"; // "chat" or "plan"
let currentSessionId = null;
let welcomeVisible = true;

// ─── Init ────────────────────────────────────────────────────
async function init() {
    await loadModels();
    renderSessionList();
    setupAutoResize();
    updateChipInfo();
    setMode('chat');
    document.getElementById('chat-search').addEventListener('change', updateChipInfo);
    document.getElementById('chat-model').addEventListener('change', updateChipInfo);
}

async function loadModels() {
    try {
        const res = await fetch('/api/models');
        const data = await res.json();
        const models = data.models || [];
        const select = document.getElementById('chat-model');
        models.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m; opt.textContent = m;
            select.appendChild(opt);
        });
        updateChipInfo();
    } catch(err) {
        console.error("Failed to load models", err);
    }
}

function updateChipInfo() {
    const model = document.getElementById('chat-model').value || '—';
    const search = document.getElementById('chat-search').value;
    const searchLabel = { auto: 'Auto', on: 'ON', off: 'OFF' }[search] || 'Auto';
    const shortModel = model.split(':')[0];
    document.getElementById('chip-model-info').textContent = `Model: ${shortModel}`;
    document.getElementById('chip-search-info').textContent = `Search: ${searchLabel}`;
}

// ─── Auto-resize textarea (like all modern AI chats) ─────────
function setupAutoResize() {
    const ta = document.getElementById('chat-input');
    ta.addEventListener('input', () => {
        ta.style.height = 'auto';
        ta.style.height = Math.min(ta.scrollHeight, 200) + 'px';
    });
    ta.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendMessage();
        }
    });
}

function handleSendMessage() {
    if (currentMode === 'plan') {
        generateChatPlan();
    } else {
        sendChat();
    }
}

// ─── Mode ────────────────────────────────────────────────────
function setMode(mode) {
    currentMode = mode;
    document.getElementById('mode-chat-btn').classList.toggle('active', mode === 'chat');
    document.getElementById('mode-plan-btn').classList.toggle('active', mode === 'plan');
    document.getElementById('chip-plan').classList.toggle('active', mode === 'plan');
    const ta = document.getElementById('chat-input');
    ta.placeholder = mode === 'plan'
        ? 'Type your goal and press Enter to generate a plan…'
        : 'Message Planner Agent…';
}

function triggerPlanMode() {
    const val = document.getElementById('chat-input').value.trim();
    if (val) {
        generateChatPlan();
    } else {
        setMode(currentMode === 'plan' ? 'chat' : 'plan');
    }
}

// ─── Welcome Screen ──────────────────────────────────────────
function hideWelcome() {
    if (!welcomeVisible) return;
    welcomeVisible = false;
    const ws = document.getElementById('welcome-screen');
    const ca = document.getElementById('chat-history');
    ws.classList.add('hidden');
    ca.classList.add('visible');
}

function showWelcome() {
    welcomeVisible = true;
    const ws = document.getElementById('welcome-screen');
    const ca = document.getElementById('chat-history');
    ws.classList.remove('hidden');
    ca.classList.remove('visible');
}

function usePrompt(text) {
    document.getElementById('chat-input').value = text;
    setupAutoResize();
    const ta = document.getElementById('chat-input');
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 200) + 'px';
    ta.focus();
}

// ─── New Chat ────────────────────────────────────────────────
function newChat() {
    // Save current session before clearing
    if (chatHistory.length > 0) saveSession();

    // Reset state
    chatHistory = [];
    chatCurrentPlan = "";
    currentSessionId = crypto.randomUUID();

    // Reset UI
    document.getElementById('chat-history').innerHTML = '';
    showWelcome();

    // Reset plan panel
    document.getElementById('chat-plan-output').innerHTML = `
        <div class="plan-placeholder">
            <span class="plan-placeholder-icon">📋</span>
            <p>Type a goal in chat and press<br><strong>📋 Plan This</strong> to get started.</p>
        </div>`;
    document.getElementById('plan-download-row').style.display = 'none';
    document.getElementById('info-task').textContent = '🧠 —';
    document.getElementById('info-model').textContent = '🤖 —';
    document.getElementById('info-search').textContent = '🔍 —';

    setMode('chat');
    if (window.innerWidth <= 900) closeSidebar();
    document.getElementById('chat-input').focus();
}

// ─── Sidebar Controls ────────────────────────────────────────
function openSidebar() {
    document.getElementById('sidebar').classList.add('open');
    const overlay = document.getElementById('sidebar-overlay');
    overlay.style.display = 'block';
    setTimeout(() => overlay.classList.add('active'), 10);
}

function closeSidebar() {
    document.getElementById('sidebar').classList.remove('open');
    const overlay = document.getElementById('sidebar-overlay');
    overlay.classList.remove('active');
    setTimeout(() => { overlay.style.display = 'none'; }, 250);
}

// ─── Plan Panel ──────────────────────────────────────────────
function togglePlanPanel() {
    document.querySelector('.app-shell').classList.toggle('plan-open');
}

function openPlanPanel() {
    document.querySelector('.app-shell').classList.add('plan-open');
}

// ─── Session History (localStorage) ─────────────────────────
const SESSIONS_KEY = 'planner_sessions';

function saveSession() {
    if (chatHistory.length === 0) return;
    const sessions = getSessions();
    const id = currentSessionId || crypto.randomUUID();
    currentSessionId = id;
    const firstUser = chatHistory.find(m => m.role === 'user');
    const title = firstUser ? firstUser.content.slice(0, 50) : 'Session';
    const idx = sessions.findIndex(s => s.id === id);
    const entry = { id, title, ts: Date.now(), history: chatHistory, plan: chatCurrentPlan };
    if (idx >= 0) sessions[idx] = entry;
    else sessions.unshift(entry);
    // Keep 20 sessions max
    if (sessions.length > 20) sessions.pop();
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions));
    renderSessionList();
}

function getSessions() {
    try { return JSON.parse(localStorage.getItem(SESSIONS_KEY) || '[]'); }
    catch { return []; }
}

function renderSessionList() {
    const sessions = getSessions();
    const container = document.getElementById('session-list');
    if (sessions.length === 0) {
        container.innerHTML = '<div class="session-empty">No recent sessions</div>';
        return;
    }
    container.innerHTML = sessions.map(s => `
        <div class="session-item-wrapper ${s.id === currentSessionId ? 'active' : ''}">
            <button class="session-item" onclick="loadSession('${s.id}')" title="${escapeHtml(s.title)}">
                ${escapeHtml(s.title)}
            </button>
            <button class="session-delete-btn" onclick="deleteSession(event, '${s.id}')" title="Delete session">✕</button>
        </div>
    `).join('');
}

function deleteSession(event, id) {
    if (event) event.stopPropagation();
    if (!confirm('Are you sure you want to delete this session?')) return;
    
    const sessions = getSessions();
    const newSessions = sessions.filter(s => s.id !== id);
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(newSessions));
    
    if (currentSessionId === id) {
        newChat();
    } else {
        renderSessionList();
    }
}

function loadSession(id) {
    const sessions = getSessions();
    const session = sessions.find(s => s.id === id);
    if (!session) return;

    // Save current session first
    if (chatHistory.length > 0) saveSession();

    // Load session
    currentSessionId = id;
    chatHistory = session.history || [];
    chatCurrentPlan = session.plan || '';

    // Rebuild chat UI
    const chatHist = document.getElementById('chat-history');
    chatHist.innerHTML = '';
    chatHistory.forEach(m => {
        if (m.role === 'user') _renderUserMsg(m.content);
        else if (m.role === 'assistant') _renderAssistantMsg(m.content);
    });
    hideWelcome();
    chatHist.scrollTop = chatHist.scrollHeight;

    // Restore plan if any
    if (chatCurrentPlan) {
        document.getElementById('chat-plan-output').innerHTML = marked.parse(chatCurrentPlan);
        document.getElementById('plan-download-row').style.display = 'flex';
        openPlanPanel();
    }

    renderSessionList();
    if (window.innerWidth <= 900) closeSidebar();
}

function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// ─── Message Rendering Helpers ───────────────────────────────
function _renderUserMsg(text) {
    const chatHist = document.getElementById('chat-history');
    const el = document.createElement('div');
    el.className = 'msg user';
    el.innerHTML = `<div class="msg-inner"><div class="msg-bubble">${escapeHtml(text)}</div></div>`;
    chatHist.appendChild(el);
    chatHist.scrollTop = chatHist.scrollHeight;
    return el;
}

function _renderAssistantMsg(content, withCursor = false) {
    const chatHist = document.getElementById('chat-history');
    const el = document.createElement('div');
    el.className = 'msg assistant';
    el.innerHTML = `
        <div class="msg-inner">
            <div class="msg-avatar">PA</div>
            <div class="msg-body">
                <div class="msg-meta-label">Planner Agent</div>
                <div class="msg-content">${marked.parse(content)}</div>
                ${withCursor ? '<span class="cursor"></span>' : ''}
            </div>
        </div>`;
    chatHist.appendChild(el);
    chatHist.scrollTop = chatHist.scrollHeight;
    return el;
}

function _renderSystemMsg(html) {
    const chatHist = document.getElementById('chat-history');
    const el = document.createElement('div');
    el.className = 'msg system';
    el.innerHTML = `<div class="msg-inner"><div class="msg-body">${html}</div></div>`;
    chatHist.appendChild(el);
    chatHist.scrollTop = chatHist.scrollHeight;
    return el;
}

// ─── Chat ────────────────────────────────────────────────────
async function sendChat() {
    const inputEl = document.getElementById('chat-input');
    const text = inputEl.value.trim();
    if (!text) return;

    const modelChoice = document.getElementById('chat-model').value;
    inputEl.value = '';
    inputEl.style.height = 'auto';

    hideWelcome();
    _renderUserMsg(text);

    const btnSend = document.getElementById('btn-send-chat');
    const btnStop = document.getElementById('btn-stop-chat');
    btnSend.disabled = true;
    btnStop.classList.remove('hidden');

    chatAbortController = new AbortController();

    const assistantEl = _renderAssistantMsg('', true);
    const contentDiv = assistantEl.querySelector('.msg-content');
    let currentResponse = '';

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: text,
                history: chatHistory,
                model_choice: modelChoice,
                use_search: document.getElementById('chat-search').value,
                current_plan: chatCurrentPlan
            }),
            signal: chatAbortController.signal
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split('\n\n');
            buffer = parts.pop();

            for (const chunk of parts) {
                if (!chunk.trim()) continue;
                const [eventLine, dataLine] = chunk.split('\n');
                const event = eventLine.replace('event: ', '').trim();
                let data = {};
                try { data = JSON.parse(dataLine.replace('data: ', '')); } catch(e) {}

                if (event === 'metadata') {
                    const metaEl = assistantEl.querySelector('.msg-meta-label');
                    if (data.model && metaEl) {
                        metaEl.textContent = `🤖 ${data.model}`;
                    }
                    if (data.status) {
                        contentDiv.innerHTML = `<span style="color: var(--text-muted); font-style: italic;">${data.status}</span>`;
                    }
                } else if (event === 'message') {
                    currentResponse += data.content || '';
                    contentDiv.innerHTML = marked.parse(currentResponse);
                    document.getElementById('chat-history').scrollTop = 9999;
                } else if (event === 'error') {
                    currentResponse += '\n\n' + data.content;
                    contentDiv.innerHTML = marked.parse(currentResponse);
                }
            }
        }
    } catch(err) {
        if (err.name !== 'AbortError') {
            contentDiv.innerHTML = `<em>❌ Error: ${err.message}</em>`;
        }
    } finally {
        // Remove cursor
        const cursor = assistantEl.querySelector('.cursor');
        if (cursor) cursor.remove();
        contentDiv.innerHTML = marked.parse(currentResponse);

        btnSend.disabled = false;
        btnStop.classList.add('hidden');

        chatHistory.push({ role: 'user', content: text });
        chatHistory.push({ role: 'assistant', content: currentResponse });
        saveSession();
    }
}

// ─── Plan Generation ─────────────────────────────────────────
async function generateChatPlan() {
    const inputEl = document.getElementById('chat-input');
    const goal = inputEl.value.trim();
    if (!goal) return;

    const modelChoice = document.getElementById('chat-model').value;
    const searchChoice = document.getElementById('chat-search').value;
    inputEl.value = '';
    inputEl.style.height = 'auto';

    hideWelcome();
    _renderUserMsg(`📋 Plan: ${goal}`);
    const systemEl = _renderSystemMsg('⏳ <em>Generating plan…</em>');

    // Open plan panel
    openPlanPanel();
    const panelDiv = document.getElementById('chat-plan-output');
    panelDiv.innerHTML = `<em style="color:var(--text-muted)">⏳ Generating plan…</em><span class="cursor"></span>`;
    document.getElementById('plan-download-row').style.display = 'none';

    // Reset badges
    document.getElementById('info-task').textContent = '🧠 …';
    document.getElementById('info-model').textContent = '🤖 …';
    document.getElementById('info-search').textContent = '🔍 …';

    chatCurrentPlan = '';

    const btnSend = document.getElementById('btn-send-chat');
    const btnStop = document.getElementById('btn-stop-chat');
    btnSend.disabled = true;
    btnStop.classList.remove('hidden');

    chatAbortController = new AbortController();
    const chatContextText = chatHistory
        .map(m => `${m.role === 'user' ? 'User' : 'Assistant'}: ${m.content}`)
        .join('\n');

    try {
        const response = await fetch('/api/plan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                goal,
                model_choice: modelChoice,
                use_search: searchChoice,
                chat_context: chatContextText
            }),
            signal: chatAbortController.signal
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split('\n\n');
            buffer = parts.pop();

            for (const chunk of parts) {
                if (!chunk.trim()) continue;
                const [eventLine, dataLine] = chunk.split('\n');
                const event = eventLine.replace('event: ', '').trim();
                let data = {};
                try { data = JSON.parse(dataLine.replace('data: ', '')); } catch(e) {}

                if (event === 'metadata') {
                    document.getElementById('info-task').textContent = data.badge;
                    document.getElementById('info-model').textContent = data.model;
                    document.getElementById('info-search').textContent = data.search;
                } else if (event === 'update') {
                    chatCurrentPlan = data.content || '';
                    panelDiv.innerHTML = marked.parse(chatCurrentPlan) + '<span class="cursor"></span>';
                }
            }
        }

        // Finalize plan
        const cursor = panelDiv.querySelector('.cursor');
        if (cursor) cursor.remove();
        panelDiv.innerHTML = marked.parse(chatCurrentPlan);
        document.getElementById('plan-download-row').style.display = 'flex';

        systemEl.querySelector('.msg-body').innerHTML =
            `✅ <strong>Plan ready!</strong> <em>${goal}</em>`;

        chatHistory.push({ role: 'user', content: `📋 Plan: ${goal}` });
        chatHistory.push({ role: 'assistant', content: `✅ **Plan generated!**\n\n> *Goal: ${goal}*` });
        saveSession();

    } catch(err) {
        if (err.name === 'AbortError') {
            systemEl.querySelector('.msg-body').textContent = '⏹ Stopped';
            panelDiv.innerHTML = '<em style="color:var(--text-muted)">⏹ Stopped</em>';
        } else {
            systemEl.querySelector('.msg-body').innerHTML = `❌ ${err.message}`;
        }
    } finally {
        const cursor = panelDiv.querySelector('.cursor');
        if (cursor) cursor.remove();
        btnSend.disabled = false;
        btnStop.classList.add('hidden');
        setMode('chat');
    }
}

function stopChat() {
    if (chatAbortController) chatAbortController.abort();
}

// ─── Downloads ───────────────────────────────────────────────
async function downloadChatPlan() {
    if (!chatCurrentPlan) return;
    const blob = new Blob([chatCurrentPlan], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'ai_plan.md';
    document.body.appendChild(a); a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

async function downloadChatPlanPDF() {
    if (!chatCurrentPlan) return;
    const element = document.createElement('div');
    element.className = 'pdf-export';
    element.innerHTML = marked.parse(chatCurrentPlan);
    const opt = {
        margin: 0.75,
        filename: 'ai_plan.pdf',
        image: { type: 'jpeg', quality: 0.98 },
        html2canvas: { scale: 2 },
        jsPDF: { unit: 'in', format: 'letter', orientation: 'portrait' },
        pagebreak: { mode: 'avoid-all' }
    };
    html2pdf().set(opt).from(element).save();
}

// ─── Boot ─────────────────────────────────────────────────────
window.onload = init;
