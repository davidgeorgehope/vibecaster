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
                include_links INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id)
            )
        """)

        # Create post_history table to track covered topics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS post_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                post_text TEXT NOT NULL,
                topics_json TEXT,
                created_at INTEGER NOT NULL,
                platforms TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Migration: Add include_links column to existing campaign tables
        cursor.execute("PRAGMA table_info(campaign)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'include_links' not in columns:
            cursor.execute("ALTER TABLE campaign ADD COLUMN include_links INTEGER DEFAULT 0")
            print("Migration: Added include_links column to campaign table")

        # Migration: Add is_admin column to users table
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'is_admin' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
            print("Migration: Added is_admin column to users table")

        # Set admin flag for the admin email
        cursor.execute("""
            UPDATE users SET is_admin = 1 WHERE email = 'email.djhope@gmail.com'
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
                   visual_style: Optional[str] = None, schedule_cron: Optional[str] = None, include_links: Optional[bool] = None):
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
            if include_links is not None:
                updates.append("include_links = ?")
                params.append(1 if include_links else 0)

            if updates:
                query = f"UPDATE campaign SET {', '.join(updates)} WHERE user_id = ?"
                params.append(user_id)
                cursor.execute(query, params)
        else:
            # Create new campaign
            cursor.execute("""
                INSERT INTO campaign (user_id, user_prompt, refined_persona, visual_style, schedule_cron, include_links)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, user_prompt or "", refined_persona or "", visual_style or "", schedule_cron or "0 9 * * *", 1 if include_links else 0))


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


# Post history operations
def save_post_history(user_id: int, post_text: str, topics: list, platforms: list):
    """Save post history with extracted topics."""
    import json
    import time

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO post_history (user_id, post_text, topics_json, created_at, platforms)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, post_text, json.dumps(topics), int(time.time()), json.dumps(platforms)))


def get_recent_topics(user_id: int, days: int = 14) -> list:
    """Get all topics covered in the last N days."""
    import json
    import time

    cutoff_time = int(time.time()) - (days * 24 * 60 * 60)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT topics_json FROM post_history
            WHERE user_id = ? AND created_at >= ?
            ORDER BY created_at DESC
        """, (user_id, cutoff_time))

        all_topics = []
        for row in cursor.fetchall():
            if row[0]:
                topics = json.loads(row[0])
                all_topics.extend(topics)

        return all_topics


# ===== ADMIN FUNCTIONS =====

def is_user_admin(user_id: int) -> bool:
    """Check if a user has admin privileges."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return bool(row and row[0])


def get_all_users(page: int = 1, per_page: int = 20) -> dict:
    """Get paginated users for admin view."""
    offset = (page - 1) * per_page
    with get_db() as conn:
        cursor = conn.cursor()
        # Get total count
        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]
        # Get paginated results
        cursor.execute("""
            SELECT id, email, created_at, is_active, is_admin
            FROM users
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (per_page, offset))
        users = [dict(row) for row in cursor.fetchall()]
        return {
            "items": users,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page
        }


def get_all_campaigns(page: int = 1, per_page: int = 20) -> dict:
    """Get paginated campaigns with user info for admin view."""
    offset = (page - 1) * per_page
    with get_db() as conn:
        cursor = conn.cursor()
        # Get total count
        cursor.execute("SELECT COUNT(*) FROM campaign")
        total = cursor.fetchone()[0]
        # Get paginated results
        cursor.execute("""
            SELECT c.*, u.email
            FROM campaign c
            JOIN users u ON c.user_id = u.id
            ORDER BY c.id DESC
            LIMIT ? OFFSET ?
        """, (per_page, offset))
        campaigns = [dict(row) for row in cursor.fetchall()]
        return {
            "items": campaigns,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page
        }


def get_all_posts(page: int = 1, per_page: int = 20) -> dict:
    """Get paginated posts across all users for admin view."""
    import json
    offset = (page - 1) * per_page
    with get_db() as conn:
        cursor = conn.cursor()
        # Get total count
        cursor.execute("SELECT COUNT(*) FROM post_history")
        total = cursor.fetchone()[0]
        # Get paginated results
        cursor.execute("""
            SELECT p.*, u.email
            FROM post_history p
            JOIN users u ON p.user_id = u.id
            ORDER BY p.created_at DESC
            LIMIT ? OFFSET ?
        """, (per_page, offset))
        posts = []
        for row in cursor.fetchall():
            post = dict(row)
            # Parse JSON fields
            if post.get('topics_json'):
                post['topics'] = json.loads(post['topics_json'])
            if post.get('platforms'):
                post['platforms'] = json.loads(post['platforms'])
            posts.append(post)
        return {
            "items": posts,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page
        }


def get_admin_stats() -> dict:
    """Get admin dashboard statistics."""
    import time
    today_start = int(time.time()) - (int(time.time()) % 86400)

    with get_db() as conn:
        cursor = conn.cursor()

        # Total users
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        # Active users (with campaigns)
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM campaign WHERE user_prompt IS NOT NULL AND user_prompt != ''")
        active_campaigns = cursor.fetchone()[0]

        # Posts today
        cursor.execute("SELECT COUNT(*) FROM post_history WHERE created_at >= ?", (today_start,))
        posts_today = cursor.fetchone()[0]

        # Total posts
        cursor.execute("SELECT COUNT(*) FROM post_history")
        total_posts = cursor.fetchone()[0]

        # Connected platforms
        cursor.execute("SELECT service, COUNT(*) FROM secrets GROUP BY service")
        connections = {row[0]: row[1] for row in cursor.fetchall()}

        return {
            "total_users": total_users,
            "active_campaigns": active_campaigns,
            "posts_today": posts_today,
            "total_posts": total_posts,
            "twitter_connections": connections.get("twitter", 0),
            "linkedin_connections": connections.get("linkedin", 0)
        }
