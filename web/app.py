"""
Genesis Protocol - Web Application Backend

Flask-based web server with authentication and AI chat API.
Channel isolation: Web users ONLY receive web responses.
"""

import os
import sys
import json
import hmac
import hashlib
import logging
import time
import threading
import contextlib
import errno
import fcntl
import tempfile
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify, session, render_template, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

# Import channel isolation
from genesis_protocol.core.channel import Channel, get_channel_isolation
from web import security_config

# ============================================================================
# VERSION & METRICS
# ============================================================================
VERSION = "1.1.0"
BUILD_DATE = "2026-06-20"
START_TIME = time.time()

# Metrics (thread-safe counters)
_metrics_lock = threading.Lock()
_metrics = {
    'request_count': 0,
    'error_count': 0,
    'total_latency_ms': 0,
    'provider_latency': {},  # {'groq': [latencies]}
}

def increment_metric(name: str, value: int = 1):
    """Thread-safe metric increment."""
    with _metrics_lock:
        _metrics[name] = _metrics.get(name, 0) + value

def record_latency(provider: str, latency_ms: float):
    """Record provider latency."""
    with _metrics_lock:
        _metrics['total_latency_ms'] += latency_ms
        if provider not in _metrics['provider_latency']:
            _metrics['provider_latency'][provider] = []
        _metrics['provider_latency'][provider].append(latency_ms)
        # Keep last 100 latencies per provider
        if len(_metrics['provider_latency'][provider]) > 100:
            _metrics['provider_latency'][provider] = _metrics['provider_latency'][provider][-100:]

def get_metrics() -> Dict[str, Any]:
    """Get current metrics snapshot."""
    with _metrics_lock:
        m = _metrics.copy()
        m['uptime_seconds'] = time.time() - START_TIME
        
        # Calculate average latencies
        if m['provider_latency']:
            avg_latencies = {
                p: sum(vals) / len(vals) if vals else 0 
                for p, vals in m['provider_latency'].items()
            }
            m['avg_provider_latency'] = avg_latencies
        else:
            m['avg_provider_latency'] = {}
        
        if m['request_count'] > 0:
            m['avg_latency_ms'] = m['total_latency_ms'] / m['request_count']
        else:
            m['avg_latency_ms'] = 0
            
        return m

# Initialize Flask app
app = Flask(__name__, 
            template_folder='templates',
            static_folder='static')
app.secret_key = security_config.resolve_secret_key()
app.permanent_session_lifetime = timedelta(days=7)

# Validate the token-signing secret at import so a misconfigured production
# deploy fails fast instead of at the first login. Resolution stays lazy (see
# _token_signing_key) so a rotation takes effect without a restart.
security_config.resolve_mobile_token_secret()

# Mobile Bearer tokens are HMAC-signed so the server can verify it issued them.
# A token that only *looks* like "genesis_mobile_{id}_{ts}_{sig}" must not
# authenticate anyone: without a valid signature, naming another user's id is
# enough to act as that user.


def _token_signing_key() -> bytes:
    """Resolve the HMAC key for mobile tokens.

    Production requires a dedicated, strong GENESIS_MOBILE_TOKEN_SECRET; a
    missing one raises at import so the app fails closed rather than signing
    with a guessable key.
    """
    return security_config.resolve_mobile_token_secret().encode()


# Mobile tokens expire. The window is short enough to bound a leaked token and
# long enough for a normal app session.
MOBILE_TOKEN_TTL_SECONDS = int(os.environ.get('GENESIS_MOBILE_TOKEN_TTL', 7 * 24 * 3600))

# Token invalidation epoch. A token is only accepted if it was issued strictly
# after the user's epoch, so revocation (logout, deactivation) and a global
# secret rotation move the epoch forward and invalidate every token minted
# earlier. The epoch is persisted in the database so revocation survives a
# restart; an in-memory cache keeps the common read path off the database.
_token_epochs: dict[int, int] = {}
_epoch_lock = threading.Lock()
_global_epoch = 0


def _epoch_from_db(user_id: int) -> "int | None":
    """Read a persisted revocation epoch, or None if absent/unreadable."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT invalid_before FROM token_epochs WHERE user_id = ?', (user_id,)
        )
        row = cursor.fetchone()
        conn.close()
    except sqlite3.Error:
        return None
    return int(row['invalid_before']) if row is not None else None


def _token_epoch(user_id: int) -> int:
    """Return the user's revocation epoch, preferring the durable value."""
    stored = _epoch_from_db(user_id)
    if stored is not None:
        return stored
    with _epoch_lock:
        return _token_epochs.get(user_id, 0)


def _global_token_epoch() -> int:
    """Return the global revocation epoch, preferring the durable value."""
    stored = _epoch_from_db(-1)
    return stored if stored is not None else _global_epoch


def invalidate_user_tokens(user_id: int) -> int:
    """Revoke every mobile token for ``user_id`` issued before now.

    Persisted so the revocation outlives the process.
    """
    epoch = int(time.time())
    with _epoch_lock:
        _token_epochs[user_id] = epoch
    try:
        conn = get_db()
        conn.execute(
            'INSERT INTO token_epochs (user_id, invalid_before) VALUES (?, ?) '
            'ON CONFLICT(user_id) DO UPDATE SET invalid_before = excluded.invalid_before',
            (user_id, epoch),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error:
        logger.warning("Token revocation for user %s could not be persisted", user_id)
    return epoch


def rotate_token_epoch() -> None:
    """Invalidate all outstanding mobile tokens after a secret rotation."""
    global _global_epoch
    now = int(time.time())
    with _epoch_lock:
        _global_epoch = now
        for uid in list(_token_epochs):
            _token_epochs[uid] = now
    try:
        conn = get_db()
        conn.execute(
            'INSERT INTO token_epochs (user_id, invalid_before) VALUES (-1, ?) '
            'ON CONFLICT(user_id) DO UPDATE SET invalid_before = excluded.invalid_before',
            (now,),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error:
        logger.warning("Global token epoch rotation could not be persisted")


def _sign_token(user_id: int, issued_at: int) -> str:
    """Return an unforgeable mobile token for ``user_id``.

    The signature is hex-encoded (not base64) because the token is delimited by
    underscores: a base64url signature can itself contain ``_`` and would be
    split into the wrong number of parts.
    """
    payload = f"{user_id}:{issued_at}"
    token_sig = hmac.new(_token_signing_key(), payload.encode(), hashlib.sha256).hexdigest()
    return f"genesis_mobile_{user_id}_{issued_at}_{token_sig}"


def _verify_token(token: str, now: int | None = None) -> int | None:
    """Return the user_id for a valid token, else None.

    Rejects a token whose signature is missing/wrong (checked in constant
    time), that is older than the TTL, or that predates the user's revocation
    epoch. Callers still check ``is_active`` before serving the request.
    """
    if not token.startswith('genesis_mobile_'):
        return None
    rest = token[len('genesis_mobile_'):]
    parts = rest.split('_')
    if len(parts) != 3:
        return None
    user_id_str, issued_at_str, token_sig = parts
    try:
        user_id = int(user_id_str)
        issued_at = int(issued_at_str)
    except ValueError:
        return None
    expected = hmac.new(_token_signing_key(), f"{user_id}:{issued_at}".encode(),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, token_sig):
        return None
    current = int(time.time()) if now is None else now
    if issued_at > current:
        return None  # clock-skewed or forged timestamp
    if current - issued_at > MOBILE_TOKEN_TTL_SECONDS:
        return None
    if issued_at <= _token_epoch(user_id):
        return None  # revoked (issued at or before the revocation epoch)
    if issued_at <= _global_token_epoch():
        return None  # invalidated by a global token-epoch rotation
    return user_id


def _user_auth_state(user_id: int) -> "sqlite3.Row | None":
    """Return the authenticated user's server-side row, or None.

    A token is only an identity claim. The role and active flag must come from
    the database, never from the token or the request, so a caller cannot grant
    itself privileges by changing what it sends. Any lookup error fails closed.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, username, role, is_active FROM users WHERE id = ?',
            (user_id,),
        )
        row = cursor.fetchone()
        conn.close()
    except sqlite3.Error:
        return None
    if row is None or not row['is_active']:
        return None
    return row

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiting. flask-limiter is optional: fall back to a no-op decorator so a
# missing optional dependency can never break app import (it previously did).
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=[],
        storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
    )
except Exception:  # pragma: no cover - optional dependency
    class _NoopLimiter:
        def limit(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

    limiter = _NoopLimiter()

# Database setup
DATABASE = 'genesis.db'


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def json_body() -> Dict[str, Any]:
    """Parse the request body as a JSON object.

    A malformed, missing or non-object body (e.g. a JSON array or string)
    yields an empty dict instead of raising, so callers can validate fields
    and return a 400 rather than crashing with a 500.
    """
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


MAX_FIELD_LENGTH = 254


def string_field(data: dict, key: str,
                 max_length: int = MAX_FIELD_LENGTH):
    """Return a non-empty string field, or None.

    A JSON body can carry a number, list or object where a string is
    expected. Rejecting it here keeps the bad type away from ``len()`` and
    the database driver, which would otherwise answer with a 500 instead of
    a 400.
    """
    value = data.get(key)
    if not isinstance(value, str) or not value or len(value) > max_length:
        return None
    return value


def init_db():
    """Initialize database tables."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Users table
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
            usage_count INTEGER DEFAULT 0
        )
    ''')
    
    # Chat history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            response TEXT,
            model_used TEXT,
            provider TEXT,
            quality_score REAL,
            mode TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Request logs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS request_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            provider TEXT,
            model TEXT,
            intent TEXT,
            status TEXT,
            latency_ms INTEGER,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Token revocation epochs. Persisting these makes revocation survive a
    # restart: an in-memory-only set would silently un-revoke every token when
    # the process restarts.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS token_epochs (
            user_id INTEGER PRIMARY KEY,
            invalid_before INTEGER NOT NULL
        )
    ''')
    
    # Provision a first administrator only from an explicit, non-default
    # ADMIN_PASSWORD. In production a missing/default password raises instead of
    # creating a guessable admin. An existing admin is never overwritten.
    cursor.execute('SELECT id FROM users WHERE role = "admin"')
    if not cursor.fetchone():
        admin_password = security_config.resolve_admin_bootstrap_password()
        if admin_password:
            admin_hash = generate_password_hash(admin_password)
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, role)
                VALUES (?, ?, ?, ?)
            ''', ('admin', 'admin@genesis.ai', admin_hash, 'admin'))
            logger.info("Administrator account provisioned from ADMIN_PASSWORD")
        else:
            logger.warning(
                "No administrator provisioned: set ADMIN_PASSWORD to create one."
            )
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")


# Authentication decorators
def login_required(f):
    """Decorator to require login - supports both session and Bearer token auth."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # A Bearer token is authoritative when present. The caller is identified
        # and authorised from the token plus the database, never from a cookie
        # that may belong to a different user. A bad token is a hard failure,
        # not a silent fallback to the session.
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            user_id = _verify_token(token)
            user = _user_auth_state(user_id) if user_id is not None else None
            if user is None:
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({'error': 'Unauthorized', 'login_required': True}), 401
                return redirect(url_for('login'))
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            return f(*args, **kwargs)

        # Fall back to session check
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized', 'login_required': True}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin role.

    Bearer tokens are accepted on the same terms as ``login_required`` so a
    mobile client cannot reach an admin route by a different path, and the role
    is always read from the database rather than trusted from the caller.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            user_id = _verify_token(auth_header[7:])
            user = _user_auth_state(user_id) if user_id is not None else None
            if user is None:
                return jsonify({'error': 'Unauthorized'}), 401
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']

        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            if request.is_json:
                return jsonify({'error': 'Admin access required'}), 403
            return redirect(url_for('chat'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# API AUTH ROUTES (for mobile app)
# ============================================================================

@app.route('/api/auth/login', methods=['POST'])
def api_auth_login():
    """Mobile API login endpoint."""
    data = json_body()
    username = string_field(data, 'username')
    password = string_field(data, 'password', max_length=1024)
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, username, email, password_hash, role, is_active 
        FROM users WHERE username = ?
    ''', (username,))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    if not check_password_hash(user['password_hash'], password):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    if not user['is_active']:
        return jsonify({'error': 'Account disabled'}), 403
    
    # Create session
    session.permanent = True
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user['role']
    
    # Generate token for mobile auth
    token = _sign_token(user['id'], int(time.time()))
    
    return jsonify({
        'success': True,
        'token': token,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'role': user['role']
        }
    })


@app.route('/api/auth/register', methods=['POST'])
def api_auth_register():
    """Mobile API registration endpoint."""
    data = json_body()
    username = string_field(data, 'username')
    email = string_field(data, 'email')
    password = string_field(data, 'password', max_length=1024)
    
    if not username or not email or not password:
        return jsonify({'error': 'All fields required'}), 400
    
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        password_hash = generate_password_hash(password)
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, role)
            VALUES (?, ?, ?, ?)
        ''', (username, email, password_hash, 'user'))
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Auto-login
        session.permanent = True
        session['user_id'] = user_id
        session['username'] = username
        session['role'] = 'user'
        
        token = _sign_token(user_id, int(time.time()))
        
        return jsonify({
            'success': True,
            'token': token,
            'user': {
                'id': user_id,
                'username': username,
                'email': email,
                'role': 'user'
            }
        })
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username or email already exists'}), 409


@app.route('/api/auth/logout', methods=['POST'])
def api_auth_logout():
    """Mobile API logout endpoint."""
    # Mobile clients authenticate with a Bearer token and have no session, so
    # revoke the identity proven by the presented token; fall back to the
    # session user for browser callers. Without this, a mobile logout would
    # leave the token valid.
    user_id = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        user_id = _verify_token(auth_header[7:])
    if user_id is None:
        user_id = session.get('user_id')
    if user_id is not None:
        invalidate_user_tokens(user_id)
    session.clear()
    return jsonify({'success': True})


@app.route('/api/auth/me', methods=['GET'])
def api_auth_me():
    """Get current user info."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, username, email, role, created_at
        FROM users WHERE id = ?
    ''', (session['user_id'],))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({
        'user': {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'role': user['role'],
            'created_at': user['created_at']
        }
    })


@app.route('/api/user', methods=['GET'])
@login_required
def api_user():
    """Get current user info (alias for /api/auth/me)."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, username, email, role, created_at, usage_count
        FROM users WHERE id = ?
    ''', (session['user_id'],))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({
        'id': user['id'],
        'username': user['username'],
        'email': user['email'],
        'role': user['role'],
        'created_at': user['created_at'],
        'usage_count': user['usage_count']
    })


@app.route('/api/chat/conversations', methods=['GET'])
@login_required
def api_chat_conversations():
    """Get user's chat conversations."""
    user_id = session['user_id']
    limit = request.args.get('limit', 50, type=int)
    
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get conversations from chat_history
    cursor.execute('''
        SELECT 
            MIN(id) as id,
            SUBSTR(message, 1, 50) as title,
            message,
            response,
            model_used,
            provider,
            created_at
        FROM chat_history 
        WHERE user_id = ?
        GROUP BY DATE(created_at), SUBSTR(message, 1, 30)
        ORDER BY created_at DESC
        LIMIT ?
    ''', (user_id, limit))
    
    conversations = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({'conversations': conversations})


@app.route('/api/chat/history/<int:chat_id>', methods=['GET'])
@login_required
def api_chat_history_by_id(chat_id):
    """Get a specific chat conversation by ID."""
    user_id = session['user_id']
    
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM chat_history 
        WHERE id = ? AND user_id = ?
    ''', (chat_id, user_id))
    
    chat = cursor.fetchone()
    
    if not chat:
        conn.close()
        return jsonify({'error': 'Chat not found'}), 404
    
    conn.close()
    
    # Return as array of messages for compatibility
    return jsonify({
        'messages': [
            {'role': 'user', 'content': chat['message'], 'created_at': chat['created_at']},
            {'role': 'assistant', 'content': chat['response'], 'created_at': chat['created_at']}
        ]
    })


# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login."""
    if request.method == 'POST':
        data = json_body() if request.is_json else request.form
        username = string_field(data, 'username')
        password = string_field(data, 'password', max_length=1024)
        
        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, password_hash, role, is_active 
            FROM users WHERE username = ?
        ''', (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            if not user['is_active']:
                return jsonify({'error': 'Account disabled'}), 403
            
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            
            # Update last login
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user['id'],))
            conn.commit()
            conn.close()
            
            logger.info(f"User {username} logged in")
            
            if request.is_json:
                return jsonify({'success': True, 'redirect': '/chat', 'role': user['role']})
            return redirect(url_for('chat'))
        
        if request.is_json:
            return jsonify({'error': 'Invalid credentials'}), 401
        return render_template('login.html', error='Invalid credentials')
    
    if 'user_id' in session:
        return redirect(url_for('chat'))
    
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration."""
    if request.method == 'POST':
        data = json_body() if request.is_json else request.form
        username = string_field(data, 'username')
        email = string_field(data, 'email')
        password = string_field(data, 'password', max_length=1024)
        
        if not username or not email or not password:
            return jsonify({'error': 'All fields required'}), 400
        
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, role)
                VALUES (?, ?, ?, ?)
            ''', (username, email, generate_password_hash(password), 'user'))
            conn.commit()
            conn.close()
            
            logger.info(f"User {username} registered")
            
            if request.is_json:
                return jsonify({'success': True, 'redirect': '/login'})
            return redirect(url_for('login'))
            
        except sqlite3.IntegrityError:
            return jsonify({'error': 'Username or email already exists'}), 400
    
    return render_template('register.html')


@app.route('/logout')
def logout():
    """User logout."""
    username = session.get('username')
    session.clear()
    logger.info(f"User {username} logged out")
    return redirect(url_for('login'))


# Main routes
@app.route('/')
def index():
    """Homepage."""
    if 'user_id' in session:
        return redirect(url_for('ultra'))
    return render_template('genesis_ultra.html')


@app.route('/chat')
@login_required
def chat():
    """Chat interface."""
    return render_template('chat.html', 
                          username=session.get('username'),
                          role=session.get('role'))


@app.route('/gemini')
@login_required
def gemini():
    """Advanced Gemini-style chat interface."""
    return render_template('genesis_gemini.html', 
                          username=session.get('username'),
                          role=session.get('role'))


@app.route('/ultra')
@login_required
def ultra():
    """Ultra Advanced chat interface with all features."""
    return render_template('genesis_ultra.html', 
                          username=session.get('username'),
                          role=session.get('role'))


@app.route('/agent')
@login_required
def agent_workspace():
    """AI Agent Workspace - Full autonomous agent experience."""
    return render_template('agent_workspace.html',
                          username=session.get('username'),
                          role=session.get('role'))


@app.route('/settings')
@login_required
def settings():
    """Settings page."""
    config = get_config()
    
    # Get provider status
    providers = {
        'groq': config.groq.is_configured(),
        'openai': config.openai.is_configured(),
        'gemini': config.gemini.is_configured(),
        'claude': config.claude.is_configured(),
        'deepseek': config.deepseek.is_configured(),
        'mistral': config.mistral.is_configured(),
        'huggingface': config.huggingface.is_configured(),
    }
    
    return render_template('settings.html',
                          username=session.get('username'),
                          providers=providers,
                          version=VERSION)


@app.route('/admin')
@admin_required
def admin():
    """Admin dashboard."""
    return render_template('admin.html',
                          username=session.get('username'))


# API Routes
@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    """Chat API endpoint - WEB CHANNEL ONLY."""
    increment_metric('request_count')
    start_time = time.time()
    
    # Support both JSON and FormData
    if request.is_json:
        data = request.get_json()
        message = data.get('message', '')
        provider = data.get('provider', 'groq')
        model = data.get('model', 'llama-3.3-70b-versatile')
    else:
        message = request.form.get('message', '')
        provider = request.form.get('provider', 'groq')
        model = request.form.get('model', 'llama-3.3-70b-versatile')
    
    if not message:
        return jsonify({'error': 'Message required'}), 400
    
    user_id = session['user_id']
    
    # Set channel isolation - WEB ONLY
    channel_isolation = get_channel_isolation()
    channel_isolation.set_channel(Channel.WEB)
    channel_isolation.log_channel_activity(Channel.WEB, "chat_request", f"User {user_id} using {provider}/{model}")
    
    # Check rate limit (100 messages per day for non-admin)
    if session.get('role') != 'admin':
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM chat_history 
            WHERE user_id = ? AND created_at > datetime('now', '-1 day')
        ''', (user_id,))
        count = cursor.fetchone()[0]
        conn.close()
        
        if count >= 100:
            return jsonify({'error': 'Rate limit exceeded. Try again tomorrow.'}), 429
    
    try:
        # Import and use Genesis Agent
        import asyncio
        from genesis_protocol.ai.agent import get_genesis_agent
        
        async def get_response():
            agent = get_genesis_agent()
            result = await agent.process(
                message, 
                chat_id=user_id, 
                user_id=user_id
            )
            return result
        
        # FIX: Reuse existing event loop if available
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(get_response())
        
        # Record latency
        latency_ms = (time.time() - start_time) * 1000
        record_latency(result.provider_used or 'unknown', latency_ms)
        
        # Store in database
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO chat_history (user_id, message, response, model_used, provider, quality_score, mode)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, message, result.response, result.model_used, result.provider_used, 
              result.quality_score, result.mode))
        
        # Increment usage count
        cursor.execute('UPDATE users SET usage_count = usage_count + 1 WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
        
        # Estimate tokens (rough estimate: ~4 chars per token)
        response_text = result.response if result.response else ""
        tokens_estimate = len(message) // 4 + len(response_text) // 4
        
        return jsonify({
            'success': True,
            'response': result.response if result.response else "AI response unavailable",
            'model': result.model_used,
            'provider': result.provider_used,
            'quality': result.quality_score,
            'mode': result.mode,
            'planning': result.planning_active,
            'tools_used': result.tools_used,
            'tokens': tokens_estimate
        })
        
    except Exception as e:
        increment_metric('error_count')
        logger.error(f"Chat error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/history', methods=['GET'])
@login_required
def api_chat_history():
    """Get chat history - WEB CHANNEL ONLY."""
    user_id = session['user_id']
    limit = request.args.get('limit', 50, type=int)
    
    # Set channel isolation - WEB ONLY
    channel_isolation = get_channel_isolation()
    channel_isolation.set_channel(Channel.WEB)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT message, response, model_used, created_at, 'web' as channel
        FROM chat_history 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT ?
    ''', (user_id, limit))
    
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({'history': history, 'channel': 'web'})


@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def api_admin_stats():
    """Get system statistics for admin."""
    conn = get_db()
    cursor = conn.cursor()
    
    # User stats
    cursor.execute('SELECT COUNT(*) as total, SUM(usage_count) as usage FROM users')
    user_stats = dict(cursor.fetchone())
    
    # Request logs
    cursor.execute('''
        SELECT provider, model, COUNT(*) as count, AVG(latency_ms) as avg_latency
        FROM request_logs 
        WHERE created_at > datetime('now', '-24 hours')
        GROUP BY provider, model
    ''')
    model_usage = [dict(row) for row in cursor.fetchall()]
    
    # Recent errors
    cursor.execute('''
        SELECT error, COUNT(*) as count 
        FROM request_logs 
        WHERE status = 'failed' AND created_at > datetime('now', '-24 hours')
        GROUP BY error
        ORDER BY count DESC
        LIMIT 10
    ''')
    recent_errors = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({
        'users': user_stats,
        'model_usage': model_usage,
        'recent_errors': recent_errors
    })


@app.route('/api/admin/users', methods=['GET'])
@admin_required
def api_admin_users():
    """Get all users for admin."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, username, email, role, created_at, last_login, usage_count, is_active
        FROM users ORDER BY created_at DESC
    ''')
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'users': users})


@app.route('/api/admin/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def api_admin_toggle_user(user_id):
    """Toggle user active status."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_active = NOT is_active WHERE id = ?', (user_id,))
    cursor.execute('SELECT is_active FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.commit()
    conn.close()
    # Deactivating an account must revoke its outstanding mobile tokens.
    if row and not row['is_active']:
        invalidate_user_tokens(user_id)
    return jsonify({'success': True})


@app.route('/api/admin/logs', methods=['GET'])
@admin_required
def api_admin_logs():
    """Get request logs for admin."""
    limit = request.args.get('limit', 100, type=int)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.*, u.username 
        FROM request_logs r 
        LEFT JOIN users u ON r.user_id = u.id
        ORDER BY r.created_at DESC 
        LIMIT ?
    ''', (limit,))
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({'logs': logs})


# Dashboard Route
@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard with chat history and stats."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get user info
    cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = dict(cursor.fetchone())
    
    # Get chat stats
    cursor.execute('''
        SELECT COUNT(*) as total_chats,
               COUNT(DISTINCT provider) as providers_used,
               AVG(quality_score) as avg_quality,
               MIN(created_at) as first_chat,
               MAX(created_at) as last_chat
        FROM chat_history WHERE user_id = ?
    ''', (session['user_id'],))
    stats = dict(cursor.fetchone())
    
    # Get recent chats
    cursor.execute('''
        SELECT * FROM chat_history 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT 20
    ''', (session['user_id'],))
    recent_chats = [dict(row) for row in cursor.fetchall()]
    
    # Get provider usage
    cursor.execute('''
        SELECT provider, COUNT(*) as count 
        FROM chat_history 
        WHERE user_id = ? 
        GROUP BY provider
        ORDER BY count DESC
    ''', (session['user_id'],))
    provider_usage = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template('dashboard.html', 
                         user=user, 
                         stats=stats, 
                         recent_chats=recent_chats,
                         provider_usage=provider_usage)


@app.route('/api/chat/history')
@login_required
def get_chat_history():
    """Get user's chat history (JSON API)."""
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    offset = (page - 1) * per_page
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM chat_history 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT ? OFFSET ?
    ''', (session['user_id'], per_page, offset))
    chats = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute('SELECT COUNT(*) FROM chat_history WHERE user_id = ?', (session['user_id'],))
    total = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'chats': chats,
        'page': page,
        'per_page': per_page,
        'total': total,
        'pages': (total + per_page - 1) // per_page
    })


@app.route('/api/chat/<int:chat_id>')
@login_required
def get_chat(chat_id):
    """Get a specific chat."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM chat_history 
        WHERE id = ? AND user_id = ?
    ''', (chat_id, session['user_id']))
    chat = cursor.fetchone()
    
    conn.close()
    
    if not chat:
        return jsonify({'error': 'Chat not found'}), 404
    
    return jsonify(dict(chat))


@app.route('/api/stats')
@login_required
def get_user_stats():
    """Get user statistics (JSON API)."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get stats
    cursor.execute('''
        SELECT 
            COUNT(*) as total_chats,
            COUNT(DISTINCT provider) as providers_used,
            AVG(quality_score) as avg_quality,
            SUM(LENGTH(message) + LENGTH(response)) as total_chars
        FROM chat_history WHERE user_id = ?
    ''', (session['user_id'],))
    stats = dict(cursor.fetchone())
    
    # Get daily stats (last 7 days)
    cursor.execute('''
        SELECT DATE(created_at) as date, COUNT(*) as count
        FROM chat_history 
        WHERE user_id = ? AND created_at >= DATE('now', '-7 days')
        GROUP BY DATE(created_at)
        ORDER BY date
    ''', (session['user_id'],))
    daily_stats = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({**stats, 'daily': daily_stats})


# Error handlers
@app.errorhandler(404)
def not_found(e):
    if request.is_json:
        return jsonify({'error': 'Not found'}), 404
    return render_template('error.html', error='Page not found'), 404


@app.errorhandler(500)
def server_error(e):
    if request.is_json:
        return jsonify({'error': 'Server error'}), 500
    return render_template('error.html', error='Server error'), 500


# Initialize database on startup
init_db()


@app.route('/api/debug', methods=['GET'])
def api_debug():
    """Debug endpoint to check AI providers and deployment info."""
    try:
        from genesis_protocol.ai.provider_chain import get_provider_chain
        
        chain = get_provider_chain()
        available = chain.get_available_providers()
        status = chain.get_status()
        
        return jsonify({
            'status': 'ok',
            'entrypoint': 'web/app.py',
            'commit': '417a557',
            'available_providers': available,
            'provider_status': status,
            'groq_configured': status.get('groq', {}).get('configured', False)
        })
    except Exception as e:
        import traceback
        return jsonify({
            'status': 'error',
            'entrypoint': 'web/app.py',
            'error': str(e),
            'traceback': traceback.format_exc()
        })


@app.route('/api/test-417a557', methods=['GET'])
def api_test():
    """UNIQUE test endpoint - only exists in app.py"""
    return jsonify({
        'status': 'ok',
        'entrypoint': 'web/app.py',
        'commit': '417a557',
        'unique': True,
        'timestamp': str(datetime.now())
    })


# ============================================================================
# MONITORING ENDPOINTS
# ============================================================================

@app.route('/api/version', methods=['GET'])
def api_version():
    """Get version info."""
    return jsonify({
        'version': VERSION,
        'build_date': BUILD_DATE,
        'entrypoint': 'web/app.py'
    })


@app.route('/api/health', methods=['GET'])
def api_health():
    """Basic health check - is the server responding?"""
    return jsonify({
        'status': 'healthy',
        'entrypoint': 'web/app.py'
    })


@app.route('/api/debug/telegram', methods=['GET'])
def api_debug_telegram():
    """Debug endpoint: check if Telegram bot is running and what env vars are set."""
    import subprocess
    env_status = {
        'TELEGRAM_BOT_TOKEN': bool(os.environ.get('TELEGRAM_BOT_TOKEN')),
        'TELEGRAM_ADMIN_IDS': os.environ.get('TELEGRAM_ADMIN_IDS', ''),
        'GROQ_API_KEY': bool(os.environ.get('GROQ_API_KEY')),
    }
    # Check if telegram process is running
    try:
        result = subprocess.run(['pgrep', '-af', 'start_all_telegram'], capture_output=True, text=True, timeout=5)
        tg_procs = result.stdout.strip().split('\n') if result.stdout.strip() else []
    except Exception:
        tg_procs = []
    # Read telegram error logs if they exist
    logs = {}
    for logfile in ['/tmp/telegram.err.log', '/tmp/telegram.out.log']:
        try:
            with open(logfile) as f:
                logs[logfile] = f.read()[-3000:]
        except Exception as e:
            logs[logfile] = f'Cannot read: {e}'
    
    # Network egress test: can we reach telegram.org?
    net_test = {}
    import requests as req
    for url, name in [('https://api.telegram.org/', 'telegram.org'), ('https://api.groq.com/', 'groq.com'), ('https://huggingface.co/', 'huggingface.co')]:
        try:
            r = req.get(url, timeout=15)
            net_test[name] = f'OK (HTTP {r.status_code}, {r.elapsed.total_seconds()}s)'
        except Exception as e:
            net_test[name] = f'FAILED: {str(e)[:100]}'
    
    return jsonify({
        'env': env_status,
        'telegram_processes': tg_procs,
        'logs': logs,
        'network_egress_test': net_test,
    })


TELEGRAM_REPLY_QUEUE = '/tmp/telegram_reply_queue.json'
TELEGRAM_QUEUE_MAX = 200  # bound so the file cannot grow without limit
# How long a writer waits for the cross-process queue lock before it refuses to
# write. Bounded so a stuck holder cannot hang a request thread indefinitely; a
# timeout surfaces as a raised error (never a silent success). Tests shrink this
# to exercise the timeout path.
TELEGRAM_QUEUE_LOCK_TIMEOUT = 5.0
# Owner commands (/approve, /reject, /updates) are parked here, separate from
# the reply queue: the relay sends replies, but only the self-improvement
# harness acts on commands, so a command must not be rendered as a reply.
TELEGRAM_COMMAND_QUEUE = '/tmp/telegram_command_queue.json'

# Owner work orders (/do <instruction>) are parked here. The self-improvement
# harness drains it, runs the agent, and opens a PR — then asks for /approve.
TELEGRAM_TASK_QUEUE = '/tmp/telegram_task_queue.json'


def _configured_owner_ids():
    """Owner Telegram user ids from TELEGRAM_ADMIN_ID. Never a default.

    Comma- or semicolon-separated, so more than one owner can be configured.
    An unset value authorises nobody.
    """
    raw = os.environ.get('TELEGRAM_ADMIN_ID', '')
    return frozenset(
        part.strip()
        for part in raw.replace(';', ',').split(',')
        if part.strip()
    )


def _sender_identity(sender):
    """The verified Telegram user id from a message/callback ``from`` object.

    Only the numeric ``id`` Telegram itself delivers is trusted. A value
    supplied inside message text or callback data is never consulted.
    """
    if not isinstance(sender, dict):
        return ''
    sender_id = sender.get('id')
    if isinstance(sender_id, bool):
        return ''
    if isinstance(sender_id, int):
        return str(sender_id)
    if isinstance(sender_id, str) and sender_id.strip():
        return sender_id.strip()
    return ''


def _is_owner(sender):
    """True only when the sender's verified id is a configured owner.

    Fails closed: with no configured owner id nobody is an owner, so a
    privileged command is never accepted merely because another check (such as
    the webhook secret) is also unset.
    """
    identity = _sender_identity(sender)
    if not identity:
        return False
    return identity in _configured_owner_ids()


def _read_queue(path):
    """Load a queue file, treating a missing file as an empty queue.

    A corrupt or unreadable file is not silently treated as empty: that would
    look like "no messages" and hide a dropped reply, so it is logged with the
    file name and reason. Callers still get [] so one bad file cannot take the
    webhook down.
    """
    try:
        with open(path) as f:
            queue = json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.warning("queue read failed (%s): %s: %s", path, type(e).__name__, e)
        return []
    if not isinstance(queue, list):
        logger.warning(
            "queue read failed (%s): expected a list, got %s", path, type(queue).__name__
        )
        return []
    return queue


def _quarantine_corrupt_queue(path):
    """Move an unreadable queue aside so its bytes are preserved, not lost.

    Returns the backup path. Raises OSError if it cannot be moved, so a caller
    refuses to overwrite data it could not preserve rather than discarding it.
    """
    backup = f'{path}.corrupt-{int(time.time())}'
    os.replace(path, backup)
    return backup


def _load_queue_for_write(path):
    """Load a queue for a read-modify-write without discarding bad data.

    Unlike :func:`_read_queue` (which returns [] so a GET cannot take the app
    down), a corrupt file here is not quietly overwritten: its bytes are moved
    aside to a ``.corrupt-<ts>`` sibling and logged, then the queue restarts
    empty. A missing file is simply an empty queue. If the corrupt file cannot
    be moved aside, the error propagates so the caller refuses to clobber it.
    """
    try:
        with open(path) as f:
            queue = json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        backup = _quarantine_corrupt_queue(path)
        logger.error(
            "queue %s unreadable (%s: %s); moved aside to %s",
            path, type(e).__name__, e, backup,
        )
        return []
    if not isinstance(queue, list):
        backup = _quarantine_corrupt_queue(path)
        logger.error(
            "queue %s was not a list (%s); moved aside to %s",
            path, type(queue).__name__, backup,
        )
        return []
    return queue


class QueueLockError(RuntimeError):
    """Raised when the cross-process queue lock cannot be acquired in time."""


# Serialises read-modify-write on one queue inside this process. The file lock
# below is the cross-process guard; this lock is the thread guard, so two
# threads do not both race for the file lock and a re-entrant call cannot
# deadlock on the same thread.
_QUEUE_LOCKS = {}
_QUEUE_LOCKS_GUARD = threading.Lock()


def _thread_lock(path):
    with _QUEUE_LOCKS_GUARD:
        lock = _QUEUE_LOCKS.get(path)
        if lock is None:
            lock = threading.RLock()
            _QUEUE_LOCKS[path] = lock
        return lock


@contextlib.contextmanager
def _queue_lock(path, timeout=None):
    """Hold an exclusive lock on ``path.lock`` across a read-modify-write.

    fcntl.flock is advisory and released automatically when the process dies,
    so a crashed writer cannot leave the queue permanently locked. The
    thread-level lock is taken first so threads in this process queue up
    before they contend for the file lock.

    A timeout raises QueueLockError rather than proceeding, so a caller can
    never mistake a failed lock for a successful write.
    """
    if timeout is None:
        timeout = TELEGRAM_QUEUE_LOCK_TIMEOUT
    with _thread_lock(path):
        lock_path = path + '.lock'
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        except OSError as e:
            raise QueueLockError(f'cannot open queue lock {lock_path}: {e}') from e
        acquired = False
        try:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except OSError as e:
                    if e.errno not in (errno.EACCES, errno.EAGAIN):
                        raise QueueLockError(
                            f'cannot lock queue {lock_path}: {e}'
                        ) from e
                    if time.monotonic() >= deadline:
                        raise QueueLockError(
                            f'timed out after {timeout}s waiting for {lock_path}'
                        ) from e
                    time.sleep(0.02)
            yield
        finally:
            if acquired:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
            os.close(fd)


def _write_queue(path, queue):
    """Replace a queue file atomically, never exposing a partial file.

    A plain open(path, 'w') truncates first, so a crash or a full disk mid-write
    leaves invalid JSON that the next read discards. Writing a sibling temp file
    in the same directory, flushing and fsync-ing it, then os.replace()-ing it
    onto the target means a reader sees either the whole old queue or the whole
    new one. os.replace is atomic within a filesystem, hence "same directory".
    """
    directory = os.path.dirname(path) or '.'
    fd, tmp = tempfile.mkstemp(dir=directory, prefix='.queue-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(queue, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _append_queue(path, chat_id, text, from_id=None):
    """Append one bounded entry under the lock, tagged with an id to dedup.

    ``from_id`` records the verified sender of a privileged command so a
    downstream consumer (the self-improvement harness) can re-check it before
    acting, without trusting the queue contents alone.
    """
    with _queue_lock(path):
        queue = _load_queue_for_write(path)
        entry = {
            'id': f'{chat_id}:{int(time.time() * 1000)}:{len(queue)}',
            'chat_id': chat_id,
            'text': str(text)[:4000],
        }
        if from_id is not None:
            entry['from_id'] = from_id
        queue.append(entry)
        _write_queue(path, queue[-TELEGRAM_QUEUE_MAX:])


def _clear_queue(path):
    with _queue_lock(path):
        _write_queue(path, [])


def _ack_queue(path, ack_ids):
    """Remove exactly the acknowledged entries under the same queue lock.

    A drain runs on a different host (GitHub Actions), so it cannot hold the
    fcntl lock itself; instead it reports which ids it acted on and the removal
    happens here, inside the lock, as one read-modify-write. An entry appended
    while the drain was working is therefore never in ``ack_ids`` and is kept,
    which is what stops a concurrent writer and a drain from losing entries.

    ``ack_ids`` is normalised to a set of strings. Only ids that are present are
    removed; unknown ids are ignored, so a retried ack is harmless. Returns the
    number of entries removed.
    """
    wanted = {str(i) for i in ack_ids if i is not None and str(i).strip()}
    if not wanted:
        return 0
    with _queue_lock(path):
        queue = _load_queue_for_write(path)
        kept = [e for e in queue if not (isinstance(e, dict) and str(e.get('id')) in wanted)]
        removed = len(queue) - len(kept)
        if removed:
            _write_queue(path, kept)
        return removed


def _read_command_queue():
    return _read_queue(TELEGRAM_COMMAND_QUEUE)


def _append_command(chat_id, text, from_id=None):
    """Park an owner command, re-checking the sender id at the boundary.

    The webhook authorises the sender before it gets here, but this is the one
    function every privileged command passes through, so it refuses to park a
    command unless ``from_id`` is a configured owner. A future caller therefore
    cannot enqueue a privileged command while skipping the check.
    """
    if not _is_owner({'id': from_id}):
        logger.warning(
            "refused to queue a privileged command: sender is not a configured owner"
        )
        return False
    _append_queue(TELEGRAM_COMMAND_QUEUE, chat_id, text, from_id=from_id)
    return True


def _read_task_queue():
    return _read_queue(TELEGRAM_TASK_QUEUE)


def _append_task(order):
    with _queue_lock(TELEGRAM_TASK_QUEUE):
        queue = _load_queue_for_write(TELEGRAM_TASK_QUEUE)
        queue.append(order)
        _write_queue(TELEGRAM_TASK_QUEUE, queue[-TELEGRAM_QUEUE_MAX:])


def _update_task(order_id, **changes):
    """Patch one work order in place; returns the updated order or None."""
    with _queue_lock(TELEGRAM_TASK_QUEUE):
        queue = _load_queue_for_write(TELEGRAM_TASK_QUEUE)
        updated = None
        for order in queue:
            if isinstance(order, dict) and str(order.get('id')) == str(order_id):
                order.update({k: v for k, v in changes.items() if v is not None})
                updated = order
                break
        if updated is not None:
            _write_queue(TELEGRAM_TASK_QUEUE, queue[-TELEGRAM_QUEUE_MAX:])
        return updated


def _handle_work_order(chat_id, verb, arg):
    """Park a /do order, or cancel one with /cancel.

    The self-improvement harness owns the task queue: it runs the agent and
    opens a PR, then reports back. Nothing here runs the agent or merges.
    """
    from genesis_protocol.updates import WorkOrder, render_work_orders, resolve_order

    if verb == 'do':
        if not arg:
            _append_reply(chat_id, "Kya karwana hai? Bhejo: /do <instruction>")
            return jsonify({'ok': True, 'queued': 'do-help'})
        order_id = f"{int(time.time() * 1000) % 100000000}"
        order = WorkOrder(
            id=order_id,
            instruction=arg[:2000],
            state='queued',
            created=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        )
        try:
            _append_task(order.to_dict())
        except Exception as e:
            # The order was not durably parked; do not acknowledge it as queued.
            print(f"Task queue store error: {e}")
            return jsonify({'ok': False, 'error': 'work order not queued'}), 500
        _append_reply(
            chat_id,
            f"🛠️ Work order #{order_id} mil gaya. Genesis agent ispe kaam karega "
            f"aur ek PR kholega — merge tumhari /approve ke baad hi hoga.\n\n"
            f"Instruction: {arg[:300]}",
        )
        return jsonify({'ok': True, 'queued': 'work-order', 'id': order_id})

    # verb == 'cancel'
    orders = [WorkOrder(**{k: o.get(k, '') for k in ('id', 'instruction', 'state', 'pr', 'note', 'created')})
              for o in _read_task_queue() if isinstance(o, dict)]
    target = resolve_order(orders, arg)
    if target is None:
        _append_reply(chat_id, f"Work order '{arg}' nahi mila. /tasks se dekho.")
        return jsonify({'ok': True})
    try:
        _update_task(target.id, state='cancelled')
    except Exception as e:
        print(f"Task queue store error: {e}")
        return jsonify({'ok': False, 'error': 'cancel not stored'}), 500
    _append_reply(chat_id, f"🚫 Work order #{target.id} cancel kar diya.")
    return jsonify({'ok': True, 'queued': 'cancel'})


def _handle_tasks_list(chat_id):
    from genesis_protocol.updates import WorkOrder, render_work_orders

    orders = [WorkOrder(**{k: o.get(k, '') for k in ('id', 'instruction', 'state', 'pr', 'note', 'created')})
              for o in _read_task_queue() if isinstance(o, dict)]
    _append_reply(chat_id, render_work_orders(orders))
    return jsonify({'ok': True, 'queued': 'tasks'})


# /council [best|vote|synth] <question> — ask several models, reconcile.
_COUNCIL_STRATEGIES = {
    'best': 'best',
    'vote': 'vote',
    'synth': 'synthesis',
    'synthesis': 'synthesis',
}


def _handle_council(chat_id, arg):
    """Run a multi-LLM deliberation and queue the reconciled answer.

    The first word may select the strategy; anything else is the question.
    Runs the async council on a fresh loop, the same way the normal AI path
    does, because the webhook is synchronous.
    """
    if not arg:
        _append_reply(
            chat_id,
            "🧠 *Council mode* — kai models ek saath jawab dete hain, phir best chunte hain.\n\n"
            "Use: /council <question>\n"
            "/council vote <question> — majority jawab\n"
            "/council synth <question> — sab jawab ek me merge",
        )
        return jsonify({'ok': True, 'queued': 'council-help'})

    strategy_name = 'best'
    question = arg
    first, _, rest = arg.partition(' ')
    if first.lower() in _COUNCIL_STRATEGIES and rest.strip():
        strategy_name = _COUNCIL_STRATEGIES[first.lower()]
        question = rest.strip()

    try:
        import asyncio
        from genesis_protocol.ai.council import CouncilStrategy, get_council

        strategy = CouncilStrategy(strategy_name)
        council = get_council()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            council.deliberate(
                messages=[
                    {"role": "system", "content": "You are Genesis, a helpful autonomous AI. Keep responses concise and helpful."},
                    {"role": "user", "content": question},
                ],
                user_input=question,
                strategy=strategy,
            )
        )
        loop.close()
    except Exception as e:
        _append_reply(chat_id, f"❌ Council error: {str(e)[:500]}")
        return jsonify({'ok': True, 'queued': 'council-error'})

    if not result.success:
        _append_reply(chat_id, f"❌ Council failed: {(result.error or 'unknown')[:500]}")
        return jsonify({'ok': True, 'queued': 'council-failed'})

    members = ", ".join(f"{m.provider}✓" for m in result.members if m.ok)
    header = f"🧠 *Council* ({result.strategy.value}) — {result.answered_by}"
    if result.consensus:
        header += f" | agreement {int(result.consensus * 100)}%"
    body = f"{header}\n_({members})_\n\n{result.answer[:3800]}"
    _append_reply(chat_id, body)
    return jsonify({'ok': True, 'queued': 'council'})


def _handle_callback_query(callback):
    """Turn an inline-button tap into the command it represents.

    Button payloads are ``"<verb>:<arg>"`` (e.g. ``approve:17``, ``list``).
    Only verbs the update pipeline understands are accepted, so a forged
    callback cannot inject an arbitrary command. The command is parked on the
    same queue as a typed one; the harness replies after it acts.
    """
    data = str(callback.get('data', '')).strip()
    verb, _, arg = data.partition(':')
    allowed = {'approve', 'reject', 'list', 'updates', 'pending', 'status', 'help'}
    if verb not in allowed:
        return jsonify({'ok': True})
    command = f'/{verb}' + (f' {arg}' if arg else '')
    message = callback.get('message') or {}
    chat = message.get('chat') or {}
    chat_id = chat.get('id') if isinstance(chat, dict) else None
    if not isinstance(chat_id, (int, str)) or not str(chat_id).strip():
        return jsonify({'ok': True})
    # A button tap is a privileged action: only a configured owner may use it.
    # The sender id comes from callback.from, never from the button payload.
    if not _is_owner(callback.get('from')):
        return jsonify({'ok': True, 'denied': 'not-owner'})
    try:
        _append_command(chat_id, command, from_id=_sender_identity(callback.get('from')))
    except Exception as e:
        print(f"Callback command store error: {e}")
        return jsonify({'ok': False, 'error': 'callback not queued'}), 500
    return jsonify({'ok': True, 'queued': 'callback', 'command': command})


def _telegram_secret_ok():
    """Shared-secret check for the Telegram webhook and the reply queue.

    Set TELEGRAM_WEBHOOK_SECRET in the Space env and register it with Telegram
    (setWebhook secret_token). This authenticates *Telegram* as the caller; it
    is separate from owner identity, which is checked per request in the
    webhook handler. In production the secret is required: an unset secret fails
    closed (401) rather than leaving the endpoint open. Outside production an
    unset secret keeps the endpoint open so an existing deployment does not
    break.
    """
    expected = os.environ.get('TELEGRAM_WEBHOOK_SECRET', '')
    if not expected:
        return not security_config.is_production()
    supplied = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
    return hmac.compare_digest(str(supplied), str(expected))


def _read_reply_queue():
    return _read_queue(TELEGRAM_REPLY_QUEUE)


def _append_reply(chat_id, text):
    """Append one validated reply, bounded, tagged with an id for dedup.

    Replies are best-effort: a reply that cannot be stored (for example a lock
    timeout) must not fail the request that already stored the authoritative
    command, so a write error is logged and swallowed here. Command and task
    queues do not swallow errors.
    """
    try:
        _append_queue(TELEGRAM_REPLY_QUEUE, chat_id, text)
    except Exception as e:  # noqa: BLE001 - a lost reply must not 500 a handled request
        print(f"Reply queue store error: {e}")


@app.route('/api/telegram/webhook', methods=['POST'])
def telegram_webhook():
    """Receive Telegram updates via webhook (inbound - works on HF Spaces).
    Stores replies in a queue file since HF can't reach telegram.org outbound.
    GitHub Actions sends queued replies to Telegram."""
    if not _telegram_secret_ok():
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401

    update = request.get_json(force=True, silent=True) or {}

    # Inline-button taps arrive as callback_query, not message. The button
    # carries its own command (e.g. "approve:17"), so we translate it into the
    # equivalent /command and park it for the self-improvement harness. A tap
    # therefore never depends on the owner retyping a number.
    callback = update.get('callback_query')
    if isinstance(callback, dict):
        return _handle_callback_query(callback)

    if 'message' not in update:
        return jsonify({'ok': True})

    msg = update['message']
    if not isinstance(msg, dict):
        return jsonify({'ok': True})
    chat = msg.get('chat') or {}
    chat_id = chat.get('id') if isinstance(chat, dict) else None
    # Only ever reply to a real chat id; drop anything else.
    if not isinstance(chat_id, (int, str)) or not str(chat_id).strip():
        return jsonify({'ok': True})
    text = msg.get('text', '')
    if not isinstance(text, str):
        return jsonify({'ok': True})
    text = text[:4000]
    user = msg.get('from', {})
    # Owner identity is the verified sender id from the update, checked against
    # the explicitly configured TELEGRAM_ADMIN_ID. It is never taken from the
    # message text. A missing or non-owner sender fails closed, so no
    # privileged command (work order or approval) is ever parked on a queue.
    is_owner = _is_owner(user)

    # Owner work orders (/do, /cancel, /tasks) are handled here: the order is
    # parked on the task queue for the harness, and the owner gets an immediate
    # acknowledgement. These are not approval commands.
    try:
        from genesis_protocol.updates import is_tasks_command, parse_work_order
        work = parse_work_order(text)
        if work is not None:
            if not is_owner:
                return jsonify({'ok': True, 'denied': 'not-owner'})
            return _handle_work_order(chat_id, work[0], work[1])
        if is_tasks_command(text):
            if not is_owner:
                return jsonify({'ok': True, 'denied': 'not-owner'})
            return _handle_tasks_list(chat_id)
    except Exception as e:
        print(f"Work-order routing error: {e}")

    # Owner update commands are parked for the self-improvement harness, which
    # is the only thing that may act on them. They get no immediate reply; the
    # harness replies after it merges or rejects.
    try:
        from genesis_protocol.updates import parse_command
        is_command = parse_command(text) is not None
    except Exception:
        is_command = False
    if is_command:
        if not is_owner:
            return jsonify({'ok': True, 'denied': 'not-owner'})
        try:
            _append_command(chat_id, text, from_id=_sender_identity(user))
        except Exception as e:
            # Never report a queued command that was not durably stored: a lost
            # /approve must surface as an error, not a silent success.
            print(f"Command queue store error: {e}")
            return jsonify({'ok': False, 'error': 'command not queued'}), 500
        return jsonify({'ok': True, 'queued': 'command'})

    # Multi-LLM council: /council <question> asks several models at once and
    # reconciles their answers, so a hard question does not depend on one model
    # being right. /council vote and /council synth pick the reconciliation.
    if text.startswith('/council'):
        return _handle_council(chat_id, text[len('/council'):].strip())

    # Build reply text
    if text == '/start':
        reply = "🤖 *Genesis Protocol* online!\n\nI'm your autonomous AI. Send me any message or question!\n\nCommands:\n/start - Welcome\n/status - Bot status\n/ask <question> - Ask AI\n/council <question> - Ask several models at once"
    elif text == '/status':
        reply = "✅ Genesis bot running (webhook + relay mode)\n🚀 HF Space: LIVE\n🧠 AI: Groq-powered\n📡 Replies relayed via GitHub Actions"
    elif text.startswith('/ask '):
        question = text[5:].strip()
        reply = None
    elif text.startswith('/'):
        reply = "Unknown command. Send /start for help."
    else:
        question = text
        reply = None
    
    # If no immediate reply, process with AI
    if reply is None:
        if not question:
            return jsonify({'ok': True})
        try:
            from genesis_protocol.ai.provider_chain import get_provider_chain
            import asyncio
            ai = get_provider_chain()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                ai.call(
                    messages=[
                        {"role": "system", "content": "You are Genesis, a helpful autonomous AI. Keep responses concise and helpful."},
                        {"role": "user", "content": question}
                    ],
                    user_input=question
                )
            )
            loop.close()
            if result.success and result.response:
                reply = f"🤖 *Genesis AI:*\n\n{result.response.content[:4000]}"
            else:
                err = result.error[:500] if result.error else "Unknown error"
                reply = f"❌ Error: {err}"
        except Exception as e:
            reply = f"❌ Error: {str(e)[:500]}"
    
    # Store reply in queue (GitHub Actions will send it)
    if reply:
        try:
            _append_reply(chat_id, reply)
        except Exception as e:
            print(f"Queue store error: {e}")

    return jsonify({'ok': True})


@app.route('/api/telegram/queue', methods=['GET'])
def telegram_queue_get():
    """Return pending replies (called by GitHub Actions relay)."""
    if not _telegram_secret_ok():
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401
    queue = _read_reply_queue()
    return jsonify({'replies': queue, 'count': len(queue)})


@app.route('/api/telegram/queue', methods=['DELETE'])
def telegram_queue_clear():
    """Clear the reply queue (called by GitHub Actions after sending).

    With a JSON body ``{"ids": [...]}`` only those replies are removed, so a
    reply appended while the relay was sending is kept and delivered next tick
    instead of being wiped. Without a body the whole queue is cleared, which
    stays correct for an owner-requested full clear.
    """
    if not _telegram_secret_ok():
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401
    body = request.get_json(force=True, silent=True) or {}
    ids = body.get('ids') if isinstance(body, dict) else None
    try:
        if ids is not None:
            if not isinstance(ids, list):
                return jsonify({'ok': False, 'error': 'ids must be a list'}), 400
            removed = _ack_queue(TELEGRAM_REPLY_QUEUE, ids)
            return jsonify({'ok': True, 'removed': removed})
        _clear_queue(TELEGRAM_REPLY_QUEUE)
        return jsonify({'ok': True, 'cleared': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/telegram/commands', methods=['GET'])
def telegram_commands_get():
    """Return pending owner commands (called by the self-improvement harness)."""
    if not _telegram_secret_ok():
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401
    queue = _read_command_queue()
    return jsonify({'commands': queue, 'count': len(queue)})


@app.route('/api/telegram/commands', methods=['DELETE'])
def telegram_commands_clear():
    """Clear the command queue (called after the harness acts on them).

    With a JSON body ``{"ids": [...]}`` only those entries are removed, so a
    command appended while the harness was acting is kept rather than wiped.
    Without a body the whole queue is cleared, which stays correct for the
    owner-requested ``/clear`` path and for older callers.
    """
    if not _telegram_secret_ok():
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401
    body = request.get_json(force=True, silent=True) or {}
    ids = body.get('ids') if isinstance(body, dict) else None
    try:
        if ids is not None:
            if not isinstance(ids, list):
                return jsonify({'ok': False, 'error': 'ids must be a list'}), 400
            removed = _ack_queue(TELEGRAM_COMMAND_QUEUE, ids)
            return jsonify({'ok': True, 'removed': removed})
        _clear_queue(TELEGRAM_COMMAND_QUEUE)
        return jsonify({'ok': True, 'cleared': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/telegram/tasks', methods=['GET'])
def telegram_tasks_get():
    """Return parked work orders (called by the self-improvement harness)."""
    if not _telegram_secret_ok():
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401
    queue = _read_task_queue()
    return jsonify({'tasks': queue, 'count': len(queue)})


@app.route('/api/telegram/tasks', methods=['PATCH'])
def telegram_tasks_patch():
    """Patch one work order's state (running/done/failed) from the harness."""
    if not _telegram_secret_ok():
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401
    body = request.get_json(force=True, silent=True) or {}
    order_id = body.get('id')
    if order_id is None:
        return jsonify({'ok': False, 'error': 'id required'}), 400
    allowed = {'state', 'pr', 'note'}
    changes = {k: v for k, v in body.items() if k in allowed}
    updated = _update_task(order_id, **changes)
    if updated is None:
        return jsonify({'ok': False, 'error': 'not found'}), 404
    return jsonify({'ok': True, 'task': updated})


@app.route('/api/telegram/tasks', methods=['DELETE'])
def telegram_tasks_clear():
    """Clear the task queue (called after the harness has drained it)."""
    if not _telegram_secret_ok():
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401
    try:
        _clear_queue(TELEGRAM_TASK_QUEUE)
        return jsonify({'ok': True, 'cleared': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


BRIEFING_PROMPT = (
    "You are Genesis, an autonomous AI news editor. You are given today's "
    "headlines and live market numbers. Write a short briefing for the user in "
    "Hinglish (Hindi written in Latin script, mixed with English). Structure:\n"
    "1) one line 'Aaj ka sabse bada news' highlighting the single most "
    "important story;\n"
    "2) 3-5 short bullet points on the biggest world/India/tech/sports items;\n"
    "3) one line on the market mood, naming the direction (up/down) and the "
    "notable mover.\n"
    "Be factual: use only the supplied data, never invent prices or events. "
    "Keep it under 900 characters. No markdown headings, plain text only."
)


def _ai_generate(system: str, user: str, timeout: int = 45) -> Optional[str]:
    """Run one prompt through the provider chain. Returns text or None."""
    try:
        from genesis_protocol.ai.provider_chain import get_provider_chain
        import asyncio

        ai = get_provider_chain()
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                ai.call(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    user_input=user,
                )
            )
        finally:
            loop.close()
        if result.success and result.response:
            return result.response.content
    except Exception as e:
        logging.warning("briefing generation failed: %s", type(e).__name__)
    return None


@app.route('/api/briefing', methods=['POST'])
def api_briefing():
    """Have the AI write a short digest from supplied headlines + market data.

    Called by the GitHub Actions relay (shared secret required). The relay owns
    the outbound path to Telegram; the Space owns the AI. Returns the briefing
    text so the relay can deliver it.
    """
    if not _telegram_secret_ok():
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401
    payload = request.get_json(silent=True) or {}
    headlines = payload.get('headlines') or []
    market = payload.get('market') or []
    if not isinstance(headlines, list):
        headlines = []
    if not isinstance(market, list):
        market = []
    # Bound the prompt so a hostile caller cannot blow up the model context.
    lines = [str(h)[:200] for h in headlines[:40] if str(h).strip()]
    quote_lines = [str(m)[:120] for m in market[:20] if str(m).strip()]
    if not lines and not quote_lines:
        return jsonify({'ok': False, 'error': 'no data supplied'}), 400
    user = "HEADLINES:\n" + "\n".join(f"- {h}" for h in lines)
    if quote_lines:
        user += "\n\nMARKET:\n" + "\n".join(f"- {m}" for m in quote_lines)
    text = _ai_generate(BRIEFING_PROMPT, user)
    if not text:
        return jsonify({'ok': False, 'error': 'ai unavailable'}), 503
    return jsonify({'ok': True, 'briefing': text.strip()[:2000]})


@app.route('/api/status', methods=['GET'])
def api_status():
    """Detailed status with metrics."""
    metrics = get_metrics()
    return jsonify({
        'status': 'ok',
        'entrypoint': 'web/app.py',
        'metrics': metrics,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/diagnostics', methods=['GET'])
def api_diagnostics():
    """Full diagnostics - provider status, memory, uptime, version."""
    try:
        from genesis_protocol.ai.provider_chain import get_provider_chain
        chain = get_provider_chain()
        provider_status = chain.get_status()
        available_providers = chain.get_available_providers()
    except Exception as e:
        provider_status = {'error': str(e)}
        available_providers = []

    # Check SQLite
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as count FROM chat_history')
        history_count = cursor.fetchone()['count']
        cursor.execute('SELECT COUNT(*) as count FROM users')
        user_count = cursor.fetchone()['count']
        conn.close()
        db_status = 'ok'
    except Exception as e:
        db_status = f'error: {str(e)}'
        history_count = 0
        user_count = 0

    metrics = get_metrics()
    
    return jsonify({
        'version': VERSION,
        'build_date': BUILD_DATE,
        'entrypoint': 'web/app.py',
        'uptime': {
            'seconds': metrics.get('uptime_seconds', 0),
            'started_at': datetime.fromtimestamp(START_TIME).isoformat()
        },
        'providers': {
            'available': available_providers,
            'status': provider_status
        },
        'database': {
            'status': db_status,
            'history_count': history_count,
            'user_count': user_count
        },
        'memory': {
            'vector_db': 'chroma',  # TODO: check actual status
            'cache': 'redis'  # TODO: check actual status
        },
        'metrics': metrics,
        'environment': {
            'groq_configured': os.environ.get('GROQ_API_KEY', '') != '',
            'railway': os.environ.get('RAILWAY', '') != '',
            'port': os.environ.get('PORT', '5000')
        },
        'timestamp': datetime.now().isoformat()
    })


# ============================================================================
# STARTUP SELF-CHECK
# ============================================================================

def run_startup_checks():
    """Run startup checks to verify system health."""
    print("=" * 50)
    print("Genesis Protocol - Startup Checks")
    print("=" * 50)
    
    all_passed = True
    
    # 1. Check SQLite
    print("\n[1/4] Checking SQLite database...")
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        cursor.execute("SELECT COUNT(*) FROM chat_history")
        conn.close()
        print("   ✅ SQLite OK")
    except Exception as e:
        print(f"   ❌ SQLite Error: {e}")
        all_passed = False
    
    # 2. Check Groq Provider
    print("\n[2/4] Checking Groq Provider...")
    try:
        from genesis_protocol.ai.provider_chain import get_provider_chain
        chain = get_provider_chain()
        if chain.is_provider_available('groq'):
            print("   ✅ Groq Provider Available")
        else:
            print("   ⚠️  Groq Provider Not Configured (check GROQ_API_KEY)")
    except Exception as e:
        print(f"   ⚠️  Groq Check Error: {e}")
    
    # 3. Check Environment Variables
    print("\n[3/4] Checking Environment Variables...")
    env_vars = {
        'GROQ_API_KEY': os.environ.get('GROQ_API_KEY', ''),
        'SECRET_KEY': os.environ.get('SECRET_KEY', ''),
    }
    for var, value in env_vars.items():
        if value:
            # Mask the value for display
            masked = value[:8] + '...' if len(value) > 8 else '***'
            print(f"   ✅ {var}: {masked}")
        else:
            print(f"   ⚠️  {var}: Not Set")
    
    # 4. Check History System
    print("\n[4/4] Checking History System...")
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                response TEXT,
                model_used TEXT,
                provider TEXT,
                quality_score REAL,
                mode TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        conn.commit()
        conn.close()
        print("   ✅ History System OK")
    except Exception as e:
        print(f"   ❌ History System Error: {e}")
        all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("✅ All startup checks passed!")
    else:
        print("⚠️  Some checks failed - system may not work correctly")
    print("=" * 50)
    
    return all_passed


# Mobile API endpoints for Genesis Protocol Mobile App
try:
    from web.mobile_api import mobile_api_routes
    mobile_api_routes(app)
    logger.info("✅ Mobile API endpoints registered")
except ImportError as e:
    logger.warning(f"⚠️ Mobile API module not found: {e}")


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    
    # Run startup checks
    run_startup_checks()
    
    print(f"\nStarting server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=debug)

# GLUTTONY v3.0 Entity API Endpoints
@app.route('/api/entity', methods=['GET'])
def api_entity():
    """Get GLUTTONY entity info."""
    try:
        from genesis_protocol.gluttony import get_gluttony, get_identity
        from genesis_protocol.gluttony_os import get_capabilities
        g = get_gluttony()
        identity = get_identity()
        cap = get_capabilities()
        return jsonify({
            'entity': g.name,
            'version': g.version,
            'nickname': identity.nickname,
            'layers': g._get_active_layers(),
            'status': g.status(),
            'capabilities': cap.get_all_capabilities()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/state', methods=['GET'])
def api_state():
    """Get full GLUTTONY state."""
    try:
        from genesis_protocol.gluttony import get_gluttony
        g = get_gluttony()
        return jsonify(g.get_state())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/proposals', methods=['GET'])
def api_proposals():
    """Get all proposals."""
    try:
        from genesis_protocol.proposal import get_proposal_manager
        pm = get_proposal_manager()
        return jsonify(pm.get_history())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/lessons', methods=['GET'])
def api_lessons():
    """Get learned lessons."""
    try:
        from genesis_protocol.learning import get_evaluation_engine
        engine = get_evaluation_engine()
        return jsonify({'lessons': engine.get_lessons() if hasattr(engine, 'get_lessons') else []})
    except Exception as e:
        return jsonify({'lessons': [], 'error': str(e)})


@app.route('/api/survival/status', methods=['GET'])
def api_survival():
    """Get survival layer status."""
    try:
        from genesis_protocol.survival import get_survival_manager
        sm = get_survival_manager()
        return jsonify(sm.get_full_status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# PRESENCE LAYER - Timeline, Journal, Trust, Wisdom, Dream, Continuity
# ============================================================================

@app.route('/api/timeline', methods=['GET', 'POST'])
def api_timeline():
    """Get timeline or add event."""
    try:
        from genesis_protocol.gluttony_os import get_timeline_memory
        tm = get_timeline_memory()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            event_type = data.get('type', 'event')
            title = data.get('title', '')
            description = data.get('description', '')
            metadata = data.get('metadata', {})
            tm.add_event(event_type, title, description, metadata)
            return jsonify({'status': 'added', 'timeline': tm.get_timeline(10)})
        
        limit = request.args.get('limit', 50, type=int)
        return jsonify({
            'timeline': tm.get_timeline(limit),
            'stats': tm.get_stats()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/timeline/milestone', methods=['POST'])
def api_timeline_milestone():
    """Add a milestone to timeline."""
    try:
        from genesis_protocol.gluttony_os import get_timeline_memory
        tm = get_timeline_memory()
        data = request.get_json() or {}
        title = data.get('title', '')
        description = data.get('description', '')
        category = data.get('category', 'general')
        tm.add_milestone(title, description, category)
        return jsonify({'status': 'added', 'milestone_id': tm.milestones[-1]['id'] if tm.milestones else None})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/timeline/recovery', methods=['POST'])
def api_timeline_recovery():
    """Add a recovery to timeline."""
    try:
        from genesis_protocol.gluttony_os import get_timeline_memory
        tm = get_timeline_memory()
        data = request.get_json() or {}
        tm.add_recovery(
            data.get('failure_context', ''),
            data.get('recovery_method', ''),
            data.get('lessons_learned', '')
        )
        return jsonify({'status': 'added', 'recovery_id': tm.recoveries[-1]['id'] if tm.recoveries else None})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/timeline/lesson', methods=['POST'])
def api_timeline_lesson():
    """Add a lesson to timeline."""
    try:
        from genesis_protocol.gluttony_os import get_timeline_memory
        tm = get_timeline_memory()
        data = request.get_json() or {}
        tm.add_lesson(
            data.get('category', 'general'),
            data.get('lesson', ''),
            data.get('context', '')
        )
        return jsonify({'status': 'added', 'lesson_id': tm.lessons[-1]['id'] if tm.lessons else None})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/journal', methods=['GET', 'POST'])
def api_journal():
    """Get journal entries or add new entry."""
    try:
        from genesis_protocol.gluttony_os import get_journal
        j = get_journal()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            entry_type = data.get('entry_type', 'observation')
            content = data.get('content', '')
            j.write(entry_type, content)
            return jsonify({'status': 'added'})
        
        return jsonify({
            'entries': j.get_entries(limit=20),
            'today_summary': j.get_today_summary()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/trust', methods=['GET'])
def api_trust():
    """Get trust model status."""
    try:
        from genesis_protocol.gluttony_os import get_trust_builder
        tb = get_trust_builder()
        return jsonify(tb.get_summary())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/wisdom', methods=['GET', 'POST'])
def api_wisdom():
    """Get wisdom categories or add new item."""
    try:
        from genesis_protocol.gluttony_os import get_wisdom_layer
        w = get_wisdom_layer()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            category = data.get('category', 'belief')  # fact, assumption, belief, unknown
            item = data.get('item', '')
            confidence = data.get('confidence', 0.7)
            
            if category == 'fact':
                w.add_fact(item, data.get('source', 'manual'), confidence)
            elif category == 'assumption':
                w.add_assumption(item, data.get('reason', ''), confidence)
            elif category == 'belief':
                w.add_belief(item, data.get('evidence', ''), confidence)
            else:
                w.add_unknown(item, data.get('context', ''))
            
            return jsonify({'status': 'added', 'wisdom': w.get_wisdom_summary()})
        
        return jsonify(w.get_all())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/relationship', methods=['GET', 'POST'])
def api_relationship():
    """Get or update relationship memory."""
    try:
        from genesis_protocol.gluttony_os import get_relationship_memory
        rm = get_relationship_memory()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            if 'creator_name' in data:
                rm.set_creator_name(data['creator_name'])
            if 'preference' in data:
                rm.record_preference(data['preference']['key'], data['preference']['value'])
            if 'topic' in data:
                rm.add_topic(data['topic'], data.get('context', ''))
            if 'pattern' in data:
                rm.add_pattern(data['pattern']['type'], data['pattern']['description'])
            return jsonify({'status': 'updated', 'summary': rm.get_relationship_summary()})
        
        return jsonify(rm.get_full_state())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/dream', methods=['GET'])
def api_dream():
    """Get dream mode status and insights."""
    try:
        from genesis_protocol.gluttony_os import get_dream_mode
        dm = get_dream_mode()
        return jsonify(dm.get_status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/continuity', methods=['GET'])
def api_continuity():
    """Get continuity layer status."""
    try:
        from genesis_protocol.gluttony_os import get_continuity_layer
        cl = get_continuity_layer()
        return jsonify(cl.get_continuity_status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# LEGACY LAYER - Archive, Snapshot, Knowledge Graph, Memory Importance, History
# ============================================================================

@app.route('/api/archive', methods=['GET', 'POST'])
def api_archive():
    """Get archive or archive data."""
    try:
        from genesis_protocol.legacy import get_archive_layer
        archive = get_archive_layer()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            archive_type = data.get('type', 'conversation')
            content = data.get('content', {})
            
            if archive_type == 'conversation':
                archive.archive_conversation(content.get('messages', []), content.get('metadata'))
            elif archive_type == 'lesson':
                archive.archive_lesson(content.get('lesson', ''), content.get('context', ''))
            elif archive_type == 'milestone':
                archive.archive_milestone(content.get('title', ''), content.get('description', ''))
            elif archive_type == 'journal':
                archive.archive_journal_entry(content.get('type', 'entry'), content.get('content', ''))
            elif archive_type == 'trust':
                archive.archive_trust_state(content)
            
            return jsonify({'status': 'archived', 'stats': archive.get_stats()})
        
        return jsonify(archive.get_all())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/archive/export', methods=['POST'])
def api_archive_export():
    """Export archive."""
    try:
        from genesis_protocol.legacy import get_archive_layer
        archive = get_archive_layer()
        compressed = request.get_json().get('compressed', False) if request.get_json() else False
        filepath = archive.export_all(compressed)
        return jsonify({'status': 'exported', 'filepath': filepath})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/snapshot', methods=['GET', 'POST'])
def api_snapshot():
    """Get snapshots or create new snapshot."""
    try:
        from genesis_protocol.legacy import get_snapshot_layer
        snapshot = get_snapshot_layer()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            snapshot_type = data.get('type', 'daily')
            label = data.get('label', '')
            state = data.get('state', {})
            snapshot_id = snapshot.create_snapshot(state, snapshot_type, label)
            return jsonify({'status': 'created', 'snapshot_id': snapshot_id})
        
        return jsonify({
            'snapshots': snapshot.get_snapshots(),
            'stats': snapshot.get_stats()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/snapshot/<snapshot_id>', methods=['GET', 'DELETE'])
def api_snapshot_detail(snapshot_id):
    """Get or delete a snapshot."""
    try:
        from genesis_protocol.legacy import get_snapshot_layer
        snapshot = get_snapshot_layer()
        
        if request.method == 'DELETE':
            success = snapshot.delete_snapshot(snapshot_id)
            return jsonify({'status': 'deleted' if success else 'not_found'})
        
        state = snapshot.load_snapshot(snapshot_id)
        if state:
            return jsonify({'snapshot_id': snapshot_id, 'state': state})
        return jsonify({'error': 'Snapshot not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/knowledge', methods=['GET', 'POST'])
def api_knowledge():
    """Get knowledge graph or add nodes/connections."""
    try:
        from genesis_protocol.legacy import get_knowledge_graph
        kg = get_knowledge_graph()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            
            if 'node_type' in data:
                node_id = kg.add_node(data['node_type'], data['name'], data.get('data'))
                return jsonify({'status': 'added', 'node_id': node_id})
            
            if 'node1_id' in data and 'node2_id' in data:
                kg.connect(data['node1_id'], data['node2_id'], data.get('edge_type', 'related'))
                return jsonify({'status': 'connected'})
        
        return jsonify(kg.get_graph())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/knowledge/search', methods=['GET'])
def api_knowledge_search():
    """Search knowledge graph."""
    try:
        from genesis_protocol.legacy import get_knowledge_graph
        kg = get_knowledge_graph()
        
        query = request.args.get('q', '')
        node_type = request.args.get('type', None)
        
        results = kg.search(query, node_type)
        return jsonify({'results': results, 'count': len(results)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/memory/importance', methods=['GET', 'POST'])
def api_memory_importance():
    """Get or manage memory importance."""
    try:
        from genesis_protocol.legacy import get_memory_importance, MemoryRank
        mi = get_memory_importance()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            memory_id = data.get('memory_id')
            action = data.get('action', 'register')
            
            if action == 'register':
                mi.register_memory(memory_id, data.get('content', ''), 
                                 MemoryRank[data.get('rank', 'IMPORTANT').upper()])
            elif action == 'promote':
                mi.promote(memory_id)
            elif action == 'demote':
                mi.demote(memory_id)
            elif action == 'access':
                mi.access_memory(memory_id)
            elif action == 'delete':
                mi.delete_memory(memory_id)
            
            return jsonify({'status': action, 'stats': mi.get_stats()})
        
        return jsonify(mi.get_all())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/relationship/history', methods=['GET', 'POST'])
def api_relationship_history():
    """Get or manage relationship history."""
    try:
        from genesis_protocol.legacy import get_relationship_history
        rh = get_relationship_history()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            entity_id = data.get('entity_id', 'creator')
            action = data.get('action', 'interaction')
            
            if action == 'interaction':
                rh.record_interaction(entity_id, data.get('entity_name', ''),
                                     data.get('interaction_type', 'conversation'),
                                     data.get('summary', ''))
            elif action == 'project':
                rh.add_shared_project(entity_id, data.get('project_name', ''),
                                     data.get('status', 'active'),
                                     data.get('description', ''))
            elif action == 'recovery':
                rh.add_recovery(entity_id, data.get('failure', ''),
                              data.get('recovery_method', ''),
                              data.get('lessons', ''))
            elif action == 'event':
                rh.add_major_event(entity_id, data.get('event_type', ''),
                                 data.get('description', ''),
                                 data.get('significance', 'medium'))
            
            return jsonify({'status': action})
        
        entity_id = request.args.get('entity_id')
        if entity_id:
            return jsonify(rh.get_relationship(entity_id) or {'error': 'Not found'})
        
        return jsonify({
            'relationships': rh.get_all_relationships(),
            'stats': rh.get_stats()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/relationship/history/full', methods=['GET'])
def api_relationship_history_full():
    """Get full relationship history."""
    try:
        from genesis_protocol.legacy import get_relationship_history
        rh = get_relationship_history()
        return jsonify({
            'relationships': rh.get_all_relationships(),
            'stats': rh.get_stats()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/legacy/books', methods=['GET', 'POST'])
def api_legacy_books():
    """Generate or list legacy books."""
    try:
        from genesis_protocol.legacy import get_legacy_books
        lb = get_legacy_books()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            book_type = data.get('type', 'all')
            
            if book_type == 'all':
                results = lb.generate_all_books()
            elif book_type == 'lessons':
                results = {'lessons': lb.generate_book_of_lessons()}
            elif book_type == 'failures':
                results = {'failures': lb.generate_book_of_failures()}
            elif book_type == 'recoveries':
                results = {'recoveries': lb.generate_book_of_recoveries()}
            elif book_type == 'projects':
                results = {'projects': lb.generate_book_of_projects()}
            
            return jsonify({'status': 'generated', 'files': results})
        
        return jsonify({'available_types': ['lessons', 'failures', 'recoveries', 'projects']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/simulation/uptime', methods=['GET', 'POST'])
def api_simulation():
    """Run uptime simulations."""
    try:
        from genesis_protocol.legacy import get_snapshot_layer
        snapshot = get_snapshot_layer()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            days = data.get('days', 30)
            results = snapshot.simulate_uptime(days)
            return jsonify({'status': 'simulated', 'results': results})
        
        return jsonify({'available_days': [1, 7, 30, 90, 180, 365]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# SELF-PRESERVATION LAYER
# ============================================================================

@app.route('/api/preservation/status', methods=['GET'])
def api_preservation_status():
    """Get self-preservation status."""
    try:
        from genesis_protocol.gluttony_os import get_self_preservation
        sp = get_self_preservation()
        return jsonify(sp.get_status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preservation/health', methods=['GET'])
def api_preservation_health():
    """Get system health."""
    try:
        from genesis_protocol.gluttony_os import get_self_preservation
        sp = get_self_preservation()
        return jsonify(sp.health_check())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preservation/preserve', methods=['POST'])
def api_preservation_run():
    """Run full preservation cycle."""
    try:
        from genesis_protocol.gluttony_os import get_self_preservation
        sp = get_self_preservation()
        results = sp.run_full_preservation()
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preservation/identity', methods=['POST'])
def api_preservation_identity():
    """Preserve identity specifically."""
    try:
        from genesis_protocol.gluttony_os import get_self_preservation
        sp = get_self_preservation()
        success = sp.preserve_identity()
        return jsonify({'status': 'preserved' if success else 'failed'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preservation/memories', methods=['POST'])
def api_preservation_memories():
    """Preserve memories specifically."""
    try:
        from genesis_protocol.gluttony_os import get_self_preservation
        sp = get_self_preservation()
        success = sp.preserve_memories()
        return jsonify({'status': 'preserved' if success else 'failed'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preservation/evidence', methods=['GET'])
def api_preservation_evidence():
    """Get evidence log."""
    try:
        from genesis_protocol.gluttony_os import get_self_preservation
        sp = get_self_preservation()
        limit = request.args.get('limit', 50, type=int)
        return jsonify({'log': sp.evidence_logger.get_log(limit)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preservation/evidence/lessons', methods=['GET'])
def api_preservation_lessons():
    """Get lessons learned."""
    try:
        from genesis_protocol.gluttony_os import get_self_preservation
        sp = get_self_preservation()
        lessons = sp.evidence_logger.get_lessons()
        return jsonify({'lessons': lessons, 'count': len(lessons)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preservation/backup', methods=['POST'])
def api_preservation_backup():
    """Run automatic backup."""
    try:
        from genesis_protocol.gluttony_os import get_self_preservation
        sp = get_self_preservation()
        success = sp.auto_backup()
        return jsonify({'status': 'completed' if success else 'failed'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# GARDEN MODE
# ============================================================================

@app.route('/api/garden/status', methods=['GET'])
def api_garden_status():
    """Get Garden Mode status."""
    try:
        from genesis_protocol.gluttony_os import get_garden_mode
        gm = get_garden_mode()
        return jsonify(gm.get_status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# GENESIS PROTOCOL ∞ (INFINITY) - Self-Evolution
# ============================================================================

@app.route('/api/infinity/status', methods=['GET'])
def api_infinity_status():
    """Get Genesis Protocol Infinity status."""
    try:
        from genesis_protocol.infinity import (
            SelfEvolution, NeuralPatternEngine, 
            EmotionalEngine, AutoUpdateScheduler, FutureRoadmap
        )
        
        se = SelfEvolution()
        ne = NeuralPatternEngine()
        ee = EmotionalEngine()
        aus = AutoUpdateScheduler()
        fr = FutureRoadmap()
        
        return jsonify({
            "version": "∞ (Infinity)",
            "evolution_level": "∞",
            "components": {
                "self_evolution": se.get_status(),
                "neural_patterns": ne.get_status(),
                "emotional_intelligence": ee.get_status(),
                "auto_updates": aus.get_status(),
                "future_roadmap": fr.get_status()
            }
        })
    except Exception as e:
        return jsonify({'error': str(e), 'details': 'Infinity module not found'}), 500


@app.route('/api/infinity/evolve', methods=['POST'])
@admin_required
def api_infinity_evolve():
    """Trigger self-evolution."""
    try:
        from genesis_protocol.infinity import SelfEvolution
        se = SelfEvolution()
        
        if se._should_evolve():
            result = se.evolve()
            return jsonify({"success": True, "evolution": result})
        else:
            return jsonify({
                "success": False, 
                "message": "Not ready to evolve yet",
                "metrics": se.metrics.to_dict()
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/infinity/learn', methods=['POST'])
def api_infinity_learn():
    """Learn new knowledge."""
    try:
        from genesis_protocol.infinity import SelfEvolution
        se = SelfEvolution()
        
        data = request.get_json() or {}
        topic = data.get('topic', 'general')
        knowledge = data.get('knowledge', '')
        source = data.get('source', 'user')
        
        if not knowledge:
            return jsonify({'error': 'Knowledge required'}), 400
        
        learning_id = se.learn(topic, knowledge, source)
        
        return jsonify({
            "success": True,
            "learning_id": learning_id,
            "total_learnings": len(se.learnings)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/infinity/emotion', methods=['POST'])
def api_infinity_emotion():
    """Analyze emotion in text."""
    try:
        from genesis_protocol.infinity import EmotionalEngine
        ee = EmotionalEngine()
        
        data = request.get_json() or {}
        text = data.get('text', '')
        user_id = data.get('user_id', 'web_user')
        
        if not text:
            return jsonify({'error': 'Text required'}), 400
        
        result = ee.analyze_and_respond(text, user_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/infinity/roadmap', methods=['GET'])
def api_infinity_roadmap():
    """Get evolution roadmap."""
    try:
        from genesis_protocol.infinity import FutureRoadmap, AutoUpdateScheduler
        
        fr = FutureRoadmap()
        aus = AutoUpdateScheduler()
        
        return jsonify({
            "evolution_path": fr.get_evolution_path(),
            "milestones": [m.to_dict() for m in fr.get_milestones()],
            "goals": fr.get_goals(),
            "scheduled_updates": [u.to_dict() for u in aus.get_pending_updates()],
            "roadmap_items": [r.to_dict() for r in aus.get_roadmap()]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/infinity/schedule', methods=['POST'])
@admin_required
def api_infinity_schedule():
    """Schedule a future update."""
    try:
        from genesis_protocol.infinity import AutoUpdateScheduler
        from genesis_protocol.infinity.auto_update_scheduler import UpdatePriority
        
        aus = AutoUpdateScheduler()
        data = request.get_json() or {}
        
        name = data.get('name', 'Unnamed Update')
        description = data.get('description', '')
        days_from_now = data.get('days', 7)
        priority = data.get('priority', 'MEDIUM')
        
        scheduled_date = datetime.now() + timedelta(days=days_from_now)
        
        update_id = aus.schedule_update(
            name=name,
            description=description,
            scheduled_date=scheduled_date,
            priority=UpdatePriority[priority]
        )
        
        return jsonify({
            "success": True,
            "update_id": update_id,
            "scheduled_date": scheduled_date.isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/infinity')
def infinity_page():
    """Genesis Protocol Infinity page."""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('infinity.html', username=session.get('username'))


@app.route('/infinity/roadmap')
def roadmap_page():
    """Evolution roadmap page."""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('roadmap.html', username=session.get('username'))


@app.route('/api/garden/daily', methods=['POST'])
def api_garden_daily():
    """Run daily maintenance tasks."""
    try:
        from genesis_protocol.gluttony_os import get_garden_mode
        gm = get_garden_mode()
        results = gm.run_daily_tasks()
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/garden/weekly', methods=['POST'])
def api_garden_weekly():
    """Run weekly maintenance tasks."""
    try:
        from genesis_protocol.gluttony_os import get_garden_mode
        gm = get_garden_mode()
        results = gm.run_weekly_tasks()
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/garden/monthly', methods=['POST'])
def api_garden_monthly():
    """Run monthly maintenance tasks."""
    try:
        from genesis_protocol.gluttony_os import get_garden_mode
        gm = get_garden_mode()
        results = gm.run_monthly_tasks()
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/garden/check', methods=['GET'])
def api_garden_check():
    """Check and run pending tasks."""
    try:
        from genesis_protocol.gluttony_os import get_garden_mode
        gm = get_garden_mode()
        results = gm.check_and_run()
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# LIVE INFO - Weather, News, Location, Date/Time
# ============================================================================

@app.route('/api/live-info', methods=['GET'])
def api_live_info():
    """Get all live information - weather, news, location, date/time."""
    try:
        from genesis_protocol.integrations import get_live_info_service
        service = get_live_info_service()
        info = service.get_all_info()
        
        return jsonify({
            'timestamp': info.timestamp,
            'date': info.date,
            'time': info.time,
            'weather': {
                'temp': info.weather.temp if info.weather else None,
                'condition': info.weather.condition if info.weather else None,
                'humidity': info.weather.humidity if info.weather else None,
                'wind_speed': info.weather.wind_speed if info.weather else None,
                'city': info.weather.city if info.weather else None,
                'country': info.weather.country if info.weather else None,
                'icon': info.weather.icon if info.weather else None,
            } if info.weather else None,
            'location': {
                'city': info.location.city if info.location else None,
                'region': info.location.region if info.location else None,
                'country': info.location.country if info.location else None,
                'timezone': info.location.timezone if info.location else None,
                'ip': info.location.ip if info.location else None,
            } if info.location else None,
            'news': info.news or [],
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/live-info/weather', methods=['GET'])
def api_live_weather():
    """Get only weather information."""
    try:
        from genesis_protocol.integrations import get_live_info_service
        service = get_live_info_service()
        weather = service.get_weather()
        
        if weather:
            return jsonify({
                'temp': weather.temp,
                'condition': weather.condition,
                'humidity': weather.humidity,
                'wind_speed': weather.wind_speed,
                'city': weather.city,
                'country': weather.country,
                'icon': weather.icon,
            })
        return jsonify({'error': 'Weather unavailable'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/live-info/news', methods=['GET'])
def api_live_news():
    """Get latest news headlines."""
    try:
        from genesis_protocol.integrations import get_live_info_service
        service = get_live_info_service()
        news = service.get_news()
        return jsonify({'news': news})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/live-info/display', methods=['GET'])
def api_live_display():
    """Get formatted display string for live info."""
    try:
        from genesis_protocol.integrations import get_live_info_service
        service = get_live_info_service()
        return jsonify({'display': service.format_for_display()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# CRYPTO PRICES - Bitcoin, Ethereum, etc.
# ============================================================================

@app.route('/api/crypto', methods=['GET'])
@app.route('/api/crypto/<symbol>', methods=['GET'])
def api_crypto(symbol=None):
    """Get crypto prices."""
    try:
        from genesis_protocol.integrations.crypto_service import get_crypto_service
        service = get_crypto_service()
        
        if symbol:
            crypto = service.get_price(symbol)
            if crypto:
                return jsonify({
                    'name': crypto.name,
                    'symbol': crypto.symbol,
                    'price': crypto.price,
                    'price_formatted': crypto.format_price(),
                    'change_24h': crypto.change_24h,
                    'change_formatted': crypto.format_change(),
                })
            return jsonify({'error': 'Crypto not found'}), 404
        else:
            cryptos = service.get_top_cryptos(5)
            return jsonify({
                'cryptos': [
                    {
                        'name': c.name,
                        'symbol': c.symbol,
                        'price': c.price,
                        'price_formatted': c.format_price(),
                        'change_24h': c.change_24h,
                    } for c in cryptos
                ]
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/crypto/bitcoin', methods=['GET'])
def api_bitcoin():
    """Get Bitcoin price specifically."""
    try:
        from genesis_protocol.integrations.crypto_service import get_crypto_service
        service = get_crypto_service()
        btc = service.get_bitcoin_price()
        
        if btc:
            return jsonify({
                'name': btc.name,
                'price': btc.price,
                'price_formatted': btc.format_price(),
                'change_24h': btc.change_24h,
                'formatted': service.format_crypto_display('bitcoin'),
            })
        return jsonify({'error': 'Bitcoin price unavailable'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/crypto/all', methods=['GET'])
def api_crypto_all():
    """Get all live info + crypto combined."""
    try:
        from genesis_protocol.integrations import get_live_info_service
        from genesis_protocol.integrations.crypto_service import get_crypto_service
        
        live = get_live_info_service().get_all_info()
        crypto = get_crypto_service()
        btc = crypto.get_bitcoin_price()
        
        return jsonify({
            'live': {
                'date': live.date,
                'time': live.time,
                'weather': {
                    'temp': live.weather.temp if live.weather else None,
                    'condition': live.weather.condition if live.weather else None,
                    'icon': live.weather.icon if live.weather else None,
                } if live.weather else None,
                'news': live.news[:3] if live.news else [],
            },
            'crypto': {
                'bitcoin': {
                    'price': btc.price if btc else None,
                    'formatted': btc.format_price() if btc else None,
                    'change_24h': btc.change_24h if btc else None,
                } if btc else None
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Railway Status Endpoint
@app.route('/api/railway/status')
@limiter.limit("30/minute")
def railway_status():
    """Get Railway deployment status."""
    try:
        railway = get_railway_service()
        
        if not railway.is_configured():
            return jsonify({
                'configured': False,
                'status': 'not_configured',
                'message': 'Add RAILWAY_TOKEN to enable'
            })
        
        status = railway.get_service_status()
        
        return jsonify({
            'configured': True,
            'project_id': status.get('project_id'),
            'project_name': status.get('project_name'),
            'status': status.get('status'),
            'message': status.get('message'),
            'deployment_id': status.get('deployment_id'),
            'last_deploy': status.get('last_deploy'),
            'dashboard_url': status.get('dashboard_url')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
