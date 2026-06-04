import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import os
import uuid
import asyncio
import json
import re
import io
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from threading import Thread
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer
import jwt
import bcrypt
from wordcloud import WordCloud
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Import local backend layers
from backend.config import HOST, PORT, RELOAD
from backend.scraper import AsyncWebScraper
from backend.vector_store import FAISSVectorStore
from backend import database as db
from backend.translator import translator_engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up local models on startup inside the worker process
    try:
        load_qwen_model()
    except Exception as e:
        print(f"Could not load local Qwen model on startup: {str(e)}. Will attempt on first query.")
    yield

# Initialize FastAPI app with lifespan handler
app = FastAPI(
    title="RAG-Powered Website Chatbot API (Local Qwen Edition)", 
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS so local HTML files can make requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In development, allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global states for real-time progress logs
crawling_status = {
    "state": "idle", # idle, crawling, completed, error
    "logs": [],
    "visited_count": 0,
    "max_pages": 0,
    "current_url": ""
}

# Initialize vector store
vector_store = FAISSVectorStore()

# Global local LLM states
qwen_model = None
qwen_tokenizer = None

def load_qwen_model():
    """Lazily loads local Qwen-2.5-1.5B model on demand or startup."""
    global qwen_model, qwen_tokenizer
    if qwen_model is None:
        model_name = "Qwen/Qwen2.5-1.5B-Instruct"
        print(f"\n--- Loading local LLM model: {model_name} ---")
        
        # Check for CUDA GPU availability
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Hardware Acceleration: {device.upper()}")
        
        qwen_tokenizer = AutoTokenizer.from_pretrained(model_name)
        
        # Use Float16 on GPU (low memory) and BFloat16 on CPU to save memory
        torch_dtype = torch.float16 if device == "cuda" else torch.bfloat16
        
        qwen_model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch_dtype,
            device_map="auto" if device == "cuda" else None,
            low_cpu_mem_usage=True
        )
        
        if device == "cpu":
            qwen_model = qwen_model.to(device)
            
        print("Local LLM model loaded successfully!\n")

# Security Configuration
SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-key-for-rag-chatbot")
ALGORITHM = "HS256"

security_bearer = HTTPBearer()

def is_strong_password(password: str) -> bool:
    if len(password) < 8:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False
    return True

def create_access_token(email: str, is_admin: int) -> str:
    payload = {
        "email": email,
        "is_admin": is_admin,
        "exp": datetime.utcnow() + timedelta(days=1)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None

async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security_bearer)):
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token or expired session.")
    
    user = db.get_user_by_email(payload["email"])
    if not user:
        raise HTTPException(status_code=401, detail="User account not found.")
    if user.get("is_deleted"):
        raise HTTPException(status_code=401, detail="User account has been deleted.")
        
    # Check lock status
    if user.get("is_locked"):
        lock_until = user.get("lock_until")
        if lock_until:
            try:
                lock_time = datetime.fromisoformat(lock_until)
                if datetime.utcnow() < lock_time:
                    raise HTTPException(
                        status_code=403, 
                        detail=f"Account is temporarily locked due to failed attempts."
                    )
                else:
                    db.reset_failed_attempts(user["email"])
                    user = db.get_user_by_email(payload["email"])
            except ValueError:
                raise HTTPException(status_code=403, detail="Account is locked.")
        else:
            raise HTTPException(status_code=403, detail="Account is locked by administrator.")
            
    return user

async def get_admin_user(current_user: dict = Depends(get_current_user)):
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin permissions required.")
    return current_user

# Pydantic Schemas
class ScrapeRequest(BaseModel):
    url: str
    max_depth: Optional[int] = 2
    max_pages: Optional[int] = 50

class ChatRequest(BaseModel):
    session_id: str
    message: str
    language: Optional[str] = "en"

class SessionCreateRequest(BaseModel):
    url: str

class UserSignupRequest(BaseModel):
    email: str
    username: str
    password: str

class UserLoginRequest(BaseModel):
    email: str
    password: str

class FeedbackRequest(BaseModel):
    rating: int
    comments: Optional[str] = ""

# ----------------- BACKGROUND TASK FUNCTION -----------------
async def background_crawl_task(url: str, max_depth: int, max_pages: int):
    global crawling_status
    crawling_status["state"] = "crawling"
    crawling_status["logs"] = []
    crawling_status["visited_count"] = 0
    crawling_status["max_pages"] = max_pages
    crawling_status["current_url"] = url
    
    def log_callback(message: str):
        crawling_status["logs"].append(message)
        # Parse visited count from standard log line: "Scraping (X/Y): URL"
        if "Scraping (" in message:
            try:
                parts = message.split("Scraping (")[1].split("/")[0]
                crawling_status["visited_count"] = int(parts)
            except Exception:
                pass
                
    try:
        # Clear database crawled log from previous sessions
        db.clear_crawled_pages()
        
        # Start scraping
        scraper = AsyncWebScraper(url, max_depth=max_depth, max_pages=max_pages)
        log_callback(f"Starting recursive crawl of: {url} (Max Depth: {max_depth}, Max Pages: {max_pages})")
        scraped_pages = await scraper.crawl(log_callback)
        
        if scraped_pages:
            log_callback("Indexing scraped pages into FAISS vector database...")
            num_chunks = vector_store.ingest_pages(scraped_pages)
            log_callback(f"FAISS indexing complete! Extracted and indexed {num_chunks} text chunks.")
            crawling_status["state"] = "completed"
        else:
            log_callback("Crawling finished but no content was extracted.")
            crawling_status["state"] = "error"
            
    except Exception as e:
        log_callback(f"Scraping task encountered an error: {str(e)}")
        crawling_status["state"] = "error"

# ----------------- ENDPOINTS -----------------

@app.post("/api/sessions")
def create_new_session(req: SessionCreateRequest, current_user: dict = Depends(get_current_user)):
    """Creates a new session for a specific target URL."""
    session_id = str(uuid.uuid4())
    success = db.create_session(session_id, req.url, current_user["email"])
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create session.")
    # Initialize welcome message
    db.add_chat_message(
        session_id, 
        "assistant", 
        f"Hello! I am ready to answer your questions about **{req.url}** based on the scraped content. Ask me anything!"
    )
    return {"session_id": session_id, "url": req.url}

@app.get("/api/sessions")
def get_all_chat_sessions(current_user: dict = Depends(get_current_user)):
    """Retrieves all chat sessions."""
    email = None if current_user.get("is_admin") else current_user["email"]
    return db.get_all_sessions(email)

@app.get("/api/sessions/{session_id}/history")
def get_session_chat_history(session_id: str, current_user: dict = Depends(get_current_user)):
    """Retrieves chronological chat log for a session."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    
    if not current_user.get("is_admin") and session.get("user_email") != current_user["email"]:
        raise HTTPException(status_code=403, detail="Access denied to this chat session.")
        
    messages = db.get_chat_history(session_id)
    return {"session": session, "messages": messages}

@app.delete("/api/sessions/{session_id}")
def delete_chat_session(session_id: str, current_user: dict = Depends(get_current_user)):
    """Deletes a chat session and cascades history removal."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
        
    if not current_user.get("is_admin") and session.get("user_email") != current_user["email"]:
        raise HTTPException(status_code=403, detail="Access denied to this chat session.")
        
    success = db.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete session.")
        
    return {"message": "Session deleted successfully."}


@app.post("/api/scrape")
def trigger_website_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    """Triggers an async recursive crawl of the given URL in the background."""
    db.log_system_activity("feature_hit", "scrape")
    # Verify URL format
    if not req.url.startswith("http://") and not req.url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invalid URL scheme. Must start with http:// or https://")
        
    # Start crawl in the background
    background_tasks.add_task(
        background_crawl_task, 
        req.url, 
        req.max_depth, 
        req.max_pages
    )
    return {"message": "Scraping triggered successfully.", "url": req.url}

@app.get("/api/status")
def get_crawling_status(current_user: dict = Depends(get_current_user)):
    """Returns real-time scraping progression and index analytics."""
    crawled_pages = db.get_all_crawled_pages()
    total_pages = len(crawled_pages)
    total_words = sum(p["word_count"] for p in crawled_pages)
    
    return {
        "state": crawling_status["state"],
        "logs": crawling_status["logs"][-15:], # return last 15 log lines for readability
        "visited_count": crawling_status["visited_count"],
        "max_pages": crawling_status["max_pages"],
        "analytics": {
            "total_pages_scraped": total_pages,
            "total_words_indexed": total_words,
            "scrawled_details": crawled_pages
        }
    }

@app.post("/api/chat")
async def chat_with_website(req: ChatRequest, current_user: dict = Depends(get_current_user)):
    """Answers user queries with stream tokens using RAG over the FAISS vector database with Qwen."""
    session = db.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
        
    # Access control: users can only chat in their own sessions unless admin
    if not current_user.get("is_admin") and session.get("user_email") != current_user["email"]:
        raise HTTPException(status_code=403, detail="Access denied to this chat session.")
        
    # Ensure Qwen model is fully loaded locally
    load_qwen_model()
    
    # 1. Translate query to English if non-English
    original_query = req.message
    source_lang = req.language or "en"
    
    db.log_system_activity("chat_query", "qwen")
    db.log_system_activity("feature_hit", "chat")
    
    if source_lang != "en":
        db.log_system_activity("translation", source_lang)
        english_query = translator_engine.translate(original_query, source_lang, "en")
    else:
        english_query = original_query
        
    # Search FAISS index using English query for top 4 relevant chunks
    matching_chunks = vector_store.search(english_query, top_k=4)
    
    # Format matching context and citations
    context_str = ""
    citations = []
    
    for i, chunk in enumerate(matching_chunks):
        context_str += f"\n[Context Chunk {i+1}] (Source: {chunk['url']})\n{chunk['text']}\n"
        citations.append({
            "title": chunk["title"],
            "url": chunk["url"],
            "score": chunk["score"]
        })
        
    # Retrieve chat history for conversational grounding
    past_messages = db.get_chat_history(req.session_id)
    recent_history = past_messages[-4:] if past_messages else []
    
    # Assemble template message block in OpenAI style
    system_prompt = (
        "You are an intelligent, helpful RAG chatbot trained to answer questions about a website.\n"
        "Generate a clear, detailed, and directly relevant response based ONLY on the provided Context below.\n"
        "Support markdown formatting (such as lists, bold text, and code block formatting).\n"
        "If the provided Context does not contain enough information to answer the question, state politely "
        "that the context does not contain the answer. Do not hallucinate or make up facts.\n"
        "Keep your tone professional, objective, and extremely helpful.\n"
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    
    # Append past conversational dialogues
    for msg in recent_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
        
    # Append current context and question
    user_prompt = (
        f"Context Chunks:\n{context_str}\n\n"
        f"Question: {english_query}"
    )
    messages.append({"role": "user", "content": user_prompt})
    
    # Save original native user query to history
    db.add_chat_message(req.session_id, "user", original_query)
    
    async def response_streamer():
        full_response = ""
        try:
            # Format applying Qwen Chat Template
            text = qwen_tokenizer.apply_chat_template(
                messages, 
                tokenize=False, 
                add_generation_prompt=True
            )
            
            # Map input tensors to the Qwen device (CPU or CUDA GPU)
            model_inputs = qwen_tokenizer([text], return_tensors="pt").to(qwen_model.device)
            
            # Create a TextIteratorStreamer to stream causally generated tokens
            streamer = TextIteratorStreamer(
                qwen_tokenizer, 
                skip_prompt=True, 
                skip_special_tokens=True
            )
            
            generation_kwargs = dict(
                model_inputs, 
                streamer=streamer, 
                max_new_tokens=512,
                do_sample=True,
                temperature=0.7,
                top_p=0.9
            )
            
            # Start Qwen generator inside a separate background thread
            thread = Thread(target=qwen_model.generate, kwargs=generation_kwargs)
            thread.start()
            
            # Send citations first as a special SSE line
            citation_line = f"__CITATIONS__:{json.dumps(citations)}\n"
            yield citation_line
            
            # Stream tokens
            for new_text in streamer:
                full_response += new_text
                if source_lang == "en":
                    yield new_text
                await asyncio.sleep(0.01) # minor sleep for pacing
                
            # If target language is not English, translate final response back and yield
            if source_lang != "en":
                translated_response = translator_engine.translate(full_response, "en", source_lang)
                yield translated_response
                full_response = translated_response
                
            # Log assistant dialogue response to database once stream closes
            db.add_chat_message(req.session_id, "assistant", full_response)
            
        except Exception as e:
            error_msg = f"\n[Error generating response: {str(e)}]"
            yield error_msg
            db.add_chat_message(req.session_id, "assistant", error_msg)
            
    return StreamingResponse(response_streamer(), media_type="text/event-stream")

# ----------------- AUTHENTICATION ENDPOINTS -----------------

@app.post("/api/auth/signup")
def signup(req: UserSignupRequest):
    """Signs up a new user checking password strength and account presence."""
    if not is_strong_password(req.password):
        raise HTTPException(
            status_code=400, 
            detail="Password must be at least 8 characters long, contain an uppercase letter, a lowercase letter, a number, and a special character."
        )
    
    existing_user = db.get_user_by_email(req.email)
    if existing_user:
        if existing_user.get("is_deleted"):
            raise HTTPException(status_code=400, detail="Registration not allowed for this email address.")
        raise HTTPException(status_code=400, detail="Email is already registered.")
        
    pwd_hash = bcrypt.hashpw(req.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    success = db.create_user(req.email, req.username, pwd_hash)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create user account.")
        
    db.log_system_activity("feature_hit", "signup")
    return {"message": "User registered successfully."}

@app.post("/api/auth/login")
def login(req: UserLoginRequest):
    """Authenticates a user and issues a JWT token, managing failed attempts and lockouts."""
    user = db.get_user_by_email(req.email)
    if not user or user.get("is_deleted"):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
        
    # Check lock status
    if user.get("is_locked"):
        lock_until = user.get("lock_until")
        if lock_until:
            try:
                lock_time = datetime.fromisoformat(lock_until)
                if datetime.utcnow() < lock_time:
                    raise HTTPException(
                        status_code=403, 
                        detail=f"Account locked. Try again later."
                    )
                else:
                    db.reset_failed_attempts(req.email)
                    user = db.get_user_by_email(req.email)
            except ValueError:
                raise HTTPException(status_code=403, detail="Account is locked.")
        else:
            raise HTTPException(status_code=403, detail="Account is locked by administrator.")
            
    # Check password
    pwd_correct = bcrypt.checkpw(req.password.encode('utf-8'), user["password_hash"].encode('utf-8'))
    
    if not pwd_correct:
        db.increment_failed_attempts(req.email)
        updated_user = db.get_user_by_email(req.email)
        if updated_user and updated_user.get("is_locked"):
            raise HTTPException(status_code=403, detail="Account locked. Too many failed login attempts.")
        raise HTTPException(status_code=401, detail="Invalid email or password.")
        
    # Reset lock state on successful login
    db.reset_failed_attempts(req.email)
    
    token = create_access_token(user["email"], user["is_admin"])
    db.log_system_activity("feature_hit", "login")
    
    return {
        "token": token,
        "email": user["email"],
        "username": user["username"],
        "role": "admin" if user["is_admin"] else "user"
    }

# ----------------- FEEDBACK ENDPOINTS -----------------

@app.post("/api/feedback")
def submit_feedback(req: FeedbackRequest, current_user: dict = Depends(get_current_user)):
    """Logs user ratings and comments."""
    if req.rating < 1 or req.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5.")
    db.log_feedback(current_user["email"], req.rating, req.comments)
    db.log_system_activity("feature_hit", "feedback")
    return {"message": "Feedback submitted successfully."}

# ----------------- ADMIN PANEL CONTROL ENDPOINTS -----------------

@app.get("/api/admin/users")
def get_users(admin_user: dict = Depends(get_admin_user)):
    """Lists all active user accounts."""
    return db.get_all_users()

@app.post("/api/admin/users/{email}/promote")
def promote_user(email: str, admin_user: dict = Depends(get_admin_user)):
    """Promotes or demotes admin privileges for a user."""
    user = db.get_user_by_email(email)
    if not user or user.get("is_deleted"):
        raise HTTPException(status_code=404, detail="User not found.")
    new_status = 1 if not user.get("is_admin") else 0
    db.promote_user_to_admin(email, new_status)
    db.log_system_activity("feature_hit", "admin_promote")
    return {"message": f"User status updated. Admin: {bool(new_status)}"}

@app.post("/api/admin/users/{email}/lock")
def lock_user_user(email: str, admin_user: dict = Depends(get_admin_user)):
    """Locks or unlocks a user account manually."""
    user = db.get_user_by_email(email)
    if not user or user.get("is_deleted"):
        raise HTTPException(status_code=404, detail="User not found.")
    if email == admin_user["email"]:
        raise HTTPException(status_code=400, detail="You cannot lock your own account.")
    new_status = 1 if not user.get("is_locked") else 0
    db.toggle_user_lock(email, new_status)
    db.log_system_activity("feature_hit", "admin_lock")
    return {"message": f"User lock status updated. Locked: {bool(new_status)}"}

@app.delete("/api/admin/users/{email}/delete")
def delete_user(email: str, admin_user: dict = Depends(get_admin_user)):
    """Soft deletes a user account."""
    user = db.get_user_by_email(email)
    if not user or user.get("is_deleted"):
        raise HTTPException(status_code=404, detail="User not found.")
    if email == admin_user["email"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")
    db.delete_user_account(email)
    db.log_system_activity("feature_hit", "admin_delete")
    return {"message": "User account soft-deleted successfully."}

@app.get("/api/admin/stats")
def get_admin_stats(admin_user: dict = Depends(get_admin_user)):
    """Returns aggregated stats for dashboard counters and Plotly charts."""
    gen_stats = db.get_general_stats()
    activity_stats = db.get_activity_stats()
    feedbacks = db.get_all_feedback()
    db.log_system_activity("feature_hit", "admin_stats")
    return {
        "general": gen_stats,
        "activity": activity_stats,
        "feedback": feedbacks
    }

@app.get("/api/admin/feedback/wordcloud")
def get_wordcloud(admin_user: dict = Depends(get_admin_user)):
    """Generates and serves the feedback comments word cloud image stream."""
    feedbacks = db.get_all_feedback()
    comments = [f["comments"] for f in feedbacks if f["comments"] and f["comments"].strip()]
    text = " ".join(comments)
    if not text.strip():
        text = "No feedback comments available yet"
        
    wordcloud = WordCloud(width=800, height=400, background_color='#0f1226', colormap='prism').generate(text)
    
    plt.figure(figsize=(10, 5), facecolor='#0f1226')
    plt.imshow(wordcloud, interpolation='bilinear')
    plt.axis('off')
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0, facecolor='#0f1226')
    plt.close()
    buf.seek(0)
    
    db.log_system_activity("feature_hit", "admin_wordcloud")
    return StreamingResponse(buf, media_type="image/png")

@app.get("/api/admin/export/{type}")
def export_data(type: str, admin_user: dict = Depends(get_admin_user)):
    """Exports feedback or activity logs to a downloadable CSV file."""
    import csv
    if type == "feedback":
        data = db.get_all_feedback()
        columns = ["id", "user_email", "rating", "comments", "created_at"]
        filename = "feedback_export.csv"
    elif type == "activity":
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM system_activity ORDER BY created_at DESC")
        data = [dict(row) for row in cursor.fetchall()]
        conn.close()
        columns = ["id", "activity_type", "detail", "created_at"]
        filename = "activity_export.csv"
    else:
        raise HTTPException(status_code=400, detail="Invalid export type. Must be 'feedback' or 'activity'.")
        
    buf = io.StringIO()
    writer = csv.writer(buf)
    
    # Write header
    writer.writerow(columns)
    
    # Write data rows
    for row in data:
        writer.writerow([row.get(col, "") for col in columns])
        
    csv_str = buf.getvalue()
    
    db.log_system_activity("feature_hit", f"admin_export_{type}")
    return StreamingResponse(
        io.BytesIO(csv_str.encode("utf-8")), 
        media_type="text/csv", 
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

from fastapi.staticfiles import StaticFiles
from backend.config import BASE_DIR
app.mount("/", StaticFiles(directory=str(BASE_DIR / "frontend"), html=True), name="frontend")

# Start command execution helper
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=RELOAD)
