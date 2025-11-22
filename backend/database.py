import sqlite3
from typing import Optional, Dict, Any
from contextlib import contextmanager
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "vibecaster.db")


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database():
    """Initialize database tables if they don't exist."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                is_active INTEGER DEFAULT 1
            )
        """)

        # Create secrets table for OAuth tokens (updated with user_id FK)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS secrets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                service TEXT NOT NULL,
                access_token TEXT,
                refresh_token TEXT,
                platform_user_id TEXT,
                expires_at INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, service)
            )
        """)

        # Create campaign table for user configuration (updated with user_id FK)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS campaign (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_prompt TEXT,
                refined_persona TEXT,
                visual_style TEXT,
                schedule_cron TEXT DEFAULT '0 9 * * *',
                last_run INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id)
            )
        """)

        conn.commit()


# User table operations
def create_user(email: str, hashed_password: str) -> int:
    """Create a new user and return their ID."""
    import time
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (email, hashed_password, created_at)
            VALUES (?, ?, ?)
        """, (email, hashed_password, int(time.time())))
        return cursor.lastrowid


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Retrieve a user by email."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve a user by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


# Secrets table operations
def save_oauth_tokens(user_id: int, service: str, access_token: str, refresh_token: Optional[str] = None,
                     platform_user_id: Optional[str] = None, expires_at: Optional[int] = None):
    """Save or update OAuth tokens for a service."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO secrets
            (user_id, service, access_token, refresh_token, platform_user_id, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, service, access_token, refresh_token, platform_user_id, expires_at))


def get_oauth_tokens(user_id: int, service: str) -> Optional[Dict[str, Any]]:
    """Retrieve OAuth tokens for a service."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM secrets WHERE user_id = ? AND service = ?", (user_id, service))
        row = cursor.fetchone()
        return dict(row) if row else None


def delete_oauth_tokens(user_id: int, service: str):
    """Delete OAuth tokens for a service."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM secrets WHERE user_id = ? AND service = ?", (user_id, service))


# Campaign table operations
def update_campaign(user_id: int, user_prompt: Optional[str] = None, refined_persona: Optional[str] = None,
                   visual_style: Optional[str] = None, schedule_cron: Optional[str] = None):
    """Update or create campaign configuration for a user."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Check if campaign exists
        cursor.execute("SELECT id FROM campaign WHERE user_id = ?", (user_id,))
        campaign = cursor.fetchone()

        if campaign:
            # Update existing campaign
            updates = []
            params = []

            if user_prompt is not None:
                updates.append("user_prompt = ?")
                params.append(user_prompt)
            if refined_persona is not None:
                updates.append("refined_persona = ?")
                params.append(refined_persona)
            if visual_style is not None:
                updates.append("visual_style = ?")
                params.append(visual_style)
            if schedule_cron is not None:
                updates.append("schedule_cron = ?")
                params.append(schedule_cron)

            if updates:
                query = f"UPDATE campaign SET {', '.join(updates)} WHERE user_id = ?"
                params.append(user_id)
                cursor.execute(query, params)
        else:
            # Create new campaign
            cursor.execute("""
                INSERT INTO campaign (user_id, user_prompt, refined_persona, visual_style, schedule_cron)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, user_prompt or "", refined_persona or "", visual_style or "", schedule_cron or "0 9 * * *"))


def get_campaign(user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve campaign configuration for a user."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM campaign WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_last_run(user_id: int, timestamp: int):
    """Update the last run timestamp for a user."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE campaign SET last_run = ? WHERE user_id = ?", (timestamp, user_id))


def get_connection_status(user_id: int) -> Dict[str, bool]:
    """Check which services are connected for a user."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT service FROM secrets WHERE user_id = ?", (user_id,))
        connected_services = {row[0] for row in cursor.fetchall()}

        return {
            "twitter": "twitter" in connected_services,
            "linkedin": "linkedin" in connected_services
        }
