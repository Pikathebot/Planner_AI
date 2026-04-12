import logging
import json
import traceback
import os
import secrets
import threading
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
from agent.planner import stream_planner

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
    return credentials.username

app = FastAPI(title="Planner Agent Custom UI", dependencies=[Depends(verify_credentials)])

inference_lock = threading.Lock()

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

_model_manager = ModelManager()

# --- Data Models ---
class ChatRequest(BaseModel):
    message: str
    history: list[dict]
    model_choice: str

class PlanRequest(BaseModel):
    goal: str
    model_choice: str

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

def _build_lc_history(history: list) -> list:
    messages = [SystemMessage(content=CHAT_SYSTEM_PROMPT)]
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
    def chat_generator():
        try:
            model_name, task_type, task_badge = _resolve_model(req.model_choice, req.message)
            override = None if req.model_choice == AUTO_CHOICE else req.model_choice
            
            logger.info("Chat requested. Model: %s", model_name)
            yield f"event: metadata\ndata: {json.dumps({'model': model_name, 'badge': task_badge})}\n\n"

            with inference_lock:
                if override:
                    _model_manager.switch_to_name(override)
                else:
                    _model_manager.switch_to(task_type)
                llm = _model_manager.get_llm()
                
                lc_messages = _build_lc_history(req.history)
                lc_messages.append(HumanMessage(content=req.message))
                
                for chunk in llm.stream(lc_messages):
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
    def plan_generator():
        try:
            model_name, task_type, task_badge = _resolve_model(req.model_choice, req.goal)
            search_needed = needs_search(req.goal)
            search_str = "✅ Enabled" if search_needed else "❌ Not needed"
            
            logger.info("Plan requested. Model: %s", model_name)
            meta = {
                "model": model_name, 
                "badge": task_badge, 
                "search": search_str,
                "task": task_type
            }
            yield f"event: metadata\ndata: {json.dumps(meta)}\n\n"
            
            override = None if req.model_choice == AUTO_CHOICE else req.model_choice
            
            with inference_lock:
                # stream_planner yields accumulated full string text step-by-step
                for partial in stream_planner(req.goal, _model_manager, override):
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
