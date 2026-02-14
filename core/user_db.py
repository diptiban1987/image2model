"""
Simple SQLite User Database for Web App

Handles:
- User accounts
- Trial tracking per user
- License keys per user

Note: This is for the WEB APP only - desktop app uses hardware fingerprinting.
"""

import sqlite3
import os
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

DB_PATH = Path("config/users.db")


def get_db_connection():
    """Get database connection, create tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    _init_tables(conn)
    return conn


def _init_tables(conn: sqlite3.Connection):
    """Initialize database tables."""
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0
        )
    """)
    
    # User trials table - tracks trial per user
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_trials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            generations_used INTEGER DEFAULT 0,
            generations_remaining INTEGER DEFAULT 1,
            first_used_at TEXT,
            last_used_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    # User licenses table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            license_key TEXT NOT NULL,
            plan_id TEXT,
            credits INTEGER DEFAULT 0,
            activated_at TEXT NOT NULL,
            expires_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    conn.commit()


def _hash_password(password: str) -> str:
    """Hash password using SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()


def create_user(username: str, password: str, is_admin: bool = False) -> bool:
    """Create a new user. Returns True if successful."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash, created_at, is_admin) VALUES (?, ?, ?, ?)",
            (username, _hash_password(password), datetime.utcnow().isoformat(), 1 if is_admin else 0)
        )
        user_id = cursor.lastrowid
        
        # Initialize trial for new user
        cursor.execute(
            "INSERT INTO user_trials (user_id, generations_used, generations_remaining) VALUES (?, 0, 1)",
            (user_id,)
        )
        
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def verify_user(username: str, password: str) -> Optional[int]:
    """Verify user credentials. Returns user_id if valid, None otherwise."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, is_admin FROM users WHERE username = ? AND password_hash = ?",
            (username, _hash_password(password))
        )
        row = cursor.fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user by ID."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, created_at, is_admin FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Get user by username."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, created_at, is_admin FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# Trial Management
def get_user_trial(user_id: int) -> Dict[str, Any]:
    """Get trial status for a user."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT generations_used, generations_remaining, first_used_at, last_used_at FROM user_trials WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        else:
            # Initialize trial if not exists
            cursor.execute(
                "INSERT INTO user_trials (user_id, generations_used, generations_remaining) VALUES (?, 0, 1)",
                (user_id,)
            )
            conn.commit()
            return {
                "generations_used": 0,
                "generations_remaining": 1,
                "first_used_at": None,
                "last_used_at": None
            }
    finally:
        conn.close()


def use_user_trial(user_id: int) -> bool:
    """Use one trial generation. Returns True if successful."""
    trial = get_user_trial(user_id)
    if trial["generations_remaining"] <= 0:
        return False
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        
        # Check if first use
        if trial["generations_used"] == 0:
            cursor.execute(
                "UPDATE user_trials SET generations_used = generations_used + 1, generations_remaining = generations_remaining - 1, first_used_at = ?, last_used_at = ? WHERE user_id = ?",
                (now, now, user_id)
            )
        else:
            cursor.execute(
                "UPDATE user_trials SET generations_used = generations_used + 1, generations_remaining = generations_remaining - 1, last_used_at = ? WHERE user_id = ?",
                (now, user_id)
            )
        
        conn.commit()
        return True
    finally:
        conn.close()


def has_trial_available(user_id: int) -> bool:
    """Check if user has trial available."""
    trial = get_user_trial(user_id)
    return trial["generations_remaining"] > 0


# License Management
def get_user_license(user_id: int) -> Optional[Dict[str, Any]]:
    """Get license for a user."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT license_key, plan_id, credits, activated_at, expires_at FROM user_licenses WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def add_user_license(user_id: int, license_key: str, plan_id: str = "pro", credits: int = 300, expires_at: str = None):
    """Add a license for a user."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_licenses (user_id, license_key, plan_id, credits, activated_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, license_key, plan_id, credits, datetime.utcnow().isoformat(), expires_at)
        )
        conn.commit()
    finally:
        conn.close()


def has_valid_license(user_id: int) -> bool:
    """Check if user has a valid license."""
    license = get_user_license(user_id)
    if not license:
        return False
    
    # Check expiration if set
    if license["expires_at"]:
        expires = datetime.fromisoformat(license["expires_at"])
        if datetime.utcnow() > expires:
            return False
    
    return True


def get_user_credits(user_id: int) -> int:
    """Get remaining credits for user."""
    license = get_user_license(user_id)
    return license["credits"] if license else 0


def deduct_user_credits(user_id: int, amount: int) -> bool:
    """Deduct credits from user. Returns True if successful."""
    if not has_valid_license(user_id):
        return False
    
    credits = get_user_credits(user_id)
    if credits < amount:
        return False
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE user_licenses SET credits = credits - ? WHERE user_id = ?",
            (amount, user_id)
        )
        conn.commit()
        return True
    finally:
        conn.close()


# Check if admin exists
def admin_exists() -> bool:
    """Check if an admin user exists."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
        return cursor.fetchone()[0] > 0
    finally:
        conn.close()


def get_all_users() -> list:
    """Get all users (for admin)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.username, u.created_at, u.is_admin,
                   t.generations_used, t.generations_remaining,
                   l.plan_id, l.credits, l.expires_at
            FROM users u
            LEFT JOIN user_trials t ON u.id = t.user_id
            LEFT JOIN user_licenses l ON u.id = l.user_id
            ORDER BY u.id
        """)
        rows = cursor.fetchall()
        users = []
        for row in rows:
            users.append({
                "id": row[0],
                "username": row[1],
                "created_at": row[2],
                "is_admin": bool(row[3]),
                "generations_used": row[4] or 0,
                "generations_remaining": row[5] or 0,
                "plan_id": row[6],
                "credits": row[7] or 0,
                "expires_at": row[8],
            })
        return users
    finally:
        conn.close()


def delete_user(user_id: int) -> bool:
    """Delete a user (for admin)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_licenses WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM user_trials WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM users WHERE id = ? AND is_admin = 0", (user_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def update_user_password(username: str, new_password: str) -> bool:
    """Update user password."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (_hash_password(new_password), username)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def reset_user_trial(user_id: int) -> bool:
    """Reset trial for a user (for admin)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE user_trials SET generations_used = 0, generations_remaining = 1, first_used_at = NULL, last_used_at = NULL WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def is_user_admin(user_id: int) -> bool:
    """Check if user is admin."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return bool(row[0]) if row else False
    finally:
        conn.close()
