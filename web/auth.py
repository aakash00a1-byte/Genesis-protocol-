"""Genesis Protocol - Authentication System

Complete auth with:
- Login/Registration
- Password reset
- Email verification
- Session security
- Profile management
"""

import os
import sys
import sqlite3
import secrets
import hashlib
import re
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Dict, Any, Tuple

from flask import Flask, request, jsonify, session, render_template, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

# Import from main app
DATABASE = 'genesis.db'


class AuthManager:
    """Central authentication manager."""
    
    def __init__(self, db_path: str = DATABASE):
        self.db_path = db_path
        self._init_auth_tables()
    
    def _get_db(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_auth_tables(self):
        """Initialize authentication tables."""
        conn = self._get_db()
        cursor = conn.cursor()
        
        # Users table (enhanced)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                is_verified INTEGER DEFAULT 0,
                usage_count INTEGER DEFAULT 0,
                theme TEXT DEFAULT 'dark',
                language TEXT DEFAULT 'en',
                settings TEXT DEFAULT '{}'
            )
        ''')
        
        # Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_token TEXT UNIQUE NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Password reset tokens
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                used INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Email verification tokens
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_verifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                verified INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Login attempts (for rate limiting)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT NOT NULL,
                username TEXT,
                success INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create default admin if not exists
        cursor.execute('SELECT id FROM users WHERE role = "admin"')
        if not cursor.fetchone():
            admin_hash = generate_password_hash(
                os.environ.get('ADMIN_PASSWORD', secrets.token_urlsafe(16))
            )
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, role, is_verified)
                VALUES (?, ?, ?, ?, ?)
            ''', ('admin', 'admin@genesis.ai', admin_hash, 'admin', 1))
        
        conn.commit()
        conn.close()
    
    # ============ User Management ============
    
    def create_user(self, username: str, email: str, password: str) -> Tuple[bool, str, Optional[int]]:
        """Create new user account."""
        # Validate inputs
        if not self._validate_username(username):
            return False, "Username must be 3-20 characters, alphanumeric and underscore only", None
        
        if not self._validate_email(email):
            return False, "Invalid email address", None
        
        if not self._validate_password(password):
            return False, "Password must be at least 8 characters with uppercase, lowercase, and number", None
        
        try:
            conn = self._get_db()
            cursor = conn.cursor()
            
            # Check if username or email exists
            cursor.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email))
            if cursor.fetchone():
                return False, "Username or email already exists", None
            
            # Create user
            password_hash = generate_password_hash(password)
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, is_verified)
                VALUES (?, ?, ?, ?)
            ''', (username, email, password_hash, 0))
            
            user_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return True, "User created successfully", user_id
            
        except Exception as e:
            return False, str(e), None
    
    def authenticate(self, username: str, password: str, ip_address: str = None, 
                    user_agent: str = None) -> Tuple[bool, str, Optional[Dict]]:
        """Authenticate user and create session."""
        # Check rate limiting
        if ip_address and self._is_rate_limited(ip_address):
            return False, "Too many login attempts. Please try again later.", None
        
        conn = self._get_db()
        cursor = conn.cursor()
        
        # Get user
        cursor.execute('''
            SELECT id, username, email, password_hash, role, is_active, is_verified
            FROM users WHERE username = ?
        ''', (username,))
        user = cursor.fetchone()
        
        # Log attempt
        self._log_login_attempt(ip_address, username, user is not None and 
                               check_password_hash(user['password_hash'], password) if user else False)
        
        if not user:
            conn.close()
            return False, "Invalid username or password", None
        
        if not user['is_active']:
            conn.close()
            return False, "Account is disabled", None
        
        if not check_password_hash(user['password_hash'], password):
            conn.close()
            return False, "Invalid username or password", None
        
        # Create session
        session_token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=7)
        
        cursor.execute('''
            INSERT INTO sessions (user_id, session_token, ip_address, user_agent, expires_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (user['id'], session_token, ip_address, user_agent, expires_at))
        
        # Update last login
        cursor.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user['id'],))
        
        conn.commit()
        conn.close()
        
        return True, "Login successful", {
            'user_id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'role': user['role'],
            'session_token': session_token,
            'is_verified': user['is_verified']
        }
    
    def verify_session(self, session_token: str) -> Optional[Dict]:
        """Verify session token and return user data."""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT s.*, u.username, u.email, u.role, u.is_active, u.is_verified, u.theme, u.settings
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.session_token = ? AND s.is_active = 1 AND s.expires_at > CURRENT_TIMESTAMP
        ''', (session_token,))
        
        session_data = cursor.fetchone()
        
        if not session_data:
            conn.close()
            return None
        
        # Update last activity
        cursor.execute('UPDATE sessions SET last_activity = CURRENT_TIMESTAMP WHERE id = ?', 
                      (session_data['id'],))
        conn.commit()
        conn.close()
        
        return {
            'user_id': session_data['user_id'],
            'username': session_data['username'],
            'email': session_data['email'],
            'role': session_data['role'],
            'is_active': session_data['is_active'],
            'is_verified': session_data['is_verified'],
            'theme': session_data['theme'],
            'settings': session_data['settings']
        }
    
    def logout(self, session_token: str) -> bool:
        """Logout user by invalidating session."""
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE sessions SET is_active = 0 WHERE session_token = ?', (session_token,))
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0
    
    def logout_all(self, user_id: int) -> int:
        """Logout user from all sessions."""
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE sessions SET is_active = 0 WHERE user_id = ?', (user_id,))
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected
    
    # ============ Password Reset ============
    
    def create_password_reset(self, email: str) -> Tuple[bool, str, Optional[str]]:
        """Create password reset token."""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        
        if not user:
            # Don't reveal if email exists
            return True, "If the email exists, a reset link has been sent", None
        
        # Create token
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=1)
        
        # Invalidate old tokens
        cursor.execute('UPDATE password_resets SET used = 1 WHERE user_id = ?', (user['id'],))
        
        cursor.execute('''
            INSERT INTO password_resets (user_id, token, expires_at)
            VALUES (?, ?, ?)
        ''', (user['id'], token, expires_at))
        
        conn.commit()
        conn.close()
        
        return True, "Password reset token created", token
    
    def reset_password(self, token: str, new_password: str) -> Tuple[bool, str]:
        """Reset password using token."""
        if not self._validate_password(new_password):
            return False, "Password must be at least 8 characters with uppercase, lowercase, and number"
        
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id FROM password_resets 
            WHERE token = ? AND used = 0 AND expires_at > CURRENT_TIMESTAMP
        ''', (token,))
        reset = cursor.fetchone()
        
        if not reset:
            conn.close()
            return False, "Invalid or expired reset token"
        
        # Update password
        password_hash = generate_password_hash(new_password)
        cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', 
                      (password_hash, reset['user_id']))
        
        # Mark token as used
        cursor.execute('UPDATE password_resets SET used = 1 WHERE token = ?', (token,))
        
        # Logout from all sessions
        cursor.execute('UPDATE sessions SET is_active = 0 WHERE user_id = ?', (reset['user_id'],))
        
        conn.commit()
        conn.close()
        
        return True, "Password reset successfully"
    
    # ============ Email Verification ============
    
    def create_verification(self, user_id: int) -> Tuple[bool, str, Optional[str]]:
        """Create email verification token."""
        conn = self._get_db()
        cursor = conn.cursor()
        
        # Check if already verified
        cursor.execute('SELECT is_verified FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        
        if user and user['is_verified']:
            conn.close()
            return True, "Email already verified", None
        
        # Create token
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=1)
        
        cursor.execute('''
            INSERT INTO email_verifications (user_id, token, expires_at)
            VALUES (?, ?, ?)
        ''', (user_id, token, expires_at))
        
        conn.commit()
        conn.close()
        
        return True, "Verification token created", token
    
    def verify_email(self, token: str) -> Tuple[bool, str]:
        """Verify email using token."""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id FROM email_verifications 
            WHERE token = ? AND verified = 0 AND expires_at > CURRENT_TIMESTAMP
        ''', (token,))
        verification = cursor.fetchone()
        
        if not verification:
            conn.close()
            return False, "Invalid or expired verification token"
        
        # Mark as verified
        cursor.execute('UPDATE users SET is_verified = 1 WHERE id = ?', (verification['user_id'],))
        cursor.execute('UPDATE email_verifications SET verified = 1 WHERE token = ?', (token,))
        
        conn.commit()
        conn.close()
        
        return True, "Email verified successfully"
    
    # ============ User Profile ============
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user profile."""
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, email, role, created_at, last_login, 
                   is_active, is_verified, usage_count, theme, language, settings
            FROM users WHERE id = ?
        ''', (user_id,))
        user = cursor.fetchone()
        conn.close()
        
        return dict(user) if user else None
    
    def update_user(self, user_id: int, updates: Dict) -> Tuple[bool, str]:
        """Update user profile."""
        allowed_fields = ['theme', 'language', 'settings']
        filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}
        
        if not filtered_updates:
            return False, "No valid fields to update"
        
        conn = self._get_db()
        cursor = conn.cursor()
        
        for key, value in filtered_updates.items():
            cursor.execute(f'UPDATE users SET {key} = ? WHERE id = ?', (str(value), user_id))
        
        conn.commit()
        conn.close()
        
        return True, "User updated successfully"
    
    def change_password(self, user_id: int, old_password: str, new_password: str) -> Tuple[bool, str]:
        """Change user password."""
        if not self._validate_password(new_password):
            return False, "Password must be at least 8 characters with uppercase, lowercase, and number"
        
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT password_hash FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        
        if not user or not check_password_hash(user['password_hash'], old_password):
            conn.close()
            return False, "Current password is incorrect"
        
        password_hash = generate_password_hash(new_password)
        cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, user_id))
        
        conn.commit()
        conn.close()
        
        return True, "Password changed successfully"
    
    # ============ Validation Helpers ============
    
    def _validate_username(self, username: str) -> bool:
        """Validate username format."""
        if not username or len(username) < 3 or len(username) > 20:
            return False
        return bool(re.match(r'^[a-zA-Z0-9_]+$', username))
    
    def _validate_email(self, email: str) -> bool:
        """Validate email format."""
        if not email:
            return False
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def _validate_password(self, password: str) -> bool:
        """Validate password strength."""
        if not password or len(password) < 8:
            return False
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        return has_upper and has_lower and has_digit
    
    def _is_rate_limited(self, ip_address: str, max_attempts: int = 5, 
                        window_minutes: int = 15) -> bool:
        """Check if IP is rate limited."""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) FROM login_attempts 
            WHERE ip_address = ? AND success = 0 
            AND created_at > datetime('now', '-' || ? || ' minutes')
        ''', (ip_address, window_minutes))
        
        count = cursor.fetchone()[0]
        conn.close()
        
        return count >= max_attempts
    
    def _log_login_attempt(self, ip_address: str, username: str, success: bool):
        """Log login attempt."""
        if not ip_address:
            return
        
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO login_attempts (ip_address, username, success)
            VALUES (?, ?, ?)
        ''', (ip_address, username, 1 if success else 0))
        conn.commit()
        conn.close()
    
    # ============ Admin Functions ============
    
    def get_all_users(self, limit: int = 100, offset: int = 0) -> list:
        """Get all users (admin)."""
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, email, role, created_at, last_login, 
                   is_active, is_verified, usage_count
            FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?
        ''', (limit, offset))
        users = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return users
    
    def toggle_user_status(self, user_id: int) -> bool:
        """Toggle user active status (admin)."""
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_active = NOT is_active WHERE id = ?', (user_id,))
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0
    
    def get_user_sessions(self, user_id: int) -> list:
        """Get active sessions for user."""
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, ip_address, user_agent, created_at, last_activity, expires_at
            FROM sessions WHERE user_id = ? AND is_active = 1
            ORDER BY last_activity DESC
        ''', (user_id,))
        sessions = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return sessions
    
    def delete_session(self, session_id: int) -> bool:
        """Delete specific session."""
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE sessions SET is_active = 0 WHERE id = ?', (session_id,))
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected > 0


# Singleton instance
_auth_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    """Get auth manager singleton."""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager