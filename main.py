import warnings
import atexit
warnings.filterwarnings("ignore", category=DeprecationWarning)

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from config import MODEL_MAP
from agent.classifier import classify_task
from agent.model_manager import ModelManager
from agent.planner import run_planner, _get_text
from logger_config import log_run, log_chat

# ── ANSI color codes ──────────────────────────────────────────────────────────
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RED    = "\033[91m"
RESET  = "\033[0m"

BANNER = f"""
{CYAN}{BOLD}
╔══════════════════════════════════════════════════════════╗
║              Local AI Planning Agent  v2.0               ║
║ Models: llama3.1:8b · qwen · gemma4 · llama3.2:latest    ║
╚══════════════════════════════════════════════════════════╝
{RESET}
  Commands:
  {YELLOW}/chat{RESET}  → Enter Chat Mode (conversational)
  {YELLOW}/plan{RESET}  → Return to Planning Mode (default)
  {YELLOW}quit{RESET}   → Exit application
  
  Manual Model Override:
  Prefix your message with {CYAN}@model_name{RESET} to manually select a model.
  This model will STAY active for the rest of the session.
  Type {CYAN}@auto{RESET} to return to automatic model switching.
  Example: {CYAN}@llama3.2:latest{RESET} How do I bake a cake?
"""

CHAT_SYSTEM_PROMPT = """You are a helpful, knowledgeable AI assistant. Be conversational, clear, and concise.
- Answer questions directly without unnecessary preamble
- Use markdown formatting when it improves readability
- If asked for a plan, suggest using Planning Mode
- Keep context from the conversation"""


def chat_loop(model_manager: ModelManager, initial_override: str | None = None):
    """Interactive conversational loop."""
    print(f"\n{GREEN}{BOLD}=== CHAT MODE ENABLED ==={RESET}")
    print(f"Type {YELLOW}'/plan'{RESET} to go back to Planning Mode.")
    
    current_override = initial_override
    history = [SystemMessage(content=CHAT_SYSTEM_PROMPT)]
    
    while True:
        try:
            msg = input(f"\n{BOLD}(Chat) Model: {current_override if current_override else 'Auto'}{RESET}\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not msg:
            continue
        
        if msg.lower() == "/plan":
            print(f"\n{CYAN}Returning to Planning Mode...{RESET}")
            break
        
        if msg.lower() in {"quit", "exit", "q"}:
            return "exit", current_override

        # Logic for manual model override via "@model_name message"
        if msg.startswith("@"):
            parts = msg.split(" ", 1)
            model_part = parts[0][1:].lower()
            if model_part == "auto":
                current_override = None
                print(f"  {YELLOW}(Switched to Auto Model Selection){RESET}")
                if len(parts) > 1:
                    msg = parts[1]
                else:
                    continue
            else:
                if len(parts) > 1:
                    current_override = parts[0][1:]
                    msg = parts[1]
                    print(f"  {YELLOW}(Model Locked to: {current_override}){RESET}")
                else:
                    current_override = parts[0][1:]
                    print(f"  {YELLOW}(Model Locked to: {current_override}){RESET}")
                    continue

        # Classification for chat (handles model switching)
        task_type = classify_task(msg)
        
        if current_override:
            model_manager.switch_to_name(current_override)
        else:
            model_manager.switch_to(task_type)
            
        llm = model_manager.get_llm()
        
        history.append(HumanMessage(content=msg))
        
        print(f"\n{BOLD}AI ({model_manager.get_model_name()}):{RESET} ", end="", flush=True)
        full_response = ""
        
        try:
            for chunk in llm.stream(history):
                content = _get_text(chunk.content)
                full_response += content
                print(content, end="", flush=True)
            print() # Newline after response
            history.append(AIMessage(content=full_response))
            # Log chat interaction
            log_chat(msg, model_manager.get_model_name(), full_response)
        except Exception as e:
            print(f"\n{RED}[Error] Chat failed: {e}{RESET}")

    return "continue", current_override


# Shared model manager (global for cleanup access)
_model_manager = None

def _cleanup():
    """Ensure the model is stopped when exiting (Ctrl+C, etc)"""
    if _model_manager:
        _model_manager.stop_current_model()

# Register cleanup for when the script exits
atexit.register(_cleanup)

def main():
    global _model_manager
    print(BANNER)

    # Shared ModelManager — only one Ollama model active at a time (per spec)
    _model_manager = ModelManager()

    # Shared Persistent Model Override
    session_override = None

    while True:
        try:
            prompt_model = session_override if session_override else "Auto"
            goal = input(f"\n{BOLD}Plan (Model: {prompt_model}){RESET}\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{YELLOW}Exiting. Goodbye!{RESET}")
            break

        if not goal:
            continue

        if goal.lower() == "/chat":
            result, session_override = chat_loop(_model_manager, session_override)
            if result == "exit":
                print(f"\n{YELLOW}Exiting. Goodbye!{RESET}")
                break
            continue

        if goal.lower() in {"quit", "exit", "q"}:
            print(f"\n{YELLOW}Exiting. Goodbye!{RESET}")
            break

        # Logic for persistent model override via "@model_name goal"
        if goal.startswith("@"):
            parts = goal.split(" ", 1)
            model_part = parts[0][1:].lower()
            if model_part == "auto":
                session_override = None
                print(f"  {YELLOW}(Switched to Auto Model Selection){RESET}")
                if len(parts) > 1:
                    goal = parts[1]
                else:
                    continue
            else:
                if len(parts) > 1:
                    session_override = parts[0][1:]
                    goal = parts[1]
                    print(f"  {YELLOW}(Model Locked to: {session_override}){RESET}")
                else:
                    session_override = parts[0][1:]
                    print(f"  {YELLOW}(Model Locked to: {session_override}){RESET}")
                    continue

        # Show which model will be selected before running
        task_type = classify_task(goal)
        selected_model = session_override if session_override else MODEL_MAP.get(task_type, "llama3.1:8b")
        
        print(f"\n{CYAN}{'─' * 50}{RESET}")
        print(f"  Task type  : {BOLD}{task_type.upper()}{RESET}")
        print(f"  Model      : {BOLD}{selected_model}{RESET}")
        if session_override:
            print(f"  {YELLOW}(Persistent Manual Override Active){RESET}")
        print(f"{CYAN}{'─' * 50}{RESET}")
        print(f"{BOLD}=== AGENT REASONING ==={RESET}")

        try:
            plan = run_planner(goal, _model_manager, model_override=session_override)
            model_name = _model_manager.get_model_name() or "unknown"

            print(f"\n{GREEN}{BOLD}{'═' * 50}")
            print("  FINAL PLAN")
            print(f"{'═' * 50}{RESET}")
            print(plan)

            # Auto-log every run
            log_run(goal, task_type, model_name, plan)
            print(f"\n{YELLOW}  ✓ Logged to log.txt{RESET}")

        except Exception as e:
            print(f"\n  [Error] Agent failed: {e}")


if __name__ == "__main__":
    main()