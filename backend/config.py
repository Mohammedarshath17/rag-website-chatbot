import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(dotenv_path=BASE_DIR / ".env")

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
RELOAD = os.getenv("RELOAD", "True").lower() in ("true", "1", "yes")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./chatbot.db")
VECTOR_DB_PATH = os.getenv("VECTOR_DB_PATH", "./faiss_index")

if DATABASE_URL.startswith("sqlite:///./"):
    sqlite_db_name = DATABASE_URL.split("sqlite:///./")[1]
    DATABASE_PATH = str(BASE_DIR / sqlite_db_name)
else:
    DATABASE_PATH = DATABASE_URL

if VECTOR_DB_PATH.startswith("./"):
    VECTOR_DB_ABS_PATH = str(BASE_DIR / VECTOR_DB_PATH[2:])
else:
    VECTOR_DB_ABS_PATH = VECTOR_DB_PATH