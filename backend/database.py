import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import sqlite3
import json
from datetime import datetime
from backend.config import DATABASE_PATH

def get_db_connection():
    """Returns a connection to the SQLite database."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes the database schema if tables do not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Chat Sessions Table (with user_email check)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id TEXT PRIMARY KEY,
            url TEXT,
            user_email TEXT,
            created_at TEXT NOT NULL
        )
    """)
    
    # Alter chat_sessions if user_email is missing (backward compatibility)
    cursor.execute("PRAGMA table_info(chat_sessions)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'user_email' not in columns:
        cursor.execute("ALTER TABLE chat_sessions ADD COLUMN user_email TEXT")
    
    # 2. Chat History Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE
        )
    """)
    
    # 3. Crawled Pages Table (for tracking parsed pages and their statistics)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS crawled_pages (
            url TEXT PRIMARY KEY,
            title TEXT,
            word_count INTEGER,
            scraped_at TEXT NOT NULL
        )
    """)
    
    # 4. Users Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            failed_attempts INTEGER DEFAULT 0,
            lock_until TEXT,
            is_admin INTEGER DEFAULT 0,
            is_locked INTEGER DEFAULT 0,
            is_deleted INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    
    # 5. Password History Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            changed_at TEXT NOT NULL,
            FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE
        )
    """)
    
    # 6. Feedback Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            rating INTEGER NOT NULL,
            comments TEXT,
            created_at TEXT NOT NULL
        )
    """)
    
    # 7. System Activity Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_type TEXT NOT NULL,
            detail TEXT,
            created_at TEXT NOT NULL
        )
    """)
    
    conn.commit()
    
    # Insert default admin user if not exists
    cursor.execute("SELECT COUNT(*) FROM users WHERE email = 'admin@webrag.com'")
    if cursor.fetchone()[0] == 0:
        import bcrypt
        pwd = "AdminPassword123!"
        pwd_hash = bcrypt.hashpw(pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        now_str = datetime.utcnow().isoformat()
        cursor.execute("""
            INSERT INTO users (email, username, password_hash, is_admin, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, ('admin@webrag.com', 'admin', pwd_hash, 1, now_str))
        cursor.execute("""
            INSERT INTO password_history (email, password_hash, changed_at)
            VALUES (?, ?, ?)
        """, ('admin@webrag.com', pwd_hash, now_str))
        conn.commit()
        print("Default admin user created successfully.")
        
    conn.close()
    print(f"Database initialized successfully at: {DATABASE_PATH}")

# Session Helper Functions
def create_session(session_id: str, url: str, user_email: str = None) -> bool:
    """Creates a new chat session."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO chat_sessions (session_id, url, user_email, created_at) VALUES (?, ?, ?, ?)",
            (session_id, url, user_email, datetime.utcnow().isoformat())
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_session(session_id: str) -> bool:
    """Deletes a chat session (cascades to chat history if foreign keys are enabled)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def get_session(session_id: str):
    """Retrieves session details by id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM chat_sessions WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_sessions(user_email: str = None):
    """Retrieves list of active sessions filtered by user_email if provided, sorted by creation time."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if user_email:
        cursor.execute("SELECT * FROM chat_sessions WHERE user_email = ? ORDER BY created_at DESC", (user_email,))
    else:
        cursor.execute("SELECT * FROM chat_sessions ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Chat History Helper Functions
def add_chat_message(session_id: str, role: str, content: str):
    """Adds a new message to the chat history of a session."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_history (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (session_id, role, content, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

def get_chat_history(session_id: str):
    """Retrieves all chat messages for a specific session sorted chronologically."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content, created_at FROM chat_history WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Crawled Pages Helper Functions
def log_crawled_page(url: str, title: str, word_count: int):
    """Logs a successfully crawled and processed page."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO crawled_pages (url, title, word_count, scraped_at)
        VALUES (?, ?, ?, ?)
        """,
        (url, title, word_count, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

def get_all_crawled_pages():
    """Retrieves list of all successfully crawled pages."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM crawled_pages ORDER BY scraped_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def clear_crawled_pages():
    """Clears all logged crawled pages (useful on re-scraping/resetting)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM crawled_pages")
    conn.commit()
    conn.close()

# User persistence and security helper functions
def get_user_by_email(email: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_user(email: str, username: str, password_hash: str, is_admin: int = 0) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    try:
        cursor.execute("""
            INSERT INTO users (email, username, password_hash, is_admin, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (email, username, password_hash, is_admin, now_str))
        cursor.execute("""
            INSERT INTO password_history (email, password_hash, changed_at)
            VALUES (?, ?, ?)
        """, (email, password_hash, now_str))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_password_history(email: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM password_history WHERE email = ? ORDER BY changed_at DESC", (email,))
    rows = cursor.fetchall()
    conn.close()
    return [row['password_hash'] for row in rows]

def add_password_history(email: str, password_hash: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO password_history (email, password_hash, changed_at)
            VALUES (?, ?, ?)
        """, (email, password_hash, datetime.utcnow().isoformat()))
        conn.commit()
    finally:
        conn.close()

def increment_failed_attempts(email: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT failed_attempts FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        if row:
            attempts = row['failed_attempts'] + 1
            lock_until = None
            is_locked = 0
            if attempts >= 3:
                is_locked = 1
                from datetime import timedelta
                lock_until = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
            cursor.execute(
                "UPDATE users SET failed_attempts = ?, is_locked = ?, lock_until = ? WHERE email = ?",
                (attempts, is_locked, lock_until, email)
            )
            conn.commit()
    finally:
        conn.close()

def reset_failed_attempts(email: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET failed_attempts = 0, is_locked = 0, lock_until = NULL WHERE email = ?",
            (email,)
        )
        conn.commit()
    finally:
        conn.close()

def lock_user_account(email: str, lock_until: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET is_locked = 1, lock_until = ? WHERE email = ?",
            (lock_until, email)
        )
        conn.commit()
    finally:
        conn.close()

def toggle_user_lock(email: str, is_locked: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET is_locked = ?, failed_attempts = 0, lock_until = NULL WHERE email = ?",
            (is_locked, email)
        )
        conn.commit()
    finally:
        conn.close()

def promote_user_to_admin(email: str, is_admin: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET is_admin = ? WHERE email = ?",
            (is_admin, email)
        )
        conn.commit()
    finally:
        conn.close()

def delete_user_account(email: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET is_deleted = 1 WHERE email = ?",
            (email,)
        )
        conn.commit()
    finally:
        conn.close()

def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT email, username, is_admin, is_locked, is_deleted, created_at FROM users WHERE is_deleted = 0 ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Feedback helpers
def log_feedback(user_email: str, rating: int, comments: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO feedback (user_email, rating, comments, created_at) VALUES (?, ?, ?, ?)",
            (user_email, rating, comments, datetime.utcnow().isoformat())
        )
        conn.commit()
    finally:
        conn.close()

def get_all_feedback():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM feedback ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# System Activity log helpers
def log_system_activity(activity_type: str, detail: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO system_activity (activity_type, detail, created_at) VALUES (?, ?, ?)",
            (activity_type, detail, datetime.utcnow().isoformat())
        )
        conn.commit()
    finally:
        conn.close()

def get_activity_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    stats = {}
    
    # Invoked languages (translation activities)
    cursor.execute("SELECT detail, COUNT(*) as count FROM system_activity WHERE activity_type = 'translation' GROUP BY detail")
    stats['languages'] = {row['detail']: row['count'] for row in cursor.fetchall()}
    
    # Model query counts (chat activities)
    cursor.execute("SELECT detail, COUNT(*) as count FROM system_activity WHERE activity_type = 'chat_query' GROUP BY detail")
    stats['model_queries'] = {row['detail']: row['count'] for row in cursor.fetchall()}
    
    # Feature hits
    cursor.execute("SELECT detail, COUNT(*) as count FROM system_activity WHERE activity_type = 'feature_hit' GROUP BY detail")
    stats['feature_hits'] = {row['detail']: row['count'] for row in cursor.fetchall()}
    
    conn.close()
    return stats

def get_general_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Locked accounts count
    now_str = datetime.utcnow().isoformat()
    cursor.execute("SELECT COUNT(*) FROM users WHERE (is_locked = 1 OR (lock_until IS NOT NULL AND lock_until > ?)) AND is_deleted = 0", (now_str,))
    locked_count = cursor.fetchone()[0]
    
    # Total active users (not deleted)
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_deleted = 0")
    user_count = cursor.fetchone()[0]
    
    # Total crawled pages and word count
    cursor.execute("SELECT COUNT(*), SUM(word_count) FROM crawled_pages")
    crawled_row = cursor.fetchone()
    pages_count = crawled_row[0] or 0
    words_count = crawled_row[1] or 0
    
    # Total active chat sessions
    cursor.execute("SELECT COUNT(*) FROM chat_sessions")
    sessions_count = cursor.fetchone()[0]
    
    conn.close()
    return {
        "total_users": user_count,
        "locked_accounts": locked_count,
        "total_pages": pages_count,
        "total_words": words_count,
        "active_sessions": sessions_count
    }

# Initialize tables automatically when this file is imported
init_db()
