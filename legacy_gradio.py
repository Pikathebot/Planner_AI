"""
app.py — Local AI Planning Agent (Gradio Web UI)
Run with: python app.py
Opens at: http://localhost:7860

Two modes:
  Tab 1 - Planner: Generate structured plans with rich markdown + download
  Tab 2 - Chat:    Conversational AI with a side panel for generated plans
"""

import warnings
import traceback
import tempfile
import os
import atexit
import logging

warnings.filterwarnings("ignore", category=DeprecationWarning)

import gradio as gr
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from config import AUTO_CHOICE, MODEL_OPTIONS, MODEL_MAP, TASK_BADGES
from agent.classifier import classify_task
from agent.model_manager import ModelManager
from agent.search_gate import needs_search
from agent.planner import stream_planner, SYSTEM_PROMPT

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

CHAT_SYSTEM_PROMPT = """You are a helpful, knowledgeable AI assistant. Be conversational, clear, and concise.
- Answer questions directly without unnecessary preamble
- Use markdown formatting when it improves readability (code blocks, lists)
- If the user asks you to make a plan, suggest they click '📋 Plan This' for a structured result
- Keep context from the conversation"""

# Shared model manager
_model_manager = ModelManager()


def _cleanup():
    """Ensure the model is stopped when exiting (Ctrl+C, etc)"""
    if _model_manager:
        _model_manager.stop_current_model()


# Register cleanup for when the script exits
atexit.register(_cleanup)


# ── Helper: resolve model override ───────────────────────────────────────────
def _resolve_model(model_choice: str, goal: str) -> tuple[str, str, str]:
    """Returns (model_name, task_type, task_badge)"""
    task_type = classify_task(goal)
    task_badge = TASK_BADGES.get(task_type, "🧠 GENERAL")

    if model_choice != AUTO_CHOICE:
        return model_choice, task_type, f"{task_badge}  *(manual)*"
    return MODEL_MAP.get(task_type, "gemma-4-12b"), task_type, task_badge


# ── Planner Tab functions ─────────────────────────────────────────────────────
def generate_plan(goal: str, model_choice: str):
    """
    Streaming generator for the Planner tab.
    Yields: (plan_md, task_badge, model_name, search_status, plan_state)
    """
    if not goal.strip():
        yield "⚠️ Please enter a goal above.", "—", "—", "—", ""
        return

    model_name, task_type, task_badge = _resolve_model(model_choice, goal)
    override = None if model_choice == AUTO_CHOICE else model_choice
    search_needed = needs_search(goal)
    search_status = "✅ Enabled" if search_needed else "❌ Not needed"

    yield f"> ⏳ *Loading **{model_name}**...*", task_badge, model_name, search_status, ""

    try:
        current_plan = ""
        for partial in stream_planner(goal, _model_manager, override):
            current_plan = partial
            yield partial, task_badge, model_name, search_status, current_plan

    except Exception as e:
        error_tb = traceback.format_exc()
        error_md = (
            f"## ❌ Error\n\n"
            f"**{type(e).__name__}:** {e}\n\n"
            f"<details>\n<summary>Full traceback (click to expand)</summary>\n\n"
            f"```\n{error_tb}\n```\n\n"
            f"</details>\n\n"
            f"> 💡 **Tip:** Check that LM Studio is running (using 'lms status') and the model is available (using 'lms ls')."
        )
        yield error_md, task_badge, model_name, search_status, ""


def download_plan(plan_text: str):
    """Save the current plan to a temp .md file and return the path for download."""
    if not plan_text.strip():
        return gr.update(visible=False)
    path = os.path.join(tempfile.gettempdir(), "ai_plan.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(plan_text)
    return gr.update(value=path, visible=True)


# ── Chat Tab functions ────────────────────────────────────────────────────────
def _build_lc_history(history: list) -> list:
    """Convert Gradio chatbot history (list of role/content dicts) to LangChain messages."""
    messages = [SystemMessage(content=CHAT_SYSTEM_PROMPT)]
    for msg in history:
        role    = msg.get("role", "") if isinstance(msg, dict) else ""
        content = msg.get("content", "") if isinstance(msg, dict) else ""
        if role == "user" and content:
            messages.append(HumanMessage(content=str(content)))
        elif role == "assistant" and content:
            messages.append(AIMessage(content=str(content)))
    return messages


def _get_text(content: str | list) -> str:
    """Safely extract text from a message content (handle multimodal list or string)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                text_parts.append(block["text"])
            elif isinstance(block, str):
                text_parts.append(block)
        return "".join(text_parts)
    return str(content)


def send_chat(message: str, history: list, model_choice: str):
    """
    Stream a chat response.
    History format: list of {"role": str, "content": str} dicts.
    """
    if not message.strip():
        yield history
        return

    model_name, task_type, _ = _resolve_model(model_choice, message)
    override = None if model_choice == AUTO_CHOICE else model_choice

    try:
        if override:
            _model_manager.switch_to_name(override)
        else:
            _model_manager.switch_to(task_type)
        llm = _model_manager.get_llm()
    except Exception as e:
        error_msg = f"❌ **Model Error:** {e}\n\n```\n{traceback.format_exc()}\n```"
        yield history + [
            {"role": "user",      "content": message},
            {"role": "assistant", "content": error_msg},
        ]
        return

    lc_messages = _build_lc_history(history)
    lc_messages.append(HumanMessage(content=message))

    new_history = history + [
        {"role": "user",      "content": message},
        {"role": "assistant", "content": ""},
    ]

    try:
        response = ""
        for chunk in llm.stream(lc_messages):
            response += _get_text(chunk.content)
            new_history[-1]["content"] = response
            yield new_history
    except Exception as e:
        new_history[-1]["content"] = (
            f"❌ **Error during generation:**\n\n"
            f"**{type(e).__name__}:** {e}\n\n"
            f"<details><summary>Traceback</summary>\n\n```\n{traceback.format_exc()}\n```\n</details>"
        )
        yield new_history


def generate_chat_plan(message: str, history: list, model_choice: str):
    """
    Generate a structured plan inside the Chat tab.
    Plan goes to the side panel; chat gets a brief confirmation message.
    Yields: (updated_history, plan_md, plan_state)
    """
    if not message.strip():
        yield history, gr.update(), ""
        return

    override = None if model_choice == AUTO_CHOICE else model_choice

    new_history = history + [
        {"role": "user",      "content": f"📋 *Plan request:* {message}"},
        {"role": "assistant", "content": "> ⏳ *Generating structured plan...*"},
    ]
    yield new_history, "> ⏳ *Generating plan...*", ""

    try:
        plan = ""
        for chunk in stream_planner(message, _model_manager, override):
            plan = chunk
            yield new_history, chunk, ""

        new_history[-1]["content"] = (
            "✅ **Plan generated!** See the **📋 Plan Panel** on the right →\n\n"
            f"> *Goal: {message}*"
        )
        yield new_history, plan, plan

    except Exception as e:
        error_md = (
            f"## ❌ Error\n\n**{type(e).__name__}:** {e}\n\n"
            f"<details><summary>Traceback</summary>\n\n```\n{traceback.format_exc()}\n```\n</details>"
        )
        new_history[-1]["content"] = f"❌ Planning failed: {e}"
        yield new_history, error_md, ""


def clear_chat():
    return [], "", ""  # chatbot, chat_plan_md, chat_plan_state


CSS = """
/* ── Enhanced Design System ─────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

:root {
    --bg-primary: #0a0c10;
    --bg-secondary: #12151d;
    --accent-blue: #3b82f6;
    --accent-purple: #8b5cf6;
    --accent-green: #10b981;
    --accent-red: #ef4444;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --border-color: rgba(255, 255, 255, 0.08);
    --glass-bg: rgba(18, 21, 29, 0.7);
    --glass-border: rgba(255, 255, 255, 0.1);
}

* { 
    font-family: 'Plus Jakarta Sans', sans-serif !important; 
}

body, .gradio-container {
    background-color: var(--bg-primary) !important;
    background-image: 
        radial-gradient(circle at 0% 0%, rgba(59, 130, 246, 0.05) 0%, transparent 50%),
        radial-gradient(circle at 100% 100%, rgba(139, 92, 246, 0.05) 0%, transparent 50%) !important;
    background-attachment: fixed !important;
    color: var(--text-primary) !important;
}

.gradio-container { max-width: 1440px !important; padding: 20px !important; margin: 0 auto !important; }

/* Header */
#header {
    background: var(--glass-bg);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid var(--glass-border);
    border-radius: 24px;
    padding: 40px 20px;
    margin-bottom: 24px;
    text-align: center;
    box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
}
#header h1 {
    font-size: 2.5rem; font-weight: 800; letter-spacing: -0.02em;
    background: linear-gradient(135deg, #60a5fa 0%, #a78bfa 50%, #f472b6 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin: 0 0 12px 0;
}
#header p { color: var(--text-secondary); font-size: 1rem; font-weight: 500; }

/* Tabs */
.tab-nav {
    background: var(--glass-bg) !important;
    padding: 6px !important;
    border-radius: 12px !important;
    border: 1px solid var(--glass-border) !important;
    margin-bottom: 20px !important;
}
.tab-nav button {
    background: transparent !important; color: var(--text-secondary) !important;
    border: none !important; border-radius: 8px !important;
    font-size: 0.9rem !important; font-weight: 600 !important;
    padding: 10px 24px !important;
}
.tab-nav button.selected {
    background: rgba(255, 255, 255, 0.05) !important;
    color: var(--text-primary) !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.1) !important;
}

/* Inputs */
textarea {
    background: rgba(15, 23, 42, 0.6) !important;
    border: 1px solid var(--glass-border) !important;
    border-radius: 12px !important;
    color: var(--text-primary) !important;
    padding: 16px !important;
}
textarea:focus { 
    border-color: var(--accent-blue) !important; 
    box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.15) !important; 
    background: rgba(15, 23, 42, 0.8) !important;
}

/* Model Selector */
.model-radio .wrap {
    background: rgba(15, 23, 42, 0.4) !important;
    border: 1px solid var(--glass-border) !important;
    border-radius: 12px !important;
    padding: 10px !important;
}
.model-radio span { 
    background: transparent !important; 
    border: 1px solid transparent !important;
    color: var(--text-secondary) !important;
    padding: 8px 16px !important;
    font-weight: 500 !important;
}
.model-radio input[type="radio"]:checked + span { 
    background: var(--accent-blue) !important;
    color: white !important;
    border-radius: 8px !important;
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3) !important;
}

/* Buttons */
.gr-button {
    border-radius: 12px !important;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
}
#generate-btn, #chat-plan-btn, #chat-send-btn {
    background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple)) !important;
    border: none !important; color: white !important;
}
#generate-btn:hover, #chat-plan-btn:hover, #chat-send-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(59, 130, 246, 0.25) !important;
}
#stop-btn, #chat-stop-btn {
    background: rgba(239, 68, 68, 0.1) !important;
    color: var(--accent-red) !important;
    border: 1px solid rgba(239, 68, 68, 0.2) !important;
}

/* Panels */
.plan-panel {
    background: var(--glass-bg) !important;
    backdrop-filter: blur(8px);
    border: 1px solid var(--glass-border) !important;
    border-radius: 16px !important;
    padding: 32px !important;
    box-shadow: 0 10px 30px rgba(0,0,0,0.2) !important;
}

.chatbot { 
    background: rgba(15, 23, 42, 0.4) !important;
    border: 1px solid var(--glass-border) !important;
    border-radius: 16px !important;
}

.info-card {
    background: rgba(255, 255, 255, 0.03) !important;
    border: 1px solid var(--glass-border) !important;
    border-radius: 12px !important;
}

.section-label { 
    color: var(--accent-blue);
    font-size: 0.75rem !important;
    font-weight: 800 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.15em !important;
    margin-bottom: 12px !important;
}
"""

# ── Gradio App ────────────────────────────────────────────────────────────────
with gr.Blocks(
    title="Local AI Planning Agent",
) as demo:

    # ── Header ────────────────────────────────────────────────────────────────
    gr.HTML("""
    <div id="header">
        <h1>✨ Local AI Planning Agent</h1>
        <p>Intelligent Multi-Model Orchestration &nbsp;•&nbsp; Powered by LM Studio</p>
        <div style="margin-top: 12px; font-size: 0.85rem; color: #64748b; font-weight: 500;">
            Gemma-4 12B &nbsp;·&nbsp; Nomic Embed
        </div>
    </div>
    """)

    # ── Shared state ──────────────────────────────────────────────────────────
    plan_state = gr.State("")  # current plan text (for download)

    with gr.Tabs():

        # ════════════════════════════════════════════════════════════════════
        # TAB 1 — PLANNER
        # ════════════════════════════════════════════════════════════════════
        with gr.Tab("📋 Planner"):

            goal_input = gr.Textbox(
                placeholder='e.g. "I want to build a SaaS product from scratch"',
                label="Your Goal",
                lines=1, max_lines=10,
            )

            model_radio = gr.Radio(
                choices=MODEL_OPTIONS, value=AUTO_CHOICE,
                label="Model", elem_classes=["model-radio"],
            )

            with gr.Row():
                generate_btn = gr.Button("⚡ Generate Plan", variant="primary", scale=3, elem_id="generate-btn")
                stop_btn     = gr.Button("⏹ Stop", variant="stop", scale=1, elem_id="stop-btn")
                download_btn = gr.Button("📥 Download Plan", scale=1, elem_id="download-btn")
                dl_file      = gr.File(label="", visible=False)

            gr.HTML("<hr class='divider'>")

            with gr.Row(equal_height=False):
                # Left — run info
                with gr.Column(scale=1, min_width=180):
                    gr.HTML("<div class='section-label'>Run Info</div>")
                    task_out   = gr.Textbox(label="Task Type",     value="—", interactive=False, elem_classes=["info-card"])
                    model_out  = gr.Textbox(label="Model",         value="—", interactive=False, elem_classes=["info-card"])
                    search_out = gr.Textbox(label="Web Search",    value="—", interactive=False, elem_classes=["info-card"])

                # Right — plan output
                with gr.Column(scale=4):
                    gr.HTML("<div class='section-label'>Generated Plan</div>")
                    plan_output = gr.Markdown(
                        value="*Your plan will appear here...*",
                        elem_classes=["plan-panel"],
                    )

            gr.HTML("<div style='margin:10px 0 6px;color:#8b949e;font-size:0.78rem;font-weight:600;text-transform:uppercase;letter-spacing:.1em'>Try an Example</div>")
            gr.Examples(
                examples=[
                    ["I want to build a SaaS product from scratch"],
                    ["How do I write a REST API using FastAPI and PostgreSQL"],
                    ["I want to learn machine learning in 6 months"],
                    ["What are the latest AI agent frameworks in 2026"],
                    ["What is a transformer model?"],
                ],
                inputs=goal_input,
                label="",
            )

            # ── Planner events ────────────────────────────────────────────
            click_event = generate_btn.click(
                fn=generate_plan,
                inputs=[goal_input, model_radio],
                outputs=[plan_output, task_out, model_out, search_out, plan_state],
            )
            goal_input.submit(
                fn=generate_plan,
                inputs=[goal_input, model_radio],
                outputs=[plan_output, task_out, model_out, search_out, plan_state],
            )
            stop_btn.click(fn=None, cancels=[click_event])
            download_btn.click(fn=download_plan, inputs=[plan_state], outputs=[dl_file])
            # Show the file component when download is triggered
            plan_state.change(
                fn=lambda t: gr.update(visible=False),
                inputs=[plan_state], outputs=[dl_file],
            )

        # ════════════════════════════════════════════════════════════════════
        # TAB 2 — CHAT
        # ════════════════════════════════════════════════════════════════════
        with gr.Tab("💬 Chat"):

            with gr.Row(equal_height=False):

                # ── Left: chat area ───────────────────────────────────────
                with gr.Column(scale=3):
                    chatbot = gr.Chatbot(
                        height=480,
                        label="",
                        elem_classes=["chatbot"],
                        show_label=False,
                    )

                    chat_msg = gr.Textbox(
                        placeholder="Type a message… (Enter to send)",
                        label="", lines=1, max_lines=10, show_label=False,
                    )

                    with gr.Row():
                        chat_send_btn = gr.Button("💬 Send",       variant="primary", scale=2, elem_id="chat-send-btn")
                        chat_plan_btn = gr.Button("📋 Plan This",  variant="secondary", scale=2, elem_id="chat-plan-btn")
                        chat_stop_btn = gr.Button("⏹ Stop",        variant="stop",      scale=1, elem_id="chat-stop-btn")
                        clear_btn     = gr.Button("🗑 Clear",       scale=1, elem_id="clear-btn")

                    chat_model = gr.Radio(
                        choices=MODEL_OPTIONS, value=AUTO_CHOICE,
                        label="Model", elem_classes=["model-radio"],
                    )

                # ── Right: plan side panel ────────────────────────────────
                with gr.Column(scale=2):
                    gr.HTML("<div class='section-label'>📋 Plan Panel</div>")
                    gr.HTML("<div style='color:#8b949e;font-size:0.8rem;margin-bottom:8px'>Plans generated here stay pinned while you chat →</div>")

                    chat_plan_md = gr.Markdown(
                        value="*No plan yet. Type a goal and click **📋 Plan This**.*",
                        elem_classes=["plan-panel"],
                    )

                    chat_download_btn = gr.Button("📥 Download Plan", elem_id="chat-download-btn")
                    chat_dl_file      = gr.File(label="", visible=False)

                    chat_plan_state = gr.State("")

            # ── Chat events ───────────────────────────────────────────────
            send_event = chat_send_btn.click(
                fn=send_chat,
                inputs=[chat_msg, chatbot, chat_model],
                outputs=[chatbot],
            ).then(fn=lambda: "", outputs=[chat_msg])  # clear input after send

            chat_msg.submit(
                fn=send_chat,
                inputs=[chat_msg, chatbot, chat_model],
                outputs=[chatbot],
            ).then(fn=lambda: "", outputs=[chat_msg])

            plan_event = chat_plan_btn.click(
                fn=generate_chat_plan,
                inputs=[chat_msg, chatbot, chat_model],
                outputs=[chatbot, chat_plan_md, chat_plan_state],
            ).then(fn=lambda: "", outputs=[chat_msg])

            chat_stop_btn.click(fn=None, cancels=[send_event, plan_event])

            clear_btn.click(fn=clear_chat, outputs=[chatbot, chat_plan_md, chat_plan_state])

            chat_download_btn.click(
                fn=download_plan,
                inputs=[chat_plan_state],
                outputs=[chat_dl_file],
            )


if __name__ == "__main__":
    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
        inbrowser=True,
        share=False,
        theme=gr.themes.Soft(primary_hue="blue", neutral_hue="slate"),
        css=CSS,
    )
