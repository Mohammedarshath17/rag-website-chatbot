# 🕸️ WebRAG: Premium Local Offline RAG-Powered Website Chatbot

WebRAG is a state-of-the-art, high-performance RAG (Retrieval-Augmented Generation) website chatbot. It crawls and ingests any given website URL, recursively scrapes sub-pages under the same domain, indexes the content chunks into a **FAISS** vector database using a local **`all-MiniLM-L6-v2`** model, and streams answers using the local **`Qwen/Qwen2.5-1.5B-Instruct`** model with sub-second latency.

Because it runs local open-source models, the system is **100% free, runs entirely offline, and respects data privacy**—no user queries or scraped details are ever transmitted to third-party APIs.

---

## ✨ Features

* **Asynchronous Recursive Scraper**: Dynamic concurrent crawler using `httpx` and `BeautifulSoup4` that crawls sub-pages within a domain, ignoring navigation bars, footers, script code, and non-HTML assets.
* **FAISS Vector Database (`faiss-cpu`)**: Highly optimized similarity search indexing on extracted text chunks using the local `all-MiniLM-L6-v2` embedding model.
* **Qwen/Qwen2.5-1.5B-Instruct LLM**: A local, state-of-the-art conversational model loaded via the HuggingFace `transformers` library. It automatically uses CUDA GPU acceleration if available, falling back smoothly to CPU execution.
* **Token-by-Token SSE Stream Routing**: streaming response generation using `StreamingResponse` for chat responses, yielding instantaneous chatbot replies.
* **Session and Crawl History**: Relational SQLite3 database that stores session states, message histories, and scrapers statistics (e.g. pages scraped, words indexed).
* **Live Ingestion logs**: Terminal progression screen that streams crawling state changes in real-time.
* **Source Citation Chips**: Provides citation links and search relevance matching percentages for every retrieved chunk.
* **100% Offline Integrity**: Zero remote API keys are required for scraping, embedding, or text generation. Perfect for secure enterprise workloads.

---

## 🛠️ Tech Stack

* **Frontend**: Vanilla HTML5, Modern CSS3 (Glassmorphism, Neon HSL Gradients), Async ES6 JavaScript (ReadableStream SSE reader)
* **Backend Framework**: Python FastAPI + Uvicorn (Asynchronous, High-Performance Web Server)
* **Scraper Layer**: Async HTTPX client + BeautifulSoup4 html parser
* **Vector Index**: FAISS (`faiss-cpu`) + SentenceTransformer (`all-MiniLM-L6-v2` - 384 dimensions)
* **Relational Database**: SQLite3 (Session, history log, and analytics storage)
* **LLM Engine**: HuggingFace Qwen-2.5-1.5B-Instruct (loaded via AutoModelForCausalLM + TextIteratorStreamer)

---

## 🚀 Setup & Launch Guide

### 1. Prerequisites
Ensure you have Python **3.10+** or **Docker** installed on your system. A GPU with CUDA support is recommended for faster generation speeds, but CPU is fully supported.

### 2. Option A: Running Locally (Bare Metal)

#### Install Dependencies
```bash
pip install -r backend/requirements.txt
```

#### Start the FastAPI Server
From the project root folder, start the Uvicorn server:
```bash
python -m backend.main
```
*Note: On the first launch, the server will download the Qwen-2.5-1.5B-Instruct, NLLB-200, and all-MiniLM-L6-v2 models directly from HuggingFace and cache them locally (approx. 3.2 GB total download). Subsequent startups are nearly instantaneous!*

The server will start running on **`http://localhost:8000`**. 

---

### 3. Option B: Running with Docker (Containerized Deployment)

To deploy the application for a demo or production environment using Docker:

#### Build & Start the Container
Run the following command from the root directory:
```bash
docker compose up --build -d
```

This will:
* Build the WebRAG container image.
* Mount a local directory `./models_cache` to `/app/models_cache` inside the container so models are cached on the host.
* Persist the database `./chatbot.db` and FAISS index `./faiss_index` on the host.
* Start the server on **`http://localhost:8000`**.

#### Stop the Container
```bash
docker compose down
```

---

## 🏃 Accessing the Application
Once the server is running (via Python or Docker), open your browser and navigate to:
👉 **`http://localhost:8000/`**

You will be greeted by the premium glassmorphic interface where you can login, sign up, trigger scrapers, and chat in real-time.

* **Default Admin Credentials:** `admin@webrag.com` / `AdminPassword123!`
* **Interactive API Documentation:** `http://localhost:8000/docs`
