import logging
import json
import traceback
import os
import secrets
import threading
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, StreamingResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from config import AUTO_CHOICE, MODEL_OPTIONS, MODEL_MAP, TASK_BADGES
from agent.classifier import classify_task
from agent.model_manager import ModelManager
from agent.search_gate import needs_search
from agent.planner import stream_planner_async

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

security = HTTPBasic()

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, os.getenv("AUTH_USERNAME", "admin"))
    correct_password = secrets.compare_digest(credentials.password, os.getenv("AUTH_PASSWORD", "password123"))
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Nothing specific needed
    yield
    # Shutdown: Release GPU memory by stopping the current model
    logger.info("Server shutting down - unloading model from memory...")
    try:
        # stop_current_model is synchronous but we can run it in a thread or just call it
        _model_manager.stop_current_model()
    except Exception as e:
        logger.warning("Error unloading model during shutdown: %s", e)

app = FastAPI(
    title="Planner Agent Custom UI", 
    dependencies=[Depends(verify_credentials)],
    lifespan=lifespan
)

inference_lock = asyncio.Lock()

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

_model_manager = ModelManager()

# --- Data Models ---
class ChatRequest(BaseModel):
    message: str
    history: list[dict]
    model_choice: str
    current_plan: str = ""

class PlanRequest(BaseModel):
    goal: str
    model_choice: str
    use_search: str = "auto"
    chat_context: str = ""

class DownloadRequest(BaseModel):
    plan_text: str

CHAT_SYSTEM_PROMPT = """You are a helpful, knowledgeable AI assistant. Be conversational, clear, and concise.
- Answer questions directly without unnecessary preamble
- Use markdown formatting when it improves readability (code blocks, lists)
- If the user asks you to make a plan, suggest they use the Planner tab.
- Keep context from the conversation"""

def _resolve_model(model_choice: str, goal: str) -> tuple[str, str, str]:
    task_type = classify_task(goal)
    task_badge = TASK_BADGES.get(task_type, "🧠 GENERAL")
    if model_choice != AUTO_CHOICE:
        return model_choice, task_type, f"{task_badge} *(manual)*"
    return MODEL_MAP.get(task_type, "llama3.1:8b"), task_type, task_badge

def _build_lc_history(history: list, current_plan: str = "") -> list:
    sys_content = CHAT_SYSTEM_PROMPT
    if current_plan.strip():
        sys_content += f"\n\n[CONTEXT: The system previously generated the following plan. You are highly aware of this active plan:]\n{current_plan}"
        
    messages = [SystemMessage(content=sys_content)]
    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user" and content:
            messages.append(HumanMessage(content=str(content)))
        elif role == "assistant" and content:
            messages.append(AIMessage(content=str(content)))
    return messages

def _get_text(content: str | list) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join([b.get("text", str(b)) if isinstance(b, dict) else str(b) for b in content])
    return str(content)

# --- Routes ---
@app.get("/")
def read_root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    async def chat_generator():
        try:
            model_name, task_type, task_badge = _resolve_model(req.model_choice, req.message)
            override = None if req.model_choice == AUTO_CHOICE else req.model_choice
            
            async with inference_lock:
                logger.info("Chat requested. Model: %s", model_name)
                yield f"event: metadata\ndata: {json.dumps({'model': model_name, 'badge': task_badge})}\n\n"

                if override:
                    await asyncio.to_thread(_model_manager.switch_to_name, override)
                else:
                    await asyncio.to_thread(_model_manager.switch_to, task_type)
                
                llm = _model_manager.get_llm()
                
                lc_messages = _build_lc_history(req.history, getattr(req, "current_plan", ""))
                lc_messages.append(HumanMessage(content=req.message))
                
                async for chunk in llm.astream(lc_messages):
                    text = _get_text(chunk.content)
                    if text:
                        yield f"event: message\ndata: {json.dumps({'content': text})}\n\n"
                    
            yield "event: done\ndata: {}\n\n"
        except Exception as e:
            logger.error("Chat error: %s", e)
            error_msg = f"❌ **Model Error:** {e}\n\n```\n{traceback.format_exc()}\n```"
            yield f"event: error\ndata: {json.dumps({'content': error_msg})}\n\n"

    return StreamingResponse(chat_generator(), media_type="text/event-stream")

@app.post("/api/plan")
async def api_plan(req: PlanRequest):
    async def plan_generator():
        try:
            model_name, task_type, task_badge = _resolve_model(req.model_choice, req.goal)
            
            if req.use_search == "on":
                search_needed = True
                search_str = "✅ Force ON"
            elif req.use_search == "off":
                search_needed = False
                search_str = "❌ Force OFF"
            else:
                search_needed = needs_search(req.goal)
                search_str = "✅ Enabled (Auto)" if search_needed else "❌ Not needed (Auto)"
            
            override = None if req.model_choice == AUTO_CHOICE else req.model_choice
            
            async with inference_lock:
                logger.info("Plan requested. Model: %s", model_name)
                meta = {
                    "model": model_name, 
                    "badge": task_badge, 
                    "search": search_str,
                    "task": task_type
                }
                yield f"event: metadata\ndata: {json.dumps(meta)}\n\n"
                
                # stream_planner_async yields accumulated full string text step-by-step
                async for partial in stream_planner_async(req.goal, _model_manager, override, req.use_search, getattr(req, "chat_context", "")):
                    if partial:
                        yield f"event: update\ndata: {json.dumps({'content': partial})}\n\n"
            
            yield "event: done\ndata: {}\n\n"
        except Exception as e:
            logger.error("Plan error: %s", e)
            error_msg = f"## ❌ Error\n**{e}**"
            yield f"event: error\ndata: {json.dumps({'content': error_msg})}\n\n"

    return StreamingResponse(plan_generator(), media_type="text/event-stream")

@app.get("/api/models")
async def api_get_models():
    return {"models": MODEL_OPTIONS}

@app.post("/api/download")
async def api_download(req: DownloadRequest):
    return PlainTextResponse(
        req.plan_text, 
        headers={"Content-Disposition": 'attachment; filename="ai_plan.md"'}
    )

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
