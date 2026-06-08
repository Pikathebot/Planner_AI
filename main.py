import warnings
import atexit
import json
import os
import datetime
warnings.filterwarnings("ignore", category=DeprecationWarning)

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from config import MODEL_MAP
from agent.classifier import classify_task
from agent.model_manager import ModelManager
from agent.search_gate import needs_search
from agent.planner import run_planner, _get_text, _search_tool
from logger_config import log_run, log_chat

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

console = Console()

SESSIONS_FILE = "cli_sessions.json"
LAST_PLAN_EXPORT = ""

BANNER = """[cyan bold]
╔══════════════════════════════════════════════════════════╗
║              Local AI Planning Agent  v2.0               ║
║ Models: Gemma-4 12B · Powered by LM Studio               ║
╚══════════════════════════════════════════════════════════╝
[/cyan bold]
  [bold]Commands:[/bold]
  [yellow]/chat[/yellow]    → Enter Chat Mode (conversational)
  [yellow]/plan[/yellow]    → Return to Planning Mode (default)
  [yellow]/search[/yellow]  → Toggle Web Search (on|off|auto)
  [yellow]/export[/yellow]  → Export the last plan to a markdown file
  [yellow]/history[/yellow] → List saved sessions
  [yellow]/load ID[/yellow] → Load a past session
  [yellow]/save[/yellow]    → Save current session context
  [yellow]/clear[/yellow]   → Clear current context
  [yellow]quit[/yellow]     → Exit application
  
  [bold]Manual Model Override:[/bold]
  Prefix your message with [cyan]@model_name[/cyan] to manually select a model.
  Example: [cyan]@gemma-4-12b[/cyan] How do I bake a cake?
"""

CHAT_SYSTEM_PROMPT = """You are a helpful, knowledgeable AI assistant. Be conversational, clear, and concise.
- Answer questions directly without unnecessary preamble
- Use markdown formatting when it improves readability
- Keep context from the conversation"""

def load_sessions():
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def save_sessions(sessions):
    with open(SESSIONS_FILE, "w") as f:
        json.dump(sessions, f, indent=2)

def save_current_state(history, current_plan):
    if len(history) <= 1 and not current_plan:
        console.print("[yellow]Nothing to save.[/yellow]")
        return
    sessions = load_sessions()
    session_id = str(len(sessions) + 1)
    
    # Store history as list of dicts for safety
    serializable_history = []
    for msg in history:
        if isinstance(msg, SystemMessage):
            serializable_history.append({"role": "system", "content": msg.content})
        elif isinstance(msg, AIMessage):
            serializable_history.append({"role": "assistant", "content": msg.content})
        elif isinstance(msg, HumanMessage):
            serializable_history.append({"role": "user", "content": msg.content})

    title = "Session"
    for msg in serializable_history:
        if msg["role"] == "user":
            title = msg["content"][:30] + "..."
            break

    entry = {
        "id": session_id,
        "title": title,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "history": serializable_history,
        "plan": current_plan
    }
    sessions.append(entry)
    save_sessions(sessions)
    console.print(f"[green]✓ Session saved as ID {session_id}[/green]")

def load_state(session_id):
    sessions = load_sessions()
    for s in sessions:
        if s["id"] == str(session_id):
            history = []
            for msg in s["history"]:
                if msg["role"] == "system":
                    history.append(SystemMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    history.append(AIMessage(content=msg["content"]))
                elif msg["role"] == "user":
                    history.append(HumanMessage(content=msg["content"]))
            return history, s.get("plan", "")
    console.print(f"[red]Error: Session {session_id} not found.[/red]")
    return None, None

def show_history():
    sessions = load_sessions()
    if not sessions:
        console.print("[yellow]No saved sessions found.[/yellow]")
        return
    table = Table(title="Saved Sessions")
    table.add_column("ID", justify="right", style="cyan", no_wrap=True)
    table.add_column("Date", style="magenta")
    table.add_column("Title", style="green")
    
    for s in sessions[-10:]: # Show last 10
        table.add_row(s["id"], s["timestamp"], s["title"])
    console.print(table)

def chat_loop(model_manager: ModelManager, initial_override: str | None, current_history: list, search_mode: str):
    console.print(Panel.fit("[bold green]=== CHAT MODE ENABLED ===[/bold green]\nType [yellow]/plan[/yellow] to go back.", border_style="green"))
    
    current_override = initial_override
    sys_prompt = CHAT_SYSTEM_PROMPT + f"\n- Current System Date/Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    history = current_history if current_history else [SystemMessage(content=sys_prompt)]
    
    while True:
        try:
            model_disp = current_override if current_override else 'Auto'
            console.print(f"\n[bold](Chat)[/bold] Model: [cyan]{model_disp}[/cyan]")
            msg = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not msg:
            continue
            
        if msg.lower() == "/plan":
            console.print("[cyan]Returning to Planning Mode...[/cyan]")
            break
            
        if msg.lower() in {"quit", "exit", "q"}:
            return "exit", current_override, history

        if msg.startswith("@"):
            parts = msg.split(" ", 1)
            model_part = parts[0][1:].lower()
            if model_part == "auto":
                current_override = None
                console.print("  [yellow](Switched to Auto Model Selection)[/yellow]")
                if len(parts) > 1: msg = parts[1]
                else: continue
            else:
                if len(parts) > 1:
                    current_override = parts[0][1:]
                    msg = parts[1]
                else:
                    current_override = parts[0][1:]
                    console.print(f"  [yellow](Model Locked to: {current_override})[/yellow]")
                    continue
                console.print(f"  [yellow](Model Locked to: {current_override})[/yellow]")

        task_type = classify_task(msg)
        if current_override:
            model_manager.switch_to_name(current_override)
        else:
            model_manager.switch_to(task_type)
            
        llm = model_manager.get_llm()
        
        # Search Integration
        perform_search = False
        if search_mode == "on":
            perform_search = True
        elif search_mode == "off":
            perform_search = False
        else:
            perform_search = needs_search(msg)
            
        user_content = msg
        if perform_search:
            console.print("[dim italic]🔍 Searching the web...[/dim italic]")
            try:
                results = _search_tool.run(msg)
                user_content = (
                    f"User Query: {msg}\n\n"
                    f"Relevant search results (use these to inform your answer):\n"
                    f"{results}\n\n"
                    f"Based on the above, answer the user: {msg}"
                )
            except Exception as e:
                console.print(f"[red]Search failed: {e}[/red]")
                
        history.append(HumanMessage(content=user_content))
        
        console.print(f"\n[bold reverse] AI ({model_manager.get_model_name()}) [/bold reverse] ", end="")
        full_response = ""
        
        try:
            for chunk in llm.stream(history):
                content = _get_text(chunk.content)
                full_response += content
                print(content, end="", flush=True)
            print() 
            history.append(AIMessage(content=full_response))
            log_chat(msg, model_manager.get_model_name(), full_response)
        except Exception as e:
            console.print(f"\n[red][Error] Chat failed: {e}[/red]")

    return "continue", current_override, history


_model_manager = None

def _cleanup():
    if _model_manager:
        _model_manager.stop_current_model()

atexit.register(_cleanup)

def main():
    global _model_manager, LAST_PLAN_EXPORT
    console.print(BANNER)

    _model_manager = ModelManager()

    session_override = None
    search_mode = "auto"
    sys_prompt = CHAT_SYSTEM_PROMPT + f"\n- Current System Date/Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    active_history = [SystemMessage(content=sys_prompt)]
    active_plan = ""

    while True:
        try:
            prompt_model = session_override if session_override else "Auto"
            console.print(f"\n[bold]Plan[/bold] (Model: [cyan]{prompt_model}[/cyan] | Search: [magenta]{search_mode}[/magenta])")
            goal = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Exiting. Goodbye![/yellow]")
            break

        if not goal:
            continue

        if goal.lower() == "/chat":
            result, session_override, active_history = chat_loop(_model_manager, session_override, active_history, search_mode)
            if result == "exit":
                console.print("\n[yellow]Exiting. Goodbye![/yellow]")
                break
            continue

        if goal.lower() in {"quit", "exit", "q"}:
            console.print("\n[yellow]Exiting. Goodbye![/yellow]")
            break

        if goal.lower() == "/clear":
            sys_prompt = CHAT_SYSTEM_PROMPT + f"\n- Current System Date/Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            active_history = [SystemMessage(content=sys_prompt)]
            active_plan = ""
            LAST_PLAN_EXPORT = ""
            console.print("[green]Context cleared![/green]")
            continue

        if goal.lower() == "/save":
            save_current_state(active_history, active_plan)
            continue
            
        if goal.lower() == "/history":
            show_history()
            continue

        if goal.lower().startswith("/load "):
            sess_id = goal.split(" ")[1]
            h, p = load_state(sess_id)
            if h is not None:
                active_history = h
                active_plan = p
                LAST_PLAN_EXPORT = p
                console.print(f"[green]Session {sess_id} loaded into active memory![/green]")
            continue

        if goal.lower().startswith("/search "):
            parts = goal.split(" ")
            if len(parts) == 2 and parts[1].lower() in ["on", "off", "auto"]:
                search_mode = parts[1].lower()
                console.print(f"[green]Web search set to: {search_mode}[/green]")
            else:
                console.print("[red]Usage: /search on|off|auto[/red]")
            continue

        if goal.lower() == "/export":
            if not LAST_PLAN_EXPORT:
                console.print("[red]No plan generated yet to export![/red]")
            else:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"plan_export_{timestamp}.md"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(LAST_PLAN_EXPORT)
                console.print(f"[green]✓ Plan exported to {filename}[/green]")
            continue

        if goal.startswith("@"):
            parts = goal.split(" ", 1)
            model_part = parts[0][1:].lower()
            if model_part == "auto":
                session_override = None
                console.print("  [yellow](Switched to Auto Model Selection)[/yellow]")
                if len(parts) > 1: goal = parts[1]
                else: continue
            else:
                if len(parts) > 1:
                    session_override = parts[0][1:]
                    goal = parts[1]
                else:
                    session_override = parts[0][1:]
                    console.print(f"  [yellow](Model Locked to: {session_override})[/yellow]")
                    continue

        task_type = classify_task(goal)
        selected_model = session_override if session_override else MODEL_MAP.get(task_type, "gemma-4-12b")
        
        info_panel = Panel.fit(f"Task type: [bold]{task_type.upper()}[/bold]\nModel: [bold]{selected_model}[/bold]\nSearch: [bold]{search_mode}[/bold]", title="Agent Reasoning", border_style="cyan")
        console.print(info_panel)

        try:
            # Build stringified chat context
            chat_context_str = ""
            for msg in active_history:
                role = "User" if isinstance(msg, HumanMessage) else "Assistant"
                if not isinstance(msg, SystemMessage):
                    chat_context_str += f"{role}: {msg.content}\n"

            console.print("[dim italic]Generating plan...[/dim italic]")
            plan = run_planner(goal, _model_manager, model_override=session_override, use_search=search_mode, chat_context=chat_context_str)
            model_name = _model_manager.get_model_name() or "unknown"
            
            LAST_PLAN_EXPORT = plan
            active_plan = plan
            active_history.append(HumanMessage(content=f"Plan this: {goal}"))
            active_history.append(AIMessage(content=f"Generated Plan:\n{plan}"))

            console.print(Panel(Markdown(plan), title="[bold green]FINAL PLAN[/bold green]", border_style="green"))

            log_run(goal, task_type, model_name, plan)
            console.print("[yellow]  ✓ Logged to log.txt[/yellow]")

        except Exception as e:
            console.print(f"\n  [red][Error] Agent failed: {e}[/red]")

if __name__ == "__main__":
    main()