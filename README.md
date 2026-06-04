# 🕸️ WebRAG: Premium Local Offline RAG-Powered Website Chatbot

WebRAG is a state-of-the-art, high-performance RAG (Retrieval-Augmented Generation) website chatbot. It crawls and ingests any given website URL, recursively scrapes sub-pages under the same domain, indexes the content chunks into a **FAISS** vector database using a local **`all-MiniLM-L6-v2`** model, and streams answers using the local **`Qwen/Qwen2.5-1.5B-Instruct`** model with sub-second latency.

Because it runs local open-source models, the system is **100% free, runs entirely offline, and respects data privacy**—no user queries or scraped details are ever transmitted to third-party APIs.

---

## ✨ Features

* **Asynchronous Recursive Scraper**: Dynamic concurrent crawler using `httpx` and `BeautifulSoup4` that crawls sub-pages within a domain, ignoring navigation bars, footers, script code, and non-HTML assets.
* **FAISS Vector Database (`faiss-cpu`)**: Highly optimized similarity search indexing on extracted text chunks using the local `all-MiniLM-L6-v2` embedding model.
* **Qwen/Qwen2.5-1.5B-Instruct LLM**: A local, state-of-the-art conversational model loaded via the HuggingFace `transformers` library. It automatically uses CUDA GPU acceleration if available, falling back smoothly to CPU execution.
* **Multi-Language Translation Engine**: Built-in translation pipeline using Facebook's `NLLB-200-distilled-600M` model. Users can ask questions and receive answers in Hindi (`hi`), Tamil (`ta`), Japanese (`ja`), French (`fr`), and many other languages even when the scraped website is in English.
* **Token-by-Token SSE Stream Routing**: streaming response generation using `StreamingResponse` for chat responses, yielding instantaneous chatbot replies.
* **Session and Crawl History**: Relational SQLite3 database that stores session states, message histories, and scrapers statistics (e.g. pages scraped, words indexed).
* **Live Ingestion logs**: Terminal progression screen that streams crawling state changes in real-time.
* **Source Citation Chips**: Provides citation links and search relevance matching percentages for every retrieved chunk.
* **Security & User Lockout System**: Features advanced user security including strong password validation, admin promotions, and temporary account lockout policies after 5 failed login attempts to prevent brute-force attacks.
* **100% Offline Integrity**: Zero remote API keys are required for scraping, embedding, or text generation. Perfect for secure enterprise workloads.

---

## 🏗️ System Architecture

The following diagram illustrates the end-to-end data pipeline of the WebRAG application, showing how web content is crawled, indexed, and retrieved to serve AI-generated, cited responses:

```mermaid
graph TD
    subgraph Client ["Client (Browser Interface)"]
        UI["Glassmorphic HTML5/CSS3/JS UI"]
    end

    subgraph API ["FastAPI Web Server (Uvicorn)"]
        main["main.py (Router & Controllers)"]
        db["database.py (SQLite3 Schema & Queries)"]
    end

    subgraph Core ["Local AI & Indexing Core"]
        scraper["scraper.py (AsyncWebScraper)"]
        embeddings["vector_store.py (SentenceTransformers / all-MiniLM-L6-v2)"]
        faiss["FAISS Vector Index"]
        llm["Qwen-2.5-1.5B-Instruct LLM Engine"]
        translator["translator.py (TranslationEngine / NLLB-200)"]
    end

    UI -->|1. Ingest Request| main
    main -->|Crawl URL| scraper
    scraper -->|HTML Content| main
    main -->|Generate Chunks & Embeddings| embeddings
    embeddings -->|Store Vectors| faiss

    UI -->|2. Chat Query| main
    main -->|Query Translation if needed| translator
    main -->|Semantic Vector Search| faiss
    faiss -->|Top Context Chunks| main
    main -->|Context + History Prompt| llm
    llm -->|Stream Tokens (SSE)| UI

    main -->|Write Stats / Log History| db
    db -->|Store/Retrieve Sessions & Accounts| SQLite[("SQLite Database (chatbot.db)")]
```

### 1. Ingestion Pipeline
* **Crawling**: The `AsyncWebScraper` recursively explores website domains up to a specified depth and page limit.
* **Preprocessing**: Boilerplate elements (navbars, footers, script files) are filtered out, and raw text is split into overlapping chunks (500 words with a 100-word overlap) to maintain contextual coherence.
* **Embedding**: Text chunks are passed to the `all-MiniLM-L6-v2` transformer model to yield 384-dimensional dense vectors.
* **Indexing**: Vectors are indexed in an inner-product FAISS index to run fast Cosine Similarity searches.

### 2. Retrieval & Generation (RAG)
* **Query Expansion**: When a user queries in a non-English language, the query is translated into English using `NLLB-200` to maximize similarity search recall.
* **Retrieval**: The vector database searches for the top 4 most relevant context chunks.
* **Generation**: The retrieved chunks, conversation history, and system instructions are formatted into a prompt and passed to `Qwen-2.5-1.5B-Instruct` to stream a grounded answer.
* **Post-Processing**: If the query was in a foreign language, the generated response is translated back into the source language before outputting to the UI.

---

## 🛠️ Tech Stack

* **Frontend**: Vanilla HTML5, Modern CSS3 (Glassmorphism, Neon HSL Gradients), Async ES6 JavaScript (ReadableStream SSE reader)
* **Backend Framework**: Python FastAPI + Uvicorn (Asynchronous, High-Performance Web Server)
* **Scraper Layer**: Async HTTPX client + BeautifulSoup4 html parser
* **Vector Index**: FAISS (`faiss-cpu`) + SentenceTransformer (`all-MiniLM-L6-v2` - 384 dimensions)
* **Translation Core**: NLLB-200 (`facebook/nllb-200-distilled-600M` - 600M parameters)
* **Relational Database**: SQLite3 (Session, history log, and analytics storage)
* **LLM Engine**: HuggingFace Qwen-2.5-1.5B-Instruct (loaded via AutoModelForCausalLM + TextIteratorStreamer)

---

## 🚀 Setup & Launch Guide

### 1. Prerequisites
Ensure you have Python **3.10+** or **Docker** installed on your system. A GPU with CUDA support is recommended for faster generation speeds, but CPU is fully supported.

### 2. Option A: Running Locally (Bare Metal)

#### Install Dependencies
Make sure you activate your python virtual environment first:
```bash
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```
Then install the packages:
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

---

## 📸 Screenshots & Demos

Below are screenshots and recordings of the running application interface:

### 1. Main Chat Interface
The landing page includes the chat history panel, website crawler interface, and active chat session controls.
![Main Chat Interface](file:///C:/Users/Dell/.gemini/antigravity-ide/brain/ce05bf83-7a54-4a66-8d2b-fc983540e34e/landing_page_1780583059074.png)

### 2. Admin System Dashboard
Accessible via the UI header. Shows database stats, active users count, indexed words metric, and system log exports.
![Admin System Dashboard](file:///C:/Users/Dell/.gemini/antigravity-ide/brain/ce05bf83-7a54-4a66-8d2b-fc983540e34e/admin_dashboard_screenshot_1780583298861.png)

### 3. Interactive Web App Session Demo
The video recording below demonstrates navigating the application, triggering ingestion logs, and browsing the dashboard:
![Interactive Session Demo](file:///C:/Users/Dell/.gemini/antigravity-ide/brain/ce05bf83-7a54-4a66-8d2b-fc983540e34e/webrag_landing_page_1780582992111.webp)
