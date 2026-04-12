// View Switching
function switchTab(viewName) {
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    
    document.getElementById(`tab-${viewName}-btn`).classList.add('active');
    document.getElementById(`view-${viewName}`).classList.add('active');
}

// Variables for aborting fetches
let planAbortController = null;
let chatAbortController = null;

let chatHistory = [];
let plannerCurrentPlan = "";
let chatCurrentPlan = "";

// Initialize
async function init() {
    // Fetch models and populate dropdowns
    try {
        const res = await fetch('/api/models');
        const data = await res.json();
        const models = data.models || [];
        
        const plannerSelect = document.getElementById('planner-model');
        const chatSelect = document.getElementById('chat-model');
        
        models.forEach(m => {
            const opt1 = document.createElement('option');
            opt1.value = m; opt1.textContent = m;
            plannerSelect.appendChild(opt1);
            
            const opt2 = document.createElement('option');
            opt2.value = m; opt2.textContent = m;
            chatSelect.appendChild(opt2);
        });
    } catch(err) {
        console.error("Failed to load models", err);
    }
}

// --- Planner Logic ---
async function generatePlan() {
    const goalInput = document.getElementById('planner-goal');
    const goal = goalInput.value.trim();
    if(!goal) return;

    const modelChoice = document.getElementById('planner-model').value;
    const btnGenerate = document.getElementById('btn-generate-plan');
    const btnStop = document.getElementById('btn-stop-plan');
    const btnDownload = document.getElementById('btn-download-plan');
    const outputDiv = document.getElementById('plan-output');
    
    // UI Reset
    btnGenerate.disabled = true;
    btnStop.disabled = false;
    btnDownload.style.display = 'none';
    outputDiv.innerHTML = `<em>⏳ Waiting in queue...</em><span class="cursor"></span>`;
    
    document.getElementById('info-task').innerText = "Waiting...";
    document.getElementById('info-model').innerText = "Waiting...";
    document.getElementById('info-search').innerText = "Waiting...";

    plannerCurrentPlan = "";
    planAbortController = new AbortController();

    try {
        const response = await fetch('/api/plan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ goal, model_choice: modelChoice }),
            signal: planAbortController.signal
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            
            // Process SSE
            const lines = buffer.split("\n\n");
            buffer = lines.pop(); // Keep the incomplete part

            for (const chunk of lines) {
                if (!chunk.trim()) continue;
                
                const [eventLine, dataLine] = chunk.split("\n");
                const event = eventLine.replace("event: ", "").trim();
                let data = {};
                try {
                    data = JSON.parse(dataLine.replace("data: ", ""));
                } catch(e) {}

                if (event === "metadata") {
                    document.getElementById('info-task').innerText = data.badge;
                    document.getElementById('info-model').innerText = data.model;
                    document.getElementById('info-search').innerText = data.search;
                } else if (event === "update") {
                    plannerCurrentPlan = data.content || "";
                    outputDiv.innerHTML = marked.parse(plannerCurrentPlan) + '<span class="cursor"></span>';
                } else if (event === "error") {
                    outputDiv.innerHTML = marked.parse(data.content);
                } else if (event === "done") {
                    break;
                }
            }
        }
        
        // Remove cursor
        outputDiv.innerHTML = marked.parse(plannerCurrentPlan);
        btnDownload.style.display = 'inline-block';
    } catch(err) {
        if(err.name === 'AbortError') {
            outputDiv.innerHTML += "\n<br><em>⏹ Stopped by user</em>";
        } else {
            console.error(err);
            outputDiv.innerHTML = `<em>❌ Error: ${err.message}</em>`;
        }
    } finally {
        btnGenerate.disabled = false;
        btnStop.disabled = true;
    }
}

function stopPlan() {
    if(planAbortController) planAbortController.abort();
}

async function downloadPlan() {
    await triggerDownload(plannerCurrentPlan);
}

// --- Chat Logic ---
function appendMessage(role, content) {
    const chatHist = document.getElementById('chat-history');
    const msgDiv = document.createElement('div');
    msgDiv.className = `msg ${role}`;
    msgDiv.innerHTML = marked.parse(content);
    chatHist.appendChild(msgDiv);
    chatHist.scrollTop = chatHist.scrollHeight;
    return msgDiv;
}

async function sendChat() {
    const inputEl = document.getElementById('chat-input');
    const text = inputEl.value.trim();
    if(!text) return;

    const modelChoice = document.getElementById('chat-model').value;
    inputEl.value = "";
    
    appendMessage('user', text);
    
    const btnSend = document.getElementById('btn-send-chat');
    const btnPlan = document.getElementById('btn-plan-chat');
    const btnStop = document.getElementById('btn-stop-chat');
    
    btnSend.disabled = true;
    btnPlan.disabled = true;
    btnStop.disabled = false;

    chatAbortController = new AbortController();
    
    const assistantMsgDiv = appendMessage('assistant', `<em>⏳ Waiting in queue...</em><span class="cursor"></span>`);
    let currentResponse = "";

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, history: chatHistory, model_choice: modelChoice }),
            signal: chatAbortController.signal
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            
            const lines = buffer.split("\n\n");
            buffer = lines.pop();

            for (const chunk of lines) {
                if (!chunk.trim()) continue;
                
                const [eventLine, dataLine] = chunk.split("\n");
                const event = eventLine.replace("event: ", "").trim();
                let data = {};
                try { data = JSON.parse(dataLine.replace("data: ", "")); } catch(e) {}

                if (event === "metadata") {
                    assistantMsgDiv.innerHTML = `<span class="msg-meta">🤖 ${data.model}</span><div class="msg-content"></div><span class="cursor"></span>`;
                } else if (event === "message") {
                    currentResponse += data.content || "";
                    const contentDiv = assistantMsgDiv.querySelector('.msg-content');
                    if (contentDiv) {
                        contentDiv.innerHTML = marked.parse(currentResponse);
                    } else {
                        assistantMsgDiv.innerHTML = marked.parse(currentResponse) + '<span class="cursor"></span>';
                    }
                    document.getElementById('chat-history').scrollTop = document.getElementById('chat-history').scrollHeight;
                } else if (event === "error") {
                    currentResponse += "\n\n" + data.content;
                    assistantMsgDiv.innerHTML = marked.parse(currentResponse);
                } else if (event === "done") {
                    break;
                }
            }
        }
        
        // Finalize
        const contentDiv = assistantMsgDiv.querySelector('.msg-content');
        if (contentDiv) {
            contentDiv.innerHTML = marked.parse(currentResponse);
        } else {
            assistantMsgDiv.innerHTML = marked.parse(currentResponse);
        }
        chatHistory.push({ role: "user", content: text });
        chatHistory.push({ role: "assistant", content: currentResponse });
        
    } catch(err) {
        if(err.name === 'AbortError') {
            assistantMsgDiv.innerHTML += "\n<br><em>⏹ Stopped</em>";
        } else {
            assistantMsgDiv.innerHTML = `<em>❌ Error: ${err.message}</em>`;
        }
    } finally {
        btnSend.disabled = false;
        btnPlan.disabled = false;
        btnStop.disabled = true;
    }
}

async function generateChatPlan() {
    const inputEl = document.getElementById('chat-input');
    const goal = inputEl.value.trim();
    if(!goal) return;

    const modelChoice = document.getElementById('chat-model').value;
    inputEl.value = "";
    
    appendMessage('user', `📋 *Plan request:* ${goal}`);
    const systemMsgDiv = appendMessage('system', '⏳ <em>Waiting in queue...</em>');
    
    const panelDiv = document.getElementById('chat-plan-output');
    panelDiv.innerHTML = `<em>Waiting in queue...</em><span class="cursor"></span>`;
    document.getElementById('btn-download-chat-plan').style.display = 'none';

    chatCurrentPlan = "";
    
    // Using same plan backend
    const btnSend = document.getElementById('btn-send-chat');
    const btnPlan = document.getElementById('btn-plan-chat');
    const btnStop = document.getElementById('btn-stop-chat');
    
    btnSend.disabled = true;
    btnPlan.disabled = true;
    btnStop.disabled = false;

    chatAbortController = new AbortController();

    try {
        const response = await fetch('/api/plan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ goal, model_choice: modelChoice }),
            signal: chatAbortController.signal
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n\n");
            buffer = lines.pop();

            for (const chunk of lines) {
                if (!chunk.trim()) continue;
                const [eventLine, dataLine] = chunk.split("\n");
                const event = eventLine.replace("event: ", "").trim();
                let data = {};
                try { data = JSON.parse(dataLine.replace("data: ", "")); } catch(e) {}

                if (event === "update") {
                    chatCurrentPlan = data.content || "";
                    panelDiv.innerHTML = marked.parse(chatCurrentPlan) + '<span class="cursor"></span>';
                }
            }
        }
        
        panelDiv.innerHTML = marked.parse(chatCurrentPlan);
        document.getElementById('btn-download-chat-plan').style.display = 'inline-block';
        
        systemMsgDiv.innerHTML = `✅ <strong>Plan generated!</strong> See the 📋 Plan Panel on the right → <br><em>Goal: ${goal}</em>`;
        chatHistory.push({ role: "user", content: `📋 *Plan request:* ${goal}` });
        chatHistory.push({ role: "assistant", content: `✅ **Plan generated!** See the **📋 Plan Panel** on the right →\n\n> *Goal: ${goal}*` });
    } catch(err) {
        if(err.name === 'AbortError') {
             systemMsgDiv.innerHTML = "⏹ Stopped by user";
             panelDiv.innerHTML = "<em>⏹ Stopped by user</em>";
        } else {
             systemMsgDiv.innerHTML = `❌ Failed: ${err.message}`;
        }
    } finally {
        btnSend.disabled = false;
        btnPlan.disabled = false;
        btnStop.disabled = true;
    }
}

function stopChat() {
    if(chatAbortController) chatAbortController.abort();
}

function clearChat() {
    document.getElementById('chat-history').innerHTML = "";
    document.getElementById('chat-plan-output').innerHTML = "<em>No plan yet. Type a goal and click <strong>📋 Plan This</strong>.</em>";
    document.getElementById('btn-download-chat-plan').style.display = "none";
    chatHistory = [];
    chatCurrentPlan = "";
}

async function downloadChatPlan() {
    await triggerDownload(chatCurrentPlan);
}

// Global download helper hitting the post route
async function triggerDownload(content) {
    if(!content) return;
    
    // We can do a POST form submission to trigger a real file download in the browser natively
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = '/api/download';
    form.target = '_blank'; // Optional

    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'plan_text'; // the backend expects JSON body, but we need HTML form urlencoded if we submit conventionally.
    // Wait, typical download is easier with a blob
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "ai_plan.md";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Enter-to-send bindings
document.getElementById('chat-input').addEventListener('keypress', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChat();
    }
});

// Run Init
window.onload = init;
